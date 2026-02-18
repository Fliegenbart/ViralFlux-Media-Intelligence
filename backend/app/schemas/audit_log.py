from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogBase(BaseModel):
    timestamp: datetime | None = None
    user: str | None = None
    action: str = Field(..., min_length=1)  # view, approve, modify, reject
    entity_type: str | None = None
    entity_id: int | None = Field(default=None, ge=0)
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    reason: str | None = None
    ip_address: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogUpdate(BaseModel):
    timestamp: datetime | None = None
    user: str | None = None
    action: str | None = Field(default=None, min_length=1)
    entity_type: str | None = None
    entity_id: int | None = Field(default=None, ge=0)
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    reason: str | None = None
    ip_address: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class AuditLogResponse(AuditLogBase):
    id: int = Field(..., ge=1)

    model_config = ConfigDict(from_attributes=True)

