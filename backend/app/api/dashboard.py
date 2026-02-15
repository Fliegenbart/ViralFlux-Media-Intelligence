from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Dict
import logging

from app.db.session import get_db
from app.models.database import (
    WastewaterAggregated,
    GoogleTrendsData,
    GrippeWebData,
    MLForecast,
    WeatherData,
    InventoryLevel,
    LLMRecommendation,
    SchoolHolidays
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview(
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """Full dashboard overview with all metrics."""
    logger.info(f"Fetching dashboard overview for last {days_back} days")
    start_date = datetime.now() - timedelta(days=days_back)

    # 1. Current viral loads
    current_viral_loads = {}
    for virus in ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']:
        latest = db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus
        ).order_by(WastewaterAggregated.datum.desc()).first()

        if latest:
            current_viral_loads[virus] = {
                "value": latest.viruslast,
                "date": latest.datum,
                "trend": _calculate_trend(db, virus)
            }

    # 2. Google Trends
    top_trends = db.query(
        GoogleTrendsData.keyword,
        func.avg(GoogleTrendsData.interest_score).label('avg_score')
    ).filter(
        GoogleTrendsData.datum >= start_date
    ).group_by(GoogleTrendsData.keyword).order_by(
        func.avg(GoogleTrendsData.interest_score).desc()
    ).limit(5).all()

    # 3. GrippeWeb ARE + ILI Inzidenz
    grippeweb_data = {}
    for erkrankung in ['ARE', 'ILI']:
        latest_gw = db.query(GrippeWebData).filter(
            GrippeWebData.erkrankung_typ == erkrankung,
            GrippeWebData.altersgruppe == '00+',
            GrippeWebData.bundesland.is_(None),
        ).order_by(GrippeWebData.datum.desc()).first()

        previous_gw = db.query(GrippeWebData).filter(
            GrippeWebData.erkrankung_typ == erkrankung,
            GrippeWebData.altersgruppe == '00+',
            GrippeWebData.bundesland.is_(None),
        ).order_by(GrippeWebData.datum.desc()).offset(1).first()

        if latest_gw:
            gw_trend = "stabil"
            if previous_gw and previous_gw.inzidenz and latest_gw.inzidenz:
                gw_change = (latest_gw.inzidenz - previous_gw.inzidenz) / previous_gw.inzidenz if previous_gw.inzidenz > 0 else 0
                gw_trend = "steigend" if gw_change > 0.05 else "fallend" if gw_change < -0.05 else "stabil"
            grippeweb_data[erkrankung] = {
                "value": latest_gw.inzidenz,
                "date": latest_gw.datum,
                "kalenderwoche": latest_gw.kalenderwoche,
                "trend": gw_trend,
            }

    # 4. Forecast summary (show all 14 days from latest run, not just future)
    forecast_summary = {}
    for virus in ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']:
        latest_run = db.query(MLForecast).filter(
            MLForecast.virus_typ == virus
        ).order_by(MLForecast.created_at.desc()).first()

        if latest_run:
            forecasts = db.query(MLForecast).filter(
                MLForecast.virus_typ == virus,
                MLForecast.created_at >= latest_run.created_at - timedelta(seconds=10)
            ).order_by(MLForecast.forecast_date.asc()).limit(14).all()

            if forecasts:
                forecast_summary[virus] = {
                    "days": len(forecasts),
                    "trend": "steigend" if forecasts[-1].predicted_value > forecasts[0].predicted_value else "fallend",
                    "confidence": forecasts[0].confidence,
                    "next_7d": round(forecasts[min(6, len(forecasts)-1)].predicted_value, 1),
                    "next_14d": round(forecasts[-1].predicted_value, 1) if len(forecasts) >= 14 else None,
                    "model_version": forecasts[0].model_version
                }

    # 5. Weather
    latest_weather = db.query(WeatherData).order_by(
        WeatherData.datum.desc()
    ).limit(5).all()
    avg_temp = sum(w.temperatur for w in latest_weather) / len(latest_weather) if latest_weather else 0
    avg_humidity = sum(w.luftfeuchtigkeit for w in latest_weather) / len(latest_weather) if latest_weather else 0

    # 6. Inventory overview
    inventory = {}
    subq = db.query(
        InventoryLevel.test_typ,
        func.max(InventoryLevel.datum).label('max_datum')
    ).group_by(InventoryLevel.test_typ).subquery()

    latest_inv = db.query(InventoryLevel).join(
        subq,
        (InventoryLevel.test_typ == subq.c.test_typ) &
        (InventoryLevel.datum == subq.c.max_datum)
    ).all()

    for inv in latest_inv:
        fill_pct = (inv.aktueller_bestand / inv.max_bestand * 100) if inv.max_bestand else 0
        status = "critical" if fill_pct < 20 else "warning" if fill_pct < 40 else "good"
        inventory[inv.test_typ] = {
            "current": inv.aktueller_bestand,
            "min": inv.min_bestand,
            "max": inv.max_bestand,
            "recommended": inv.empfohlener_bestand,
            "lead_time_days": inv.lieferzeit_tage,
            "fill_percentage": round(fill_pct, 1),
            "status": status
        }

    # 7. Latest recommendations
    latest_recs = db.query(LLMRecommendation).order_by(
        LLMRecommendation.created_at.desc()
    ).limit(4).all()

    recommendations = [
        {
            "id": r.id,
            "text": r.recommendation_text,
            "action": r.suggested_action,
            "confidence": r.confidence_score,
            "approved": r.approved,
            "created_at": r.created_at.isoformat()
        }
        for r in latest_recs
    ]

    # 8. Active holidays
    now = datetime.now()
    active_holidays = db.query(SchoolHolidays).filter(
        SchoolHolidays.start_datum <= now,
        SchoolHolidays.end_datum >= now
    ).all()

    return {
        "current_viral_loads": current_viral_loads,
        "top_trends": [
            {"keyword": t.keyword, "score": round(t.avg_score, 1)}
            for t in top_trends
        ],
        "are_inzidenz": {
            "value": grippeweb_data.get('ARE', {}).get('value'),
            "date": grippeweb_data.get('ARE', {}).get('date'),
        },
        "grippeweb": grippeweb_data,
        "forecast_summary": forecast_summary,
        "weather": {
            "avg_temperature": round(avg_temp, 1),
            "avg_humidity": round(avg_humidity, 1)
        },
        "inventory": inventory,
        "recommendations": recommendations,
        "active_holidays": [
            {"bundesland": h.bundesland, "typ": h.ferien_typ}
            for h in active_holidays
        ],
        "has_forecasts": len(forecast_summary) > 0,
        "has_inventory": len(inventory) > 0,
        "timestamp": datetime.utcnow()
    }


VIRUS_TEST_MAP = {
    'Influenza A': 'Influenza A/B Schnelltest',
    'Influenza B': 'Influenza A/B Schnelltest',
    'SARS-CoV-2': 'SARS-CoV-2 PCR',
    'RSV A': 'RSV Schnelltest',
}


@router.get("/timeseries/{virus_typ}")
async def get_timeseries_data(
    virus_typ: str,
    days_back: int = 90,
    include_forecast: bool = True,
    db: Session = Depends(get_db)
):
    """Time series data for a virus type with optional forecast and inventory."""
    logger.info(f"Fetching timeseries for {virus_typ}")
    start_date = datetime.now() - timedelta(days=days_back)

    wastewater = db.query(WastewaterAggregated).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum >= start_date
    ).order_by(WastewaterAggregated.datum.asc()).all()

    forecast = []
    if include_forecast:
        # Get all forecasts from the latest run (not just future ones)
        latest_run = db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ
        ).order_by(MLForecast.created_at.desc()).first()
        if latest_run:
            forecast = db.query(MLForecast).filter(
                MLForecast.virus_typ == virus_typ,
                MLForecast.created_at >= latest_run.created_at - timedelta(seconds=10)
            ).order_by(MLForecast.forecast_date.asc()).limit(14).all()

    # Inventory history for corresponding test type
    test_typ = VIRUS_TEST_MAP.get(virus_typ)
    inventory_history = []
    if test_typ:
        inv_records = db.query(InventoryLevel).filter(
            InventoryLevel.test_typ == test_typ,
            InventoryLevel.datum >= start_date
        ).order_by(InventoryLevel.datum.asc()).all()

        if not inv_records:
            # Fallback: get latest inventory entry regardless of date
            latest_inv = db.query(InventoryLevel).filter(
                InventoryLevel.test_typ == test_typ
            ).order_by(InventoryLevel.datum.desc()).first()
            if latest_inv:
                inv_records = [latest_inv]

        inventory_history = [
            {
                "date": inv.datum.isoformat(),
                "bestand": inv.aktueller_bestand,
                "min_bestand": inv.min_bestand,
                "max_bestand": inv.max_bestand,
                "empfohlen": inv.empfohlener_bestand,
            }
            for inv in inv_records
        ]

    return {
        "virus_typ": virus_typ,
        "test_typ": test_typ,
        "historical": [
            {
                "date": w.datum.isoformat(),
                "viral_load": w.viruslast,
                "normalized": w.viruslast_normalisiert,
                "prediction": w.vorhersage,
                "upper_bound": w.obere_schranke,
                "lower_bound": w.untere_schranke
            }
            for w in wastewater
        ],
        "forecast": [
            {
                "date": f.forecast_date.isoformat(),
                "predicted_value": round(f.predicted_value, 1),
                "upper_bound": round(f.upper_bound, 1) if f.upper_bound else None,
                "lower_bound": round(f.lower_bound, 1) if f.lower_bound else None,
                "confidence": f.confidence
            }
            for f in forecast
        ],
        "inventory": inventory_history,
    }


@router.get("/trends-heatmap")
async def get_trends_heatmap(
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """Google Trends heatmap data."""
    start_date = datetime.now() - timedelta(days=days_back)
    trends = db.query(GoogleTrendsData).filter(
        GoogleTrendsData.datum >= start_date
    ).order_by(GoogleTrendsData.datum.asc()).all()

    heatmap_data = {}
    for trend in trends:
        date_str = trend.datum.strftime('%Y-%m-%d')
        if date_str not in heatmap_data:
            heatmap_data[date_str] = {}
        heatmap_data[date_str][trend.keyword] = trend.interest_score

    return {
        "heatmap": heatmap_data,
        "keywords": list(set(t.keyword for t in trends)),
        "dates": sorted(heatmap_data.keys())
    }


@router.get("/sparkline/{virus_typ}")
async def get_sparkline_data(
    virus_typ: str,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Compact sparkline data for virus cards."""
    start_date = datetime.now() - timedelta(days=days)

    data = db.query(
        WastewaterAggregated.datum,
        WastewaterAggregated.viruslast
    ).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum >= start_date
    ).order_by(WastewaterAggregated.datum.asc()).all()

    return {
        "virus_typ": virus_typ,
        "data": [{"d": d.datum.strftime('%m-%d'), "v": round(d.viruslast, 0)} for d in data]
    }


@router.get("/grippeweb-timeseries")
async def get_grippeweb_timeseries(
    erkrankung: str = "ARE",
    altersgruppe: str = "00+",
    weeks_back: int = 52,
    db: Session = Depends(get_db)
):
    """GrippeWeb ARE/ILI timeseries for charting."""
    start_date = datetime.now() - timedelta(weeks=weeks_back)

    data = db.query(GrippeWebData).filter(
        GrippeWebData.erkrankung_typ == erkrankung,
        GrippeWebData.altersgruppe == altersgruppe,
        GrippeWebData.bundesland.is_(None),
        GrippeWebData.datum >= start_date
    ).order_by(GrippeWebData.datum.asc()).all()

    return {
        "erkrankung": erkrankung,
        "altersgruppe": altersgruppe,
        "data": [
            {
                "date": d.datum.isoformat(),
                "kalenderwoche": d.kalenderwoche,
                "inzidenz": d.inzidenz,
                "meldungen": d.anzahl_meldungen,
            }
            for d in data
        ]
    }


def _calculate_trend(db: Session, virus_typ: str) -> str:
    """Calculate trend for a virus type."""
    last_7_days = db.query(WastewaterAggregated).filter(
        WastewaterAggregated.virus_typ == virus_typ
    ).order_by(WastewaterAggregated.datum.desc()).limit(7).all()

    if len(last_7_days) < 2:
        return "stabil"

    recent_vals = [d.viruslast for d in last_7_days[:3] if d.viruslast]
    older_vals = [d.viruslast for d in last_7_days[4:] if d.viruslast]

    if not recent_vals or not older_vals:
        return "stabil"

    recent = sum(recent_vals) / len(recent_vals)
    older = sum(older_vals) / len(older_vals)

    change = (recent - older) / older if older > 0 else 0

    if change > 0.1:
        return "steigend"
    elif change < -0.1:
        return "fallend"
    return "stabil"
