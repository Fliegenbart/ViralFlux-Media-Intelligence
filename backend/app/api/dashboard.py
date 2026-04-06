from app.core.time import utc_now
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Dict
import logging

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.database import (
    WastewaterAggregated,
    GoogleTrendsData,
    GrippeWebData,
    NotaufnahmeSyndromData,
    SurvstatWeeklyData,
    MLForecast,
    WeatherData,
    InventoryLevel,
    LLMRecommendation,
    SchoolHolidays
)

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


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

    # 3b. Notaufnahmesurveillance (RKI/AKTIN)
    notaufnahme_data = {}
    for syndrome in ['ARI', 'ILI', 'COVID']:
        latest_no = db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.age_group == '00+',
            NotaufnahmeSyndromData.ed_type == 'all',
        ).order_by(NotaufnahmeSyndromData.datum.desc()).first()

        previous_no = db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.age_group == '00+',
            NotaufnahmeSyndromData.ed_type == 'all',
        ).order_by(NotaufnahmeSyndromData.datum.desc()).offset(1).first()

        if latest_no:
            latest_value = (
                latest_no.relative_cases_7day_ma
                if latest_no.relative_cases_7day_ma is not None
                else latest_no.relative_cases
            )
            previous_value = None
            if previous_no:
                previous_value = (
                    previous_no.relative_cases_7day_ma
                    if previous_no.relative_cases_7day_ma is not None
                    else previous_no.relative_cases
                )

            no_trend = "stabil"
            if previous_value is not None and latest_value is not None:
                no_change = (
                    (latest_value - previous_value) / previous_value
                    if previous_value > 0 else 0
                )
                no_trend = "steigend" if no_change > 0.05 else "fallend" if no_change < -0.05 else "stabil"

            notaufnahme_data[syndrome] = {
                "value": latest_value,
                "date": latest_no.datum,
                "ed_count": latest_no.ed_count,
                "expected_value": latest_no.expected_value,
                "trend": no_trend,
            }

    # 3c. SURVSTAT (RKI) — manuell importierte Wochenwerte
    survstat_data = {}
    latest_surv_week = db.query(func.max(SurvstatWeeklyData.week_start)).filter(
        SurvstatWeeklyData.bundesland == "Gesamt"
    ).scalar()

    if latest_surv_week:
        latest_surv_rows = db.query(SurvstatWeeklyData).filter(
            SurvstatWeeklyData.week_start == latest_surv_week,
            SurvstatWeeklyData.bundesland == "Gesamt",
        ).all()

        prev_surv_week = db.query(func.max(SurvstatWeeklyData.week_start)).filter(
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.week_start < latest_surv_week,
        ).scalar()

        prev_map: dict[str, float | None] = {}
        if prev_surv_week:
            prev_rows = db.query(SurvstatWeeklyData).filter(
                SurvstatWeeklyData.week_start == prev_surv_week,
                SurvstatWeeklyData.bundesland == "Gesamt",
            ).all()
            prev_map = {
                row.disease: row.incidence
                for row in prev_rows
            }

        latest_map = {
            row.disease: row
            for row in latest_surv_rows
            if row.incidence is not None
        }

        top_non_all = sorted(
            [row for row in latest_surv_rows if row.disease != "All" and row.incidence is not None],
            key=lambda row: row.incidence or 0.0,
            reverse=True,
        )

        selected_diseases: list[str] = []
        if "All" in latest_map:
            selected_diseases.append("All")
        selected_diseases.extend([row.disease for row in top_non_all[:2]])

        if not selected_diseases:
            selected_diseases = [
                row.disease for row in sorted(
                    [r for r in latest_surv_rows if r.incidence is not None],
                    key=lambda r: r.incidence or 0.0,
                    reverse=True,
                )[:3]
            ]

        for disease in dict.fromkeys(selected_diseases):
            latest_row = latest_map.get(disease)
            if not latest_row:
                continue
            survstat_data[disease] = {
                "value": latest_row.incidence,
                "week_label": latest_row.week_label,
                "week_start": latest_row.week_start,
                "bundesland": latest_row.bundesland,
                "trend": _calculate_relative_trend(latest_row.incidence, prev_map.get(disease)),
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
    temps = [w.temperatur for w in latest_weather if w.temperatur is not None]
    humids = [w.luftfeuchtigkeit for w in latest_weather if w.luftfeuchtigkeit is not None]
    avg_temp = sum(temps) / len(temps) if temps else 0
    avg_humidity = sum(humids) / len(humids) if humids else 0

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
        "notaufnahme": notaufnahme_data,
        "survstat": survstat_data,
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
        "timestamp": utc_now()
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


@router.get("/notaufnahme-timeseries")
async def get_notaufnahme_timeseries(
    syndrome: str = "ARI",
    age_group: str = "00+",
    ed_type: str = "all",
    days_back: int = 365,
    db: Session = Depends(get_db)
):
    """Notaufnahmesurveillance timeseries for charting."""
    syndrome = syndrome.upper()
    if syndrome not in {"ARI", "SARI", "ILI", "COVID", "GI"}:
        raise HTTPException(status_code=400, detail="Unsupported syndrome")

    start_date = datetime.now() - timedelta(days=days_back)

    data = db.query(NotaufnahmeSyndromData).filter(
        NotaufnahmeSyndromData.syndrome == syndrome,
        NotaufnahmeSyndromData.age_group == age_group,
        NotaufnahmeSyndromData.ed_type == ed_type,
        NotaufnahmeSyndromData.datum >= start_date
    ).order_by(NotaufnahmeSyndromData.datum.asc()).all()

    return {
        "syndrome": syndrome,
        "age_group": age_group,
        "ed_type": ed_type,
        "data": [
            {
                "date": d.datum.isoformat(),
                "relative_cases": d.relative_cases,
                "relative_cases_7day_ma": d.relative_cases_7day_ma,
                "expected_value": d.expected_value,
                "expected_lowerbound": d.expected_lowerbound,
                "expected_upperbound": d.expected_upperbound,
                "ed_count": d.ed_count,
            }
            for d in data
        ]
    }


@router.get("/survstat-timeseries")
async def get_survstat_timeseries(
    disease: str = "All",
    bundesland: str = "Gesamt",
    weeks_back: int = 52,
    db: Session = Depends(get_db)
):
    """SURVSTAT Wochen-Zeitreihe für ein Krankheitsbild."""
    latest_week = db.query(func.max(SurvstatWeeklyData.week_start)).filter(
        SurvstatWeeklyData.disease == disease,
        SurvstatWeeklyData.bundesland == bundesland,
    ).scalar()

    if not latest_week:
        return {
            "disease": disease,
            "bundesland": bundesland,
            "data": [],
        }

    start_date = latest_week - timedelta(weeks=weeks_back)
    data = db.query(SurvstatWeeklyData).filter(
        SurvstatWeeklyData.disease == disease,
        SurvstatWeeklyData.bundesland == bundesland,
        SurvstatWeeklyData.week_start >= start_date,
    ).order_by(SurvstatWeeklyData.week_start.asc()).all()

    return {
        "disease": disease,
        "bundesland": bundesland,
        "data": [
            {
                "week_label": row.week_label,
                "week_start": row.week_start.isoformat(),
                "incidence": row.incidence,
            }
            for row in data
        ],
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


def _calculate_relative_trend(latest: float | None, previous: float | None) -> str:
    """Trend zwischen zwei Messwerten mit +/-5%-Band."""
    if latest is None or previous is None:
        return "stabil"
    if previous <= 0:
        return "steigend" if latest > 0 else "stabil"

    delta = (latest - previous) / previous
    if delta > 0.05:
        return "steigend"
    if delta < -0.05:
        return "fallend"
    return "stabil"
