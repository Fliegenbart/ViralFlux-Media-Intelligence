"""Typed contracts for research-only Tri-Layer Evidence Fusion v0."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SourceStatus = Literal["connected", "partial", "not_connected"]
GateState = Literal["pass", "watch", "fail", "not_available"]
BudgetPermissionState = Literal[
    "blocked",
    "calibration_window",
    "shadow_only",
    "limited",
    "approved",
]
WavePhase = Literal["baseline", "early_growth", "acceleration", "peak", "decline", "unknown"]


class SourceEvidence(BaseModel):
    status: SourceStatus = "not_connected"
    freshness: float | None = None
    reliability: float | None = None
    baseline_stability: float | None = None
    snr: float | None = None
    consistency: float | None = None
    drift: float | None = None
    coverage: float | None = None
    signal: float | None = None
    intensity: float | None = None
    growth: float | None = None
    real_sell_out: bool = False
    historical_weeks: int | None = None
    region_count: int | None = None
    holdout_validated: bool = False
    oos_lift_predictiveness: float | None = None
    budget_isolated: bool = False
    causal_adjusted: bool = False


class BudgetIsolationEvidence(BaseModel):
    status: GateState = "pass"
    reason: str | None = None


class TriLayerRegionEvidence(BaseModel):
    region: str
    region_code: str
    wastewater: SourceEvidence = Field(default_factory=SourceEvidence)
    clinical: SourceEvidence = Field(default_factory=SourceEvidence)
    sales: SourceEvidence = Field(default_factory=SourceEvidence)
    budget_isolation: BudgetIsolationEvidence = Field(default_factory=BudgetIsolationEvidence)


class LatentWaveState(BaseModel):
    intensity_mean: float | None = None
    intensity_p10: float | None = None
    intensity_p90: float | None = None
    growth_mean: float | None = None
    uncertainty: float | None = None
    wave_phase: WavePhase = "unknown"


class EvidenceWeights(BaseModel):
    wastewater: float | None = None
    clinical: float | None = None
    sales: float | None = None


class LeadLagEstimate(BaseModel):
    wastewater_to_clinical_days_mean: float | None = None
    clinical_to_sales_days_mean: float | None = None
    lag_uncertainty: float | None = None


class GateStates(BaseModel):
    epidemiological_signal: GateState = "not_available"
    clinical_confirmation: GateState = "not_available"
    sales_calibration: GateState = "not_available"
    coverage: GateState = "not_available"
    drift: GateState = "not_available"
    budget_isolation: GateState = "pass"


class BudgetPermission(BaseModel):
    state: BudgetPermissionState
    budget_can_change: bool = False
    reasons: list[str] = Field(default_factory=list)


class TriLayerRegionSnapshot(BaseModel):
    region: str
    region_code: str
    early_warning_score: float | None = None
    commercial_relevance_score: float | None = None
    budget_permission_state: BudgetPermissionState = "blocked"
    budget_can_change: bool = False
    wave_phase: WavePhase = "unknown"
    posterior: LatentWaveState = Field(default_factory=LatentWaveState)
    evidence_weights: EvidenceWeights = Field(default_factory=EvidenceWeights)
    lead_lag: LeadLagEstimate = Field(default_factory=LeadLagEstimate)
    gates: GateStates = Field(default_factory=GateStates)
    explanation: str
