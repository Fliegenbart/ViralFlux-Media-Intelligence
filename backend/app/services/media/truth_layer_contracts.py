"""Typed contracts for the optional GELO truth/outcome layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OutcomeObservationInput:
    brand: str
    product: str
    region_code: str
    metric_name: str
    metric_value: float
    window_start: datetime
    window_end: datetime
    source_label: str = "manual"
    metric_unit: str | None = None
    channel: str | None = None
    campaign_id: str | None = None
    holdout_group: str | None = None
    confidence_hint: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["window_start"] = self.window_start.isoformat()
        payload["window_end"] = self.window_end.isoformat()
        return payload


@dataclass(frozen=True)
class OutcomeReadinessAssessment:
    status: str
    score: float
    coverage_weeks: int
    metrics_present: list[str] = field(default_factory=list)
    regions_present: int = 0
    products_present: int = 0
    spend_windows: int = 0
    response_windows: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SignalOutcomeAgreement:
    status: str
    signal_present: bool
    historical_response_observed: bool
    score: float | None = None
    signal_confidence: float | None = None
    outcome_support_score: float | None = None
    outcome_confidence: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HoldoutEligibility:
    eligible: bool
    ready: bool
    holdout_groups: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TruthLayerAssessment:
    scope: dict[str, Any]
    outcome_readiness: OutcomeReadinessAssessment
    signal_outcome_agreement: SignalOutcomeAgreement
    holdout_eligibility: HoldoutEligibility
    evidence_status: str
    evidence_confidence: float
    commercial_gate: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome_readiness"] = self.outcome_readiness.to_dict()
        payload["signal_outcome_agreement"] = self.signal_outcome_agreement.to_dict()
        payload["holdout_eligibility"] = self.holdout_eligibility.to_dict()
        return payload
