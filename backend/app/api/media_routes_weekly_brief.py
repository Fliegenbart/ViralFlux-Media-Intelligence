"""Dashboard and weekly brief routes for the media API."""

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.api.media_contracts import json_safe_response
from app.db.schema_contracts import MLForecastSchemaMismatchError
from app.db.session import get_db
from app.services.media.cockpit_service import MediaCockpitService
from app.services.media.v2_service import MediaV2Service

router = APIRouter()


@router.get("/cockpit", dependencies=[Depends(get_current_user)])
async def get_media_cockpit(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    db: Session = Depends(get_db),
):
    """Aggregierter One-shot Payload für das Map-first Dashboard."""
    service = MediaCockpitService(db)
    try:
        return service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/decision", dependencies=[Depends(get_current_user)])
async def get_media_decision(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
    db: Session = Depends(get_db),
):
    """V2 Decision-View Payload mit WeeklyDecision, Gate-Mix und Model/Truth-Kontext."""
    try:
        return json_safe_response(
            MediaV2Service(db).get_decision_payload(
                virus_typ=virus_typ,
                target_source=target_source,
                brand=brand,
            )
        )
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/regions", dependencies=[Depends(get_current_user)])
async def get_media_regions(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
    db: Session = Depends(get_db),
):
    """V2 Regionen-Workbench Payload mit Signal-Treibern und Prioritätslogik."""
    try:
        return json_safe_response(
            MediaV2Service(db).get_regions_payload(
                virus_typ=virus_typ,
                target_source=target_source,
                brand=brand,
            )
        )
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/campaigns", dependencies=[Depends(get_current_user)])
async def get_media_campaigns(
    brand: str = "gelo",
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """V2 Campaign-Queue mit Deduplizierung, Lifecycle-State und Publish-Blockern."""
    return json_safe_response(MediaV2Service(db).get_campaigns_payload(brand=brand, limit=limit))


@router.get("/evidence", dependencies=[Depends(get_current_user)])
async def get_media_evidence(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
    db: Session = Depends(get_db),
):
    """V2 Evidenz-View mit Proxy, Truth, SignalStack und ModelLineage."""
    try:
        return json_safe_response(
            MediaV2Service(db).get_evidence_payload(
                virus_typ=virus_typ,
                target_source=target_source,
                brand=brand,
            )
        )
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/signal-stack", dependencies=[Depends(get_current_user)])
async def get_media_signal_stack(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Technischer V2-Endpunkt für den expliziten Signal-Stack."""
    return json_safe_response(MediaV2Service(db).get_signal_stack(virus_typ=virus_typ))


@router.get("/model-lineage", dependencies=[Depends(get_current_user)])
async def get_media_model_lineage(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Liefert Modellversion, Feature-Set und Drift-Status des aktuellen Forecast-Stacks."""
    return json_safe_response(MediaV2Service(db).get_model_lineage(virus_typ=virus_typ))


@router.post("/weekly-brief/generate", dependencies=[Depends(get_current_admin)])
async def generate_weekly_brief(
    virus_typ: str = Query(default="Influenza A"),
    db: Session = Depends(get_db),
):
    """Manueller Trigger: Generiert den Action Brief für die aktuelle KW."""
    from app.services.media.weekly_brief_service import WeeklyBriefService

    service = WeeklyBriefService(db)
    result = service.generate(virus_typ=virus_typ)
    return {
        "status": "success",
        "calendar_week": result["calendar_week"],
        "pages": result["pages"],
        "summary": result["summary"],
    }


@router.get("/weekly-brief/latest", dependencies=[Depends(get_current_user)])
async def get_latest_weekly_brief(
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Download des neuesten Action Brief als PDF."""
    from app.models.database import WeeklyBrief

    brief = (
        db.query(WeeklyBrief)
        .filter_by(brand=brand)
        .order_by(WeeklyBrief.generated_at.desc())
        .first()
    )
    if not brief or not brief.pdf_bytes:
        raise HTTPException(status_code=404, detail="Kein Weekly Brief vorhanden. Bitte zuerst generieren.")

    filename = f"Gelo_Action_Brief_{brief.calendar_week}.pdf"
    return StreamingResponse(
        io.BytesIO(brief.pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/weekly-brief/{calendar_week}", dependencies=[Depends(get_current_user)])
async def get_weekly_brief_by_week(
    calendar_week: str,
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Download eines spezifischen Action Brief nach Kalenderwoche."""
    from app.models.database import WeeklyBrief

    brief = (
        db.query(WeeklyBrief)
        .filter_by(calendar_week=calendar_week, brand=brand)
        .first()
    )
    if not brief or not brief.pdf_bytes:
        raise HTTPException(status_code=404, detail=f"Kein Brief für {calendar_week} vorhanden.")

    filename = f"Gelo_Action_Brief_{calendar_week}.pdf"
    return StreamingResponse(
        io.BytesIO(brief.pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
