from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SurvstatWeeklyDataBase(BaseModel):
    week_label: str = Field(..., min_length=1)  # YYYY_WW
    week_start: datetime
    available_time: datetime | None = None
    year: int = Field(..., ge=1900)
    week: int = Field(..., ge=1, le=53)
    bundesland: str = Field(..., min_length=1)
    disease: str = Field(..., min_length=1)
    incidence: float | None = Field(default=None, ge=0)
    source_file: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class SurvstatWeeklyDataCreate(SurvstatWeeklyDataBase):
    pass


class SurvstatWeeklyDataUpdate(BaseModel):
    week_label: str | None = Field(default=None, min_length=1)
    week_start: datetime | None = None
    available_time: datetime | None = None
    year: int | None = Field(default=None, ge=1900)
    week: int | None = Field(default=None, ge=1, le=53)
    bundesland: str | None = Field(default=None, min_length=1)
    disease: str | None = Field(default=None, min_length=1)
    incidence: float | None = Field(default=None, ge=0)
    source_file: str | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class SurvstatWeeklyDataResponse(SurvstatWeeklyDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

