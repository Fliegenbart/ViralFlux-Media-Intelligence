"""GET /api/v1/media/cockpit/snapshot — honest peix cockpit payload.

This endpoint exists because the peix cockpit frontend was previously wired
to a curated fixture (``frontend/src/pages/cockpit/snapshot.ts``). After the
2026-04-16 math audit (~/peix-math-audit.md) we replace the fixture with a
payload whose every field is either pulled from a real model output or
explicitly null.

Auth:
    The endpoint accepts EITHER a logged-in user (cookie/bearer, same as
    ``/api/v1/forecast/regional/*``) OR a machine-to-machine ``X-API-Key``
    header. The M2M path exists so the audit smoke tests can run without
    requiring a personal admin login (see PR description).

This module does not mutate state. All DB access is read-only.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_optional_current_user
from app.db.session import get_db
from app.services.media.cockpit.snapshot_builder import build_cockpit_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"RSV A", "Influenza A", "Influenza B", "SARS-CoV-2"}


def _verify_m2m_header(x_api_key: str | None) -> bool:
    expected = os.getenv("M2M_SECRET_KEY", "")
    if not expected or not x_api_key:
        return False
    try:
        return secrets.compare_digest(x_api_key, expected)
    except TypeError:
        return False


async def require_cockpit_auth(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    current_user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Accept either a session user or a valid M2M key."""
    if current_user:
        return {"principal": "user", "sub": current_user.get("sub")}
    if _verify_m2m_header(x_api_key):
        return {"principal": "m2m", "sub": None}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (session cookie, bearer, or X-API-Key).",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/cockpit/snapshot", dependencies=[Depends(require_cockpit_auth)])
async def get_cockpit_snapshot(
    virus_typ: str = Query("Influenza A", description="Champion-scope virus (RSV A / Influenza A / Influenza B / SARS-CoV-2)."),
    horizon_days: int = Query(7, description="Forecast horizon in days. Currently only 7 is a champion scope."),
    client: str = Query("GELO", description="Client label shown in the UI."),
    brand: str | None = Query(default=None, description="Brand identifier passed through to the regional forecast service."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported virus_typ={virus_typ!r}. "
                f"Expected one of: {sorted(_SUPPORTED_VIRUSES)}."
            ),
        )
    if horizon_days != 7:
        # Champion-scope contract: only h=7 is promoted to production.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only horizon_days=7 is an active champion scope.",
        )
    try:
        return build_cockpit_snapshot(
            db,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            client=client,
            brand=brand,
        )
    except Exception:  # pragma: no cover - safety net, logged for ops
        logger.exception("build_cockpit_snapshot failed for virus=%s h=%s", virus_typ, horizon_days)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="cockpit_snapshot_build_failed",
        )
