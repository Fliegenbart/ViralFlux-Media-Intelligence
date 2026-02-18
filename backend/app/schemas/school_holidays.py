from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SchoolHolidaysBase(BaseModel):
    bundesland: str = Field(..., min_length=1)
    ferien_typ: str = Field(..., min_length=1)
    start_datum: datetime
    end_datum: datetime
    jahr: int = Field(..., ge=2000)

    model_config = ConfigDict(extra="forbid", strict=True)


class SchoolHolidaysCreate(SchoolHolidaysBase):
    pass


class SchoolHolidaysUpdate(BaseModel):
    bundesland: str | None = Field(default=None, min_length=1)
    ferien_typ: str | None = Field(default=None, min_length=1)
    start_datum: datetime | None = None
    end_datum: datetime | None = None
    jahr: int | None = Field(default=None, ge=2000)

    model_config = ConfigDict(extra="forbid", strict=True)


class SchoolHolidaysResponse(SchoolHolidaysBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

