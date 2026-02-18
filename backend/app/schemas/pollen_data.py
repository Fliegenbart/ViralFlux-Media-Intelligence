from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PollenDataBase(BaseModel):
    datum: datetime
    available_time: datetime | None = None
    region_code: str = Field(..., min_length=1)
    pollen_type: str = Field(..., min_length=1)
    pollen_index: float = Field(..., ge=0)
    source: str = Field(default="DWD", min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True)


class PollenDataCreate(PollenDataBase):
    pass


class PollenDataUpdate(BaseModel):
    datum: datetime | None = None
    available_time: datetime | None = None
    region_code: str | None = Field(default=None, min_length=1)
    pollen_type: str | None = Field(default=None, min_length=1)
    pollen_index: float | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True)


class PollenDataResponse(PollenDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

