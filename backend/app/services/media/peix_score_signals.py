from __future__ import annotations
from app.core.time import utc_now

import math
from bisect import bisect_right
from datetime import timedelta

import numpy as np
from sqlalchemy import func

from app.db.schema_contracts import ensure_ml_forecast_schema_aligned
from app.models.database import (
    AREKonsultation,
    GanzimmunData,
    GoogleTrendsData,
    MLForecast,
    NotaufnahmeSyndromData,
    SchoolHolidays,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.data_ingest.weather_service import CITY_STATE_MAP
from app.services.ml.forecast_contracts import DEFAULT_DECISION_HORIZON_DAYS
from app.services.ml.forecast_horizon_utils import DEFAULT_FORECAST_REGION

REGION_CODE_TO_NAME = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
REGION_NAME_TO_CODE = {name.lower(): code for code, name in REGION_CODE_TO_NAME.items()}

_NOTAUFNAHME_BY_VIRUS = {
    "Influenza A": "ILI",
    "Influenza B": "ILI",
    "SARS-CoV-2": "COVID",
    "RSV A": "ARI",
}

_SURVSTAT_BY_VIRUS: dict[str, list[str]] = {
    "Influenza A": ["influenza, saisonal"],
    "Influenza B": ["influenza, saisonal"],
    "SARS-CoV-2": ["covid-19"],
    "RSV A": ["rsv (meldepflicht gemäß ifsg)"],
}

PEIX_CONFIG = {
    "weather_temp_threshold": 20.0,
    "weather_temp_divisor": 25.0,
    "weather_uv_threshold": 8.0,
    "weather_temp_weight": 0.40,
    "weather_uv_weight": 0.35,
    "weather_humidity_weight": 0.25,
    "school_start_multiplier": 1.15,
    "school_start_weather_min": 0.6,
    "shortage_norm_divisor": 20.0,
    "shortage_fieber_weight": 0.5,
    "notaufnahme_fallback_divisor": 20.0,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _wastewater_by_region(service, virus_typ: str) -> dict[str, float]:
    latest = service.db.query(func.max(WastewaterData.datum)).filter(
        WastewaterData.virus_typ == virus_typ
    ).scalar()
    if not latest:
        return {}

    rows = (
        service.db.query(
            WastewaterData.bundesland,
            func.avg(WastewaterData.viruslast).label("avg_viruslast"),
        )
        .filter(
            WastewaterData.virus_typ == virus_typ,
            WastewaterData.datum == latest,
        )
        .group_by(WastewaterData.bundesland)
        .all()
    )

    max_val = max((float(row.avg_viruslast or 0.0) for row in rows), default=1.0) or 1.0
    out: dict[str, float] = {}
    for row in rows:
        code = str(row.bundesland or "").strip().upper()
        if code not in REGION_CODE_TO_NAME:
            continue
        out[code] = _clamp(float(row.avg_viruslast or 0.0) / max_val)
    return out


def _are_by_region(service) -> dict[str, float]:
    latest = service.db.query(func.max(AREKonsultation.datum)).filter(
        AREKonsultation.altersgruppe == "00+",
    ).scalar()
    if not latest:
        return {}

    latest_row = service.db.query(AREKonsultation).filter(
        AREKonsultation.datum == latest,
        AREKonsultation.altersgruppe == "00+",
    ).first()
    current_week = latest_row.kalenderwoche if latest_row else None

    rows = service.db.query(AREKonsultation).filter(
        AREKonsultation.datum == latest,
        AREKonsultation.altersgruppe == "00+",
    ).all()

    out: dict[str, float] = {}
    for row in rows:
        name = str(row.bundesland or "").strip().lower()
        code = REGION_NAME_TO_CODE.get(name)
        if not code:
            continue
        current_value = float(row.konsultationsinzidenz or 0.0)

        if current_week is not None:
            historical = service.db.query(AREKonsultation.konsultationsinzidenz).filter(
                AREKonsultation.kalenderwoche == current_week,
                AREKonsultation.altersgruppe == "00+",
                AREKonsultation.bundesland == row.bundesland,
            ).all()
            values = sorted([h[0] for h in historical if h[0] is not None])
            if len(values) >= 3:
                rank = bisect_right(values, current_value)
                out[code] = _clamp(rank / len(values))
                continue

        max_val = max((float(item.konsultationsinzidenz or 0.0) for item in rows), default=1.0) or 1.0
        out[code] = _clamp(current_value / max_val)
    return out


def _survstat_by_region(service, virus_typ: str) -> dict[str, float]:
    diseases = _SURVSTAT_BY_VIRUS.get(virus_typ)
    if not diseases:
        return {}

    latest_week = (
        service.db.query(func.max(SurvstatWeeklyData.week_start))
        .filter(
            func.lower(SurvstatWeeklyData.disease).in_(diseases),
            SurvstatWeeklyData.bundesland != "Gesamt",
            SurvstatWeeklyData.week > 0,
        )
        .scalar()
    )
    if not latest_week:
        return {}

    rows = (
        service.db.query(SurvstatWeeklyData)
        .filter(
            func.lower(SurvstatWeeklyData.disease).in_(diseases),
            SurvstatWeeklyData.week_start == latest_week,
            SurvstatWeeklyData.bundesland != "Gesamt",
        )
        .all()
    )
    if not rows:
        return {}

    current_week_nr = rows[0].week
    per_bl: dict[str, float] = {}
    for row in rows:
        bundesland = str(row.bundesland or "").strip()
        per_bl[bundesland] = per_bl.get(bundesland, 0.0) + float(row.incidence or 0.0)

    out: dict[str, float] = {}
    for bundesland, current_incidence in per_bl.items():
        code = REGION_NAME_TO_CODE.get(bundesland.lower())
        if not code:
            continue

        if current_week_nr and current_week_nr > 0:
            historical = (
                service.db.query(func.sum(SurvstatWeeklyData.incidence))
                .filter(
                    func.lower(SurvstatWeeklyData.disease).in_(diseases),
                    SurvstatWeeklyData.week == current_week_nr,
                    SurvstatWeeklyData.bundesland == bundesland,
                    SurvstatWeeklyData.week_start < latest_week,
                )
                .group_by(SurvstatWeeklyData.year)
                .all()
            )
            values = sorted([float(item[0]) for item in historical if item[0] is not None])
            if len(values) >= 3:
                rank = bisect_right(values, current_incidence)
                out[code] = _clamp(rank / len(values))
                continue

        max_val = max(per_bl.values(), default=1.0) or 1.0
        out[code] = _clamp(current_incidence / max_val)

    return out


def _weather_by_region(service) -> dict[str, float]:
    cutoff = utc_now() - timedelta(days=2)
    rows = service.db.query(WeatherData).filter(
        WeatherData.datum >= cutoff,
    ).all()
    if not rows:
        return {}

    per_region: dict[str, list[float]] = {}
    for row in rows:
        state_name = CITY_STATE_MAP.get(row.city)
        if not state_name:
            continue
        code = REGION_NAME_TO_CODE.get(state_name.lower())
        if not code:
            continue
        temp = float(row.temperatur) if row.temperatur is not None else 7.0
        uv = float(row.uv_index) if row.uv_index is not None else 2.5
        humidity = float(row.luftfeuchtigkeit) if row.luftfeuchtigkeit is not None else 70.0
        temp_factor = _clamp((PEIX_CONFIG["weather_temp_threshold"] - temp) / PEIX_CONFIG["weather_temp_divisor"])
        uv_factor = _clamp((PEIX_CONFIG["weather_uv_threshold"] - uv) / PEIX_CONFIG["weather_uv_threshold"])
        humidity_factor = _clamp(humidity / 100.0)
        risk = (
            temp_factor * PEIX_CONFIG["weather_temp_weight"]
            + uv_factor * PEIX_CONFIG["weather_uv_weight"]
            + humidity_factor * PEIX_CONFIG["weather_humidity_weight"]
        )
        per_region.setdefault(code, []).append(_clamp(risk))

    return {code: round(sum(values) / max(len(values), 1), 4) for code, values in per_region.items()}


def _notaufnahme_signal(service, virus_typ: str) -> float:
    syndrome = _NOTAUFNAHME_BY_VIRUS.get(virus_typ, "ARI")
    latest = (
        service.db.query(NotaufnahmeSyndromData)
        .filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
        )
        .order_by(NotaufnahmeSyndromData.datum.desc())
        .first()
    )
    if not latest:
        return 0.0

    current_value = (
        latest.relative_cases_7day_ma
        if latest.relative_cases_7day_ma is not None
        else latest.relative_cases
    )
    if current_value is None:
        return 0.0

    three_years_ago = utc_now() - timedelta(days=365 * 3)
    historical = service.db.query(
        NotaufnahmeSyndromData.relative_cases_7day_ma,
        NotaufnahmeSyndromData.relative_cases,
    ).filter(
        NotaufnahmeSyndromData.syndrome == syndrome,
        NotaufnahmeSyndromData.age_group == "00+",
        NotaufnahmeSyndromData.ed_type == "all",
        NotaufnahmeSyndromData.datum >= three_years_ago,
    ).all()

    values = []
    for rel_ma, rel in historical:
        value = rel_ma if rel_ma is not None else rel
        if value is not None:
            values.append(value)
    values = sorted(values)

    if len(values) < 14:
        return _clamp(float(current_value) / PEIX_CONFIG["notaufnahme_fallback_divisor"])

    rank = bisect_right(values, current_value)
    return _clamp(rank / len(values))


def _search_signal(service) -> float:
    now = utc_now()
    two_weeks_ago = now - timedelta(days=14)
    four_weeks_ago = now - timedelta(days=28)

    recent = float(
        service.db.query(func.avg(GoogleTrendsData.interest_score))
        .filter(GoogleTrendsData.datum >= two_weeks_ago)
        .scalar()
        or 0
    )

    previous = float(
        service.db.query(func.avg(GoogleTrendsData.interest_score))
        .filter(
            GoogleTrendsData.datum >= four_weeks_ago,
            GoogleTrendsData.datum < two_weeks_ago,
        )
        .scalar()
        or 0
    )

    slope = (recent - previous) / previous if previous > 0 else 0.0
    if slope > 0.2:
        return _clamp(0.5 + slope)
    if slope < -0.2:
        return _clamp(0.5 + slope)
    return 0.5


def _shortage_signal(service) -> float:
    signals = get_cached_signals() or {}
    by_cat = signals.get("by_category", {})
    atemwege = float((by_cat.get("Atemwege") or {}).get("high_demand", 0) or 0)
    fieber = float((by_cat.get("Fieber_Schmerz") or {}).get("high_demand", 0) or 0)
    count = atemwege + fieber * PEIX_CONFIG["shortage_fieber_weight"]
    return _clamp(count / PEIX_CONFIG["shortage_norm_divisor"])


def _forecast_signal(service, virus_typ: str) -> float:
    ensure_ml_forecast_schema_aligned(service.db)
    latest = (
        service.db.query(MLForecast)
        .filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.region == DEFAULT_FORECAST_REGION,
            MLForecast.horizon_days == DEFAULT_DECISION_HORIZON_DAYS,
        )
        .order_by(MLForecast.created_at.desc())
        .first()
    )
    if not latest:
        return 0.5

    forecasts = (
        service.db.query(MLForecast)
        .filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.region == DEFAULT_FORECAST_REGION,
            MLForecast.horizon_days == DEFAULT_DECISION_HORIZON_DAYS,
            MLForecast.created_at >= latest.created_at - timedelta(seconds=10),
        )
        .order_by(MLForecast.forecast_date.asc())
        .all()
    )
    if len(forecasts) < 2:
        return 0.5

    slope = (forecasts[-1].predicted_value - forecasts[0].predicted_value) / len(forecasts)
    first_val = forecasts[0].predicted_value or 1
    trend_pct = slope / first_val if first_val > 0 else 0

    if trend_pct > 0.01:
        return _clamp(0.5 + trend_pct * 10)
    if trend_pct < -0.01:
        return _clamp(0.5 + trend_pct * 10)
    return 0.5


def _baseline_adjustment(service, virus_typ: str) -> float:
    current_week = utc_now().isocalendar()[1]
    historical = service.db.query(GanzimmunData).filter(
        GanzimmunData.anzahl_tests > 0,
    ).all()

    if len(historical) < 52:
        return 0.5

    weekly_rates: dict[int, list[float]] = {}
    for item in historical:
        week = item.datum.isocalendar()[1]
        rate = (item.positive_ergebnisse or 0) / item.anzahl_tests
        weekly_rates.setdefault(week, []).append(rate)

    if current_week not in weekly_rates or len(weekly_rates[current_week]) < 2:
        return 0.5

    hist_mean = float(np.mean(weekly_rates[current_week]))
    hist_std = float(np.std(weekly_rates[current_week])) or 0.01
    current_rate = service._get_positivity_rate(virus_typ)
    z_score = (current_rate - hist_mean) / hist_std
    return _clamp(1.0 / (1.0 + math.exp(-z_score)))


def _get_positivity_rate(service, virus_typ: str) -> float:
    two_weeks_ago = utc_now() - timedelta(days=14)
    test_typ_map = {
        "Influenza A": "Influenza A",
        "Influenza B": "Influenza B",
        "SARS-CoV-2": "SARS-CoV-2",
        "RSV A": "RSV",
    }

    query = service.db.query(GanzimmunData).filter(
        GanzimmunData.datum >= two_weeks_ago,
        GanzimmunData.anzahl_tests > 0,
    )
    mapped = test_typ_map.get(virus_typ)
    if mapped:
        query = query.filter(GanzimmunData.test_typ == mapped)

    recent = query.all()
    if not recent:
        return 0.0

    total = sum(item.anzahl_tests for item in recent)
    positive = sum(item.positive_ergebnisse or 0 for item in recent)
    return positive / total if total > 0 else 0.0


def _is_school_start(service) -> bool:
    now = utc_now()
    week_ago = now - timedelta(days=7)
    count = service.db.query(SchoolHolidays).filter(
        SchoolHolidays.end_datum >= week_ago,
        SchoolHolidays.end_datum <= now,
    ).count()
    return count > 0
