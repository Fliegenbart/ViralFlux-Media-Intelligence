"""Signal and time-travel helpers for BacktestService."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from typing import Optional

from sqlalchemy import func

from app.models.database import (
    AREKonsultation,
    GanzimmunData,
    GoogleTrendsData,
    GrippeWebData,
    NotaufnahmeSyndromData,
    SchoolHolidays,
    SurvstatWeeklyData,
    WastewaterAggregated,
    WeatherData,
)


def asof_filter(service, model_cls, event_col, cutoff: datetime, *, and_fn, or_fn):
    """As-of-Filter mit Fallback auf event_time wenn available_time fehlt."""
    if not service.strict_vintage_mode:
        return event_col <= cutoff

    available_col = getattr(model_cls, "available_time", None)
    if available_col is None:
        return event_col <= cutoff

    return or_fn(
        available_col <= cutoff,
        and_fn(available_col.is_(None), event_col <= cutoff),
    )


def wastewater_at_date(
    service,
    target: datetime,
    virus_typ: str,
    *,
    available_cutoff: Optional[datetime] = None,
    timedelta_cls,
) -> float:
    effective = available_cutoff or target
    one_year_ago = effective - timedelta_cls(days=365)

    max_load = service.db.query(func.max(WastewaterAggregated.viruslast)).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum >= one_year_ago,
        WastewaterAggregated.datum <= effective,
        service._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
    ).scalar() or 1.0

    current = service.db.query(WastewaterAggregated).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum <= effective,
        service._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
    ).order_by(WastewaterAggregated.datum.desc()).first()

    if not current or not current.viruslast:
        return 0.0
    return min(current.viruslast / max_load, 1.0)


def amelag_raw_at_date(
    service,
    target: datetime,
    virus_typ: str,
    *,
    available_cutoff: Optional[datetime] = None,
) -> Optional[float]:
    effective = available_cutoff or target
    current = service.db.query(WastewaterAggregated).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum <= effective,
        service._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
    ).order_by(WastewaterAggregated.datum.desc()).first()

    if not current or not current.viruslast:
        return None
    return float(current.viruslast)


def wastewater_lags_at_date(
    service,
    target: datetime,
    virus_typ: str,
    *,
    available_cutoff: Optional[datetime] = None,
    timedelta_cls,
) -> dict[str, float]:
    effective = available_cutoff or target
    one_year_ago = effective - timedelta_cls(days=365)

    max_load = service.db.query(func.max(WastewaterAggregated.viruslast)).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum >= one_year_ago,
        WastewaterAggregated.datum <= effective,
        service._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
    ).scalar() or 1.0

    vals: list[float] = []
    result: dict[str, float] = {}
    for lag_w in range(4):
        cutoff = effective - timedelta_cls(weeks=lag_w)
        row = service.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum <= cutoff,
            service._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, cutoff),
        ).order_by(WastewaterAggregated.datum.desc()).first()
        v = min(row.viruslast / max_load, 1.0) if row and row.viruslast else 0.0
        result[f"ww_lag{lag_w}w"] = round(v, 4)
        vals.append(v)

    result["ww_max_3w"] = round(max(vals), 4)
    result["ww_slope_2w"] = round(vals[0] - vals[2], 4) if len(vals) > 2 else 0.0
    return result


def positivity_rate_at_date(
    service,
    target: datetime,
    virus_typ: str,
    *,
    available_cutoff: Optional[datetime] = None,
    timedelta_cls,
) -> float:
    effective = available_cutoff or target
    start = effective - timedelta_cls(days=14)

    test_typ_map = {
        "Influenza A": "Influenza A",
        "Influenza B": "Influenza B",
        "SARS-CoV-2": "SARS-CoV-2",
        "RSV A": "RSV",
    }

    query = service.db.query(GanzimmunData).filter(
        GanzimmunData.datum >= start,
        GanzimmunData.datum <= effective,
        GanzimmunData.anzahl_tests > 0,
        service._asof_filter(GanzimmunData, GanzimmunData.datum, effective),
    )
    mapped = test_typ_map.get(virus_typ)
    if mapped:
        query = query.filter(GanzimmunData.test_typ == mapped)

    recent = query.all()
    if not recent:
        return 0.0

    total = sum(d.anzahl_tests for d in recent)
    positive = sum(d.positive_ergebnisse or 0 for d in recent)
    return positive / total if total > 0 else 0.0


def trends_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
    timedelta_cls,
) -> float:
    effective = available_cutoff or target
    two_weeks_ago = effective - timedelta_cls(days=14)
    four_weeks_ago = effective - timedelta_cls(days=28)

    recent = service.db.query(func.avg(GoogleTrendsData.interest_score)).filter(
        GoogleTrendsData.datum >= two_weeks_ago,
        GoogleTrendsData.datum <= effective,
        service._asof_filter(GoogleTrendsData, GoogleTrendsData.datum, effective),
    ).scalar() or 0

    previous = service.db.query(func.avg(GoogleTrendsData.interest_score)).filter(
        GoogleTrendsData.datum >= four_weeks_ago,
        GoogleTrendsData.datum < two_weeks_ago,
        service._asof_filter(GoogleTrendsData, GoogleTrendsData.datum, effective),
    ).scalar() or 0

    if previous > 0:
        slope = float((recent - previous) / previous)
    else:
        slope = 0.0

    if slope > 0.2:
        return min(1.0, 0.5 + slope)
    if slope < -0.2:
        return max(0.0, 0.5 + slope)
    return 0.5


def weather_risk_components_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
) -> dict[str, float]:
    effective = available_cutoff or target
    latest = service.db.query(WeatherData).filter(
        WeatherData.datum <= effective,
        service._asof_filter(WeatherData, WeatherData.datum, effective),
    ).order_by(WeatherData.datum.desc()).limit(5).all()

    if not latest:
        return {
            "temp_factor": 0.3,
            "uv_factor": 0.3,
            "humidity_factor": 0.6,
            "composite": 0.3,
        }

    temps = [w.temperatur for w in latest if w.temperatur is not None]
    avg_temp = sum(temps) / len(temps) if temps else 5.0
    avg_uv = sum(w.uv_index or 0 for w in latest) / len(latest)
    avg_humidity = sum(w.luftfeuchtigkeit or 60 for w in latest) / len(latest)

    temp_factor = max(0, min(1, (20 - avg_temp) / 25))
    uv_factor = max(0, min(1, (8 - avg_uv) / 8))
    humidity_factor = max(0, min(1, avg_humidity / 100))
    composite = temp_factor * 0.4 + uv_factor * 0.35 + humidity_factor * 0.25

    return {
        "temp_factor": round(temp_factor, 4),
        "uv_factor": round(uv_factor, 4),
        "humidity_factor": round(humidity_factor, 4),
        "composite": round(composite, 4),
    }


def weather_risk_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
) -> float:
    components = service._weather_risk_components_at_date(target, available_cutoff)
    return components["composite"]


def school_start_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
    timedelta_cls,
) -> bool:
    effective = available_cutoff or target
    week_ago = effective - timedelta_cls(days=7)
    count = service.db.query(SchoolHolidays).filter(
        SchoolHolidays.end_datum >= week_ago,
        SchoolHolidays.end_datum <= effective,
    ).count()
    return count > 0


def cross_disease_load_at_date(
    service,
    target: datetime,
    xdisease_viruses: list[str],
    *,
    available_cutoff: Optional[datetime] = None,
    timedelta_cls,
) -> float:
    if not xdisease_viruses:
        return 0.0
    effective = available_cutoff or target
    week_ago = effective - timedelta_cls(days=7)

    avg_load = service.db.query(func.avg(WastewaterAggregated.viruslast_normalisiert)).filter(
        WastewaterAggregated.virus_typ.in_(xdisease_viruses),
        WastewaterAggregated.datum >= week_ago,
        WastewaterAggregated.datum <= effective,
        service._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
    ).scalar()

    return round(float(avg_load or 0.0), 4)


def grippeweb_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
) -> dict[str, float]:
    effective = available_cutoff or target
    row = service.db.query(GrippeWebData).filter(
        GrippeWebData.erkrankung_typ == "ARE",
        GrippeWebData.altersgruppe == "Gesamt",
        GrippeWebData.datum <= effective,
    ).order_by(GrippeWebData.datum.desc()).first()
    are_val = float(row.inzidenz / 10000.0) if row and row.inzidenz else 0.0
    return {"grippeweb_are": round(min(are_val, 1.0), 4)}


def notaufnahme_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
) -> dict[str, float]:
    effective = available_cutoff or target
    row = service.db.query(NotaufnahmeSyndromData).filter(
        NotaufnahmeSyndromData.syndrome == "ARI",
        NotaufnahmeSyndromData.age_group == "00+",
        NotaufnahmeSyndromData.ed_type == "all",
        NotaufnahmeSyndromData.datum <= effective,
    ).order_by(NotaufnahmeSyndromData.datum.desc()).first()
    ari_val = float(row.relative_cases_7day_ma) if row and row.relative_cases_7day_ma else 0.0
    return {"notaufnahme_ari": round(ari_val, 4)}


def survstat_cross_disease_at_date(
    service,
    target: datetime,
    target_disease: str,
    *,
    available_cutoff: Optional[datetime] = None,
) -> dict[str, float]:
    related = service.SURVSTAT_CROSS_DISEASE_MAP.get(target_disease, [])
    effective = available_cutoff or target
    result = {"survstat_xdisease_1": 0.0, "survstat_xdisease_2": 0.0}

    for i, disease in enumerate(related[:2]):
        row = service.db.query(SurvstatWeeklyData).filter(
            SurvstatWeeklyData.disease == disease,
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.week_start <= effective,
            SurvstatWeeklyData.available_time <= effective,
        ).order_by(SurvstatWeeklyData.week_start.desc()).first()
        if row and row.incidence is not None:
            result[f"survstat_xdisease_{i + 1}"] = round(
                min(float(row.incidence) / 1000.0, 1.0), 4
            )

    return result


def are_consultation_at_date(
    service,
    target: datetime,
    *,
    available_cutoff: Optional[datetime] = None,
) -> float:
    effective = available_cutoff or target
    latest = service.db.query(AREKonsultation).filter(
        AREKonsultation.altersgruppe == "00+",
        AREKonsultation.bundesland == "Bundesweit",
        AREKonsultation.datum <= effective,
        service._asof_filter(AREKonsultation, AREKonsultation.datum, effective),
    ).order_by(AREKonsultation.datum.desc()).first()

    if not latest or not latest.konsultationsinzidenz:
        return 0.0

    current_value = latest.konsultationsinzidenz
    current_week = latest.kalenderwoche

    historical = service.db.query(AREKonsultation.konsultationsinzidenz).filter(
        AREKonsultation.kalenderwoche == current_week,
        AREKonsultation.altersgruppe == "00+",
        AREKonsultation.bundesland == "Bundesweit",
        AREKonsultation.datum <= effective,
        service._asof_filter(AREKonsultation, AREKonsultation.datum, effective),
    ).all()

    values = sorted([h[0] for h in historical if h[0] is not None])

    if len(values) < 3:
        return min(current_value / 8200.0, 1.0)

    rank = bisect_right(values, current_value)
    return min(rank / len(values), 1.0)


def market_proxy_at_date(
    target: datetime,
    *,
    bio: float,
    wastewater: float,
    positivity: float,
) -> float:
    _ = target
    raw = bio * 0.4 + wastewater * 0.3 + min(positivity * 5.0, 1.0) * 0.3
    return min(raw**0.7, 1.0)


def compute_sub_scores_at_date(
    service,
    target: datetime,
    virus_typ: str,
    *,
    delay_rules: Optional[dict[str, int]] = None,
    target_disease: Optional[str] = None,
    timedelta_cls,
) -> dict[str, float]:
    if not hasattr(service, "_scores_cache"):
        service._scores_cache = {}
    cache_key = f"{target.isoformat()}|{virus_typ}|{target_disease}"
    if cache_key in service._scores_cache:
        return service._scores_cache[cache_key]

    rules = dict(service.DEFAULT_DELAY_RULES_DAYS)
    if delay_rules:
        rules.update(delay_rules)

    wastewater_cutoff = target - timedelta_cls(days=max(0, int(rules.get("wastewater", 0))))
    positivity_cutoff = target - timedelta_cls(days=max(0, int(rules.get("positivity", 0))))
    are_cutoff = target - timedelta_cls(days=max(0, int(rules.get("are_consultation", 0))))
    trends_cutoff = target - timedelta_cls(days=max(0, int(rules.get("trends", 0))))
    weather_cutoff = target - timedelta_cls(days=max(0, int(rules.get("weather", 0))))
    holidays_cutoff = target - timedelta_cls(days=max(0, int(rules.get("school_holidays", 0))))

    wastewater = service._wastewater_at_date(
        target, virus_typ, available_cutoff=wastewater_cutoff
    )
    ww_lags = service._wastewater_lags_at_date(
        target, virus_typ, available_cutoff=wastewater_cutoff
    )
    positivity = service._positivity_rate_at_date(
        target, virus_typ, available_cutoff=positivity_cutoff
    )
    are_consultation = service._are_consultation_at_date(target, available_cutoff=are_cutoff)
    trends = service._trends_at_date(target, available_cutoff=trends_cutoff)
    weather_components = service._weather_risk_components_at_date(
        target, available_cutoff=weather_cutoff
    )
    weather = weather_components["composite"]
    school_start = service._school_start_at_date(
        target, available_cutoff=holidays_cutoff
    )

    xdisease_viruses = service.CROSS_DISEASE_MAP.get(virus_typ, [])
    xdisease_load = service._cross_disease_load_at_date(
        target,
        xdisease_viruses,
        available_cutoff=wastewater_cutoff,
    )

    grippeweb = service._grippeweb_at_date(target, available_cutoff=are_cutoff)
    notaufnahme = service._notaufnahme_at_date(target, available_cutoff=are_cutoff)

    if target_disease:
        survstat_xd = service._survstat_cross_disease_at_date(
            target,
            target_disease,
            available_cutoff=are_cutoff,
        )
    else:
        survstat_xd = {"survstat_xdisease_1": 0.0, "survstat_xdisease_2": 0.0}

    if are_consultation > 0:
        bio = min(
            wastewater * 0.40 + positivity * 5.0 * 0.35 + are_consultation * 0.25,
            1.0,
        )
    else:
        bio = min(wastewater * 0.5 + positivity * 5.0 * 0.5, 1.0)

    market = service._market_proxy_at_date(target, bio, wastewater, positivity)
    psycho = trends

    context = weather
    if school_start:
        context = min(context * 1.3, 1.0)

    result = {
        "bio": round(bio, 4),
        "market": round(market, 4),
        "psycho": round(psycho, 4),
        "context": round(context, 4),
        "school_start": school_start,
        "wastewater_raw": round(wastewater, 4),
        "positivity_raw": round(min(positivity * 5.0, 1.0), 4),
        "are_consultation_raw": round(are_consultation, 4),
        "trends_raw": round(trends, 4),
        "weather_temp": weather_components["temp_factor"],
        "weather_uv": weather_components["uv_factor"],
        "weather_humidity": weather_components["humidity_factor"],
        "weather_raw": weather,
        "school_start_float": 1.0 if school_start else 0.0,
        "xdisease_load": xdisease_load,
        "ww_lag0w": ww_lags.get("ww_lag0w", 0.0),
        "ww_lag1w": ww_lags.get("ww_lag1w", 0.0),
        "ww_lag2w": ww_lags.get("ww_lag2w", 0.0),
        "ww_lag3w": ww_lags.get("ww_lag3w", 0.0),
        "ww_max_3w": ww_lags.get("ww_max_3w", 0.0),
        "ww_slope_2w": ww_lags.get("ww_slope_2w", 0.0),
        "grippeweb_are": grippeweb["grippeweb_are"],
        "notaufnahme_ari": notaufnahme["notaufnahme_ari"],
        "survstat_xdisease_1": survstat_xd["survstat_xdisease_1"],
        "survstat_xdisease_2": survstat_xd["survstat_xdisease_2"],
    }
    service._scores_cache[cache_key] = result
    return result
