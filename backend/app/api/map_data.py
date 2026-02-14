from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

from app.db.session import get_db
from app.models.database import WastewaterData, MLForecast, InventoryLevel

logger = logging.getLogger(__name__)
router = APIRouter()

BUNDESLAND_NAMES = {
    'BW': 'Baden-Württemberg', 'BY': 'Bayern', 'BE': 'Berlin',
    'BB': 'Brandenburg', 'HB': 'Bremen', 'HH': 'Hamburg',
    'HE': 'Hessen', 'MV': 'Mecklenburg-Vorpommern', 'NI': 'Niedersachsen',
    'NW': 'Nordrhein-Westfalen', 'RP': 'Rheinland-Pfalz', 'SL': 'Saarland',
    'SN': 'Sachsen', 'ST': 'Sachsen-Anhalt', 'SH': 'Schleswig-Holstein',
    'TH': 'Thüringen',
}


@router.get("/regional/{virus_typ}")
async def get_regional_data(
    virus_typ: str,
    db: Session = Depends(get_db)
):
    """Get latest viral load per Bundesland for map visualization."""
    # Get latest date with data
    latest_date = db.query(func.max(WastewaterData.datum)).filter(
        WastewaterData.virus_typ == virus_typ
    ).scalar()

    if not latest_date:
        return {"virus_typ": virus_typ, "regions": {}, "has_data": False}

    # Aggregate per Bundesland: average viruslast across Standorte
    results = db.query(
        WastewaterData.bundesland,
        func.avg(WastewaterData.viruslast).label('avg_viruslast'),
        func.avg(WastewaterData.viruslast_normalisiert).label('avg_normalisiert'),
        func.count(WastewaterData.standort.distinct()).label('n_standorte'),
        func.sum(WastewaterData.einwohner).label('total_einwohner'),
    ).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.datum == latest_date,
    ).group_by(WastewaterData.bundesland).all()

    # Also get the previous week for trend calculation
    prev_date = latest_date - timedelta(days=7)
    prev_results = db.query(
        WastewaterData.bundesland,
        func.avg(WastewaterData.viruslast).label('avg_viruslast'),
    ).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.datum >= prev_date - timedelta(days=2),
        WastewaterData.datum <= prev_date + timedelta(days=2),
    ).group_by(WastewaterData.bundesland).all()

    prev_map = {r.bundesland: r.avg_viruslast for r in prev_results}

    # Find max for intensity scaling
    all_values = [r.avg_viruslast for r in results if r.avg_viruslast]
    max_val = max(all_values) if all_values else 1

    regions = {}
    for r in results:
        if not r.bundesland or not r.avg_viruslast:
            continue

        prev_val = prev_map.get(r.bundesland)
        if prev_val and prev_val > 0:
            change_pct = ((r.avg_viruslast - prev_val) / prev_val) * 100
            trend = "steigend" if change_pct > 10 else "fallend" if change_pct < -10 else "stabil"
        else:
            change_pct = 0
            trend = "stabil"

        regions[r.bundesland] = {
            "name": BUNDESLAND_NAMES.get(r.bundesland, r.bundesland),
            "avg_viruslast": round(r.avg_viruslast, 1),
            "avg_normalisiert": round(r.avg_normalisiert, 1) if r.avg_normalisiert else None,
            "n_standorte": r.n_standorte,
            "einwohner": r.total_einwohner,
            "intensity": round(r.avg_viruslast / max_val, 3) if max_val else 0,
            "trend": trend,
            "change_pct": round(change_pct, 1),
        }

    return {
        "virus_typ": virus_typ,
        "date": latest_date.isoformat(),
        "regions": regions,
        "has_data": len(regions) > 0,
        "max_viruslast": round(max_val, 1),
    }


@router.get("/regional-timeseries/{virus_typ}/{bundesland}")
async def get_regional_timeseries(
    virus_typ: str,
    bundesland: str,
    days_back: int = 90,
    db: Session = Depends(get_db)
):
    """Get timeseries for a specific Bundesland."""
    start_date = datetime.now() - timedelta(days=days_back)

    data = db.query(
        WastewaterData.datum,
        func.avg(WastewaterData.viruslast).label('avg_viruslast'),
        func.count(WastewaterData.standort.distinct()).label('n_standorte'),
    ).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.bundesland == bundesland,
        WastewaterData.datum >= start_date,
    ).group_by(WastewaterData.datum).order_by(WastewaterData.datum.asc()).all()

    return {
        "virus_typ": virus_typ,
        "bundesland": bundesland,
        "name": BUNDESLAND_NAMES.get(bundesland, bundesland),
        "timeseries": [
            {"date": d.datum.isoformat(), "viruslast": round(d.avg_viruslast, 1), "n_standorte": d.n_standorte}
            for d in data
        ]
    }


@router.get("/transfer-suggestions/{virus_typ}")
async def get_transfer_suggestions(
    virus_typ: str,
    db: Session = Depends(get_db)
):
    """Suggest inventory transfers between locations based on regional virus activity."""
    from app.api.dashboard import VIRUS_TEST_MAP

    test_typ = VIRUS_TEST_MAP.get(virus_typ)
    if not test_typ:
        return {"suggestions": [], "virus_typ": virus_typ}

    # Get regional virus data
    latest_date = db.query(func.max(WastewaterData.datum)).filter(
        WastewaterData.virus_typ == virus_typ
    ).scalar()

    if not latest_date:
        return {"suggestions": [], "virus_typ": virus_typ}

    regional = db.query(
        WastewaterData.bundesland,
        func.avg(WastewaterData.viruslast).label('avg_viruslast'),
    ).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.datum == latest_date,
    ).group_by(WastewaterData.bundesland).all()

    if not regional:
        return {"suggestions": [], "virus_typ": virus_typ}

    # Sort by intensity
    sorted_regions = sorted(regional, key=lambda r: r.avg_viruslast or 0, reverse=True)
    max_val = sorted_regions[0].avg_viruslast if sorted_regions else 1

    suggestions = []
    hotspots = [r for r in sorted_regions if r.avg_viruslast and r.avg_viruslast > max_val * 0.7]
    low_regions = [r for r in sorted_regions if r.avg_viruslast and r.avg_viruslast < max_val * 0.3]

    for hot in hotspots[:3]:
        for low in low_regions[:2]:
            suggestions.append({
                "from_region": low.bundesland,
                "from_name": BUNDESLAND_NAMES.get(low.bundesland, low.bundesland),
                "to_region": hot.bundesland,
                "to_name": BUNDESLAND_NAMES.get(hot.bundesland, hot.bundesland),
                "reason": f"{BUNDESLAND_NAMES.get(hot.bundesland, hot.bundesland)} hat {round(hot.avg_viruslast / (low.avg_viruslast or 1), 1)}x hoehere Viruslast",
                "priority": "high" if hot.avg_viruslast > max_val * 0.85 else "medium",
                "test_typ": test_typ,
            })

    return {
        "virus_typ": virus_typ,
        "test_typ": test_typ,
        "suggestions": suggestions[:5],
        "date": latest_date.isoformat(),
    }
