"""API-Endpunkte für Marketing Opportunity Engine."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate")
async def generate_opportunities(db: Session = Depends(get_db)):
    """Alle Detektoren ausführen und neue Marketing-Opportunities erzeugen.

    Analysiert: BfArM-Engpässe, UV/Wetter, ERP-Bestellgeschwindigkeit.
    Gibt priorisiertes JSON für CRM-Integration zurück.
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    return engine.generate_opportunities()


@router.get("/list")
async def list_opportunities(
    type: str = None,
    status: str = None,
    min_urgency: float = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Gespeicherte Opportunities abrufen mit optionalen Filtern.

    type: RESOURCE_SCARCITY, SEASONAL_DEFICIENCY, PREDICTIVE_SALES_SPIKE
    status: NEW, URGENT, SENT, CONVERTED, EXPIRED, DISMISSED
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    opportunities = engine.get_opportunities(
        type_filter=type,
        status_filter=status,
        min_urgency=min_urgency,
        limit=limit,
    )
    return {"total": len(opportunities), "opportunities": opportunities}


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Aggregierte Statistiken über alle Opportunities."""
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    return engine.get_stats()


@router.get("/export/crm")
async def export_crm_json(
    ids: str = None,
    db: Session = Depends(get_db),
):
    """CRM-Export als JSON. Markiert exportierte Opportunities.

    ids: Komma-getrennte Opportunity-IDs. Ohne IDs werden alle NEW/URGENT exportiert.
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    opportunity_ids = ids.split(",") if ids else None
    return engine.export_crm_json(opportunity_ids=opportunity_ids)


@router.get("/{opportunity_id}")
async def get_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    """Einzelne Opportunity abrufen."""
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    results = engine.get_opportunities()
    for opp in results:
        if opp.get("id") == opportunity_id:
            return opp

    raise HTTPException(status_code=404, detail=f"Opportunity {opportunity_id} nicht gefunden")


@router.patch("/{opportunity_id}/status")
async def update_status(
    opportunity_id: str,
    status: str,
    db: Session = Depends(get_db),
):
    """Status einer Opportunity aktualisieren.

    Erlaubte Werte: NEW, URGENT, SENT, CONVERTED, EXPIRED, DISMISSED
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    result = engine.update_status(opportunity_id, status)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
