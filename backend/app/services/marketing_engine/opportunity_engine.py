"""MarketingOpportunityEngine — Hauptorchestrator.

Führt alle Detektoren aus, erzeugt Sales Pitches, matcht Produkte,
persistiert Opportunities und liefert CRM-fähiges JSON.
"""

from __future__ import annotations
from datetime import datetime, timedelta
import time
from typing import Any
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import AuditLog, BacktestRun, MarketingOpportunity
from app.services.media.ai_campaign_planner import AiCampaignPlanner
from app.services.media.campaign_guardrails import CampaignGuardrails
from app.services.media.message_library import select_gelo_message_pack
from app.services.media.product_catalog_service import ProductCatalogService
from app.services.media.ranking_signal_service import RankingSignalService
from app.services.media.playbook_engine import PlaybookEngine

from .detectors.market_supply_monitor import MarketSupplyMonitor
from .detectors.predictive_sales_spike import PredictiveSalesSpikeDetector
from .detectors.resource_scarcity import ResourceScarcityDetector
from .detectors.weather_forecast import WeatherForecastDetector
from .opportunity_engine_constants import (
    FORECAST_PLAYBOOK_MAP,
)
from . import opportunity_engine_generation
from .opportunity_engine_campaigns import (
    export_crm_json as export_crm_json_impl,
    update_campaign as update_campaign_impl,
    update_status as update_status_impl,
)
from .opportunity_engine_campaign_planning import (
    build_channel_mix as build_channel_mix_impl,
    build_channel_plan as build_channel_plan_impl,
    build_measurement_plan as build_measurement_plan_impl,
    derive_activation_window as derive_activation_window_impl,
    derive_activation_window_from_days as derive_activation_window_from_days_impl,
    derive_campaign_name as derive_campaign_name_impl,
)
from .opportunity_engine_helpers import (
    canonical_brand,
    clean_for_output,
    confidence_pct,
    derive_peix_context,
    derive_ranking_signal_context,
    extract_region_codes_from_opportunity,
    fact_label,
    normalize_region_token,
    normalize_workflow_status,
    parse_iso_datetime,
    public_fact_value,
    region_label,
    secondary_products,
    status_filter_values,
)
from .opportunity_engine_maintenance import (
    backfill_peix_context as backfill_peix_context_impl,
    backfill_product_mapping as backfill_product_mapping_impl,
    save_opportunity as save_opportunity_impl,
)
from .opportunity_engine_playbooks import (
    build_campaign_pack as build_campaign_pack_impl,
    campaign_preview_from_payload as campaign_preview_from_payload_impl,
    enrich_opportunity_for_media as enrich_opportunity_for_media_impl,
    ensure_synthetic_opportunity_row as ensure_synthetic_opportunity_row_impl,
    generate_legacy_action_cards as generate_legacy_action_cards_impl,
    generate_playbook_ai_cards as generate_playbook_ai_cards_impl,
    get_playbook_catalog as get_playbook_catalog_impl,
    merge_ai_playbook_payload as merge_ai_playbook_payload_impl,
    regenerate_ai_plan as regenerate_ai_plan_impl,
    synthetic_playbook_opportunity as synthetic_playbook_opportunity_impl,
)
from .opportunity_engine_presenters import (
    build_decision_brief as build_decision_brief_impl,
    decision_facts as decision_facts_impl,
    model_to_dict as model_to_dict_impl,
)
from .opportunity_engine_queries import (
    count_opportunities as count_opportunities_impl,
    get_opportunities as get_opportunities_impl,
    get_recommendation_by_id as get_recommendation_by_id_impl,
    get_stats as get_stats_impl,
)
from .opportunity_engine_retrospective import (
    get_roi_retrospective as get_roi_retrospective_impl,
)
from .pitch_generator import PitchGenerator
from .product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SYSTEM_VERSION = "ViralFlux-Media-v3.0"
settings = get_settings()


class MarketingOpportunityEngine:
    """Orchestriert alle Opportunity-Detektoren und CRM-Output."""

    def __init__(self, db: Session):
        self.db = db
        self.detectors = [
            ResourceScarcityDetector(db),
            MarketSupplyMonitor(db),
            PredictiveSalesSpikeDetector(db),
            WeatherForecastDetector(db),
        ]
        self.pitch_generator = PitchGenerator()
        self.product_matcher = ProductMatcher(db)
        self.product_catalog_service = ProductCatalogService(db)
        self.playbook_engine = PlaybookEngine(db)
        self.ai_planner = AiCampaignPlanner()
        self.guardrails = CampaignGuardrails()

    def _latest_market_backtest(
        self,
        *,
        virus_typ: str | None = None,
        target_source: str | None = None,
    ) -> BacktestRun | None:
        """Return the latest successful market backtest for the requested context."""
        query = self.db.query(BacktestRun).filter(
            BacktestRun.status == "success",
            BacktestRun.mode == "MARKET_CHECK",
        )
        if virus_typ:
            query = query.filter(BacktestRun.virus_typ == virus_typ)
        if target_source:
            query = query.filter(
                func.upper(BacktestRun.target_source) == str(target_source).strip().upper()
            )
        return query.order_by(BacktestRun.created_at.desc()).first()

    @staticmethod
    def _market_backtest_is_ready(backtest: BacktestRun | None) -> bool:
        if not backtest or not backtest.metrics:
            return False
        quality_gate = backtest.metrics.get("quality_gate") or {}
        return bool(quality_gate.get("overall_passed") and quality_gate.get("lead_passed", False))

    @staticmethod
    def _derive_playbook_workflow_status(peix_score: float, model_ready: bool) -> str:
        return MarketingOpportunityEngine._derive_activation_workflow_status(peix_score, model_ready)

    @staticmethod
    def _derive_activation_workflow_status(ranking_signal_score: float, model_ready: bool) -> str:
        return "READY" if (ranking_signal_score >= 80.0 and model_ready) else "DRAFT"

    @staticmethod
    def _extract_improvement_vs_baselines(imp: dict | None) -> tuple[float, float]:
        """Liest MAE-Verbesserung aus neuem oder legacy improvement-Schema."""
        if not imp:
            return 0.0, 0.0

        persistence_val = imp.get("mae_vs_persistence_pct")
        seasonal_val = imp.get("mae_vs_seasonal_pct")

        # Backward compatibility for legacy nested schema.
        if persistence_val is None:
            persistence_val = imp.get("persistence", {}).get("mae_improvement_pct", 0)
        if seasonal_val is None:
            seasonal_val = imp.get("seasonal_naive", {}).get("mae_improvement_pct", 0)

        return float(persistence_val or 0.0), float(seasonal_val or 0.0)

    @staticmethod
    def _select_forecast_playbook_key(virus_typ: str) -> str:
        return FORECAST_PLAYBOOK_MAP.get(virus_typ, "ERKAELTUNGSWELLE")

    def _secondary_modifier_from_opportunities(
        self,
        *,
        opportunities: list[dict[str, Any]],
        region_code: str,
    ) -> tuple[float, list[dict[str, Any]]]:
        return opportunity_engine_generation._secondary_modifier_from_opportunities(
            self,
            opportunities=opportunities,
            region_code=region_code,
        )

    def _forecast_first_candidates(
        self,
        *,
        opportunities: list[dict[str, Any]],
        brand: str,
        virus_typ: str,
        region_scope: list[str] | None,
        max_cards: int,
    ) -> list[dict[str, Any]]:
        return opportunity_engine_generation._forecast_first_candidates(
            self,
            opportunities=opportunities,
            brand=brand,
            virus_typ=virus_typ,
            region_scope=region_scope,
            max_cards=max_cards,
        )

    def generate_opportunities(self) -> dict:
        return opportunity_engine_generation.generate_opportunities(self)

    @staticmethod
    def _deduplicate_signals(opportunities: list[dict]) -> list[dict]:
        return opportunity_engine_generation._deduplicate_signals(opportunities)

    @staticmethod
    def _apply_supply_gap_priority_multipliers(opportunities: list[dict]) -> list[dict]:
        return opportunity_engine_generation._apply_supply_gap_priority_multipliers(opportunities)

    def _kreis_bundesland(self, kreis_name: str) -> str:
        return opportunity_engine_generation._kreis_bundesland(self, kreis_name)

    def _enrich_kreis_targeting(self, opportunities: list[dict]) -> list[dict]:
        return opportunity_engine_generation._enrich_kreis_targeting(self, opportunities)

    def get_opportunities(
        self,
        type_filter: str | None = None,
        status_filter: str | None = None,
        brand_filter: str | None = None,
        min_urgency: float | None = None,
        limit: int = 50,
        skip: int = 0,
        normalize_status: bool = True,
    ) -> list[dict]:
        return get_opportunities_impl(
            self,
            type_filter=type_filter,
            status_filter=status_filter,
            brand_filter=brand_filter,
            min_urgency=min_urgency,
            limit=limit,
            skip=skip,
            normalize_status=normalize_status,
        )

    def count_opportunities(
        self,
        type_filter: str | None = None,
        status_filter: str | None = None,
        brand_filter: str | None = None,
        min_urgency: float | None = None,
    ) -> int:
        return count_opportunities_impl(
            self,
            type_filter=type_filter,
            status_filter=status_filter,
            brand_filter=brand_filter,
            min_urgency=min_urgency,
        )

    def get_recommendation_by_id(self, opportunity_id: str) -> dict | None:
        return get_recommendation_by_id_impl(self, opportunity_id)

    def generate_action_cards(
        self,
        *,
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        channel_pool: list[str] | None = None,
        region_scope: list[str] | None = None,
        strategy_mode: str = "PLAYBOOK_AI",
        max_cards: int = 4,
        virus_typ: str = "Influenza A",
    ) -> dict:
        """Erzeugt strukturierte Media-Action-Cards für das Cockpit."""
        normalized_mode = str(strategy_mode or "PLAYBOOK_AI").upper()
        generation = self.generate_opportunities()
        opportunities = generation.get("opportunities", [])
        if normalized_mode == "PLAYBOOK_AI" and settings.MEDIA_AI_PLAYBOOKS_ENABLED:
            playbook_cards = self._generate_playbook_ai_cards(
                opportunities=opportunities,
                brand=brand,
                product=product,
                campaign_goal=campaign_goal,
                weekly_budget=weekly_budget,
                region_scope=region_scope,
                max_cards=max_cards,
                virus_typ=virus_typ,
            )
            if playbook_cards:
                playbook_cards.sort(
                    key=lambda x: (float(x.get("urgency_score") or 0.0), float(x.get("confidence") or 0.0)),
                    reverse=True,
                )
                top_card_id = playbook_cards[0]["id"] if playbook_cards else None
                return {
                    "meta": {
                        **generation.get("meta", {}),
                        "strategy_mode": normalized_mode,
                        "cards_generated": len(playbook_cards),
                    },
                    "cards": playbook_cards,
                    "total_cards": len(playbook_cards),
                    "top_card_id": top_card_id,
                    "auto_open_url": f"/kampagnen/{top_card_id}" if top_card_id else None,
                }

        legacy = self._generate_legacy_action_cards(
            opportunities=opportunities,
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            weekly_budget=weekly_budget,
            channel_pool=channel_pool,
            region_scope=region_scope,
        )
        legacy_meta = legacy.get("meta", {})
        legacy_meta["strategy_mode"] = normalized_mode if normalized_mode != "PLAYBOOK_AI" else "LEGACY_FALLBACK"
        legacy["meta"] = legacy_meta
        return legacy

    def _generate_playbook_ai_cards(
        self,
        *,
        opportunities: list[dict[str, Any]],
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        region_scope: list[str] | None,
        max_cards: int,
        virus_typ: str,
    ) -> list[dict[str, Any]]:
        return generate_playbook_ai_cards_impl(
            self,
            opportunities=opportunities,
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            weekly_budget=weekly_budget,
            region_scope=region_scope,
            max_cards=max_cards,
            virus_typ=virus_typ,
        )

    def _generate_legacy_action_cards(
        self,
        *,
        opportunities: list[dict[str, Any]],
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        channel_pool: list[str] | None,
        region_scope: list[str] | None,
    ) -> dict[str, Any]:
        return generate_legacy_action_cards_impl(
            self,
            opportunities=opportunities,
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            weekly_budget=weekly_budget,
            channel_pool=channel_pool,
            region_scope=region_scope,
        )

    @staticmethod
    def _select_product_for_opportunity(
        *,
        fallback_product: str,
        product_mapping: dict[str, Any],
    ) -> str:
        status = str(product_mapping.get("mapping_status") or "").strip().lower()
        if status == "approved":
            recommended = product_mapping.get("recommended_product")
            if recommended:
                return str(recommended)

        # Multi-Produkt-Modus: wenn kein fixes Produkt vorgegeben, bestes
        # Candidate-Produkt aus dem Mapping verwenden (auch bei needs_review).
        is_multi = not fallback_product or "alle" in fallback_product.lower()
        if is_multi:
            candidate = product_mapping.get("candidate_product")
            if candidate:
                return str(candidate)
            # Fallback: SEED_PRODUCTS-Katalog nach condition_key durchsuchen
            condition_key = product_mapping.get("condition_key")
            if condition_key:
                from app.services.marketing_engine.product_matcher import SEED_PRODUCTS
                for seed in SEED_PRODUCTS:
                    if condition_key in seed.get("applicable_conditions", []):
                        return seed["name"]

        if status == "not_applicable":
            return fallback_product or "Produktfreigabe ausstehend"

        return "Produktfreigabe ausstehend"

    def backfill_peix_context(self, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        return backfill_peix_context_impl(self, force=force, limit=limit)

    def backfill_product_mapping(self, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        return backfill_product_mapping_impl(self, force=force, limit=limit)

    def update_campaign(
        self,
        opportunity_id: str,
        *,
        activation_window: dict | None = None,
        budget: dict | None = None,
        channel_plan: list[dict] | None = None,
        kpi_targets: dict | None = None,
    ) -> dict:
        return update_campaign_impl(
            self,
            opportunity_id,
            activation_window=activation_window,
            budget=budget,
            channel_plan=channel_plan,
            kpi_targets=kpi_targets,
        )

    def get_playbook_catalog(self) -> dict[str, Any]:
        return get_playbook_catalog_impl(self)

    def regenerate_ai_plan(self, opportunity_id: str) -> dict[str, Any]:
        return regenerate_ai_plan_impl(self, opportunity_id)

    def update_status(
        self,
        opportunity_id: str,
        new_status: str,
        *,
        dismiss_reason: str | None = None,
        dismiss_comment: str | None = None,
    ) -> dict:
        return update_status_impl(
            self,
            opportunity_id,
            new_status,
            dismiss_reason=dismiss_reason,
            dismiss_comment=dismiss_comment,
        )

    def export_crm_json(self, opportunity_ids: list[str] | None = None) -> dict:
        return export_crm_json_impl(self, opportunity_ids, system_version=SYSTEM_VERSION)

    def get_stats(self) -> dict:
        return get_stats_impl(self)

    def get_roi_retrospective(self) -> dict:
        return get_roi_retrospective_impl(self)

    def _save_opportunity(self, opp: dict) -> bool:
        return save_opportunity_impl(self, opp)

    def _build_channel_mix(self, channels: list[str], opportunity_type: str, urgency: float) -> dict:
        return build_channel_mix_impl(channels, opportunity_type, urgency)

    def _derive_campaign_name(self, brand: str, product: str, region: str, opportunity_type: str) -> str:
        return derive_campaign_name_impl(brand, product, region, opportunity_type)

    def _derive_activation_window(self, urgency: float) -> dict:
        return derive_activation_window_impl(urgency)

    def _build_channel_plan(
        self,
        channel_mix: dict[str, float],
        budget_shift_value: float,
        campaign_goal: str,
    ) -> list[dict[str, Any]]:
        return build_channel_plan_impl(channel_mix, budget_shift_value, campaign_goal)

    def _build_measurement_plan(self, campaign_goal: str, channel_plan: list[dict]) -> dict:
        return build_measurement_plan_impl(campaign_goal, channel_plan)

    @staticmethod
    def _derive_activation_window_from_days(days: int) -> dict[str, Any]:
        return derive_activation_window_from_days_impl(days)

    def _synthetic_playbook_opportunity(
        self,
        *,
        playbook_key: str,
        region_code: str,
        region_label: str,
        candidate: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        return synthetic_playbook_opportunity_impl(
            self,
            playbook_key=playbook_key,
            region_code=region_code,
            region_label=region_label,
            candidate=candidate,
            now=now,
        )

    def _ensure_synthetic_opportunity_row(
        self,
        *,
        synthetic_opportunity: dict[str, Any],
        strategy_mode: str,
        playbook_key: str,
    ) -> str:
        return ensure_synthetic_opportunity_row_impl(
            self,
            synthetic_opportunity=synthetic_opportunity,
            strategy_mode=strategy_mode,
            playbook_key=playbook_key,
        )

    def _merge_ai_playbook_payload(
        self,
        *,
        campaign_payload: dict[str, Any],
        playbook_key: str,
        candidate: dict[str, Any],
        ai_plan: dict[str, Any],
        ai_generated: dict[str, Any],
        guardrail_report: dict[str, Any],
        workflow_status: str,
        budget_shift_pct: float,
        budget_shift_value: float,
        weekly_budget: float,
        activation_window: dict[str, Any],
        condition_key: str,
    ) -> None:
        merge_ai_playbook_payload_impl(
            self,
            campaign_payload=campaign_payload,
            playbook_key=playbook_key,
            candidate=candidate,
            ai_plan=ai_plan,
            ai_generated=ai_generated,
            guardrail_report=guardrail_report,
            workflow_status=workflow_status,
            budget_shift_pct=budget_shift_pct,
            budget_shift_value=budget_shift_value,
            weekly_budget=weekly_budget,
            activation_window=activation_window,
            condition_key=condition_key,
        )

    def _build_campaign_pack(
        self,
        *,
        opportunity: dict,
        brand: str,
        product: str,
        campaign_goal: str,
        region: str,
        urgency: float,
        confidence: float,
        weekly_budget: float,
        budget_shift_pct: float,
        budget_shift_value: float,
        channel_mix: dict,
        activation_window: dict,
        product_mapping: dict,
        region_codes: list[str],
        peix_context: dict[str, Any] | None = None,
    ) -> dict:
        return build_campaign_pack_impl(
            self,
            opportunity=opportunity,
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            region=region,
            urgency=urgency,
            confidence=confidence,
            weekly_budget=weekly_budget,
            budget_shift_pct=budget_shift_pct,
            budget_shift_value=budget_shift_value,
            channel_mix=channel_mix,
            activation_window=activation_window,
            product_mapping=product_mapping,
            region_codes=region_codes,
            peix_context=peix_context,
        )

    def _campaign_preview_from_payload(self, payload: dict) -> dict:
        return campaign_preview_from_payload_impl(self, payload)

    def _enrich_opportunity_for_media(
        self,
        *,
        opportunity_id: str,
        brand: str,
        product: str,
        budget_shift_pct: float,
        channel_mix: dict,
        reason: str,
        campaign_payload: dict,
        status: str,
        activation_start: datetime | None,
        activation_end: datetime | None,
        playbook_key: str | None = None,
        strategy_mode: str | None = None,
    ) -> None:
        enrich_opportunity_for_media_impl(
            self,
            opportunity_id=opportunity_id,
            brand=brand,
            product=product,
            budget_shift_pct=budget_shift_pct,
            channel_mix=channel_mix,
            reason=reason,
            campaign_payload=campaign_payload,
            status=status,
            activation_start=activation_start,
            activation_end=activation_end,
            playbook_key=playbook_key,
            strategy_mode=strategy_mode,
        )

    def _normalize_region_token(self, value: str | None) -> str | None:
        return normalize_region_token(value)

    @staticmethod
    def _canonical_brand(value: str | None) -> str:
        return canonical_brand(value)

    def _region_label(self, region_code: str) -> str:
        return region_label(region_code)

    def _extract_region_codes_from_opportunity(self, opportunity: dict[str, Any]) -> list[str]:
        return extract_region_codes_from_opportunity(opportunity)

    def _derive_peix_context(
        self,
        peix_regions: dict[str, Any],
        selected_region: str,
        opportunity: dict[str, Any],
        *,
        peix_national: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return derive_peix_context(
            peix_regions,
            selected_region,
            opportunity,
            peix_national=peix_national,
        )

    def _derive_ranking_signal_context(
        self,
        ranking_signal_regions: dict[str, Any],
        selected_region: str,
        opportunity: dict[str, Any],
        *,
        ranking_signal_national: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return derive_ranking_signal_context(
            ranking_signal_regions,
            selected_region,
            opportunity,
            ranking_signal_national=ranking_signal_national,
        )

    @staticmethod
    def _fact_label(key: str) -> str:
        return fact_label(key)

    @staticmethod
    def _confidence_pct(raw_confidence: Any, urgency_score: float | None) -> float | None:
        return confidence_pct(raw_confidence, urgency_score)

    @staticmethod
    def _public_fact_value(key: str, value: Any) -> Any:
        return public_fact_value(key, value)

    @staticmethod
    def _secondary_products(
        suggested_products: Any,
        mapping_candidate_product: str | None,
        primary_product: str | None,
    ) -> list[str]:
        return secondary_products(
            suggested_products=suggested_products,
            mapping_candidate_product=mapping_candidate_product,
            primary_product=primary_product,
        )

    def _decision_facts(
        self,
        *,
        trigger_snapshot: dict[str, Any],
        trigger_evidence: dict[str, Any],
        peix_context: dict[str, Any],
        confidence_pct: float | None,
        forecast_assessment: dict[str, Any] | None = None,
        opportunity_assessment: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return decision_facts_impl(
            self,
            trigger_snapshot=trigger_snapshot,
            trigger_evidence=trigger_evidence,
            peix_context=peix_context,
            confidence_pct_value=confidence_pct,
            forecast_assessment=forecast_assessment,
            opportunity_assessment=opportunity_assessment,
        )

    def _build_decision_brief(
        self,
        *,
        urgency_score: float | None,
        recommendation_reason: str | None,
        trigger_context: dict[str, Any],
        trigger_snapshot: dict[str, Any],
        trigger_evidence: dict[str, Any],
        peix_context: dict[str, Any],
        region_codes: list[str],
        condition_key: str | None,
        condition_label: str | None,
        recommended_product: str | None,
        mapping_status: str | None,
        mapping_reason: str | None,
        mapping_candidate_product: str | None,
        suggested_products: Any,
        budget_shift_pct: float | None,
        budget_shift_pct_fallback: float | None,
        forecast_assessment: dict[str, Any] | None = None,
        opportunity_assessment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_decision_brief_impl(
            self,
            urgency_score=urgency_score,
            recommendation_reason=recommendation_reason,
            trigger_context=trigger_context,
            trigger_snapshot=trigger_snapshot,
            trigger_evidence=trigger_evidence,
            peix_context=peix_context,
            region_codes=region_codes,
            condition_key=condition_key,
            condition_label=condition_label,
            recommended_product=recommended_product,
            mapping_status=mapping_status,
            mapping_reason=mapping_reason,
            mapping_candidate_product=mapping_candidate_product,
            suggested_products=suggested_products,
            budget_shift_pct=budget_shift_pct,
            budget_shift_pct_fallback=budget_shift_pct_fallback,
            forecast_assessment=forecast_assessment,
            opportunity_assessment=opportunity_assessment,
        )

    def _clean_for_output(self, opp: dict) -> dict:
        return clean_for_output(opp)

    def _normalize_workflow_status(self, status: str | None) -> str:
        return normalize_workflow_status(status)

    def _status_filter_values(self, status_filter: str) -> set[str]:
        return status_filter_values(status_filter)

    def _parse_iso_datetime(self, value: str | None) -> datetime | None:
        return parse_iso_datetime(value)

    def _model_to_dict(self, m: MarketingOpportunity, normalize_status: bool = True) -> dict:
        return model_to_dict_impl(self, m, normalize_status=normalize_status)
