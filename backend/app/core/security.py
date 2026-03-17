import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import bcrypt
from jose import jwt

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

_KNOWN_PLACEHOLDERS = {
    "CHANGE_ME_IN_PROD_GELO_2026",
    "dev-secret-key-change-me",
    "viralflux-prod-secret-key-change-me-2026",
    "generate-a-secure-random-key-here-minimum-32-characters",
}

SECRET_KEY = os.getenv("SECRET_KEY", "")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if not SECRET_KEY or SECRET_KEY in _KNOWN_PLACEHOLDERS:
    if _ENVIRONMENT == "production":
        raise RuntimeError(
            "FATAL: SECRET_KEY is missing or uses a known placeholder in production! "
            "Set a secure random SECRET_KEY (≥32 chars) via environment variable."
        )
    # Dev/test: generate ephemeral key
    import secrets
    SECRET_KEY = secrets.token_urlsafe(48)
    logger.warning(
        "SECRET_KEY not set — using ephemeral key (tokens will NOT survive restarts). "
        "Set SECRET_KEY env var for persistent sessions."
    )


def _normalize_password_for_bcrypt(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password
    return hashlib.sha256(password_bytes).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    normalized_password = _normalize_password_for_bcrypt(plain_password).encode("utf-8")
    stored_hash = hashed_password.encode("utf-8")
    return bcrypt.checkpw(normalized_password, stored_hash)


def get_password_hash(password: str) -> str:
    normalized_password = _normalize_password_for_bcrypt(password).encode("utf-8")
    return bcrypt.hashpw(normalized_password, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: Dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = dict(data)
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
