from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class SessionState(BaseModel):
    authenticated: bool
    subject: str | None = None
    role: str | None = None


class TokenPayload(BaseModel):
    sub: str | None = None
    role: str | None = None
