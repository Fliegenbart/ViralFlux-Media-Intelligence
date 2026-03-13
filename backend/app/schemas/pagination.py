"""Pagination helpers for list endpoints."""

from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PaginationParams:
    """Dependency-injectable pagination parameters."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Seitennummer"),
        page_size: int = Query(default=50, ge=1, le=500, description="Einträge pro Seite"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse(BaseModel):
    """Standard paginated response wrapper."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[Any],
        total: int,
        params: PaginationParams,
    ) -> "PaginatedResponse":
        total_pages = max(1, (total + params.page_size - 1) // params.page_size)
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
        )
