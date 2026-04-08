"""MarketingOpportunityEngine — Hauptorchestrator.

Führt alle Detektoren aus, erzeugt Sales Pitches, matcht Produkte,
persistiert Opportunities und liefert CRM-fähiges JSON.
"""

from __future__ import annotations
from app.core.time import utc_now

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
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.playbook_engine import PLAYBOOK_CATALOG, PlaybookEngine
from app.services.media.semantic_contracts import (
    normalize_confidence_pct,
)
from app.services.ml.forecast_contracts import DEFAULT_DECISION_HORIZON_DAYS
from app.services.ml.forecast_decision_service import ForecastDecisionService

from .detectors.market_supply_monitor import MarketSupplyMonitor
from .detectors.predictive_sales_spike import PredictiveSalesSpikeDetector
from .detectors.resource_scarcity import ResourceScarcityDetector
from .detectors.weather_forecast import WeatherForecastDetector
from .opportunity_engine_constants import (
    FORECAST_PLAYBOOK_MAP,
)
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
        return "READY" if (peix_score >= 80.0 and model_ready) else "DRAFT"

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
        """Secondary modifiers may rank opportunities, but never create readiness."""
        relevant: list[dict[str, Any]] = []
        for opp in opportunities:
            region_codes = self._extract_region_codes_from_opportunity(opp)
            if not region_codes or region_code == "Gesamt" or region_code in region_codes:
                relevant.append(opp)

        if not relevant:
            return 1.0, []

        strongest = max(float(item.get("urgency_score") or 0.0) for item in relevant)
        delta = max(-0.15, min(0.15, (strongest - 50.0) / 333.0))
        modifier = round(1.0 + delta, 3)
        exploratory_signals = [
            {
                "type": item.get("type"),
                "urgency_score": round(float(item.get("urgency_score") or 0.0), 1),
                "reason": (item.get("trigger_context") or {}).get("event")
                or (item.get("trigger_context") or {}).get("details")
                or item.get("type"),
            }
            for item in sorted(
                relevant,
                key=lambda row: float(row.get("urgency_score") or 0.0),
                reverse=True,
            )[:3]
        ]
        return modifier, exploratory_signals

    def _forecast_first_candidates(
        self,
        *,
        opportunities: list[dict[str, Any]],
        brand: str,
        virus_typ: str,
        region_scope: list[str] | None,
        max_cards: int,
    ) -> list[dict[str, Any]]:
        service = ForecastDecisionService(self.db)
        forecast_bundle = service.build_forecast_bundle(
            virus_typ=virus_typ,
            target_source="RKI_ARE",
        )
        burden_forecast = forecast_bundle.get("burden_forecast") or {}
        event_forecast = forecast_bundle.get("event_forecast") or {}
        forecast_quality = forecast_bundle.get("forecast_quality") or {}
        burden_points = burden_forecast.get("points") or []
        if not burden_points:
            return []

        normalized_scope = [
            self._normalize_region_token(item)
            for item in (region_scope or [])
            if item
        ]
        region_codes = [item for item in normalized_scope if item] or ["Gesamt"]
        playbook_key = self._select_forecast_playbook_key(virus_typ)
        playbook_cfg = PLAYBOOK_CATALOG.get(playbook_key) or {}
        event_probability = float(event_forecast.get("event_probability") or 0.0)
        calibration_passed = bool(event_forecast.get("calibration_passed"))
        forecast_readiness = str(forecast_quality.get("forecast_readiness") or "WATCH")
        primary_threshold = event_forecast.get("threshold_value")
        baseline_value = event_forecast.get("baseline_value")

        candidates: list[dict[str, Any]] = []
        for region_code in region_codes[: max(1, max_cards)]:
            modifier, exploratory_signals = self._secondary_modifier_from_opportunities(
                opportunities=opportunities,
                region_code=region_code,
            )
            opportunity_assessment = service.build_opportunity_assessment(
                virus_typ=virus_typ,
                target_source="RKI_ARE",
                brand=brand,
                secondary_modifier=modifier,
            )
            expected_value_index = float(opportunity_assessment.get("expected_value_index") or 0.0)
            action_class = str(opportunity_assessment.get("action_class") or "watch_only")
            if action_class == "customer_lift_ready":
                budget_shift_pct = round(max(10.0, min(35.0, expected_value_index * 0.35)), 1)
            else:
                budget_shift_pct = 0.0

            candidates.append(
                {
                    "playbook_key": playbook_key,
                    "region_code": region_code,
                    "region_name": self._region_label(region_code) if region_code != "Gesamt" else "Deutschland",
                    "signal_score": round(event_probability * 100.0, 1),
                    "trigger_strength": round(event_probability * 100.0, 2),
                    "confidence": round(float(event_forecast.get("confidence") or event_probability) * 100.0, 2),
                    "signal_confidence_pct": normalize_confidence_pct(event_forecast.get("confidence")),
                    "priority_score": round(expected_value_index, 2),
                    "impact_probability": round(event_probability * 100.0, 1) if calibration_passed else None,
                    "budget_shift_pct": budget_shift_pct,
                    "channel_mix": playbook_cfg.get("default_mix") or {},
                    "shift_bounds": {
                        "min": playbook_cfg.get("shift_min"),
                        "max": playbook_cfg.get("shift_max"),
                    },
                    "playbook_title": playbook_cfg.get("title"),
                    "message_direction": playbook_cfg.get("message_direction"),
                    "condition_key": (PLAYBOOK_CATALOG.get(playbook_key) or {}).get("condition_key"),
                    "forecast_quality": forecast_quality,
                    "event_forecast": event_forecast,
                    "opportunity_assessment": opportunity_assessment,
                    "exploratory_signals": exploratory_signals,
                    "trigger_snapshot": {
                        "source": "ForecastDecisionService",
                        "event": f"{virus_typ} Forecast Event Window",
                        "details": (
                            f"7-Tage Event-Forecast für {virus_typ}: "
                            f"{round(event_probability * 100.0, 1)}% "
                            f"bei Baseline {baseline_value} und Schwelle {primary_threshold}."
                        ),
                        "lead_time_days": (
                            (forecast_quality.get("timing_metrics") or {}).get("best_lag_days")
                            or DEFAULT_DECISION_HORIZON_DAYS
                        ),
                        "confidence": float(event_forecast.get("confidence") or event_probability),
                        "values": {
                            "event_probability_pct": round(event_probability * 100.0, 1),
                            "threshold_pct": event_forecast.get("threshold_pct"),
                            "baseline_value": baseline_value,
                            "threshold_value": primary_threshold,
                            "expected_value_index": expected_value_index,
                            "secondary_modifier": modifier,
                        },
                    },
                    "forecast_readiness": forecast_readiness,
                    "action_class": action_class,
                }
            )

        candidates.sort(
            key=lambda item: (
                float(item.get("priority_score") or 0.0),
                float(item.get("trigger_strength") or 0.0),
            ),
            reverse=True,
        )
        return candidates[:max_cards]

    def generate_opportunities(self) -> dict:
        """Alle Detektoren ausführen -> Pitches -> Products -> Supply-Gap Modifier anwenden -> Persist -> JSON."""
        all_opportunities = []

        for detector in self.detectors:
            try:
                raw_opps = detector.detect()
                logger.info(
                    "%s: %s Opportunities erkannt",
                    detector.OPPORTUNITY_TYPE,
                    len(raw_opps),
                )
                for raw in raw_opps:
                    raw["sales_pitch"] = self.pitch_generator.generate(raw["type"], raw)
                    raw["suggested_products"] = self.product_matcher.match(raw["type"], raw)
                    all_opportunities.append(raw)
            except Exception as exc:
                logger.error("Detector %s fehlgeschlagen: %s", detector.OPPORTUNITY_TYPE, exc)

        # ── Signal-Deduplizierung: gleiche Condition + Region → nur höchste Urgency behalten ──
        all_opportunities = self._deduplicate_signals(all_opportunities)

        # ── Supply-Gap Fusion: apply priority multipliers from BfArM shortage signals ──
        all_opportunities = self._apply_supply_gap_priority_multipliers(all_opportunities)

        # ── Kreis-Targeting: Top-Kreise nach aktueller Inzidenz anreichern ──
        all_opportunities = self._enrich_kreis_targeting(all_opportunities)

        all_opportunities.sort(key=lambda x: x.get("urgency_score", 0), reverse=True)

        saved = 0
        for opp in all_opportunities:
            if self._save_opportunity(opp):
                saved += 1

        logger.info(
            "MarketingOpportunityEngine: %s erkannt, %s neu gespeichert",
            len(all_opportunities),
            saved,
        )

        clean_opps = [self._clean_for_output(o) for o in all_opportunities]
        return {
            "meta": {
                "generated_at": utc_now().isoformat() + "Z",
                "system_version": SYSTEM_VERSION,
                "total_opportunities": len(clean_opps),
                "new_saved": saved,
            },
            "opportunities": clean_opps,
        }

    @staticmethod
    def _deduplicate_signals(opportunities: list[dict]) -> list[dict]:
        """Dedupliziere Detektor-Signale: gleiche Condition + Region-Fingerprint
        aus verschiedenen Detektoren → nur die Opportunity mit der höchsten
        Urgency behalten. MARKET_SUPPLY_GAP wird nicht dedupliziert (ist
        Modifier, kein eigenständiger Trigger)."""
        seen: dict[str, dict] = {}
        passthrough: list[dict] = []

        for opp in opportunities:
            opp_type = opp.get("type", "")
            if opp_type == "MARKET_SUPPLY_GAP":
                passthrough.append(opp)
                continue

            condition = opp.get("_condition", "")
            region = opp.get("region_target", {})
            states = tuple(sorted(region.get("states", []))) if isinstance(region, dict) else ()
            dedup_key = f"{condition}::{states}"

            existing = seen.get(dedup_key)
            if existing is None or opp.get("urgency_score", 0) > existing.get("urgency_score", 0):
                seen[dedup_key] = opp

        deduped = list(seen.values()) + passthrough
        removed = len(opportunities) - len(deduped)
        if removed > 0:
            logger.info("Signal-Deduplizierung: %d Duplikate entfernt", removed)
        return deduped

    @staticmethod
    def _apply_supply_gap_priority_multipliers(opportunities: list[dict]) -> list[dict]:
        """Fuse MARKET_SUPPLY_GAP priority multipliers into epidemiological opportunities.

        When a MARKET_SUPPLY_GAP opportunity exists for a condition, its
        priority_multiplier is applied to all other opportunities sharing that condition.
        The supply-gap opportunity itself is kept for audit/tracking but treated
        as a modifier (not a standalone campaign trigger).

        Fusion rules:
        - Match on _condition field (e.g. "bronchitis_husten")
        - Multiply urgency_score by priority_multiplier (no hard cap)
        - Annotate the fused opportunity with supply-gap metadata
        - If multiple supply-gap signals match, use the highest multiplier
        """
        # Collect supply-gap multipliers by condition
        supply_gap_by_condition: dict[str, dict] = {}
        for opp in opportunities:
            if opp.get("type") != "MARKET_SUPPLY_GAP":
                continue
            condition = opp.get("_condition", "")
            if not condition:
                continue
            existing = supply_gap_by_condition.get(condition)
            if not existing or opp.get("_priority_multiplier", 1.0) > existing.get("_priority_multiplier", 1.0):
                supply_gap_by_condition[condition] = opp

        if not supply_gap_by_condition:
            return opportunities

        # Apply multipliers to non-supply-gap opportunities
        for opp in opportunities:
            if opp.get("type") == "MARKET_SUPPLY_GAP":
                continue

            condition = opp.get("_condition", "")
            supply_gap = supply_gap_by_condition.get(condition)
            if not supply_gap:
                continue

            multiplier = float(supply_gap.get("_priority_multiplier", 1.0))
            original_urgency = float(opp.get("urgency_score", 0))
            # Kein Cap bei 100: erlaubt Ranking unter mehreren urgenten
            # Opportunities wenn Supply-Gap Multiplikator angewendet wird.
            fused_urgency = original_urgency * multiplier

            opp["urgency_score"] = round(fused_urgency, 1)
            opp["_supply_gap_applied"] = True
            opp["_supply_gap_priority_multiplier"] = multiplier
            opp["_supply_gap_sku"] = supply_gap.get("_supply_gap_sku")
            opp["_supply_gap_product"] = supply_gap.get("_supply_gap_product")
            opp["_supply_gap_matched_products"] = supply_gap.get("_matched_products", [])

            logger.info(
                "Supply-gap fusion: %s urgency %.0f → %.0f (×%.2f from %s)",
                opp.get("id", "?"),
                original_urgency,
                fused_urgency,
                multiplier,
                supply_gap.get("_supply_gap_sku"),
            )

        return opportunities

    # ── Condition → Disease-Cluster Mapping ──
    _CONDITION_CLUSTER_MAP = {
        "bronchitis_husten": "RESPIRATORY",
        "sinusitis_nebenhoehlen": "RESPIRATORY",
        "erkaltung_akut": "RESPIRATORY",
        "halsschmerz_heiserkeit": "RESPIRATORY",
        "rhinitis_trockene_nase": "RESPIRATORY",
        "immun_support": "RESPIRATORY",
    }

    # Grossstädte → Bundesland (für schnelle Zuordnung ohne DB-Lookup)
    _KREIS_BL_MAP = {
        "SK Hamburg": "Hamburg", "SK München": "Bayern", "SK Berlin": "Berlin",
        "SK Dresden": "Sachsen", "SK Leipzig": "Sachsen", "SK Köln": "Nordrhein-Westfalen",
        "SK Frankfurt am Main": "Hessen", "SK Stuttgart": "Baden-Württemberg",
        "SK Düsseldorf": "Nordrhein-Westfalen", "SK Hannover": "Niedersachsen",
        "SK Bremen": "Bremen", "SK Nürnberg": "Bayern", "SK Dortmund": "Nordrhein-Westfalen",
        "SK Essen": "Nordrhein-Westfalen", "SK Duisburg": "Nordrhein-Westfalen",
        "SK Chemnitz": "Sachsen", "SK Erfurt": "Thüringen", "SK Magdeburg": "Sachsen-Anhalt",
        "SK Rostock": "Mecklenburg-Vorpommern", "SK Potsdam": "Brandenburg",
        "SK Kiel": "Schleswig-Holstein", "SK Mainz": "Rheinland-Pfalz",
        "SK Saarbrücken": "Saarland", "SK Freiburg i.Breisgau": "Baden-Württemberg",
    }

    def _kreis_bundesland(self, kreis_name: str) -> str:
        """Bundesland aus Kreisname ableiten (Lookup + KreisEinwohner Fallback)."""
        return self._KREIS_BL_MAP.get(kreis_name, "")

    def _enrich_kreis_targeting(self, opportunities: list[dict]) -> list[dict]:
        """Anreicherung mit Top-Kreisen nach aktueller Fallzahl.

        Liest SurvstatKreisData der letzten 4 Wochen, gruppiert nach
        Disease-Cluster, und fügt die Top-10 Kreise in region_target ein.
        """
        from app.models.database import SurvstatKreisData

        needed_clusters = set()
        for opp in opportunities:
            condition = opp.get("_condition", "")
            cluster = self._CONDITION_CLUSTER_MAP.get(condition)
            if cluster:
                needed_clusters.add(cluster)

        if not needed_clusters:
            return opportunities

        now = utc_now()
        current_week = now.isocalendar()[1]
        current_year = now.year

        kreise_by_cluster: dict[str, list[dict]] = {}
        for cluster in needed_clusters:
            # Letzte 4 verfügbare Wochen (aktuelles Jahr)
            rows = (
                self.db.query(
                    SurvstatKreisData.kreis,
                    func.sum(SurvstatKreisData.fallzahl).label("total_faelle"),
                )
                .filter(
                    SurvstatKreisData.disease_cluster == cluster,
                    SurvstatKreisData.year == current_year,
                    SurvstatKreisData.week >= max(1, current_week - 4),
                )
                .group_by(SurvstatKreisData.kreis)
                .order_by(func.sum(SurvstatKreisData.fallzahl).desc())
                .limit(10)
                .all()
            )

            if not rows:
                # Fallback: letztes verfügbares Jahr
                latest_year = (
                    self.db.query(func.max(SurvstatKreisData.year))
                    .filter(SurvstatKreisData.disease_cluster == cluster)
                    .scalar()
                )
                if latest_year and latest_year != current_year:
                    latest_week = (
                        self.db.query(func.max(SurvstatKreisData.week))
                        .filter(SurvstatKreisData.disease_cluster == cluster, SurvstatKreisData.year == latest_year)
                        .scalar()
                    ) or 52
                    rows = (
                        self.db.query(
                            SurvstatKreisData.kreis,
                            func.sum(SurvstatKreisData.fallzahl).label("total_faelle"),
                        )
                        .filter(
                            SurvstatKreisData.disease_cluster == cluster,
                            SurvstatKreisData.year == latest_year,
                            SurvstatKreisData.week >= max(1, latest_week - 4),
                        )
                        .group_by(SurvstatKreisData.kreis)
                        .order_by(func.sum(SurvstatKreisData.fallzahl).desc())
                        .limit(10)
                        .all()
                    )

            if rows:
                kreise_by_cluster[cluster] = [
                    {
                        "kreis": r.kreis,
                        "bundesland": self._kreis_bundesland(r.kreis),
                        "faelle_4w": int(r.total_faelle or 0),
                    }
                    for r in rows
                ]

        for opp in opportunities:
            condition = opp.get("_condition", "")
            cluster = self._CONDITION_CLUSTER_MAP.get(condition)
            top_kreise = kreise_by_cluster.get(cluster, []) if cluster else []

            if top_kreise:
                region = opp.get("region_target", {})
                region["top_kreise"] = [k["kreis"] for k in top_kreise]
                region["kreis_detail"] = top_kreise
                if not region.get("states"):
                    unique_bl = list(dict.fromkeys(k["bundesland"] for k in top_kreise if k["bundesland"]))
                    region["states"] = unique_bl
                opp["region_target"] = region

        return opportunities

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
