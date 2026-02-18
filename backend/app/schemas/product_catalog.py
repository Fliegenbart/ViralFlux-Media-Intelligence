from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProductCatalogBase(BaseModel):
    sku: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str | None = None
    applicable_types: dict[str, Any] | list[Any] | None = None
    applicable_conditions: dict[str, Any] | list[Any] | None = None
    is_active: bool = True

    model_config = ConfigDict(extra="forbid", strict=True)


class ProductCatalogCreate(ProductCatalogBase):
    pass


class ProductCatalogUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    category: str | None = None
    applicable_types: dict[str, Any] | list[Any] | None = None
    applicable_conditions: dict[str, Any] | list[Any] | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class ProductCatalogResponse(ProductCatalogBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

