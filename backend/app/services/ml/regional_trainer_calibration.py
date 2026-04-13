from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Sequence

import numpy as np
from app.services.ml.forecast_horizon_utils import fit_platt_calibrator


def _clip_probabilities(raw_probabilities: Sequence[float]) -> np.ndarray:
    return np.clip(np.asarray(raw_probabilities, dtype=float), 0.001, 0.999)


def _format_decimal_token(value: float) -> str:
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


@dataclass(frozen=True)
class LogitTemperatureCalibration:
    temperature: float

    def predict(self, raw_probabilities: Sequence[float]) -> np.ndarray:
        probabilities = _clip_probabilities(raw_probabilities)
        logits = np.log(probabilities / (1.0 - probabilities))
        scaled = logits / max(float(self.temperature), 0.05)
        return 1.0 / (1.0 + np.exp(-scaled))


@dataclass(frozen=True)
class ShrinkageBlendCalibration:
    alpha: float
    prior: float

    def predict(self, raw_probabilities: Sequence[float]) -> np.ndarray:
        probabilities = _clip_probabilities(raw_probabilities)
        alpha = max(0.0, min(1.0, float(self.alpha)))
        return np.clip(((1.0 - alpha) * probabilities) + (alpha * float(self.prior)), 0.001, 0.999)


@dataclass(frozen=True)
class QuantileSmoothingCalibration:
    edges: tuple[float, ...]
    values: tuple[float, ...]

    def predict(self, raw_probabilities: Sequence[float]) -> np.ndarray:
        probabilities = _clip_probabilities(raw_probabilities)
        if len(self.edges) < 2 or not self.values:
            return probabilities
        bucket_ids = np.digitize(probabilities, np.asarray(self.edges[1:-1], dtype=float), right=True)
        bucket_values = np.asarray(self.values, dtype=float)
        return np.clip(bucket_values[np.clip(bucket_ids, 0, len(bucket_values) - 1)], 0.001, 0.999)


def _fit_quantile_smoothing(
    *,
    raw_probabilities: Sequence[float],
    labels: Sequence[int],
    quantile_bins: int = 8,
    smoothing: float = 4.0,
) -> QuantileSmoothingCalibration | None:
    probabilities = _clip_probabilities(raw_probabilities)
    y_true = np.asarray(labels, dtype=int)
    if len(probabilities) < 20 or len(np.unique(y_true)) < 2:
        return None

    bin_count = max(3, int(quantile_bins))
    quantiles = np.linspace(0.0, 1.0, bin_count + 1)
    edges = np.quantile(probabilities, quantiles)
    edges[0] = 0.0
    edges[-1] = 1.0
    unique_edges = np.unique(edges)
    if len(unique_edges) < 3:
        return None

    bucket_ids = np.digitize(probabilities, unique_edges[1:-1], right=True)
    global_rate = float(np.mean(y_true.astype(float)))
    values: list[float] = []
    for bucket in range(len(unique_edges) - 1):
        mask = bucket_ids == bucket
        count = int(np.sum(mask))
        positives = int(np.sum(y_true[mask]))
        smoothed = (
            (positives + (float(smoothing) * global_rate))
            / max(float(count) + float(smoothing), 1.0)
        )
        values.append(smoothed)
    monotone_values = np.maximum.accumulate(np.asarray(values, dtype=float))
    return QuantileSmoothingCalibration(
        edges=tuple(float(value) for value in unique_edges.tolist()),
        values=tuple(float(value) for value in np.clip(monotone_values, 0.001, 0.999).tolist()),
    )


def _extra_guarded_calibration_candidates(
    *,
    raw_probabilities: Sequence[float],
    labels: Sequence[int],
) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    for temperature in (1.1, 1.25, 1.5, 1.75, 2.0):
        if np.isclose(float(temperature), 1.0):
            continue
        candidates.append(
            (
                f"logit_temp_guarded_t{_format_decimal_token(float(temperature))}",
                LogitTemperatureCalibration(temperature=float(temperature)),
            )
        )
    prior = float(np.mean(np.asarray(labels, dtype=float))) if len(labels) else 0.0
    for alpha in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3):
        candidates.append(
            (
                f"shrinkage_guarded_a{_format_decimal_token(float(alpha))}",
                ShrinkageBlendCalibration(alpha=float(alpha), prior=prior),
            )
        )
    quantile_smoothing = _fit_quantile_smoothing(
        raw_probabilities=raw_probabilities,
        labels=labels,
        quantile_bins=8,
        smoothing=4.0,
    )
    if quantile_smoothing is not None:
        candidates.append(("quantile_smooth_guarded_q8_s4", quantile_smoothing))
    return candidates


def calibration_guard_metrics(
    *,
    as_of_dates: Any,
    labels,
    probabilities,
    action_threshold: float,
    apply_calibration_fn,
    pd_module,
    np_module,
    brier_score_safe_fn,
    compute_ece_fn,
    precision_at_k_fn,
    activation_false_positive_rate_fn,
) -> dict[str, float]:
    clipped = apply_calibration_fn(None, np_module.asarray(probabilities, dtype=float))
    guard_frame = pd_module.DataFrame(
        {
            "as_of_date": pd_module.to_datetime(as_of_dates).normalize(),
            "event_label": np_module.asarray(labels, dtype=int),
            "guard_probability": clipped,
            "action_threshold": np_module.full(len(clipped), float(action_threshold), dtype=float),
        }
    )
    return {
        "brier_score": float(brier_score_safe_fn(guard_frame["event_label"], clipped)),
        "ece": float(compute_ece_fn(guard_frame["event_label"], clipped)),
        "precision_at_top3": float(
            precision_at_k_fn(
                guard_frame,
                k=3,
                score_col="guard_probability",
            )
        ),
        "activation_false_positive_rate": float(
            activation_false_positive_rate_fn(
                guard_frame,
                threshold=None,
                score_col="guard_probability",
            )
        ),
    }


def select_guarded_calibration(
    trainer,
    *,
    calibration_frame,
    raw_probability_col: str,
    action_threshold: float | None = None,
    min_recall_for_threshold: float = 0.35,
    label_col: str = "event_label",
    date_col: str = "as_of_date",
    calibration_guard_epsilon: float,
    choose_action_threshold_fn,
) -> tuple[Any | None, str]:
    if calibration_frame.empty:
        return None, "raw_passthrough"

    working = calibration_frame[[date_col, label_col, raw_probability_col]].copy()
    working[date_col] = trainer.pd.to_datetime(working[date_col]).dt.normalize() if hasattr(trainer, "pd") else working[date_col]
    # Keep using trainer hooks so older tests and patches still work.
    import pandas as pd

    working[date_col] = pd.to_datetime(working[date_col]).dt.normalize()

    guard_split = trainer._calibration_guard_split_dates(working[date_col].tolist())
    if not guard_split:
        return None, "raw_passthrough"
    fit_dates, guard_dates = guard_split
    fit_df = working.loc[working[date_col].isin(fit_dates)].copy()
    guard_df = working.loc[working[date_col].isin(guard_dates)].copy()
    if fit_df.empty or guard_df.empty:
        return None, "raw_passthrough"

    guard_labels = guard_df[label_col].to_numpy(dtype=int)
    raw_guard = trainer._apply_calibration(None, guard_df[raw_probability_col].to_numpy())
    effective_threshold = float(action_threshold) if action_threshold is not None else float(
        choose_action_threshold_fn(
            raw_guard,
            guard_labels,
            min_recall=min_recall_for_threshold,
        )[0]
    )
    raw_metrics = trainer._calibration_guard_metrics(
        as_of_dates=guard_df[date_col].to_numpy(),
        labels=guard_labels,
        probabilities=raw_guard,
        action_threshold=effective_threshold,
    )
    candidate_payloads: list[tuple[str, Any]] = []
    isotonic = trainer._fit_isotonic(
        fit_df[raw_probability_col].to_numpy(),
        fit_df[label_col].to_numpy(),
    )
    if isotonic is not None:
        candidate_payloads.append(("isotonic_guarded", isotonic))
    platt = trainer._fit_platt(
        fit_df[raw_probability_col].to_numpy(),
        fit_df[label_col].to_numpy(),
    )
    if platt is not None:
        candidate_payloads.append(("platt_guarded", platt))
    candidate_payloads.extend(
        _extra_guarded_calibration_candidates(
            raw_probabilities=fit_df[raw_probability_col].to_numpy(dtype=float),
            labels=fit_df[label_col].to_numpy(dtype=int),
        )
    )

    best_mode: str | None = None
    best_calibration: Any | None = None
    best_key: tuple[float, float, float, float, str] | None = None
    for mode, calibration in candidate_payloads:
        calibrated_guard = trainer._apply_calibration(
            calibration,
            guard_df[raw_probability_col].to_numpy(),
        )
        calibrated_metrics = trainer._calibration_guard_metrics(
            as_of_dates=guard_df[date_col].to_numpy(),
            labels=guard_labels,
            probabilities=calibrated_guard,
            action_threshold=effective_threshold,
        )
        if not (
            calibrated_metrics["brier_score"] <= raw_metrics["brier_score"] + calibration_guard_epsilon
            and calibrated_metrics["ece"] <= raw_metrics["ece"] + calibration_guard_epsilon
            and calibrated_metrics["precision_at_top3"] + calibration_guard_epsilon
            >= raw_metrics["precision_at_top3"]
            and calibrated_metrics["activation_false_positive_rate"]
            <= raw_metrics["activation_false_positive_rate"] + calibration_guard_epsilon
        ):
            continue
        candidate_key = (
            float(calibrated_metrics["ece"]),
            float(calibrated_metrics["brier_score"]),
            -float(calibrated_metrics["precision_at_top3"]),
            float(calibrated_metrics["activation_false_positive_rate"]),
            mode,
        )
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best_mode = mode
            best_calibration = calibration

    if best_calibration is not None and best_mode is not None:
        return best_calibration, best_mode
    return None, "raw_passthrough"
