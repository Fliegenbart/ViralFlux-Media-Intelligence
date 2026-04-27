"""GET /api/v1/media/cockpit/truth-scoreboard."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.services.media.cockpit.truth_scoreboard import (
    DEFAULT_HORIZONS,
    DEFAULT_VIRUSES,
    build_truth_scoreboard,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = set(DEFAULT_VIRUSES) | {"SARS-CoV-2"}
_SUPPORTED_HORIZONS = {3, 5, 7, 14, 21}


@router.get("/cockpit/truth-scoreboard", dependencies=[Depends(require_cockpit_auth)])
async def get_cockpit_truth_scoreboard(
    virus_typ: Annotated[list[str] | None, Query()] = None,
    horizon_days: Annotated[list[int] | None, Query()] = None,
    weeks_to_surface: int = Query(400, ge=1, le=600),
):
    viruses = virus_typ or list(DEFAULT_VIRUSES)
    horizons = horizon_days or list(DEFAULT_HORIZONS)
    invalid_viruses = sorted(set(viruses) - _SUPPORTED_VIRUSES)
    invalid_horizons = sorted(set(int(item) for item in horizons) - _SUPPORTED_HORIZONS)
    if invalid_viruses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )
    if invalid_horizons:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"horizon_days must be one of {sorted(_SUPPORTED_HORIZONS)}",
        )
    try:
        return build_truth_scoreboard(
            virus_types=viruses,
            horizons=[int(item) for item in horizons],
            weeks_to_surface=weeks_to_surface,
        )
    except Exception as exc:
        logger.exception("cockpit/truth-scoreboard payload build failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Truth-Scoreboard konnte nicht erzeugt werden: {exc}",
        ) from exc
