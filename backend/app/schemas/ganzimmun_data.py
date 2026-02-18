from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GanzimmunDataBase(BaseModel):
    datum: datetime
    available_time: datetime | None = None
    test_typ: str = Field(..., min_length=1)
    anzahl_tests: int | None = Field(default=None, ge=0)
    positive_ergebnisse: int | None = Field(default=None, ge=0)
    region: str | None = None
    extra_data: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class GanzimmunDataCreate(GanzimmunDataBase):
    pass


class GanzimmunDataUpdate(BaseModel):
    datum: datetime | None = None
    available_time: datetime | None = None
    test_typ: str | None = Field(default=None, min_length=1)
    anzahl_tests: int | None = Field(default=None, ge=0)
    positive_ergebnisse: int | None = Field(default=None, ge=0)
    region: str | None = None
    extra_data: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class GanzimmunDataResponse(GanzimmunDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

