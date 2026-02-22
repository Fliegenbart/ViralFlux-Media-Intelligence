import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.token import Token

router = APIRouter()

_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@gelo.de")
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "gelo2026")

_USERS = {
    _ADMIN_EMAIL: {
        "password": get_password_hash(_ADMIN_PASSWORD),
        "role": "admin",
    }
}


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
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

