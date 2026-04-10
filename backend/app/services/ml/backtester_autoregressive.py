"""Autoregressive SURVSTAT helpers for BacktestService."""

from __future__ import annotations

import math

import numpy as np


def build_survstat_ar_row(
    *,
    series,
    idx: int,
    target_date,
    xgboost_survstat_features: list[str],
) -> dict[str, float]:
    """Baut einen einzelnen Feature-Vektor aus der SURVSTAT-Zeitreihe."""
    _ = xgboost_survstat_features
    n = len(series)

    def lag(k: int) -> float:
        i = idx - k
        return float(series.iloc[i]) if 0 <= i < n else 0.0

    y_lag1 = lag(1)
    y_lag2 = lag(2)
    y_lag4 = lag(4)
    y_lag8 = lag(8)
    y_lag52 = lag(52)

    window4 = [float(series.iloc[idx - j]) for j in range(1, 5) if 0 <= idx - j < n]
    window8 = [float(series.iloc[idx - j]) for j in range(1, 9) if 0 <= idx - j < n]
    y_roll4_mean = float(np.mean(window4)) if window4 else 0.0
    y_roll4_std = float(np.std(window4)) if len(window4) >= 2 else 0.0
    y_roll8_mean = float(np.mean(window8)) if window8 else 0.0

    y_roc1 = (y_lag1 - lag(2)) / max(lag(2), 1e-6) if lag(2) > 0 else 0.0
    y_roc4 = (y_lag1 - lag(5)) / max(lag(5), 1e-6) if lag(5) > 0 else 0.0

    iso_week = target_date.isocalendar()[1]
    week_sin = round(math.sin(2 * math.pi * iso_week / 52), 4)
    week_cos = round(math.cos(2 * math.pi * iso_week / 52), 4)

    all_vals = [float(series.iloc[j]) for j in range(max(0, idx - 52), idx) if j < n]
    median_val = float(np.median(all_vals)) if all_vals else 1.0
    y_level = y_lag1 / max(median_val, 1e-6)

    return {
        "y_lag1": y_lag1,
        "y_lag2": y_lag2,
        "y_lag4": y_lag4,
        "y_lag8": y_lag8,
        "y_lag52": y_lag52,
        "y_roll4_mean": y_roll4_mean,
        "y_roll4_std": y_roll4_std,
        "y_roll8_mean": y_roll8_mean,
        "y_roc1": y_roc1,
        "y_roc4": y_roc4,
        "week_sin": week_sin,
        "week_cos": week_cos,
        "y_level": y_level,
    }


def build_survstat_ar_training_data(
    train_df,
    *,
    xgboost_survstat_features: list[str],
    build_survstat_ar_row_fn,
):
    """Baut X/y aus SURVSTAT train_df für XGBoost."""
    series = train_df["menge"].reset_index(drop=True)
    dates = train_df["datum"].reset_index(drop=True)
    n = len(series)
    min_idx = min(52, n - 1)

    rows = []
    targets = []
    for i in range(max(min_idx, 1), n):
        feat = build_survstat_ar_row_fn(
            series=series,
            idx=i,
            target_date=dates.iloc[i],
        )
        rows.append([feat[c] for c in xgboost_survstat_features])
        targets.append(float(series.iloc[i]))

    if not rows:
        return np.empty((0, len(xgboost_survstat_features))), np.empty(0)

    X = np.array(rows, dtype=float)
    y = np.array(targets, dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X, y
