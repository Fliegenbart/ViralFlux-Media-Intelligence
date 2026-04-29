from __future__ import annotations

from datetime import datetime
import math
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


FEATURE_FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
    "amelag_wastewater": ("ww_", "neighbor_ww_", "national_ww_", "xdisease_"),
    "survstat_truth": ("survstat_", "current_known_incidence", "seasonal_"),
    "grippeweb": ("grippeweb_",),
    "are_konsultation": ("are_consult_",),
    "ifsg_influenza": ("ifsg_influenza_",),
    "ifsg_rsv": ("ifsg_rsv_",),
    "notaufnahme": ("sars_notaufnahme_",),
    "google_trends": ("sars_trends_",),
    "weather": ("weather_",),
    "pollen": ("pollen_",),
    "school_holidays": ("target_holiday_",),
    "state_context": ("state_",),
}

SOURCE_LINEAGE_CONFIG: dict[str, dict[str, Any]] = {
    "amelag_wastewater": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "asof_latest_available_at_or_before_cutoff_core_history",
        "can_drop_region_rows": True,
        "drop_policy": "requires_core_wastewater_history",
        "calendar_driver": False,
        "age_columns": ("ww_feature_age_days",),
        "missing_columns": ("ww_feature_missing",),
    },
    "grippeweb": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "left_join_asof_latest_available_at_or_before_cutoff",
        "can_drop_region_rows": False,
        "age_columns": (
            "grippeweb_are_feature_age_days",
            "grippeweb_ili_feature_age_days",
            "grippeweb_are_national_feature_age_days",
            "grippeweb_ili_national_feature_age_days",
        ),
        "missing_columns": (
            "grippeweb_are_feature_missing",
            "grippeweb_ili_feature_missing",
            "grippeweb_are_national_feature_missing",
            "grippeweb_ili_national_feature_missing",
        ),
    },
    "are_konsultation": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "left_join_asof_latest_available_at_or_before_cutoff",
        "can_drop_region_rows": False,
        "age_columns": ("are_feature_age_days",),
        "missing_columns": ("are_feature_missing", "are_consult_missing"),
    },
    "ifsg_influenza": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "left_join_asof_latest_available_at_or_before_cutoff",
        "can_drop_region_rows": False,
        "age_columns": ("ifsg_influenza_feature_age_days",),
        "missing_columns": ("ifsg_influenza_feature_missing", "ifsg_influenza_missing"),
    },
    "ifsg_rsv": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "left_join_asof_latest_available_at_or_before_cutoff",
        "can_drop_region_rows": False,
        "age_columns": ("ifsg_rsv_feature_age_days",),
        "missing_columns": ("ifsg_rsv_feature_missing", "ifsg_rsv_missing"),
    },
    "notaufnahme": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "left_join_asof_latest_available_at_or_before_cutoff",
        "can_drop_region_rows": False,
        "age_columns": ("notaufnahme_feature_age_days",),
        "missing_columns": ("notaufnahme_feature_missing",),
    },
    "google_trends": {
        "importer_present": True,
        "db_table_present": True,
        "feature_builder_present": True,
        "lag_safe": True,
        "join_policy": "left_join_asof_latest_available_at_or_before_cutoff",
        "can_drop_region_rows": False,
        "age_columns": ("trends_feature_age_days",),
        "missing_columns": ("trends_feature_missing",),
    },
}


def _column_matches_family(column: str, prefixes: tuple[str, ...]) -> bool:
    return any(column == prefix or column.startswith(prefix) for prefix in prefixes)


def feature_family_columns(
    panel: pd.DataFrame,
    *,
    feature_columns: list[str] | tuple[str, ...] | None = None,
) -> dict[str, list[str]]:
    columns = list(feature_columns or [])
    if not columns and panel is not None and not panel.empty:
        columns = list(panel.columns)
    result: dict[str, list[str]] = {}
    for family, prefixes in FEATURE_FAMILY_PREFIXES.items():
        result[family] = sorted(
            column for column in columns
            if _column_matches_family(str(column), prefixes)
        )
    return result


def _finite_values(series: pd.Series) -> list[float]:
    values: list[float] = []
    for value in pd.to_numeric(series, errors="coerce").dropna().tolist():
        number = float(value)
        if math.isfinite(number):
            values.append(number)
    return values


def _family_age_summary(panel: pd.DataFrame, age_columns: tuple[str, ...]) -> dict[str, Any]:
    if panel is None or panel.empty or "as_of_date" not in panel.columns:
        return {"max_source_week": None, "max_data_age_days": None}
    as_of = pd.to_datetime(panel["as_of_date"], errors="coerce").dt.normalize()
    latest_source_dates: list[pd.Timestamp] = []
    all_ages: list[float] = []
    for column in age_columns:
        if column not in panel.columns:
            continue
        ages = pd.to_numeric(panel[column], errors="coerce")
        for source_date in (as_of - pd.to_timedelta(ages, unit="D")).dropna().tolist():
            latest_source_dates.append(pd.Timestamp(source_date).normalize())
        all_ages.extend(_finite_values(ages))
    return {
        "max_source_week": (
            str(max(latest_source_dates).date()) if latest_source_dates else None
        ),
        "max_data_age_days": (
            round(float(max(all_ages)), 3) if all_ages else None
        ),
    }


def source_lineage_manifest(
    panel: pd.DataFrame,
    *,
    feature_columns: list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    family_columns = feature_family_columns(panel, feature_columns=feature_columns)
    lineage: dict[str, dict[str, Any]] = {}
    for family, config in SOURCE_LINEAGE_CONFIG.items():
        columns = family_columns.get(family) or []
        age_summary = _family_age_summary(panel, tuple(config.get("age_columns") or ()))
        missing_columns = [
            column for column in config.get("missing_columns") or ()
            if panel is not None and column in panel.columns
        ]
        missing_rate = None
        if panel is not None and not panel.empty and missing_columns:
            missing_values: list[float] = []
            for column in missing_columns:
                missing_values.extend(_finite_values(panel[column]))
            if missing_values:
                missing_rate = round(float(sum(missing_values) / len(missing_values)), 4)
        lineage[family] = {
            **{key: value for key, value in config.items() if key not in {"age_columns", "missing_columns"}},
            "active_in_regional_panel_h5_h7": bool(columns),
            "included_in_feature_columns": bool(columns),
            "written_to_backtest_source_lineage": True,
            "feature_columns": columns,
            "feature_column_count": len(columns),
            "missing_columns": missing_columns,
            "missing_rate": missing_rate,
            **age_summary,
        }
    return lineage


def signal_bundle_metadata(
    *,
    virus_typ: str,
    panel: pd.DataFrame,
    feature_columns: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    family_columns = feature_family_columns(panel, feature_columns=feature_columns)
    lineage = source_lineage_manifest(panel, feature_columns=feature_columns)
    active_families = sorted(
        family for family, columns in family_columns.items()
        if columns
    )
    source_weeks = [
        value.get("max_source_week")
        for value in lineage.values()
        if value.get("max_source_week")
    ]
    ages = [
        float(value.get("max_data_age_days"))
        for value in lineage.values()
        if value.get("max_data_age_days") is not None
    ]
    return {
        "virus_typ": virus_typ,
        "issue_calendar_type": "weekly_shared_issue_calendar",
        "feature_asof_policy": "latest_available_at_or_before_cutoff",
        "target_join_policy": "weekly_target_week_start",
        "forecast_target_semantics": "day_horizon_to_weekly_target",
        "target_week_start_formula": "week_start(forecast_issue_cutoff_date + horizon_days)",
        "active_feature_families": active_families,
        "feature_family_columns": family_columns,
        "source_lineage": lineage,
        "max_source_week": max(source_weeks) if source_weeks else None,
        "max_data_age_days": round(float(max(ages)), 3) if ages else None,
    }


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
            **signal_bundle_metadata(
                virus_typ=virus_typ,
                panel=panel,
                feature_columns=[],
            ),
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
            "are_consult_available",
            "sars_notaufnahme_available",
            "sars_trends_available",
        )
        if column in panel.columns
    }
    signal_metadata = signal_bundle_metadata(
        virus_typ=virus_typ,
        panel=panel,
        feature_columns=None,
    )
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
        **signal_metadata,
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
