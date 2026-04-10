from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.exogenous_feature_contracts import (
    EXOGENOUS_FEATURE_CONTRACTS,
    issue_time_forecast_rows,
    observed_as_of_only_rows,
)
from app.services.ml.forecast_horizon_utils import ensure_supported_horizon
from app.services.ml.regional_panel_utils import ALL_BUNDESLAENDER
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_ISSUE_TIME_SEMANTICS,
    WEATHER_FORECAST_RUN_IDENTITY_QUALITY_LEGACY,
    WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING,
    WEATHER_FORECAST_RUN_IDENTITY_SOURCE_LEGACY,
    WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING,
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
    normalize_weather_forecast_vintage_mode,
    select_weather_forecast_vintage_rows,
)


def _feature_virus_slug(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def relative_delta(current_value: float, previous_value: float) -> float:
    return float((current_value - previous_value) / max(abs(previous_value), 1.0))


def latest_value_as_of(frame: pd.DataFrame, as_of: pd.Timestamp, column: str) -> float:
    if frame is None or frame.empty or "datum" not in frame.columns or column not in frame.columns:
        return 0.0
    visible = frame.loc[frame["datum"] <= as_of]
    if visible.empty:
        return 0.0
    return float(visible.iloc[-1][column] or 0.0)


def window_mean(
    frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    window_days: int,
    column: str,
) -> float:
    if (
        frame is None
        or frame.empty
        or window_days <= 0
        or "datum" not in frame.columns
        or column not in frame.columns
    ):
        return 0.0
    window_start = as_of - pd.Timedelta(days=window_days - 1)
    visible = frame.loc[(frame["datum"] >= window_start) & (frame["datum"] <= as_of)]
    if visible.empty:
        return 0.0
    return float(visible[column].astype(float).mean() or 0.0)


def latest_truth_value(frame: pd.DataFrame, lag_weeks: int) -> float:
    if len(frame) <= lag_weeks:
        return 0.0
    return float(frame.iloc[-(lag_weeks + 1)]["incidence"] or 0.0)


def latest_wastewater_by_state(
    wastewater_by_state: dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
) -> dict[str, float]:
    latest: dict[str, float] = {}
    for state, frame in wastewater_by_state.items():
        visible = frame.loc[(frame["datum"] <= as_of) & (frame["available_time"] <= as_of)]
        if visible.empty:
            continue
        latest[state] = float(visible.iloc[-1]["viral_load"] or 0.0)
    return latest


def latest_wastewater_snapshot_by_state(
    wastewater_by_state: dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
) -> dict[str, dict[str, float]]:
    latest: dict[str, dict[str, float]] = {}
    for state, frame in wastewater_by_state.items():
        visible = frame.loc[(frame["datum"] <= as_of) & (frame["available_time"] <= as_of)]
        if visible.empty:
            continue
        latest_row = visible.iloc[-1]
        level = float(latest_row["viral_load"] or 0.0)
        lag7 = latest_value_as_of(visible, as_of - pd.Timedelta(days=7), "viral_load")
        lag14 = latest_value_as_of(visible, as_of - pd.Timedelta(days=14), "viral_load")
        slope7 = float((level - lag7) / max(abs(lag7), 1.0))
        slope14 = float((lag7 - lag14) / max(abs(lag14), 1.0))
        latest[state] = {
            "viral_load": level,
            "slope7d": slope7,
            "acceleration7d": float(slope7 - slope14),
        }
    return latest


def missing_days_in_window(frame: pd.DataFrame, as_of: pd.Timestamp, window_days: int) -> float:
    if window_days <= 0:
        return 0.0
    window_start = as_of - pd.Timedelta(days=window_days - 1)
    visible = frame.loc[(frame["datum"] >= window_start) & (frame["datum"] <= as_of)]
    observed_days = int(visible["datum"].nunique()) if not visible.empty else 0
    return float(max(window_days - observed_days, 0))


def cross_virus_features(
    *,
    target_virus: str,
    state: str,
    latest_cross_virus_snapshots: dict[str, dict[str, dict[str, float]]],
) -> dict[str, float]:
    features: dict[str, float] = {}
    for candidate_virus in SUPPORTED_VIRUS_TYPES:
        if candidate_virus == target_virus:
            continue
        slug = _feature_virus_slug(candidate_virus)
        snapshot = latest_cross_virus_snapshots.get(candidate_virus, {})
        state_metrics = snapshot.get(state, {})
        national_levels = [metrics["viral_load"] for metrics in snapshot.values()]
        national_slopes = [metrics["slope7d"] for metrics in snapshot.values()]
        state_level = float(state_metrics.get("viral_load") or 0.0)
        national_level = float(np.mean(national_levels)) if national_levels else 0.0
        features[f"xdisease_state_level_{slug}"] = state_level
        features[f"xdisease_state_slope7d_{slug}"] = float(state_metrics.get("slope7d") or 0.0)
        features[f"xdisease_national_level_{slug}"] = national_level
        features[f"xdisease_national_slope7d_{slug}"] = float(np.mean(national_slopes)) if national_slopes else 0.0
        features[f"xdisease_relative_level_{slug}"] = float(state_level - national_level)
    return features


def weather_features(
    weather_frame: pd.DataFrame | None,
    as_of: pd.Timestamp,
    *,
    horizon_days: int,
    vintage_mode: str = WEATHER_FORECAST_VINTAGE_DISABLED,
    vintage_metadata: dict[str, Any] | None = None,
) -> dict[str, float]:
    metadata = vintage_metadata if vintage_metadata is not None else {}
    metadata.setdefault(
        "weather_forecast_vintage_mode",
        normalize_weather_forecast_vintage_mode(vintage_mode),
    )
    metadata.setdefault(
        "weather_forecast_issue_time_semantics",
        WEATHER_FORECAST_ISSUE_TIME_SEMANTICS,
    )
    metadata.setdefault("weather_forecast_run_identity_present", False)
    metadata.setdefault(
        "weather_forecast_run_identity_source",
        WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING,
    )
    metadata.setdefault(
        "weather_forecast_run_identity_quality",
        WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING,
    )
    metadata.setdefault("weather_forecast_vintage_degraded", False)
    if weather_frame is None or weather_frame.empty:
        return {
            "weather_forecast_temp_3_7": 0.0,
            "weather_forecast_humidity_3_7": 0.0,
            "weather_temp_anomaly_3_7": 0.0,
            "weather_humidity_anomaly_3_7": 0.0,
        }

    visible = weather_frame.loc[weather_frame["available_time"] <= as_of].copy()
    observed = observed_as_of_only_rows(
        visible.loc[
            visible["data_type"].isin(["CURRENT", "DAILY_OBSERVATION"])
        ].copy(),
        as_of=as_of,
    )
    target = target_date(as_of, horizon_days)
    raw_forecast_candidates = visible.loc[
        (visible["data_type"] == "DAILY_FORECAST")
        & (visible["datum"] > as_of)
    ].copy()
    if not raw_forecast_candidates.empty:
        if "forecast_run_identity_source" in raw_forecast_candidates.columns:
            sources = sorted(
                {
                    str(value)
                    for value in raw_forecast_candidates["forecast_run_identity_source"].dropna().unique()
                }
            )
            if len(sources) == 1:
                metadata["weather_forecast_run_identity_source"] = sources[0]
            elif len(sources) > 1:
                metadata["weather_forecast_run_identity_source"] = "mixed"
        if "forecast_run_identity_quality" in raw_forecast_candidates.columns:
            qualities = sorted(
                {
                    str(value)
                    for value in raw_forecast_candidates["forecast_run_identity_quality"].dropna().unique()
                }
            )
            if len(qualities) == 1:
                metadata["weather_forecast_run_identity_quality"] = qualities[0]
            elif len(qualities) > 1:
                metadata["weather_forecast_run_identity_quality"] = "mixed"
    normalized_vintage_mode = normalize_weather_forecast_vintage_mode(vintage_mode)
    if normalized_vintage_mode == WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1:
        forecast_candidates, selected_vintage = select_weather_forecast_vintage_rows(
            raw_forecast_candidates,
            as_of=as_of,
        )
        for key, value in selected_vintage.items():
            if key in {
                "weather_forecast_selected_run_timestamp",
                "weather_forecast_selected_run_id",
            } and value is not None:
                metadata[key] = value
        metadata["weather_forecast_run_identity_present"] = bool(
            metadata.get("weather_forecast_run_identity_present")
            or selected_vintage.get("weather_forecast_run_identity_present")
        )
        metadata["weather_forecast_vintage_degraded"] = bool(
            metadata.get("weather_forecast_vintage_degraded")
            or selected_vintage.get("weather_forecast_vintage_degraded")
        )
        if selected_vintage.get("weather_forecast_run_identity_source"):
            metadata["weather_forecast_run_identity_source"] = selected_vintage.get(
                "weather_forecast_run_identity_source"
            )
        if selected_vintage.get("weather_forecast_run_identity_quality"):
            metadata["weather_forecast_run_identity_quality"] = selected_vintage.get(
                "weather_forecast_run_identity_quality"
            )
    else:
        forecast_candidates = issue_time_forecast_rows(
            raw_forecast_candidates,
            as_of=as_of,
            contract=EXOGENOUS_FEATURE_CONTRACTS["weather_daily_forecast"],
        )
        has_persisted_run_identity = (
            "forecast_run_timestamp" in raw_forecast_candidates.columns
            and raw_forecast_candidates["forecast_run_timestamp"].notna().any()
        )
        metadata["weather_forecast_run_identity_present"] = bool(
            metadata.get("weather_forecast_run_identity_present")
            or has_persisted_run_identity
        )
        if not has_persisted_run_identity and (
            "issue_time" in raw_forecast_candidates.columns
            and raw_forecast_candidates["issue_time"].notna().any()
        ):
            metadata["weather_forecast_run_identity_source"] = WEATHER_FORECAST_RUN_IDENTITY_SOURCE_LEGACY
            metadata["weather_forecast_run_identity_quality"] = WEATHER_FORECAST_RUN_IDENTITY_QUALITY_LEGACY
    forecast = forecast_candidates.loc[forecast_candidates["datum"] == target].copy() if not forecast_candidates.empty else forecast_candidates.copy()
    if forecast.empty and not forecast_candidates.empty:
        forecast_candidates["target_distance_days"] = (
            forecast_candidates["datum"] - target
        ).abs() / pd.Timedelta(days=1)
        forecast = forecast_candidates.sort_values(["target_distance_days", "datum"]).head(3)
    obs_temp = float(observed.tail(7)["temp"].mean() or 0.0) if not observed.empty else 0.0
    obs_humidity = float(observed.tail(7)["humidity"].mean() or 0.0) if not observed.empty else 0.0
    fc_temp_mean = float(forecast["temp"].mean()) if not forecast.empty else float("nan")
    fc_humidity_mean = float(forecast["humidity"].mean()) if not forecast.empty else float("nan")
    fc_temp = obs_temp if np.isnan(fc_temp_mean) else fc_temp_mean
    fc_humidity = obs_humidity if np.isnan(fc_humidity_mean) else fc_humidity_mean
    return {
        "weather_forecast_temp_3_7": fc_temp,
        "weather_forecast_humidity_3_7": fc_humidity,
        "weather_temp_anomaly_3_7": fc_temp - obs_temp,
        "weather_humidity_anomaly_3_7": fc_humidity - obs_humidity,
    }


def pollen_context(pollen_frame: pd.DataFrame | None, as_of: pd.Timestamp) -> float:
    if pollen_frame is None or pollen_frame.empty:
        return 0.0
    visible = observed_as_of_only_rows(
        pollen_frame,
        as_of=as_of,
    )
    if visible.empty:
        return 0.0
    return float(visible.tail(3)["pollen_index"].mean() or 0.0)


def holiday_share_in_target_window(
    holiday_ranges: list[tuple[pd.Timestamp, pd.Timestamp]],
    as_of: pd.Timestamp,
    *,
    horizon_days: int,
) -> float:
    target = target_date(as_of, horizon_days)
    return float(any(start <= target <= end for start, end in holiday_ranges))


def target_date(as_of: pd.Timestamp, horizon_days: int) -> pd.Timestamp:
    horizon = ensure_supported_horizon(horizon_days)
    return (pd.Timestamp(as_of) + pd.Timedelta(days=horizon)).normalize()


def target_week_start(as_of: pd.Timestamp, horizon_days: int) -> pd.Timestamp:
    target = target_date(as_of, horizon_days)
    return (target - pd.Timedelta(days=int(target.weekday()))).normalize()


def week_start_from_label(week_label: str) -> pd.Timestamp:
    year_text, week_text = str(week_label).split("_", 1)
    return pd.Timestamp.fromisocalendar(int(year_text), max(int(week_text), 1), 1).normalize()


def finalize_panel(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows).sort_values(["as_of_date", "bundesland"]).reset_index(drop=True)
    for code in ALL_BUNDESLAENDER:
        frame[f"state_{code}"] = (frame["bundesland"] == code).astype(float)
    return frame
