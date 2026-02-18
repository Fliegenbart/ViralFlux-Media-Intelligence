from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoogleTrendsDataBase(BaseModel):
    datum: datetime
    available_time: datetime | None = None
    keyword: str = Field(..., min_length=1)
    region: str = Field(default="DE", min_length=1)
    interest_score: int | None = Field(default=None, ge=0, le=100)
    is_partial: bool = False

    model_config = ConfigDict(extra="forbid", strict=True)


class GoogleTrendsDataCreate(GoogleTrendsDataBase):
    pass


class GoogleTrendsDataUpdate(BaseModel):
    datum: datetime | None = None
    available_time: datetime | None = None
    keyword: str | None = Field(default=None, min_length=1)
    region: str | None = Field(default=None, min_length=1)
    interest_score: int | None = Field(default=None, ge=0, le=100)
    is_partial: bool | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class GoogleTrendsDataResponse(GoogleTrendsDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

