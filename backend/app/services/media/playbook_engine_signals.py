"""Signal-loading helpers for the playbook engine."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func

from app.core.time import utc_now
from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    PollenData,
    WeatherData,
)
from app.services.data_ingest.weather_service import CITY_STATE_MAP
from app.services.media.playbook_engine import REGION_NAME_TO_CODE


def are_growth_by_region(engine) -> dict[str, float]:
    rows = engine.db.query(AREKonsultation).filter(
        AREKonsultation.altersgruppe == "00+",
        AREKonsultation.bundesland != "Bundesweit",
    ).order_by(AREKonsultation.datum.desc()).all()
    grouped: dict[str, list[AREKonsultation]] = {}
    for row in rows:
        code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
        if not code:
            continue
        grouped.setdefault(code, []).append(row)

    growth: dict[str, float] = {}
    for code, values in grouped.items():
        series = sorted(values, key=lambda item: item.datum)
        if len(series) < 2:
            continue
        latest = float(series[-1].konsultationsinzidenz or 0.0)
        prev = float(series[-2].konsultationsinzidenz or 0.0)
        if prev <= 0:
            growth[code] = 0.0 if latest <= 0 else 1.0
        else:
            growth[code] = (latest - prev) / prev
    return growth


def weather_burden_by_region(engine) -> dict[str, float]:
    now = utc_now()
    until = now + timedelta(days=8)
    rows = engine.db.query(WeatherData).filter(
        WeatherData.data_type == "DAILY_FORECAST",
        WeatherData.datum >= now,
        WeatherData.datum <= until,
    ).all()
    if not rows:
        return {}

    per_region: dict[str, list[float]] = {}
    for row in rows:
        state = CITY_STATE_MAP.get(str(row.city or ""))
        if not state:
            continue
        code = REGION_NAME_TO_CODE.get(state.lower())
        if not code:
            continue

        temp = float(row.temperatur) if row.temperatur is not None else 7.0
        uv = float(row.uv_index) if row.uv_index is not None else 2.0
        rain_prob = float(row.niederschlag_wahrscheinlichkeit) if row.niederschlag_wahrscheinlichkeit is not None else 35.0
        rain_prob = rain_prob / 100.0 if rain_prob > 1.0 else rain_prob
        temp_factor = max(0.0, min(1.0, (10.0 - temp) / 12.0))
        uv_factor = max(0.0, min(1.0, (2.0 - uv) / 2.0))
        rain_factor = max(0.0, min(1.0, rain_prob))
        burden = (temp_factor * 0.45 + uv_factor * 0.20 + rain_factor * 0.35) * 100.0
        per_region.setdefault(code, []).append(burden)

    return {
        code: round(sum(values) / max(len(values), 1), 2)
        for code, values in per_region.items()
    }


def pollen_by_region(engine) -> dict[str, float]:
    latest = engine.db.query(func.max(PollenData.datum)).scalar()
    if not latest:
        return {}
    if (utc_now() - latest) > timedelta(days=3):
        return {}
    rows = engine.db.query(
        PollenData.region_code,
        func.max(PollenData.pollen_index).label("max_index"),
    ).filter(
        PollenData.datum == latest,
    ).group_by(PollenData.region_code).all()
    return {
        str(row.region_code).upper(): round(max(0.0, min(100.0, (float(row.max_index or 0.0) / 3.0) * 100.0)), 2)
        for row in rows
    }


def google_signal_score(engine, keywords: list[str]) -> dict[str, float]:
    now = utc_now()
    recent_start = now - timedelta(days=14)
    prev_start = now - timedelta(days=28)
    prev_end = recent_start

    base = engine.db.query(func.avg(GoogleTrendsData.interest_score))
    recent = (
        base.filter(
            GoogleTrendsData.datum >= recent_start,
            GoogleTrendsData.datum <= now,
            engine._keyword_filter(keywords),
        ).scalar()
        or 0.0
    )
    previous = (
        base.filter(
            GoogleTrendsData.datum >= prev_start,
            GoogleTrendsData.datum < prev_end,
            engine._keyword_filter(keywords),
        ).scalar()
        or 0.0
    )
    return {
        "current": float(recent),
        "previous": float(previous),
        "delta": float(recent) - float(previous),
    }
