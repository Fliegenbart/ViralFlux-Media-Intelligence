from __future__ import annotations
from app.core.time import utc_now

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
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
from app.services.media.v2.campaigns import build_campaigns_payload
from app.services.media.v2.decision import build_decision_payload
from app.services.media.v2.evidence import build_evidence_payload
from app.services.media.v2 import outcomes as outcomes_module
from app.services.media.v2.regions import build_regions_payload

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
        return build_decision_payload(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )

    def get_regions_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return build_regions_payload(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )

    def get_campaigns_payload(
        self,
        *,
        brand: str = "gelo",
        limit: int = 120,
    ) -> dict[str, Any]:
        return build_campaigns_payload(self, brand=brand, limit=limit)

    def get_evidence_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return build_evidence_payload(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )

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
            "generated_at": utc_now().isoformat(),
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
        return outcomes_module.build_truth_coverage(
            self,
            brand=brand,
            virus_typ=virus_typ,
        )

    def get_truth_evidence(
        self,
        *,
        brand: str = "gelo",
        virus_typ: str | None = None,
    ) -> dict[str, Any]:
        return outcomes_module.build_truth_evidence(
            self,
            brand=brand,
            virus_typ=virus_typ,
        )

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
        return outcomes_module.import_outcomes(
            self,
            source_label=source_label,
            records=records,
            csv_payload=csv_payload,
            brand=brand,
            replace_existing=replace_existing,
            validate_only=validate_only,
            file_name=file_name,
        )

    def list_outcome_import_batches(
        self,
        *,
        brand: str = "gelo",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return outcomes_module.list_outcome_import_batches(
            self,
            brand=brand,
            limit=limit,
        )

    def get_outcome_import_batch_detail(self, *, batch_id: str) -> dict[str, Any] | None:
        return outcomes_module.get_outcome_import_batch_detail(
            self,
            batch_id=batch_id,
        )

    def outcome_template_csv(self) -> str:
        return outcomes_module.outcome_template_csv(self)

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
        return outcomes_module._collect_outcome_rows(
            self,
            records=records,
            csv_payload=csv_payload,
            brand=brand,
            source_label=source_label,
        )

    def _parse_csv_payload(
        self,
        csv_payload: str,
        *,
        brand: str,
        source_label: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return outcomes_module._parse_csv_payload(
            self,
            csv_payload,
            brand=brand,
            source_label=source_label,
        )

    def _coerce_week_start(self, value: Any) -> datetime | None:
        return outcomes_module._coerce_week_start(self, value)

    def _float_or_none(self, value: Any) -> float | None:
        return outcomes_module._float_or_none(self, value)

    def _truth_gate(self, truth_coverage: dict[str, Any]) -> dict[str, Any]:
        return self.truth_gate_service.evaluate(truth_coverage)

    def _latest_import_batch(self, *, brand: str) -> MediaOutcomeImportBatch | None:
        return outcomes_module._latest_import_batch(self, brand=brand)

    def _uses_legacy_outcome_batch_schema(self) -> bool:
        return outcomes_module._uses_legacy_outcome_batch_schema(self)

    def _legacy_import_batch_rows(self, *, brand: str, limit: int) -> list[SimpleNamespace]:
        return outcomes_module._legacy_import_batch_rows(self, brand=brand, limit=limit)

    def _legacy_import_batch_detail(self, *, batch_id: str) -> SimpleNamespace | None:
        return outcomes_module._legacy_import_batch_detail(self, batch_id=batch_id)

    def _latest_epi_reference_week(self, *, virus_typ: str | None = None) -> datetime | None:
        return outcomes_module._latest_epi_reference_week(self, virus_typ=virus_typ)

    def _truth_freshness_state(
        self,
        *,
        latest_truth_week: datetime | None,
        reference_week: datetime | None,
    ) -> str:
        return outcomes_module._truth_freshness_state(
            self,
            latest_truth_week=latest_truth_week,
            reference_week=reference_week,
        )

    def _normalize_outcome_row(
        self,
        *,
        row: dict[str, Any],
        brand: str,
        source_label: str,
    ) -> dict[str, Any]:
        return outcomes_module._normalize_outcome_row(
            self,
            row=row,
            brand=brand,
            source_label=source_label,
        )

    def _normalize_outcome_product(
        self,
        *,
        brand: str,
        raw_product: Any,
    ) -> tuple[str | None, dict[str, str] | None]:
        return outcomes_module._normalize_outcome_product(
            self,
            brand=brand,
            raw_product=raw_product,
        )

    def _normalize_outcome_region(self, raw_region: Any) -> tuple[str | None, dict[str, str] | None]:
        return outcomes_module._normalize_outcome_region(self, raw_region)

    def _find_existing_outcome(
        self,
        *,
        brand: str,
        source_label: str,
        week_start: datetime,
        product: str,
        region_code: str,
    ) -> MediaOutcomeRecord | None:
        return outcomes_module._find_existing_outcome(
            self,
            brand=brand,
            source_label=source_label,
            week_start=week_start,
            product=product,
            region_code=region_code,
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
        return outcomes_module._project_truth_coverage(
            self,
            brand=brand,
            normalized_rows=normalized_rows,
            virus_typ=virus_typ,
            replace_existing=replace_existing,
            validate_only=validate_only,
        )

    def _coverage_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        brand: str,
        virus_typ: str | None,
    ) -> dict[str, Any]:
        return outcomes_module._coverage_from_rows(
            self,
            rows,
            brand=brand,
            virus_typ=virus_typ,
        )

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
        return outcomes_module._issue_dict(
            self,
            batch_id=batch_id,
            row_number=row_number,
            field_name=field_name,
            issue_code=issue_code,
            message=message,
            raw_row=raw_row,
        )

    def _issue_response(self, issue: dict[str, Any]) -> dict[str, Any]:
        return outcomes_module._issue_response(self, issue)

    def _issue_to_dict(self, issue: MediaOutcomeImportIssue) -> dict[str, Any]:
        return outcomes_module._issue_to_dict(self, issue)

    def _batch_to_dict(self, batch: MediaOutcomeImportBatch | SimpleNamespace) -> dict[str, Any]:
        return outcomes_module._batch_to_dict(self, batch)
