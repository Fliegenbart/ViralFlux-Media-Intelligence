from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.security import ALGORITHM, SECRET_KEY
from app.schemas.token import TokenPayload

AUTH_COOKIE_NAME = "viralflux_session"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(request: Request, token: str | None = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    auth_token = token or request.cookies.get(AUTH_COOKIE_NAME)
    if not auth_token:
        raise credentials_exception

    try:
        payload = jwt.decode(
            auth_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require_exp": True},
        )
        token_payload = TokenPayload.model_validate(payload)
        if not token_payload.sub:
            raise credentials_exception
        return token_payload.model_dump()
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_exception


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges",
        )
    return current_user
