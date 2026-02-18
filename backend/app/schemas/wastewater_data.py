from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WastewaterDataBase(BaseModel):
    standort: str = Field(..., min_length=1)
    bundesland: str = Field(..., min_length=1)
    datum: datetime
    available_time: datetime | None = None
    virus_typ: str = Field(..., min_length=1)
    viruslast: float | None = None
    viruslast_normalisiert: float | None = None
    vorhersage: float | None = None
    obere_schranke: float | None = None
    untere_schranke: float | None = None
    einwohner: int | None = Field(default=None, ge=0)
    unter_bg: bool | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class WastewaterDataCreate(WastewaterDataBase):
    pass


class WastewaterDataUpdate(BaseModel):
    standort: str | None = Field(default=None, min_length=1)
    bundesland: str | None = Field(default=None, min_length=1)
    datum: datetime | None = None
    available_time: datetime | None = None
    virus_typ: str | None = Field(default=None, min_length=1)
    viruslast: float | None = None
    viruslast_normalisiert: float | None = None
    vorhersage: float | None = None
    obere_schranke: float | None = None
    untere_schranke: float | None = None
    einwohner: int | None = Field(default=None, ge=0)
    unter_bg: bool | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class WastewaterDataResponse(WastewaterDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

