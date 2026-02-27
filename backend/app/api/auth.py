import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.rate_limit import limiter

from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.token import Token

logger = logging.getLogger(__name__)
router = APIRouter()

_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_WEAK_PASSWORDS = {"gelo2026", "admin", "password", "123456", "test", "changeme"}

if not _ADMIN_EMAIL or not _ADMIN_PASSWORD:
    if _ENVIRONMENT == "production":
        raise RuntimeError(
            "FATAL: ADMIN_EMAIL and ADMIN_PASSWORD must be set via environment "
            "variables in production. Do NOT use hardcoded defaults."
        )
    _ADMIN_EMAIL = _ADMIN_EMAIL or "admin@gelo.de"
    _ADMIN_PASSWORD = _ADMIN_PASSWORD or "gelo2026"
    logger.warning("Using default admin credentials (dev only). Set ADMIN_EMAIL/ADMIN_PASSWORD in production.")

if _ENVIRONMENT == "production" and _ADMIN_PASSWORD.lower() in _WEAK_PASSWORDS:
    raise RuntimeError(
        "FATAL: ADMIN_PASSWORD is a known weak/default password. "
        "Set a strong password via environment variable in production."
    )

_USERS = {
    _ADMIN_EMAIL: {
        "password": get_password_hash(_ADMIN_PASSWORD),
        "role": "admin",
    }
}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    user = _USERS.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": form_data.username, "role": user.get("role")},
        expires_delta=timedelta(minutes=60),
    )
    return Token(access_token=access_token, token_type="bearer")

