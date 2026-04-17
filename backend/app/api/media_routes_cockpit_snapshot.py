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

import hmac
import logging
import os
import secrets
from typing import Any

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_optional_current_user
from app.core.security import SECRET_KEY
from app.db.session import get_db
from app.services.media.cockpit.snapshot_builder import build_cockpit_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"RSV A", "Influenza A", "Influenza B", "SARS-CoV-2"}
_SUPPORTED_HORIZONS = {7, 14, 21}
_SUPPORTED_LEAD_TARGETS = {"ATEMWEGSINDEX", "RKI_ARE", "SURVSTAT"}

# Cockpit-gate cookie: 30-day HMAC-signed token. Rotates when SECRET_KEY
# rotates. Not JWT because we don't need claims — just a "has the password
# been presented correctly" bit.
COCKPIT_UNLOCK_COOKIE = "cockpit_unlock"
COCKPIT_UNLOCK_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _gate_secret() -> str:
    """Derive the signing secret for the cockpit-unlock cookie from the
    server SECRET_KEY. Keeps the value out of .env and rotates with the
    main app secret."""
    return f"cockpit-gate-v1:{SECRET_KEY}"


def _issue_unlock_token() -> str:
    payload = secrets.token_urlsafe(18)
    signature = hmac.new(
        _gate_secret().encode("utf-8"),
        payload.encode("utf-8"),
        "sha256",
    ).hexdigest()
    return f"{payload}.{signature}"


def _verify_unlock_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    try:
        payload, signature = token.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(
        _gate_secret().encode("utf-8"),
        payload.encode("utf-8"),
        "sha256",
    ).hexdigest()
    try:
        return hmac.compare_digest(signature, expected)
    except TypeError:
        return False


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
    unlock_cookie: str | None = Cookie(default=None, alias=COCKPIT_UNLOCK_COOKIE),
) -> dict[str, Any]:
    """Accept a logged-in user (cookie/bearer), a valid M2M key,
    OR a valid cockpit_unlock cookie (set by POST /cockpit/unlock).

    The gate cookie exists so we can hand GELO a simple password-protected
    demo URL without the full OAuth-login flow."""
    if current_user:
        return {"principal": "user", "sub": current_user.get("sub")}
    if _verify_m2m_header(x_api_key):
        return {"principal": "m2m", "sub": None}
    if _verify_unlock_token(unlock_cookie):
        return {"principal": "gate", "sub": None}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (session cookie, bearer, X-API-Key, or cockpit-gate cookie).",
        headers={"WWW-Authenticate": "Bearer"},
    )


class CockpitUnlockRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


@router.post("/cockpit/unlock")
async def cockpit_unlock(payload: CockpitUnlockRequest, response: Response) -> dict[str, Any]:
    """Validate the simple shared password and set the gate cookie.

    Returns 200 + sets HttpOnly cookie on match. Returns 401 on mismatch.
    Password is only valid if COCKPIT_ACCESS_PASSWORD is actually configured
    (we refuse to silently accept requests when no password is set, to avoid
    accidentally exposing the cockpit)."""
    expected = os.getenv("COCKPIT_ACCESS_PASSWORD", "").strip()
    if not expected:
        logger.error("COCKPIT_ACCESS_PASSWORD is empty; refusing unlock request.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cockpit gate not configured.",
        )
    if not secrets.compare_digest(payload.password.strip(), expected):
        # Small random sleep to blunt timing attacks would be nice but
        # not strictly needed for a shared demo password.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falsches Passwort.",
        )
    token = _issue_unlock_token()
    response.set_cookie(
        key=COCKPIT_UNLOCK_COOKIE,
        value=token,
        max_age=COCKPIT_UNLOCK_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "ttl_days": COCKPIT_UNLOCK_COOKIE_MAX_AGE // 86400}


@router.post("/cockpit/lock")
async def cockpit_lock(response: Response) -> dict[str, Any]:
    """Clear the gate cookie — used by a future 'logout' button if needed."""
    response.delete_cookie(key=COCKPIT_UNLOCK_COOKIE, path="/")
    return {"ok": True}


@router.get("/cockpit/snapshot", dependencies=[Depends(require_cockpit_auth)])
async def get_cockpit_snapshot(
    virus_typ: str = Query(
        "Influenza A",
        description="Champion-scope virus (RSV A / Influenza A / Influenza B / SARS-CoV-2).",
    ),
    horizon_days: int = Query(
        14,
        description=(
            "Lead-time horizon for the headline story. Default 14 days — that's the horizon at "
            "which the backtest against Notaufnahme-Aktivität shows the strongest honest lead. "
            "Accepted: 7, 14, 21."
        ),
    ),
    lead_target_source: str = Query(
        "ATEMWEGSINDEX",
        alias="lead_target",
        description=(
            "Truth target the lead-time is measured against. Default ATEMWEGSINDEX "
            "(Notaufnahme-Syndromsurveillance). Alternatives: RKI_ARE (Meldewesen, slower), "
            "SURVSTAT."
        ),
    ),
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
    try:
        return build_cockpit_snapshot(
            db,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            client=client,
            brand=brand,
            lead_target_source=target_key,
        )
    except Exception:  # pragma: no cover - safety net, logged for ops
        logger.exception("build_cockpit_snapshot failed for virus=%s h=%s", virus_typ, horizon_days)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="cockpit_snapshot_build_failed",
        )
