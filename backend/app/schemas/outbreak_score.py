from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutbreakScoreBase(BaseModel):
    datum: datetime
    virus_typ: str = Field(..., min_length=1)
    decision_priority_index: float = Field(..., ge=0, le=100)
    signal_level: str | None = None
    signal_source: str | None = None
    reliability_label: str | None = None
    reliability_score: float | None = Field(default=None, ge=0, le=1)
    component_scores: dict[str, Any] | None = None
    data_source_mode: str | None = None
    phase: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class OutbreakScoreCreate(OutbreakScoreBase):
    pass


class OutbreakScoreUpdate(BaseModel):
    datum: datetime | None = None
    virus_typ: str | None = Field(default=None, min_length=1)
    decision_priority_index: float | None = Field(default=None, ge=0, le=100)
    signal_level: str | None = None
    signal_source: str | None = None
    reliability_label: str | None = None
    reliability_score: float | None = Field(default=None, ge=0, le=1)
    component_scores: dict[str, Any] | None = None
    data_source_mode: str | None = None
    phase: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class OutbreakScoreResponse(OutbreakScoreBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
