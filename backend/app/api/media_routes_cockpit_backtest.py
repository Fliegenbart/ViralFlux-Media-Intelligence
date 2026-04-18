"""GET /api/v1/media/cockpit/backtest — Drawer V "Backtest" payload.

Pitch-story endpoint: serves an aggregated walk-forward backtest view
that proves the regional ranking was correct point-in-time. The
underlying artefact is produced by ``regional_trainer`` +
``regional_trainer_backtest``; this endpoint only shapes it for the UI.

Auth: same contract as the snapshot / impact endpoints — session
cookie, X-API-Key (M2M), or cockpit_unlock gate cookie.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.services.media.cockpit.backtest_builder import build_backtest_summary

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"Influenza A", "Influenza B", "RSV A", "SARS-CoV-2"}
_SUPPORTED_HORIZONS = {3, 5, 7, 14, 21}


@router.get("/cockpit/backtest", dependencies=[Depends(require_cockpit_auth)])
async def get_cockpit_backtest(
    virus_typ: str = Query("Influenza A"),
    horizon_days: int = Query(7),
    weeks_to_surface: int = Query(52, ge=1, le=400),
):
    """Pitch-story backtest summary for the cockpit's Drawer V."""
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )
    if horizon_days not in _SUPPORTED_HORIZONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"horizon_days must be one of {sorted(_SUPPORTED_HORIZONS)}",
        )

    try:
        payload = build_backtest_summary(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            weeks_to_surface=weeks_to_surface,
        )
    except Exception as exc:
        logger.exception("cockpit/backtest payload build failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest-Payload konnte nicht erzeugt werden: {exc}",
        ) from exc

    return payload
