"""Lightweight, as-of-safe viral pressure features for MediaSpendingTruth v1.

This module deliberately avoids retrospective smoothing, target-week truth and
heavy latent-state models. The formulas are simple proxies that can be audited
and backtested before they are allowed to influence media spending decisions.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

FORMULA_VERSIONS: dict[str, str] = {
    "wastewater_case_divergence": "research_v1_causal_z_proxy",
    "viral_pressure_score": "research_v1_weighted_proxy",
    "spatial_import_pressure": "research_v1_neighbor_national_mean",
    "recent_saturation_score": "research_v1_baseline_zscore",
    "budget_opportunity_score": "media_spending_truth_v1",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _get(row: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in row and row.get(key) is not None:
            return _safe_float(row.get(key), default)
    return default


def build_viral_pressure_features(
    feature_row: Mapping[str, Any],
    *,
    surge_probability: float,
    expected_growth_score: float,
    confidence: float,
    market_weight: float,
    timing_fit: float = 1.0,
    data_quality_factor: float = 1.0,
) -> dict[str, Any]:
    """Build explanatory viral-pressure features from only current/as-of inputs."""

    row = feature_row or {}
    ww_growth = _get(row, "ww_slope7d", "wastewater_growth_z")
    ww_acceleration = _get(row, "ww_acceleration7d", "wastewater_acceleration_z")
    case_growth = _get(row, "survstat_momentum_2w", "reported_case_growth_z")
    are_growth = _get(row, "grippeweb_are_momentum_1w", "are_growth_z")
    ifsg_growth = _get(row, "ifsg_influenza_momentum_1w", "ifsg_rsv_momentum_1w", "ifsg_growth_z")

    wastewater_case_divergence = _clamp(ww_growth - case_growth, -2.0, 2.0)

    spatial_parts: list[float] = []
    for key in ("neighbor_ww_slope7d", "national_ww_slope7d", "spatial_import_pressure"):
        if key in row and row.get(key) is not None:
            spatial_parts.append(_safe_float(row.get(key)))
    spatial_import_pressure = _clamp(_mean(spatial_parts), -2.0, 2.0)

    recent_saturation_score = _clamp(_get(row, "survstat_baseline_zscore") / 2.5)
    saturation_factor = _clamp(1.0 - 0.65 * recent_saturation_score, 0.25, 1.0)

    pressure_raw = (
        0.34 * ww_growth
        + 0.18 * wastewater_case_divergence
        + 0.16 * case_growth
        + 0.12 * are_growth
        + 0.10 * ifsg_growth
        + 0.07 * spatial_import_pressure
        + 0.03 * ww_acceleration
        - 0.12 * recent_saturation_score
    )
    viral_pressure_score = _clamp(0.5 + pressure_raw / 2.0)

    budget_opportunity_score = _clamp(
        _clamp(_safe_float(surge_probability))
        * _clamp(_safe_float(expected_growth_score))
        * _clamp(_safe_float(confidence))
        * _clamp(_safe_float(market_weight))
        * _clamp(_safe_float(timing_fit))
        * _clamp(_safe_float(data_quality_factor))
        * saturation_factor
    )

    return {
        "wastewater_case_divergence": round(wastewater_case_divergence, 4),
        "viral_pressure_score": round(viral_pressure_score, 4),
        "spatial_import_pressure": round(spatial_import_pressure, 4),
        "recent_saturation_score": round(recent_saturation_score, 4),
        "saturation_factor": round(saturation_factor, 4),
        "budget_opportunity_score": round(budget_opportunity_score, 4),
        "formula_versions": dict(FORMULA_VERSIONS),
    }


def _data_quality_from_prediction(prediction: Mapping[str, Any]) -> float:
    decision = prediction.get("decision") if isinstance(prediction.get("decision"), Mapping) else {}
    parts = [
        _safe_float(decision.get("source_freshness_score"), 0.75),
        _safe_float(decision.get("usable_source_share"), 0.75),
        _safe_float(decision.get("source_coverage_score"), 0.75),
        1.0 - _safe_float(decision.get("source_revision_risk"), 0.25),
        1.0 if prediction.get("regional_data_fresh", True) else 0.35,
    ]
    return _clamp(_mean(parts))


def _timing_fit_for_horizon(horizon_days: int | None) -> float:
    if horizon_days == 5:
        return 0.95
    if horizon_days == 7:
        return 1.0
    if horizon_days in {10, 14}:
        return 0.80
    if horizon_days == 21:
        return 0.65
    return 0.75


def build_prediction_viral_pressure_features(
    *,
    prediction: Mapping[str, Any],
    feature_row: Mapping[str, Any],
    timing_fit: float | None = None,
) -> dict[str, Any]:
    """Attach MediaSpendingTruth research features to one regional prediction."""

    decision = prediction.get("decision") if isinstance(prediction.get("decision"), Mapping) else {}
    confidence = _safe_float(
        decision.get("forecast_confidence")
        or decision.get("decision_score")
        or prediction.get("event_probability"),
        0.50,
    )
    change_pct = _safe_float(prediction.get("change_pct"))
    expected_growth_score = _clamp(max(change_pct, 0.0) / 50.0)
    population_m = _safe_float(prediction.get("state_population_millions"), 0.0)
    market_weight = _clamp(population_m / 18.0, 0.20, 1.0) if population_m > 0 else 0.50
    horizon_raw = prediction.get("horizon_days")
    try:
        horizon_days = int(horizon_raw) if horizon_raw is not None else None
    except (TypeError, ValueError):
        horizon_days = None

    return build_viral_pressure_features(
        feature_row,
        surge_probability=_safe_float(prediction.get("event_probability")),
        expected_growth_score=expected_growth_score,
        confidence=confidence,
        market_weight=market_weight,
        timing_fit=timing_fit if timing_fit is not None else _timing_fit_for_horizon(horizon_days),
        data_quality_factor=_data_quality_from_prediction(prediction),
    )
