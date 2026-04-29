"""GET /api/v1/media/cockpit/media-spending-truth."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db
from app.services.media.cockpit.media_spending_truth import build_media_spending_truth_from_forecast

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"RSV A", "Influenza A", "Influenza B", "SARS-CoV-2"}
_SUPPORTED_HORIZONS = {5, 7, 10, 14, 21}


@router.get("/cockpit/media-spending-truth", dependencies=[Depends(require_cockpit_auth)])
async def get_cockpit_media_spending_truth(
    virus_typ: str = Query("Influenza A", description="Virus scope for the spending decision layer."),
    horizon_days: int = Query(7, description="Decision horizon in days."),
    client: str = Query("GELO", description="Client label used for optional media-plan lookup."),
    brand: str | None = Query(default=None, description="Brand identifier passed through to regional forecasts."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )
    if int(horizon_days) not in _SUPPORTED_HORIZONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"horizon_days must be one of {sorted(_SUPPORTED_HORIZONS)}",
        )
    try:
        return build_media_spending_truth_from_forecast(
            db,
            virus_typ=virus_typ,
            horizon_days=int(horizon_days),
            client=client,
            brand=brand,
        )
    except Exception as exc:  # pragma: no cover - endpoint safety net
        logger.exception("cockpit/media-spending-truth payload build failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MediaSpendingTruth konnte nicht erzeugt werden: {exc}",
        ) from exc
