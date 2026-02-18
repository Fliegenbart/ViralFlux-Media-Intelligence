from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BacktestPointBase(BaseModel):
    run_id: str = Field(..., min_length=1)
    date: datetime
    region: str | None = None
    real_qty: float | None = None
    predicted_qty: float | None = None
    baseline_persistence: float | None = None
    baseline_seasonal: float | None = None
    bio: float | None = None
    psycho: float | None = None
    context: float | None = None
    extra: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BacktestPointCreate(BacktestPointBase):
    pass


class BacktestPointUpdate(BaseModel):
    run_id: str | None = Field(default=None, min_length=1)
    date: datetime | None = None
    region: str | None = None
    real_qty: float | None = None
    predicted_qty: float | None = None
    baseline_persistence: float | None = None
    baseline_seasonal: float | None = None
    bio: float | None = None
    psycho: float | None = None
    context: float | None = None
    extra: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BacktestPointResponse(BacktestPointBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

