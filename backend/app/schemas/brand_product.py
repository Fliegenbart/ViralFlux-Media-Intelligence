from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrandProductBase(BaseModel):
    brand: str = Field(..., min_length=1)
    product_name: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1)
    source_hash: str = Field(..., min_length=1)
    active: bool = True
    extra_data: dict[str, Any] | None = None
    last_seen_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductCreate(BrandProductBase):
    pass


class BrandProductUpdate(BaseModel):
    brand: str | None = Field(default=None, min_length=1)
    product_name: str | None = Field(default=None, min_length=1)
    source_url: str | None = Field(default=None, min_length=1)
    source_hash: str | None = Field(default=None, min_length=1)
    active: bool | None = None
    extra_data: dict[str, Any] | None = None
    last_seen_at: datetime | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandProductResponse(BrandProductBase):
    id: int = Field(..., ge=1)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

