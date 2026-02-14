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
    WeatherData
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview(
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """
    Hole Dashboard-Übersicht mit allen wichtigen Metriken.
    
    Args:
        days_back: Anzahl Tage zurück für historische Daten
    """
    logger.info(f"Fetching dashboard overview for last {days_back} days")
    
    start_date = datetime.now() - timedelta(days=days_back)
    
    # 1. Aktuelle Viruslast (letzte verfügbare Daten)
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
    
    # 2. Google Trends Top Keywords
    top_trends = db.query(
        GoogleTrendsData.keyword,
        func.avg(GoogleTrendsData.interest_score).label('avg_score')
    ).filter(
        GoogleTrendsData.datum >= start_date
    ).group_by(
        GoogleTrendsData.keyword
    ).order_by(
        func.avg(GoogleTrendsData.interest_score).desc()
    ).limit(5).all()
    
    # 3. ARE Inzidenz (aktuell)
    latest_are = db.query(GrippeWebData).filter(
        GrippeWebData.erkrankung_typ == 'ARE',
        GrippeWebData.bundesland.is_(None)
    ).order_by(GrippeWebData.datum.desc()).first()
    
    # 4. Aktuelle Prognose-Summary
    forecast_summary = {}
    for virus in ['Influenza A', 'Influenza B', 'SARS-CoV-2']:
        forecast = db.query(MLForecast).filter(
            MLForecast.virus_typ == virus,
            MLForecast.forecast_date >= datetime.now()
        ).order_by(MLForecast.forecast_date.asc()).limit(14).all()
        
        if forecast:
            forecast_summary[virus] = {
                "days": len(forecast),
                "trend": "steigend" if forecast[-1].predicted_value > forecast[0].predicted_value else "fallend",
                "confidence": forecast[0].confidence
            }
    
    # 5. Wetter (aktuell)
    latest_weather = db.query(WeatherData).order_by(
        WeatherData.datum.desc()
    ).limit(5).all()
    
    avg_temp = sum(w.temperatur for w in latest_weather) / len(latest_weather) if latest_weather else 0
    avg_humidity = sum(w.luftfeuchtigkeit for w in latest_weather) / len(latest_weather) if latest_weather else 0
    
    return {
        "current_viral_loads": current_viral_loads,
        "top_trends": [
            {"keyword": t.keyword, "score": round(t.avg_score, 1)}
            for t in top_trends
        ],
        "are_inzidenz": {
            "value": latest_are.inzidenz if latest_are else None,
            "date": latest_are.datum if latest_are else None
        },
        "forecast_summary": forecast_summary,
        "weather": {
            "avg_temperature": round(avg_temp, 1),
            "avg_humidity": round(avg_humidity, 1)
        },
        "timestamp": datetime.utcnow()
    }


@router.get("/timeseries/{virus_typ}")
async def get_timeseries_data(
    virus_typ: str,
    days_back: int = 90,
    db: Session = Depends(get_db)
):
    """
    Hole Zeitreihen-Daten für einen Virustyp.
    
    Args:
        virus_typ: Virustyp (z.B. 'Influenza A')
        days_back: Anzahl Tage zurück
    """
    logger.info(f"Fetching timeseries for {virus_typ}")
    
    start_date = datetime.now() - timedelta(days=days_back)
    
    # Abwasser-Daten
    wastewater = db.query(WastewaterAggregated).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum >= start_date
    ).order_by(WastewaterAggregated.datum.asc()).all()
    
    # ML Prognose
    forecast = db.query(MLForecast).filter(
        MLForecast.virus_typ == virus_typ,
        MLForecast.forecast_date >= datetime.now()
    ).order_by(MLForecast.forecast_date.asc()).limit(14).all()
    
    return {
        "virus_typ": virus_typ,
        "historical": [
            {
                "date": w.datum,
                "viral_load": w.viruslast,
                "prediction": w.vorhersage,
                "upper_bound": w.obere_schranke,
                "lower_bound": w.untere_schranke
            }
            for w in wastewater
        ],
        "forecast": [
            {
                "date": f.forecast_date,
                "predicted_value": f.predicted_value,
                "upper_bound": f.upper_bound,
                "lower_bound": f.lower_bound,
                "confidence": f.confidence
            }
            for f in forecast
        ]
    }


@router.get("/trends-heatmap")
async def get_trends_heatmap(
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """
    Hole Google Trends Heatmap-Daten.
    
    Returns:
        Matrix von Keywords x Zeitpunkte mit Scores
    """
    logger.info("Fetching trends heatmap data")
    
    start_date = datetime.now() - timedelta(days=days_back)
    
    trends = db.query(GoogleTrendsData).filter(
        GoogleTrendsData.datum >= start_date
    ).order_by(
        GoogleTrendsData.datum.asc()
    ).all()
    
    # Gruppiere nach Datum und Keyword
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


def _calculate_trend(db: Session, virus_typ: str) -> str:
    """Berechne Trend (steigend/fallend/stabil) für einen Virustyp."""
    last_7_days = db.query(WastewaterAggregated).filter(
        WastewaterAggregated.virus_typ == virus_typ
    ).order_by(WastewaterAggregated.datum.desc()).limit(7).all()
    
    if len(last_7_days) < 2:
        return "stabil"
    
    recent = sum(d.viruslast for d in last_7_days[:3] if d.viruslast) / 3
    older = sum(d.viruslast for d in last_7_days[4:] if d.viruslast) / 3
    
    change = (recent - older) / older if older > 0 else 0
    
    if change > 0.1:
        return "steigend"
    elif change < -0.1:
        return "fallend"
    else:
        return "stabil"
