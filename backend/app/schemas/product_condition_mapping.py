from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductConditionMappingBase(BaseModel):
    brand: str = Field(..., min_length=1)
    product_id: int = Field(..., ge=1)
    condition_key: str = Field(..., min_length=1)
    rule_source: str = Field(default="auto", min_length=1)  # auto | hard_rule
    fit_score: float = Field(default=0.0, ge=0)
    mapping_reason: str | None = None
    is_approved: bool = False
    priority: int = Field(default=0, ge=0)
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class ProductConditionMappingCreate(ProductConditionMappingBase):
    pass


class ProductConditionMappingUpdate(BaseModel):
    brand: str | None = Field(default=None, min_length=1)
    product_id: int | None = Field(default=None, ge=1)
    condition_key: str | None = Field(default=None, min_length=1)
    rule_source: str | None = Field(default=None, min_length=1)
    fit_score: float | None = Field(default=None, ge=0)
    mapping_reason: str | None = None
    is_approved: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class ProductConditionMappingResponse(ProductConditionMappingBase):
    id: int = Field(..., ge=1)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

