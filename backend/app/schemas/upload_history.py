from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UploadHistoryBase(BaseModel):
    filename: str = Field(..., min_length=1)
    upload_type: str = Field(..., min_length=1)  # lab_results | orders
    file_format: str | None = None  # csv | xlsx
    row_count: int | None = Field(default=None, ge=0)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    status: str = Field(default="success", min_length=1)  # success, error, partial
    error_message: str | None = None
    summary: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class UploadHistoryCreate(UploadHistoryBase):
    pass


class UploadHistoryUpdate(BaseModel):
    filename: str | None = Field(default=None, min_length=1)
    upload_type: str | None = Field(default=None, min_length=1)
    file_format: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    status: str | None = Field(default=None, min_length=1)
    error_message: str | None = None
    summary: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class UploadHistoryResponse(UploadHistoryBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

