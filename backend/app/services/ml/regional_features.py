"""Regional as-of panel dataset builder for pooled outbreak forecasting."""

from __future__ import annotations
from app.core.time import utc_now

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    GrippeWebData,
    InfluenzaData,
    KreisEinwohner,
    NotaufnahmeSyndromData,
    PollenData,
    RSVData,
    SchoolHolidays,
    SurvstatKreisData,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.ml.forecast_horizon_utils import ensure_supported_horizon
from app.services.ml.forecast_service import SURVSTAT_VIRUS_MAP
from app.services.ml.exogenous_feature_contracts import (
    EXOGENOUS_FEATURE_CONTRACTS,
    EXOGENOUS_FEATURE_SEMANTICS_VERSION,
    exogenous_feature_semantics_manifest,
    issue_time_forecast_rows,
    observed_as_of_only_rows,
)
from app.services.ml.nowcast_contracts import NowcastObservation, NowcastResult
from app.services.ml.nowcast_revision import NowcastRevisionService
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    CITY_TO_BUNDESLAND,
    EVENT_DEFINITION_VERSION,
    REGIONAL_NEIGHBORS,
    SOURCE_LAG_DAYS,
    STATE_NAME_TO_CODE,
    TARGET_WINDOW_DAYS,
    circular_week_distance,
    effective_available_time,
    event_definition_config_for_virus,
    normalize_state_code,
    seasonal_baseline_and_mad,
)
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_ISSUE_TIME_SEMANTICS,
    WEATHER_FORECAST_RUN_IDENTITY_QUALITY_LEGACY,
    WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING,
    WEATHER_FORECAST_RUN_IDENTITY_SOURCE_LEGACY,
    WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING,
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
    empty_weather_forecast_vintage_metadata,
    normalize_weather_forecast_vintage_mode,
    select_weather_forecast_vintage_rows,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)


def _feature_virus_slug(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _geo_unit_fallback_id(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace(",", "")
        .replace("/", "_")
        .replace("-", "_")
    )


class RegionalFeatureBuilder:
    """Build leakage-safe panel datasets for regional outbreak forecasting."""

    def __init__(self, db: Session):
        self.db = db
        self._nowcast_service = NowcastRevisionService()
        self._last_weather_forecast_metadata = empty_weather_forecast_vintage_metadata(
            WEATHER_FORECAST_VINTAGE_DISABLED
        )

    @property
    def nowcast_service(self) -> NowcastRevisionService:
        service = getattr(self, "_nowcast_service", None)
        if service is None:
            service = NowcastRevisionService()
            self._nowcast_service = service
        return service

    def build_panel_training_data(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
        horizon_days: int = 7,
        *,
        include_nowcast: bool = False,
        use_revision_adjusted: bool = False,
        revision_policy: str | None = None,
        source_revision_policy: dict[str, str] | None = None,
        weather_forecast_vintage_mode: str | None = None,
    ) -> pd.DataFrame:
        """Build pooled training rows across all Bundesländer."""
        horizon = ensure_supported_horizon(horizon_days)
        end_date = pd.Timestamp(utc_now()).normalize()
        start_date = end_date - pd.Timedelta(days=lookback_days)
        truth_start = start_date - pd.Timedelta(days=730)

        wastewater = self._load_wastewater_daily(virus_typ, truth_start)
        wastewater_context = self._load_supported_wastewater_context(virus_typ, truth_start)
        truth = self._load_truth_series(virus_typ, truth_start)
        grippeweb = self._load_grippeweb_signals(truth_start, end_date)
        influenza_ifsg = self._load_influenza_ifsg(truth_start, end_date)
        rsv_ifsg = self._load_rsv_ifsg(truth_start, end_date)
        are = self._load_are_konsultation(truth_start, end_date) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        notaufnahme = self._load_notaufnahme_covid(truth_start, end_date) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        trends = self._load_corona_test_trends(truth_start, end_date) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        weather = self._load_weather(truth_start, end_date + pd.Timedelta(days=horizon))
        pollen = self._load_pollen(truth_start, end_date + pd.Timedelta(days=horizon))
        holidays = self._load_holidays()
        state_populations = self._load_state_population_map()
        weather_metadata = empty_weather_forecast_vintage_metadata(weather_forecast_vintage_mode)
        self._last_weather_forecast_metadata = dict(weather_metadata)

        rows = self._build_rows(
            virus_typ=virus_typ,
            wastewater=wastewater,
            wastewater_context=wastewater_context,
            truth=truth,
            grippeweb=grippeweb,
            influenza_ifsg=influenza_ifsg,
            rsv_ifsg=rsv_ifsg,
            are=are,
            notaufnahme=notaufnahme,
            trends=trends,
            weather=weather,
            pollen=pollen,
            holidays=holidays,
            state_populations=state_populations,
            start_date=start_date,
            end_date=end_date,
            horizon_days=horizon,
            include_targets=True,
            include_nowcast=include_nowcast,
            use_revision_adjusted=use_revision_adjusted,
            revision_policy=self._resolve_revision_policy(
                revision_policy=revision_policy,
                use_revision_adjusted=use_revision_adjusted,
            ),
            source_revision_policy=source_revision_policy,
            weather_forecast_vintage_mode=normalize_weather_forecast_vintage_mode(
                weather_forecast_vintage_mode
            ),
            weather_forecast_metadata=weather_metadata,
        )
        panel = self._finalize_panel(rows)
        panel.attrs["weather_forecast_metadata"] = dict(weather_metadata)
        self._last_weather_forecast_metadata = dict(weather_metadata)
        return panel

    def build_inference_panel(
        self,
        virus_typ: str = "Influenza A",
        as_of_date: datetime | None = None,
        lookback_days: int = 180,
        horizon_days: int = 7,
        *,
        include_nowcast: bool = False,
        use_revision_adjusted: bool = False,
        revision_policy: str | None = None,
        source_revision_policy: dict[str, str] | None = None,
        weather_forecast_vintage_mode: str | None = None,
    ) -> pd.DataFrame:
        """Build one inference row per Bundesland for a shared as-of date."""
        horizon = ensure_supported_horizon(horizon_days)
        effective_as_of = pd.Timestamp(as_of_date or utc_now()).normalize()
        history_start = effective_as_of - pd.Timedelta(days=lookback_days)
        row_start = effective_as_of - pd.Timedelta(days=horizon + 7)
        truth_start = history_start - pd.Timedelta(days=730)

        wastewater = self._load_wastewater_daily(virus_typ, truth_start)
        wastewater_context = self._load_supported_wastewater_context(virus_typ, truth_start)
        truth = self._load_truth_series(virus_typ, truth_start)
        grippeweb = self._load_grippeweb_signals(truth_start, effective_as_of)
        influenza_ifsg = self._load_influenza_ifsg(truth_start, effective_as_of)
        rsv_ifsg = self._load_rsv_ifsg(truth_start, effective_as_of)
        are = self._load_are_konsultation(truth_start, effective_as_of) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        notaufnahme = (
            self._load_notaufnahme_covid(truth_start, effective_as_of)
            if virus_typ == "SARS-CoV-2"
            else pd.DataFrame()
        )
        trends = self._load_corona_test_trends(truth_start, effective_as_of) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        weather = self._load_weather(truth_start, effective_as_of + pd.Timedelta(days=horizon))
        pollen = self._load_pollen(truth_start, effective_as_of + pd.Timedelta(days=horizon))
        holidays = self._load_holidays()
        state_populations = self._load_state_population_map()
        weather_metadata = empty_weather_forecast_vintage_metadata(weather_forecast_vintage_mode)
        self._last_weather_forecast_metadata = dict(weather_metadata)

        rows = self._build_rows(
            virus_typ=virus_typ,
            wastewater=wastewater,
            wastewater_context=wastewater_context,
            truth=truth,
            grippeweb=grippeweb,
            influenza_ifsg=influenza_ifsg,
            rsv_ifsg=rsv_ifsg,
            are=are,
            notaufnahme=notaufnahme,
            trends=trends,
            weather=weather,
            pollen=pollen,
            holidays=holidays,
            state_populations=state_populations,
            start_date=row_start,
            end_date=effective_as_of,
            horizon_days=horizon,
            include_targets=False,
            include_nowcast=include_nowcast,
            use_revision_adjusted=use_revision_adjusted,
            revision_policy=self._resolve_revision_policy(
                revision_policy=revision_policy,
                use_revision_adjusted=use_revision_adjusted,
            ),
            source_revision_policy=source_revision_policy,
            weather_forecast_vintage_mode=normalize_weather_forecast_vintage_mode(
                weather_forecast_vintage_mode
            ),
            weather_forecast_metadata=weather_metadata,
        )
        panel = self._finalize_panel(rows)
        if panel.empty:
            panel.attrs["weather_forecast_metadata"] = dict(weather_metadata)
            self._last_weather_forecast_metadata = dict(weather_metadata)
            return panel
        panel.attrs["weather_forecast_metadata"] = dict(weather_metadata)
        self._last_weather_forecast_metadata = dict(weather_metadata)

        latest_rows = (
            panel.sort_values(["bundesland", "as_of_date"])
            .groupby("bundesland", as_index=False)
            .tail(1)
            .sort_values("bundesland")
            .reset_index(drop=True)
        )
        return latest_rows

    def latest_available_as_of_date(self, virus_typ: str = "Influenza A") -> pd.Timestamp:
        row = (
            self.db.query(
                func.max(WastewaterData.available_time).label("available_time"),
                func.max(WastewaterData.datum).label("datum"),
            )
            .filter(WastewaterData.virus_typ == virus_typ)
            .first()
        )
        if row is None:
            return pd.Timestamp(utc_now()).normalize()
        return effective_available_time(
            row.datum or utc_now(),
            row.available_time,
            0,
        ).normalize()

    def build_regional_training_data(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        lookback_days: int = 900,
        *,
        include_nowcast: bool = False,
        use_revision_adjusted: bool = False,
        revision_policy: str | None = None,
        source_revision_policy: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        """Backward-compatible helper returning the per-state panel slice."""
        code = normalize_state_code(bundesland) or bundesland
        panel = self.build_panel_training_data(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            include_nowcast=include_nowcast,
            use_revision_adjusted=use_revision_adjusted,
            revision_policy=revision_policy,
            source_revision_policy=source_revision_policy,
        )
        if panel.empty:
            return panel
        return panel.loc[panel["bundesland"] == code].reset_index(drop=True)

    def get_available_bundeslaender(self, virus_typ: str = "Influenza A") -> list[str]:
        rows = (
            self.db.query(WastewaterData.bundesland)
            .filter(
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.viruslast.isnot(None),
            )
            .distinct()
            .all()
        )
        available = {
            code
            for (value,) in rows
            if (code := normalize_state_code(value)) is not None
        }
        return sorted(available)

    def dataset_manifest(self, virus_typ: str, panel: pd.DataFrame) -> dict[str, Any]:
        event_config = event_definition_config_for_virus(virus_typ)
        weather_metadata = dict(
            panel.attrs.get("weather_forecast_metadata")
            or getattr(self, "_last_weather_forecast_metadata", {})
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

    def point_in_time_snapshot_manifest(self, virus_typ: str, panel: pd.DataFrame) -> dict[str, Any]:
        dataset_manifest = self.dataset_manifest(virus_typ=virus_typ, panel=panel)
        if panel.empty:
            return {
                "virus_typ": virus_typ,
                "snapshot_type": "regional_panel_as_of_training",
                "captured_at": utc_now().isoformat(),
                "rows": 0,
                "source_lag_days": SOURCE_LAG_DAYS,
                "exogenous_feature_semantics_version": EXOGENOUS_FEATURE_SEMANTICS_VERSION,
                "weather_forecast_vintage_mode": dataset_manifest.get("weather_forecast_vintage_mode"),
                "weather_forecast_issue_time_semantics": dataset_manifest.get("weather_forecast_issue_time_semantics"),
                "weather_forecast_run_identity_present": dataset_manifest.get("weather_forecast_run_identity_present"),
                "weather_forecast_run_identity_source": dataset_manifest.get(
                    "weather_forecast_run_identity_source"
                ),
                "weather_forecast_run_identity_quality": dataset_manifest.get(
                    "weather_forecast_run_identity_quality"
                ),
                "dataset_manifest": dataset_manifest,
            }

        state_row_counts = {
            code: int(count)
            for code, count in panel.groupby("bundesland")["as_of_date"].count().to_dict().items()
        }
        return {
            "virus_typ": virus_typ,
            "horizon_days": dataset_manifest.get("horizon_days"),
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
            "weather_forecast_vintage_mode": dataset_manifest.get("weather_forecast_vintage_mode"),
            "weather_forecast_issue_time_semantics": dataset_manifest.get("weather_forecast_issue_time_semantics"),
            "weather_forecast_run_identity_present": dataset_manifest.get("weather_forecast_run_identity_present"),
            "weather_forecast_run_identity_source": dataset_manifest.get(
                "weather_forecast_run_identity_source"
            ),
            "weather_forecast_run_identity_quality": dataset_manifest.get(
                "weather_forecast_run_identity_quality"
            ),
            "target_window_days": dataset_manifest.get("target_window_days") or list(TARGET_WINDOW_DAYS),
            "dataset_manifest": dataset_manifest,
        }

    def live_source_readiness_frames(
        self,
        *,
        virus_typ: str,
        as_of_date: datetime | pd.Timestamp,
        lookback_days: int = 28,
    ) -> dict[str, pd.DataFrame]:
        effective_as_of = pd.Timestamp(as_of_date).normalize()
        start_date = effective_as_of - pd.Timedelta(days=max(int(lookback_days), 28))
        grippeweb = self._load_grippeweb_signals(start_date, effective_as_of)
        frames: dict[str, pd.DataFrame] = {
            "wastewater": self._load_wastewater_daily(virus_typ, start_date),
            "grippeweb_are": grippeweb.loc[grippeweb["signal_type"] == "ARE"].copy()
            if not grippeweb.empty
            else pd.DataFrame(),
            "grippeweb_ili": grippeweb.loc[grippeweb["signal_type"] == "ILI"].copy()
            if not grippeweb.empty
            else pd.DataFrame(),
        }
        if virus_typ in {"Influenza A", "Influenza B"}:
            frames["ifsg_influenza"] = self._load_influenza_ifsg(start_date, effective_as_of)
        elif virus_typ == "RSV A":
            frames["ifsg_rsv"] = self._load_rsv_ifsg(start_date, effective_as_of)
        elif virus_typ == "SARS-CoV-2":
            frames["sars_are"] = self._load_are_konsultation(start_date, effective_as_of)
            frames["sars_notaufnahme"] = self._load_notaufnahme_covid(start_date, effective_as_of)
            frames["sars_trends"] = self._load_corona_test_trends(start_date, effective_as_of)
        return {
            source_id: frame.reset_index(drop=True) if not frame.empty else pd.DataFrame()
            for source_id, frame in frames.items()
        }

    def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        rows = (
            self.db.query(
                WastewaterData.bundesland,
                WastewaterData.datum,
                func.max(WastewaterData.available_time).label("available_time"),
                func.avg(WastewaterData.viruslast).label("viral_load"),
                func.count(WastewaterData.id).label("site_count"),
                func.avg(func.cast(func.coalesce(WastewaterData.unter_bg, False), Integer)).label("under_bg_share"),
                func.stddev_pop(WastewaterData.viruslast).label("viral_std"),
            )
            .filter(
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.datum >= start_date.to_pydatetime(),
                WastewaterData.viruslast.isnot(None),
            )
            .group_by(
                WastewaterData.bundesland,
                WastewaterData.datum,
            )
            .order_by(WastewaterData.datum.asc())
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.bundesland),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(row.datum, row.available_time, 0),
                    "viral_load": float(row.viral_load or 0.0),
                    "site_count": int(row.site_count or 0),
                    "under_bg_share": float(row.under_bg_share or 0.0),
                    "viral_std": float(row.viral_std or 0.0),
                }
                for row in rows
                if normalize_state_code(row.bundesland)
            ]
        )
        if frame.empty:
            return frame

        return frame.sort_values(["bundesland", "datum"]).reset_index(drop=True)

    def _load_supported_wastewater_context(
        self,
        virus_typ: str,
        start_date: pd.Timestamp,
    ) -> dict[str, pd.DataFrame]:
        bundle: dict[str, pd.DataFrame] = {}
        for candidate in SUPPORTED_VIRUS_TYPES:
            frame = self._load_wastewater_daily(candidate, start_date)
            if not frame.empty:
                bundle[candidate] = frame
        if virus_typ not in bundle:
            bundle[virus_typ] = self._load_wastewater_daily(virus_typ, start_date)
        return bundle

    def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        truth = self._load_truth_from_kreis(virus_typ=virus_typ, start_date=start_date)
        if truth.empty:
            truth = self._load_truth_from_weekly(virus_typ=virus_typ, start_date=start_date)
        return truth

    def load_landkreis_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        if self.db is None:
            return pd.DataFrame()
        diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
        if not diseases:
            return pd.DataFrame()

        rows = (
            self.db.query(
                SurvstatKreisData.year,
                SurvstatKreisData.week,
                SurvstatKreisData.week_label,
                SurvstatKreisData.kreis,
                KreisEinwohner.ags,
                KreisEinwohner.bundesland,
                KreisEinwohner.einwohner,
                func.sum(SurvstatKreisData.fallzahl).label("total_cases"),
            )
            .join(KreisEinwohner, KreisEinwohner.kreis_name == SurvstatKreisData.kreis)
            .filter(
                func.lower(SurvstatKreisData.disease).in_(diseases),
                SurvstatKreisData.year >= start_date.year,
            )
            .group_by(
                SurvstatKreisData.year,
                SurvstatKreisData.week,
                SurvstatKreisData.week_label,
                SurvstatKreisData.kreis,
                KreisEinwohner.ags,
                KreisEinwohner.bundesland,
                KreisEinwohner.einwohner,
            )
            .order_by(
                SurvstatKreisData.year.asc(),
                SurvstatKreisData.week.asc(),
                SurvstatKreisData.kreis.asc(),
            )
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "geo_unit_level": "landkreis",
                    "geo_unit_id": str(row.ags or _geo_unit_fallback_id(row.kreis)),
                    "geo_unit_name": str(row.kreis),
                    "parent_bundesland": normalize_state_code(row.bundesland),
                    "parent_bundesland_name": str(row.bundesland or ""),
                    "population": float(row.einwohner or 0.0),
                    "week_start": self._week_start_from_label(row.week_label),
                    "available_date": effective_available_time(
                        self._week_start_from_label(row.week_label),
                        None,
                        SOURCE_LAG_DAYS["survstat_kreis"],
                    ),
                    "incidence": (
                        (float(row.total_cases or 0.0) / float(row.einwohner or 0.0)) * 100_000.0
                        if float(row.einwohner or 0.0) > 0.0
                        else np.nan
                    ),
                    "truth_source": "survstat_kreis",
                }
                for row in rows
                if normalize_state_code(row.bundesland)
            ]
        )
        if frame.empty:
            return frame

        return (
            frame.dropna(subset=["incidence"])
            .loc[lambda df: df["population"] > 0.0]
            .sort_values(["geo_unit_id", "week_start"])
            .reset_index(drop=True)
        )

    def _load_truth_from_kreis(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
        if not diseases:
            return pd.DataFrame()

        state_populations = self._load_state_population_map()
        if not state_populations:
            logger.warning("Regional truth fallback to weekly SurvStat because Kreis state populations are unavailable.")
            return pd.DataFrame()

        rows = (
            self.db.query(
                SurvstatKreisData.year,
                SurvstatKreisData.week,
                SurvstatKreisData.week_label,
                KreisEinwohner.bundesland,
                func.sum(SurvstatKreisData.fallzahl).label("total_cases"),
            )
            .join(KreisEinwohner, KreisEinwohner.kreis_name == SurvstatKreisData.kreis)
            .filter(
                func.lower(SurvstatKreisData.disease).in_(diseases),
                SurvstatKreisData.year >= start_date.year,
            )
            .group_by(
                SurvstatKreisData.year,
                SurvstatKreisData.week,
                SurvstatKreisData.week_label,
                KreisEinwohner.bundesland,
            )
            .order_by(
                SurvstatKreisData.year.asc(),
                SurvstatKreisData.week.asc(),
            )
            .all()
        )

        if not rows:
            return pd.DataFrame()

        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.bundesland),
                    "week_start": self._week_start_from_label(row.week_label),
                    "available_date": effective_available_time(
                        self._week_start_from_label(row.week_label),
                        None,
                        SOURCE_LAG_DAYS["survstat_kreis"],
                    ),
                    "incidence": (
                        (float(row.total_cases or 0.0) / state_populations[normalize_state_code(row.bundesland)]) * 100_000.0
                        if normalize_state_code(row.bundesland) in state_populations
                        and state_populations[normalize_state_code(row.bundesland)] > 0
                        else np.nan
                    ),
                    "truth_source": "survstat_kreis",
                }
                for row in rows
                if normalize_state_code(row.bundesland)
            ]
        )
        if frame.empty or frame["incidence"].notna().sum() == 0:
            logger.warning("Regional truth fallback to weekly SurvStat because Kreis population data is unusable.")
            return pd.DataFrame()

        return (
            frame.dropna(subset=["incidence"])
            .sort_values(["bundesland", "week_start"])
            .reset_index(drop=True)
        )

    def _load_state_population_map(self) -> dict[str, float]:
        rows = (
            self.db.query(
                KreisEinwohner.bundesland,
                func.sum(KreisEinwohner.einwohner).label("population"),
            )
            .filter(KreisEinwohner.einwohner > 0)
            .group_by(KreisEinwohner.bundesland)
            .all()
        )
        return {
            code: float(row.population or 0.0)
            for row in rows
            if (code := normalize_state_code(row.bundesland)) and float(row.population or 0.0) > 0
        }

    def _load_truth_from_weekly(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
        if not diseases:
            return pd.DataFrame()

        rows = (
            self.db.query(
                SurvstatWeeklyData.week_start,
                func.max(SurvstatWeeklyData.available_time).label("available_time"),
                SurvstatWeeklyData.bundesland,
                func.sum(SurvstatWeeklyData.incidence).label("incidence"),
            )
            .filter(
                func.lower(SurvstatWeeklyData.disease).in_(diseases),
                SurvstatWeeklyData.week_start >= start_date.to_pydatetime(),
                SurvstatWeeklyData.bundesland != "Gesamt",
            )
            .group_by(
                SurvstatWeeklyData.week_start,
                SurvstatWeeklyData.bundesland,
            )
            .order_by(SurvstatWeeklyData.week_start.asc())
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.bundesland),
                    "week_start": pd.Timestamp(row.week_start).normalize(),
                    "available_date": effective_available_time(
                        row.week_start,
                        row.available_time,
                        SOURCE_LAG_DAYS["survstat_weekly"],
                    ),
                    "incidence": float(row.incidence or 0.0),
                    "truth_source": "survstat_weekly",
                }
                for row in rows
                if normalize_state_code(row.bundesland)
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values(["bundesland", "week_start"]).reset_index(drop=True)

    def _load_grippeweb_signals(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        if self.db is None:
            return pd.DataFrame()
        rows = (
            self.db.query(
                GrippeWebData.bundesland,
                GrippeWebData.datum,
                GrippeWebData.erkrankung_typ,
                func.max(GrippeWebData.created_at).label("created_at"),
                func.avg(GrippeWebData.inzidenz).label("incidence"),
            )
            .filter(
                GrippeWebData.datum >= start_date.to_pydatetime(),
                GrippeWebData.datum <= end_date.to_pydatetime(),
                GrippeWebData.erkrankung_typ.in_(["ARE", "ILI"]),
                GrippeWebData.altersgruppe.in_(["00+", "Gesamt"]),
            )
            .group_by(
                GrippeWebData.bundesland,
                GrippeWebData.datum,
                GrippeWebData.erkrankung_typ,
            )
            .order_by(GrippeWebData.datum.asc())
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.bundesland),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": self._created_proxy_available_time(
                        datum=row.datum,
                        created_at=row.created_at,
                        fallback_lag_days=SOURCE_LAG_DAYS["grippeweb"],
                    ),
                    "signal_type": str(row.erkrankung_typ or "").strip().upper(),
                    "incidence": float(row.incidence or 0.0),
                }
                for row in rows
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values(["signal_type", "bundesland", "datum"], na_position="last").reset_index(drop=True)

    def _load_influenza_ifsg(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        return self._load_ifsg_signal_frame(
            model=InfluenzaData,
            start_date=start_date,
            end_date=end_date,
            lag_key="influenza_ifsg",
        )

    def _load_rsv_ifsg(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        return self._load_ifsg_signal_frame(
            model=RSVData,
            start_date=start_date,
            end_date=end_date,
            lag_key="rsv_ifsg",
        )

    def _load_ifsg_signal_frame(
        self,
        *,
        model,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        lag_key: str,
    ) -> pd.DataFrame:
        if self.db is None:
            return pd.DataFrame()
        rows = (
            self.db.query(
                model.region,
                model.datum,
                func.max(model.available_time).label("available_time"),
                func.avg(model.inzidenz).label("incidence"),
            )
            .filter(
                model.datum >= start_date.to_pydatetime(),
                model.datum <= end_date.to_pydatetime(),
                model.altersgruppe.in_(["00+", "Gesamt"]),
            )
            .group_by(
                model.region,
                model.datum,
            )
            .order_by(model.datum.asc())
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.region),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(
                        row.datum,
                        row.available_time,
                        SOURCE_LAG_DAYS[lag_key],
                    ),
                    "incidence": float(row.incidence or 0.0),
                }
                for row in rows
                if normalize_state_code(row.region)
            ]
        )
        if frame.empty:
            return frame
        sort_columns = ["bundesland", "datum"]
        if "forecast_run_timestamp" in frame.columns:
            sort_columns.append("forecast_run_timestamp")
        return frame.sort_values(sort_columns).reset_index(drop=True)

    def _load_are_konsultation(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        if self.db is None:
            return pd.DataFrame()
        rows = (
            self.db.query(
                AREKonsultation.bundesland,
                AREKonsultation.datum,
                func.max(AREKonsultation.available_time).label("available_time"),
                func.avg(AREKonsultation.konsultationsinzidenz).label("incidence"),
            )
            .filter(
                AREKonsultation.altersgruppe == "00+",
                AREKonsultation.datum >= start_date.to_pydatetime(),
                AREKonsultation.datum <= end_date.to_pydatetime(),
            )
            .group_by(
                AREKonsultation.bundesland,
                AREKonsultation.datum,
            )
            .all()
        )
        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.bundesland),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(
                        row.datum,
                        row.available_time,
                        SOURCE_LAG_DAYS["are_konsultation"],
                    ),
                    "incidence": float(row.incidence or 0.0),
                }
                for row in rows
                if normalize_state_code(row.bundesland)
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values(["bundesland", "datum"]).reset_index(drop=True)

    def _load_notaufnahme_covid(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        if self.db is None:
            return pd.DataFrame()
        rows = (
            self.db.query(NotaufnahmeSyndromData)
            .filter(
                NotaufnahmeSyndromData.syndrome == "COVID",
                NotaufnahmeSyndromData.ed_type == "all",
                NotaufnahmeSyndromData.age_group == "00+",
                NotaufnahmeSyndromData.datum >= start_date.to_pydatetime(),
                NotaufnahmeSyndromData.datum <= end_date.to_pydatetime(),
            )
            .order_by(NotaufnahmeSyndromData.datum.asc())
            .all()
        )
        frame = pd.DataFrame(
            [
                {
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": self._created_proxy_available_time(
                        datum=row.datum,
                        created_at=row.created_at,
                        fallback_lag_days=SOURCE_LAG_DAYS["notaufnahme"],
                    ),
                    "level": float(row.relative_cases or 0.0),
                    "ma7": float(
                        row.relative_cases_7day_ma
                        if row.relative_cases_7day_ma is not None
                        else row.relative_cases
                        or 0.0
                    ),
                    "expected_value": float(row.expected_value or 0.0),
                    "expected_upperbound": float(row.expected_upperbound or 0.0),
                }
                for row in rows
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values("datum").reset_index(drop=True)

    def _load_corona_test_trends(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        if self.db is None:
            return pd.DataFrame()
        rows = (
            self.db.query(
                GoogleTrendsData.datum,
                func.max(GoogleTrendsData.available_time).label("available_time"),
                func.avg(GoogleTrendsData.interest_score).label("interest_score"),
            )
            .filter(
                func.lower(GoogleTrendsData.keyword) == "corona test",
                GoogleTrendsData.region == "DE",
                GoogleTrendsData.datum >= start_date.to_pydatetime(),
                GoogleTrendsData.datum <= end_date.to_pydatetime(),
            )
            .group_by(GoogleTrendsData.datum)
            .order_by(GoogleTrendsData.datum.asc())
            .all()
        )
        frame = pd.DataFrame(
            [
                {
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(
                        row.datum,
                        row.available_time,
                        SOURCE_LAG_DAYS["google_trends"],
                    ),
                    "interest_score": float(row.interest_score or 0.0),
                }
                for row in rows
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values("datum").reset_index(drop=True)

    def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        rows = (
            self.db.query(
                WeatherData.city,
                WeatherData.datum,
                WeatherData.data_type,
                WeatherData.forecast_run_timestamp,
                WeatherData.forecast_run_id,
                WeatherData.forecast_run_identity_source,
                WeatherData.forecast_run_identity_quality,
                func.max(WeatherData.available_time).label("available_time"),
                func.max(WeatherData.created_at).label("created_at"),
                func.avg(WeatherData.temperatur).label("temp"),
                func.avg(WeatherData.luftfeuchtigkeit).label("humidity"),
            )
            .filter(
                WeatherData.datum >= start_date.to_pydatetime(),
                WeatherData.datum <= end_date.to_pydatetime(),
                WeatherData.city.in_(list(CITY_TO_BUNDESLAND.keys())),
            )
            .group_by(
                WeatherData.city,
                WeatherData.datum,
                WeatherData.data_type,
                WeatherData.forecast_run_timestamp,
                WeatherData.forecast_run_id,
                WeatherData.forecast_run_identity_source,
                WeatherData.forecast_run_identity_quality,
            )
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "bundesland": CITY_TO_BUNDESLAND.get(row.city),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(row.datum, row.available_time, 0),
                    "issue_time": (
                        pd.Timestamp(row.forecast_run_timestamp)
                        if row.forecast_run_timestamp is not None
                        else (
                            pd.Timestamp(row.created_at)
                            if row.created_at is not None
                            else pd.NaT
                        )
                    ),
                    "forecast_run_timestamp": (
                        pd.Timestamp(row.forecast_run_timestamp)
                        if row.forecast_run_timestamp is not None
                        else pd.NaT
                    ),
                    "forecast_run_id": str(row.forecast_run_id) if row.forecast_run_id is not None else None,
                    "forecast_run_identity_source": (
                        str(row.forecast_run_identity_source)
                        if row.forecast_run_identity_source
                        else (
                            WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING
                            if str(row.data_type or "") == "DAILY_FORECAST"
                            else "not_applicable"
                        )
                    ),
                    "forecast_run_identity_quality": (
                        str(row.forecast_run_identity_quality)
                        if row.forecast_run_identity_quality
                        else (
                            WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING
                            if str(row.data_type or "") == "DAILY_FORECAST"
                            else "not_applicable"
                        )
                    ),
                    "data_type": str(row.data_type or "CURRENT"),
                    "temp": float(row.temp or 0.0),
                    "humidity": float(row.humidity or 0.0),
                }
                for row in rows
                if CITY_TO_BUNDESLAND.get(row.city)
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values(["bundesland", "datum"]).reset_index(drop=True)

    def _load_pollen(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        rows = (
            self.db.query(
                PollenData.region_code,
                PollenData.datum,
                func.max(PollenData.available_time).label("available_time"),
                func.max(PollenData.pollen_index).label("max_index"),
            )
            .filter(
                PollenData.datum >= start_date.to_pydatetime(),
                PollenData.datum <= end_date.to_pydatetime(),
            )
            .group_by(PollenData.region_code, PollenData.datum)
            .all()
        )
        frame = pd.DataFrame(
            [
                {
                    "bundesland": normalize_state_code(row.region_code),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(
                        row.datum,
                        row.available_time,
                        SOURCE_LAG_DAYS["pollen"],
                    ),
                    "pollen_index": float(row.max_index or 0.0),
                }
                for row in rows
                if normalize_state_code(row.region_code)
            ]
        )
        return frame.sort_values(["bundesland", "datum"]).reset_index(drop=True) if not frame.empty else frame

    def _load_holidays(self) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
        rows = self.db.query(SchoolHolidays).all()
        holiday_ranges: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
        for row in rows:
            code = normalize_state_code(row.bundesland)
            if not code:
                continue
            holiday_ranges.setdefault(code, []).append(
                (pd.Timestamp(row.start_datum).normalize(), pd.Timestamp(row.end_datum).normalize())
            )
        return holiday_ranges

    def _build_rows(
        self,
        *,
        virus_typ: str,
        wastewater: pd.DataFrame,
        wastewater_context: dict[str, pd.DataFrame],
        truth: pd.DataFrame,
        grippeweb: pd.DataFrame,
        influenza_ifsg: pd.DataFrame,
        rsv_ifsg: pd.DataFrame,
        are: pd.DataFrame,
        notaufnahme: pd.DataFrame,
        trends: pd.DataFrame,
        weather: pd.DataFrame,
        pollen: pd.DataFrame,
        holidays: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
        state_populations: dict[str, float],
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        horizon_days: int,
        include_targets: bool,
        include_nowcast: bool,
        use_revision_adjusted: bool,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
        weather_forecast_vintage_mode: str,
        weather_forecast_metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if wastewater.empty or truth.empty:
            return []
        horizon = ensure_supported_horizon(horizon_days)
        event_config = event_definition_config_for_virus(virus_typ)

        wastewater_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in wastewater.groupby("bundesland")
        }
        wastewater_context_by_virus_state = {
            candidate_virus: {
                state: frame.sort_values("datum").reset_index(drop=True)
                for state, frame in candidate_frame.groupby("bundesland")
            }
            for candidate_virus, candidate_frame in wastewater_context.items()
            if candidate_frame is not None and not candidate_frame.empty
        }
        truth_by_state = {
            state: frame.sort_values("week_start").reset_index(drop=True)
            for state, frame in truth.groupby("bundesland")
        }
        grippeweb_by_state = {
            (signal_type, state): frame.sort_values("datum").reset_index(drop=True)
            for (signal_type, state), frame in grippeweb.dropna(subset=["bundesland"]).groupby(["signal_type", "bundesland"])
        } if not grippeweb.empty else {}
        grippeweb_national = {
            signal_type: frame.sort_values("datum").reset_index(drop=True)
            for signal_type, frame in grippeweb.loc[grippeweb["bundesland"].isna()].groupby("signal_type")
        } if not grippeweb.empty else {}
        influenza_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in influenza_ifsg.groupby("bundesland")
        } if not influenza_ifsg.empty else {}
        rsv_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in rsv_ifsg.groupby("bundesland")
        } if not rsv_ifsg.empty else {}
        are_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in are.groupby("bundesland")
        } if not are.empty else {}
        national_notaufnahme = notaufnahme.sort_values("datum").reset_index(drop=True) if not notaufnahme.empty else None
        national_trends = trends.sort_values("datum").reset_index(drop=True) if not trends.empty else None
        weather_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in weather.groupby("bundesland")
        } if not weather.empty else {}
        pollen_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in pollen.groupby("bundesland")
        } if not pollen.empty else {}

        max_sites = {
            state: max(int(frame["site_count"].max() or 0), 1)
            for state, frame in wastewater_by_state.items()
        }

        rows: list[dict[str, Any]] = []
        for state in sorted(set(wastewater_by_state) & set(truth_by_state)):
            ww_frame = wastewater_by_state[state]
            truth_frame = truth_by_state[state]
            candidate_dates = ww_frame.loc[
                (ww_frame["datum"] >= start_date) & (ww_frame["datum"] <= end_date),
                "datum",
            ].drop_duplicates().sort_values()

            for as_of in candidate_dates:
                visible_ww = ww_frame.loc[
                    (ww_frame["datum"] <= as_of) & (ww_frame["available_time"] <= as_of)
                ].copy()
                if len(visible_ww) < 8:
                    continue

                visible_truth = truth_frame.loc[truth_frame["available_date"] <= as_of].copy()
                if len(visible_truth) < 8:
                    continue

                visible_grippeweb_state = {
                    signal_type: self._visible_signal_frame(
                        grippeweb_by_state.get((signal_type, state)),
                        as_of=as_of,
                    )
                    for signal_type in ("ARE", "ILI")
                }
                visible_grippeweb_national = {
                    signal_type: self._visible_signal_frame(
                        grippeweb_national.get(signal_type),
                        as_of=as_of,
                    )
                    for signal_type in ("ARE", "ILI")
                }
                visible_influenza_ifsg = self._visible_signal_frame(
                    influenza_by_state.get(state),
                    as_of=as_of,
                )
                visible_rsv_ifsg = self._visible_signal_frame(
                    rsv_by_state.get(state),
                    as_of=as_of,
                )
                visible_are = None
                if virus_typ == "SARS-CoV-2":
                    are_frame = are_by_state.get(state)
                    if are_frame is not None and not are_frame.empty:
                        visible_are = are_frame.loc[
                            (are_frame["datum"] <= as_of) & (are_frame["available_time"] <= as_of)
                        ].copy()
                    else:
                        visible_are = pd.DataFrame()

                visible_notaufnahme = None
                if virus_typ == "SARS-CoV-2" and national_notaufnahme is not None:
                    visible_notaufnahme = national_notaufnahme.loc[
                        (national_notaufnahme["datum"] <= as_of)
                        & (national_notaufnahme["available_time"] <= as_of)
                    ].copy()

                visible_trends = None
                if virus_typ == "SARS-CoV-2" and national_trends is not None:
                    visible_trends = observed_as_of_only_rows(
                        national_trends,
                        as_of=as_of,
                    )

                target_date = self._target_date(as_of, horizon)
                target_week_start = self._target_week_start(as_of, horizon)

                target_row = truth_frame.loc[truth_frame["week_start"] == target_week_start]

                current_truth = visible_truth.iloc[-1]
                next_truth = target_row.iloc[0] if not target_row.empty else None
                truth_source = str(current_truth.get("truth_source") or "survstat_weekly")
                truth_nowcast = self.nowcast_service.evaluate_frame(
                    source_id=truth_source,
                    signal_id=truth_source,
                    frame=visible_truth,
                    as_of_date=as_of,
                    value_column="incidence",
                    reference_column="week_start",
                    available_column="available_date",
                    region_code=state,
                    metadata={"truth_source": truth_source},
                )
                effective_current_incidence = self.nowcast_service.preferred_value(
                    truth_nowcast,
                    use_revision_adjusted=self._use_revision_adjusted_for_source(
                        source_id=truth_source,
                        result=truth_nowcast,
                        revision_policy=revision_policy,
                        source_revision_policy=source_revision_policy,
                        fallback_use_revision_adjusted=use_revision_adjusted,
                    ),
                )
                baseline, mad = seasonal_baseline_and_mad(
                    truth_frame,
                    target_week_start,
                    max_history_weeks=event_config.baseline_max_history_weeks,
                    upper_quantile_cap=event_config.baseline_upper_quantile_cap,
                )
                latest_ww_snapshot = self._latest_wastewater_snapshot_by_state(wastewater_by_state, as_of)
                latest_cross_virus_snapshots = {
                    candidate_virus: self._latest_wastewater_snapshot_by_state(candidate_frames, as_of)
                    for candidate_virus, candidate_frames in wastewater_context_by_virus_state.items()
                    if candidate_virus != virus_typ
                }
                feature_row = self._build_feature_row(
                    virus_typ=virus_typ,
                    state=state,
                    as_of=as_of,
                    visible_ww=visible_ww,
                    visible_truth=visible_truth,
                    visible_grippeweb_state=visible_grippeweb_state,
                    visible_grippeweb_national=visible_grippeweb_national,
                    visible_influenza_ifsg=visible_influenza_ifsg,
                    visible_rsv_ifsg=visible_rsv_ifsg,
                    visible_are=visible_are,
                    visible_notaufnahme=visible_notaufnahme,
                    visible_trends=visible_trends,
                    weather_frame=weather_by_state.get(state),
                    pollen_frame=pollen_by_state.get(state),
                    holiday_ranges=holidays.get(state, []),
                    latest_ww_snapshot=latest_ww_snapshot,
                    latest_cross_virus_snapshots=latest_cross_virus_snapshots,
                    state_population=float(state_populations.get(state, 0.0)),
                    max_site_count=max_sites.get(state, 1),
                    horizon_days=horizon,
                    target_week_start=target_week_start,
                    current_known_incidence=float(effective_current_incidence),
                    seasonal_baseline=float(baseline),
                    seasonal_mad=float(mad),
                    include_nowcast=include_nowcast,
                    use_revision_adjusted=use_revision_adjusted,
                    revision_policy=revision_policy,
                    source_revision_policy=source_revision_policy,
                    weather_forecast_vintage_mode=weather_forecast_vintage_mode,
                    weather_forecast_metadata=weather_forecast_metadata,
                    truth_nowcast=truth_nowcast,
                )
                if feature_row is None:
                    continue

                row_payload = {
                    "virus_typ": virus_typ,
                    "bundesland": state,
                    "bundesland_name": BUNDESLAND_NAMES.get(state, state),
                    "as_of_date": pd.Timestamp(as_of).normalize(),
                    "target_date": pd.Timestamp(target_date).normalize(),
                    "target_week_start": pd.Timestamp(target_week_start).normalize(),
                    "target_window_days": [horizon, horizon],
                    "horizon_days": horizon,
                    "event_definition_version": EVENT_DEFINITION_VERSION,
                    "truth_source": str(
                        (next_truth.get("truth_source") if next_truth is not None else None)
                        or current_truth.get("truth_source")
                        or "survstat_weekly"
                    ),
                    "current_known_incidence": float(effective_current_incidence),
                    "next_week_incidence": (
                        float(next_truth["incidence"] or 0.0)
                        if include_targets and next_truth is not None
                        else np.nan
                    ),
                    "seasonal_baseline": float(baseline),
                    "seasonal_mad": float(mad),
                    **feature_row,
                }
                rows.append(row_payload)

        return rows

    def _build_feature_row(
        self,
        *,
        virus_typ: str,
        state: str,
        as_of: pd.Timestamp,
        visible_ww: pd.DataFrame,
        visible_truth: pd.DataFrame,
        visible_grippeweb_state: dict[str, pd.DataFrame],
        visible_grippeweb_national: dict[str, pd.DataFrame],
        visible_influenza_ifsg: pd.DataFrame | None,
        visible_rsv_ifsg: pd.DataFrame | None,
        visible_are: pd.DataFrame | None,
        visible_notaufnahme: pd.DataFrame | None,
        visible_trends: pd.DataFrame | None,
        weather_frame: pd.DataFrame | None,
        pollen_frame: pd.DataFrame | None,
        holiday_ranges: list[tuple[pd.Timestamp, pd.Timestamp]],
        latest_ww_snapshot: dict[str, dict[str, float]],
        latest_cross_virus_snapshots: dict[str, dict[str, dict[str, float]]],
        state_population: float,
        max_site_count: int,
        horizon_days: int,
        target_week_start: pd.Timestamp,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
        include_nowcast: bool,
        use_revision_adjusted: bool,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
        weather_forecast_vintage_mode: str,
        weather_forecast_metadata: dict[str, Any],
        truth_nowcast: NowcastResult,
    ) -> dict[str, Any] | None:
        nowcast_features: dict[str, float] = {}
        ww_latest = visible_ww.iloc[-1]
        ww_nowcast = self.nowcast_service.evaluate_frame(
            source_id="wastewater",
            signal_id=virus_typ,
            frame=visible_ww,
            as_of_date=as_of,
            value_column="viral_load",
            region_code=state,
            metadata={"virus_typ": virus_typ},
        )
        ww_level = self.nowcast_service.preferred_value(
            ww_nowcast,
            use_revision_adjusted=self._use_revision_adjusted_for_source(
                source_id="wastewater",
                result=ww_nowcast,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
                fallback_use_revision_adjusted=use_revision_adjusted,
            ),
        )
        ww_lag4 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=4), "viral_load")
        ww_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_load")
        ww_lag14 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=14), "viral_load")
        ww_site_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "site_count")
        ww_under_bg_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "under_bg_share")
        ww_dispersion_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_std")
        ww_window7 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=7)]
        ww_window28 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=28)]
        ww_site_count = float(ww_latest["site_count"] or 0.0)
        ww_slope7d = float((ww_level - ww_lag7) / max(abs(ww_lag7), 1.0))
        ww_slope14d = float((ww_lag7 - ww_lag14) / max(abs(ww_lag14), 1.0))
        ww_acceleration7d = float(ww_slope7d - ww_slope14d)
        if include_nowcast:
            nowcast_features.update(self._nowcast_feature_family("ww_level", ww_nowcast))
            nowcast_features.update(
                self._nowcast_feature_family("survstat_current_incidence", truth_nowcast)
            )

        truth_lag1 = self._latest_truth_value(visible_truth, lag_weeks=1)
        truth_lag2 = self._latest_truth_value(visible_truth, lag_weeks=2)
        truth_lag4 = self._latest_truth_value(visible_truth, lag_weeks=4)
        truth_lag8 = self._latest_truth_value(visible_truth, lag_weeks=8)

        neighbor_values = [
            snapshot["viral_load"]
            for code in REGIONAL_NEIGHBORS.get(state, [])
            if (snapshot := latest_ww_snapshot.get(code))
        ]
        neighbor_slopes = [
            snapshot["slope7d"]
            for code in REGIONAL_NEIGHBORS.get(state, [])
            if (snapshot := latest_ww_snapshot.get(code))
        ]
        national_values = [snapshot["viral_load"] for snapshot in latest_ww_snapshot.values()]
        national_slopes = [snapshot["slope7d"] for snapshot in latest_ww_snapshot.values()]
        national_accelerations = [snapshot["acceleration7d"] for snapshot in latest_ww_snapshot.values()]
        neighbor_mean = float(np.mean(neighbor_values)) if neighbor_values else 0.0
        national_mean = float(np.mean(national_values)) if national_values else 0.0
        site_coverage_vs_28d = float(
            ww_site_count / max(float(ww_window28["site_count"].median() or 0.0), 1.0)
        )
        state_population_millions = float(state_population / 1_000_000.0) if state_population > 0 else 0.0
        cross_virus_features = self._cross_virus_features(
            target_virus=virus_typ,
            state=state,
            latest_cross_virus_snapshots=latest_cross_virus_snapshots,
        )

        weather_features = self._weather_features(
            weather_frame,
            as_of,
            horizon_days=horizon_days,
            vintage_mode=weather_forecast_vintage_mode,
            vintage_metadata=weather_forecast_metadata,
        )
        pollen_context = self._pollen_context(pollen_frame, as_of)
        holiday_share = self._holiday_share_in_target_window(
            holiday_ranges,
            as_of,
            horizon_days=horizon_days,
        )
        grippeweb_features = self._grippeweb_context_features(
            state=state,
            as_of=as_of,
            visible_state_signals=visible_grippeweb_state,
            visible_national_signals=visible_grippeweb_national,
            current_known_incidence=current_known_incidence,
            seasonal_baseline=seasonal_baseline,
            seasonal_mad=seasonal_mad,
            include_nowcast=include_nowcast,
            use_revision_adjusted=use_revision_adjusted,
            revision_policy=revision_policy,
            source_revision_policy=source_revision_policy,
        )
        virus_specific_ifsg_features = self._virus_specific_ifsg_features(
            virus_typ=virus_typ,
            state=state,
            as_of=as_of,
            visible_influenza_ifsg=visible_influenza_ifsg,
            visible_rsv_ifsg=visible_rsv_ifsg,
            current_known_incidence=current_known_incidence,
            seasonal_baseline=seasonal_baseline,
            seasonal_mad=seasonal_mad,
            include_nowcast=include_nowcast,
            use_revision_adjusted=use_revision_adjusted,
            revision_policy=revision_policy,
            source_revision_policy=source_revision_policy,
        )
        sars_context_features = self._sars_context_features(
            virus_typ=virus_typ,
            state=state,
            as_of=as_of,
            visible_are=visible_are,
            visible_notaufnahme=visible_notaufnahme,
            visible_trends=visible_trends,
            ww_level=ww_level,
            ww_slope7d=ww_slope7d,
            current_known_incidence=current_known_incidence,
            seasonal_baseline=seasonal_baseline,
            seasonal_mad=seasonal_mad,
            include_nowcast=include_nowcast,
            use_revision_adjusted=use_revision_adjusted,
            revision_policy=revision_policy,
            source_revision_policy=source_revision_policy,
        )
        if include_nowcast:
            weather_nowcast = self._manual_nowcast_result(
                source_id="weather",
                signal_id="forecast_temp_3_7",
                region_code=state,
                as_of=as_of,
                raw_value=float(weather_features.get("weather_forecast_temp_3_7") or 0.0),
                reference_date=self._latest_reference_date(weather_frame, as_of=as_of),
                available_time=self._latest_available_time(weather_frame, as_of=as_of),
                coverage_ratio=1.0 if weather_frame is not None and not weather_frame.empty else 0.0,
            )
            pollen_nowcast = self._manual_nowcast_result(
                source_id="pollen",
                signal_id="context_score",
                region_code=state,
                as_of=as_of,
                raw_value=float(pollen_context),
                reference_date=self._latest_reference_date(pollen_frame, as_of=as_of),
                available_time=self._latest_available_time(pollen_frame, as_of=as_of),
                coverage_ratio=1.0 if pollen_frame is not None and not pollen_frame.empty else 0.0,
            )
            holiday_nowcast = self._manual_nowcast_result(
                source_id="school_holidays",
                signal_id="target_window_share",
                region_code=state,
                as_of=as_of,
                raw_value=float(holiday_share),
                reference_date=as_of,
                available_time=as_of,
                coverage_ratio=1.0,
            )
            nowcast_features.update(self._nowcast_feature_family("weather_context", weather_nowcast))
            nowcast_features.update(self._nowcast_feature_family("pollen_context", pollen_nowcast))
            nowcast_features.update(self._nowcast_feature_family("holiday_context", holiday_nowcast))

        return {
            "ww_level": ww_level,
            "ww_lag4d": float(ww_lag4),
            "ww_lag7d": float(ww_lag7),
            "ww_lag14d": float(ww_lag14),
            "ww_slope7d": ww_slope7d,
            "ww_acceleration7d": ww_acceleration7d,
            "ww_mean7d": float(ww_window7["viral_load"].mean() or 0.0),
            "ww_std7d": float(ww_window7["viral_load"].std(ddof=0) or 0.0),
            "ww_level_vs_28d_median": float(
                ww_level - float(ww_window28["viral_load"].median() or 0.0)
            ),
            "ww_site_count": ww_site_count,
            "ww_site_coverage_ratio": float(ww_site_count / max(float(max_site_count), 1.0)),
            "ww_site_coverage_vs_28d": site_coverage_vs_28d,
            "ww_site_count_delta7d": float(ww_site_count - ww_site_lag7),
            "ww_site_count_ratio7d": float((ww_site_count - ww_site_lag7) / max(abs(ww_site_lag7), 1.0)),
            "ww_missing_days7d": self._missing_days_in_window(visible_ww, as_of, 7),
            "ww_missing_days14d": self._missing_days_in_window(visible_ww, as_of, 14),
            "ww_observation_lag_days": float(max((pd.Timestamp(as_of) - pd.Timestamp(ww_latest["datum"])).days, 0)),
            "ww_coverage_break_flag": float(site_coverage_vs_28d < 0.75),
            "ww_under_bg_share7d": float(ww_window7["under_bg_share"].mean() or 0.0),
            "ww_under_bg_trend7d": float(float(ww_latest["under_bg_share"] or 0.0) - ww_under_bg_lag7),
            "ww_regional_dispersion7d": float(ww_window7["viral_std"].mean() or 0.0),
            "ww_regional_dispersion_delta7d": float(float(ww_latest["viral_std"] or 0.0) - ww_dispersion_lag7),
            "survstat_current_incidence": float(current_known_incidence),
            "survstat_lag1w": float(truth_lag1),
            "survstat_lag2w": float(truth_lag2),
            "survstat_lag4w": float(truth_lag4),
            "survstat_lag8w": float(truth_lag8),
            "survstat_momentum_2w": float((truth_lag1 - truth_lag2) / max(abs(truth_lag2), 1.0)),
            "survstat_momentum_4w": float((truth_lag1 - truth_lag4) / max(abs(truth_lag4), 1.0)),
            "survstat_seasonal_baseline": float(seasonal_baseline),
            "survstat_seasonal_mad": float(seasonal_mad),
            "survstat_baseline_gap": float(current_known_incidence - seasonal_baseline),
            "survstat_baseline_zscore": float((current_known_incidence - seasonal_baseline) / max(seasonal_mad, 1.0)),
            "neighbor_ww_level": neighbor_mean,
            "neighbor_ww_slope7d": float(np.mean(neighbor_slopes)) if neighbor_slopes else 0.0,
            "national_ww_level": national_mean,
            "national_ww_slope7d": float(np.mean(national_slopes)) if national_slopes else 0.0,
            "national_ww_acceleration7d": float(np.mean(national_accelerations)) if national_accelerations else 0.0,
            "ww_relative_to_neighbor_mean": float(ww_level - neighbor_mean),
            "ww_relative_to_national": float(ww_level - national_mean),
            "ww_share_of_national": float(ww_level / max(abs(national_mean), 1.0)),
            "state_population_millions": state_population_millions,
            "ww_sites_per_million": float(ww_site_count / max(state_population_millions, 0.1)),
            "state_neighbor_count": float(len(REGIONAL_NEIGHBORS.get(state, []))),
            "state_is_city_state": float(state in {"BE", "HB", "HH"}),
            "target_holiday_share": float(holiday_share),
            "target_holiday_any": float(holiday_share > 0.0),
            "target_week_iso": float(target_week_start.isocalendar().week),
            "pollen_context_score": float(pollen_context),
            **weather_features,
            **cross_virus_features,
            **grippeweb_features,
            **virus_specific_ifsg_features,
            **sars_context_features,
            **nowcast_features,
        }

    @staticmethod
    def _created_proxy_available_time(
        *,
        datum: datetime | pd.Timestamp,
        created_at: datetime | pd.Timestamp | None,
        fallback_lag_days: int = 0,
        max_created_delay_days: int = 14,
    ) -> pd.Timestamp:
        base = effective_available_time(datum, None, fallback_lag_days)
        if created_at is None or pd.isna(created_at):
            return base
        created_ts = pd.Timestamp(created_at)
        if created_ts <= base + pd.Timedelta(days=max_created_delay_days):
            return created_ts
        return base

    @staticmethod
    def _nowcast_feature_family(prefix: str, result: NowcastResult) -> dict[str, float]:
        return {
            f"{prefix}_raw": float(result.raw_observed_value),
            f"{prefix}_nowcast": float(result.revision_adjusted_value),
            f"{prefix}_revision_risk": float(result.revision_risk_score),
            f"{prefix}_freshness_days": float(result.source_freshness_days),
            f"{prefix}_usable_confidence": float(result.usable_confidence_score),
            f"{prefix}_usable": float(result.usable_for_forecast),
            f"{prefix}_coverage_ratio": float(result.coverage_ratio),
        }

    @staticmethod
    def _resolve_revision_policy(
        *,
        revision_policy: str | None,
        use_revision_adjusted: bool,
    ) -> str:
        candidate = str(revision_policy or "").strip().lower()
        if candidate in {"raw", "adjusted", "adaptive"}:
            return candidate
        return "adjusted" if use_revision_adjusted else "raw"

    @staticmethod
    def _use_revision_adjusted_for_source(
        *,
        source_id: str,
        result: NowcastResult,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
        fallback_use_revision_adjusted: bool,
    ) -> bool:
        source_override = str((source_revision_policy or {}).get(source_id) or "").strip().lower()
        effective_policy = source_override or str(revision_policy or "").strip().lower()
        if effective_policy == "adjusted":
            return True
        if effective_policy == "raw":
            return False
        if effective_policy == "adaptive":
            return bool(result.correction_applied and result.usable_for_forecast)
        return bool(fallback_use_revision_adjusted)

    def _manual_nowcast_result(
        self,
        *,
        source_id: str,
        signal_id: str,
        region_code: str | None,
        as_of: pd.Timestamp,
        raw_value: float,
        reference_date: pd.Timestamp | datetime | None,
        available_time: pd.Timestamp | datetime | None,
        coverage_ratio: float,
    ) -> NowcastResult:
        if reference_date is None or available_time is None:
            return self.nowcast_service.evaluate_missing(
                source_id=source_id,
                signal_id=signal_id,
                region_code=region_code,
                as_of_date=as_of,
            )
        observation = NowcastObservation(
            source_id=source_id,
            signal_id=signal_id,
            region_code=region_code,
            reference_date=pd.Timestamp(reference_date).to_pydatetime(),
            as_of_date=pd.Timestamp(as_of).to_pydatetime(),
            raw_value=float(raw_value),
            effective_available_time=pd.Timestamp(available_time).to_pydatetime(),
            timing_provenance=self.nowcast_service.get_config(source_id).timing_provenance,
            coverage_ratio=float(coverage_ratio),
        )
        return self.nowcast_service.evaluate(observation)

    @staticmethod
    def _latest_reference_date(
        frame: pd.DataFrame | None,
        *,
        as_of: pd.Timestamp,
        reference_column: str = "datum",
    ) -> pd.Timestamp | None:
        if frame is None or frame.empty or reference_column not in frame.columns:
            return None
        visible = frame.loc[pd.to_datetime(frame[reference_column]).dt.normalize() <= as_of]
        if visible.empty:
            return None
        return pd.Timestamp(visible[reference_column].max()).normalize()

    @staticmethod
    def _latest_available_time(
        frame: pd.DataFrame | None,
        *,
        as_of: pd.Timestamp,
        available_column: str = "available_time",
    ) -> pd.Timestamp | None:
        if frame is None or frame.empty:
            return None
        if available_column not in frame.columns:
            return RegionalFeatureBuilder._latest_reference_date(frame, as_of=as_of)
        visible = frame.loc[pd.to_datetime(frame[available_column]).dt.normalize() <= as_of]
        if visible.empty:
            return None
        return pd.Timestamp(visible[available_column].max())

    @staticmethod
    def _seasonal_signal_baseline(
        frame: pd.DataFrame | None,
        *,
        target_date: pd.Timestamp,
        value_col: str,
    ) -> tuple[float, float]:
        if frame is None or frame.empty:
            return 0.0, 1.0
        hist = frame.loc[frame["datum"] < target_date, ["datum", value_col]].copy()
        if hist.empty:
            return 0.0, 1.0
        iso_week = int(target_date.isocalendar().week)
        hist["iso_week"] = hist["datum"].dt.isocalendar().week.astype(int)
        seasonal = hist.loc[
            hist["iso_week"].apply(lambda value: circular_week_distance(value, iso_week) <= 1)
        ]
        if len(seasonal) < 5:
            seasonal = hist.tail(12)
        if seasonal.empty:
            seasonal = hist
        values = seasonal[value_col].astype(float).dropna().to_numpy()
        baseline = float(np.median(values)) if len(values) else 0.0
        mad = float(np.median(np.abs(values - baseline))) if len(values) else 1.0
        return baseline, max(mad, 1.0)

    def _sars_context_features(
        self,
        *,
        virus_typ: str,
        state: str,
        as_of: pd.Timestamp,
        visible_are: pd.DataFrame | None,
        visible_notaufnahme: pd.DataFrame | None,
        visible_trends: pd.DataFrame | None,
        ww_level: float,
        ww_slope7d: float,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
        include_nowcast: bool,
        use_revision_adjusted: bool,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
    ) -> dict[str, float]:
        if virus_typ != "SARS-CoV-2":
            return {}

        are_frame = visible_are if visible_are is not None else pd.DataFrame()
        are_nowcast = self.nowcast_service.evaluate_frame(
            source_id="are_konsultation",
            signal_id="ARE",
            frame=are_frame,
            as_of_date=as_of,
            value_column="incidence",
            region_code=state,
        )
        are_level = self.nowcast_service.preferred_value(
            are_nowcast,
            use_revision_adjusted=self._use_revision_adjusted_for_source(
                source_id="are_konsultation",
                result=are_nowcast,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
                fallback_use_revision_adjusted=use_revision_adjusted,
            ),
        )
        are_lag7 = self._latest_value_as_of(are_frame, as_of - pd.Timedelta(days=7), "incidence")
        are_momentum_1w = float((are_level - are_lag7) / max(abs(are_lag7), 1.0))
        are_baseline, are_mad = self._seasonal_signal_baseline(
            are_frame,
            target_date=as_of,
            value_col="incidence",
        )
        are_baseline_gap = float(are_level - are_baseline)
        are_baseline_zscore = float(are_baseline_gap / max(are_mad, 1.0))

        notaufnahme_frame = visible_notaufnahme if visible_notaufnahme is not None else pd.DataFrame()
        notaufnahme_nowcast = self.nowcast_service.evaluate_frame(
            source_id="notaufnahme",
            signal_id="COVID",
            frame=notaufnahme_frame,
            as_of_date=as_of,
            value_column="ma7",
            region_code="DE",
        )
        notaufnahme_level = self._latest_value_as_of(notaufnahme_frame, as_of, "level")
        notaufnahme_ma7 = self.nowcast_service.preferred_value(
            notaufnahme_nowcast,
            use_revision_adjusted=self._use_revision_adjusted_for_source(
                source_id="notaufnahme",
                result=notaufnahme_nowcast,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
                fallback_use_revision_adjusted=use_revision_adjusted,
            ),
        )
        notaufnahme_ma7_lag7 = self._latest_value_as_of(notaufnahme_frame, as_of - pd.Timedelta(days=7), "ma7")
        notaufnahme_expected = self._latest_value_as_of(notaufnahme_frame, as_of, "expected_value")
        notaufnahme_upper = self._latest_value_as_of(notaufnahme_frame, as_of, "expected_upperbound")
        notaufnahme_momentum_7d = float(
            (notaufnahme_ma7 - notaufnahme_ma7_lag7) / max(abs(notaufnahme_ma7_lag7), 1.0)
        )

        trends_frame = visible_trends if visible_trends is not None else pd.DataFrame()
        trends_nowcast = self.nowcast_service.evaluate_frame(
            source_id="google_trends",
            signal_id="corona test",
            frame=trends_frame,
            as_of_date=as_of,
            value_column="interest_score",
            region_code="DE",
        )
        trends_level = self.nowcast_service.preferred_value(
            trends_nowcast,
            use_revision_adjusted=self._use_revision_adjusted_for_source(
                source_id="google_trends",
                result=trends_nowcast,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
                fallback_use_revision_adjusted=use_revision_adjusted,
            ),
        )
        trends_recent14 = self._window_mean(trends_frame, as_of=as_of, window_days=14, column="interest_score")
        trends_previous14 = self._window_mean(
            trends_frame,
            as_of=as_of - pd.Timedelta(days=14),
            window_days=14,
            column="interest_score",
        )
        trends_recent7 = self._window_mean(trends_frame, as_of=as_of, window_days=7, column="interest_score")
        trends_previous7 = self._window_mean(
            trends_frame,
            as_of=as_of - pd.Timedelta(days=7),
            window_days=7,
            column="interest_score",
        )
        trends_momentum_14_28 = float(
            (trends_recent14 - trends_previous14) / max(abs(trends_previous14), 1.0)
        )
        trends_momentum_7_14 = float(
            (trends_recent7 - trends_previous7) / max(abs(trends_previous7), 1.0)
        )
        survstat_baseline_zscore = float((current_known_incidence - seasonal_baseline) / max(seasonal_mad, 1.0))

        features = {
            "sars_are_available": float(not are_frame.empty),
            "sars_notaufnahme_available": float(not notaufnahme_frame.empty),
            "sars_trends_available": float(not trends_frame.empty),
            "sars_are_level": float(are_level),
            "sars_are_lag7d": float(are_lag7),
            "sars_are_momentum_1w": are_momentum_1w,
            "sars_are_baseline_gap": are_baseline_gap,
            "sars_are_baseline_zscore": are_baseline_zscore,
            "sars_notaufnahme_level": float(notaufnahme_level),
            "sars_notaufnahme_ma7": float(notaufnahme_ma7),
            "sars_notaufnahme_momentum_7d": notaufnahme_momentum_7d,
            "sars_notaufnahme_expected_gap": float(notaufnahme_ma7 - notaufnahme_expected),
            "sars_notaufnahme_upper_gap": float(notaufnahme_ma7 - notaufnahme_upper),
            "sars_notaufnahme_breach_flag": float(notaufnahme_ma7 > notaufnahme_upper and notaufnahme_upper > 0.0),
            "sars_trends_level": float(trends_level),
            "sars_trends_momentum_14_28": trends_momentum_14_28,
            "sars_trends_acceleration_7d": float(trends_momentum_7_14 - trends_momentum_14_28),
            "sars_ww_are_log_gap": float(np.log1p(max(ww_level, 0.0)) - np.log1p(max(are_level, 0.0))),
            "sars_ww_are_trend_gap": float(ww_slope7d - are_momentum_1w),
            "sars_ww_notaufnahme_log_gap": float(
                np.log1p(max(ww_level, 0.0)) - np.log1p(max(notaufnahme_ma7, 0.0))
            ),
            "sars_ww_notaufnahme_trend_gap": float(ww_slope7d - notaufnahme_momentum_7d),
            "sars_are_survstat_log_gap": float(
                np.log1p(max(are_level, 0.0)) - np.log1p(max(current_known_incidence, 0.0))
            ),
            "sars_are_survstat_zscore_gap": float(are_baseline_zscore - survstat_baseline_zscore),
        }
        if include_nowcast:
            features.update(self._nowcast_feature_family("sars_are", are_nowcast))
            features.update(self._nowcast_feature_family("sars_notaufnahme", notaufnahme_nowcast))
            features.update(self._nowcast_feature_family("sars_trends", trends_nowcast))
        return features

    @staticmethod
    def _visible_signal_frame(frame: pd.DataFrame | None, *, as_of: pd.Timestamp) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        visible = frame.loc[frame["datum"] <= as_of].copy()
        if "available_time" in visible.columns:
            visible = visible.loc[visible["available_time"] <= as_of].copy()
        return visible.reset_index(drop=True)

    def _grippeweb_context_features(
        self,
        *,
        state: str,
        as_of: pd.Timestamp,
        visible_state_signals: dict[str, pd.DataFrame],
        visible_national_signals: dict[str, pd.DataFrame],
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
        include_nowcast: bool,
        use_revision_adjusted: bool,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
    ) -> dict[str, float]:
        features: dict[str, float] = {}
        for signal_type in ("ARE", "ILI"):
            signal_slug = signal_type.lower()
            state_frame = visible_state_signals.get(signal_type)
            if state_frame is None:
                state_frame = pd.DataFrame()
            national_frame = visible_national_signals.get(signal_type)
            if national_frame is None:
                national_frame = pd.DataFrame()
            primary_frame = state_frame if not state_frame.empty else national_frame
            features.update(
                self._signal_feature_family(
                    prefix=f"grippeweb_{signal_slug}",
                    frame=primary_frame,
                    as_of=as_of,
                    current_known_incidence=current_known_incidence,
                    seasonal_baseline=seasonal_baseline,
                    seasonal_mad=seasonal_mad,
                    source_id="grippeweb",
                    signal_id=signal_type,
                    region_code=state if not state_frame.empty else "DE",
                    include_nowcast=include_nowcast,
                    use_revision_adjusted=use_revision_adjusted,
                    revision_policy=revision_policy,
                    source_revision_policy=source_revision_policy,
                )
            )
            national_level = self._latest_value_as_of(national_frame, as_of, "incidence")
            state_level = self._latest_value_as_of(state_frame, as_of, "incidence")
            features[f"grippeweb_{signal_slug}_national_level"] = float(national_level)
            features[f"grippeweb_{signal_slug}_national_momentum_1w"] = float(
                self._relative_delta(
                    national_level,
                    self._latest_value_as_of(national_frame, as_of - pd.Timedelta(days=7), "incidence"),
                )
            )
            features[f"grippeweb_{signal_slug}_state_vs_national"] = float(state_level - national_level)
        return features

    def _virus_specific_ifsg_features(
        self,
        *,
        virus_typ: str,
        state: str,
        as_of: pd.Timestamp,
        visible_influenza_ifsg: pd.DataFrame | None,
        visible_rsv_ifsg: pd.DataFrame | None,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
        include_nowcast: bool,
        use_revision_adjusted: bool,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
    ) -> dict[str, float]:
        if virus_typ in {"Influenza A", "Influenza B"}:
            return self._signal_feature_family(
                prefix="ifsg_influenza",
                frame=visible_influenza_ifsg,
                as_of=as_of,
                current_known_incidence=current_known_incidence,
                seasonal_baseline=seasonal_baseline,
                seasonal_mad=seasonal_mad,
                source_id="ifsg_influenza",
                signal_id="Influenza",
                region_code=state,
                include_nowcast=include_nowcast,
                use_revision_adjusted=use_revision_adjusted,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
            )
        if virus_typ == "RSV A":
            return self._signal_feature_family(
                prefix="ifsg_rsv",
                frame=visible_rsv_ifsg,
                as_of=as_of,
                current_known_incidence=current_known_incidence,
                seasonal_baseline=seasonal_baseline,
                seasonal_mad=seasonal_mad,
                source_id="ifsg_rsv",
                signal_id="RSV",
                region_code=state,
                include_nowcast=include_nowcast,
                use_revision_adjusted=use_revision_adjusted,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
            )
        return {}

    def _signal_feature_family(
        self,
        *,
        prefix: str,
        frame: pd.DataFrame | None,
        as_of: pd.Timestamp,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
        source_id: str,
        signal_id: str,
        region_code: str | None,
        include_nowcast: bool,
        use_revision_adjusted: bool,
        revision_policy: str,
        source_revision_policy: dict[str, str] | None,
    ) -> dict[str, float]:
        signal_frame = frame if frame is not None else pd.DataFrame()
        result = self.nowcast_service.evaluate_frame(
            source_id=source_id,
            signal_id=signal_id,
            frame=signal_frame,
            as_of_date=as_of,
            value_column="incidence",
            region_code=region_code,
        )
        level = self.nowcast_service.preferred_value(
            result,
            use_revision_adjusted=self._use_revision_adjusted_for_source(
                source_id=source_id,
                result=result,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
                fallback_use_revision_adjusted=use_revision_adjusted,
            ),
        )
        lag7 = self._latest_value_as_of(signal_frame, as_of - pd.Timedelta(days=7), "incidence")
        baseline, mad = self._seasonal_signal_baseline(
            signal_frame,
            target_date=as_of,
            value_col="incidence",
        )
        baseline_gap = float(level - baseline)
        baseline_zscore = float(baseline_gap / max(mad, 1.0))
        survstat_zscore = float((current_known_incidence - seasonal_baseline) / max(seasonal_mad, 1.0))
        features = {
            f"{prefix}_available": float(not signal_frame.empty),
            f"{prefix}_level": float(level),
            f"{prefix}_lag7d": float(lag7),
            f"{prefix}_momentum_1w": float(self._relative_delta(level, lag7)),
            f"{prefix}_baseline_gap": baseline_gap,
            f"{prefix}_baseline_zscore": baseline_zscore,
            f"{prefix}_survstat_log_gap": float(
                np.log1p(max(level, 0.0)) - np.log1p(max(current_known_incidence, 0.0))
            ),
            f"{prefix}_survstat_zscore_gap": float(baseline_zscore - survstat_zscore),
        }
        if include_nowcast:
            features.update(self._nowcast_feature_family(prefix, result))
        return features

    @staticmethod
    def _relative_delta(current_value: float, previous_value: float) -> float:
        return float((current_value - previous_value) / max(abs(previous_value), 1.0))

    @staticmethod
    def _latest_value_as_of(frame: pd.DataFrame, as_of: pd.Timestamp, column: str) -> float:
        if frame is None or frame.empty or "datum" not in frame.columns or column not in frame.columns:
            return 0.0
        visible = frame.loc[frame["datum"] <= as_of]
        if visible.empty:
            return 0.0
        return float(visible.iloc[-1][column] or 0.0)

    @staticmethod
    def _window_mean(frame: pd.DataFrame | None, *, as_of: pd.Timestamp, window_days: int, column: str) -> float:
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

    @staticmethod
    def _latest_truth_value(frame: pd.DataFrame, lag_weeks: int) -> float:
        if len(frame) <= lag_weeks:
            return 0.0
        return float(frame.iloc[-(lag_weeks + 1)]["incidence"] or 0.0)

    @staticmethod
    def _latest_wastewater_by_state(
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

    @classmethod
    def _latest_wastewater_snapshot_by_state(
        cls,
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
            lag7 = cls._latest_value_as_of(visible, as_of - pd.Timedelta(days=7), "viral_load")
            lag14 = cls._latest_value_as_of(visible, as_of - pd.Timedelta(days=14), "viral_load")
            slope7 = float((level - lag7) / max(abs(lag7), 1.0))
            slope14 = float((lag7 - lag14) / max(abs(lag14), 1.0))
            latest[state] = {
                "viral_load": level,
                "slope7d": slope7,
                "acceleration7d": float(slope7 - slope14),
            }
        return latest

    @staticmethod
    def _missing_days_in_window(frame: pd.DataFrame, as_of: pd.Timestamp, window_days: int) -> float:
        if window_days <= 0:
            return 0.0
        window_start = as_of - pd.Timedelta(days=window_days - 1)
        visible = frame.loc[(frame["datum"] >= window_start) & (frame["datum"] <= as_of)]
        observed_days = int(visible["datum"].nunique()) if not visible.empty else 0
        return float(max(window_days - observed_days, 0))

    def _cross_virus_features(
        self,
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

    @staticmethod
    def _weather_features(
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
        target_date = RegionalFeatureBuilder._target_date(as_of, horizon_days)
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
        if not raw_forecast_candidates.empty and forecast_candidates.empty:
            logger.warning(
                "Dropping future weather forecast rows without issue-time semantics for as_of=%s.",
                as_of.date(),
            )

        obs_temp = float(observed.tail(7)["temp"].mean() or 0.0) if not observed.empty else 0.0
        obs_humidity = float(observed.tail(7)["humidity"].mean() or 0.0) if not observed.empty else 0.0
        if forecast_candidates.empty:
            forecast = forecast_candidates.copy()
        else:
            forecast = forecast_candidates.loc[forecast_candidates["datum"] == target_date].copy()
        if forecast.empty and not forecast_candidates.empty:
            forecast_candidates["target_distance_days"] = (
                forecast_candidates["datum"] - target_date
            ).abs() / pd.Timedelta(days=1)
            forecast = forecast_candidates.sort_values(["target_distance_days", "datum"]).head(3)
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

    @staticmethod
    def _pollen_context(pollen_frame: pd.DataFrame | None, as_of: pd.Timestamp) -> float:
        if pollen_frame is None or pollen_frame.empty:
            return 0.0
        visible = observed_as_of_only_rows(
            pollen_frame,
            as_of=as_of,
        )
        if visible.empty:
            return 0.0
        return float(visible.tail(3)["pollen_index"].mean() or 0.0)

    @staticmethod
    def _holiday_share_in_target_window(
        holiday_ranges: list[tuple[pd.Timestamp, pd.Timestamp]],
        as_of: pd.Timestamp,
        *,
        horizon_days: int,
    ) -> float:
        target_date = RegionalFeatureBuilder._target_date(as_of, horizon_days)
        return float(any(start <= target_date <= end for start, end in holiday_ranges))

    @staticmethod
    def _target_date(as_of: pd.Timestamp, horizon_days: int) -> pd.Timestamp:
        horizon = ensure_supported_horizon(horizon_days)
        return (pd.Timestamp(as_of) + pd.Timedelta(days=horizon)).normalize()

    @classmethod
    def _target_week_start(cls, as_of: pd.Timestamp, horizon_days: int) -> pd.Timestamp:
        target_date = cls._target_date(as_of, horizon_days)
        return (target_date - pd.Timedelta(days=int(target_date.weekday()))).normalize()

    @staticmethod
    def _week_start_from_label(week_label: str) -> pd.Timestamp:
        year_text, week_text = str(week_label).split("_", 1)
        return pd.Timestamp.fromisocalendar(int(year_text), max(int(week_text), 1), 1).normalize()

    @staticmethod
    def _finalize_panel(rows: list[dict[str, Any]]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()

        frame = pd.DataFrame(rows).sort_values(["as_of_date", "bundesland"]).reset_index(drop=True)
        for code in ALL_BUNDESLAENDER:
            frame[f"state_{code}"] = (frame["bundesland"] == code).astype(float)
        return frame
