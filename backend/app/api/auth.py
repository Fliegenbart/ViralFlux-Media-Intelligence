import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import AUTH_COOKIE_NAME, get_current_user
from app.core.rate_limit import limiter
from app.core.time import utc_now
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.models.database import AuditLog
from app.schemas.token import SessionState

logger = logging.getLogger(__name__)
router = APIRouter()

_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_WEAK_PASSWORDS = {
    "admin", "password", "123456", "test", "changeme",
    "letmein", "welcome", "monkey", "qwerty", "abc123",
}
_FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
_MAX_FAILED_LOGIN_ATTEMPTS = 5
_ACCESS_TOKEN_LIFETIME_MINUTES = 60
_COOKIE_SAMESITE = "lax"
_COOKIE_SECURE = _ENVIRONMENT.lower() in {"production", "staging"}
_AUTH_ENTITY_TYPE = "auth_session"
_LOGIN_SUCCESS_ACTION = "login_success"
_LOGIN_FAILED_ACTION = "login_failed"
_LOGOUT_ACTION = "logout"

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


def _normalized_username(username: str) -> str:
    return str(username or "").strip().lower()


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _record_auth_event(
    db: Session,
    *,
    user: str,
    ip_address: str,
    action: str,
    reason: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user=user,
            action=action,
            entity_type=_AUTH_ENTITY_TYPE,
            reason=reason,
            ip_address=ip_address,
        )
    )
    db.commit()


def _failed_attempt_count(db: Session, username: str, ip_address: str, now_dt) -> int:
    window_start = now_dt - timedelta(seconds=_FAILED_LOGIN_WINDOW_SECONDS)
    latest_success = (
        db.query(func.max(AuditLog.timestamp))
        .filter(
            AuditLog.entity_type == _AUTH_ENTITY_TYPE,
            AuditLog.action == _LOGIN_SUCCESS_ACTION,
            AuditLog.user == username,
            AuditLog.ip_address == ip_address,
        )
        .scalar()
    )
    effective_window_start = max(window_start, latest_success) if latest_success else window_start
    return int(
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.entity_type == _AUTH_ENTITY_TYPE,
            AuditLog.action == _LOGIN_FAILED_ACTION,
            AuditLog.user == username,
            AuditLog.ip_address == ip_address,
            AuditLog.timestamp >= effective_window_start,
        )
        .scalar()
        or 0
    )


def _is_locked_out(db: Session, username: str, ip_address: str, now_dt) -> bool:
    return _failed_attempt_count(db, username, ip_address, now_dt) >= _MAX_FAILED_LOGIN_ATTEMPTS


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


@router.post("/login", response_model=SessionState)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    remember_me: bool = True,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    now_dt = utc_now()
    username = _normalized_username(form_data.username)
    client_host = _client_host(request)

    if _is_locked_out(db, username, client_host, now_dt):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    user = _USERS.get(form_data.username)
    if not user or not verify_password(form_data.password, user["password"]):
        _record_auth_event(
            db,
            user=username,
            ip_address=client_host,
            action=_LOGIN_FAILED_ACTION,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": form_data.username, "role": user.get("role")},
        expires_delta=timedelta(minutes=_ACCESS_TOKEN_LIFETIME_MINUTES),
    )
    _set_auth_cookie(response, access_token, remember_me)
    _record_auth_event(
        db,
        user=username,
        ip_address=client_host,
        action=_LOGIN_SUCCESS_ACTION,
    )
    return SessionState(
        authenticated=True,
        subject=form_data.username,
        role=user.get("role"),
    )


@router.get("/session", response_model=SessionState)
async def get_session(current_user: dict = Depends(get_current_user)):
    return SessionState(
        authenticated=True,
        subject=current_user.get("sub"),
        role=current_user.get("role"),
    )


@router.post("/logout", response_model=SessionState)
async def logout(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_id = str(current_user.get("sid") or "").strip()
    if session_id:
        _record_auth_event(
            db,
            user=_normalized_username(current_user.get("sub") or ""),
            ip_address=_client_host(request),
            action=_LOGOUT_ACTION,
            reason=session_id,
        )
    _clear_auth_cookie(response)
    return SessionState(authenticated=False)
