"""Standardized error response schemas for consistent API error handling."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response returned by all API endpoints."""

    error: str
    detail: str | None = None
    correlation_id: str | None = None


class ValidationErrorResponse(BaseModel):
    """Validation error with field-level details."""

    error: str = "validation_error"
    detail: str | None = None
    fields: list[dict] | None = None
