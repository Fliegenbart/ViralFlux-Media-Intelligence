from __future__ import annotations

from typing import Any


def finalize_training_frame(
    df: Any,
    *,
    leakage_safe_warmup_rows: int,
    np_module: Any,
) -> Any:
    cleaned = df.copy()
    cleaned = cleaned.sort_values("ds").reset_index(drop=True)
    cleaned = cleaned.replace([np_module.inf, -np_module.inf], np_module.nan)

    held_signal_cols = [
        "trends_score",
        "schulferien",
        "amelag_pred",
        "xd_load",
        "survstat_incidence",
        "lab_positivity_rate",
        "lab_signal_available",
        "lab_baseline_mean",
        "lab_baseline_zscore",
    ]
    for col in held_signal_cols:
        if col in cleaned.columns:
            cleaned[col] = cleaned[col].ffill()

    if len(cleaned) > leakage_safe_warmup_rows:
        cleaned = cleaned.iloc[leakage_safe_warmup_rows:].copy()

    cleaned = cleaned.fillna(0.0).reset_index(drop=True)
    return cleaned


def build_meta_feature_row(
    last_row: Any,
    *,
    hw_pred: float,
    ridge_pred: float,
    prophet_pred: float,
) -> dict[str, float]:
    return {
        "hw_pred": float(hw_pred),
        "ridge_pred": float(ridge_pred),
        "prophet_pred": float(prophet_pred),
        "amelag_lag4": float(last_row.get("amelag_lag4", 0.0)),
        "amelag_lag7": float(last_row.get("amelag_lag7", 0.0)),
        "trend_momentum_7d": float(last_row.get("trend_momentum_7d", 0.0)),
        "schulferien": float(last_row.get("schulferien", 0.0)),
        "trends_score": float(last_row.get("trends_score", 0.0)),
        "xdisease_lag7": float(last_row.get("xdisease_lag7", 0.0)),
        "xdisease_lag14": float(last_row.get("xdisease_lag14", 0.0)),
        "survstat_incidence": float(last_row.get("survstat_incidence", 0.0)),
        "survstat_lag7": float(last_row.get("survstat_lag7", 0.0)),
        "survstat_lag14": float(last_row.get("survstat_lag14", 0.0)),
        "lab_positivity_rate": float(last_row.get("lab_positivity_rate", 0.0)),
        "lab_signal_available": float(last_row.get("lab_signal_available", 0.0)),
        "lab_baseline_mean": float(last_row.get("lab_baseline_mean", 0.0)),
        "lab_baseline_zscore": float(last_row.get("lab_baseline_zscore", 0.0)),
        "lab_positivity_lag7": float(last_row.get("lab_positivity_lag7", 0.0)),
    }


def direct_ridge_feature_columns(frame: Any, *, ridge_direct_features: list[str]) -> list[str]:
    return [column for column in ridge_direct_features if column in frame.columns]


def event_feature_columns(frame: Any, *, meta_features: list[str]) -> list[str]:
    columns: list[str] = []
    if "current_y" in frame.columns:
        columns.append("current_y")
    for name in meta_features:
        if name in frame.columns and name not in columns:
            columns.append(name)
    if "horizon_days" in frame.columns and "horizon_days" not in columns:
        columns.append("horizon_days")
    return columns


def build_live_event_feature_row(
    *,
    raw: Any,
    live_feature_row: dict[str, float],
    horizon_days: int,
) -> dict[str, float]:
    feature_row = dict(live_feature_row)
    feature_row["current_y"] = float(raw["y"].iloc[-1]) if not raw.empty else 0.0
    feature_row["horizon_days"] = float(horizon_days)
    return feature_row


def event_model_candidates() -> list[str]:
    candidates = ["logistic_regression"]
    try:
        from xgboost import XGBClassifier  # noqa: F401

        candidates.append("xgb_classifier")
    except Exception:
        pass
    return candidates
