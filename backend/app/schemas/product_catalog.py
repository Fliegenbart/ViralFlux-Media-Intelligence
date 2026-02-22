from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConquestingTargets(BaseModel):
    """Defines which competitor drugs a product can conquest against.

    Used by CompetitorShortageDetector to match BfArM shortage data
    against our product portfolio. When a competitor drug in a shortage
    matches these targets, a conquesting opportunity is generated.
    """

    target_ingredients: list[str] = Field(
        default_factory=list,
        description="Competitor Wirkstoffe (lowercase). Matched against BfArM 'Wirkstoffe' column.",
    )
    target_forms: list[str] = Field(
        default_factory=list,
        description="Competitor Darreichungsformen (lowercase substrings). Matched against BfArM 'Darreichungsform'.",
    )
    bid_multiplier: float = Field(
        default=1.5,
        ge=1.0,
        le=5.0,
        description="Programmatic bid multiplier when conquesting opportunity is active.",
    )

    model_config = ConfigDict(extra="forbid")


class ProductCatalogBase(BaseModel):
    sku: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str | None = None
    applicable_types: dict[str, Any] | list[Any] | None = None
    applicable_conditions: dict[str, Any] | list[Any] | None = None
    conquesting: ConquestingTargets | None = None
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
    conquesting: ConquestingTargets | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class ProductCatalogResponse(ProductCatalogBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

