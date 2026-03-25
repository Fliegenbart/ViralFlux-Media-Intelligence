"""Typed contracts for the rule-based regional decision engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DecisionComponentScore:
    key: str
    value: float
    score: float
    weight: float
    weighted_contribution: float
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionReasonTrace:
    why: list[str] = field(default_factory=list)
    why_details: list[dict[str, Any]] = field(default_factory=list)
    contributing_signals: list[DecisionComponentScore] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    uncertainty_details: list[dict[str, Any]] = field(default_factory=list)
    policy_overrides: list[str] = field(default_factory=list)
    policy_override_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contributing_signals"] = [
            item.to_dict()
            for item in self.contributing_signals
        ]
        return payload


@dataclass(frozen=True)
class RegionalDecisionRuleConfig:
    version: str
    weights: dict[str, float]
    activate_probability_threshold: float
    prepare_probability_threshold: float
    activate_score_threshold: float
    prepare_score_threshold: float
    activate_forecast_confidence_threshold: float
    prepare_forecast_confidence_threshold: float
    activate_freshness_threshold: float
    prepare_freshness_threshold: float
    activate_revision_risk_max: float
    prepare_revision_risk_max: float
    activate_agreement_threshold: float
    prepare_agreement_threshold: float
    activate_trend_threshold: float
    prepare_trend_threshold: float
    prepare_probability_margin: float = 0.08
    agreement_neutral_band: float = 0.03
    min_agreement_signal_count: int = 2
    acceleration_reference: float = 0.8
    failed_quality_gate_confidence_factor: float = 0.55
    uncertainty_revision_risk_threshold: float = 0.45
    uncertainty_freshness_threshold: float = 0.50

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionalDecision:
    bundesland: str
    bundesland_name: str
    virus_typ: str
    horizon_days: int
    signal_stage: str
    stage: str
    decision_score: float
    event_probability: float
    forecast_confidence: float
    source_freshness_score: float
    source_freshness_days: float
    source_revision_risk: float
    trend_acceleration_score: float
    cross_source_agreement_score: float
    cross_source_agreement_direction: str
    usable_source_share: float
    source_coverage_score: float
    explanation_summary: str
    uncertainty_summary: str
    explanation_summary_detail: dict[str, Any] | None = None
    uncertainty_summary_detail: dict[str, Any] | None = None
    components: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    reason_trace: DecisionReasonTrace = field(default_factory=DecisionReasonTrace)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_trace"] = self.reason_trace.to_dict()
        return payload
