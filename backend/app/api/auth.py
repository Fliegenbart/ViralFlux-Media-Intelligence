import logging
import os
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AUTH_COOKIE_NAME, get_current_user
from app.core.rate_limit import limiter

from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.token import SessionState, Token

logger = logging.getLogger(__name__)
router = APIRouter()

_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_WEAK_PASSWORDS = {
    "admin", "password", "123456", "test", "changeme",
    "letmein", "welcome", "monkey", "qwerty", "abc123",
}
_FAILED_LOGINS: dict[str, list[float]] = {}
_LOCKED_UNTIL: dict[str, float] = {}
_FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
_LOCKOUT_SECONDS = 15 * 60
_MAX_FAILED_LOGIN_ATTEMPTS = 5
_ACCESS_TOKEN_LIFETIME_MINUTES = 60
_COOKIE_SAMESITE = "lax"
_COOKIE_SECURE = _ENVIRONMENT.lower() in {"production", "staging"}

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


def _login_throttle_key(username: str, request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{str(username or '').strip().lower()}:{client_host}"


def _prune_failed_attempts(key: str, now_ts: float) -> list[float]:
    attempts = [
        attempt_ts
        for attempt_ts in _FAILED_LOGINS.get(key, [])
        if now_ts - attempt_ts <= _FAILED_LOGIN_WINDOW_SECONDS
    ]
    _FAILED_LOGINS[key] = attempts
    return attempts


def _is_locked_out(key: str, now_ts: float) -> bool:
    locked_until = _LOCKED_UNTIL.get(key)
    if not locked_until:
        return False
    if now_ts >= locked_until:
        _LOCKED_UNTIL.pop(key, None)
        _FAILED_LOGINS.pop(key, None)
        return False
    return True


def _register_failed_login(key: str, now_ts: float) -> None:
    attempts = _prune_failed_attempts(key, now_ts)
    attempts.append(now_ts)
    _FAILED_LOGINS[key] = attempts
    if len(attempts) >= _MAX_FAILED_LOGIN_ATTEMPTS:
        _LOCKED_UNTIL[key] = now_ts + _LOCKOUT_SECONDS


def _clear_failed_logins(key: str) -> None:
    _FAILED_LOGINS.pop(key, None)
    _LOCKED_UNTIL.pop(key, None)


def _set_auth_cookie(response: Response, token: str, remember_me: bool) -> None:
    max_age = _ACCESS_TOKEN_LIFETIME_MINUTES * 60 if remember_me else None
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=max_age,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        path="/",
    )


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    remember_me: bool = True,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    now_ts = time.time()
    throttle_key = _login_throttle_key(form_data.username, request)

    if _is_locked_out(throttle_key, now_ts):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    user = _USERS.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        _register_failed_login(throttle_key, now_ts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _clear_failed_logins(throttle_key)
    access_token = create_access_token(
        data={"sub": form_data.username, "role": user.get("role")},
        expires_delta=timedelta(minutes=_ACCESS_TOKEN_LIFETIME_MINUTES),
    )
    _set_auth_cookie(response, access_token, remember_me)
    return Token(access_token=access_token, token_type="bearer")


@router.get("/session", response_model=SessionState)
async def get_session(current_user: dict = Depends(get_current_user)):
    return SessionState(
        authenticated=True,
        subject=current_user.get("sub"),
        role=current_user.get("role"),
    )


@router.post("/logout", response_model=SessionState)
async def logout(response: Response):
    _clear_auth_cookie(response)
    return SessionState(authenticated=False)
