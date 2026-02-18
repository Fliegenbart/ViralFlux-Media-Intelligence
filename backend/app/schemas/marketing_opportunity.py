from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MarketingOpportunityBase(BaseModel):
    opportunity_id: str = Field(..., min_length=1)
    opportunity_type: str = Field(..., min_length=1)
    status: str = Field(default="NEW", min_length=1)
    urgency_score: float = Field(..., ge=0)

    region_target: dict[str, Any] | None = None
    trigger_source: str | None = None
    trigger_event: str | None = None
    trigger_details: dict[str, Any] | None = None
    trigger_detected_at: datetime | None = None

    target_audience: dict[str, Any] | None = None
    sales_pitch: dict[str, Any] | None = None
    suggested_products: dict[str, Any] | None = None

    brand: str | None = None
    product: str | None = None
    budget_shift_pct: float | None = None
    channel_mix: dict[str, Any] | None = None
    activation_start: datetime | None = None
    activation_end: datetime | None = None
    recommendation_reason: str | None = None
    campaign_payload: dict[str, Any] | None = None
    playbook_key: str | None = None
    strategy_mode: str = Field(default="PLAYBOOK_AI", min_length=1)
    expires_at: datetime | None = None
    exported_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class MarketingOpportunityCreate(MarketingOpportunityBase):
    pass


class MarketingOpportunityUpdate(BaseModel):
    opportunity_id: str | None = Field(default=None, min_length=1)
    opportunity_type: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, min_length=1)
    urgency_score: float | None = Field(default=None, ge=0)

    region_target: dict[str, Any] | None = None
    trigger_source: str | None = None
    trigger_event: str | None = None
    trigger_details: dict[str, Any] | None = None
    trigger_detected_at: datetime | None = None

    target_audience: dict[str, Any] | None = None
    sales_pitch: dict[str, Any] | None = None
    suggested_products: dict[str, Any] | None = None

    brand: str | None = None
    product: str | None = None
    budget_shift_pct: float | None = None
    channel_mix: dict[str, Any] | None = None
    activation_start: datetime | None = None
    activation_end: datetime | None = None
    recommendation_reason: str | None = None
    campaign_payload: dict[str, Any] | None = None
    playbook_key: str | None = None
    strategy_mode: str | None = Field(default=None, min_length=1)
    expires_at: datetime | None = None
    exported_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class MarketingOpportunityResponse(MarketingOpportunityBase):
    id: int = Field(..., ge=1)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

