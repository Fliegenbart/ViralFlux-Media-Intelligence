"""Typed contracts for the rule-based regional decision engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


_DECISION_KEY_RENAMES = {
    "decision_score": "decision_priority_index",
    "forecast_confidence": "signal_support_score",
    "activate_forecast_confidence": "activate_signal_support",
    "prepare_forecast_confidence": "prepare_signal_support",
}

_DECISION_TEXT_REPLACEMENTS = (
    ("Forecast confidence", "Signal support"),
    ("forecast confidence", "signal support"),
    (
        "Confidence combines interval width, backtest quality and live source usability",
        "Signal support combines interval width, backtest quality and live source usability",
    ),
    (
        "trend, freshness and confidence support preparation",
        "trend, freshness and signal support justify preparation",
    ),
)


def _normalize_decision_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value
    for source, target in _DECISION_TEXT_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    if normalized.startswith("forecast_confidence_"):
        return "signal_support_" + normalized[len("forecast_confidence_"):]
    return normalized


def _normalize_decision_structure(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            target_key = _DECISION_KEY_RENAMES.get(str(key), str(key))
            normalized[target_key] = _normalize_decision_structure(item)
        if normalized.get("key") == "forecast_confidence":
            normalized["key"] = "signal_support_score"
        return normalized
    if isinstance(value, list):
        return [_normalize_decision_structure(item) for item in value]
    return _normalize_decision_text(value)


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
        return _normalize_decision_structure(payload)
