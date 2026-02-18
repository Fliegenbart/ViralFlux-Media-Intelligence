from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WastewaterAggregatedBase(BaseModel):
    datum: datetime
    available_time: datetime | None = None
    virus_typ: str = Field(..., min_length=1)
    n_standorte: int | None = Field(default=None, ge=0)
    anteil_bev: float | None = Field(default=None, ge=0)
    viruslast: float | None = None
    viruslast_normalisiert: float | None = None
    vorhersage: float | None = None
    obere_schranke: float | None = None
    untere_schranke: float | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class WastewaterAggregatedCreate(WastewaterAggregatedBase):
    pass


class WastewaterAggregatedUpdate(BaseModel):
    datum: datetime | None = None
    available_time: datetime | None = None
    virus_typ: str | None = Field(default=None, min_length=1)
    n_standorte: int | None = Field(default=None, ge=0)
    anteil_bev: float | None = Field(default=None, ge=0)
    viruslast: float | None = None
    viruslast_normalisiert: float | None = None
    vorhersage: float | None = None
    obere_schranke: float | None = None
    untere_schranke: float | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class WastewaterAggregatedResponse(WastewaterAggregatedBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

