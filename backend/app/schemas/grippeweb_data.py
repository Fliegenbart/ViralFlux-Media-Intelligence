from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GrippeWebDataBase(BaseModel):
    datum: datetime
    kalenderwoche: int | None = Field(default=None, ge=1, le=53)
    erkrankung_typ: str = Field(..., min_length=1)  # ARE, ILI
    altersgruppe: str | None = None
    bundesland: str | None = None
    inzidenz: float | None = Field(default=None, ge=0)
    anzahl_meldungen: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class GrippeWebDataCreate(GrippeWebDataBase):
    pass


class GrippeWebDataUpdate(BaseModel):
    datum: datetime | None = None
    kalenderwoche: int | None = Field(default=None, ge=1, le=53)
    erkrankung_typ: str | None = Field(default=None, min_length=1)
    altersgruppe: str | None = None
    bundesland: str | None = None
    inzidenz: float | None = Field(default=None, ge=0)
    anzahl_meldungen: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class GrippeWebDataResponse(GrippeWebDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

