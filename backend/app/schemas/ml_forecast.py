from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MLForecastBase(BaseModel):
    forecast_date: datetime
    virus_typ: str = Field(..., min_length=1)
    predicted_value: float = Field(..., ge=0)
    lower_bound: float | None = None
    upper_bound: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    model_version: str | None = None
    features_used: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class MLForecastCreate(MLForecastBase):
    pass


class MLForecastUpdate(BaseModel):
    forecast_date: datetime | None = None
    virus_typ: str | None = Field(default=None, min_length=1)
    predicted_value: float | None = Field(default=None, ge=0)
    lower_bound: float | None = None
    upper_bound: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    model_version: str | None = None
    features_used: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class MLForecastResponse(MLForecastBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

