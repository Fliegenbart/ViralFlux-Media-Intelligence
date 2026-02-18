from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotaufnahmeSyndromDataBase(BaseModel):
    datum: datetime
    ed_type: str = Field(..., min_length=1)  # all, central, pediatric
    age_group: str = Field(..., min_length=1)  # 00+, 0-4, ...
    syndrome: str = Field(..., min_length=1)  # ARI, SARI, ILI, COVID, GI
    relative_cases: float | None = None
    relative_cases_7day_ma: float | None = None
    expected_value: float | None = None
    expected_lowerbound: float | None = None
    expected_upperbound: float | None = None
    ed_count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class NotaufnahmeSyndromDataCreate(NotaufnahmeSyndromDataBase):
    pass


class NotaufnahmeSyndromDataUpdate(BaseModel):
    datum: datetime | None = None
    ed_type: str | None = Field(default=None, min_length=1)
    age_group: str | None = Field(default=None, min_length=1)
    syndrome: str | None = Field(default=None, min_length=1)
    relative_cases: float | None = None
    relative_cases_7day_ma: float | None = None
    expected_value: float | None = None
    expected_lowerbound: float | None = None
    expected_upperbound: float | None = None
    ed_count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class NotaufnahmeSyndromDataResponse(NotaufnahmeSyndromDataBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

