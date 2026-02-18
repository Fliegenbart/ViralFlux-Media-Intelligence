from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LabConfigurationBase(BaseModel):
    is_global_default: bool = False
    weight_bio: float = Field(default=0.35, ge=0, le=1)
    weight_market: float = Field(default=0.35, ge=0, le=1)
    weight_psycho: float = Field(default=0.10, ge=0, le=1)
    weight_context: float = Field(default=0.20, ge=0, le=1)
    last_calibration_date: datetime | None = None
    calibration_source: str | None = None
    correlation_score: float | None = None
    analyzed_days: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class LabConfigurationCreate(LabConfigurationBase):
    pass


class LabConfigurationUpdate(BaseModel):
    is_global_default: bool | None = None
    weight_bio: float | None = Field(default=None, ge=0, le=1)
    weight_market: float | None = Field(default=None, ge=0, le=1)
    weight_psycho: float | None = Field(default=None, ge=0, le=1)
    weight_context: float | None = Field(default=None, ge=0, le=1)
    last_calibration_date: datetime | None = None
    calibration_source: str | None = None
    correlation_score: float | None = None
    analyzed_days: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class LabConfigurationResponse(LabConfigurationBase):
    id: int = Field(..., ge=1)

    model_config = ConfigDict(from_attributes=True)

