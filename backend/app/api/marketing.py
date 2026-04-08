"""API-Endpunkte für Marketing Opportunity Engine."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
import logging

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

_WORKFLOW_TO_LEGACY = {
    "DRAFT": "NEW",
    "READY": "NEW",
    "APPROVED": "SENT",
    "ACTIVATED": "CONVERTED",
    "DISMISSED": "DISMISSED",
    "EXPIRED": "EXPIRED",
}


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_opportunities(request: Request, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
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
    brand: str = None,
    min_urgency: float = None,
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Gespeicherte Opportunities abrufen mit optionalen Filtern.

    type: RESOURCE_SCARCITY, SEASONAL_DEFICIENCY, PREDICTIVE_SALES_SPIKE
    status: NEW, URGENT, SENT, CONVERTED, EXPIRED, DISMISSED
    skip: Offset für Pagination (default 0)
    limit: Max Ergebnisse pro Seite (default 50)
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    total_count = engine.count_opportunities(
        type_filter=type,
        status_filter=status,
        brand_filter=brand,
        min_urgency=min_urgency,
    )
    opportunities = engine.get_opportunities(
        type_filter=type,
        status_filter=status,
        brand_filter=brand,
        min_urgency=min_urgency,
        limit=limit,
        skip=skip,
        normalize_status=True,
    )

    # Legacy-kompatible Ausgabe für bestehende Vertriebsradar-UI.
    legacy_opps = []
    for opp in opportunities:
        copy = dict(opp)
        workflow_status = opp.get("status")
        copy["workflow_status"] = workflow_status
        copy["status"] = _WORKFLOW_TO_LEGACY.get(workflow_status, workflow_status)
        legacy_opps.append(copy)

    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "page": skip // limit + 1 if limit else 1,
        "pages": (total_count + limit - 1) // limit if limit else 1,
        "opportunities": legacy_opps,
    }


@router.get("/roi")
async def get_roi_retrospective(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """ROI-Retrospektive: Simulierter Wert vergangener Empfehlungen."""
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    return engine.get_roi_retrospective()


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Aggregierte Statistiken über alle Opportunities."""
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    stats = engine.get_stats()
    by_status = stats.get("by_status", {})
    legacy = {
        "NEW": by_status.get("DRAFT", 0) + by_status.get("READY", 0),
        "SENT": by_status.get("APPROVED", 0),
        "CONVERTED": by_status.get("ACTIVATED", 0),
        "EXPIRED": by_status.get("EXPIRED", 0),
        "DISMISSED": by_status.get("DISMISSED", 0),
    }
    stats["by_status_workflow"] = by_status
    stats["by_status"] = legacy
    return stats


@router.post("/export/crm")
async def export_crm_json(
    ids: str = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """CRM-Export als JSON. Markiert exportierte Opportunities.

    ids: Komma-getrennte Opportunity-IDs. Ohne IDs werden alle NEW/URGENT exportiert.
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    opportunity_ids = ids.split(",") if ids else None
    return engine.export_crm_json(opportunity_ids=opportunity_ids)


@router.get("/briefing/{opportunity_id}.pdf")
async def download_briefing_pdf(
    opportunity_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """PDF-Briefing einer Opportunity herunterladen."""
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
    from app.services.marketing_engine.briefing_pdf import generate_briefing_pdf

    engine = MarketingOpportunityEngine(db)
    results = engine.get_opportunities(normalize_status=True)
    opp = next((o for o in results if o.get("id") == opportunity_id), None)
    if not opp:
        raise HTTPException(status_code=404, detail=f"Opportunity {opportunity_id} nicht gefunden")

    pdf_bytes = generate_briefing_pdf(opp)
    filename = f"Briefing_{opp.get('type', 'OPP')}_{opportunity_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{opportunity_id}")
async def get_opportunity(opportunity_id: str, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Einzelne Opportunity abrufen."""
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    results = engine.get_opportunities(normalize_status=True)
    for opp in results:
        if opp.get("id") == opportunity_id:
            copy = dict(opp)
            workflow_status = opp.get("status")
            copy["workflow_status"] = workflow_status
            copy["status"] = _WORKFLOW_TO_LEGACY.get(workflow_status, workflow_status)
            return copy

    raise HTTPException(status_code=404, detail=f"Opportunity {opportunity_id} nicht gefunden")


@router.patch("/{opportunity_id}/status")
async def update_status(
    opportunity_id: str,
    status: str,
    dismiss_reason: str | None = None,
    dismiss_comment: str | None = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Status einer Opportunity aktualisieren.

    Erlaubte Werte:
    - Legacy: NEW, URGENT, SENT, CONVERTED, EXPIRED, DISMISSED
    - Workflow: DRAFT, READY, APPROVED, ACTIVATED, DISMISSED, EXPIRED

    Bei DISMISSED können optional dismiss_reason (Kategorie) und
    dismiss_comment (Freitext) übergeben werden.
    """
    from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

    engine = MarketingOpportunityEngine(db)
    result = engine.update_status(
        opportunity_id,
        status,
        dismiss_reason=dismiss_reason,
        dismiss_comment=dismiss_comment,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    workflow_status = result.get("new_status")
    result["workflow_status"] = workflow_status
    result["new_status"] = _WORKFLOW_TO_LEGACY.get(workflow_status, workflow_status)
    return result
