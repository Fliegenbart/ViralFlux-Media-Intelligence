from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProductAttribute(BaseModel):
    target_segments: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    age_min_months: int | None = None
    age_max_months: int | None = None
    audience_mode: str = Field(default="b2c")
    channel_fit: list[str] = Field(default_factory=list)
    compliance_notes: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductBase(BaseModel):
    brand: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1)
    source_url: str | None = None
    source_hash: str | None = None
    active: bool = True
    extra_data: dict[str, Any] | None = None
    last_seen_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductCreatePayload(BaseModel):
    brand: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1)
    source_url: str | None = None
    source_hash: str | None = None
    active: bool = True
    sku: str | None = None
    target_segments: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    age_min_months: int | None = None
    age_max_months: int | None = None
    audience_mode: str = Field(default="b2c")
    channel_fit: list[str] = Field(default_factory=list)
    compliance_notes: str | None = None
    extra_data: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductCreateInput(BaseModel):
    brand: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1)
    source_url: str | None = None
    source_hash: str | None = None
    active: bool = True
    # Backward-compatible explicit field set for Product-Katalog input
    sku: str | None = None
    target_segments: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    age_min_months: int | None = None
    age_max_months: int | None = None
    audience_mode: str = Field(default="b2c")
    channel_fit: list[str] = Field(default_factory=list)
    compliance_notes: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductUpdate(BaseModel):
    brand: str | None = Field(default=None, min_length=1)
    product_name: str | None = Field(default=None, min_length=1)
    source_url: str | None = Field(default=None, min_length=1)
    source_hash: str | None = Field(default=None, min_length=1)
    active: bool | None = None
    extra_data: dict[str, Any] | None = None
    sku: str | None = None
    target_segments: list[str] | None = None
    conditions: list[str] | None = None
    forms: list[str] | None = None
    age_min_months: int | None = None
    age_max_months: int | None = None
    audience_mode: str | None = None
    channel_fit: list[str] | None = None
    compliance_notes: str | None = None
    last_seen_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductResponse(BrandProductBase):
    id: int = Field(..., ge=1)
    created_at: datetime
    updated_at: datetime

    sku: str | None = None
    target_segments: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    age_min_months: int | None = None
    age_max_months: int | None = None
    audience_mode: str | None = None
    channel_fit: list[str] = Field(default_factory=list)
    compliance_notes: str | None = None
    review_state: str | None = None
    last_change: str | None = None

    model_config = ConfigDict(from_attributes=True)
