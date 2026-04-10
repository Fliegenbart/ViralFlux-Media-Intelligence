from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.core.time import utc_now
from app.services.ml.exogenous_feature_contracts import (
    EXOGENOUS_FEATURE_SEMANTICS_VERSION,
    exogenous_feature_semantics_manifest,
)
from app.services.ml.regional_panel_utils import (
    EVENT_DEFINITION_VERSION,
    SOURCE_LAG_DAYS,
    TARGET_WINDOW_DAYS,
    event_definition_config_for_virus,
)
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    empty_weather_forecast_vintage_metadata,
)


def dataset_manifest(builder: Any, virus_typ: str, panel: pd.DataFrame) -> dict[str, Any]:
    event_config = event_definition_config_for_virus(virus_typ)
    weather_metadata = dict(
        panel.attrs.get("weather_forecast_metadata")
        or getattr(builder, "_last_weather_forecast_metadata", {})
        or empty_weather_forecast_vintage_metadata(WEATHER_FORECAST_VINTAGE_DISABLED)
    )
    if panel.empty:
        return {
            "virus_typ": virus_typ,
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "event_definition_config": event_config.to_manifest(),
            "target_window_days": list(TARGET_WINDOW_DAYS),
            "source_lag_days": SOURCE_LAG_DAYS,
            "exogenous_feature_semantics_version": EXOGENOUS_FEATURE_SEMANTICS_VERSION,
            "exogenous_feature_semantics": exogenous_feature_semantics_manifest(),
            "weather_forecast_vintage_mode": weather_metadata.get("weather_forecast_vintage_mode"),
            "weather_forecast_issue_time_semantics": weather_metadata.get("weather_forecast_issue_time_semantics"),
            "weather_forecast_run_identity_present": bool(
                weather_metadata.get("weather_forecast_run_identity_present")
            ),
            "weather_forecast_run_identity_source": weather_metadata.get(
                "weather_forecast_run_identity_source"
            ),
            "weather_forecast_run_identity_quality": weather_metadata.get(
                "weather_forecast_run_identity_quality"
            ),
            "rows": 0,
            "truth_source": "unavailable",
            "source_coverage": {},
            "training_source_coverage": {},
        }

    target_window_days = (
        list(panel["target_window_days"].iloc[0])
        if "target_window_days" in panel.columns and len(panel) > 0
        else list(TARGET_WINDOW_DAYS)
    )
    horizon_days = (
        int(panel["horizon_days"].iloc[0])
        if "horizon_days" in panel.columns and len(panel) > 0
        else target_window_days[-1]
    )
    truth_sources = sorted(str(value) for value in panel["truth_source"].dropna().unique())
    source_coverage = {
        column: round(float(panel[column].mean()), 4)
        for column in (
            "grippeweb_are_available",
            "grippeweb_ili_available",
            "ifsg_influenza_available",
            "ifsg_rsv_available",
            "sars_are_available",
            "sars_notaufnahme_available",
            "sars_trends_available",
        )
        if column in panel.columns
    }
    return {
        "virus_typ": virus_typ,
        "horizon_days": horizon_days,
        "event_definition_version": EVENT_DEFINITION_VERSION,
        "event_definition_config": event_config.to_manifest(),
        "target_window_days": target_window_days,
        "source_lag_days": SOURCE_LAG_DAYS,
        "exogenous_feature_semantics_version": EXOGENOUS_FEATURE_SEMANTICS_VERSION,
        "exogenous_feature_semantics": exogenous_feature_semantics_manifest(),
        "weather_forecast_vintage_mode": weather_metadata.get("weather_forecast_vintage_mode"),
        "weather_forecast_issue_time_semantics": weather_metadata.get("weather_forecast_issue_time_semantics"),
        "weather_forecast_run_identity_present": bool(
            weather_metadata.get("weather_forecast_run_identity_present")
        ),
        "weather_forecast_run_identity_source": weather_metadata.get(
            "weather_forecast_run_identity_source"
        ),
        "weather_forecast_run_identity_quality": weather_metadata.get(
            "weather_forecast_run_identity_quality"
        ),
        "rows": int(len(panel)),
        "states": int(panel["bundesland"].nunique()),
        "unique_as_of_dates": int(panel["as_of_date"].nunique()),
        "as_of_range": {
            "start": str(panel["as_of_date"].min()),
            "end": str(panel["as_of_date"].max()),
        },
        "truth_source": truth_sources[0] if len(truth_sources) == 1 else truth_sources,
        "source_coverage": source_coverage,
        "training_source_coverage": dict(source_coverage),
    }


def point_in_time_snapshot_manifest(builder: Any, virus_typ: str, panel: pd.DataFrame) -> dict[str, Any]:
    manifest = dataset_manifest(builder, virus_typ=virus_typ, panel=panel)
    if panel.empty:
        return {
            "virus_typ": virus_typ,
            "snapshot_type": "regional_panel_as_of_training",
            "captured_at": utc_now().isoformat(),
            "rows": 0,
            "source_lag_days": SOURCE_LAG_DAYS,
            "exogenous_feature_semantics_version": EXOGENOUS_FEATURE_SEMANTICS_VERSION,
            "weather_forecast_vintage_mode": manifest.get("weather_forecast_vintage_mode"),
            "weather_forecast_issue_time_semantics": manifest.get("weather_forecast_issue_time_semantics"),
            "weather_forecast_run_identity_present": manifest.get("weather_forecast_run_identity_present"),
            "weather_forecast_run_identity_source": manifest.get(
                "weather_forecast_run_identity_source"
            ),
            "weather_forecast_run_identity_quality": manifest.get(
                "weather_forecast_run_identity_quality"
            ),
            "dataset_manifest": manifest,
        }

    state_row_counts = {
        code: int(count)
        for code, count in panel.groupby("bundesland")["as_of_date"].count().to_dict().items()
    }
    return {
        "virus_typ": virus_typ,
        "horizon_days": manifest.get("horizon_days"),
        "snapshot_type": "regional_panel_as_of_training",
        "captured_at": utc_now().isoformat(),
        "rows": int(len(panel)),
        "states": int(panel["bundesland"].nunique()),
        "unique_as_of_dates": int(panel["as_of_date"].nunique()),
        "as_of_range": {
            "start": str(panel["as_of_date"].min()),
            "end": str(panel["as_of_date"].max()),
        },
        "state_row_counts": state_row_counts,
        "feature_columns": sorted(
            column for column in panel.columns
            if column not in {
                "virus_typ",
                "bundesland",
                "bundesland_name",
                "as_of_date",
                "target_week_start",
                "target_window_days",
                "event_definition_version",
                "truth_source",
            }
        ),
        "source_lag_days": SOURCE_LAG_DAYS,
        "exogenous_feature_semantics_version": EXOGENOUS_FEATURE_SEMANTICS_VERSION,
        "weather_forecast_vintage_mode": manifest.get("weather_forecast_vintage_mode"),
        "weather_forecast_issue_time_semantics": manifest.get("weather_forecast_issue_time_semantics"),
        "weather_forecast_run_identity_present": manifest.get("weather_forecast_run_identity_present"),
        "weather_forecast_run_identity_source": manifest.get(
            "weather_forecast_run_identity_source"
        ),
        "weather_forecast_run_identity_quality": manifest.get(
            "weather_forecast_run_identity_quality"
        ),
        "target_window_days": manifest.get("target_window_days") or list(TARGET_WINDOW_DAYS),
        "dataset_manifest": manifest,
    }


def live_source_readiness_frames(
    builder: Any,
    *,
    virus_typ: str,
    as_of_date: datetime | pd.Timestamp,
    lookback_days: int = 28,
) -> dict[str, pd.DataFrame]:
    effective_as_of = pd.Timestamp(as_of_date).normalize()
    start_date = effective_as_of - pd.Timedelta(days=max(int(lookback_days), 28))
    grippeweb = builder._load_grippeweb_signals(start_date, effective_as_of)
    frames: dict[str, pd.DataFrame] = {
        "wastewater": builder._load_wastewater_daily(virus_typ, start_date),
        "grippeweb_are": grippeweb.loc[grippeweb["signal_type"] == "ARE"].copy()
        if not grippeweb.empty
        else pd.DataFrame(),
        "grippeweb_ili": grippeweb.loc[grippeweb["signal_type"] == "ILI"].copy()
        if not grippeweb.empty
        else pd.DataFrame(),
    }
    if virus_typ in {"Influenza A", "Influenza B"}:
        frames["ifsg_influenza"] = builder._load_influenza_ifsg(start_date, effective_as_of)
    elif virus_typ == "RSV A":
        frames["ifsg_rsv"] = builder._load_rsv_ifsg(start_date, effective_as_of)
    elif virus_typ == "SARS-CoV-2":
        frames["sars_are"] = builder._load_are_konsultation(start_date, effective_as_of)
        frames["sars_notaufnahme"] = builder._load_notaufnahme_covid(start_date, effective_as_of)
        frames["sars_trends"] = builder._load_corona_test_trends(start_date, effective_as_of)
    return {
        source_id: frame.reset_index(drop=True) if not frame.empty else pd.DataFrame()
        for source_id, frame in frames.items()
    }
