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
    min_eligible_regions: int = 2


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


def _live_data_quality_passed(predictions: Iterable[Mapping[str, Any]]) -> bool:
    rows = list(predictions)
    if not rows:
        return False
    return all(row.get("regional_data_fresh", True) and not row.get("coverage_blockers") for row in rows)


def _live_data_observed(predictions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(predictions)
    stale_regions = [
        str(row.get("bundesland") or row.get("region_code") or "")
        for row in rows
        if not row.get("regional_data_fresh", True)
    ]
    blocker_regions = [
        str(row.get("bundesland") or row.get("region_code") or "")
        for row in rows
        if row.get("coverage_blockers")
    ]
    return {
        "regions": len(rows),
        "stale_regions": sorted(region for region in stale_regions if region),
        "coverage_blocker_regions": sorted(region for region in blocker_regions if region),
    }



def _region_is_live_eligible(prediction: Mapping[str, Any]) -> bool:
    return bool(prediction.get("regional_data_fresh", True)) and not bool(prediction.get("coverage_blockers"))


def _decision_backtest_status(decision_backtest: Mapping[str, Any]) -> str:
    if bool(decision_backtest.get("decision_backtest_passed")):
        return "passed"

    verdict = str(decision_backtest.get("verdict") or "").lower()
    windows = int(
        _safe_float(
            decision_backtest.get("evaluable_panel_weeks")
            or decision_backtest.get("sample_size")
            or decision_backtest.get("sampleSize"),
            999.0,
        )
    )
    uplift = _safe_float(
        decision_backtest.get("upliftVsPersistence")
        or decision_backtest.get("uplift_vs_persistence")
        or decision_backtest.get("regret_reduction_vs_static")
        or decision_backtest.get("regret_reduction_vs_current_incidence"),
        0.0,
    )

    if verdict in {"not_enough_data", "insufficient_evidence"} or windows < MIN_EVALUABLE_PANEL_WEEKS:
        return "insufficient_evidence"
    if verdict in {"better_but_uncertain", "roughly_equal", "equal_to_persistence"} or uplift >= 0.0:
        return "warning"
    return "failed"


def _build_gate_evaluations(
    *,
    forecast_gate_passed: bool,
    live_data_gate_status: str,
    decision_backtest_status: str,
    business_constraints_passed: bool,
    insufficient_evidence: bool,
    model_worse_than_persistence: bool,
    readiness: str,
    blockers: list[str],
    warnings: list[str],
    evaluable_weeks: int,
    card: Mapping[str, Any],
    predictions: list[Mapping[str, Any]],
    decision_backtest: Mapping[str, Any],
    eligible_region_count: int,
    min_eligible_regions: int,
) -> list[dict[str, Any]]:
    if forecast_gate_passed:
        forecast_status = "passed"
    elif insufficient_evidence and not model_worse_than_persistence and not any(item in HARD_FORECAST_BLOCKERS for item in blockers):
        forecast_status = "insufficient_evidence"
    else:
        forecast_status = "failed"

    backtest_threshold = _safe_float(decision_backtest.get("min_regret_reduction"), 0.03)
    backtest_observed = {
        "decision_backtest_passed": bool(decision_backtest.get("decision_backtest_passed")),
        "regret_reduction_vs_static": decision_backtest.get("regret_reduction_vs_static"),
        "regret_reduction_vs_current_incidence": decision_backtest.get("regret_reduction_vs_current_incidence"),
        "model_rank_among_strategies": decision_backtest.get("model_rank_among_strategies"),
        "verdict": decision_backtest.get("verdict"),
        "evaluable_panel_weeks": decision_backtest.get("evaluable_panel_weeks"),
    }

    live_severity = "hard" if live_data_gate_status == "failed" else "soft"
    decision_severity = "hard" if decision_backtest_status in {"failed", "insufficient_evidence"} else "limited"

    return [
        {
            "gate": "forecast_quality",
            "status": forecast_status,
            "threshold": {
                "readiness": "go",
                "min_evaluable_panel_weeks": MIN_EVALUABLE_PANEL_WEEKS,
                "hard_blockers": "none",
            },
            "observed": {
                "readiness": readiness,
                "evaluable_panel_weeks": evaluable_weeks,
                "blockers": blockers,
                "warnings": warnings,
                "quality_gate_overall_passed": _quality_gate_passed(card),
            },
            "severity": "hard",
            "reason": "Forecast evidence must be strong enough before budget can be approved.",
            "explanation": "Forecast evidence is spendable only when readiness is go, enough panel weeks exist, and no hard blockers are present.",
        },
        {
            "gate": "baseline_superiority",
            "status": "failed" if model_worse_than_persistence else "passed",
            "threshold": {"model_must_beat_persistence": True},
            "observed": {
                "model_worse_than_persistence": bool(model_worse_than_persistence),
                "lift_vs_persistence": card.get("lift_vs_persistence") or {},
                "lift_vs_baseline_hit_rate": card.get("lift_vs_baseline_hit_rate") or {},
            },
            "severity": "hard",
            "reason": "Spending cannot increase when the model is worse than persistence.",
            "explanation": "Spending cannot increase when the regional policy does not beat simple persistence baselines.",
        },
        {
            "gate": "live_data_quality",
            "status": live_data_gate_status,
            "threshold": {
                "regional_data_fresh": True,
                "coverage_blockers": "none",
                "min_eligible_regions": min_eligible_regions,
            },
            "observed": {
                **_live_data_observed(predictions),
                "eligible_regions": eligible_region_count,
            },
            "severity": live_severity,
            "reason": "Regional data problems block affected regions; too few eligible regions block global approval.",
            "explanation": "Live regional data must be fresh and complete enough before budget shifts are allowed.",
        },
        {
            "gate": "decision_backtest",
            "status": decision_backtest_status,
            "threshold": {"min_regret_reduction_vs_static": backtest_threshold},
            "observed": backtest_observed,
            "severity": decision_severity,
            "reason": "The decision backtest decides whether recommendations are shadow, limited, or fully approved.",
            "explanation": "The MediaSpendingTruth allocation must beat simple allocation baselines on decision backtests.",
        },
        {
            "gate": "business_constraints",
            "status": "passed" if business_constraints_passed else "failed",
            "threshold": {"max_weekly_shift_pct": 15.0, "uncertainty_shift_cap_pct": 5.0},
            "observed": {"constraints_allow_budget_permission": bool(business_constraints_passed)},
            "severity": "hard" if not business_constraints_passed else "soft",
            "reason": "Business constraints cap normal recommendations and only block on hard exclusions.",
            "explanation": "Caps and business constraints must allow the recommendation before it becomes spendable.",
        },
    ]


def _derive_release_mode(gate_evaluations: list[Mapping[str, Any]]) -> str:
    hard_fails = [
        gate
        for gate in gate_evaluations
        if gate.get("severity") == "hard" and gate.get("status") == "failed"
    ]
    if hard_fails:
        return "blocked"
    if any(gate.get("status") == "insufficient_evidence" for gate in gate_evaluations):
        return "shadow_only"
    limited_fails = [
        gate
        for gate in gate_evaluations
        if gate.get("severity") == "limited" and gate.get("status") in {"failed", "warning"}
    ]
    if limited_fails:
        return "limited"
    return "approved"


def _blocked_reasons_from_gates(gate_evaluations: list[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    by_gate = {str(item.get("gate")): item for item in gate_evaluations}
    if (by_gate.get("forecast_quality") or {}).get("status") == "failed":
        _append_unique(reasons, "forecast_quality_gate_failed")
    if (by_gate.get("baseline_superiority") or {}).get("status") == "failed":
        _append_unique(reasons, "decision_backtest_not_better_than_persistence")
    if (by_gate.get("live_data_quality") or {}).get("status") == "failed":
        _append_unique(reasons, "data_quality_insufficient_for_budget_shift")
    if (by_gate.get("decision_backtest") or {}).get("status") == "failed":
        _append_unique(reasons, "decision_backtest_not_passed")
    if (by_gate.get("business_constraints") or {}).get("status") in {"failed", "blocked"}:
        _append_unique(reasons, "business_constraints_block_budget_shift")
    return reasons


def _global_status_for_release_mode(release_mode: str) -> str:
    return {
        "blocked": "blocked",
        "shadow_only": "planner_assist",
        "limited": "planner_assist",
        "approved": "spendable",
    }.get(release_mode, "blocked")


def _budget_permission_for_release_mode(release_mode: str) -> str:
    return {
        "blocked": "blocked",
        "shadow_only": "manual_approval_required",
        "limited": "approved_with_cap",
        "approved": "approved_with_cap",
    }.get(release_mode, "blocked")


def _max_approved_delta_for_release_mode(release_mode: str, policy: MediaSpendingTruthPolicy) -> float:
    if release_mode == "approved":
        return float(policy.max_weekly_shift_pct)
    if release_mode == "limited":
        return float(policy.uncertainty_shift_cap_pct)
    return 0.0


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
        "globalDecision": "blocked",
        "release_mode": "blocked",
        "releaseMode": "blocked",
        "max_approved_delta_pct": 0.0,
        "maxApprovedDeltaPct": 0.0,
        "budget_permission": "blocked",
        "decision_policy": policy.__dict__,
        "data_quality": "unknown",
        "forecast_evidence": "missing",
        "decision_backtest": {"decision_backtest_passed": False},
        "blocked_because": [reason],
        "blockedBecause": [reason],
        "gate_evaluations": [],
        "gateEvaluations": [],
        "gateTrace": [],
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
    decision_backtest_gate_status = _decision_backtest_status(decision_backtest_payload)
    eligible_region_count = sum(1 for row in rows if _region_is_live_eligible(row))
    min_eligible_regions = min(max(int(effective_policy.min_eligible_regions), 1), len(rows))
    if eligible_region_count >= len(rows):
        live_data_gate_status = "passed"
    elif eligible_region_count >= min_eligible_regions:
        live_data_gate_status = "warning"
    else:
        live_data_gate_status = "failed"

    business_constraints_passed = True
    gate_evaluations = _build_gate_evaluations(
        forecast_gate_passed=forecast_gate_passed,
        live_data_gate_status=live_data_gate_status,
        decision_backtest_status=decision_backtest_gate_status,
        business_constraints_passed=business_constraints_passed,
        insufficient_evidence=insufficient_evidence,
        model_worse_than_persistence=model_worse_than_persistence,
        readiness=readiness,
        blockers=blockers,
        warnings=warnings,
        evaluable_weeks=evaluable_weeks,
        card=card,
        predictions=rows,
        decision_backtest=decision_backtest_payload,
        eligible_region_count=eligible_region_count,
        min_eligible_regions=min_eligible_regions,
    )
    release_mode = _derive_release_mode(gate_evaluations)
    global_status = _global_status_for_release_mode(release_mode)
    budget_permission = _budget_permission_for_release_mode(release_mode)
    max_approved_delta_pct = _max_approved_delta_for_release_mode(release_mode, effective_policy)
    blocked_because = _blocked_reasons_from_gates(gate_evaluations) if release_mode == "blocked" else []
    full_spendable = release_mode == "approved"

    preliminary_regions: list[dict[str, Any]] = []

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
        region_eligible = fresh and not regional_blockers and not hard_blockers and not model_worse_than_persistence
        limiting_factors = list(dict.fromkeys([*hard_blockers, *regional_blockers]))
        manual = release_mode in {"shadow_only", "limited"}
        candidate_max_delta = 0.0
        media_truth = "watch_only"
        action = "maintain"

        promising = p_surge >= 0.55 and growth_score > 0.0 and confidence >= effective_policy.min_confidence_for_preposition
        plateau = p_surge >= 0.55 and _safe_float(prediction.get("change_pct")) <= 2.0 and saturation_score >= 0.55

        if hard_blockers or not fresh or regional_blockers:
            media_truth = "blocked"
            action = "none"
        elif model_worse_than_persistence:
            media_truth = "watch_only"
            action = "maintain"
        elif confidence < 0.45:
            media_truth = "watch_only"
            action = "maintain"
            _append_unique(limiting_factors, "low_confidence")
        elif release_mode == "shadow_only" and promising:
            media_truth = "preposition_approved"
            action = "small_increase"
            candidate_max_delta = effective_policy.planner_assist_max_delta_pct
        elif plateau:
            media_truth = "cap_or_reduce"
            action = "cap_or_reduce"
            candidate_max_delta = effective_policy.uncertainty_shift_cap_pct
        elif p_surge >= 0.65 and growth_score >= 0.15 and confidence >= effective_policy.min_confidence_for_approval and saturation_score < 0.75:
            media_truth = "increase_approved"
            action = "increase"
            candidate_max_delta = effective_policy.max_weekly_shift_pct
        elif promising:
            media_truth = "preposition_approved"
            action = "small_increase"
            candidate_max_delta = effective_policy.preposition_max_delta_pct
        elif p_surge <= 0.35 and growth_score <= 0.02 and confidence >= effective_policy.min_confidence_for_approval:
            media_truth = "decrease_approved"
            action = "decrease"
            candidate_max_delta = effective_policy.max_weekly_shift_pct
        else:
            media_truth = "maintain"
            action = "maintain"

        if release_mode == "blocked" or not region_eligible:
            candidate_max_delta = 0.0
            if region_eligible and not hard_blockers and not model_worse_than_persistence:
                media_truth = "watch_only"
                action = "maintain"
        if insufficient_evidence and not full_spendable:
            _append_unique(limiting_factors, "insufficient_evaluable_weeks")
        if decision_backtest_gate_status in {"failed", "insufficient_evidence", "warning"}:
            _append_unique(limiting_factors, "decision_backtest_not_passed")
        if model_worse_than_persistence:
            _append_unique(limiting_factors, "model_not_better_than_persistence")
        if not fresh:
            _append_unique(limiting_factors, "stale_data")
        if live_data_gate_status == "warning" and region_eligible:
            _append_unique(limiting_factors, "partial_regional_data_quality_warning")

        reason_codes = _region_reason_codes(
            prediction=prediction,
            confidence=confidence,
            p_surge=p_surge,
            growth_score=growth_score,
            blockers=all_gate_notes,
            insufficient_evidence=insufficient_evidence and not full_spendable,
            manual=manual and region_eligible,
        )
        if plateau:
            _append_unique(reason_codes, "high_current_activity_but_plateauing")

        region_budget_permission = "blocked"
        if region_eligible and release_mode == "shadow_only":
            region_budget_permission = "manual_approval_required"
        elif region_eligible and release_mode in {"limited", "approved"} and candidate_max_delta > 0:
            region_budget_permission = "approved_with_cap"

        preliminary_regions.append(
            {
                "region_code": code,
                "region_name": name,
                "pathogen_scope": virus_typ,
                "horizon_days": int(horizon_days),
                "media_spending_truth": media_truth,
                "budget_permission": region_budget_permission,
                "recommended_action": action,
                "recommended_delta_pct": 0.0,
                "shadow_delta_pct": 0.0,
                "shadowDeltaPct": 0.0,
                "approved_delta_pct": 0.0,
                "approvedDeltaPct": 0.0,
                "execution_status": "blocked" if not region_eligible or release_mode == "blocked" else release_mode,
                "executionStatus": "blocked" if not region_eligible or release_mode == "blocked" else release_mode,
                "max_delta_pct": round(float(max_approved_delta_pct if region_eligible else 0.0), 2),
                "shadow_max_delta_pct": round(float(candidate_max_delta), 2),
                "surge_probability_7d": round(p_surge, 4),
                "expected_growth_score": round(growth_score, 4),
                "confidence": round(confidence, 4),
                "budget_opportunity_score": round(opportunity, 4),
                "forecast_class": prediction.get("forecast_class") or prediction.get("cluster_id") or None,
                "reason_codes": reason_codes,
                "limiting_factors": limiting_factors,
                "manual_approval_required": bool(region_eligible and release_mode in {"shadow_only", "limited"}),
                "research_only": False,
                "planner_assist": bool(region_eligible and release_mode in {"shadow_only", "limited"}),
                "base_budget_eur": round(_base_budget_for_prediction(prediction, base_budget_by_region), 2),
                "uncertainty_capped": bool(release_mode == "limited"),
                "region_eligible_for_allocation": bool(region_eligible),
                "limitations": ["recommendation_valid_only_for_region_level_media_planning", "not_for_individual_targeting"],
            }
        )

    def _allocate(regions: list[dict[str, Any]], *, cap_pct: float, use_shadow_cap: bool) -> dict[str, dict[str, Any]]:
        allocation_input: list[dict[str, Any]] = []
        for region in regions:
            if not region.get("region_eligible_for_allocation"):
                continue
            region_cap = _safe_float(region.get("shadow_max_delta_pct")) if use_shadow_cap else min(_safe_float(region.get("shadow_max_delta_pct")), cap_pct)
            if region_cap <= 0.0:
                continue
            allocation_row = dict(region)
            allocation_row["max_delta_pct"] = region_cap
            allocation_row["uncertainty_capped"] = False
            allocation_input.append(allocation_row)
        if not allocation_input:
            return {}
        allocation = allocate_budget_deltas(
            allocation_input,
            config=BudgetAllocatorConfig(
                max_weekly_shift_pct=cap_pct,
                uncertainty_shift_cap_pct=cap_pct,
            ),
        )
        return {str(row.get("region_code")): row for row in allocation.get("regions", [])}

    shadow_allocation_rows: dict[str, dict[str, Any]] = {}
    approved_allocation_rows: dict[str, dict[str, Any]] = {}
    if release_mode != "blocked":
        shadow_allocation_rows = _allocate(
            preliminary_regions,
            cap_pct=effective_policy.max_weekly_shift_pct,
            use_shadow_cap=True,
        )
    if release_mode == "approved":
        approved_allocation_rows = shadow_allocation_rows
    elif release_mode == "limited":
        approved_allocation_rows = _allocate(
            preliminary_regions,
            cap_pct=effective_policy.uncertainty_shift_cap_pct,
            use_shadow_cap=False,
        )

    final_regions: list[dict[str, Any]] = []
    for region in preliminary_regions:
        code = str(region.get("region_code"))
        shadow_allocated = shadow_allocation_rows.get(code)
        approved_allocated = approved_allocation_rows.get(code)
        final_region = dict(region)

        shadow_delta = _safe_float(shadow_allocated.get("recommended_delta_pct")) if shadow_allocated else 0.0
        approved_delta = _safe_float(approved_allocated.get("recommended_delta_pct")) if approved_allocated else 0.0
        final_region["shadow_delta_pct"] = round(shadow_delta, 6)
        final_region["shadowDeltaPct"] = round(shadow_delta, 6)
        final_region["approved_delta_pct"] = round(approved_delta, 6)
        final_region["approvedDeltaPct"] = round(approved_delta, 6)
        final_region["recommended_delta_pct"] = round(approved_delta, 6)

        if approved_allocated:
            final_region["before_budget_eur"] = approved_allocated.get("before_budget_eur")
            final_region["after_budget_eur"] = approved_allocated.get("after_budget_eur")
            final_region["allocated_shift_eur"] = approved_allocated.get("allocated_shift_eur")
        else:
            final_region["before_budget_eur"] = final_region.get("base_budget_eur")
            final_region["after_budget_eur"] = final_region.get("base_budget_eur")
            final_region["allocated_shift_eur"] = 0.0

        if release_mode == "shadow_only" and final_region.get("region_eligible_for_allocation"):
            final_region["max_delta_pct"] = min(_safe_float(final_region.get("shadow_max_delta_pct")), effective_policy.planner_assist_max_delta_pct)
        elif release_mode == "limited" and final_region.get("region_eligible_for_allocation"):
            final_region["max_delta_pct"] = effective_policy.uncertainty_shift_cap_pct
        elif release_mode == "approved" and final_region.get("region_eligible_for_allocation"):
            final_region["max_delta_pct"] = effective_policy.max_weekly_shift_pct
        else:
            final_region["max_delta_pct"] = 0.0

        final_region.pop("region_eligible_for_allocation", None)
        final_region.pop("shadow_max_delta_pct", None)
        final_regions.append(final_region)

    forecast_evidence = "validated" if forecast_gate_passed else "limited" if not hard_blockers else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_date": decision_day.isoformat(),
        "valid_until": valid_day.isoformat(),
        "pathogen_scope": virus_typ,
        "horizon_days": int(horizon_days),
        "global_status": global_status,
        "globalDecision": release_mode,
        "release_mode": release_mode,
        "releaseMode": release_mode,
        "max_approved_delta_pct": round(float(max_approved_delta_pct), 2),
        "maxApprovedDeltaPct": round(float(max_approved_delta_pct), 2),
        "budget_permission": budget_permission,
        "decision_policy": effective_policy.__dict__,
        "data_quality": _data_quality_label(rows),
        "forecast_evidence": forecast_evidence,
        "decision_backtest": decision_backtest_payload,
        "blocked_because": blocked_because,
        "blockedBecause": blocked_because,
        "gate_evaluations": gate_evaluations,
        "gateEvaluations": gate_evaluations,
        "gateTrace": gate_evaluations,
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
