from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WeatherDataBase(BaseModel):
    datum: datetime
    available_time: datetime | None = None
    city: str = Field(..., min_length=1)
    temperatur: float | None = None
    gefuehlte_temperatur: float | None = None
    luftfeuchtigkeit: float | None = Field(default=None, ge=0, le=100)
    luftdruck: float | None = Field(default=None, ge=0)
    wetter_beschreibung: str | None = None
    wind_geschwindigkeit: float | None = Field(default=None, ge=0)
    uv_index: float | None = Field(default=None, ge=0)
    wolken: float | None = Field(default=None, ge=0, le=100)
    niederschlag_wahrscheinlichkeit: float | None = None
    regen_mm: float | None = Field(default=None, ge=0)
    schnee_mm: float | None = Field(default=None, ge=0)
    taupunkt: float | None = None
    data_type: str = Field(default="CURRENT", min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True)


class WeatherDataCreate(WeatherDataBase):
    pass


class WeatherDataUpdate(BaseModel):
    datum: datetime | None = None
    available_time: datetime | None = None
    city: str | None = Field(default=None, min_length=1)
    temperatur: float | None = None
    gefuehlte_temperatur: float | None = None
    luftfeuchtigkeit: float | None = Field(default=None, ge=0, le=100)
    luftdruck: float | None = Field(default=None, ge=0)
    wetter_beschreibung: str | None = None
    wind_geschwindigkeit: float | None = Field(default=None, ge=0)
    uv_index: float | None = Field(default=None, ge=0)
    wolken: float | None = Field(default=None, ge=0, le=100)
    niederschlag_wahrscheinlichkeit: float | None = None
    regen_mm: float | None = Field(default=None, ge=0)
    schnee_mm: float | None = Field(default=None, ge=0)
    taupunkt: float | None = None
    data_type: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True)


class WeatherDataResponse(WeatherDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

