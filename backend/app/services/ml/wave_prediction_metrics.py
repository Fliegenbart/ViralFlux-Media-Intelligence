"""Calibration, threshold, and summary helpers for wave prediction."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression


def fit_calibration(
    *,
    classifier: Any,
    calibration_frame: Any,
    feature_columns: list[str],
    np_module: Any,
) -> IsotonicRegression | None:
    x_cal = calibration_frame[feature_columns].fillna(0.0).to_numpy(dtype=float)
    y_cal = calibration_frame["target_wave14"].astype(int).to_numpy()
    if len(np_module.unique(y_cal)) < 2:
        return None
    raw_scores = classifier.predict_proba(x_cal)[:, 1]
    calibration = IsotonicRegression(out_of_bounds="clip")
    calibration.fit(raw_scores, y_cal)
    return calibration


def apply_calibration(
    calibration: IsotonicRegression | None,
    raw_scores: np.ndarray,
    *,
    np_module: Any,
) -> np.ndarray:
    if calibration is None:
        return raw_scores.astype(float)
    return np_module.clip(np_module.asarray(calibration.predict(raw_scores), dtype=float), 0.0, 1.0)


def select_classification_threshold(
    y_true: np.ndarray,
    score_values: np.ndarray,
    *,
    default_threshold: float,
    precision_score_fn: Any,
    recall_score_fn: Any,
    f1_score_fn: Any,
    false_alarm_rate_fn: Any,
    np_module: Any,
) -> float:
    labels = np_module.asarray(y_true, dtype=int)
    scores = np_module.clip(np_module.asarray(score_values, dtype=float), 0.0, 1.0)
    if len(scores) == 0 or len(np_module.unique(labels)) < 2:
        return float(default_threshold)

    candidates = {
        float(np_module.clip(default_threshold, 0.0, 1.0)),
        0.0,
        1.0,
        *[float(value) for value in np_module.unique(np_module.round(scores, 6))],
    }
    best_key = None
    best_threshold = float(default_threshold)
    for threshold in sorted(candidates):
        predictions = (scores >= threshold).astype(int)
        precision = float(precision_score_fn(labels, predictions, zero_division=0))
        recall = float(recall_score_fn(labels, predictions, zero_division=0))
        f1 = float(f1_score_fn(labels, predictions, zero_division=0))
        far = false_alarm_rate_fn(labels, predictions)
        candidate = (
            round(f1, 12),
            round(precision, 12),
            round(recall, 12),
            -round(far if far is not None else 1.0, 12),
            round(threshold, 12),
        )
        if best_key is None or candidate > best_key:
            best_key = candidate
            best_threshold = float(threshold)
    return best_threshold


def resolve_decision_strategy(
    service: Any,
    *,
    y_true: np.ndarray,
    raw_scores: np.ndarray,
    calibration: IsotonicRegression | None,
    default_threshold: float,
    f1_score_fn: Any,
    brier_score_loss_fn: Any,
    np_module: Any,
) -> dict[str, Any]:
    labels = np_module.asarray(y_true, dtype=int)
    raw = np_module.clip(np_module.asarray(raw_scores, dtype=float), 0.0, 1.0)
    raw_threshold = service._select_classification_threshold(
        labels,
        raw,
        default_threshold=default_threshold,
    )
    raw_predictions = (raw >= raw_threshold).astype(int)
    raw_f1 = float(f1_score_fn(labels, raw_predictions, zero_division=0))
    notes: list[str] = []

    if calibration is None:
        if abs(raw_threshold - float(default_threshold)) > 1e-6:
            notes.append(
                f"Classification threshold tuned on holdout window: {raw_threshold:.3f}."
            )
        return {
            "use_calibration": False,
            "threshold": raw_threshold,
            "notes": notes,
        }

    calibrated = service._apply_calibration(calibration, raw)
    calibrated_threshold = service._select_classification_threshold(
        labels,
        calibrated,
        default_threshold=default_threshold,
    )
    calibrated_predictions = (calibrated >= calibrated_threshold).astype(int)
    calibrated_f1 = float(f1_score_fn(labels, calibrated_predictions, zero_division=0))
    raw_brier = float(brier_score_loss_fn(labels, raw))
    calibrated_brier = float(brier_score_loss_fn(labels, calibrated))

    if calibrated_brier <= raw_brier + 1e-6 and calibrated_f1 >= raw_f1 - 1e-6:
        if abs(calibrated_threshold - float(default_threshold)) > 1e-6:
            notes.append(
                f"Classification threshold tuned on calibrated holdout scores: {calibrated_threshold:.3f}."
            )
        return {
            "use_calibration": True,
            "threshold": calibrated_threshold,
            "notes": notes,
        }

    notes.append(
        "Calibration skipped; isotonic mapping degraded holdout decision quality."
    )
    if abs(raw_threshold - float(default_threshold)) > 1e-6:
        notes.append(
            f"Classification threshold tuned on holdout window: {raw_threshold:.3f}."
        )
    return {
        "use_calibration": False,
        "threshold": raw_threshold,
        "notes": notes,
    }


def compute_calibration_summary(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    from app.services.ml.regional_panel_utils import compute_ece

    return float(compute_ece(y_true, probabilities))


def aggregate_fold_metrics(folds: list[dict[str, Any]], *, np_module: Any) -> dict[str, Any]:
    if not folds:
        return {}
    numeric_keys = [
        "mae",
        "rmse",
        "mape",
        "roc_auc",
        "pr_auc",
        "brier_score",
        "precision",
        "recall",
        "f1",
        "ece",
        "false_alarm_rate",
        "mean_lead_time_days",
    ]
    aggregate: dict[str, Any] = {"fold_count": len(folds)}
    for key in numeric_keys:
        values = [float(item[key]) for item in folds if item.get(key) is not None]
        aggregate[key] = float(np_module.mean(values)) if values else None
    count_keys = ["rows", "positive_rows", "tp", "fp", "tn", "fn"]
    for key in count_keys:
        aggregate[key] = int(sum(int(item.get(key) or 0) for item in folds))
    aggregate["probability_output_folds"] = int(sum(1 for item in folds if item.get("probability_output")))
    aggregate["confusion_matrix"] = {
        "tp": aggregate["tp"],
        "fp": aggregate["fp"],
        "tn": aggregate["tn"],
        "fn": aggregate["fn"],
    }
    return aggregate


def dataset_manifest(panel: Any) -> dict[str, Any]:
    source_coverage = {
        column: round(float(panel[column].mean()), 4)
        for column in panel.columns
        if column.endswith("_available")
    }
    return {
        "rows": int(len(panel)),
        "pathogens": sorted(str(value) for value in panel["pathogen"].dropna().unique()),
        "regions": sorted(str(value) for value in panel["region"].dropna().unique()),
        "date_range": {
            "start": str(panel["as_of_date"].min()),
            "end": str(panel["as_of_date"].max()),
        },
        "source_coverage": source_coverage,
    }
