from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.regional_panel_utils import average_precision_safe, brier_score_safe, compute_ece


def _coerce_quantile_columns(frame: pd.DataFrame) -> dict[float, str]:
    mapping: dict[float, str] = {}
    for quantile in CANONICAL_FORECAST_QUANTILES:
        for candidate in (f"q_{quantile:g}", f"quantile_{quantile:g}", f"pred_q_{quantile:g}", f"q{quantile}"):
            if candidate in frame.columns:
                mapping[quantile] = candidate
                break
        if quantile in mapping:
            continue
        normalized = f"q{int(round(quantile * 1000)):04d}"
        if normalized in frame.columns:
            mapping[quantile] = normalized
    return mapping


def pinball_loss(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    quantile: float,
) -> float:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    q = float(quantile)
    errors = y_true_arr - y_pred_arr
    return float(np.mean(np.maximum(q * errors, (q - 1.0) * errors)))


def coverage(
    y_true: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float],
) -> float:
    y_true_arr = np.asarray(y_true, dtype=float)
    lower_arr = np.asarray(lower, dtype=float)
    upper_arr = np.asarray(upper, dtype=float)
    if len(y_true_arr) == 0:
        return 0.0
    covered = (y_true_arr >= lower_arr) & (y_true_arr <= upper_arr)
    return float(np.mean(covered))


def weighted_interval_score(
    y_true: Sequence[float],
    quantile_predictions: dict[float, Sequence[float]],
) -> float:
    y_true_arr = np.asarray(y_true, dtype=float)
    if len(y_true_arr) == 0:
        return 0.0

    median = np.asarray(quantile_predictions.get(0.5, y_true_arr), dtype=float)
    total_score = 0.5 * np.abs(y_true_arr - median)
    total_weight = 0.5

    for lower_q, upper_q in ((0.025, 0.975), (0.1, 0.9), (0.25, 0.75)):
        if lower_q not in quantile_predictions or upper_q not in quantile_predictions:
            continue
        alpha = 2.0 * lower_q
        lower_arr = np.asarray(quantile_predictions[lower_q], dtype=float)
        upper_arr = np.asarray(quantile_predictions[upper_q], dtype=float)
        interval_score = (
            (upper_arr - lower_arr)
            + (2.0 / max(alpha, 1e-9)) * (lower_arr - y_true_arr) * (y_true_arr < lower_arr)
            + (2.0 / max(alpha, 1e-9)) * (y_true_arr - upper_arr) * (y_true_arr > upper_arr)
        )
        weight = alpha / 2.0
        total_score = total_score + weight * interval_score
        total_weight += weight

    return float(np.mean(total_score / max(total_weight, 1e-9)))


def quantile_crps(
    y_true: Sequence[float],
    quantile_predictions: dict[float, Sequence[float]],
) -> float:
    """Approximate CRPS from a discrete quantile grid.

    For a forecast represented by quantiles only, we approximate CRPS as
    ``2 * mean(pinball_loss_q)`` across the available quantile grid. This keeps
    the score strictly proper for the represented quantiles and is stable across
    the benchmark stack without requiring full distribution objects.
    """
    if not quantile_predictions:
        return 0.0
    monotone = monotone_quantiles(quantile_predictions)
    losses = [
        pinball_loss(y_true, predictions, quantile)
        for quantile, predictions in monotone.items()
    ]
    if not losses:
        return 0.0
    return float(2.0 * np.mean(losses))


def winkler_score(
    y_true: Sequence[float],
    *,
    lower: Sequence[float],
    upper: Sequence[float],
    alpha: float,
) -> float:
    y_true_arr = np.asarray(y_true, dtype=float)
    lower_arr = np.asarray(lower, dtype=float)
    upper_arr = np.asarray(upper, dtype=float)
    alpha_value = max(float(alpha), 1e-9)
    if len(y_true_arr) == 0:
        return 0.0
    interval = upper_arr - lower_arr
    below_penalty = (2.0 / alpha_value) * (lower_arr - y_true_arr) * (y_true_arr < lower_arr)
    above_penalty = (2.0 / alpha_value) * (y_true_arr - upper_arr) * (y_true_arr > upper_arr)
    return float(np.mean(interval + below_penalty + above_penalty))


def monotone_quantiles(quantile_predictions: dict[float, Sequence[float]]) -> dict[float, np.ndarray]:
    if not quantile_predictions:
        return {}
    ordered = sorted(quantile_predictions)
    values = np.vstack([np.asarray(quantile_predictions[q], dtype=float) for q in ordered])
    monotone = np.maximum.accumulate(values, axis=0)
    return {quantile: monotone[idx] for idx, quantile in enumerate(ordered)}


def summarize_probabilistic_metrics(
    *,
    y_true: Sequence[float],
    quantile_predictions: dict[float, Sequence[float]],
    baseline_quantiles: dict[float, Sequence[float]] | None = None,
    event_labels: Sequence[int] | None = None,
    event_probabilities: Sequence[float] | None = None,
    action_threshold: float | None = None,
) -> dict[str, Any]:
    y_true_arr = np.asarray(y_true, dtype=float)
    monotone = monotone_quantiles(quantile_predictions)
    metrics: dict[str, Any] = {
        "wis": round(weighted_interval_score(y_true_arr, monotone), 6),
        "crps": round(quantile_crps(y_true_arr, monotone), 6),
        "crps_method": "quantile_pinball_grid",
    }

    if baseline_quantiles:
        baseline_wis = weighted_interval_score(y_true_arr, monotone_quantiles(baseline_quantiles))
        metrics["baseline_wis"] = round(float(baseline_wis), 6)
        metrics["relative_wis"] = round(float(metrics["wis"]) / max(float(baseline_wis), 1e-9), 6)

    for lower_q, upper_q, name in (
        (0.25, 0.75, "coverage_50"),
        (0.1, 0.9, "coverage_80"),
        (0.025, 0.975, "coverage_95"),
    ):
        if lower_q in monotone and upper_q in monotone:
            metrics[name] = round(coverage(y_true_arr, monotone[lower_q], monotone[upper_q]), 6)

    if 0.1 in monotone and 0.9 in monotone:
        metrics["winkler_80"] = round(
            winkler_score(
                y_true_arr,
                lower=monotone[0.1],
                upper=monotone[0.9],
                alpha=0.2,
            ),
            6,
        )
    if 0.025 in monotone and 0.975 in monotone:
        metrics["winkler_95"] = round(
            winkler_score(
                y_true_arr,
                lower=monotone[0.025],
                upper=monotone[0.975],
                alpha=0.05,
            ),
            6,
        )

    pinball_summary: dict[str, float] = {}
    for quantile, predictions in monotone.items():
        pinball_summary[str(quantile)] = round(pinball_loss(y_true_arr, predictions, quantile), 6)
    if pinball_summary:
        metrics["pinball_loss"] = round(float(np.mean(list(pinball_summary.values()))), 6)
        metrics["pinball_by_quantile"] = pinball_summary

    if 0.5 in monotone:
        median = np.asarray(monotone[0.5], dtype=float)
        errors = median - y_true_arr
        nonzero = y_true_arr != 0
        metrics["mae"] = round(float(np.mean(np.abs(errors))), 6)
        metrics["rmse"] = round(float(np.sqrt(np.mean(errors ** 2))), 6)
        metrics["mape"] = round(
            float(np.mean(np.abs(errors[nonzero] / y_true_arr[nonzero])) * 100.0) if nonzero.any() else 0.0,
            6,
        )

    if event_labels is not None and event_probabilities is not None:
        labels = np.asarray(event_labels, dtype=int)
        probs = np.clip(np.asarray(event_probabilities, dtype=float), 0.001, 0.999)
        metrics["brier_score"] = round(brier_score_safe(labels, probs), 6)
        metrics["ece"] = round(compute_ece(labels, probs), 6)
        metrics["pr_auc"] = round(average_precision_safe(labels, probs), 6)
        threshold = float(action_threshold if action_threshold is not None else 0.5)
        activated = probs >= threshold
        positives = labels == 1
        tp = float(np.sum(activated & positives))
        fp = float(np.sum(activated & ~positives))
        fn = float(np.sum(~activated & positives))
        recall = tp / max(tp + fn, 1.0)
        precision = tp / max(tp + fp, 1.0)
        fp_rate = fp / max(float(np.sum(~positives)), 1.0)
        metrics["recall_at_action_threshold"] = round(recall, 6)
        metrics["precision_at_action_threshold"] = round(precision, 6)
        metrics["decision_utility"] = round((0.7 * recall) + (0.3 * precision) - (0.4 * fp_rate), 6)

    return metrics


def summarize_frame_metrics(
    frame: pd.DataFrame,
    *,
    y_true_col: str = "y_true",
    event_label_col: str = "event_label",
    event_probability_col: str = "event_probability",
    baseline_prefix: str = "baseline_",
    action_threshold: float | None = None,
) -> dict[str, Any]:
    quantile_columns = _coerce_quantile_columns(frame)
    quantile_predictions = {
        quantile: frame[column].to_numpy(dtype=float)
        for quantile, column in quantile_columns.items()
    }
    baseline_quantiles = {
        quantile: frame[f"{baseline_prefix}{column}"].to_numpy(dtype=float)
        for quantile, column in quantile_columns.items()
        if f"{baseline_prefix}{column}" in frame.columns
    }
    return summarize_probabilistic_metrics(
        y_true=frame[y_true_col].to_numpy(dtype=float),
        quantile_predictions=quantile_predictions,
        baseline_quantiles=baseline_quantiles or None,
        event_labels=frame[event_label_col].to_numpy(dtype=int) if event_label_col in frame.columns else None,
        event_probabilities=(
            frame[event_probability_col].to_numpy(dtype=float)
            if event_probability_col in frame.columns
            else None
        ),
        action_threshold=action_threshold,
    )
