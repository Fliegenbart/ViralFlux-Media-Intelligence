from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.benchmarking.metrics import weighted_interval_score
from app.services.ml.regional_panel_utils import time_based_panel_splits

DEFAULT_BASELINE_WEIGHT_STEP = 0.25
DEFAULT_BASELINE_WEIGHTS = {
    "current_log": 0.5,
    "seasonal_log": 0.3,
    "pooled_log": 0.2,
}


def baseline_component_logs(
    frame: pd.DataFrame,
    *,
    date_col: str = "as_of_date",
    state_col: str = "bundesland",
    current_col: str = "current_known_incidence",
    seasonal_col: str = "seasonal_baseline",
) -> dict[str, np.ndarray]:
    del state_col
    if frame.empty:
        return {
            "current_log": np.asarray([], dtype=float),
            "seasonal_log": np.asarray([], dtype=float),
            "pooled_log": np.asarray([], dtype=float),
            "pooled_incidence": np.asarray([], dtype=float),
        }

    working = frame.copy()
    working[date_col] = pd.to_datetime(working[date_col]).dt.normalize()
    current_arr = np.maximum(working[current_col].astype(float).to_numpy(), 0.0)
    seasonal_arr = np.maximum(working[seasonal_col].astype(float).to_numpy(), 0.0)

    date_series = working[date_col]
    total = working.groupby(date_col)[current_col].transform("sum").astype(float).to_numpy()
    count = working.groupby(date_col)[current_col].transform("count").astype(float).to_numpy()
    pooled_incidence = np.where(
        count > 1.0,
        (total - current_arr) / np.maximum(count - 1.0, 1.0),
        current_arr,
    )
    del date_series

    return {
        "current_log": np.log1p(current_arr),
        "seasonal_log": np.log1p(seasonal_arr),
        "pooled_log": np.log1p(np.maximum(pooled_incidence, 0.0)),
        "pooled_incidence": np.maximum(pooled_incidence, 0.0),
    }


def baseline_center_log(
    frame: pd.DataFrame,
    *,
    weights: dict[str, float],
) -> np.ndarray:
    components = baseline_component_logs(frame)
    return (
        float(weights.get("current_log") or 0.0) * components["current_log"]
        + float(weights.get("seasonal_log") or 0.0) * components["seasonal_log"]
        + float(weights.get("pooled_log") or 0.0) * components["pooled_log"]
    )


def empirical_residual_quantiles(
    y_next_log: Sequence[float],
    baseline_log: Sequence[float],
    *,
    quantiles: Sequence[float] = CANONICAL_FORECAST_QUANTILES,
) -> dict[float, float]:
    residuals = np.asarray(y_next_log, dtype=float) - np.asarray(baseline_log, dtype=float)
    if residuals.size == 0:
        return {float(quantile): 0.0 for quantile in quantiles}
    return {
        float(quantile): float(np.quantile(residuals, float(quantile)))
        for quantile in quantiles
    }


def apply_residual_quantiles(
    baseline_log: Sequence[float],
    residual_quantiles: dict[float, float],
) -> dict[float, np.ndarray]:
    baseline_arr = np.asarray(baseline_log, dtype=float)
    return {
        float(quantile): np.maximum(np.expm1(baseline_arr + float(residual)), 0.0)
        for quantile, residual in residual_quantiles.items()
    }


def _simplex_weight_grid(step: float = DEFAULT_BASELINE_WEIGHT_STEP) -> list[dict[str, float]]:
    normalized_step = max(float(step), 0.05)
    steps = int(round(1.0 / normalized_step))
    grid: list[dict[str, float]] = []
    for a_idx in range(steps + 1):
        for b_idx in range(steps - a_idx + 1):
            c_idx = steps - a_idx - b_idx
            grid.append(
                {
                    "current_log": round(a_idx * normalized_step, 6),
                    "seasonal_log": round(b_idx * normalized_step, 6),
                    "pooled_log": round(c_idx * normalized_step, 6),
                }
            )
    return grid


def optimize_baseline_weights(
    frame: pd.DataFrame,
    *,
    quantiles: Sequence[float] = CANONICAL_FORECAST_QUANTILES,
    candidate_step: float = DEFAULT_BASELINE_WEIGHT_STEP,
    min_train_periods: int = 8,
    min_test_periods: int = 2,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "weights": dict(DEFAULT_BASELINE_WEIGHTS),
            "diagnostics": {"evaluated_candidates": 0, "used_splits": 0, "fallback_used": True},
            "residual_quantiles": {float(quantile): 0.0 for quantile in quantiles},
        }

    working = frame.copy()
    working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
    working["y_next_log"] = np.log1p(np.maximum(working["next_week_incidence"].astype(float).to_numpy(), 0.0))
    splits = time_based_panel_splits(
        working["as_of_date"],
        n_splits=4,
        min_train_periods=min_train_periods,
        min_test_periods=min_test_periods,
    )
    candidates = _simplex_weight_grid(step=candidate_step)
    if not splits:
        residual_quantiles = empirical_residual_quantiles(
            working["y_next_log"].to_numpy(dtype=float),
            baseline_center_log(working, weights=DEFAULT_BASELINE_WEIGHTS),
            quantiles=quantiles,
        )
        return {
            "weights": dict(DEFAULT_BASELINE_WEIGHTS),
            "diagnostics": {"evaluated_candidates": len(candidates), "used_splits": 0, "fallback_used": True},
            "residual_quantiles": residual_quantiles,
        }

    best_weights = dict(DEFAULT_BASELINE_WEIGHTS)
    best_score: float | None = None
    for candidate in candidates:
        score = 0.0
        used = 0
        for train_dates, test_dates in splits:
            train_df = working.loc[working["as_of_date"].isin(train_dates)].copy()
            test_df = working.loc[working["as_of_date"].isin(test_dates)].copy()
            if train_df.empty or test_df.empty:
                continue
            residual_quantiles = empirical_residual_quantiles(
                train_df["y_next_log"].to_numpy(dtype=float),
                baseline_center_log(train_df, weights=candidate),
                quantiles=quantiles,
            )
            forecast_quantiles = apply_residual_quantiles(
                baseline_center_log(test_df, weights=candidate),
                residual_quantiles,
            )
            score += weighted_interval_score(
                test_df["next_week_incidence"].to_numpy(dtype=float),
                forecast_quantiles,
            )
            used += 1
        if used == 0:
            continue
        average_score = score / used
        if best_score is None or average_score < best_score:
            best_score = average_score
            best_weights = dict(candidate)

    final_residual_quantiles = empirical_residual_quantiles(
        working["y_next_log"].to_numpy(dtype=float),
        baseline_center_log(working, weights=best_weights),
        quantiles=quantiles,
    )
    return {
        "weights": best_weights,
        "diagnostics": {
            "evaluated_candidates": len(candidates),
            "used_splits": len(splits),
            "fallback_used": best_score is None,
            "oof_wis": float(best_score) if best_score is not None else None,
        },
        "residual_quantiles": final_residual_quantiles,
    }


def _coerce_scalar_quantiles(quantiles: dict[float, Any]) -> dict[float, float]:
    scalar_map: dict[float, float] = {}
    for quantile, value in quantiles.items():
        array = np.asarray(value, dtype=float).reshape(-1)
        if array.size == 0:
            continue
        scalar_map[float(quantile)] = float(array[0])
    return scalar_map


def _ordered_unique_quantile_points(quantiles: dict[float, float]) -> tuple[np.ndarray, np.ndarray]:
    ordered = sorted((float(q), float(v)) for q, v in quantiles.items())
    tau_by_value: dict[float, float] = {}
    for tau, value in ordered:
        tau_by_value[value] = max(float(tau_by_value.get(value, 0.0)), float(tau))
    values = np.asarray(sorted(tau_by_value), dtype=float)
    taus = np.asarray([tau_by_value[float(value)] for value in values], dtype=float)
    return values, taus


def _prepared_quantile_points(
    quantiles: dict[float, float] | tuple[np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(quantiles, tuple):
        values = np.asarray(quantiles[0], dtype=float).reshape(-1)
        taus = np.asarray(quantiles[1], dtype=float).reshape(-1)
        if values.size != taus.size:
            raise ValueError("Prepared quantile values and taus must have the same length.")
        return np.maximum.accumulate(values), taus
    return _ordered_unique_quantile_points(_coerce_scalar_quantiles(quantiles))


def _quantile_cdf_from_points(
    value: float,
    *,
    values: np.ndarray,
    taus: np.ndarray,
) -> float:
    if values.size == 0:
        return 0.5
    target_value = float(max(value, 0.0))
    if values.size == 1:
        return float(np.clip(taus[0], 1e-6, 1.0 - 1e-6))

    if target_value <= values[0]:
        x0 = np.log1p(max(values[0], 0.0))
        x1 = np.log1p(max(values[1], 0.0))
        slope = (taus[1] - taus[0]) / max(x1 - x0, 1e-6)
        extrapolated = taus[0] + slope * (np.log1p(target_value) - x0)
        return float(np.clip(extrapolated, 1e-6, taus[0]))

    if target_value >= values[-1]:
        x0 = np.log1p(max(values[-2], 0.0))
        x1 = np.log1p(max(values[-1], 0.0))
        slope = (taus[-1] - taus[-2]) / max(x1 - x0, 1e-6)
        extrapolated = taus[-1] + slope * (np.log1p(target_value) - x1)
        return float(np.clip(extrapolated, taus[-1], 1.0 - 1e-6))

    upper_idx = int(np.searchsorted(values, target_value, side="right"))
    lower_idx = max(upper_idx - 1, 0)
    v0 = values[lower_idx]
    v1 = values[upper_idx]
    tau0 = taus[lower_idx]
    tau1 = taus[upper_idx]
    if np.isclose(v1, v0):
        return float(np.clip(tau1, 1e-6, 1.0 - 1e-6))
    interpolated = tau0 + ((tau1 - tau0) * ((target_value - v0) / (v1 - v0)))
    return float(np.clip(interpolated, 1e-6, 1.0 - 1e-6))


def quantile_cdf(value: float, quantiles: dict[float, float]) -> float:
    values, taus = _prepared_quantile_points(quantiles)
    return _quantile_cdf_from_points(value, values=values, taus=taus)


def mixture_cdf_value(
    value: float,
    *,
    model_quantiles: dict[float, float],
    baseline_quantiles: dict[float, float],
    mixture_weight: float,
) -> float:
    weight = float(np.clip(mixture_weight, 0.0, 1.0))
    model_cdf = quantile_cdf(value, model_quantiles)
    baseline_cdf = quantile_cdf(value, baseline_quantiles)
    return float(((1.0 - weight) * baseline_cdf) + (weight * model_cdf))


def _mixture_cdf_from_points(
    value: float,
    *,
    model_points: tuple[np.ndarray, np.ndarray],
    baseline_points: tuple[np.ndarray, np.ndarray],
    mixture_weight: float,
) -> float:
    model_values, model_taus = model_points
    baseline_values, baseline_taus = baseline_points
    weight = float(np.clip(mixture_weight, 0.0, 1.0))
    model_cdf = _quantile_cdf_from_points(value, values=model_values, taus=model_taus)
    baseline_cdf = _quantile_cdf_from_points(value, values=baseline_values, taus=baseline_taus)
    return float(((1.0 - weight) * baseline_cdf) + (weight * model_cdf))


def _tail_log_coefficients(values: np.ndarray, taus: np.ndarray, *, side: str) -> tuple[str, float, float]:
    if values.size == 0 or taus.size == 0:
        return ("constant", 0.5, 0.0)
    if values.size == 1:
        return ("constant", float(np.clip(taus[0], 1e-6, 1.0 - 1e-6)), 0.0)
    if side == "left":
        x0 = np.log1p(max(values[0], 0.0))
        x1 = np.log1p(max(values[1], 0.0))
        slope = float((taus[1] - taus[0]) / max(x1 - x0, 1e-6))
        intercept = float(taus[0] - (slope * x0))
        return ("log", intercept, slope)
    x0 = np.log1p(max(values[-2], 0.0))
    x1 = np.log1p(max(values[-1], 0.0))
    slope = float((taus[-1] - taus[-2]) / max(x1 - x0, 1e-6))
    intercept = float(taus[-1] - (slope * x1))
    return ("log", intercept, slope)


def _component_interval_representation(
    lower: float,
    upper: float,
    *,
    values: np.ndarray,
    taus: np.ndarray,
    left_tail: tuple[str, float, float],
    right_tail: tuple[str, float, float],
) -> tuple[str, float, float]:
    if values.size == 0 or taus.size == 0:
        return ("constant", 0.5, 0.0)
    if values.size == 1:
        return ("constant", float(np.clip(taus[0], 1e-6, 1.0 - 1e-6)), 0.0)

    probe = float((lower + upper) / 2.0)
    if probe < values[0]:
        return left_tail
    if probe > values[-1]:
        return right_tail

    upper_idx = int(np.searchsorted(values, probe, side="right"))
    lower_idx = max(min(upper_idx - 1, values.size - 2), 0)
    v0 = values[lower_idx]
    v1 = values[lower_idx + 1]
    tau0 = taus[lower_idx]
    tau1 = taus[lower_idx + 1]
    if np.isclose(v1, v0):
        return ("constant", float(np.clip(tau1, 1e-6, 1.0 - 1e-6)), 0.0)
    slope = float((tau1 - tau0) / max(v1 - v0, 1e-6))
    intercept = float(tau0 - (slope * v0))
    return ("linear", intercept, slope)


def _evaluate_component_representation(value: float, representation: tuple[str, float, float]) -> float:
    mode, intercept, slope = representation
    if mode == "constant":
        return float(intercept)
    if mode == "linear":
        return float(intercept + (slope * value))
    return float(intercept + (slope * np.log1p(max(value, 0.0))))


def _solve_mixture_interval(
    *,
    target_quantile: float,
    lower: float,
    upper: float,
    weight: float,
    model_points: tuple[np.ndarray, np.ndarray],
    baseline_points: tuple[np.ndarray, np.ndarray],
    model_representation: tuple[str, float, float],
    baseline_representation: tuple[str, float, float],
) -> float:
    mode_pair = (model_representation[0], baseline_representation[0])
    if mode_pair == ("linear", "linear"):
        intercept = (weight * model_representation[1]) + ((1.0 - weight) * baseline_representation[1])
        slope = (weight * model_representation[2]) + ((1.0 - weight) * baseline_representation[2])
        if abs(slope) > 1e-12:
            solved = (float(target_quantile) - intercept) / slope
            return float(np.clip(solved, lower, upper))
    if mode_pair == ("constant", "constant"):
        return float(np.clip(lower, 0.0, upper))

    interval_lower = float(lower)
    interval_upper = float(upper)
    for _ in range(24):
        midpoint = (interval_lower + interval_upper) / 2.0
        cdf_value = _mixture_cdf_from_points(
            midpoint,
            model_points=model_points,
            baseline_points=baseline_points,
            mixture_weight=weight,
        )
        if cdf_value >= float(target_quantile):
            interval_upper = midpoint
        else:
            interval_lower = midpoint
    return float((interval_lower + interval_upper) / 2.0)


def _quantile_for_mixture_prepared(
    target_quantile: float,
    *,
    model_points: tuple[np.ndarray, np.ndarray],
    baseline_points: tuple[np.ndarray, np.ndarray],
    mixture_weight: float,
) -> float:
    model_values, model_taus = model_points
    baseline_values, baseline_taus = baseline_points
    support = np.unique(np.concatenate([model_values, baseline_values]))
    if support.size == 0:
        return 0.0
    support = np.maximum.accumulate(np.maximum(support, 0.0))
    weight = float(np.clip(mixture_weight, 0.0, 1.0))
    target = float(np.clip(float(target_quantile), 1e-6, 1.0 - 1e-6))
    support_cdf = np.asarray(
        [
            _mixture_cdf_from_points(
                float(value),
                model_points=model_points,
                baseline_points=baseline_points,
                mixture_weight=weight,
            )
            for value in support
        ],
        dtype=float,
    )
    support_cdf = np.clip(np.maximum.accumulate(support_cdf), 1e-6, 1.0 - 1e-6)

    if target <= support_cdf[0]:
        lower = 0.0
        upper = float(support[0])
    elif target >= support_cdf[-1]:
        lower = float(support[-1])
        upper = float(support[-1])
        while _mixture_cdf_from_points(
            upper,
            model_points=model_points,
            baseline_points=baseline_points,
            mixture_weight=weight,
        ) < target:
            upper = max((upper * 1.5) + 1.0, upper + 1.0)
    else:
        upper_idx = int(np.searchsorted(support_cdf, target, side="left"))
        if np.isclose(support_cdf[upper_idx], target):
            return float(support[upper_idx])
        lower_idx = max(upper_idx - 1, 0)
        lower = float(support[lower_idx])
        upper = float(support[upper_idx])

    model_left_tail = _tail_log_coefficients(model_values, model_taus, side="left")
    model_right_tail = _tail_log_coefficients(model_values, model_taus, side="right")
    baseline_left_tail = _tail_log_coefficients(baseline_values, baseline_taus, side="left")
    baseline_right_tail = _tail_log_coefficients(baseline_values, baseline_taus, side="right")
    model_representation = _component_interval_representation(
        lower,
        upper,
        values=model_values,
        taus=model_taus,
        left_tail=model_left_tail,
        right_tail=model_right_tail,
    )
    baseline_representation = _component_interval_representation(
        lower,
        upper,
        values=baseline_values,
        taus=baseline_taus,
        left_tail=baseline_left_tail,
        right_tail=baseline_right_tail,
    )
    return _solve_mixture_interval(
        target_quantile=target,
        lower=lower,
        upper=upper,
        weight=weight,
        model_points=model_points,
        baseline_points=baseline_points,
        model_representation=model_representation,
        baseline_representation=baseline_representation,
    )


def _mixture_quantiles_for_sample(
    *,
    model_points: tuple[np.ndarray, np.ndarray],
    baseline_points: tuple[np.ndarray, np.ndarray],
    mixture_weight: float,
    output_quantiles: Sequence[float],
) -> np.ndarray:
    if model_points[0].size == 0 and baseline_points[0].size == 0:
        return np.zeros(len(output_quantiles), dtype=float)
    resolved = np.zeros(len(output_quantiles), dtype=float)
    for idx, quantile in enumerate(output_quantiles):
        resolved[idx] = _quantile_for_mixture_prepared(
            float(quantile),
            model_points=model_points,
            baseline_points=baseline_points,
            mixture_weight=mixture_weight,
        )
    return np.maximum.accumulate(np.maximum(resolved, 0.0))


def _quantile_for_mixture(
    target_quantile: float,
    *,
    model_quantiles: dict[float, float],
    baseline_quantiles: dict[float, float],
    mixture_weight: float,
) -> float:
    support = list(_coerce_scalar_quantiles(model_quantiles).values()) + list(
        _coerce_scalar_quantiles(baseline_quantiles).values()
    )
    lower = max(min(support or [0.0]), 0.0)
    upper = max(support or [1.0])
    while mixture_cdf_value(
        upper,
        model_quantiles=model_quantiles,
        baseline_quantiles=baseline_quantiles,
        mixture_weight=mixture_weight,
    ) < float(target_quantile):
        upper = max((upper * 1.5) + 1.0, upper + 1.0)
    while mixture_cdf_value(
        lower,
        model_quantiles=model_quantiles,
        baseline_quantiles=baseline_quantiles,
        mixture_weight=mixture_weight,
    ) > float(target_quantile) and lower > 0.0:
        lower = max((lower / 2.0) - 1.0, 0.0)

    for _ in range(48):
        midpoint = (lower + upper) / 2.0
        cdf_value = mixture_cdf_value(
            midpoint,
            model_quantiles=model_quantiles,
            baseline_quantiles=baseline_quantiles,
            mixture_weight=mixture_weight,
        )
        if cdf_value >= float(target_quantile):
            upper = midpoint
        else:
            lower = midpoint
    return float((lower + upper) / 2.0)


def mixture_quantiles_via_cdf(
    *,
    model_quantiles: dict[float, Sequence[float] | np.ndarray],
    baseline_quantiles: dict[float, Sequence[float] | np.ndarray],
    mixture_weight: float,
    output_quantiles: Sequence[float] = CANONICAL_FORECAST_QUANTILES,
) -> dict[float, np.ndarray]:
    all_inputs = list(model_quantiles.values()) + list(baseline_quantiles.values())
    if not all_inputs:
        return {}
    sample_count = max(int(np.asarray(values, dtype=float).reshape(-1).size) for values in all_inputs)
    result = {
        float(quantile): np.zeros(sample_count, dtype=float)
        for quantile in output_quantiles
    }
    ordered_model_quantiles = sorted(float(quantile) for quantile in model_quantiles)
    ordered_baseline_quantiles = sorted(float(quantile) for quantile in baseline_quantiles)
    model_matrix = {
        quantile: np.asarray(model_quantiles[quantile], dtype=float).reshape(-1)
        for quantile in ordered_model_quantiles
    }
    baseline_matrix = {
        quantile: np.asarray(baseline_quantiles[quantile], dtype=float).reshape(-1)
        for quantile in ordered_baseline_quantiles
    }
    ordered_output_quantiles = [float(quantile) for quantile in sorted(result)]
    for idx in range(sample_count):
        scalar_model = np.asarray([float(model_matrix[quantile][idx]) for quantile in ordered_model_quantiles], dtype=float)
        scalar_baseline = np.asarray(
            [float(baseline_matrix[quantile][idx]) for quantile in ordered_baseline_quantiles],
            dtype=float,
        )
        resolved = _mixture_quantiles_for_sample(
            model_points=_prepared_quantile_points((scalar_model, np.asarray(ordered_model_quantiles, dtype=float))),
            baseline_points=_prepared_quantile_points(
                (scalar_baseline, np.asarray(ordered_baseline_quantiles, dtype=float))
            ),
            mixture_weight=mixture_weight,
            output_quantiles=ordered_output_quantiles,
        )
        for output_idx, quantile in enumerate(ordered_output_quantiles):
            result[quantile][idx] = float(resolved[output_idx])
    stacked = np.vstack([result[float(quantile)] for quantile in ordered_output_quantiles])
    monotone = np.maximum.accumulate(stacked, axis=0)
    return {
        float(quantile): monotone[idx]
        for idx, quantile in enumerate(ordered_output_quantiles)
    }


def optimize_persistence_mix_weight(
    *,
    y_true: Sequence[float],
    model_quantiles: dict[float, Sequence[float] | np.ndarray],
    persistence_quantiles: dict[float, Sequence[float] | np.ndarray],
    weight_grid: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0),
) -> dict[str, Any]:
    if not model_quantiles or not persistence_quantiles:
        return {"weight": 1.0, "evaluated_weights": 0, "wis": None}

    best_weight = 1.0
    best_score: float | None = None
    evaluated = 0
    for raw_weight in weight_grid:
        weight = float(np.clip(raw_weight, 0.0, 1.0))
        mixed_quantiles = mixture_quantiles_via_cdf(
            model_quantiles=model_quantiles,
            baseline_quantiles=persistence_quantiles,
            mixture_weight=weight,
            output_quantiles=tuple(sorted(float(q) for q in model_quantiles)),
        )
        score = weighted_interval_score(np.asarray(y_true, dtype=float), mixed_quantiles)
        evaluated += 1
        if best_score is None or score < best_score:
            best_score = float(score)
            best_weight = weight
    return {
        "weight": best_weight,
        "evaluated_weights": evaluated,
        "wis": best_score,
    }
