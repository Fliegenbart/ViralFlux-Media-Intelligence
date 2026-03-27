from __future__ import annotations

from typing import Any

import pandas as pd

WEATHER_FORECAST_VINTAGE_DISABLED = "legacy_issue_time_only"
WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1 = "run_timestamp_v1"
WEATHER_FORECAST_ISSUE_TIME_SEMANTICS = (
    "persisted_forecast_run_timestamp_or_created_at_legacy_fallback_v1"
)
WEATHER_FORECAST_RUN_IDENTITY_SOURCE_PERSISTED = "persisted_weather_ingest_run_v1"
WEATHER_FORECAST_RUN_IDENTITY_SOURCE_LEGACY = "legacy_created_at_fallback"
WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING = "missing"
WEATHER_FORECAST_RUN_IDENTITY_QUALITY_STABLE = "stable_persisted_batch"
WEATHER_FORECAST_RUN_IDENTITY_QUALITY_LEGACY = "legacy_unstable"
WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING = "missing"


def normalize_weather_forecast_vintage_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1:
        return WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1
    return WEATHER_FORECAST_VINTAGE_DISABLED


def empty_weather_forecast_vintage_metadata(mode: str | None) -> dict[str, Any]:
    normalized_mode = normalize_weather_forecast_vintage_mode(mode)
    return {
        "weather_forecast_vintage_mode": normalized_mode,
        "weather_forecast_issue_time_semantics": WEATHER_FORECAST_ISSUE_TIME_SEMANTICS,
        "weather_forecast_run_identity_present": False,
        "weather_forecast_run_identity_source": WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING,
        "weather_forecast_run_identity_quality": WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING,
        "weather_forecast_vintage_degraded": False,
    }


def select_weather_forecast_vintage_rows(
    frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    metadata = empty_weather_forecast_vintage_metadata(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1)
    if frame is None:
        return pd.DataFrame(), metadata
    if frame.empty:
        return frame.iloc[0:0].copy(), metadata

    candidates = frame.copy()
    run_timestamp_column = "forecast_run_timestamp" if "forecast_run_timestamp" in candidates.columns else None
    run_id_column = "forecast_run_id" if "forecast_run_id" in candidates.columns else None
    run_timestamp_present = bool(
        run_timestamp_column
        and candidates[run_timestamp_column].notna().any()
    )
    run_id_present = bool(
        run_id_column
        and candidates[run_id_column].notna().any()
    )
    metadata["weather_forecast_run_identity_present"] = bool(run_timestamp_present or run_id_present)
    if "forecast_run_identity_source" in candidates.columns:
        sources = [str(value) for value in candidates["forecast_run_identity_source"].dropna().unique()]
        if len(sources) == 1:
            metadata["weather_forecast_run_identity_source"] = sources[0]
        elif len(sources) > 1:
            metadata["weather_forecast_run_identity_source"] = "mixed"
    if "forecast_run_identity_quality" in candidates.columns:
        qualities = [str(value) for value in candidates["forecast_run_identity_quality"].dropna().unique()]
        if len(qualities) == 1:
            metadata["weather_forecast_run_identity_quality"] = qualities[0]
        elif len(qualities) > 1:
            metadata["weather_forecast_run_identity_quality"] = "mixed"

    if not run_timestamp_present:
        metadata["weather_forecast_vintage_degraded"] = not candidates.empty
        return candidates.iloc[0:0].copy(), metadata

    candidates = candidates.loc[
        candidates[run_timestamp_column].notna()
        & (candidates[run_timestamp_column] <= as_of)
    ].copy()
    if candidates.empty:
        metadata["weather_forecast_vintage_degraded"] = True
        return candidates, metadata

    selected_run_timestamp = pd.Timestamp(candidates[run_timestamp_column].max())
    selected = candidates.loc[
        candidates[run_timestamp_column] == selected_run_timestamp
    ].copy()
    metadata["weather_forecast_selected_run_timestamp"] = selected_run_timestamp.isoformat()
    if run_id_present:
        selected_run_id = str(selected[run_id_column].dropna().iloc[0])
        metadata["weather_forecast_selected_run_id"] = selected_run_id
    if "forecast_run_identity_source" in selected.columns and selected["forecast_run_identity_source"].notna().any():
        metadata["weather_forecast_run_identity_source"] = str(
            selected["forecast_run_identity_source"].dropna().iloc[0]
        )
    if "forecast_run_identity_quality" in selected.columns and selected["forecast_run_identity_quality"].notna().any():
        metadata["weather_forecast_run_identity_quality"] = str(
            selected["forecast_run_identity_quality"].dropna().iloc[0]
        )
    return selected.reset_index(drop=True), metadata
