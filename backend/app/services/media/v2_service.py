from __future__ import annotations

import csv
import io
import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    BacktestRun,
    ForecastAccuracyLog,
    GoogleTrendsData,
    MarketingOpportunity,
    MediaOutcomeRecord,
    MLForecast,
    SurvstatWeeklyData,
    WastewaterAggregated,
)
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.cockpit_service import MediaCockpitService
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.recommendation_contracts import (
    BUNDESLAND_NAMES,
    dedupe_group_id,
    enrich_card_v2,
    to_card_response,
)
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
    "media_spend_eur": "Media Spend",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "qualified_visits": "Qualifizierte Besuche",
    "search_lift_index": "Search Lift",
    "sales_units": "Sales",
    "order_count": "Orders",
    "revenue_eur": "Revenue",
}


class MediaV2Service:
    """View-spezifische Contracts für Decision, Regionen, Kampagnen und Evidenz."""

    def __init__(self, db: Session):
        self.db = db
        self.cockpit_service = MediaCockpitService(db)
        self.engine = MarketingOpportunityEngine(db)

    def get_decision_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
        truth_coverage = self.get_truth_coverage(brand=brand)
        model_lineage = self.get_model_lineage(virus_typ=virus_typ)
        campaign_cards = self._campaign_cards(brand=brand, limit=80)
        top_card = campaign_cards[0] if campaign_cards else None
        top_regions = cockpit.get("map", {}).get("top_regions", [])[:3]
        market = cockpit.get("backtest_summary", {}).get("latest_market") or {}

        freshness_state = self._decision_freshness_state(cockpit.get("source_status", {}))
        has_truth = truth_coverage.get("coverage_weeks", 0) >= 26
        market_passed = bool((market.get("quality_gate") or {}).get("overall_passed"))
        publishable_cards = [card for card in campaign_cards if card.get("is_publishable")]
        has_publishable = len(publishable_cards) > 0
        drift_state = str(model_lineage.get("drift_state") or "unknown")
        decision_state = "GO" if all([
            freshness_state == "fresh",
            market_passed,
            has_truth,
            has_publishable,
            drift_state != "warning",
        ]) else "WATCH"

        risk_flags: list[str] = []
        if freshness_state != "fresh":
            risk_flags.append("Kernquellen sind nicht vollständig frisch.")
        if not market_passed:
            risk_flags.append("Proxy-Validierung ist aktuell nicht im GO-Korridor.")
        if not has_truth:
            risk_flags.append("Truth-Layer ist noch nicht breit genug für harte Freigabe.")
        if drift_state == "warning":
            risk_flags.append("Modell-Drift ist im Monitoring auffällig.")
        if not has_publishable:
            risk_flags.append("Es gibt aktuell kein freigabefähiges Kampagnenpaket.")

        why_now = self._build_why_now(top_card=top_card, top_regions=top_regions, cockpit=cockpit)

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "generated_at": datetime.utcnow().isoformat(),
            "weekly_decision": {
                "decision_state": decision_state,
                "decision_window": {
                    "start": cockpit.get("map", {}).get("date"),
                    "horizon_days": top_card.get("decision_brief", {}).get("horizon", {}).get("max_days") if top_card else None,
                },
                "recommended_action": top_card.get("decision_brief", {}).get("summary_sentence") if top_card else None,
                "top_regions": [
                    {
                        "code": item.get("code"),
                        "name": item.get("name"),
                        "signal_score": item.get("peix_score") or item.get("impact_probability"),
                        "trend": item.get("trend"),
                    }
                    for item in top_regions
                ],
                "top_products": [
                    card.get("recommended_product")
                    for card in publishable_cards[:3]
                    if card.get("recommended_product")
                ] or ([top_card.get("recommended_product")] if top_card and top_card.get("recommended_product") else []),
                "budget_shift": top_card.get("budget_shift_pct") if top_card else None,
                "why_now": why_now,
                "risk_flags": risk_flags,
                "freshness_state": freshness_state,
                "proxy_state": "passed" if market_passed else "watch",
                "truth_state": truth_coverage.get("trust_readiness"),
                "signal_stack_summary": self.get_signal_stack(virus_typ=virus_typ).get("summary"),
            },
            "top_recommendations": campaign_cards[:3],
            "wave_run_id": (cockpit.get("backtest_summary", {}).get("latest_market") or {}).get("run_id"),
            "backtest_summary": cockpit.get("backtest_summary"),
            "model_lineage": model_lineage,
            "truth_coverage": truth_coverage,
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
            enriched_regions[code] = {
                **region,
                "peix_score": region.get("peix_score") or peix_region.get("score_0_100"),
                "forecast_direction": forecast_direction,
                "signal_drivers": peix_region.get("top_drivers") or [],
                "layer_contributions": peix_region.get("layer_contributions") or {},
                "budget_logic": suggestion.get("reason") or region.get("tooltip", {}).get("recommendation_text"),
                "priority_explanation": self._priority_explanation(region=region, suggestion=suggestion, forecast_direction=forecast_direction),
                "source_trace": [
                    "AMELAG",
                    "SurvStat",
                    "Forecast",
                    "ARE",
                ],
            }

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
            },
            "top_regions": [
                enriched_regions.get(item.get("code"), {"code": item.get("code")}) | {"code": item.get("code")}
                for item in map_section.get("top_regions", [])
                if item.get("code") in enriched_regions
            ],
            "decision_state": decision_payload.get("weekly_decision", {}).get("decision_state"),
        }

    def get_campaigns_payload(
        self,
        *,
        brand: str = "gelo",
        limit: int = 120,
    ) -> dict[str, Any]:
        cards = self._campaign_cards(brand=brand, limit=limit)
        active_cards = [card for card in cards if card.get("lifecycle_state") not in {"EXPIRED", "ARCHIVED"}]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for card in active_cards:
            grouped[dedupe_group_id(card)].append(card)

        primary_cards: list[dict[str, Any]] = []
        archived_cards: list[dict[str, Any]] = []
        for card in cards:
            if card.get("lifecycle_state") in {"EXPIRED", "ARCHIVED"}:
                archived_cards.append(card)

        for group_cards in grouped.values():
            ranked = sorted(
                group_cards,
                key=lambda item: (
                    item.get("is_publishable", False),
                    float(item.get("urgency_score") or 0.0),
                    float(item.get("confidence") or 0.0),
                    str(item.get("updated_at") or ""),
                ),
                reverse=True,
            )
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

        primary_cards.sort(
            key=lambda item: (
                item.get("is_publishable", False),
                float(item.get("urgency_score") or 0.0),
                float(item.get("confidence") or 0.0),
            ),
            reverse=True,
        )

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "cards": primary_cards,
            "archived_cards": archived_cards[:20],
            "summary": {
                "total_cards": len(cards),
                "active_cards": len(active_cards),
                "deduped_cards": len(primary_cards),
                "publishable_cards": len([card for card in primary_cards if card.get("is_publishable")]),
                "expired_cards": len([card for card in cards if card.get("lifecycle_state") == "EXPIRED"]),
                "states": self._campaign_state_counts(primary_cards),
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
        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "generated_at": datetime.utcnow().isoformat(),
            "proxy_validation": backtest_summary.get("latest_market"),
            "truth_validation": backtest_summary.get("latest_customer"),
            "recent_runs": backtest_summary.get("recent_runs") or [],
            "data_freshness": cockpit.get("data_freshness") or {},
            "source_status": cockpit.get("source_status") or {},
            "signal_stack": self.get_signal_stack(virus_typ=virus_typ),
            "model_lineage": self.get_model_lineage(virus_typ=virus_typ),
            "truth_coverage": self.get_truth_coverage(brand=brand),
            "known_limits": self._known_limits(cockpit, virus_typ),
        }

    def get_signal_stack(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source="RKI_ARE")
        data_freshness = cockpit.get("data_freshness") or {}
        source_status_items = {
            item.get("source_key"): item
            for item in (cockpit.get("source_status") or {}).get("items", [])
        }
        peix = cockpit.get("peix_epi_score") or PeixEpiScoreService(self.db).build(virus_typ=virus_typ)

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
                "feature_families": [
                    "AMELAG-Lags",
                    "Cross-Disease-Lags",
                    "SurvStat-Lags",
                    "Google Trends",
                    "Schulferien",
                    "Wetter-Kontext",
                ],
            },
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
        drift_state = "warning" if bool(getattr(latest_accuracy, "drift_detected", False)) else ("ok" if latest_accuracy else "unknown")
        coverage_limits: list[str] = []
        training_samples = int(metadata.get("training_samples") or 0)
        if training_samples and training_samples < 52:
            coverage_limits.append("Trainingsfenster ist noch relativ kurz.")
        if latest_accuracy and (latest_accuracy.samples or 0) < 14:
            coverage_limits.append("Forecast-Accuracy basiert auf kleinem Monitoring-Fenster.")
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
            "training_window": {
                "start": training_window[0].isoformat() if training_window and training_window[0] else None,
                "end": training_window[1].isoformat() if training_window and training_window[1] else None,
                "points": int(training_window[2] or 0) if training_window else 0,
            },
            "drift_state": drift_state,
            "coverage_limits": coverage_limits,
            "latest_accuracy": {
                "computed_at": latest_accuracy.computed_at.isoformat() if latest_accuracy and latest_accuracy.computed_at else None,
                "samples": latest_accuracy.samples if latest_accuracy else None,
                "mape": latest_accuracy.mape if latest_accuracy else None,
                "rmse": latest_accuracy.rmse if latest_accuracy else None,
                "correlation": latest_accuracy.correlation if latest_accuracy else None,
            },
            "latest_forecast_created_at": latest_forecast.created_at.isoformat() if latest_forecast and latest_forecast.created_at else None,
        }

    def get_truth_coverage(self, *, brand: str = "gelo") -> dict[str, Any]:
        rows = (
            self.db.query(MediaOutcomeRecord)
            .filter(func.lower(MediaOutcomeRecord.brand) == str(brand).lower())
            .order_by(MediaOutcomeRecord.week_start.asc())
            .all()
        )
        if not rows:
            return {
                "coverage_weeks": 0,
                "latest_week": None,
                "regions_covered": 0,
                "products_covered": 0,
                "outcome_fields_present": [],
                "trust_readiness": "noch_nicht_angeschlossen",
                "source_labels": [],
            }

        weeks = sorted({row.week_start.date().isoformat() for row in rows if row.week_start})
        regions = {row.region_code for row in rows if row.region_code}
        products = {row.product for row in rows if row.product}
        fields_present = [
            label
            for field_name, label in METRIC_FIELD_LABELS.items()
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

        return {
            "coverage_weeks": coverage_weeks,
            "latest_week": weeks[-1] if weeks else None,
            "regions_covered": len(regions),
            "products_covered": len(products),
            "outcome_fields_present": fields_present,
            "trust_readiness": readiness,
            "source_labels": sorted({row.source_label for row in rows if row.source_label}),
        }

    def import_outcomes(
        self,
        *,
        source_label: str,
        records: list[dict[str, Any]] | None = None,
        csv_payload: str | None = None,
        brand: str = "gelo",
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        parsed = list(records or [])
        if csv_payload:
            parsed.extend(self._parse_csv_payload(csv_payload, brand=brand, source_label=source_label))
        if not parsed:
            return {"imported": 0, "batch_id": None, "message": "Keine Outcome-Daten übergeben."}

        batch_id = uuid.uuid4().hex[:12]
        imported = 0
        brand_value = str(brand or "gelo").strip().lower()

        for row in parsed:
            week_start = self._coerce_week_start(row.get("week_start"))
            if week_start is None:
                continue
            product = str(row.get("product") or "").strip()
            region_code = str(row.get("region_code") or "").strip().upper()
            if not product or not region_code:
                continue

            existing = (
                self.db.query(MediaOutcomeRecord)
                .filter(
                    MediaOutcomeRecord.week_start == week_start,
                    func.lower(MediaOutcomeRecord.brand) == brand_value,
                    MediaOutcomeRecord.product == product,
                    MediaOutcomeRecord.region_code == region_code,
                    MediaOutcomeRecord.source_label == source_label,
                )
                .first()
            )
            target = existing
            if target is None:
                target = MediaOutcomeRecord(
                    week_start=week_start,
                    brand=brand_value,
                    product=product,
                    region_code=region_code,
                    source_label=source_label,
                )
                self.db.add(target)

            if existing and not replace_existing:
                continue

            target.media_spend_eur = self._float_or_none(row.get("media_spend_eur"))
            target.impressions = self._float_or_none(row.get("impressions"))
            target.clicks = self._float_or_none(row.get("clicks"))
            target.qualified_visits = self._float_or_none(row.get("qualified_visits"))
            target.search_lift_index = self._float_or_none(row.get("search_lift_index"))
            target.sales_units = self._float_or_none(row.get("sales_units"))
            target.order_count = self._float_or_none(row.get("order_count"))
            target.revenue_eur = self._float_or_none(row.get("revenue_eur"))
            target.import_batch_id = batch_id
            target.extra_data = row.get("extra_data") or {}
            target.updated_at = datetime.utcnow()
            imported += 1

        self.db.commit()
        return {
            "imported": imported,
            "batch_id": batch_id,
            "coverage": self.get_truth_coverage(brand=brand_value),
        }

    def _campaign_cards(self, *, brand: str = "gelo", limit: int = 120) -> list[dict[str, Any]]:
        opportunities = self.engine.get_opportunities(
            brand_filter=brand,
            limit=limit,
            normalize_status=True,
        )
        cards = [to_card_response(opp, include_preview=True) for opp in opportunities]
        cards.sort(
            key=lambda item: (
                float(item.get("urgency_score") or 0.0),
                float(item.get("confidence") or 0.0),
            ),
            reverse=True,
        )
        return cards

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
    ) -> list[str]:
        reasons: list[str] = []
        if top_regions:
            reasons.append(
                f"{top_regions[0].get('name')} führt den regionalen Signal-Stack mit {round(float(top_regions[0].get('peix_score') or top_regions[0].get('impact_probability') or 0))}/100 an."
            )
        if top_card and top_card.get("decision_brief", {}).get("summary_sentence"):
            reasons.append(str(top_card["decision_brief"]["summary_sentence"]))
        top_drivers = (cockpit.get("peix_epi_score") or {}).get("top_drivers") or []
        if top_drivers:
            driver_labels = ", ".join(driver.get("label") for driver in top_drivers[:2] if driver.get("label"))
            reasons.append(f"Treiber dieser Woche: {driver_labels}.")
        while len(reasons) < 3:
            reasons.append("AMELAG, SurvStat und Forecast werden gemeinsam für die Wochenentscheidung gewichtet.")
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
    ) -> str:
        trend = str(region.get("trend") or "stabil")
        name = str(region.get("name") or "Die Region")
        score = float(region.get("peix_score") or region.get("impact_probability") or 0.0)
        if trend == "fallend" and score >= 60:
            return (
                f"{name} fällt kurzfristig, bleibt aber wegen hohem Ausgangsniveau und {forecast_direction}er Modellspur priorisiert."
            )
        if suggestion.get("reason"):
            return str(suggestion["reason"])
        return f"{name} wird aus AMELAG, SurvStat, Forecast und Kontextsignalen priorisiert."

    def _campaign_state_counts(self, cards: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for card in cards:
            counts[str(card.get("lifecycle_state") or "PREPARE")] += 1
        return dict(sorted(counts.items()))

    def _known_limits(self, cockpit: dict[str, Any], virus_typ: str) -> list[str]:
        limits: list[str] = []
        truth = self.get_truth_coverage()
        if truth.get("coverage_weeks", 0) < 26:
            limits.append("Kundennahe Truth-Daten decken noch keine 26 Wochen ab.")
        if not (cockpit.get("backtest_summary", {}).get("latest_market") or {}).get("quality_gate", {}).get("overall_passed"):
            limits.append("Markt-Validierung steht aktuell auf WATCH.")
        series_points = (
            self.db.query(func.count(WastewaterAggregated.id))
            .filter(WastewaterAggregated.virus_typ == virus_typ)
            .scalar()
        ) or 0
        if series_points < 120:
            limits.append("Die virale Kernreihe ist noch relativ kurz für robuste Saisonabdeckung.")
        return limits

    def _read_model_metadata(self, virus_typ: str) -> dict[str, Any]:
        slug = _virus_slug(virus_typ)
        metadata_path = Path(_ML_MODELS_DIR) / slug / "metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _parse_csv_payload(
        self,
        csv_payload: str,
        *,
        brand: str,
        source_label: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(csv_payload))
        for raw in reader:
            row = {key: value for key, value in raw.items()}
            row.setdefault("brand", brand)
            row.setdefault("source_label", source_label)
            rows.append(row)
        return rows

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
