from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InventoryLevelBase(BaseModel):
    datum: datetime
    test_typ: str = Field(..., min_length=1)
    aktueller_bestand: int = Field(..., ge=0)
    min_bestand: int | None = Field(default=None, ge=0)
    max_bestand: int | None = Field(default=None, ge=0)
    empfohlener_bestand: int | None = Field(default=None, ge=0)
    lieferzeit_tage: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class InventoryLevelCreate(InventoryLevelBase):
    pass


class InventoryLevelUpdate(BaseModel):
    datum: datetime | None = None
    test_typ: str | None = Field(default=None, min_length=1)
    aktueller_bestand: int | None = Field(default=None, ge=0)
    min_bestand: int | None = Field(default=None, ge=0)
    max_bestand: int | None = Field(default=None, ge=0)
    empfohlener_bestand: int | None = Field(default=None, ge=0)
    lieferzeit_tage: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class InventoryLevelResponse(InventoryLevelBase):
    id: int = Field(..., ge=1)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

