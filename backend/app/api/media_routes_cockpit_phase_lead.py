"""GET /api/v1/media/cockpit/phase-lead/snapshot."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db
from app.services.research.phase_lead.artifacts import load_cached_phase_lead_map_snapshot
from app.services.research.phase_lead.live_data import build_live_phase_lead_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"RSV A", "Influenza A", "Influenza B", "SARS-CoV-2"}


def _parse_region_codes(value: str | None) -> list[str] | None:
    if not value:
        return None
    codes = [item.strip() for item in value.split(",") if item.strip()]
    return codes or None


@router.get(
    "/cockpit/phase-lead/snapshot",
    dependencies=[Depends(require_cockpit_auth)],
)
async def get_cockpit_phase_lead_snapshot(
    virus_typ: str = Query("Influenza A", description="Virus scope for the experimental phase-lead run."),
    issue_date: date | None = Query(None, description="Optional point-in-time issue date."),
    window_days: int = Query(70, ge=14, le=140, description="Fitting window length."),
    regions: str | None = Query(None, description="Optional comma-separated Bundesland codes."),
    n_samples: int = Query(80, ge=4, le=600, description="Posterior predictive samples."),
    max_iter: int = Query(0, ge=0, le=250, description="Optimizer iterations. 0 uses the fast live mode."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )
    try:
        cached = load_cached_phase_lead_map_snapshot(
            virus_typ=virus_typ,
            issue_date=issue_date,
            window_days=int(window_days),
            region_codes=_parse_region_codes(regions),
            n_samples=int(n_samples),
        )
        if cached is not None:
            return cached
        return build_live_phase_lead_snapshot(
            db,
            virus_typ=virus_typ,
            issue_date=issue_date,
            window_days=int(window_days),
            region_codes=_parse_region_codes(regions),
            n_samples=int(n_samples),
            max_iter=int(max_iter),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - endpoint safety net
        logger.exception("cockpit/phase-lead/snapshot payload build failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Phase-Lead Snapshot konnte nicht erzeugt werden: {exc}",
        ) from exc
