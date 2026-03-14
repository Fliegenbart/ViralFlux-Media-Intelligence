"""Regional as-of panel dataset builder for pooled outbreak forecasting."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Float, func
from sqlalchemy.orm import Session

from app.models.database import (
    KreisEinwohner,
    PollenData,
    SchoolHolidays,
    SurvstatKreisData,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.ml.forecast_service import SURVSTAT_VIRUS_MAP
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    CITY_TO_BUNDESLAND,
    EVENT_DEFINITION_VERSION,
    REGIONAL_NEIGHBORS,
    SOURCE_LAG_DAYS,
    STATE_NAME_TO_CODE,
    TARGET_WINDOW_DAYS,
    effective_available_time,
    first_week_start_in_window,
    normalize_state_code,
    seasonal_baseline_and_mad,
)

logger = logging.getLogger(__name__)


class RegionalFeatureBuilder:
    """Build leakage-safe panel datasets for regional outbreak forecasting."""

    def __init__(self, db: Session):
        self.db = db

    def build_panel_training_data(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
    ) -> pd.DataFrame:
        """Build pooled training rows across all Bundesländer."""
        end_date = pd.Timestamp(datetime.utcnow()).normalize()
        start_date = end_date - pd.Timedelta(days=lookback_days)
        truth_start = start_date - pd.Timedelta(days=730)

        wastewater = self._load_wastewater_daily(virus_typ, truth_start)
        truth = self._load_truth_series(virus_typ, truth_start)
        weather = self._load_weather(truth_start, end_date + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        pollen = self._load_pollen(truth_start, end_date + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        holidays = self._load_holidays()

        rows = self._build_rows(
            virus_typ=virus_typ,
            wastewater=wastewater,
            truth=truth,
            weather=weather,
            pollen=pollen,
            holidays=holidays,
            start_date=start_date,
            end_date=end_date,
            include_targets=True,
        )
        return self._finalize_panel(rows)

    def build_inference_panel(
        self,
        virus_typ: str = "Influenza A",
        as_of_date: datetime | None = None,
        lookback_days: int = 180,
    ) -> pd.DataFrame:
        """Build one inference row per Bundesland for a shared as-of date."""
        effective_as_of = pd.Timestamp(as_of_date or datetime.utcnow()).normalize()
        start_date = effective_as_of - pd.Timedelta(days=lookback_days)
        truth_start = start_date - pd.Timedelta(days=730)

        wastewater = self._load_wastewater_daily(virus_typ, truth_start)
        truth = self._load_truth_series(virus_typ, truth_start)
        weather = self._load_weather(truth_start, effective_as_of + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        pollen = self._load_pollen(truth_start, effective_as_of + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        holidays = self._load_holidays()

        rows = self._build_rows(
            virus_typ=virus_typ,
            wastewater=wastewater,
            truth=truth,
            weather=weather,
            pollen=pollen,
            holidays=holidays,
            start_date=effective_as_of,
            end_date=effective_as_of,
            include_targets=False,
        )
        return self._finalize_panel(rows)

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
            return pd.Timestamp(datetime.utcnow()).normalize()
        return effective_available_time(
            row.datum or datetime.utcnow(),
            row.available_time,
            0,
        ).normalize()

    def build_regional_training_data(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        lookback_days: int = 900,
    ) -> pd.DataFrame:
        """Backward-compatible helper returning the per-state panel slice."""
        code = normalize_state_code(bundesland) or bundesland
        panel = self.build_panel_training_data(virus_typ=virus_typ, lookback_days=lookback_days)
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
        if panel.empty:
            return {
                "virus_typ": virus_typ,
                "event_definition_version": EVENT_DEFINITION_VERSION,
                "target_window_days": list(TARGET_WINDOW_DAYS),
                "source_lag_days": SOURCE_LAG_DAYS,
                "rows": 0,
                "truth_source": "unavailable",
            }

        truth_sources = sorted(str(value) for value in panel["truth_source"].dropna().unique())
        return {
            "virus_typ": virus_typ,
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "target_window_days": list(TARGET_WINDOW_DAYS),
            "source_lag_days": SOURCE_LAG_DAYS,
            "rows": int(len(panel)),
            "states": int(panel["bundesland"].nunique()),
            "as_of_range": {
                "start": str(panel["as_of_date"].min()),
                "end": str(panel["as_of_date"].max()),
            },
            "truth_source": truth_sources[0] if len(truth_sources) == 1 else truth_sources,
        }

    def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        rows = (
            self.db.query(
                WastewaterData.bundesland,
                WastewaterData.datum,
                func.max(WastewaterData.available_time).label("available_time"),
                func.avg(WastewaterData.viruslast).label("viral_load"),
                func.count(WastewaterData.id).label("site_count"),
                func.avg(func.coalesce(WastewaterData.unter_bg, False).cast(Float)).label("under_bg_share"),
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

    def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        truth = self._load_truth_from_kreis(virus_typ=virus_typ, start_date=start_date)
        if truth.empty:
            truth = self._load_truth_from_weekly(virus_typ=virus_typ, start_date=start_date)
        return truth

    def _load_truth_from_kreis(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
        diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
        if not diseases:
            return pd.DataFrame()

        rows = (
            self.db.query(
                SurvstatKreisData.year,
                SurvstatKreisData.week,
                SurvstatKreisData.week_label,
                KreisEinwohner.bundesland,
                func.sum(SurvstatKreisData.fallzahl).label("total_cases"),
                func.sum(KreisEinwohner.einwohner).label("population"),
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
                        (float(row.total_cases or 0.0) / float(row.population or 0.0)) * 100_000.0
                        if float(row.population or 0.0) > 0
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

    def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
        rows = (
            self.db.query(
                WeatherData.city,
                WeatherData.datum,
                WeatherData.data_type,
                func.max(WeatherData.available_time).label("available_time"),
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
            )
            .all()
        )

        frame = pd.DataFrame(
            [
                {
                    "bundesland": CITY_TO_BUNDESLAND.get(row.city),
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(row.datum, row.available_time, 0),
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
        truth: pd.DataFrame,
        weather: pd.DataFrame,
        pollen: pd.DataFrame,
        holidays: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        include_targets: bool,
    ) -> list[dict[str, Any]]:
        if wastewater.empty or truth.empty:
            return []

        wastewater_by_state = {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in wastewater.groupby("bundesland")
        }
        truth_by_state = {
            state: frame.sort_values("week_start").reset_index(drop=True)
            for state, frame in truth.groupby("bundesland")
        }
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

                target_week_start = self._target_week_start(as_of)
                if target_week_start is None:
                    continue

                target_row = truth_frame.loc[truth_frame["week_start"] == target_week_start]
                if include_targets and target_row.empty:
                    continue

                current_truth = visible_truth.iloc[-1]
                next_truth = target_row.iloc[0] if not target_row.empty else None
                baseline, mad = seasonal_baseline_and_mad(truth_frame, target_week_start)
                latest_ww_levels = self._latest_wastewater_by_state(wastewater_by_state, as_of)
                feature_row = self._build_feature_row(
                    virus_typ=virus_typ,
                    state=state,
                    as_of=as_of,
                    visible_ww=visible_ww,
                    visible_truth=visible_truth,
                    weather_frame=weather_by_state.get(state),
                    pollen_frame=pollen_by_state.get(state),
                    holiday_ranges=holidays.get(state, []),
                    latest_ww_levels=latest_ww_levels,
                    max_site_count=max_sites.get(state, 1),
                    target_week_start=target_week_start,
                    current_known_incidence=float(current_truth["incidence"] or 0.0),
                    seasonal_baseline=float(baseline),
                    seasonal_mad=float(mad),
                )
                if feature_row is None:
                    continue

                row_payload = {
                    "virus_typ": virus_typ,
                    "bundesland": state,
                    "bundesland_name": BUNDESLAND_NAMES.get(state, state),
                    "as_of_date": pd.Timestamp(as_of).normalize(),
                    "target_week_start": pd.Timestamp(target_week_start).normalize(),
                    "target_window_days": list(TARGET_WINDOW_DAYS),
                    "event_definition_version": EVENT_DEFINITION_VERSION,
                    "truth_source": str(
                        (next_truth.get("truth_source") if next_truth is not None else None)
                        or current_truth.get("truth_source")
                        or "survstat_weekly"
                    ),
                    "current_known_incidence": float(current_truth["incidence"] or 0.0),
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
        weather_frame: pd.DataFrame | None,
        pollen_frame: pd.DataFrame | None,
        holiday_ranges: list[tuple[pd.Timestamp, pd.Timestamp]],
        latest_ww_levels: dict[str, float],
        max_site_count: int,
        target_week_start: pd.Timestamp,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
    ) -> dict[str, Any] | None:
        ww_latest = visible_ww.iloc[-1]
        ww_lag4 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=4), "viral_load")
        ww_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_load")
        ww_lag14 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=14), "viral_load")
        ww_window7 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=7)]
        ww_window28 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=28)]

        truth_lag1 = self._latest_truth_value(visible_truth, lag_weeks=1)
        truth_lag2 = self._latest_truth_value(visible_truth, lag_weeks=2)
        truth_lag4 = self._latest_truth_value(visible_truth, lag_weeks=4)
        truth_lag8 = self._latest_truth_value(visible_truth, lag_weeks=8)

        neighbor_values = [
            latest_ww_levels.get(code, 0.0)
            for code in REGIONAL_NEIGHBORS.get(state, [])
            if code in latest_ww_levels
        ]
        national_values = list(latest_ww_levels.values())

        weather_features = self._weather_features(weather_frame, as_of)
        pollen_context = self._pollen_context(pollen_frame, as_of)
        holiday_share = self._holiday_share_in_target_window(holiday_ranges, as_of)

        return {
            "ww_level": float(ww_latest["viral_load"] or 0.0),
            "ww_lag4d": float(ww_lag4),
            "ww_lag7d": float(ww_lag7),
            "ww_lag14d": float(ww_lag14),
            "ww_slope7d": float((float(ww_latest["viral_load"] or 0.0) - ww_lag7) / max(abs(ww_lag7), 1.0)),
            "ww_mean7d": float(ww_window7["viral_load"].mean() or 0.0),
            "ww_std7d": float(ww_window7["viral_load"].std(ddof=0) or 0.0),
            "ww_level_vs_28d_median": float(
                float(ww_latest["viral_load"] or 0.0) - float(ww_window28["viral_load"].median() or 0.0)
            ),
            "ww_site_coverage_ratio": float(float(ww_latest["site_count"] or 0.0) / max(float(max_site_count), 1.0)),
            "ww_under_bg_share7d": float(ww_window7["under_bg_share"].mean() or 0.0),
            "ww_regional_dispersion7d": float(ww_window7["viral_std"].mean() or 0.0),
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
            "neighbor_ww_level": float(np.mean(neighbor_values)) if neighbor_values else 0.0,
            "national_ww_level": float(np.mean(national_values)) if national_values else 0.0,
            "target_holiday_share": float(holiday_share),
            "target_holiday_any": float(holiday_share > 0.0),
            "target_week_iso": float(target_week_start.isocalendar().week),
            "pollen_context_score": float(pollen_context),
            **weather_features,
        }

    @staticmethod
    def _latest_value_as_of(frame: pd.DataFrame, as_of: pd.Timestamp, column: str) -> float:
        visible = frame.loc[frame["datum"] <= as_of]
        if visible.empty:
            return 0.0
        return float(visible.iloc[-1][column] or 0.0)

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

    @staticmethod
    def _weather_features(weather_frame: pd.DataFrame | None, as_of: pd.Timestamp) -> dict[str, float]:
        if weather_frame is None or weather_frame.empty:
            return {
                "weather_forecast_temp_3_7": 0.0,
                "weather_forecast_humidity_3_7": 0.0,
                "weather_temp_anomaly_3_7": 0.0,
                "weather_humidity_anomaly_3_7": 0.0,
            }

        visible = weather_frame.loc[weather_frame["available_time"] <= as_of]
        observed = visible.loc[
            (visible["data_type"].isin(["CURRENT", "DAILY_OBSERVATION"])) & (visible["datum"] <= as_of)
        ]
        forecast = visible.loc[
            (visible["data_type"] == "DAILY_FORECAST")
            & (visible["datum"] > as_of + pd.Timedelta(days=TARGET_WINDOW_DAYS[0] - 1))
            & (visible["datum"] <= as_of + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        ]

        obs_temp = float(observed.tail(7)["temp"].mean() or 0.0) if not observed.empty else 0.0
        obs_humidity = float(observed.tail(7)["humidity"].mean() or 0.0) if not observed.empty else 0.0
        fc_temp = float(forecast["temp"].mean() or obs_temp)
        fc_humidity = float(forecast["humidity"].mean() or obs_humidity)
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
        visible = pollen_frame.loc[
            (pollen_frame["datum"] <= as_of)
            & (pollen_frame["available_time"] <= as_of)
        ]
        if visible.empty:
            return 0.0
        return float(visible.tail(3)["pollen_index"].mean() or 0.0)

    @staticmethod
    def _holiday_share_in_target_window(
        holiday_ranges: list[tuple[pd.Timestamp, pd.Timestamp]],
        as_of: pd.Timestamp,
    ) -> float:
        window_days = [
            (as_of + pd.Timedelta(days=offset)).normalize()
            for offset in range(TARGET_WINDOW_DAYS[0], TARGET_WINDOW_DAYS[1] + 1)
        ]
        if not window_days:
            return 0.0

        hits = 0
        for day in window_days:
            if any(start <= day <= end for start, end in holiday_ranges):
                hits += 1
        return float(hits / len(window_days))

    @staticmethod
    def _target_week_start(as_of: pd.Timestamp) -> pd.Timestamp | None:
        week_starts = [
            (as_of + pd.Timedelta(days=offset)).normalize()
            for offset in range(TARGET_WINDOW_DAYS[0], TARGET_WINDOW_DAYS[1] + 1)
            if (as_of + pd.Timedelta(days=offset)).weekday() == 0
        ]
        return first_week_start_in_window(as_of, week_starts)

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
