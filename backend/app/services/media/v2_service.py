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
        queue = self._build_campaign_queue(self._campaign_cards(brand=brand, limit=80), visible_limit=8)
        campaign_cards = queue["visible_cards"]
        primary_cards = queue["primary_cards"]
        top_card = self._decision_focus_card(primary_cards)
        top_regions = cockpit.get("map", {}).get("top_regions", [])[:3]
        market = cockpit.get("backtest_summary", {}).get("latest_market") or {}
        signal_summary = self.get_signal_stack(virus_typ=virus_typ).get("summary") or {}

        freshness_state = self._decision_freshness_state(cockpit.get("source_status", {}))
        has_truth = truth_coverage.get("coverage_weeks", 0) >= 26
        market_passed = bool((market.get("quality_gate") or {}).get("overall_passed"))
        publishable_cards = [card for card in primary_cards if card.get("is_publishable")]
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

        why_now = self._build_why_now(
            top_card=top_card,
            top_regions=top_regions,
            cockpit=cockpit,
            decision_state=decision_state,
            signal_summary=signal_summary,
        )
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
                        "signal_score": item.get("peix_score") or item.get("impact_probability"),
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
                "truth_state": truth_coverage.get("trust_readiness"),
                "decision_mode": signal_summary.get("decision_mode"),
                "decision_mode_label": signal_summary.get("decision_mode_label"),
                "decision_mode_reason": signal_summary.get("decision_mode_reason"),
                "signal_stack_summary": signal_summary,
            },
            "top_recommendations": campaign_cards[:3],
            "campaign_summary": queue["summary"],
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
                float(item.get("peix_score") or item.get("impact_probability") or 0.0),
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
        truth_coverage = self.get_truth_coverage(brand=brand)
        latest_customer = backtest_summary.get("latest_customer")
        truth_validation = latest_customer if truth_coverage.get("coverage_weeks", 0) > 0 else None
        truth_validation_legacy = latest_customer if truth_validation is None and latest_customer else None
        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "generated_at": datetime.utcnow().isoformat(),
            "proxy_validation": backtest_summary.get("latest_market"),
            "truth_validation": truth_validation,
            "truth_validation_legacy": truth_validation_legacy,
            "recent_runs": backtest_summary.get("recent_runs") or [],
            "data_freshness": cockpit.get("data_freshness") or {},
            "source_status": cockpit.get("source_status") or {},
            "signal_stack": self.get_signal_stack(virus_typ=virus_typ),
            "model_lineage": self.get_model_lineage(virus_typ=virus_typ),
            "truth_coverage": truth_coverage,
            "known_limits": self._known_limits(
                cockpit,
                virus_typ,
                truth_coverage=truth_coverage,
                truth_validation_legacy=truth_validation_legacy,
            ),
        }

    def get_signal_stack(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        cockpit = self.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source="RKI_ARE")
        data_freshness = cockpit.get("data_freshness") or {}
        source_status_items = {
            item.get("source_key"): item
            for item in (cockpit.get("source_status") or {}).get("items", [])
        }
        peix = cockpit.get("peix_epi_score") or PeixEpiScoreService(self.db).build(virus_typ=virus_typ)
        signal_groups = self._signal_group_summary(peix)

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
            key=self._campaign_sort_key,
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
        decision_state: str,
        signal_summary: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        if decision_state != "GO":
            reasons.append("Die epidemiologischen Signale sind relevant, aber die Freigabegates stehen noch auf WATCH.")
        if top_regions:
            reasons.append(
                f"{top_regions[0].get('name')} führt den regionalen Signal-Stack mit {round(float(top_regions[0].get('peix_score') or top_regions[0].get('impact_probability') or 0))}/100 an."
            )
        if top_card:
            if decision_state == "GO" and top_card.get("decision_brief", {}).get("summary_sentence"):
                reasons.append(str(top_card["decision_brief"]["summary_sentence"]))
            else:
                title = top_card.get("display_title") or top_card.get("recommended_product") or "Das stärkste Review-Paket"
                reasons.append(f"{title} ist das nächste priorisierte Paket für Review und Freigabe.")
        if signal_summary.get("decision_mode_reason"):
            reasons.append(str(signal_summary["decision_mode_reason"]))
        else:
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
                f"{name} beschleunigt aktuell nicht, bleibt aber wegen hohem Ausgangsniveau und hoher Aktivierbarkeit "
                "für Review und Vorbereitung priorisiert."
            )
        if momentum_score >= 60 and forecast_direction == "aufwärts":
            return (
                f"{name} zeigt ein frühes Wellenfenster: steigende Dynamik, aufwärts gerichteter Forecast und hohe Aktivierbarkeit."
            )
        if trend == "fallend" and actionability_score >= 65:
            return (
                f"{name} fällt kurzfristig, bleibt aber für defensive Planung relevant: Niveau und Umsetzbarkeit sind noch hoch."
            )
        if suggestion.get("reason"):
            return str(suggestion["reason"])
        return f"{name} wird aus epidemiologischer Lage, Forecast und Umsetzungschance priorisiert."

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
            float(item.get("urgency_score") or 0.0),
            float(item.get("confidence") or 0.0),
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
            return "Diese Woche freigeben: die stärksten regionalen Pakete in die Aktivierung ziehen."

        if decision_mode == "supply_window":
            if primary_region and product:
                return f"Diese Woche vorbereiten: {product} in {primary_region} als Versorgungschance absichern, aber noch keinen nationalen Shift freigeben."
            return "Diese Woche vorbereiten: Versorgungssignale beobachten und nur reviewfähige Pakete weiterziehen."
        if decision_mode == "mixed":
            if primary_region and product:
                return f"Diese Woche vorbereiten: {product} in {primary_region} priorisieren, weil Epi-Signal und Kontext gemeinsam tragen, aber noch keinen nationalen Shift freigeben."
            return "Diese Woche vorbereiten: Epi-Signal und Kontext beobachten und keine harte Aktivierung freigeben."
        if primary_region and product:
            return f"Diese Woche vorbereiten: {product} in {primary_region} priorisieren, aber noch keinen nationalen Shift freigeben."
        if primary_region:
            return f"Diese Woche vorbereiten: {primary_region} priorisieren und nur reviewfähige Pakete weiterziehen."
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
            limits.append("Kundennahe Truth-Daten decken noch keine 26 Wochen ab.")
        if truth_validation_legacy and truth.get("coverage_weeks", 0) == 0:
            limits.append("Der sichtbare Kunden-Backtest ist nur ein explorativer Legacy-Run und kein aktiver Truth-Layer.")
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
                "forecast_model": {"label": "Forecast", "contribution": forecast_contribution},
                "supply_window": {"label": "Versorgung", "contribution": supply_contribution},
                "context_window": {"label": "Wetter & Baseline", "contribution": context_contribution},
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
                "reason": "Epi-Kern, Forecast und Kontext zeigen gleichzeitig nach oben. Die Entscheidung bleibt deshalb bewusst defensiv.",
            }
        return {
            "key": "epidemic_wave",
            "label": "Epi-Welle",
            "reason": "AMELAG, SurvStat und Forecast tragen die Entscheidung. Versorgung bleibt Zusatzsignal, nicht Hauptbeweis.",
        }

    def _severity_score(self, region: dict[str, Any]) -> int:
        impact = float(region.get("impact_probability") or region.get("peix_score") or 0.0)
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
        trace = ["AMELAG", "SurvStat", "Forecast", "ARE"]
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
