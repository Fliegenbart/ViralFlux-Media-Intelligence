"""GET /api/v1/media/cockpit/impact — feedback-loop status for the cockpit.

This endpoint powers the "Wirkung" tab that closes the cockpit narrative:
  - live ranking (top-5 BL) from the current forecast,
  - recent BL-level truth activity from SURVSTAT,
  - outcome pipeline status (what has GELO/any client actually sent us).

Auth mirrors the snapshot endpoint: session cookie OR X-API-Key (M2M).
Read-only.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db
from app.services.media.cockpit.impact_builder import build_impact_payload
from app.services.media.cockpit.snapshot_builder import build_cockpit_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"RSV A", "Influenza A", "Influenza B", "SARS-CoV-2"}
_SUPPORTED_HORIZONS = {7, 14, 21}
_SUPPORTED_LEAD_TARGETS = {"ATEMWEGSINDEX", "RKI_ARE", "SURVSTAT"}


@router.get("/cockpit/impact", dependencies=[Depends(require_cockpit_auth)])
async def get_cockpit_impact(
    virus_typ: str = Query("Influenza A"),
    horizon_days: int = Query(14),
    lead_target_source: str = Query("ATEMWEGSINDEX", alias="lead_target"),
    client: str = Query("GELO"),
    brand: str | None = Query(default=None),
    weeks_back: int = Query(12, ge=1, le=52),
    include_snapshot: bool = Query(
        True,
        description="If True (default) we also pull the cockpit snapshot to seed the live ranking.",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported virus_typ={virus_typ!r}.",
        )
    if horizon_days not in _SUPPORTED_HORIZONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported horizon_days={horizon_days}; expected one of {sorted(_SUPPORTED_HORIZONS)}.",
        )
    target_key = (lead_target_source or "").strip().upper()
    if target_key not in _SUPPORTED_LEAD_TARGETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported lead_target={target_key!r}; expected one of {sorted(_SUPPORTED_LEAD_TARGETS)}.",
        )
    snapshot: dict[str, Any] | None = None
    if include_snapshot:
        try:
            snapshot = build_cockpit_snapshot(
                db,
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                client=client,
                brand=brand,
                lead_target_source=target_key,
            )
        except Exception:  # pragma: no cover
            logger.exception("snapshot build failed inside impact endpoint")
            snapshot = None
    try:
        return build_impact_payload(
            db,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            snapshot=snapshot,
            weeks_back=weeks_back,
        )
    except Exception:  # pragma: no cover
        logger.exception("build_impact_payload failed for virus=%s", virus_typ)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="cockpit_impact_build_failed",
        )
