from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Integer, func

from app.core.time import utc_now
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
from app.services.ml.forecast_service import SURVSTAT_VIRUS_MAP
from app.services.ml.regional_panel_utils import (
    CITY_TO_BUNDESLAND,
    SOURCE_LAG_DAYS,
    effective_available_time,
    normalize_state_code,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_RUN_IDENTITY_QUALITY_MISSING,
    WEATHER_FORECAST_RUN_IDENTITY_SOURCE_MISSING,
)

logger = logging.getLogger(__name__)

_RSV_A_WASTEWATER_CANDIDATES: tuple[str, ...] = ("RSV A", "RSV A/B", "RSV A+B")


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


def _wastewater_virus_candidates(virus_typ: str) -> tuple[str, ...]:
    if str(virus_typ or "").strip() == "RSV A":
        return _RSV_A_WASTEWATER_CANDIDATES
    return (str(virus_typ or "").strip(),)


def _wastewater_virus_filter(column: Any, virus_typ: str) -> Any:
    candidates = _wastewater_virus_candidates(virus_typ)
    if len(candidates) == 1:
        return column == candidates[0]
    return column.in_(candidates)


def _select_wastewater_alias_rows(frame: pd.DataFrame, virus_typ: str) -> pd.DataFrame:
    if frame.empty or "source_virus_typ" not in frame.columns:
        return frame

    priority = {
        source_virus_typ: index
        for index, source_virus_typ in enumerate(_wastewater_virus_candidates(virus_typ))
    }
    selected = frame.copy()
    selected["_source_priority"] = (
        selected["source_virus_typ"].map(priority).fillna(len(priority)).astype(int)
    )
    selected = selected.sort_values(
        ["bundesland", "datum", "_source_priority", "source_virus_typ"]
    )
    selected = selected.drop_duplicates(["bundesland", "datum"], keep="first")
    selected = selected.drop(columns=["_source_priority"])
    return selected.sort_values(["bundesland", "datum"]).reset_index(drop=True)


def load_wastewater_daily(builder: Any, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
    rows = (
        builder.db.query(
            WastewaterData.virus_typ.label("source_virus_typ"),
            WastewaterData.bundesland,
            WastewaterData.datum,
            func.max(WastewaterData.available_time).label("available_time"),
            func.avg(WastewaterData.viruslast).label("viral_load"),
            func.count(WastewaterData.id).label("site_count"),
            func.avg(func.cast(func.coalesce(WastewaterData.unter_bg, False), Integer)).label("under_bg_share"),
            func.stddev_pop(WastewaterData.viruslast).label("viral_std"),
        )
        .filter(
            _wastewater_virus_filter(WastewaterData.virus_typ, virus_typ),
            WastewaterData.datum >= start_date.to_pydatetime(),
            WastewaterData.viruslast.isnot(None),
        )
        .group_by(
            WastewaterData.virus_typ,
            WastewaterData.bundesland,
            WastewaterData.datum,
        )
        .order_by(WastewaterData.datum.asc())
        .all()
    )

    frame = pd.DataFrame(
        [
            {
                "source_virus_typ": str(row.source_virus_typ or virus_typ),
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

    frame = _select_wastewater_alias_rows(frame, virus_typ)
    return frame.sort_values(["bundesland", "datum"]).reset_index(drop=True)


def latest_wastewater_available_date(builder: Any, virus_typ: str) -> pd.Timestamp:
    if builder.db is None:
        return pd.Timestamp(utc_now()).normalize()

    row = (
        builder.db.query(
            func.max(WastewaterData.available_time).label("available_time"),
            func.max(WastewaterData.datum).label("datum"),
        )
        .filter(_wastewater_virus_filter(WastewaterData.virus_typ, virus_typ))
        .first()
    )
    if row is None:
        return pd.Timestamp(utc_now()).normalize()
    return effective_available_time(
        row.datum or utc_now(),
        row.available_time,
        0,
    ).normalize()


def load_supported_wastewater_context(
    builder: Any,
    virus_typ: str,
    start_date: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    bundle: dict[str, pd.DataFrame] = {}
    for candidate in SUPPORTED_VIRUS_TYPES:
        frame = builder._load_wastewater_daily(candidate, start_date)
        if not frame.empty:
            bundle[candidate] = frame
    if virus_typ not in bundle:
        bundle[virus_typ] = builder._load_wastewater_daily(virus_typ, start_date)
    return bundle


def load_truth_series(builder: Any, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
    truth = builder._load_truth_from_kreis(virus_typ=virus_typ, start_date=start_date)
    if truth.empty:
        truth = builder._load_truth_from_weekly(virus_typ=virus_typ, start_date=start_date)
    return truth


def load_landkreis_truth_series(builder: Any, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
    if builder.db is None:
        return pd.DataFrame()
    diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
    if not diseases:
        return pd.DataFrame()

    rows = (
        builder.db.query(
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
                "week_start": builder._week_start_from_label(row.week_label),
                "available_date": effective_available_time(
                    builder._week_start_from_label(row.week_label),
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


def load_truth_from_kreis(builder: Any, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
    diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
    if not diseases:
        return pd.DataFrame()

    state_populations = builder._load_state_population_map()
    if not state_populations:
        logger.warning("Regional truth fallback to weekly SurvStat because Kreis state populations are unavailable.")
        return pd.DataFrame()

    rows = (
        builder.db.query(
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
                "week_start": builder._week_start_from_label(row.week_label),
                "available_date": effective_available_time(
                    builder._week_start_from_label(row.week_label),
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


def load_state_population_map(builder: Any) -> dict[str, float]:
    rows = (
        builder.db.query(
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


def load_truth_from_weekly(builder: Any, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
    diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
    if not diseases:
        return pd.DataFrame()

    rows = (
        builder.db.query(
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


def load_grippeweb_signals(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    if builder.db is None:
        return pd.DataFrame()
    rows = (
        builder.db.query(
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
                "available_time": builder._created_proxy_available_time(
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


def load_influenza_ifsg(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    return builder._load_ifsg_signal_frame(
        model=InfluenzaData,
        start_date=start_date,
        end_date=end_date,
        lag_key="influenza_ifsg",
    )


def load_rsv_ifsg(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    return builder._load_ifsg_signal_frame(
        model=RSVData,
        start_date=start_date,
        end_date=end_date,
        lag_key="rsv_ifsg",
    )


def load_ifsg_signal_frame(
    builder: Any,
    *,
    model: Any,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    lag_key: str,
) -> pd.DataFrame:
    if builder.db is None:
        return pd.DataFrame()
    rows = (
        builder.db.query(
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


def load_are_konsultation(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    if builder.db is None:
        return pd.DataFrame()
    rows = (
        builder.db.query(
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


def load_notaufnahme_syndrome(
    builder: Any,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    syndrome: str,
) -> pd.DataFrame:
    if builder.db is None:
        return pd.DataFrame()
    rows = (
        builder.db.query(NotaufnahmeSyndromData)
        .filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
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
                "available_time": builder._created_proxy_available_time(
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


def load_notaufnahme_covid(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    return load_notaufnahme_syndrome(builder, start_date, end_date, "COVID")


def load_trends_keywords(
    builder: Any,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    keywords: tuple[str, ...],
) -> pd.DataFrame:
    if builder.db is None or not keywords:
        return pd.DataFrame()
    lowered = tuple(str(k).lower() for k in keywords)
    rows = (
        builder.db.query(
            GoogleTrendsData.datum,
            func.max(GoogleTrendsData.available_time).label("available_time"),
            func.avg(GoogleTrendsData.interest_score).label("interest_score"),
        )
        .filter(
            func.lower(GoogleTrendsData.keyword).in_(lowered),
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


def load_corona_test_trends(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    return load_trends_keywords(builder, start_date, end_date, ("corona test",))


def load_weather(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    rows = (
        builder.db.query(
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


def load_pollen(builder: Any, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    rows = (
        builder.db.query(
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


def load_holidays(builder: Any) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    rows = builder.db.query(SchoolHolidays).all()
    holiday_ranges: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for row in rows:
        code = normalize_state_code(row.bundesland)
        if not code:
            continue
        holiday_ranges.setdefault(code, []).append(
            (pd.Timestamp(row.start_datum).normalize(), pd.Timestamp(row.end_datum).normalize())
        )
    return holiday_ranges
