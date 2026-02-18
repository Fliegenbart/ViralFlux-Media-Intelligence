from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotaufnahmeStandortBase(BaseModel):
    ik_number: str = Field(..., min_length=1)
    ed_name: str | None = None
    ed_type: str | None = None
    level_of_care: str | None = None
    state: str | None = None
    state_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class NotaufnahmeStandortCreate(NotaufnahmeStandortBase):
    pass


class NotaufnahmeStandortUpdate(BaseModel):
    ik_number: str | None = Field(default=None, min_length=1)
    ed_name: str | None = None
    ed_type: str | None = None
    level_of_care: str | None = None
    state: str | None = None
    state_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class NotaufnahmeStandortResponse(NotaufnahmeStandortBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

