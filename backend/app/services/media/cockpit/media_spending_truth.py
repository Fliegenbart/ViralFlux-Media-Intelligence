"""MediaSpendingTruth v1 decision layer.

Forecasts are useful only after they survive evidence, data-quality and business
constraints. This module translates validated regional forecasts into auditable
media planning actions without executing real budget changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from typing import Any, Iterable, Mapping

from app.services.media.cockpit.budget_allocator import BudgetAllocatorConfig, allocate_budget_deltas
from app.services.media.cockpit.spending_decision_backtest import evaluate_spending_decision_backtest_for_scope

SCHEMA_VERSION = "media_spending_truth_v1"
MIN_EVALUABLE_PANEL_WEEKS = 12

HARD_FORECAST_BLOCKERS = {
    "artifact_quality_gate_not_passed",
    "missing_panel",
    "missing_native_panel_evaluation",
    "no_native_panel_evaluation",
    "coverage_blocker",
    "coverage_blockers_present",
    "regional_coverage_incomplete",
    "live_data_quality_blocker",
}
PERSISTENCE_BLOCKERS = {
    "hit_rate_not_better_than_persistence",
    "model_not_better_than_persistence",
    "does_not_beat_persistence_pr_auc",
    "precision_below_persistence",
    "persistence_baseline_not_beaten",
}
CALIBRATION_WARNING_BLOCKERS = {"ece_fail", "ece_too_high", "calibration_warning", "brier_too_high"}

BUNDESLAND_NAMES: dict[str, str] = {
    "SH": "Schleswig-Holstein",
    "HH": "Hamburg",
    "NI": "Niedersachsen",
    "HB": "Bremen",
    "NW": "Nordrhein-Westfalen",
    "HE": "Hessen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "MV": "Mecklenburg-Vorpommern",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "TH": "Thüringen",
}


@dataclass(frozen=True)
class MediaSpendingTruthPolicy:
    max_weekly_shift_pct: float = 15.0
    uncertainty_shift_cap_pct: float = 5.0
    planner_assist_max_delta_pct: float = 5.0
    preposition_max_delta_pct: float = 8.0
    min_confidence_for_approval: float = 0.65
    min_confidence_for_preposition: float = 0.55
    requires_forecast_gate_pass: bool = True
    requires_budget_regret_pass: bool = True


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def _normalise_decision_date(value: date | datetime | str | None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            pass
    return datetime.utcnow().date()


def _scoreboard_card(
    truth_scoreboard: Mapping[str, Any] | None,
    *,
    virus_typ: str,
    horizon_days: int,
) -> dict[str, Any]:
    by_virus = (truth_scoreboard or {}).get("combined_by_virus") or {}
    card = ((by_virus.get(virus_typ) or {}).get(f"h{int(horizon_days)}") or {})
    return dict(card) if isinstance(card, Mapping) else {}


def _evaluable_weeks(card: Mapping[str, Any]) -> int:
    return int(_safe_float(card.get("evaluable_weeks") or card.get("evaluable_panel_weeks"), 0.0))


def _quality_gate_passed(card: Mapping[str, Any]) -> bool:
    quality_gate = card.get("quality_gate") if isinstance(card.get("quality_gate"), Mapping) else {}
    if "overall_passed" in quality_gate:
        return bool(quality_gate.get("overall_passed"))
    return str(card.get("readiness") or "").lower() == "go"


def _base_budget_for_prediction(prediction: Mapping[str, Any], base_budget_by_region: Mapping[str, float] | None) -> float:
    code = str(prediction.get("bundesland") or prediction.get("region_code") or "")
    if base_budget_by_region and code in base_budget_by_region:
        return max(_safe_float(base_budget_by_region.get(code)), 0.0)
    population_m = _safe_float(prediction.get("state_population_millions"), 1.0)
    return max(population_m, 0.1) * 1000.0


def _prediction_confidence(prediction: Mapping[str, Any]) -> float:
    decision = prediction.get("decision") if isinstance(prediction.get("decision"), Mapping) else {}
    return _clamp(
        _safe_float(
            decision.get("forecast_confidence")
            or decision.get("decision_score")
            or prediction.get("event_probability"),
            0.5,
        ),
        0.0,
        1.0,
    )


def _data_quality_label(predictions: Iterable[Mapping[str, Any]]) -> str:
    rows = list(predictions)
    if not rows:
        return "unknown"
    stale = sum(1 for row in rows if not row.get("regional_data_fresh", True))
    blockers = sum(1 for row in rows if row.get("coverage_blockers"))
    if stale or blockers:
        return "limited" if stale + blockers < len(rows) else "poor"
    return "good"


def _region_reason_codes(
    *,
    prediction: Mapping[str, Any],
    confidence: float,
    p_surge: float,
    growth_score: float,
    blockers: list[str],
    insufficient_evidence: bool,
    manual: bool,
) -> list[str]:
    features = prediction.get("viral_pressure_features") if isinstance(prediction.get("viral_pressure_features"), Mapping) else {}
    reasons: list[str] = []
    if p_surge >= 0.65:
        _append_unique(reasons, "high_surge_probability")
    if _safe_float(features.get("wastewater_case_divergence")) > 0.15:
        _append_unique(reasons, "positive_wastewater_case_divergence")
    if _safe_float(features.get("spatial_import_pressure")) > 0.25:
        _append_unique(reasons, "high_import_pressure")
    if p_surge <= 0.35 and growth_score <= 0.02:
        _append_unique(reasons, "low_activity_low_growth")
    if insufficient_evidence:
        _append_unique(reasons, "insufficient_evaluable_weeks")
    if any(blocker in CALIBRATION_WARNING_BLOCKERS for blocker in blockers):
        _append_unique(reasons, "calibration_warning")
    if any(blocker in PERSISTENCE_BLOCKERS for blocker in blockers):
        _append_unique(reasons, "model_not_better_than_persistence")
    if not prediction.get("regional_data_fresh", True):
        _append_unique(reasons, "stale_data")
    if confidence < 0.55:
        _append_unique(reasons, "low_confidence")
    if manual:
        _append_unique(reasons, "manual_approval_required")
    return reasons


def _empty_payload(
    *,
    virus_typ: str,
    horizon_days: int,
    decision_day: date,
    policy: MediaSpendingTruthPolicy,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_date": decision_day.isoformat(),
        "valid_until": (decision_day + timedelta(days=int(horizon_days))).isoformat(),
        "pathogen_scope": virus_typ,
        "horizon_days": int(horizon_days),
        "global_status": "blocked",
        "budget_permission": "blocked",
        "decision_policy": policy.__dict__,
        "data_quality": "unknown",
        "forecast_evidence": "missing",
        "decision_backtest": {"decision_backtest_passed": False},
        "regions": [],
        "limitations": [reason, "not_for_automatic_budget_execution"],
    }


def build_media_spending_truth(
    *,
    virus_typ: str,
    horizon_days: int,
    predictions: list[dict[str, Any]],
    truth_scoreboard: Mapping[str, Any] | None = None,
    decision_backtest: Mapping[str, Any] | None = None,
    base_budget_by_region: Mapping[str, float] | None = None,
    decision_date: date | datetime | str | None = None,
    valid_until: date | datetime | str | None = None,
    policy: MediaSpendingTruthPolicy | None = None,
) -> dict[str, Any]:
    """Translate regional forecasts into capped media spending decisions."""

    effective_policy = policy or MediaSpendingTruthPolicy()
    decision_day = _normalise_decision_date(decision_date)
    valid_day = _normalise_decision_date(valid_until) if valid_until else decision_day + timedelta(days=int(horizon_days))
    rows = [dict(item) for item in predictions or []]
    if not rows:
        return _empty_payload(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            decision_day=decision_day,
            policy=effective_policy,
            reason="no_regional_predictions_available",
        )

    card = _scoreboard_card(truth_scoreboard, virus_typ=virus_typ, horizon_days=horizon_days)
    readiness = str(card.get("readiness") or "unknown").lower()
    blockers = [str(item) for item in (card.get("blockers") or [])]
    warnings = [str(item) for item in (card.get("warnings") or [])]
    evaluable_weeks = _evaluable_weeks(card)
    all_gate_notes = blockers + warnings
    hard_blockers = [item for item in blockers if item in HARD_FORECAST_BLOCKERS]
    model_worse_than_persistence = any(item in PERSISTENCE_BLOCKERS for item in blockers)
    insufficient_evidence = (
        evaluable_weeks < MIN_EVALUABLE_PANEL_WEEKS
        or "too_few_evaluable_weeks" in blockers
        or readiness in {"candidate", "watch", "watch_strong", "unknown"}
    )
    forecast_gate_passed = _quality_gate_passed(card) and not hard_blockers and not model_worse_than_persistence and not insufficient_evidence
    decision_backtest_payload = dict(decision_backtest or {})
    decision_backtest_passed = bool(decision_backtest_payload.get("decision_backtest_passed"))
    full_spendable = forecast_gate_passed and decision_backtest_passed

    preliminary_regions: list[dict[str, Any]] = []
    planner_candidates = 0

    for prediction in rows:
        code = str(prediction.get("bundesland") or prediction.get("region_code") or "")
        name = str(prediction.get("bundesland_name") or BUNDESLAND_NAMES.get(code, code))
        features = prediction.get("viral_pressure_features") if isinstance(prediction.get("viral_pressure_features"), Mapping) else {}
        p_surge = _clamp(_safe_float(prediction.get("event_probability")), 0.0, 1.0)
        growth_score = _clamp(max(_safe_float(prediction.get("change_pct")), 0.0) / 50.0, 0.0, 1.0)
        confidence = _prediction_confidence(prediction)
        opportunity = _clamp(
            _safe_float(features.get("budget_opportunity_score"), p_surge * max(growth_score, 0.05) * confidence),
            0.0,
            1.0,
        )
        saturation_score = _clamp(_safe_float(features.get("recent_saturation_score")), 0.0, 1.0)
        regional_blockers = [str(item) for item in (prediction.get("coverage_blockers") or [])]
        fresh = bool(prediction.get("regional_data_fresh", True))
        limiting_factors = list(dict.fromkeys([*hard_blockers, *regional_blockers]))
        manual = False
        max_delta = 0.0
        media_truth = "watch_only"
        action = "maintain"

        promising = p_surge >= 0.55 and growth_score > 0.0 and confidence >= effective_policy.min_confidence_for_preposition
        plateau = p_surge >= 0.55 and _safe_float(prediction.get("change_pct")) <= 2.0 and saturation_score >= 0.55

        if hard_blockers or not fresh:
            media_truth = "blocked"
            action = "none"
            max_delta = 0.0
        elif model_worse_than_persistence:
            media_truth = "watch_only"
            action = "maintain"
            max_delta = 0.0
        elif not full_spendable:
            if promising:
                media_truth = "preposition_approved"
                action = "small_increase"
                manual = True
                max_delta = effective_policy.planner_assist_max_delta_pct
                planner_candidates += 1
            else:
                media_truth = "watch_only"
                action = "maintain"
                max_delta = 0.0
        elif confidence < 0.45:
            media_truth = "watch_only"
            action = "maintain"
            max_delta = 0.0
            _append_unique(limiting_factors, "low_confidence")
        elif plateau:
            media_truth = "cap_or_reduce"
            action = "cap_or_reduce"
            max_delta = effective_policy.uncertainty_shift_cap_pct
        elif p_surge >= 0.65 and growth_score >= 0.15 and confidence >= effective_policy.min_confidence_for_approval and saturation_score < 0.75:
            media_truth = "increase_approved"
            action = "increase"
            max_delta = effective_policy.max_weekly_shift_pct
        elif promising:
            media_truth = "preposition_approved"
            action = "small_increase"
            max_delta = effective_policy.preposition_max_delta_pct
        elif p_surge <= 0.35 and growth_score <= 0.02 and confidence >= effective_policy.min_confidence_for_approval:
            media_truth = "decrease_approved"
            action = "decrease"
            max_delta = effective_policy.max_weekly_shift_pct
        else:
            media_truth = "maintain"
            action = "maintain"
            max_delta = 0.0

        if insufficient_evidence and not full_spendable:
            _append_unique(limiting_factors, "insufficient_evaluable_weeks")
        if not decision_backtest_passed:
            _append_unique(limiting_factors, "decision_backtest_not_passed")
        if model_worse_than_persistence:
            _append_unique(limiting_factors, "model_not_better_than_persistence")
        if not fresh:
            _append_unique(limiting_factors, "stale_data")

        reason_codes = _region_reason_codes(
            prediction=prediction,
            confidence=confidence,
            p_surge=p_surge,
            growth_score=growth_score,
            blockers=all_gate_notes,
            insufficient_evidence=insufficient_evidence and not full_spendable,
            manual=manual,
        )
        if plateau:
            _append_unique(reason_codes, "high_current_activity_but_plateauing")

        preliminary_regions.append(
            {
                "region_code": code,
                "region_name": name,
                "pathogen_scope": virus_typ,
                "horizon_days": int(horizon_days),
                "media_spending_truth": media_truth,
                "budget_permission": "manual_approval_required" if manual else "approved_with_cap" if full_spendable and max_delta > 0 else "blocked",
                "recommended_action": action,
                "recommended_delta_pct": 0.0,
                "max_delta_pct": round(float(max_delta), 2),
                "surge_probability_7d": round(p_surge, 4),
                "expected_growth_score": round(growth_score, 4),
                "confidence": round(confidence, 4),
                "budget_opportunity_score": round(opportunity, 4),
                "forecast_class": prediction.get("forecast_class") or prediction.get("cluster_id") or None,
                "reason_codes": reason_codes,
                "limiting_factors": limiting_factors,
                "manual_approval_required": bool(manual),
                "research_only": False,
                "planner_assist": bool(manual),
                "base_budget_eur": round(_base_budget_for_prediction(prediction, base_budget_by_region), 2),
                "uncertainty_capped": bool(manual or (not full_spendable and max_delta > 0)),
                "limitations": ["recommendation_valid_only_for_region_level_media_planning", "not_for_individual_targeting"],
            }
        )

    if hard_blockers or model_worse_than_persistence:
        global_status = "blocked"
    elif full_spendable:
        global_status = "spendable"
    elif planner_candidates > 0:
        global_status = "planner_assist"
    else:
        global_status = "watch_only"

    budget_permission = {
        "blocked": "blocked",
        "watch_only": "blocked",
        "planner_assist": "manual_approval_required",
        "spendable": "approved_with_cap",
    }[global_status]

    allocation_input = [
        region
        for region in preliminary_regions
        if _safe_float(region.get("max_delta_pct")) > 0.0
    ]
    allocation_rows: dict[str, dict[str, Any]] = {}
    if allocation_input:
        allocation = allocate_budget_deltas(
            allocation_input,
            config=BudgetAllocatorConfig(
                max_weekly_shift_pct=effective_policy.max_weekly_shift_pct,
                uncertainty_shift_cap_pct=effective_policy.uncertainty_shift_cap_pct,
            ),
        )
        allocation_rows = {str(row.get("region_code")): row for row in allocation.get("regions", [])}

    final_regions: list[dict[str, Any]] = []
    for region in preliminary_regions:
        allocated = allocation_rows.get(str(region.get("region_code")))
        final_region = dict(region)
        if allocated:
            final_region["recommended_delta_pct"] = round(_safe_float(allocated.get("recommended_delta_pct")), 2)
            final_region["before_budget_eur"] = allocated.get("before_budget_eur")
            final_region["after_budget_eur"] = allocated.get("after_budget_eur")
            final_region["allocated_shift_eur"] = allocated.get("allocated_shift_eur")
        else:
            final_region["before_budget_eur"] = final_region.get("base_budget_eur")
            final_region["after_budget_eur"] = final_region.get("base_budget_eur")
            final_region["allocated_shift_eur"] = 0.0
        final_regions.append(final_region)

    return {
        "schema_version": SCHEMA_VERSION,
        "decision_date": decision_day.isoformat(),
        "valid_until": valid_day.isoformat(),
        "pathogen_scope": virus_typ,
        "horizon_days": int(horizon_days),
        "global_status": global_status,
        "budget_permission": budget_permission,
        "decision_policy": effective_policy.__dict__,
        "data_quality": _data_quality_label(rows),
        "forecast_evidence": "validated" if forecast_gate_passed else "limited" if not hard_blockers else "blocked",
        "decision_backtest": decision_backtest_payload,
        "forecast_gate": {
            "readiness": readiness,
            "passed": bool(forecast_gate_passed),
            "evaluable_panel_weeks": evaluable_weeks,
            "blockers": blockers,
            "warnings": warnings,
        },
        "regions": sorted(final_regions, key=lambda item: item.get("budget_opportunity_score", 0.0), reverse=True),
        "limitations": [
            "not_for_automatic_budget_execution",
            "recommendations_are_region_level_only",
        ],
    }


def build_media_spending_truth_from_forecast(
    db: Any,
    *,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    client: str = "GELO",
    brand: str | None = None,
    decision_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Fetch existing forecast/backtest inputs and build MediaSpendingTruth."""

    from app.services.media.cockpit.truth_scoreboard import build_truth_scoreboard
    from app.services.media.media_plan_service import aggregate_by_bundesland, current_iso_week, current_plan_rows
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    forecast = service.predict_all_regions(
        virus_typ=virus_typ,
        brand=brand or "default",
        horizon_days=int(horizon_days),
    )
    predictions = list(forecast.get("predictions") or [])
    scoreboard = build_truth_scoreboard(virus_types=[virus_typ], horizons=[int(horizon_days)])
    decision_backtest = evaluate_spending_decision_backtest_for_scope(
        virus_typ=virus_typ,
        horizon_days=int(horizon_days),
    )

    decision_day = _normalise_decision_date(decision_date)
    iso_year, iso_week = current_iso_week(decision_day)
    plan_rows = current_plan_rows(db, client=client, iso_year=iso_year, iso_week=iso_week)
    if plan_rows:
        base_budget = aggregate_by_bundesland(plan_rows)
    else:
        base_budget = {
            str(row.get("bundesland")): max(_safe_float(row.get("state_population_millions"), 1.0), 0.1) * 1000.0
            for row in predictions
            if row.get("bundesland")
        }

    return build_media_spending_truth(
        virus_typ=virus_typ,
        horizon_days=int(horizon_days),
        predictions=predictions,
        truth_scoreboard=scoreboard,
        decision_backtest=decision_backtest,
        base_budget_by_region=base_budget,
        decision_date=decision_day,
    )
