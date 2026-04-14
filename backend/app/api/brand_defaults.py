"""Helpers for API-level brand defaults."""

from __future__ import annotations

from app.core.config import get_settings


def resolve_request_brand(brand: str | None) -> str:
    normalized = str(brand or "").strip()
    if normalized:
        return normalized
    return get_settings().NORMALIZED_OPERATIONAL_DEFAULT_BRAND
