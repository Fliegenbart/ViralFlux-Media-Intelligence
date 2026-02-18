from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMRecommendationBase(BaseModel):
    recommendation_text: str = Field(..., min_length=1)
    context_data: dict[str, Any] | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    suggested_action: dict[str, Any] | None = None
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    modified_action: dict[str, Any] | None = None
    forecast_id: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid", strict=True)


class LLMRecommendationCreate(LLMRecommendationBase):
    pass


class LLMRecommendationUpdate(BaseModel):
    recommendation_text: str | None = Field(default=None, min_length=1)
    context_data: dict[str, Any] | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    suggested_action: dict[str, Any] | None = None
    approved: bool | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    modified_action: dict[str, Any] | None = None
    forecast_id: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid", strict=True)


class LLMRecommendationResponse(LLMRecommendationBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

