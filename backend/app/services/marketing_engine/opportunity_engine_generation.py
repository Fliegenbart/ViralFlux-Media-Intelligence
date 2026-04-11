from __future__ import annotations

from app.core.time import utc_now

from typing import Any
import logging

from sqlalchemy import func

from app.services.media.playbook_engine import PLAYBOOK_CATALOG
from app.services.media.semantic_contracts import normalize_confidence_pct
from app.services.ml.forecast_contracts import DEFAULT_DECISION_HORIZON_DAYS
from app.services.ml.forecast_decision_service import ForecastDecisionService

logger = logging.getLogger(__name__)

SYSTEM_VERSION = "ViralFlux-Media-v3.0"

_CONDITION_CLUSTER_MAP = {
    "bronchitis_husten": "RESPIRATORY",
    "sinusitis_nebenhoehlen": "RESPIRATORY",
    "erkaltung_akut": "RESPIRATORY",
    "halsschmerz_heiserkeit": "RESPIRATORY",
    "rhinitis_trockene_nase": "RESPIRATORY",
    "immun_support": "RESPIRATORY",
}

_KREIS_BL_MAP = {
    "SK Hamburg": "Hamburg",
    "SK München": "Bayern",
    "SK Berlin": "Berlin",
    "SK Dresden": "Sachsen",
    "SK Leipzig": "Sachsen",
    "SK Köln": "Nordrhein-Westfalen",
    "SK Frankfurt am Main": "Hessen",
    "SK Stuttgart": "Baden-Württemberg",
    "SK Düsseldorf": "Nordrhein-Westfalen",
    "SK Hannover": "Niedersachsen",
    "SK Bremen": "Bremen",
    "SK Nürnberg": "Bayern",
    "SK Dortmund": "Nordrhein-Westfalen",
    "SK Essen": "Nordrhein-Westfalen",
    "SK Duisburg": "Nordrhein-Westfalen",
    "SK Chemnitz": "Sachsen",
    "SK Erfurt": "Thüringen",
    "SK Magdeburg": "Sachsen-Anhalt",
    "SK Rostock": "Mecklenburg-Vorpommern",
    "SK Potsdam": "Brandenburg",
    "SK Kiel": "Schleswig-Holstein",
    "SK Mainz": "Rheinland-Pfalz",
    "SK Saarbrücken": "Saarland",
    "SK Freiburg i.Breisgau": "Baden-Württemberg",
}


def _secondary_modifier_from_opportunities(
    engine,
    *,
    opportunities: list[dict[str, Any]],
    region_code: str,
) -> tuple[float, list[dict[str, Any]]]:
    relevant: list[dict[str, Any]] = []
    for opp in opportunities:
        region_codes = engine._extract_region_codes_from_opportunity(opp)
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
    engine,
    *,
    opportunities: list[dict[str, Any]],
    brand: str,
    virus_typ: str,
    region_scope: list[str] | None,
    max_cards: int,
) -> list[dict[str, Any]]:
    service = ForecastDecisionService(engine.db)
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
        engine._normalize_region_token(item)
        for item in (region_scope or [])
        if item
    ]
    region_codes = [item for item in normalized_scope if item] or ["Gesamt"]
    playbook_key = engine._select_forecast_playbook_key(virus_typ)
    playbook_cfg = PLAYBOOK_CATALOG.get(playbook_key) or {}
    event_probability = (
        float(event_forecast["event_probability"])
        if event_forecast.get("event_probability") is not None
        else None
    )
    event_signal_score = float(
        event_forecast.get("event_signal_score")
        or event_forecast.get("heuristic_event_score")
        or event_probability
        or 0.0
    )
    calibration_passed = bool(event_forecast.get("calibration_passed"))
    forecast_readiness = str(forecast_quality.get("forecast_readiness") or "WATCH")
    primary_threshold = event_forecast.get("threshold_value")
    baseline_value = event_forecast.get("baseline_value")

    candidates: list[dict[str, Any]] = []
    for region_code in region_codes[: max(1, max_cards)]:
        modifier, exploratory_signals = engine._secondary_modifier_from_opportunities(
            opportunities=opportunities,
            region_code=region_code,
        )
        opportunity_assessment = service.build_opportunity_assessment(
            virus_typ=virus_typ,
            target_source="RKI_ARE",
            brand=brand,
            secondary_modifier=modifier,
        )
        decision_priority_index = float(opportunity_assessment.get("decision_priority_index") or 0.0)
        action_class = str(opportunity_assessment.get("action_class") or "watch_only")
        if action_class == "customer_lift_ready":
            budget_shift_pct = round(max(10.0, min(35.0, decision_priority_index * 0.35)), 1)
        else:
            budget_shift_pct = 0.0

        candidates.append(
            {
                "playbook_key": playbook_key,
                "region_code": region_code,
                "region_name": engine._region_label(region_code) if region_code != "Gesamt" else "Deutschland",
                "signal_score": round(event_signal_score * 100.0, 1),
                "trigger_strength": round(event_signal_score * 100.0, 2),
                "confidence": round(float(event_forecast.get("reliability_score") or event_signal_score) * 100.0, 2),
                "signal_confidence_pct": normalize_confidence_pct(event_forecast.get("reliability_score")),
                "priority_score": round(decision_priority_index, 2),
                "impact_probability": round(event_probability * 100.0, 1) if calibration_passed and event_probability is not None else None,
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
                        (
                            f"7-Tage Event-Wahrscheinlichkeit für {virus_typ}: "
                            f"{round(event_probability * 100.0, 1)}% "
                            f"bei Baseline {baseline_value} und Schwelle {primary_threshold}."
                        )
                        if event_probability is not None
                        else (
                            f"7-Tage Event-Signal-Score für {virus_typ}: "
                            f"{round(event_signal_score * 100.0, 1)} "
                            f"bei Baseline {baseline_value} und Schwelle {primary_threshold}."
                        )
                    ),
                    "lead_time_days": (
                        (forecast_quality.get("timing_metrics") or {}).get("best_lag_days")
                        or DEFAULT_DECISION_HORIZON_DAYS
                    ),
                    "confidence": float(event_forecast.get("reliability_score") or event_signal_score),
                    "values": {
                        "event_probability_pct": (
                            round(event_probability * 100.0, 1)
                            if event_probability is not None
                            else None
                        ),
                        "event_signal_pct": round(event_signal_score * 100.0, 1),
                        "threshold_pct": event_forecast.get("threshold_pct"),
                        "baseline_value": baseline_value,
                        "threshold_value": primary_threshold,
                        "decision_priority_index": decision_priority_index,
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


def generate_opportunities(engine) -> dict[str, Any]:
    all_opportunities = []

    for detector in engine.detectors:
        try:
            raw_opps = detector.detect()
            logger.info(
                "%s: %s Opportunities erkannt",
                detector.OPPORTUNITY_TYPE,
                len(raw_opps),
            )
            for raw in raw_opps:
                raw["sales_pitch"] = engine.pitch_generator.generate(raw["type"], raw)
                raw["suggested_products"] = engine.product_matcher.match(raw["type"], raw)
                all_opportunities.append(raw)
        except Exception as exc:
            logger.error("Detector %s fehlgeschlagen: %s", detector.OPPORTUNITY_TYPE, exc)

    all_opportunities = engine._deduplicate_signals(all_opportunities)
    all_opportunities = engine._apply_supply_gap_priority_multipliers(all_opportunities)
    all_opportunities = engine._enrich_kreis_targeting(all_opportunities)

    all_opportunities.sort(key=lambda item: item.get("urgency_score", 0), reverse=True)

    saved = 0
    for opp in all_opportunities:
        if engine._save_opportunity(opp):
            saved += 1

    logger.info(
        "MarketingOpportunityEngine: %s erkannt, %s neu gespeichert",
        len(all_opportunities),
        saved,
    )

    clean_opps = [engine._clean_for_output(opp) for opp in all_opportunities]
    return {
        "meta": {
            "generated_at": utc_now().isoformat() + "Z",
            "system_version": SYSTEM_VERSION,
            "total_opportunities": len(clean_opps),
            "new_saved": saved,
        },
        "opportunities": clean_opps,
    }


def _deduplicate_signals(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []

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


def _apply_supply_gap_priority_multipliers(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    supply_gap_by_condition: dict[str, dict[str, Any]] = {}
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

    for opp in opportunities:
        if opp.get("type") == "MARKET_SUPPLY_GAP":
            continue

        condition = opp.get("_condition", "")
        supply_gap = supply_gap_by_condition.get(condition)
        if not supply_gap:
            continue

        multiplier = float(supply_gap.get("_priority_multiplier", 1.0))
        original_urgency = float(opp.get("urgency_score", 0))
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


def _kreis_bundesland(engine, kreis_name: str) -> str:
    kreis_map = getattr(engine, "_KREIS_BL_MAP", _KREIS_BL_MAP)
    return kreis_map.get(kreis_name, "")


def _enrich_kreis_targeting(
    engine,
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from app.models.database import SurvstatKreisData

    condition_cluster_map = getattr(engine, "_CONDITION_CLUSTER_MAP", _CONDITION_CLUSTER_MAP)

    needed_clusters = set()
    for opp in opportunities:
        condition = opp.get("_condition", "")
        cluster = condition_cluster_map.get(condition)
        if cluster:
            needed_clusters.add(cluster)

    if not needed_clusters:
        return opportunities

    now = utc_now()
    current_week = now.isocalendar()[1]
    current_year = now.year

    kreise_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for cluster in needed_clusters:
        rows = (
            engine.db.query(
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
            latest_year = (
                engine.db.query(func.max(SurvstatKreisData.year))
                .filter(SurvstatKreisData.disease_cluster == cluster)
                .scalar()
            )
            if latest_year and latest_year != current_year:
                latest_week = (
                    engine.db.query(func.max(SurvstatKreisData.week))
                    .filter(
                        SurvstatKreisData.disease_cluster == cluster,
                        SurvstatKreisData.year == latest_year,
                    )
                    .scalar()
                ) or 52
                rows = (
                    engine.db.query(
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
                    "kreis": row.kreis,
                    "bundesland": engine._kreis_bundesland(row.kreis),
                    "faelle_4w": int(row.total_faelle or 0),
                }
                for row in rows
            ]

    for opp in opportunities:
        condition = opp.get("_condition", "")
        cluster = condition_cluster_map.get(condition)
        top_kreise = kreise_by_cluster.get(cluster, []) if cluster else []

        if top_kreise:
            region = opp.get("region_target", {})
            region["top_kreise"] = [item["kreis"] for item in top_kreise]
            region["kreis_detail"] = top_kreise
            if not region.get("states"):
                unique_bl = list(
                    dict.fromkeys(
                        item["bundesland"] for item in top_kreise if item["bundesland"]
                    )
                )
                region["states"] = unique_bl
            opp["region_target"] = region

    return opportunities
