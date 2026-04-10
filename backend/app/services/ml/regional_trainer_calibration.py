from __future__ import annotations

from typing import Any


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

    calibration = trainer._fit_isotonic(
        fit_df[raw_probability_col].to_numpy(),
        fit_df[label_col].to_numpy(),
    )
    if calibration is None:
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
    if (
        calibrated_metrics["brier_score"] <= raw_metrics["brier_score"] + calibration_guard_epsilon
        and calibrated_metrics["ece"] <= raw_metrics["ece"] + calibration_guard_epsilon
        and calibrated_metrics["precision_at_top3"] + calibration_guard_epsilon
        >= raw_metrics["precision_at_top3"]
        and calibrated_metrics["activation_false_positive_rate"]
        <= raw_metrics["activation_false_positive_rate"] + calibration_guard_epsilon
    ):
        return calibration, "isotonic_guarded"
    return None, "raw_passthrough"
