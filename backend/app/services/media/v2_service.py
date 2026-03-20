from __future__ import annotations

import csv
import io
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    BacktestRun,
    BrandProduct,
    ForecastAccuracyLog,
    GoogleTrendsData,
    MarketingOpportunity,
    MediaOutcomeImportBatch,
    MediaOutcomeImportIssue,
    MediaOutcomeRecord,
    MLForecast,
    SurvstatWeeklyData,
    WastewaterAggregated,
)
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.cockpit_service import MediaCockpitService
from app.services.media.outcome_signal_service import OutcomeSignalService
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.product_catalog_service import ProductCatalogService
from app.services.media.recommendation_contracts import (
    BUNDESLAND_NAMES,
    dedupe_group_id,
    enrich_card_v2,
    normalize_region_code,
    to_card_response,
)
from app.services.media.semantic_contracts import (
    business_gate_contract,
    evidence_tier_contract,
    forecast_probability_contract,
    infer_feature_families,
    outcome_confidence_contract,
    outcome_signal_contract,
    priority_score_contract,
    ranking_signal_contract,
    signal_confidence_contract,
    truth_readiness_contract,
)
from app.services.media.truth_gate_service import TruthGateService
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_service import _ML_MODELS_DIR, _virus_slug

SIGNAL_GROUPS: dict[str, dict[str, str]] = {
    "wastewater": {
        "label": "AMELAG Abwasser",
        "signal_group": "epi_core",
        "contribution_state": "core",
        "quality_note": "Zentrales epidemiologisches Primärsignal.",
    },
    "survstat": {
        "label": "RKI SurvStat",
        "signal_group": "epi_core",
        "contribution_state": "core",
        "quality_note": "IfSG-Meldedaten als zweite epidemiologische Achse.",
    },
    "are_konsultation": {
        "label": "RKI ARE",
        "signal_group": "epi_support",
        "contribution_state": "supporting",
        "quality_note": "Arztkonsultationen als Belastungs- und Validierungssignal.",
    },
    "notaufnahme": {
        "label": "Notaufnahme",
        "signal_group": "epi_support",
        "contribution_state": "supporting",
        "quality_note": "Kurzfristiger Morbiditätsdruck aus AKTIN/RKI.",
    },
    "google_trends": {
        "label": "Google Trends",
        "signal_group": "demand_context",
        "contribution_state": "context",
        "quality_note": "Suchverhalten als Nachfrage- und Aufmerksamkeitskontext.",
    },
    "weather": {
        "label": "Wetter",
        "signal_group": "context",
        "contribution_state": "context",
        "quality_note": "Wetterdruck als Verstärker, nicht als Primärsignal.",
    },
    "bfarm_shortage": {
        "label": "BfArM Engpässe",
        "signal_group": "supply_context",
        "contribution_state": "context",
        "quality_note": "Versorgungssignal, kein epidemiologischer Beweis.",
    },
}

CORE_SIGNAL_KEYS = {"wastewater", "survstat", "are_konsultation", "notaufnahme"}
METRIC_FIELD_LABELS = {
    "media_spend_eur": "Mediabudget",
    "impressions": "Impressionen",
    "clicks": "Klicks",
    "qualified_visits": "Qualifizierte Besuche",
    "search_lift_index": "Suchanstieg",
    "sales_units": "Verkäufe",
    "order_count": "Bestellungen",
    "revenue_eur": "Umsatz",
}
REQUIRED_OUTCOME_FIELD_NAMES = ("media_spend_eur",)
CONVERSION_OUTCOME_FIELD_NAMES = ("sales_units", "order_count", "revenue_eur")
OPTIONAL_OUTCOME_FIELD_NAMES = ("qualified_visits", "search_lift_index", "impressions", "clicks")
OUTCOME_TEMPLATE_HEADERS = (
    "week_start,product,region_code,media_spend_eur,sales_units,order_count,revenue_eur,"
    "qualified_visits,search_lift_index,impressions,clicks\n"
    "2026-02-02,GeloProsed,SH,12000,140,,,320,18.5,240000,5800\n"
    "2026-02-09,GeloRevoice,Hamburg,9000,,44,18500,210,12.0,120000,2900\n"
)
QUEUE_LIFECYCLE_PRIORITY = {
    "SYNC_READY": 5,
    "APPROVE": 4,
    "REVIEW": 3,
    "PREPARE": 2,
    "LIVE": 1,
    "EXPIRED": 0,
    "ARCHIVED": 0,
}
QUEUE_LANE_ORDER = ("APPROVE", "REVIEW", "SYNC_READY", "PREPARE", "LIVE")


class MediaV2Service:
    """View-spezifische Contracts für Decision, Regionen, Kampagnen und Evidenz."""

    def __init__(self, db: Session):
        self.db = db
        self.cockpit_service = MediaCockpitService(db)
        self.engine = MarketingOpportunityEngine(db)
        self.truth_gate_service = TruthGateService()
        self.outcome_signal_service = OutcomeSignalService(db)
        self.business_validation_service = BusinessValidationService(db)

    def get_decision_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
        forecast_bundle = ForecastDecisionService(self.db).build_forecast_bundle(
            virus_typ=virus_typ,
            target_source=target_source,
        )
        forecast_quality = forecast_bundle.get("forecast_quality") or {}
        event_forecast = forecast_bundle.get("event_forecast") or {}
        truth_coverage = self.get_truth_coverage(brand=brand, virus_typ=virus_typ)
        truth_gate = self.truth_gate_service.evaluate(truth_coverage)
        outcome_learning = self.outcome_signal_service.build_learning_bundle(
            brand=brand,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
        )["summary"]
        business_validation = self.business_validation_service.evaluate(
            brand=brand,
            virus_typ=virus_typ,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
            outcome_learning_summary=outcome_learning,
        )
        model_lineage = self.get_model_lineage(virus_typ=virus_typ)
        queue = self._build_campaign_queue(self._campaign_cards(brand=brand, limit=80), visible_limit=8)
        campaign_cards = queue["visible_cards"]
        primary_cards = queue["primary_cards"]
        top_card = self._decision_focus_card(primary_cards)
        top_regions = cockpit.get("map", {}).get("top_regions", [])[:3]
        market = cockpit.get("backtest_summary", {}).get("latest_market") or {}
        signal_summary = self.get_signal_stack(virus_typ=virus_typ).get("summary") or {}
        top_card_contracts = ((top_card or {}).get("field_contracts") or {}) if top_card else {}

        freshness_state = self._decision_freshness_state(cockpit.get("source_status", {}))
        has_truth = truth_gate["passed"]
        has_business_validation = bool(business_validation.get("validated_for_budget_activation"))
        market_passed = bool((market.get("quality_gate") or {}).get("overall_passed"))
        forecast_passed = str(forecast_quality.get("forecast_readiness") or "WATCH") == "GO"
        publishable_cards = [card for card in primary_cards if card.get("is_publishable")]
        has_publishable = len(publishable_cards) > 0
        drift_state = str(model_lineage.get("drift_state") or "unknown")
        decision_state = "GO" if all([
            freshness_state == "fresh",
            market_passed,
            forecast_passed,
            has_truth,
            has_business_validation,
            has_publishable,
            drift_state != "warning",
        ]) else "WATCH"

        risk_flags: list[str] = []
        if freshness_state != "fresh":
            risk_flags.append("Kernquellen sind nicht vollständig frisch.")
        if not market_passed:
            risk_flags.append("Der Marktvergleich liegt aktuell nicht im Zielkorridor.")
        if not forecast_passed:
            risk_flags.append("Die Vorhersage ist aktuell noch nicht freigegeben.")
        if not has_truth:
            risk_flags.append(str(truth_gate["message"]))
        if not has_business_validation:
            risk_flags.append(str(business_validation.get("message") or "Die Freigabe auf Basis von Kundendaten ist noch nicht validiert."))
        if drift_state == "warning":
            risk_flags.append("Modell-Drift ist im Monitoring auffällig.")
        if not has_publishable:
            risk_flags.append("Es gibt aktuell keinen freigabefähigen Kampagnenvorschlag.")
        if truth_gate.get("guidance") and truth_gate.get("learning_state") != "belastbar":
            risk_flags.append(str(truth_gate["guidance"]))
        if business_validation.get("guidance") and business_validation.get("decision_scope") != "validated_budget_activation":
            risk_flags.append(str(business_validation["guidance"]))

        why_now = self._build_why_now(
            top_card=top_card,
            top_regions=top_regions,
            cockpit=cockpit,
            decision_state=decision_state,
            signal_summary=signal_summary,
        )
        if truth_gate.get("message") and truth_gate["message"] not in why_now:
            why_now = [str(truth_gate["message"]), *why_now][:3]
        recommended_action = self._recommended_action(
            decision_state=decision_state,
            top_card=top_card,
            top_regions=top_regions,
            decision_mode=str(signal_summary.get("decision_mode") or "epidemic_wave"),
        )
        top_products = self._decision_top_products(primary_cards, top_card)

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "generated_at": datetime.utcnow().isoformat(),
            "weekly_decision": {
                "decision_state": decision_state,
                "action_stage": "activate" if decision_state == "GO" else "prepare",
                "decision_window": {
                    "start": cockpit.get("map", {}).get("date"),
                    "horizon_days": top_card.get("decision_brief", {}).get("horizon", {}).get("max_days") if top_card else None,
                },
                "recommended_action": recommended_action,
                "top_regions": [
                    {
                        "code": item.get("code"),
                        "name": item.get("name"),
                        "signal_score": item.get("signal_score") or item.get("peix_score") or item.get("impact_probability"),
                        "trend": item.get("trend"),
                    }
                    for item in top_regions
                ],
                "top_products": top_products,
                "budget_shift": (
                    top_card.get("budget_shift_pct")
                    if decision_state == "GO" and top_card and top_card.get("is_publishable")
                    else None
                ),
                "why_now": why_now,
                "risk_flags": risk_flags,
                "freshness_state": freshness_state,
                "proxy_state": "passed" if market_passed else "watch",
                "forecast_state": "passed" if forecast_passed else "watch",
                "forecast_quality": forecast_quality,
                "event_forecast": event_forecast,
                "truth_state": truth_coverage.get("trust_readiness"),
                "truth_freshness_state": truth_coverage.get("truth_freshness_state"),
                "truth_last_imported_at": truth_coverage.get("last_imported_at"),
                "truth_latest_batch_id": truth_coverage.get("latest_batch_id"),
                "truth_risk_flag": None if has_truth else truth_gate["message"],
                "truth_gate": truth_gate,
                "business_gate": business_validation,
                "business_readiness": business_validation.get("validation_status"),
                "business_evidence_tier": business_validation.get("evidence_tier"),
                "learning_state": outcome_learning.get("learning_state"),
                "outcome_learning_summary": outcome_learning,
                "decision_mode": signal_summary.get("decision_mode"),
                "decision_mode_label": signal_summary.get("decision_mode_label"),
                "decision_mode_reason": signal_summary.get("decision_mode_reason"),
                "signal_stack_summary": signal_summary,
                "operator_context": business_validation.get("operator_context"),
                "field_contracts": {
                    "event_probability": forecast_probability_contract(),
                    "signal_score": ranking_signal_contract(
                        source="PeixEpiScore",
                    ),
                    "priority_score": top_card_contracts.get("priority_score")
                    or priority_score_contract(source="MarketingOpportunityEngine"),
                    "signal_confidence_pct": top_card_contracts.get("signal_confidence_pct")
                    or signal_confidence_contract(
                        source="MarketingOpportunityEngine",
                        derived_from="trigger_evidence.confidence",
                    ),
                    "truth_readiness": truth_readiness_contract(),
                    "business_gate": business_gate_contract(),
                    "evidence_tier": evidence_tier_contract(),
                    "outcome_signal_score": outcome_signal_contract(),
                    "outcome_confidence_pct": outcome_confidence_contract(),
                },
            },
            "top_recommendations": campaign_cards[:3],
            "campaign_summary": queue["summary"],
            "wave_run_id": (cockpit.get("backtest_summary", {}).get("latest_market") or {}).get("run_id"),
            "backtest_summary": cockpit.get("backtest_summary"),
            "model_lineage": model_lineage,
            "truth_coverage": truth_coverage,
            "business_validation": business_validation,
            "operator_context": business_validation.get("operator_context"),
        }

    def get_regions_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
        peix = cockpit.get("peix_epi_score") or {}
        map_section = cockpit.get("map") or {}
        suggestions = {
            item.get("region"): item
            for item in map_section.get("activation_suggestions", [])
            if item.get("region")
        }

        enriched_regions: dict[str, dict[str, Any]] = {}
        for code, region in (map_section.get("regions") or {}).items():
            peix_region = (peix.get("regions") or {}).get(code, {})
            suggestion = suggestions.get(code) or {}
            forecast_direction = self._forecast_direction(region)
            severity_score = self._severity_score(region)
            momentum_score = self._momentum_score(region=region, forecast_direction=forecast_direction)
            decision_mode = self._region_decision_mode(peix_region)
            actionability_score = self._actionability_score(
                region=region,
                suggestion=suggestion,
                severity_score=severity_score,
                momentum_score=momentum_score,
            )
            enriched_regions[code] = {
                **region,
                "signal_score": region.get("signal_score") or region.get("peix_score") or peix_region.get("score_0_100") or region.get("impact_probability"),
                "peix_score": region.get("peix_score") or peix_region.get("score_0_100"),
                "severity_score": severity_score,
                "momentum_score": momentum_score,
                "actionability_score": actionability_score,
                "forecast_direction": forecast_direction,
                "signal_drivers": peix_region.get("top_drivers") or [],
                "layer_contributions": peix_region.get("layer_contributions") or {},
                "budget_logic": suggestion.get("reason") or region.get("tooltip", {}).get("recommendation_text"),
                "decision_mode": decision_mode["key"],
                "decision_mode_label": decision_mode["label"],
                "decision_mode_reason": decision_mode["reason"],
                "priority_explanation": self._priority_explanation(
                    region=region,
                    suggestion=suggestion,
                    forecast_direction=forecast_direction,
                    severity_score=severity_score,
                    momentum_score=momentum_score,
                    actionability_score=actionability_score,
                    decision_mode=decision_mode["key"],
                ),
                "source_trace": self._region_source_trace(peix_region),
                "field_contracts": {
                    "signal_score": ranking_signal_contract(source="PeixEpiScore"),
                    "priority_score": priority_score_contract(source="MediaV2Service"),
                },
            }

        sorted_regions = sorted(
            [
                {"code": code, **region}
                for code, region in enriched_regions.items()
            ],
            key=lambda item: (
                float(item.get("actionability_score") or 0.0),
                float(item.get("severity_score") or 0.0),
                float(item.get("momentum_score") or 0.0),
                float(item.get("signal_score") or item.get("peix_score") or item.get("impact_probability") or 0.0),
            ),
            reverse=True,
        )
        for index, item in enumerate(sorted_regions, start=1):
            enriched_regions[item["code"]]["priority_rank"] = index
            item["priority_rank"] = index

        decision_payload = self.get_decision_payload(
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )
        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "generated_at": datetime.utcnow().isoformat(),
            "map": {
                **map_section,
                "regions": enriched_regions,
                "top_regions": sorted_regions[:5],
            },
            "top_regions": sorted_regions[:5],
            "decision_state": decision_payload.get("weekly_decision", {}).get("decision_state"),
        }

    def get_campaigns_payload(
        self,
        *,
        brand: str = "gelo",
        limit: int = 120,
    ) -> dict[str, Any]:
        cards = self._campaign_cards(brand=brand, limit=limit)
        queue = self._build_campaign_queue(cards, visible_limit=min(limit, 8))
        primary_cards = queue["primary_cards"]
        archived_cards = queue["archived_cards"]
        visible_cards = queue["visible_cards"]
        truth_coverage = self.get_truth_coverage(brand=brand)
        truth_gate = self.truth_gate_service.evaluate(truth_coverage)
        outcome_learning = self.outcome_signal_service.build_learning_bundle(
            brand=brand,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
        )["summary"]

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "cards": visible_cards,
            "archived_cards": archived_cards[:20],
            "summary": queue["summary"] | {
                "total_cards": len(cards),
                "active_cards": len(queue["active_cards"]),
                "deduped_cards": len(primary_cards),
                "publishable_cards": len([card for card in primary_cards if card.get("is_publishable")]),
                "expired_cards": len([card for card in cards if card.get("lifecycle_state") == "EXPIRED"]),
                "states": self._campaign_state_counts(primary_cards),
                "learning_state": outcome_learning.get("learning_state"),
                "outcome_signal_score": outcome_learning.get("outcome_signal_score"),
                "outcome_confidence_pct": outcome_learning.get("outcome_confidence_pct"),
            },
        }

    def get_evidence_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
        backtest_summary = cockpit.get("backtest_summary") or {}
        truth_snapshot = self.get_truth_evidence(brand=brand, virus_typ=virus_typ)
        truth_coverage = truth_snapshot["coverage"]
        truth_gate = self.truth_gate_service.evaluate(truth_coverage)
        outcome_learning = self.outcome_signal_service.build_learning_bundle(
            brand=brand,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
        )["summary"]
        business_validation = self.business_validation_service.evaluate(
            brand=brand,
            virus_typ=virus_typ,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
            outcome_learning_summary=outcome_learning,
        )
        latest_customer = backtest_summary.get("latest_customer")
        truth_validation = latest_customer if truth_coverage.get("coverage_weeks", 0) > 0 else None
        truth_validation_legacy = latest_customer if truth_validation is None and latest_customer else None
        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "generated_at": datetime.utcnow().isoformat(),
            "proxy_validation": backtest_summary.get("latest_market"),
            "business_validation": business_validation,
            "operator_context": business_validation.get("operator_context"),
            "truth_validation": truth_validation,
            "truth_validation_legacy": truth_validation_legacy,
            "recent_runs": backtest_summary.get("recent_runs") or [],
            "data_freshness": cockpit.get("data_freshness") or {},
            "source_status": cockpit.get("source_status") or {},
            "signal_stack": self.get_signal_stack(virus_typ=virus_typ),
            "model_lineage": self.get_model_lineage(virus_typ=virus_typ),
            "forecast_monitoring": self.get_forecast_monitoring(virus_typ=virus_typ, target_source=target_source),
            "truth_coverage": truth_coverage,
            "truth_gate": truth_gate,
            "truth_snapshot": truth_snapshot,
            "outcome_learning_summary": outcome_learning,
            "known_limits": self._known_limits(
                cockpit,
                virus_typ,
                truth_coverage=truth_coverage,
                truth_validation_legacy=truth_validation_legacy,
            ),
        }

    def get_forecast_monitoring(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
    ) -> dict[str, Any]:
        return ForecastDecisionService(self.db).build_monitoring_snapshot(
            virus_typ=virus_typ,
            target_source=target_source,
        )

    def get_signal_stack(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source="RKI_ARE")
        data_freshness = cockpit.get("data_freshness") or {}
        source_status_items = {
            item.get("source_key"): item
            for item in (cockpit.get("source_status") or {}).get("items", [])
        }
        peix = cockpit.get("peix_epi_score") or PeixEpiScoreService(self.db).build(virus_typ=virus_typ)
        signal_groups = self._signal_group_summary(peix)
        model_lineage = self.get_model_lineage(virus_typ=virus_typ)

        items = []
        for source_key, meta in SIGNAL_GROUPS.items():
            status_item = source_status_items.get(source_key) or {}
            last_available_at = data_freshness.get(source_key)
            coverage_state = "covered" if last_available_at else "missing"
            if status_item.get("freshness_state") == "stale":
                coverage_state = "stale"
            items.append({
                "source_key": source_key,
                "label": meta["label"],
                "signal_group": meta["signal_group"],
                "last_available_at": last_available_at,
                "freshness_state": status_item.get("freshness_state") or "no_data",
                "coverage_state": coverage_state,
                "quality_note": meta["quality_note"],
                "contribution_state": meta["contribution_state"],
                "is_core_signal": source_key in CORE_SIGNAL_KEYS,
            })

        items.sort(key=lambda item: (not item["is_core_signal"], item["label"]))
        summary = {
            "peix_epi_score": peix.get("national_score"),
            "national_band": peix.get("national_band"),
            "top_drivers": peix.get("top_drivers") or [],
            "context_signals": peix.get("context_signals") or {},
            "math_stack": {
                "base_models": ["Holt-Winters", "Ridge", "Prophet"],
                "meta_learner": "XGBoost",
                "feature_families": model_lineage.get("feature_families") or [],
            },
            **signal_groups,
        }
        return {
            "virus_typ": virus_typ,
            "generated_at": datetime.utcnow().isoformat(),
            "items": items,
            "summary": summary,
        }

    def get_model_lineage(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        latest_forecast = (
            self.db.query(MLForecast)
            .filter(MLForecast.virus_typ == virus_typ)
            .order_by(MLForecast.created_at.desc())
            .first()
        )
        latest_market = (
            self.db.query(BacktestRun)
            .filter(
                BacktestRun.mode == "MARKET_CHECK",
                BacktestRun.virus_typ == virus_typ,
            )
            .order_by(BacktestRun.created_at.desc())
            .first()
        )
        latest_accuracy = (
            self.db.query(ForecastAccuracyLog)
            .filter(ForecastAccuracyLog.virus_typ == virus_typ)
            .order_by(ForecastAccuracyLog.computed_at.desc())
            .first()
        )
        training_window = self.db.query(
            func.min(WastewaterAggregated.datum),
            func.max(WastewaterAggregated.datum),
            func.count(WastewaterAggregated.id),
        ).filter(WastewaterAggregated.virus_typ == virus_typ).first()

        metadata = self._read_model_metadata(virus_typ)
        feature_names = metadata.get("feature_names") or (latest_forecast.features_used if latest_forecast else []) or []
        feature_families = infer_feature_families(feature_names)
        drift_state = "warning" if bool(getattr(latest_accuracy, "drift_detected", False)) else ("ok" if latest_accuracy else "unknown")
        coverage_limits: list[str] = []
        training_samples = int(metadata.get("training_samples") or 0)
        if training_samples and training_samples < 52:
            coverage_limits.append("Trainingsfenster ist noch relativ kurz.")
        if latest_accuracy and (latest_accuracy.samples or 0) < 14:
            coverage_limits.append("Die Vorhersagegenauigkeit basiert noch auf einem kleinen Monitoring-Fenster.")
        if not metadata:
            coverage_limits.append("Kein serialisiertes Modell-Metadata gefunden.")

        return {
            "virus_typ": virus_typ,
            "model_family": "stacking_forecast",
            "base_estimators": ["Holt-Winters", "Ridge", "Prophet"],
            "meta_learner": "XGBoost",
            "model_version": metadata.get("version") or (latest_forecast.model_version if latest_forecast else None) or "unbekannt",
            "trained_at": metadata.get("trained_at"),
            "feature_set_version": f"meta_{len(feature_names)}",
            "feature_names": feature_names,
            "feature_families": feature_families,
            "training_window": {
                "start": training_window[0].isoformat() if training_window and training_window[0] else None,
                "end": training_window[1].isoformat() if training_window and training_window[1] else None,
                "points": int(training_window[2] or 0) if training_window else 0,
            },
            "drift_state": drift_state,
            "coverage_limits": coverage_limits,
            "forecast_quality": (latest_market.metrics or {}).get("quality_gate") if latest_market else None,
            "latest_accuracy": {
                "computed_at": latest_accuracy.computed_at.isoformat() if latest_accuracy and latest_accuracy.computed_at else None,
                "samples": latest_accuracy.samples if latest_accuracy else None,
                "mape": latest_accuracy.mape if latest_accuracy else None,
                "rmse": latest_accuracy.rmse if latest_accuracy else None,
                "correlation": latest_accuracy.correlation if latest_accuracy else None,
            },
            "latest_forecast_created_at": latest_forecast.created_at.isoformat() if latest_forecast and latest_forecast.created_at else None,
        }

    def get_truth_coverage(
        self,
        *,
        brand: str = "gelo",
        virus_typ: str | None = None,
    ) -> dict[str, Any]:
        rows = (
            self.db.query(MediaOutcomeRecord)
            .filter(func.lower(MediaOutcomeRecord.brand) == str(brand).lower())
            .order_by(MediaOutcomeRecord.week_start.asc())
            .all()
        )
        latest_import_batch = self._latest_import_batch(brand=brand)
        reference_week = self._latest_epi_reference_week(virus_typ=virus_typ)
        if not rows:
            return {
                "coverage_weeks": 0,
                "latest_week": None,
                "regions_covered": 0,
                "products_covered": 0,
                "outcome_fields_present": [],
                "required_fields_present": [],
                "conversion_fields_present": [],
                "trust_readiness": "noch_nicht_angeschlossen",
                "truth_freshness_state": "missing",
                "source_labels": [],
                "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
                "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
                "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
            }

        week_values = sorted({row.week_start for row in rows if row.week_start})
        weeks = [value.date().isoformat() for value in week_values]
        regions = {row.region_code for row in rows if row.region_code}
        products = {row.product for row in rows if row.product}
        fields_present = [
            label
            for field_name, label in METRIC_FIELD_LABELS.items()
            if any(getattr(row, field_name) is not None for row in rows)
        ]
        required_fields_present = [
            METRIC_FIELD_LABELS[field_name]
            for field_name in REQUIRED_OUTCOME_FIELD_NAMES
            if any(getattr(row, field_name) is not None for row in rows)
        ]
        conversion_fields_present = [
            METRIC_FIELD_LABELS[field_name]
            for field_name in CONVERSION_OUTCOME_FIELD_NAMES
            if any(getattr(row, field_name) is not None for row in rows)
        ]
        coverage_weeks = len(weeks)
        if coverage_weeks >= 52:
            readiness = "belastbar"
        elif coverage_weeks >= 26:
            readiness = "im_aufbau"
        elif coverage_weeks > 0:
            readiness = "erste_signale"
        else:
            readiness = "noch_nicht_angeschlossen"
        latest_week_dt = week_values[-1] if week_values else None
        truth_freshness_state = self._truth_freshness_state(
            latest_truth_week=latest_week_dt,
            reference_week=reference_week,
        )

        return {
            "coverage_weeks": coverage_weeks,
            "latest_week": weeks[-1] if weeks else None,
            "regions_covered": len(regions),
            "products_covered": len(products),
            "outcome_fields_present": fields_present,
            "required_fields_present": required_fields_present,
            "conversion_fields_present": conversion_fields_present,
            "trust_readiness": readiness,
            "truth_freshness_state": truth_freshness_state,
            "source_labels": sorted({row.source_label for row in rows if row.source_label}),
            "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
            "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
            "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
        }

    def get_truth_evidence(
        self,
        *,
        brand: str = "gelo",
        virus_typ: str | None = None,
    ) -> dict[str, Any]:
        coverage = self.get_truth_coverage(brand=brand, virus_typ=virus_typ)
        truth_gate = self.truth_gate_service.evaluate(coverage)
        outcome_learning = self.outcome_signal_service.build_learning_bundle(
            brand=brand,
            truth_coverage=coverage,
            truth_gate=truth_gate,
        )["summary"]
        business_validation = self.business_validation_service.evaluate(
            brand=brand,
            virus_typ=virus_typ,
            truth_coverage=coverage,
            truth_gate=truth_gate,
            outcome_learning_summary=outcome_learning,
        )
        recent_batches = self.list_outcome_import_batches(brand=brand, limit=8)
        latest_batch = recent_batches[0] if recent_batches else None
        issue_count = int(latest_batch.get("rows_rejected") or 0) if latest_batch else 0
        limits: list[str] = []
        if coverage.get("coverage_weeks", 0) < 26:
            limits.append("Weniger als 26 Wochen Kundendaten reichen noch nicht für belastbare Freigaben.")
        if not coverage.get("required_fields_present"):
            limits.append("Mediabudget fehlt in den Kundendaten oder ist noch nicht breit genug vorhanden.")
        if not coverage.get("conversion_fields_present"):
            limits.append("Mindestens eine echte Wirkungszahl wie Verkäufe, Bestellungen oder Umsatz fehlt noch.")
        if coverage.get("truth_freshness_state") == "stale":
            limits.append("Der letzte Import der Kundendaten liegt zu weit hinter der aktuellen epidemiologischen Woche.")
        return {
            "brand": str(brand or "gelo").strip().lower(),
            "coverage": coverage,
            "truth_gate": truth_gate,
            "business_validation": business_validation,
            "outcome_learning_summary": outcome_learning,
            "recent_batches": recent_batches,
            "latest_batch": latest_batch,
            "latest_batch_issue_count": issue_count,
            "template_url": "/api/v1/media/outcomes/template",
            "official_ingest_url": "/api/v1/media/outcomes/ingest",
            "known_limits": limits,
            "analyst_note": "Die offizielle Kundenschnittstelle ist jetzt die M2M-Ingestion unter /api/v1/media/outcomes/ingest. CSV bleibt nur als Backoffice-Fallback.",
        }

    def import_outcomes(
        self,
        *,
        source_label: str,
        records: list[dict[str, Any]] | None = None,
        csv_payload: str | None = None,
        brand: str = "gelo",
        replace_existing: bool = False,
        validate_only: bool = False,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        brand_value = str(brand or "gelo").strip().lower()
        source_value = str(source_label or "manual").strip() or "manual"
        batch_id = uuid.uuid4().hex[:12]

        parsed_rows, header_issues = self._collect_outcome_rows(
            records=records or [],
            csv_payload=csv_payload,
            brand=brand_value,
            source_label=source_value,
        )
        batch = MediaOutcomeImportBatch(
            batch_id=batch_id,
            brand=brand_value,
            source_label=source_value,
            ingestion_mode="manual_backoffice",
            file_name=(file_name or "").strip() or None,
            status="validated" if validate_only else "failed",
            rows_total=len(parsed_rows),
            uploaded_at=datetime.utcnow(),
        )
        self.db.add(batch)
        self.db.flush()

        issues: list[dict[str, Any]] = list(header_issues)
        normalized_rows: list[dict[str, Any]] = []
        duplicate_count = 0
        seen_keys: set[tuple[str, str, datetime, str, str]] = set()

        for row in parsed_rows:
            normalized = self._normalize_outcome_row(
                row=row,
                brand=brand_value,
                source_label=source_value,
            )
            if normalized.get("issues"):
                issues.extend(normalized["issues"])
                continue

            dedupe_key = (
                brand_value,
                source_value,
                normalized["week_start"],
                normalized["product"],
                normalized["region_code"],
            )
            if dedupe_key in seen_keys:
                duplicate_count += 1
                issues.append(self._issue_dict(
                    batch_id=batch_id,
                    row_number=row.get("row_number"),
                    field_name="row",
                    issue_code="duplicate_in_upload",
                    message="Diese Kombination aus Woche, Produkt, Region und Source kommt in der Datei mehrfach vor.",
                    raw_row=row.get("raw_row"),
                ))
                continue
            seen_keys.add(dedupe_key)

            existing = self._find_existing_outcome(
                brand=brand_value,
                source_label=source_value,
                week_start=normalized["week_start"],
                product=normalized["product"],
                region_code=normalized["region_code"],
            )
            if existing and not replace_existing:
                duplicate_count += 1
                issues.append(self._issue_dict(
                    batch_id=batch_id,
                    row_number=row.get("row_number"),
                    field_name="row",
                    issue_code="duplicate_existing",
                    message="Fuer diese Woche, dieses Produkt und diese Region existiert bereits ein Datensatz in den Kundendaten.",
                    raw_row=row.get("raw_row"),
                ))
                continue

            normalized["existing_record"] = existing
            normalized_rows.append(normalized)

        imported = 0
        if not validate_only:
            for row in normalized_rows:
                target = row["existing_record"]
                if target is None:
                    target = MediaOutcomeRecord(
                        week_start=row["week_start"],
                        brand=brand_value,
                        product=row["product"],
                        region_code=row["region_code"],
                        source_label=source_value,
                    )
                    self.db.add(target)

                target.media_spend_eur = row["metrics"].get("media_spend_eur")
                target.impressions = row["metrics"].get("impressions")
                target.clicks = row["metrics"].get("clicks")
                target.qualified_visits = row["metrics"].get("qualified_visits")
                target.search_lift_index = row["metrics"].get("search_lift_index")
                target.sales_units = row["metrics"].get("sales_units")
                target.order_count = row["metrics"].get("order_count")
                target.revenue_eur = row["metrics"].get("revenue_eur")
                target.import_batch_id = batch_id
                target.extra_data = row.get("extra_data") or {}
                target.updated_at = datetime.utcnow()
                imported += 1

        coverage_after_import = self._project_truth_coverage(
            brand=brand_value,
            normalized_rows=normalized_rows,
            virus_typ=None,
            replace_existing=replace_existing,
            validate_only=validate_only,
        )

        batch.rows_valid = len(normalized_rows)
        batch.rows_imported = imported
        batch.rows_duplicate = duplicate_count
        batch.rows_rejected = len(parsed_rows) - len(normalized_rows)
        batch.week_min = min((row["week_start"] for row in normalized_rows), default=None)
        batch.week_max = max((row["week_start"] for row in normalized_rows), default=None)
        batch.coverage_after_import = coverage_after_import
        if validate_only:
            batch.status = "validated"
        elif imported and issues:
            batch.status = "partial_success"
        elif imported:
            batch.status = "imported"
        else:
            batch.status = "failed"

        if not validate_only and imported:
            coverage_after_import["last_imported_at"] = batch.uploaded_at.isoformat() if batch.uploaded_at else None
            coverage_after_import["latest_batch_id"] = batch_id
            coverage_after_import["latest_source_label"] = source_value

        for issue in issues:
            issue["batch_id"] = batch_id
        for issue in issues:
            self.db.add(MediaOutcomeImportIssue(**issue))

        self.db.commit()
        self.db.refresh(batch)

        return {
            "imported": imported,
            "batch_id": batch_id,
            "batch_summary": self._batch_to_dict(batch),
            "issues": [self._issue_response(issue) for issue in issues],
            "preview_only": validate_only,
            "coverage_after_import": coverage_after_import,
            "coverage": coverage_after_import,
            "message": (
                "Upload validiert. Es wurden noch keine Kundendaten gespeichert."
                if validate_only
                else ("Kundendaten importiert." if imported else "Import abgeschlossen, aber keine Zeilen wurden übernommen.")
            ),
        }

    def list_outcome_import_batches(
        self,
        *,
        brand: str = "gelo",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = (
            self.db.query(MediaOutcomeImportBatch)
            .filter(func.lower(MediaOutcomeImportBatch.brand) == str(brand or "gelo").lower())
            .order_by(MediaOutcomeImportBatch.uploaded_at.desc(), MediaOutcomeImportBatch.id.desc())
            .limit(limit)
            .all()
        )
        return [self._batch_to_dict(row) for row in rows]

    def get_outcome_import_batch_detail(self, *, batch_id: str) -> dict[str, Any] | None:
        batch = (
            self.db.query(MediaOutcomeImportBatch)
            .filter(MediaOutcomeImportBatch.batch_id == batch_id)
            .first()
        )
        if not batch:
            return None
        issues = (
            self.db.query(MediaOutcomeImportIssue)
            .filter(MediaOutcomeImportIssue.batch_id == batch_id)
            .order_by(
                MediaOutcomeImportIssue.row_number.is_(None),
                MediaOutcomeImportIssue.row_number.asc(),
                MediaOutcomeImportIssue.id.asc(),
            )
            .all()
        )
        return {
            "batch": self._batch_to_dict(batch),
            "issues": [self._issue_to_dict(issue) for issue in issues],
        }

    def outcome_template_csv(self) -> str:
        return OUTCOME_TEMPLATE_HEADERS

    def _campaign_cards(self, *, brand: str = "gelo", limit: int = 120) -> list[dict[str, Any]]:
        opportunities = self.engine.get_opportunities(
            brand_filter=brand,
            limit=limit,
            normalize_status=True,
        )
        truth_coverage = self.get_truth_coverage(brand=brand)
        truth_gate = self.truth_gate_service.evaluate(truth_coverage)
        learning_bundle = self.outcome_signal_service.build_learning_bundle(
            brand=brand,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
        )
        cards = [
            self._attach_outcome_learning_to_card(
                card=to_card_response(opp, include_preview=True),
                learning_bundle=learning_bundle,
                truth_gate=truth_gate,
            )
            for opp in opportunities
        ]
        cards.sort(
            key=self._campaign_sort_key,
            reverse=True,
        )
        return cards

    def _attach_outcome_learning_to_card(
        self,
        *,
        card: dict[str, Any],
        learning_bundle: dict[str, Any],
        truth_gate: dict[str, Any],
    ) -> dict[str, Any]:
        learning_signal = self.outcome_signal_service.signal_for_card(
            card=card,
            bundle=learning_bundle,
        )
        learned_priority = self._learned_priority_score(
            base_priority=float(card.get("priority_score") or card.get("urgency_score") or 0.0),
            outcome_signal_score=learning_signal.get("outcome_signal_score"),
            truth_gate=truth_gate,
        )
        updated_contracts = dict(card.get("field_contracts") or {})
        updated_contracts.update({
            "outcome_signal_score": outcome_signal_contract(),
            "outcome_confidence_pct": outcome_confidence_contract(),
            "truth_readiness": truth_readiness_contract(),
        })
        return card | {
            "priority_score": learned_priority,
            "learning_state": learning_signal.get("learning_state"),
            "outcome_signal_score": learning_signal.get("outcome_signal_score"),
            "outcome_confidence_pct": learning_signal.get("outcome_confidence_pct"),
            "outcome_learning_scope": learning_signal.get("outcome_learning_scope"),
            "outcome_learning_explanation": learning_signal.get("outcome_learning_explanation"),
            "observed_response": learning_signal.get("observed_response"),
            "learned_lifts": learning_signal.get("learned_lifts"),
            "field_contracts": updated_contracts,
        }

    def _learned_priority_score(
        self,
        *,
        base_priority: float,
        outcome_signal_score: Any,
        truth_gate: dict[str, Any],
    ) -> float:
        learning_state = str(truth_gate.get("learning_state") or "missing").lower()
        if learning_state in {"missing", "explorative", "stale"}:
            learning_weight = 0.0 if learning_state == "missing" else 0.12
        elif learning_state == "im_aufbau":
            learning_weight = 0.20
        else:
            learning_weight = 0.30

        try:
            outcome_score = float(outcome_signal_score)
        except (TypeError, ValueError):
            outcome_score = 0.0
        blended = base_priority * (1.0 - learning_weight) + outcome_score * learning_weight
        return round(max(0.0, min(100.0, blended)), 1)

    def _decision_freshness_state(self, source_status: dict[str, Any]) -> str:
        items = source_status.get("items") or []
        live_core = {item.get("source_key") for item in items if item.get("is_live") and item.get("source_key") in CORE_SIGNAL_KEYS}
        if live_core == CORE_SIGNAL_KEYS:
            return "fresh"
        if live_core:
            return "degraded"
        return "stale"

    def _build_why_now(
        self,
        *,
        top_card: dict[str, Any] | None,
        top_regions: list[dict[str, Any]],
        cockpit: dict[str, Any],
        decision_state: str,
        signal_summary: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        if decision_state != "GO":
            reasons.append("Die epidemiologischen Signale sind relevant, aber die Freigabe bleibt vorerst im Beobachtungsmodus.")
        if top_regions:
            reasons.append(
                f"{top_regions[0].get('name')} fuehrt die regionalen Signale mit {round(float(top_regions[0].get('signal_score') or top_regions[0].get('peix_score') or top_regions[0].get('impact_probability') or 0))}/100 an."
            )
        if top_card:
            if decision_state == "GO" and top_card.get("decision_brief", {}).get("summary_sentence"):
                reasons.append(str(top_card["decision_brief"]["summary_sentence"]))
            else:
                title = top_card.get("display_title") or top_card.get("recommended_product") or "Der stärkste Kampagnenvorschlag"
                reasons.append(f"{title} ist der nächste priorisierte Vorschlag für Prüfung und Freigabe.")
        if signal_summary.get("decision_mode_reason"):
            reasons.append(str(signal_summary["decision_mode_reason"]))
        else:
            top_drivers = (cockpit.get("peix_epi_score") or {}).get("top_drivers") or []
            if top_drivers:
                driver_labels = ", ".join(driver.get("label") for driver in top_drivers[:2] if driver.get("label"))
                reasons.append(f"Treiber dieser Woche: {driver_labels}.")
        while len(reasons) < 3:
            reasons.append("AMELAG, SurvStat und Vorhersage werden gemeinsam für die Wochenentscheidung gewichtet.")
        return reasons[:3]

    def _forecast_direction(self, region: dict[str, Any]) -> str:
        if region.get("tooltip", {}).get("forecast_trend"):
            return str(region["tooltip"]["forecast_trend"])
        change = float(region.get("change_pct") or 0.0)
        if change >= 10:
            return "aufwärts"
        if change <= -10:
            return "abwärts"
        return "seitwärts"

    def _priority_explanation(
        self,
        *,
        region: dict[str, Any],
        suggestion: dict[str, Any],
        forecast_direction: str,
        severity_score: int,
        momentum_score: int,
        actionability_score: int,
        decision_mode: str,
    ) -> str:
        trend = str(region.get("trend") or "stabil")
        name = str(region.get("name") or "Die Region")
        if decision_mode == "supply_window":
            return (
                f"{name} bleibt im Fokus, weil Versorgungssignal und Kontext ein Aktivierungsfenster öffnen. "
                "Das ist keine reine Welleneskalation, sondern eine defensive Versorgungschance."
            )
        if momentum_score < 40 and severity_score >= 70:
            return (
                f"{name} beschleunigt aktuell nicht, bleibt aber wegen hohem Ausgangsniveau und hoher Umsetzbarkeit "
                "für Prüfung und Vorbereitung priorisiert."
            )
        if momentum_score >= 60 and forecast_direction == "aufwärts":
            return (
                f"{name} zeigt ein frühes Signal: steigende Dynamik, aufwärts gerichtete Vorhersage und hohe Umsetzbarkeit."
            )
        if trend == "fallend" and actionability_score >= 65:
            return (
                f"{name} fällt kurzfristig, bleibt aber für defensive Planung relevant: Niveau und Umsetzbarkeit sind noch hoch."
            )
        if suggestion.get("reason"):
            return str(suggestion["reason"])
        return f"{name} wird aus epidemiologischer Lage, Vorhersage und Umsetzungschance priorisiert."

    def _campaign_state_counts(self, cards: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for card in cards:
            counts[str(card.get("lifecycle_state") or "PREPARE")] += 1
        return dict(sorted(counts.items()))

    def _campaign_sort_key(self, item: dict[str, Any]) -> tuple[Any, ...]:
        lifecycle = str(item.get("lifecycle_state") or "").upper()
        blockers = item.get("publish_blockers") or []
        freshness = str(item.get("freshness_state") or "").lower()
        return (
            item.get("is_publishable", False),
            QUEUE_LIFECYCLE_PRIORITY.get(lifecycle, 0),
            freshness == "current",
            freshness == "scheduled",
            -len(blockers),
            float(item.get("priority_score") or item.get("urgency_score") or 0.0),
            float(item.get("signal_confidence_pct") or item.get("confidence") or 0.0),
            str(item.get("updated_at") or item.get("created_at") or ""),
        )

    def _build_campaign_queue(
        self,
        cards: list[dict[str, Any]],
        *,
        visible_limit: int = 8,
    ) -> dict[str, Any]:
        active_cards = [card for card in cards if card.get("lifecycle_state") not in {"EXPIRED", "ARCHIVED"}]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        archived_cards: list[dict[str, Any]] = []

        for card in cards:
            if card.get("lifecycle_state") in {"EXPIRED", "ARCHIVED"}:
                archived_cards.append(card)
                continue
            grouped[dedupe_group_id(card)].append(card)

        primary_cards: list[dict[str, Any]] = []
        for group_cards in grouped.values():
            ranked = sorted(group_cards, key=self._campaign_sort_key, reverse=True)
            primary = dict(ranked[0])
            primary["is_primary_variant"] = True
            primary["variant_count"] = len(ranked)
            primary["variants"] = [
                {
                    "id": item.get("id"),
                    "status": item.get("status"),
                    "lifecycle_state": item.get("lifecycle_state"),
                    "display_title": item.get("display_title"),
                }
                for item in ranked[1:]
            ]
            primary_cards.append(primary)

        primary_cards.sort(key=self._campaign_sort_key, reverse=True)
        visible_cards = self._select_visible_queue_cards(primary_cards, limit=visible_limit)

        return {
            "active_cards": active_cards,
            "primary_cards": primary_cards,
            "visible_cards": visible_cards,
            "archived_cards": archived_cards,
            "summary": {
                "visible_cards": len(visible_cards),
                "hidden_backlog_cards": max(len(primary_cards) - len(visible_cards), 0),
            },
        }

    def _select_visible_queue_cards(
        self,
        cards: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        if len(cards) <= limit:
            return cards

        by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for card in cards:
            by_lane[str(card.get("lifecycle_state") or "PREPARE").upper()].append(card)

        selected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for lane in QUEUE_LANE_ORDER:
            lane_cards = by_lane.get(lane) or []
            if not lane_cards:
                continue
            card = lane_cards[0]
            card_id = str(card.get("id") or "")
            if card_id and card_id not in seen_ids:
                selected.append(card)
                seen_ids.add(card_id)
            if len(selected) >= limit:
                return selected[:limit]

        for lane in QUEUE_LANE_ORDER:
            for card in by_lane.get(lane, [])[1:]:
                card_id = str(card.get("id") or "")
                if card_id and card_id in seen_ids:
                    continue
                selected.append(card)
                if card_id:
                    seen_ids.add(card_id)
                if len(selected) >= limit:
                    return selected[:limit]

        return selected[:limit]

    def _decision_focus_card(self, cards: list[dict[str, Any]]) -> dict[str, Any] | None:
        preferred = [
            card for card in cards
            if str(card.get("lifecycle_state") or "").upper() in {"SYNC_READY", "APPROVE", "REVIEW"}
        ]
        if preferred:
            return preferred[0]
        return cards[0] if cards else None

    def _decision_top_products(
        self,
        cards: list[dict[str, Any]],
        top_card: dict[str, Any] | None,
    ) -> list[str]:
        products: list[str] = []
        for card in cards:
            product = str(card.get("recommended_product") or card.get("product") or "").strip()
            if product and product not in products:
                products.append(product)
            if len(products) >= 3:
                break
        if not products and top_card:
            product = str(top_card.get("recommended_product") or top_card.get("product") or "").strip()
            if product:
                products.append(product)
        return products

    def _recommended_action(
        self,
        *,
        decision_state: str,
        top_card: dict[str, Any] | None,
        top_regions: list[dict[str, Any]],
        decision_mode: str,
    ) -> str:
        primary_region = (
            top_card.get("decision_brief", {}).get("recommendation", {}).get("primary_region")
            if top_card else None
        ) or (top_regions[0].get("name") if top_regions else None)
        product = (
            top_card.get("recommended_product")
            or top_card.get("product")
            if top_card else None
        )
        top_summary = top_card.get("decision_brief", {}).get("summary_sentence") if top_card else None

        if decision_state == "GO" and top_summary:
            return str(top_summary)
        if decision_state == "GO":
            if primary_region and product:
                return f"Diese Woche freigeben: {product} in {primary_region} priorisieren."
            return "Diese Woche freigeben: die stärksten regionalen Vorschläge in die Aktivierung ziehen."

        if decision_mode == "supply_window":
            if primary_region and product:
                return f"Diese Woche vorbereiten: {product} in {primary_region} als Versorgungschance absichern, aber noch keinen nationalen Shift freigeben."
            return "Diese Woche vorbereiten: Versorgungssignale beobachten und nur prüfbare Vorschläge weiterziehen."
        if decision_mode == "mixed":
            if primary_region and product:
                return f"Diese Woche vorbereiten: {product} in {primary_region} priorisieren, weil Epi-Signal und Kontext gemeinsam tragen, aber noch keinen nationalen Shift freigeben."
            return "Diese Woche vorbereiten: Epi-Signal und Kontext beobachten und keine harte Aktivierung freigeben."
        if primary_region and product:
            return f"Diese Woche vorbereiten: {product} in {primary_region} priorisieren, aber noch keinen nationalen Shift freigeben."
        if primary_region:
            return f"Diese Woche vorbereiten: {primary_region} priorisieren und nur prüfbare Vorschläge weiterziehen."
        return "Diese Woche vorbereiten: Signal beobachten, Regionen priorisieren und keine harte Aktivierung freigeben."

    def _known_limits(
        self,
        cockpit: dict[str, Any],
        virus_typ: str,
        *,
        truth_coverage: dict[str, Any] | None = None,
        truth_validation_legacy: dict[str, Any] | None = None,
    ) -> list[str]:
        limits: list[str] = []
        truth = truth_coverage or self.get_truth_coverage()
        if truth.get("coverage_weeks", 0) < 26:
            limits.append("Kundennahe Daten decken noch keine 26 Wochen ab.")
        if truth.get("truth_freshness_state") == "stale":
            limits.append("Der letzte Import der Kundendaten liegt zu weit hinter der aktuellen epidemiologischen Woche.")
        if not truth.get("conversion_fields_present"):
            limits.append("In den Kundendaten fehlt noch mindestens eine belastbare Wirkungszahl wie Verkäufe, Bestellungen oder Umsatz.")
        if truth_validation_legacy and truth.get("coverage_weeks", 0) == 0:
            limits.append("Der sichtbare frühere Kundenlauf ist nur ein explorativer Hinweis und noch kein aktiver Bereich für Kundendaten.")
        if not (cockpit.get("backtest_summary", {}).get("latest_market") or {}).get("quality_gate", {}).get("overall_passed"):
            limits.append("Der Marktvergleich steht aktuell auf Beobachten.")
        series_points = (
            self.db.query(func.count(WastewaterAggregated.id))
            .filter(WastewaterAggregated.virus_typ == virus_typ)
            .scalar()
        ) or 0
        if series_points < 120:
            limits.append("Die virale Kernreihe ist noch relativ kurz für robuste Saisonabdeckung.")
        return limits

    def _signal_group_summary(self, peix: dict[str, Any]) -> dict[str, Any]:
        virus_scores = peix.get("virus_scores") or {}
        context_signals = peix.get("context_signals") or {}

        epidemic_core = round(sum(float(item.get("contribution") or 0.0) for item in virus_scores.values()), 1)
        forecast_contribution = round(float((context_signals.get("forecast") or {}).get("contribution") or 0.0), 1)
        supply_contribution = round(float((context_signals.get("shortage") or {}).get("contribution") or 0.0), 1)
        context_contribution = round(sum(
            float((context_signals.get(key) or {}).get("contribution") or 0.0)
            for key in ("weather", "search", "baseline")
        ), 1)

        decision_mode = self._decision_mode_from_contributions(
            epidemic_total=epidemic_core + forecast_contribution,
            supply_total=supply_contribution,
            context_total=context_contribution,
        )
        return {
            "driver_groups": {
                "epidemic_core": {"label": "Epi-Kern", "contribution": epidemic_core},
                "forecast_model": {"label": "Vorhersage", "contribution": forecast_contribution},
                "supply_window": {"label": "Versorgung", "contribution": supply_contribution},
                "context_window": {"label": "Wetter und Grundrauschen", "contribution": context_contribution},
            },
            "decision_mode": decision_mode["key"],
            "decision_mode_label": decision_mode["label"],
            "decision_mode_reason": decision_mode["reason"],
        }

    def _decision_mode_from_contributions(
        self,
        *,
        epidemic_total: float,
        supply_total: float,
        context_total: float,
    ) -> dict[str, str]:
        if supply_total >= max(8.0, epidemic_total * 0.7):
            return {
                "key": "supply_window",
                "label": "Versorgungsfenster",
                "reason": "Das aktuelle Signal wird vor allem durch Versorgung und Kontext getrieben, nicht durch eine reine Wellenbeschleunigung.",
            }
        if supply_total >= 4.0 and (supply_total + context_total) >= epidemic_total:
            return {
                "key": "mixed",
                "label": "Gemischtes Signal",
                "reason": "Epi-Kern, Vorhersage und Kontext zeigen gleichzeitig nach oben. Die Entscheidung bleibt deshalb bewusst defensiv.",
            }
        return {
            "key": "epidemic_wave",
            "label": "Atemwegswelle",
            "reason": "AMELAG, SurvStat und Vorhersage tragen die Entscheidung. Versorgung bleibt Zusatzsignal, nicht Hauptbeweis.",
        }

    def _severity_score(self, region: dict[str, Any]) -> int:
        impact = float(region.get("signal_score") or region.get("impact_probability") or region.get("peix_score") or 0.0)
        intensity = float(region.get("intensity") or 0.0) * 100.0
        return int(round(max(impact, intensity)))

    def _momentum_score(self, *, region: dict[str, Any], forecast_direction: str) -> int:
        change = max(-40.0, min(40.0, float(region.get("change_pct") or 0.0)))
        score = 50.0 + (change * 0.7)
        trend = str(region.get("trend") or "").lower()
        if trend == "steigend":
            score += 6.0
        elif trend == "fallend":
            score -= 6.0

        if forecast_direction == "aufwärts":
            score += 18.0
        elif forecast_direction == "abwärts":
            score -= 18.0

        return int(round(max(0.0, min(100.0, score))))

    def _actionability_score(
        self,
        *,
        region: dict[str, Any],
        suggestion: dict[str, Any],
        severity_score: int,
        momentum_score: int,
    ) -> int:
        recommendation_ref = region.get("recommendation_ref") or {}
        urgency_score = float(recommendation_ref.get("urgency_score") or 0.0)
        urgency_normalized = min(max(urgency_score / 2.0, 0.0), 100.0)
        package_bonus = 10.0 if recommendation_ref.get("card_id") or suggestion.get("budget_shift_pct") else 0.0
        actionability = (
            severity_score * 0.50
            + urgency_normalized * 0.25
            + max(momentum_score, 25) * 0.15
            + package_bonus
        )
        return int(round(max(0.0, min(100.0, actionability))))

    def _region_decision_mode(self, peix_region: dict[str, Any]) -> dict[str, str]:
        contributions = peix_region.get("layer_contributions") or {}
        epidemic_total = float(contributions.get("Bio") or 0.0) + float(contributions.get("Forecast") or 0.0)
        supply_total = float(contributions.get("Shortage") or 0.0)
        context_total = sum(float(contributions.get(key) or 0.0) for key in ("Weather", "Search", "Baseline"))
        return self._decision_mode_from_contributions(
            epidemic_total=epidemic_total,
            supply_total=supply_total,
            context_total=context_total,
        )

    def _region_source_trace(self, peix_region: dict[str, Any]) -> list[str]:
        trace = ["AMELAG", "SurvStat", "Vorhersage", "ARE"]
        contributions = peix_region.get("layer_contributions") or {}
        if float(contributions.get("Shortage") or 0.0) > 0:
            trace.append("BfArM")
        if float(contributions.get("Weather") or 0.0) > 0:
            trace.append("Wetter")
        return trace

    def _read_model_metadata(self, virus_typ: str) -> dict[str, Any]:
        slug = _virus_slug(virus_typ)
        metadata_path = Path(_ML_MODELS_DIR) / slug / "metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _collect_outcome_rows(
        self,
        *,
        records: list[dict[str, Any]],
        csv_payload: str | None,
        brand: str,
        source_label: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []

        for index, record in enumerate(records, start=1):
            rows.append({
                "row_number": index,
                "raw_row": dict(record),
                "values": {**record, "brand": brand, "source_label": source_label},
            })

        if csv_payload:
            csv_rows, csv_issues = self._parse_csv_payload(
                csv_payload,
                brand=brand,
                source_label=source_label,
            )
            rows.extend(csv_rows)
            issues.extend(csv_issues)

        return rows, issues

    def _parse_csv_payload(
        self,
        csv_payload: str,
        *,
        brand: str,
        source_label: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        sanitized = csv_payload.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(sanitized))
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or []) if str(name or "").strip()]

        issues: list[dict[str, Any]] = []
        missing_headers = [
            header for header in ("week_start", "product", "region_code", "media_spend_eur")
            if header not in fieldnames
        ]
        if missing_headers:
            issues.append(self._issue_dict(
                batch_id="preview",
                row_number=None,
                field_name="header",
                issue_code="missing_headers",
                message=f"Folgende CSV-Spalten fehlen: {', '.join(missing_headers)}.",
                raw_row={"fieldnames": fieldnames},
            ))

        rows: list[dict[str, Any]] = []
        for index, raw in enumerate(reader, start=2):
            cleaned = {str(key or "").strip(): value for key, value in raw.items() if str(key or "").strip()}
            cleaned.setdefault("brand", brand)
            cleaned.setdefault("source_label", source_label)
            rows.append({
                "row_number": index,
                "raw_row": cleaned,
                "values": cleaned,
            })
        return rows, issues

    def _coerce_week_start(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.replace(tzinfo=None)
        return parsed

    def _float_or_none(self, value: Any) -> float | None:
        if value in (None, "", "null"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _truth_gate(self, truth_coverage: dict[str, Any]) -> dict[str, Any]:
        return self.truth_gate_service.evaluate(truth_coverage)

    def _latest_import_batch(self, *, brand: str) -> MediaOutcomeImportBatch | None:
        return (
            self.db.query(MediaOutcomeImportBatch)
            .filter(
                func.lower(MediaOutcomeImportBatch.brand) == str(brand or "gelo").lower(),
                MediaOutcomeImportBatch.status.in_(("imported", "partial_success")),
            )
            .order_by(MediaOutcomeImportBatch.uploaded_at.desc(), MediaOutcomeImportBatch.id.desc())
            .first()
        )

    def _latest_epi_reference_week(self, *, virus_typ: str | None = None) -> datetime | None:
        wastewater_query = self.db.query(func.max(WastewaterAggregated.datum))
        if virus_typ:
            wastewater_query = wastewater_query.filter(WastewaterAggregated.virus_typ == virus_typ)
        wastewater_max = wastewater_query.scalar()
        if wastewater_max:
            return wastewater_max

        survstat_max = self.db.query(func.max(SurvstatWeeklyData.week_start)).scalar()
        return survstat_max

    def _truth_freshness_state(
        self,
        *,
        latest_truth_week: datetime | None,
        reference_week: datetime | None,
    ) -> str:
        if latest_truth_week is None:
            return "missing"
        if reference_week is None:
            return "unknown"
        return "fresh" if (reference_week - latest_truth_week) <= timedelta(days=14) else "stale"

    def _normalize_outcome_row(
        self,
        *,
        row: dict[str, Any],
        brand: str,
        source_label: str,
    ) -> dict[str, Any]:
        values = row.get("values") or {}
        raw_row = row.get("raw_row") or values
        row_number = row.get("row_number")
        issues: list[dict[str, Any]] = []

        week_start = self._coerce_week_start(values.get("week_start"))
        if week_start is None:
            issues.append(self._issue_dict(
                batch_id="preview",
                row_number=row_number,
                field_name="week_start",
                issue_code="invalid_week_start",
                message="`week_start` fehlt oder ist kein gültiges ISO-Datum.",
                raw_row=raw_row,
            ))

        product, product_issue = self._normalize_outcome_product(
            brand=brand,
            raw_product=values.get("product"),
        )
        if product_issue:
            issues.append(self._issue_dict(
                batch_id="preview",
                row_number=row_number,
                field_name="product",
                issue_code=product_issue["code"],
                message=product_issue["message"],
                raw_row=raw_row,
            ))

        region_code, region_issue = self._normalize_outcome_region(values.get("region_code"))
        if region_issue:
            issues.append(self._issue_dict(
                batch_id="preview",
                row_number=row_number,
                field_name="region_code",
                issue_code=region_issue["code"],
                message=region_issue["message"],
                raw_row=raw_row,
            ))

        metrics: dict[str, float | None] = {
            "media_spend_eur": self._float_or_none(values.get("media_spend_eur")),
            "impressions": self._float_or_none(values.get("impressions")),
            "clicks": self._float_or_none(values.get("clicks")),
            "qualified_visits": self._float_or_none(values.get("qualified_visits")),
            "search_lift_index": self._float_or_none(values.get("search_lift_index")),
            "sales_units": self._float_or_none(values.get("sales_units")),
            "order_count": self._float_or_none(values.get("order_count")),
            "revenue_eur": self._float_or_none(values.get("revenue_eur")),
        }
        if metrics["media_spend_eur"] is None:
            issues.append(self._issue_dict(
                batch_id="preview",
                row_number=row_number,
                field_name="media_spend_eur",
                issue_code="missing_media_spend",
                message="`media_spend_eur` ist Pflicht und muss numerisch befüllt sein.",
                raw_row=raw_row,
            ))
        if not any(metrics[field_name] is not None for field_name in CONVERSION_OUTCOME_FIELD_NAMES):
            issues.append(self._issue_dict(
                batch_id="preview",
                row_number=row_number,
                field_name="conversion",
                issue_code="missing_conversion_metric",
                message="Mindestens eine Wirkungszahl (`sales_units`, `order_count` oder `revenue_eur`) ist erforderlich.",
                raw_row=raw_row,
            ))

        extra_data = values.get("extra_data")
        if extra_data is None:
            extra_data = {}
        elif not isinstance(extra_data, dict):
            extra_data = {"raw_extra_data": extra_data}

        return {
            "issues": issues,
            "week_start": week_start,
            "product": product,
            "region_code": region_code,
            "brand": brand,
            "source_label": source_label,
            "metrics": metrics,
            "extra_data": extra_data,
        }

    def _normalize_outcome_product(
        self,
        *,
        brand: str,
        raw_product: Any,
    ) -> tuple[str | None, dict[str, str] | None]:
        raw_value = str(raw_product or "").strip()
        if not raw_value:
            return None, {"code": "missing_product", "message": "Produktname fehlt."}

        normalized = ProductCatalogService._normalize_name(raw_value)
        compact = "".join(ch for ch in normalized if ch.isalnum())
        products = (
            self.db.query(BrandProduct)
            .filter(
                func.lower(BrandProduct.brand) == str(brand or "gelo").lower(),
                BrandProduct.active.is_(True),
            )
            .all()
        )
        if not products:
            return None, {
                "code": "missing_product_catalog",
                "message": f"Für die Marke `{brand}` ist kein aktiver Produktkatalog vorhanden.",
            }

        exact_map: dict[str, str] = {}
        compact_map: dict[str, str] = {}
        for product in products:
            canonical_name = str(product.product_name or "").strip()
            normalized_name = ProductCatalogService._normalize_name(canonical_name)
            if normalized_name:
                exact_map.setdefault(normalized_name, canonical_name)
                compact_map.setdefault("".join(ch for ch in normalized_name if ch.isalnum()), canonical_name)

        if normalized in exact_map:
            return exact_map[normalized], None
        if compact in compact_map:
            return compact_map[compact], None

        fuzzy_matches = [
            canonical
            for norm_name, canonical in exact_map.items()
            if normalized in norm_name or norm_name in normalized
        ]
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0], None

        return None, {
            "code": "unknown_product",
            "message": f"Produkt `{raw_value}` konnte nicht auf den aktiven Produktkatalog gemappt werden.",
        }

    def _normalize_outcome_region(self, raw_region: Any) -> tuple[str | None, dict[str, str] | None]:
        raw_value = str(raw_region or "").strip()
        if not raw_value:
            return None, {"code": "missing_region", "message": "Region fehlt."}

        if raw_value.lower() in {"de", "deutschland", "national"}:
            return "DE", None
        normalized = normalize_region_code(raw_value)
        if normalized in BUNDESLAND_NAMES:
            return normalized, None
        return None, {
            "code": "invalid_region",
            "message": f"Region `{raw_value}` ist weder ein Bundesland-Code noch ein bekannter Bundeslandname.",
        }

    def _find_existing_outcome(
        self,
        *,
        brand: str,
        source_label: str,
        week_start: datetime,
        product: str,
        region_code: str,
    ) -> MediaOutcomeRecord | None:
        return (
            self.db.query(MediaOutcomeRecord)
            .filter(
                MediaOutcomeRecord.week_start == week_start,
                func.lower(MediaOutcomeRecord.brand) == brand,
                MediaOutcomeRecord.product == product,
                MediaOutcomeRecord.region_code == region_code,
                MediaOutcomeRecord.source_label == source_label,
            )
            .first()
        )

    def _project_truth_coverage(
        self,
        *,
        brand: str,
        normalized_rows: list[dict[str, Any]],
        virus_typ: str | None,
        replace_existing: bool,
        validate_only: bool,
    ) -> dict[str, Any]:
        existing_rows = (
            self.db.query(MediaOutcomeRecord)
            .filter(func.lower(MediaOutcomeRecord.brand) == str(brand or "gelo").lower())
            .all()
        )
        synthetic_rows = [
            {
                "week_start": row.week_start,
                "brand": row.brand,
                "product": row.product,
                "region_code": row.region_code,
                "source_label": row.source_label,
                "metrics": {
                    field_name: getattr(row, field_name)
                    for field_name in (
                        *REQUIRED_OUTCOME_FIELD_NAMES,
                        *CONVERSION_OUTCOME_FIELD_NAMES,
                        *OPTIONAL_OUTCOME_FIELD_NAMES,
                    )
                },
            }
            for row in existing_rows
        ]
        keyed_rows: dict[tuple[str, str, datetime, str, str], dict[str, Any]] = {}
        for row in synthetic_rows:
            key = (
                str(row["brand"]).lower(),
                str(row["source_label"]),
                row["week_start"],
                str(row["product"]),
                str(row["region_code"]),
            )
            keyed_rows[key] = row

        for row in normalized_rows:
            key = (
                str(brand).lower(),
                str(row["source_label"]),
                row["week_start"],
                row["product"],
                row["region_code"],
            )
            if key in keyed_rows and not replace_existing and validate_only:
                continue
            keyed_rows[key] = {
                "week_start": row["week_start"],
                "brand": brand,
                "product": row["product"],
                "region_code": row["region_code"],
                "source_label": row["source_label"],
                "metrics": row["metrics"],
            }
        return self._coverage_from_rows(list(keyed_rows.values()), brand=brand, virus_typ=virus_typ)

    def _coverage_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        brand: str,
        virus_typ: str | None,
    ) -> dict[str, Any]:
        latest_import_batch = self._latest_import_batch(brand=brand)
        reference_week = self._latest_epi_reference_week(virus_typ=virus_typ)
        if not rows:
            return {
                "coverage_weeks": 0,
                "latest_week": None,
                "regions_covered": 0,
                "products_covered": 0,
                "outcome_fields_present": [],
                "required_fields_present": [],
                "conversion_fields_present": [],
                "trust_readiness": "noch_nicht_angeschlossen",
                "truth_freshness_state": "missing",
                "source_labels": [],
                "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
                "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
                "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
            }

        week_values = sorted({row["week_start"] for row in rows if row.get("week_start")})
        weeks = [value.date().isoformat() for value in week_values]
        regions = {str(row.get("region_code")) for row in rows if row.get("region_code")}
        products = {str(row.get("product")) for row in rows if row.get("product")}
        source_labels = sorted({str(row.get("source_label")) for row in rows if row.get("source_label")})
        fields_present = [
            label
            for field_name, label in METRIC_FIELD_LABELS.items()
            if any((row.get("metrics") or {}).get(field_name) is not None for row in rows)
        ]
        required_fields_present = [
            METRIC_FIELD_LABELS[field_name]
            for field_name in REQUIRED_OUTCOME_FIELD_NAMES
            if any((row.get("metrics") or {}).get(field_name) is not None for row in rows)
        ]
        conversion_fields_present = [
            METRIC_FIELD_LABELS[field_name]
            for field_name in CONVERSION_OUTCOME_FIELD_NAMES
            if any((row.get("metrics") or {}).get(field_name) is not None for row in rows)
        ]
        coverage_weeks = len(weeks)
        if coverage_weeks >= 52:
            readiness = "belastbar"
        elif coverage_weeks >= 26:
            readiness = "im_aufbau"
        elif coverage_weeks > 0:
            readiness = "erste_signale"
        else:
            readiness = "noch_nicht_angeschlossen"

        latest_week_dt = week_values[-1] if week_values else None
        return {
            "coverage_weeks": coverage_weeks,
            "latest_week": weeks[-1] if weeks else None,
            "regions_covered": len(regions),
            "products_covered": len(products),
            "outcome_fields_present": fields_present,
            "required_fields_present": required_fields_present,
            "conversion_fields_present": conversion_fields_present,
            "trust_readiness": readiness,
            "truth_freshness_state": self._truth_freshness_state(
                latest_truth_week=latest_week_dt,
                reference_week=reference_week,
            ),
            "source_labels": source_labels,
            "last_imported_at": latest_import_batch.uploaded_at.isoformat() if latest_import_batch and latest_import_batch.uploaded_at else None,
            "latest_batch_id": latest_import_batch.batch_id if latest_import_batch else None,
            "latest_source_label": latest_import_batch.source_label if latest_import_batch else None,
        }

    def _issue_dict(
        self,
        *,
        batch_id: str,
        row_number: int | None,
        field_name: str | None,
        issue_code: str,
        message: str,
        raw_row: Any,
    ) -> dict[str, Any]:
        return {
            "batch_id": batch_id,
            "row_number": row_number,
            "field_name": field_name,
            "issue_code": issue_code,
            "message": message,
            "raw_row": raw_row,
        }

    def _issue_response(self, issue: dict[str, Any]) -> dict[str, Any]:
        return {
            "row_number": issue.get("row_number"),
            "field_name": issue.get("field_name"),
            "issue_code": issue.get("issue_code"),
            "message": issue.get("message"),
            "raw_row": issue.get("raw_row"),
        }

    def _issue_to_dict(self, issue: MediaOutcomeImportIssue) -> dict[str, Any]:
        return {
            "row_number": issue.row_number,
            "field_name": issue.field_name,
            "issue_code": issue.issue_code,
            "message": issue.message,
            "raw_row": issue.raw_row,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
        }

    def _batch_to_dict(self, batch: MediaOutcomeImportBatch) -> dict[str, Any]:
        return {
            "batch_id": batch.batch_id,
            "brand": batch.brand,
            "source_label": batch.source_label,
            "source_system": batch.source_system,
            "external_batch_id": batch.external_batch_id,
            "ingestion_mode": batch.ingestion_mode,
            "file_name": batch.file_name,
            "status": batch.status,
            "rows_total": batch.rows_total,
            "rows_valid": batch.rows_valid,
            "rows_imported": batch.rows_imported,
            "rows_rejected": batch.rows_rejected,
            "rows_duplicate": batch.rows_duplicate,
            "week_min": batch.week_min.isoformat() if batch.week_min else None,
            "week_max": batch.week_max.isoformat() if batch.week_max else None,
            "coverage_after_import": batch.coverage_after_import or {},
            "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else None,
        }
