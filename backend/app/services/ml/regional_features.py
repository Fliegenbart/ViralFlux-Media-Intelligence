"""Regional as-of panel dataset builder for pooled outbreak forecasting."""

from __future__ import annotations

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
    KreisEinwohner,
    NotaufnahmeSyndromData,
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
    circular_week_distance,
    effective_available_time,
    event_definition_config_for_virus,
    first_week_start_in_window,
    normalize_state_code,
    seasonal_baseline_and_mad,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)


def _feature_virus_slug(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


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
        wastewater_context = self._load_supported_wastewater_context(virus_typ, truth_start)
        truth = self._load_truth_series(virus_typ, truth_start)
        are = self._load_are_konsultation(truth_start, end_date) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        notaufnahme = self._load_notaufnahme_covid(truth_start, end_date) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        trends = self._load_corona_test_trends(truth_start, end_date) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        weather = self._load_weather(truth_start, end_date + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        pollen = self._load_pollen(truth_start, end_date + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        holidays = self._load_holidays()
        state_populations = self._load_state_population_map()

        rows = self._build_rows(
            virus_typ=virus_typ,
            wastewater=wastewater,
            wastewater_context=wastewater_context,
            truth=truth,
            are=are,
            notaufnahme=notaufnahme,
            trends=trends,
            weather=weather,
            pollen=pollen,
            holidays=holidays,
            state_populations=state_populations,
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
        history_start = effective_as_of - pd.Timedelta(days=lookback_days)
        row_start = effective_as_of - pd.Timedelta(days=TARGET_WINDOW_DAYS[1] + 7)
        truth_start = history_start - pd.Timedelta(days=730)

        wastewater = self._load_wastewater_daily(virus_typ, truth_start)
        wastewater_context = self._load_supported_wastewater_context(virus_typ, truth_start)
        truth = self._load_truth_series(virus_typ, truth_start)
        are = self._load_are_konsultation(truth_start, effective_as_of) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        notaufnahme = (
            self._load_notaufnahme_covid(truth_start, effective_as_of)
            if virus_typ == "SARS-CoV-2"
            else pd.DataFrame()
        )
        trends = self._load_corona_test_trends(truth_start, effective_as_of) if virus_typ == "SARS-CoV-2" else pd.DataFrame()
        weather = self._load_weather(truth_start, effective_as_of + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        pollen = self._load_pollen(truth_start, effective_as_of + pd.Timedelta(days=TARGET_WINDOW_DAYS[1]))
        holidays = self._load_holidays()
        state_populations = self._load_state_population_map()

        rows = self._build_rows(
            virus_typ=virus_typ,
            wastewater=wastewater,
            wastewater_context=wastewater_context,
            truth=truth,
            are=are,
            notaufnahme=notaufnahme,
            trends=trends,
            weather=weather,
            pollen=pollen,
            holidays=holidays,
            state_populations=state_populations,
            start_date=row_start,
            end_date=effective_as_of,
            include_targets=False,
        )
        panel = self._finalize_panel(rows)
        if panel.empty:
            return panel

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
        event_config = event_definition_config_for_virus(virus_typ)
        if panel.empty:
            return {
                "virus_typ": virus_typ,
                "event_definition_version": EVENT_DEFINITION_VERSION,
                "event_definition_config": event_config.to_manifest(),
                "target_window_days": list(TARGET_WINDOW_DAYS),
                "source_lag_days": SOURCE_LAG_DAYS,
                "rows": 0,
                "truth_source": "unavailable",
            }

        truth_sources = sorted(str(value) for value in panel["truth_source"].dropna().unique())
        return {
            "virus_typ": virus_typ,
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "event_definition_config": event_config.to_manifest(),
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

    def _load_are_konsultation(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
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
        wastewater_context: dict[str, pd.DataFrame],
        truth: pd.DataFrame,
        are: pd.DataFrame,
        notaufnahme: pd.DataFrame,
        trends: pd.DataFrame,
        weather: pd.DataFrame,
        pollen: pd.DataFrame,
        holidays: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
        state_populations: dict[str, float],
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        include_targets: bool,
    ) -> list[dict[str, Any]]:
        if wastewater.empty or truth.empty:
            return []
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
                    visible_trends = national_trends.loc[
                        (national_trends["datum"] <= as_of)
                        & (national_trends["available_time"] <= as_of)
                    ].copy()

                target_week_start = self._target_week_start(as_of)
                if target_week_start is None:
                    continue

                target_row = truth_frame.loc[truth_frame["week_start"] == target_week_start]
                if include_targets and target_row.empty:
                    continue

                current_truth = visible_truth.iloc[-1]
                next_truth = target_row.iloc[0] if not target_row.empty else None
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
        target_week_start: pd.Timestamp,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
    ) -> dict[str, Any] | None:
        ww_latest = visible_ww.iloc[-1]
        ww_lag4 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=4), "viral_load")
        ww_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_load")
        ww_lag14 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=14), "viral_load")
        ww_site_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "site_count")
        ww_under_bg_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "under_bg_share")
        ww_dispersion_lag7 = self._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_std")
        ww_window7 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=7)]
        ww_window28 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=28)]
        ww_level = float(ww_latest["viral_load"] or 0.0)
        ww_site_count = float(ww_latest["site_count"] or 0.0)
        ww_slope7d = float((ww_level - ww_lag7) / max(abs(ww_lag7), 1.0))
        ww_slope14d = float((ww_lag7 - ww_lag14) / max(abs(ww_lag14), 1.0))
        ww_acceleration7d = float(ww_slope7d - ww_slope14d)

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

        weather_features = self._weather_features(weather_frame, as_of)
        pollen_context = self._pollen_context(pollen_frame, as_of)
        holiday_share = self._holiday_share_in_target_window(holiday_ranges, as_of)
        sars_context_features = self._sars_context_features(
            virus_typ=virus_typ,
            as_of=as_of,
            visible_are=visible_are,
            visible_notaufnahme=visible_notaufnahme,
            visible_trends=visible_trends,
            ww_level=ww_level,
            ww_slope7d=ww_slope7d,
            current_known_incidence=current_known_incidence,
            seasonal_baseline=seasonal_baseline,
            seasonal_mad=seasonal_mad,
        )

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
            **sars_context_features,
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
        as_of: pd.Timestamp,
        visible_are: pd.DataFrame | None,
        visible_notaufnahme: pd.DataFrame | None,
        visible_trends: pd.DataFrame | None,
        ww_level: float,
        ww_slope7d: float,
        current_known_incidence: float,
        seasonal_baseline: float,
        seasonal_mad: float,
    ) -> dict[str, float]:
        if virus_typ != "SARS-CoV-2":
            return {}

        are_frame = visible_are if visible_are is not None else pd.DataFrame()
        are_level = self._latest_value_as_of(are_frame, as_of, "incidence")
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
        notaufnahme_level = self._latest_value_as_of(notaufnahme_frame, as_of, "level")
        notaufnahme_ma7 = self._latest_value_as_of(notaufnahme_frame, as_of, "ma7")
        notaufnahme_ma7_lag7 = self._latest_value_as_of(notaufnahme_frame, as_of - pd.Timedelta(days=7), "ma7")
        notaufnahme_expected = self._latest_value_as_of(notaufnahme_frame, as_of, "expected_value")
        notaufnahme_upper = self._latest_value_as_of(notaufnahme_frame, as_of, "expected_upperbound")
        notaufnahme_momentum_7d = float(
            (notaufnahme_ma7 - notaufnahme_ma7_lag7) / max(abs(notaufnahme_ma7_lag7), 1.0)
        )

        trends_frame = visible_trends if visible_trends is not None else pd.DataFrame()
        trends_level = self._latest_value_as_of(trends_frame, as_of, "interest_score")
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

        return {
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
