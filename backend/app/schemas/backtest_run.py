from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BacktestRunBase(BaseModel):
    run_id: str = Field(..., min_length=1)
    mode: str = Field(..., min_length=1)  # MARKET_CHECK, CUSTOMER_CHECK
    status: str = Field(default="success", min_length=1)
    virus_typ: str = Field(..., min_length=1)
    target_source: str = Field(..., min_length=1)
    target_key: str | None = None
    target_label: str | None = None
    strict_vintage_mode: bool = True
    horizon_days: int = Field(default=14, ge=0)
    min_train_points: int = Field(default=20, ge=0)
    parameters: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    baseline_metrics: dict[str, Any] | None = None
    improvement_vs_baselines: dict[str, Any] | None = None
    optimized_weights: dict[str, Any] | None = None
    proof_text: str | None = None
    llm_insight: str | None = None
    lead_lag: dict[str, Any] | None = None
    chart_points: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class BacktestRunCreate(BacktestRunBase):
    pass


class BacktestRunUpdate(BaseModel):
    run_id: str | None = Field(default=None, min_length=1)
    mode: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, min_length=1)
    virus_typ: str | None = Field(default=None, min_length=1)
    target_source: str | None = Field(default=None, min_length=1)
    target_key: str | None = None
    target_label: str | None = None
    strict_vintage_mode: bool | None = None
    horizon_days: int | None = Field(default=None, ge=0)
    min_train_points: int | None = Field(default=None, ge=0)
    parameters: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    baseline_metrics: dict[str, Any] | None = None
    improvement_vs_baselines: dict[str, Any] | None = None
    optimized_weights: dict[str, Any] | None = None
    proof_text: str | None = None
    llm_insight: str | None = None
    lead_lag: dict[str, Any] | None = None
    chart_points: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", strict=True)


class BacktestRunResponse(BacktestRunBase):
    id: int = Field(..., ge=1)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

