from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

from app.db.session import get_db
from app.models.database import WastewaterData
from app.services.media.region_tooltip_service import build_region_tooltip
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

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
        func.avg(WastewaterData.vorhersage).label('avg_vorhersage'),
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

        # Vorhersage-Delta
        vorhersage_delta_pct = None
        if r.avg_vorhersage and r.avg_viruslast and r.avg_viruslast > 0:
            vorhersage_delta_pct = ((r.avg_vorhersage - r.avg_viruslast) / r.avg_viruslast) * 100

        regions[r.bundesland] = {
            "name": BUNDESLAND_NAMES.get(r.bundesland, r.bundesland),
            "avg_viruslast": round(r.avg_viruslast, 1),
            "avg_normalisiert": round(r.avg_normalisiert, 1) if r.avg_normalisiert else None,
            "n_standorte": r.n_standorte,
            "einwohner": r.total_einwohner,
            "intensity": round(r.avg_viruslast / max_val, 2) if max_val else 0,
            "trend": trend,
            "change_pct": round(change_pct, 1),
            "tooltip": build_region_tooltip(
                region_name=BUNDESLAND_NAMES.get(r.bundesland, r.bundesland),
                virus_typ=virus_typ,
                trend=trend,
                change_pct=round(change_pct, 1),
                vorhersage_delta_pct=vorhersage_delta_pct,
            ),
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


def _build_activation_suggestions(regional_rows, latest_date, virus_typ: str) -> dict:
    if not regional_rows:
        return {"suggestions": [], "virus_typ": virus_typ, "date": latest_date.isoformat()}

    sorted_regions = sorted(regional_rows, key=lambda r: r.avg_viruslast or 0, reverse=True)
    max_val = sorted_regions[0].avg_viruslast if sorted_regions else 1
    hotspots = [r for r in sorted_regions if r.avg_viruslast and r.avg_viruslast > max_val * 0.7]

    suggestions = []
    for hot in hotspots[:5]:
        shift = min(40.0, max(10.0, (hot.avg_viruslast / (max_val or 1)) * 35.0))
        suggestions.append({
            "region": hot.bundesland,
            "region_name": BUNDESLAND_NAMES.get(hot.bundesland, hot.bundesland),
            # Legacy-Felder für alte Frontends
            "from_region": "BUDGET_POOL",
            "from_name": "Nationales Budget",
            "to_region": hot.bundesland,
            "to_name": BUNDESLAND_NAMES.get(hot.bundesland, hot.bundesland),
            "test_typ": "MediaBudget",
            "reason": (
                f"{BUNDESLAND_NAMES.get(hot.bundesland, hot.bundesland)} liegt im oberen "
                f"Viruslast-Cluster ({round(hot.avg_viruslast, 1)})."
            ),
            "priority": "high" if hot.avg_viruslast > max_val * 0.85 else "medium",
            "budget_shift_pct": round(shift, 1),
            "channel_mix": {
                "programmatic": 45,
                "social": 30,
                "search": 25,
            },
        })

    return {
        "virus_typ": virus_typ,
        "suggestions": suggestions,
        "date": latest_date.isoformat(),
    }


@router.get("/activation-suggestions/{virus_typ}")
async def get_activation_suggestions(
    virus_typ: str,
    db: Session = Depends(get_db)
):
    """Media Activation Suggestions auf Basis regionaler Virusaktivität."""

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

    return _build_activation_suggestions(regional, latest_date, virus_typ)


@router.get("/standorte/{virus_typ}")
async def get_standorte_map(
    virus_typ: str,
    db: Session = Depends(get_db),
):
    """Kläranlagen-Standorte mit aktueller Viruslast für Karten-Overlay.

    Liefert pro Kläranlage: Koordinaten, aktuelle Viruslast, Trend,
    angeschlossene Einwohner. Für die Deutschland-Karte als Punkt-Layer.
    """
    latest_date = db.query(func.max(WastewaterData.datum)).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.latitude.isnot(None),
    ).scalar()

    if not latest_date:
        return {"virus_typ": virus_typ, "standorte": [], "has_data": False}

    # Aktuelle Messwerte
    current = db.query(WastewaterData).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.datum == latest_date,
        WastewaterData.latitude.isnot(None),
    ).all()

    # Vorwoche für Trend
    prev_date = latest_date - timedelta(days=7)
    prev_rows = db.query(
        WastewaterData.standort,
        WastewaterData.viruslast,
    ).filter(
        WastewaterData.virus_typ == virus_typ,
        WastewaterData.datum >= prev_date - timedelta(days=2),
        WastewaterData.datum <= prev_date + timedelta(days=2),
    ).all()
    prev_map = {r.standort: r.viruslast for r in prev_rows}

    all_values = [r.viruslast for r in current if r.viruslast]
    max_val = max(all_values) if all_values else 1

    standorte = []
    for r in current:
        if not r.viruslast:
            continue

        prev_val = prev_map.get(r.standort)
        if prev_val and prev_val > 0:
            change_pct = ((r.viruslast - prev_val) / prev_val) * 100
            trend = "steigend" if change_pct > 10 else "fallend" if change_pct < -10 else "stabil"
        else:
            change_pct = 0.0
            trend = "stabil"

        standorte.append({
            "standort": r.standort,
            "bundesland": r.bundesland,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "viruslast": round(r.viruslast, 1),
            "viruslast_normalisiert": round(r.viruslast_normalisiert, 1) if r.viruslast_normalisiert else None,
            "vorhersage": round(r.vorhersage, 1) if r.vorhersage else None,
            "einwohner": r.einwohner,
            "unter_bg": r.unter_bg,
            "intensity": round(r.viruslast / max_val, 2) if max_val else 0,
            "trend": trend,
            "change_pct": round(change_pct, 1),
        })

    return {
        "virus_typ": virus_typ,
        "date": latest_date.isoformat(),
        "standorte": standorte,
        "has_data": len(standorte) > 0,
        "total_standorte": len(standorte),
        "max_viruslast": round(max_val, 1),
    }


@router.get("/transfer-suggestions/{virus_typ}")
async def get_transfer_suggestions(
    virus_typ: str,
    db: Session = Depends(get_db)
):
    """Legacy-Alias: liefert jetzt Activation-Suggestions statt Transferlogik."""
    return await get_activation_suggestions(virus_typ=virus_typ, db=db)
