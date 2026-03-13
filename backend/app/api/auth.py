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

_WEAK_PASSWORDS = {
    "admin", "password", "123456", "test", "changeme",
    "letmein", "welcome", "monkey", "qwerty", "abc123",
}

if not _ADMIN_EMAIL or not _ADMIN_PASSWORD:
    raise RuntimeError(
        "FATAL: ADMIN_EMAIL and ADMIN_PASSWORD must be set via environment "
        "variables. Generate a strong password with: openssl rand -base64 24"
    )

if len(_ADMIN_PASSWORD) < 12:
    raise RuntimeError(
        "FATAL: ADMIN_PASSWORD must be at least 12 characters long."
    )

if _ADMIN_PASSWORD.lower() in _WEAK_PASSWORDS:
    raise RuntimeError(
        "FATAL: ADMIN_PASSWORD is a known weak/default password. "
        "Set a strong password via environment variable."
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

