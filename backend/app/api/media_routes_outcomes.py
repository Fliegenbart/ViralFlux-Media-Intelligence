"""Outcome and truth ingestion routes for the media API."""

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.brand_defaults import resolve_request_brand
from app.api.deps import get_current_admin, get_current_user
from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.api.m2m_auth import verify_m2m_api_key
from app.api.media_contracts import OutcomeImportRequest, OutcomeIngestRequest, json_safe_response
from app.db.schema_contracts import MLForecastSchemaMismatchError
from app.db.session import get_db
from app.services.media.v2_service import MediaV2Service

router = APIRouter()


@router.get("/outcomes/coverage", dependencies=[Depends(require_cockpit_auth)])
async def get_media_outcomes_coverage(
    brand: str | None = Query(default=None),
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Truth-Layer Coverage über importierte Outcome-Daten."""
    return json_safe_response(
        MediaV2Service(db).get_truth_coverage(
            brand=resolve_request_brand(brand),
            virus_typ=virus_typ,
        )
    )


@router.get("/pilot-reporting", dependencies=[Depends(get_current_user)])
async def get_media_pilot_reporting(
    brand: str | None = Query(default=None),
    lookback_weeks: int = Query(default=26, ge=1, le=104),
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    region_code: str | None = Query(default=None),
    product: str | None = Query(default=None),
    include_draft: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Legacy pilot reporting for internal/backoffice evidence review."""
    from app.services.media.pilot_reporting_service import PilotReportingService

    try:
        return json_safe_response(
            PilotReportingService(db).build_pilot_report(
                brand=resolve_request_brand(brand),
                lookback_weeks=lookback_weeks,
                window_start=window_start,
                window_end=window_end,
                region_code=region_code,
                product=product,
                include_draft=include_draft,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/pilot-readout", dependencies=[Depends(get_current_user)])
async def get_media_pilot_readout(
    brand: str | None = Query(default=None),
    virus_typ: str = "RSV A",
    horizon_days: int = Query(default=7, ge=3, le=14),
    weekly_budget_eur: float = Query(default=120000.0, ge=0),
    top_n: int = Query(default=12, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """Single-source customer readout for the customer pilot surface."""
    from app.services.media.pilot_readout_service import PilotReadoutService

    try:
        return json_safe_response(
            PilotReadoutService(db).build_readout(
                brand=resolve_request_brand(brand),
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                weekly_budget_eur=weekly_budget_eur,
                top_n=top_n,
            )
        )
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/evidence/truth", dependencies=[Depends(require_cockpit_auth)])
async def get_media_truth_evidence(
    brand: str | None = Query(default=None),
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Truth-Evidence Snapshot für Analysten-Ansicht, Coverage und Import-Historie."""
    return json_safe_response(
        MediaV2Service(db).get_truth_evidence(
            brand=resolve_request_brand(brand),
            virus_typ=virus_typ,
        )
    )


@router.get("/outcomes/import-batches", dependencies=[Depends(require_cockpit_auth)])
async def list_media_outcome_import_batches(
    brand: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Listet die letzten Truth-Import-Batches mit Status und Coverage-Snapshot."""
    brand_value = resolve_request_brand(brand)
    return json_safe_response({
        "brand": brand_value,
        "batches": MediaV2Service(db).list_outcome_import_batches(brand=brand_value, limit=limit),
    })


@router.get("/outcomes/import-batches/{batch_id}", dependencies=[Depends(require_cockpit_auth)])
async def get_media_outcome_import_batch_detail(
    batch_id: str,
    db: Session = Depends(get_db),
):
    """Liefert Detailansicht eines Truth-Import-Batches inklusive Issues."""
    detail = MediaV2Service(db).get_outcome_import_batch_detail(batch_id=batch_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Outcome-Import-Batch {batch_id} nicht gefunden")
    return json_safe_response(detail)


@router.get("/outcomes/template", dependencies=[Depends(require_cockpit_auth)])
async def download_media_outcome_template(
    db: Session = Depends(get_db),
):
    """CSV-Template für manuelle Truth-/Outcome-Uploads."""
    content = MediaV2Service(db).outcome_template_csv()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="viralflux_truth_template.csv"'},
    )


@router.post("/outcomes/import", dependencies=[Depends(get_current_admin)])
async def import_media_outcomes(
    payload: OutcomeImportRequest,
    db: Session = Depends(get_db),
):
    """Internal manual/backoffice truth import path. CSV remains a fallback only."""
    service = MediaV2Service(db)
    return json_safe_response(
        service.import_outcomes(
            source_label=payload.source_label,
            records=[item.model_dump(exclude_none=True) for item in payload.records],
            csv_payload=payload.csv_payload,
            brand=payload.brand,
            replace_existing=payload.replace_existing,
            validate_only=payload.validate_only,
            file_name=payload.file_name,
        )
    )


@router.post("/outcomes/ingest")
async def ingest_media_outcomes(
    payload: OutcomeIngestRequest,
    _: None = Depends(verify_m2m_api_key),
    db: Session = Depends(get_db),
):
    """Official GELO machine-to-machine outcome ingestion contract."""
    from app.services.media.outcome_ingestion_service import OutcomeIngestionService

    service = OutcomeIngestionService(db)
    return json_safe_response(
        service.ingest_outcomes(
            brand=payload.brand,
            source_system=payload.source_system,
            external_batch_id=payload.external_batch_id,
            observations=[item.model_dump(exclude_none=True) for item in payload.observations],
        )
    )
