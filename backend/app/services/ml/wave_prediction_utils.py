"""Utility helpers for the stage-1 wave prediction service."""

from __future__ import annotations

import json
import math
import os
import pickle
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from app.services.ml.regional_panel_utils import compute_ece, seasonal_baseline_and_mad, time_based_panel_splits

LAG_DAYS: tuple[int, ...] = (1, 2, 3, 7, 14, 21, 28)
ROLLING_WINDOWS: tuple[int, ...] = (3, 7, 14)
WAVE_LABEL_VERSION = "wave_label_v1"

NON_FEATURE_COLUMNS: set[str] = {
    "as_of_date",
    "generated_at",
    "region",
    "region_name",
    "pathogen",
    "pathogen_slug",
    "target_date",
    "target_week_start",
    "target_window_end",
    "target_regression",
    "target_regression_log",
    "target_wave14",
    "wave_event_date",
    "wave_event_reason",
    "truth_source",
    "source_truth_week_start",
    "source_truth_available_date",
    "future_truth_max",
    "future_truth_growth_ratio",
    "horizon_days",
    "model_version",
}


@dataclass(frozen=True)
class WaveLabelConfig:
    """Configurable ruleset for the stage-1 wave-start label."""

    absolute_threshold: float
    seasonal_zscore_threshold: float
    growth_observations: int
    growth_min_relative_increase: float
    mad_floor: float = 1.0
    version: str = WAVE_LABEL_VERSION

    def to_manifest(self) -> dict[str, float | int | str]:
        return asdict(self)


PATHOGEN_LABEL_OVERRIDES: dict[str, dict[str, float | int]] = {
    "SARS-CoV-2": {
        "absolute_threshold": 5.0,
        "seasonal_zscore_threshold": 1.0,
    },
    "RSV A": {
        "absolute_threshold": 7.5,
    },
}


def wave_label_config_for_pathogen(pathogen: str, settings: Any) -> WaveLabelConfig:
    """Return the pathogen-specific label configuration seeded from settings."""

    config = WaveLabelConfig(
        absolute_threshold=float(getattr(settings, "WAVE_PREDICTION_LABEL_ABSOLUTE_THRESHOLD", 10.0)),
        seasonal_zscore_threshold=float(getattr(settings, "WAVE_PREDICTION_LABEL_SEASONAL_ZSCORE", 1.5)),
        growth_observations=max(int(getattr(settings, "WAVE_PREDICTION_LABEL_GROWTH_OBSERVATIONS", 2)), 2),
        growth_min_relative_increase=float(
            getattr(settings, "WAVE_PREDICTION_LABEL_GROWTH_MIN_RELATIVE_INCREASE", 0.2)
        ),
        mad_floor=max(float(getattr(settings, "WAVE_PREDICTION_LABEL_MAD_FLOOR", 1.0)), 1.0),
    )
    overrides = PATHOGEN_LABEL_OVERRIDES.get(pathogen)
    if not overrides:
        return config
    return replace(config, **overrides)


def label_wave_start(
    future_truth: pd.DataFrame,
    historical_truth: pd.DataFrame,
    config: WaveLabelConfig,
) -> tuple[int, pd.Timestamp | None]:
    """Label whether a wave starts in the future window.

    Epidemiological intuition:
    - absolute threshold catches clinically relevant jumps even in flat seasons
    - seasonal z-score catches unusual activity relative to the usual week-of-year level
    - sustained growth catches early ramps before the absolute burden is high
    """

    future = _coerce_wave_frame(future_truth)
    history = _coerce_wave_frame(historical_truth)
    if future.empty:
        return 0, None

    for row in future.itertuples(index=False):
        baseline, mad = _seasonal_baseline_for_target(history, row.datum)
        if row.value >= float(config.absolute_threshold):
            return 1, pd.Timestamp(row.datum)
        zscore = float(row.value - baseline) / max(float(mad), float(config.mad_floor))
        if zscore >= float(config.seasonal_zscore_threshold):
            return 1, pd.Timestamp(row.datum)

    growth_event = _detect_sustained_growth(future, config)
    if growth_event is not None:
        return 1, growth_event
    return 0, None


def build_daily_signal_features(
    frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    prefix: str,
    date_col: str = "datum",
    value_col: str = "value",
    lags: Sequence[int] = LAG_DAYS,
    rolling_windows: Sequence[int] = ROLLING_WINDOWS,
    lookback_days: int = 35,
) -> dict[str, float]:
    """Create leakage-safe daily features from a signal visible as of ``as_of``."""

    features: dict[str, float] = {f"{prefix}_available": 0.0}
    history = _daily_visible_series(
        frame,
        as_of=as_of,
        date_col=date_col,
        value_col=value_col,
        lookback_days=max(int(lookback_days), 28),
    )

    if history.empty:
        features.update(_empty_signal_feature_family(prefix, lags=lags))
        return features

    values = history["value"].astype(float)
    current = float(values.iloc[-1])
    recent_28 = values.tail(28)
    recent_mean = float(recent_28.mean()) if not recent_28.empty else 0.0
    recent_std = float(recent_28.std(ddof=0) or 0.0)
    features[f"{prefix}_available"] = 1.0
    features[f"{prefix}_level"] = current
    features[f"{prefix}_days_since_last_observation"] = float((as_of - history["source_date"].iloc[-1]).days)
    features[f"{prefix}_observation_count_28"] = float(history["source_date"].tail(28).nunique())
    features[f"{prefix}_zscore_28"] = float((current - recent_mean) / max(recent_std, 1.0))

    for lag in lags:
        features[f"{prefix}_lag_{lag}"] = _series_lag(values, lag)

    for window in rolling_windows:
        tail = values.tail(window)
        features[f"{prefix}_rolling_mean_{window}"] = float(tail.mean() or 0.0)
        if window in (7, 14):
            features[f"{prefix}_rolling_std_{window}"] = float(tail.std(ddof=0) or 0.0)
        if window == 14:
            features[f"{prefix}_rolling_min_{window}"] = float(tail.min() or 0.0)
            features[f"{prefix}_rolling_max_{window}"] = float(tail.max() or 0.0)

    lag7 = features[f"{prefix}_lag_7"]
    lag14 = features[f"{prefix}_lag_14"]
    features[f"{prefix}_pct_change_7"] = _relative_change(current, lag7)
    features[f"{prefix}_pct_change_14"] = _relative_change(current, lag14)
    features[f"{prefix}_slope_7"] = _window_slope(values.tail(7))
    features[f"{prefix}_slope_14"] = _window_slope(values.tail(14))
    features[f"{prefix}_acceleration"] = features[f"{prefix}_slope_7"] - features[f"{prefix}_slope_14"]
    features[f"{prefix}_distance_to_recent_peak"] = float(current - (recent_28.max() if not recent_28.empty else current))
    features[f"{prefix}_distance_to_recent_trough"] = float(current - (recent_28.min() if not recent_28.empty else current))
    return features


def school_holiday_features(
    holiday_ranges: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
    *,
    as_of: pd.Timestamp,
    horizon_days: int,
) -> dict[str, float]:
    ranges = [(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()) for start, end in holiday_ranges]
    is_holiday = any(start <= as_of <= end for start, end in ranges)

    future_starts = [(start - as_of).days for start, _ in ranges if start > as_of]
    past_ends = [(as_of - end).days for _, end in ranges if end < as_of]

    window_days = [as_of + pd.Timedelta(days=offset) for offset in range(1, max(int(horizon_days), 1) + 1)]
    overlap_hits = 0
    for day in window_days:
        if any(start <= day.normalize() <= end for start, end in ranges):
            overlap_hits += 1

    return {
        "is_school_holiday": float(is_holiday),
        "days_until_next_holiday_start": float(min(future_starts) if future_starts else horizon_days + 1),
        "days_since_holiday_end": float(min(past_ends) if past_ends else horizon_days + 1),
        "holiday_overlap_ratio_next_14d": float(overlap_hits / len(window_days)) if window_days else 0.0,
    }


def weather_context_features(
    weather_frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    enable_forecast_weather: bool,
) -> dict[str, float]:
    base = {
        "weather_available": 0.0,
        "avg_temp_7": 0.0,
        "avg_humidity_7": 0.0,
        "min_temp_7": 0.0,
        "max_temp_7": 0.0,
        "weather_forecast_avg_temp_next_7": 0.0,
        "weather_forecast_avg_humidity_next_7": 0.0,
    }
    if weather_frame is None or weather_frame.empty:
        return base

    frame = weather_frame.copy()
    frame["datum"] = pd.to_datetime(frame["datum"]).dt.normalize()
    if "available_time" in frame.columns:
        frame["available_time"] = pd.to_datetime(frame["available_time"])
        frame = frame.loc[frame["available_time"] <= as_of].copy()
    if frame.empty:
        return base

    observed = frame.loc[
        frame["data_type"].isin(["CURRENT", "DAILY_OBSERVATION"]) & (frame["datum"] <= as_of)
    ].sort_values("datum")
    if observed.empty:
        return base

    observed_window = observed.tail(7)
    base["weather_available"] = 1.0
    base["avg_temp_7"] = float(observed_window["temp"].mean() or 0.0)
    base["avg_humidity_7"] = float(observed_window["humidity"].mean() or 0.0)
    base["min_temp_7"] = float(observed_window["temp"].min() or 0.0)
    base["max_temp_7"] = float(observed_window["temp"].max() or 0.0)

    if not enable_forecast_weather:
        return base

    forecast = frame.loc[
        frame["data_type"].isin(["DAILY_FORECAST", "HOURLY_FORECAST"])
        & (frame["datum"] > as_of)
        & (frame["datum"] <= as_of + pd.Timedelta(days=7))
    ]
    if forecast.empty:
        base["weather_forecast_avg_temp_next_7"] = base["avg_temp_7"]
        base["weather_forecast_avg_humidity_next_7"] = base["avg_humidity_7"]
        return base

    base["weather_forecast_avg_temp_next_7"] = float(forecast["temp"].mean() or base["avg_temp_7"])
    base["weather_forecast_avg_humidity_next_7"] = float(
        forecast["humidity"].mean() or base["avg_humidity_7"]
    )
    return base


def get_regression_feature_columns(df: pd.DataFrame) -> list[str]:
    return _feature_columns(df)


def get_classification_feature_columns(df: pd.DataFrame) -> list[str]:
    return _feature_columns(df)


def safe_mape(y_true: Sequence[float], y_pred: Sequence[float]) -> float | None:
    truth = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    mask = np.abs(truth) >= 1e-6
    if not np.any(mask):
        return None
    return float(np.mean(np.abs((truth[mask] - pred[mask]) / truth[mask])))


def safe_roc_auc(y_true: Sequence[int], scores: Sequence[float]) -> float | None:
    labels = np.asarray(y_true, dtype=int)
    values = np.asarray(scores, dtype=float)
    if len(np.unique(labels)) < 2:
        return None
    return float(roc_auc_score(labels, values))


def safe_pr_auc(y_true: Sequence[int], scores: Sequence[float]) -> float | None:
    labels = np.asarray(y_true, dtype=int)
    values = np.asarray(scores, dtype=float)
    if len(np.unique(labels)) < 2:
        return None
    return float(average_precision_score(labels, values))


def false_alarm_rate(y_true: Sequence[int], predictions: Sequence[int]) -> float | None:
    labels = np.asarray(y_true, dtype=int)
    preds = np.asarray(predictions, dtype=int)
    predicted_positive = preds == 1
    if not np.any(predicted_positive):
        return None
    false_alarms = np.sum((labels == 0) & predicted_positive)
    return float(false_alarms / np.sum(predicted_positive))


def mean_lead_time_days(
    as_of_dates: Sequence[pd.Timestamp],
    event_dates: Sequence[pd.Timestamp | None],
    labels: Sequence[int],
    predictions: Sequence[int],
) -> float | None:
    lead_times: list[float] = []
    for as_of, event_date, label, predicted in zip(as_of_dates, event_dates, labels, predictions):
        if int(label) != 1 or int(predicted) != 1 or event_date is None:
            continue
        lead_times.append(float((pd.Timestamp(event_date) - pd.Timestamp(as_of)).days))
    if not lead_times:
        return None
    return float(np.mean(lead_times))


def build_backtest_splits(
    dates: Sequence[pd.Timestamp],
    *,
    n_splits: int,
    min_train_periods: int,
    min_test_periods: int,
) -> list[tuple[list[pd.Timestamp], list[pd.Timestamp]]]:
    return time_based_panel_splits(
        list(pd.to_datetime(dates)),
        n_splits=int(n_splits),
        min_train_periods=int(min_train_periods),
        min_test_periods=int(min_test_periods),
    )


def top_feature_importance(
    *,
    classifier,
    regressor,
    feature_columns: Sequence[str],
    limit: int = 10,
) -> dict[str, float]:
    classifier_importance = getattr(classifier, "feature_importances_", np.zeros(len(feature_columns)))
    regressor_importance = getattr(regressor, "feature_importances_", np.zeros(len(feature_columns)))
    if len(classifier_importance) != len(feature_columns):
        classifier_importance = np.zeros(len(feature_columns))
    if len(regressor_importance) != len(feature_columns):
        regressor_importance = np.zeros(len(feature_columns))
    combined = 0.5 * np.asarray(classifier_importance, dtype=float) + 0.5 * np.asarray(regressor_importance, dtype=float)
    ranking = sorted(
        zip(feature_columns, combined, strict=False),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    return {
        str(name): round(float(score), 6)
        for name, score in ranking[: max(int(limit), 1)]
        if float(score) > 0.0
    }


def atomic_json_dump(payload: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp.json")
    os.close(fd)
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(json_safe(payload), handle, indent=2, ensure_ascii=True)
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def atomic_pickle_dump(payload: Any, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp.pkl")
    os.close(fd)
    try:
        with open(tmp_path, "wb") as handle:
            pickle.dump(payload, handle)
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _feature_columns(df: pd.DataFrame) -> list[str]:
    feature_columns: list[str] = []
    for column in df.columns:
        if column in NON_FEATURE_COLUMNS:
            continue
        if column.startswith("target_") or column.startswith("future_"):
            continue
        if column.endswith("_event_date") or column.endswith("_reason"):
            continue
        if not pd.api.types.is_numeric_dtype(df[column]):
            continue
        feature_columns.append(column)
    return sorted(feature_columns)


def _coerce_wave_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["datum", "value"])

    candidate_date_col = "week_start" if "week_start" in frame.columns else "datum"
    candidate_value_col = "incidence" if "incidence" in frame.columns else "value"
    coerced = frame[[candidate_date_col, candidate_value_col]].copy()
    coerced.columns = ["datum", "value"]
    coerced["datum"] = pd.to_datetime(coerced["datum"]).dt.normalize()
    coerced["value"] = coerced["value"].astype(float)
    return coerced.dropna(subset=["datum"]).sort_values("datum").reset_index(drop=True)


def _seasonal_baseline_for_target(history: pd.DataFrame, target_date: pd.Timestamp) -> tuple[float, float]:
    if history.empty:
        return 0.0, 1.0
    seasonal_frame = history.rename(columns={"datum": "week_start", "value": "incidence"})
    return seasonal_baseline_and_mad(seasonal_frame, pd.Timestamp(target_date))


def _detect_sustained_growth(frame: pd.DataFrame, config: WaveLabelConfig) -> pd.Timestamp | None:
    values = frame["value"].astype(float).to_numpy()
    dates = pd.to_datetime(frame["datum"]).to_numpy()
    window = max(int(config.growth_observations), 2)
    if len(values) < window:
        return None

    for start_idx in range(0, len(values) - window + 1):
        chunk = values[start_idx : start_idx + window]
        if not np.all(np.diff(chunk) > 0):
            continue
        growth_ratio = (chunk[-1] - chunk[0]) / max(abs(chunk[0]), 1.0)
        if growth_ratio >= float(config.growth_min_relative_increase):
            return pd.Timestamp(dates[start_idx])
    return None


def _daily_visible_series(
    frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    date_col: str,
    value_col: str,
    lookback_days: int,
) -> pd.DataFrame:
    if frame is None or frame.empty or date_col not in frame.columns or value_col not in frame.columns:
        return pd.DataFrame(columns=["datum", "value", "source_date"])

    visible = frame[[date_col, value_col]].copy()
    visible.columns = ["datum", "value"]
    visible["datum"] = pd.to_datetime(visible["datum"]).dt.normalize()
    visible["value"] = visible["value"].astype(float)
    visible = visible.loc[visible["datum"] <= as_of].sort_values("datum")
    if visible.empty:
        return pd.DataFrame(columns=["datum", "value", "source_date"])

    visible = visible.groupby("datum", as_index=False).last()
    index = pd.date_range(as_of - pd.Timedelta(days=max(int(lookback_days) - 1, 0)), as_of, freq="D")
    reindexed = visible.set_index("datum").reindex(index)
    reindexed["value"] = reindexed["value"].ffill()
    reindexed["source_date"] = reindexed.index.to_series().where(reindexed["value"].notna()).ffill()
    reindexed["value"] = reindexed["value"].fillna(0.0)
    reindexed["source_date"] = pd.to_datetime(reindexed["source_date"]).fillna(index[0])
    return (
        reindexed.reset_index()
        .rename(columns={"index": "datum"})
        .loc[:, ["datum", "value", "source_date"]]
    )


def _empty_signal_feature_family(prefix: str, *, lags: Sequence[int]) -> dict[str, float]:
    payload = {
        f"{prefix}_level": 0.0,
        f"{prefix}_days_since_last_observation": 999.0,
        f"{prefix}_observation_count_28": 0.0,
        f"{prefix}_zscore_28": 0.0,
        f"{prefix}_pct_change_7": 0.0,
        f"{prefix}_pct_change_14": 0.0,
        f"{prefix}_slope_7": 0.0,
        f"{prefix}_slope_14": 0.0,
        f"{prefix}_acceleration": 0.0,
        f"{prefix}_distance_to_recent_peak": 0.0,
        f"{prefix}_distance_to_recent_trough": 0.0,
        f"{prefix}_rolling_mean_3": 0.0,
        f"{prefix}_rolling_mean_7": 0.0,
        f"{prefix}_rolling_mean_14": 0.0,
        f"{prefix}_rolling_std_7": 0.0,
        f"{prefix}_rolling_std_14": 0.0,
        f"{prefix}_rolling_min_14": 0.0,
        f"{prefix}_rolling_max_14": 0.0,
    }
    for lag in lags:
        payload[f"{prefix}_lag_{lag}"] = 0.0
    return payload


def _series_lag(values: pd.Series, lag: int) -> float:
    if len(values) <= lag:
        return 0.0
    return float(values.iloc[-(lag + 1)])


def _relative_change(current: float, previous: float) -> float:
    return float((current - previous) / max(abs(previous), 1.0))


def _window_slope(values: pd.Series) -> float:
    if values is None or len(values) < 2:
        return 0.0
    xs = np.arange(len(values), dtype=float)
    ys = values.astype(float).to_numpy()
    slope, _ = np.polyfit(xs, ys, 1)
    return float(slope)
