"""Shared request models and helpers for media API routes."""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RecommendationGenerateRequest(BaseModel):
    brand: str = Field(..., min_length=1)
    product: str = Field(default="Alle Produkte")
    campaign_goal: str = Field(default="Awareness + Abverkauf")
    weekly_budget: float = Field(default=100000.0, ge=0)
    channel_pool: list[str] = Field(default_factory=lambda: ["programmatic", "social", "search", "ctv"])
    region_scope: list[str] | None = None
    strategy_mode: str = Field(default="PLAYBOOK_AI")
    max_cards: int = Field(default=8, ge=1, le=20)
    virus_typ: str = Field(default="Influenza A")


class RecommendationOpenRegionRequest(BaseModel):
    region_code: str = Field(..., min_length=2)
    brand: str = Field(..., min_length=1)
    product: str = Field(default="Alle Produkte")
    campaign_goal: str = Field(default="Sichtbarkeit aufbauen, bevor die Nachfrage steigt")
    weekly_budget: float = Field(default=100000.0, ge=0)
    virus_typ: str = Field(default="Influenza A")


class ChannelPlanItem(BaseModel):
    channel: str
    share_pct: float
    role: str | None = None
    formats: list[str] | None = None
    message_angle: str | None = None
    kpi_primary: str | None = None
    kpi_secondary: list[str] | None = None


class CampaignUpdateRequest(BaseModel):
    activation_window: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    channel_plan: list[ChannelPlanItem] | None = None
    kpi_targets: dict[str, Any] | None = None


class RecommendationStatusUpdateRequest(BaseModel):
    status: str


class PrepareSyncRequest(BaseModel):
    connector_key: str | None = Field(default=None)


class RecommendationBackfillPeixRequest(BaseModel):
    force: bool = Field(default=False)
    limit: int = Field(default=1000, ge=1, le=10000)


class ProductMappingUpdateRequest(BaseModel):
    is_approved: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=999)
    notes: str | None = None


class ProductConditionLinkRequest(BaseModel):
    condition_key: str = Field(..., min_length=1)
    is_approved: bool = False
    fit_score: float = Field(default=0.8, ge=0.0, le=1.0)
    priority: int = Field(default=600, ge=0, le=999)
    mapping_reason: str | None = None
    notes: str | None = None


class OutcomeImportRecord(BaseModel):
    week_start: str
    product: str
    region_code: str
    media_spend_eur: float | None = None
    impressions: float | None = None
    clicks: float | None = None
    qualified_visits: float | None = None
    search_lift_index: float | None = None
    sales_units: float | None = None
    order_count: float | None = None
    revenue_eur: float | None = None
    extra_data: dict[str, Any] | None = None


class OutcomeImportRequest(BaseModel):
    brand: str = Field(..., min_length=1)
    source_label: str = Field(default="manual")
    replace_existing: bool = Field(default=False)
    validate_only: bool = Field(default=False)
    file_name: str | None = None
    records: list[OutcomeImportRecord] = Field(default_factory=list)
    csv_payload: str | None = None


class OutcomeIngestObservation(BaseModel):
    product: str = Field(..., min_length=1)
    region_code: str = Field(..., min_length=1)
    window_start: datetime
    window_end: datetime
    metric_name: str = Field(..., min_length=1)
    metric_value: float
    metric_unit: str | None = None
    channel: str | None = None
    campaign_id: str | None = None
    holdout_group: str | None = None
    confidence_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutcomeIngestRequest(BaseModel):
    brand: str = Field(..., min_length=1)
    source_system: str = Field(..., min_length=1)
    external_batch_id: str = Field(..., min_length=1)
    observations: list[OutcomeIngestObservation] = Field(default_factory=list)


def json_safe_response(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe_response(item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): json_safe_response(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe_response(v) for v in value]
    return str(value)
