from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AREKonsultationBase(BaseModel):
    datum: datetime
    available_time: datetime | None = None
    kalenderwoche: int = Field(..., ge=1, le=53)
    saison: str = Field(..., min_length=1)
    altersgruppe: str = Field(..., min_length=1)
    bundesland: str = Field(..., min_length=1)
    bundesland_id: int | None = Field(default=None, ge=0)
    konsultationsinzidenz: int = Field(..., ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class AREKonsultationCreate(AREKonsultationBase):
    pass


class AREKonsultationUpdate(BaseModel):
    datum: datetime | None = None
    available_time: datetime | None = None
    kalenderwoche: int | None = Field(default=None, ge=1, le=53)
    saison: str | None = Field(default=None, min_length=1)
    altersgruppe: str | None = Field(default=None, min_length=1)
    bundesland: str | None = Field(default=None, min_length=1)
    bundesland_id: int | None = Field(default=None, ge=0)
    konsultationsinzidenz: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class AREKonsultationResponse(AREKonsultationBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

