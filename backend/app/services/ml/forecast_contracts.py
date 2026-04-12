from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any


DEFAULT_DECISION_HORIZON_DAYS = 7
DEFAULT_DECISION_BASELINE_WINDOW_DAYS = 84
DEFAULT_DECISION_EVENT_THRESHOLD_PCT = 25.0
HEURISTIC_EVENT_SCORE_SOURCE = "heuristic_sigmoid_fallback_score"
BACKTEST_RELIABILITY_PROXY_SOURCE = "backtest_reliability_proxy"


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def confidence_label(value: float | None) -> str:
    score = float(value or 0.0)
    if score >= 0.8:
        return "Sehr Hoch"
    if score >= 0.65:
        return "Hoch"
    if score >= 0.45:
        return "Mittel"
    return "Niedrig"


def threshold_value(baseline: float, threshold_pct: float = DEFAULT_DECISION_EVENT_THRESHOLD_PCT) -> float:
    return float(baseline) * (1.0 + float(threshold_pct) / 100.0)


def heuristic_event_score_from_forecast(
    *,
    prediction: float,
    baseline: float,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    threshold_pct: float = DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
) -> float:
    threshold = threshold_value(baseline, threshold_pct=threshold_pct)
    spread_candidates = [
        abs(float(prediction) - float(baseline)) * 0.35,
        abs(float(upper_bound or prediction) - float(lower_bound or prediction)) / 2.0,
        abs(float(baseline)) * 0.12,
        1.0,
    ]
    spread = max(value for value in spread_candidates if math.isfinite(value))
    z_score = (float(prediction) - threshold) / max(spread, 1e-6)
    return round(clamp(sigmoid(z_score), 0.001, 0.999), 4)


def normalized_decision_priority_index(
    *,
    decision_basis_score: float | None,
    modifier: float = 1.0,
) -> float:
    basis_score = float(decision_basis_score or 0.0)
    adjusted = clamp(basis_score * float(modifier), 0.0, 1.0)
    return round(adjusted * 100.0, 1)


def normalized_signal_index(
    *,
    signal_basis_score: float | None,
) -> float:
    basis_score = clamp(float(signal_basis_score or 0.0), 0.0, 1.0)
    return round(basis_score * 100.0, 1)


def normalized_expected_value_index(
    *,
    decision_basis_score: float | None,
    modifier: float = 1.0,
) -> float:
    """Deprecated alias for the decision-priority index."""
    return normalized_decision_priority_index(
        decision_basis_score=decision_basis_score,
        modifier=modifier,
    )


def resolve_decision_basis_score(
    *,
    event_probability: float | None,
    heuristic_event_score: float | None,
) -> float | None:
    if event_probability is not None:
        return float(event_probability)
    if heuristic_event_score is not None:
        return float(heuristic_event_score)
    return None


def resolve_decision_basis_type(
    *,
    event_probability: float | None,
    heuristic_event_score: float | None,
) -> str | None:
    if event_probability is not None:
        return "learned_probability"
    if heuristic_event_score is not None:
        return "heuristic_signal"
    return None


def normalize_event_forecast_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Keep event-forecast semantics explicit at the contract boundary."""
    normalized = dict(payload or {})
    event_probability = (
        float(normalized["event_probability"])
        if normalized.get("event_probability") is not None
        else None
    )
    heuristic_event_score = normalized.get("heuristic_event_score")
    if heuristic_event_score is None and event_probability is None and normalized.get("event_signal_score") is not None:
        heuristic_event_score = normalized.get("event_signal_score")
    heuristic_event_score = (
        float(heuristic_event_score)
        if heuristic_event_score is not None
        else None
    )

    normalized["event_probability"] = event_probability
    normalized["heuristic_event_score"] = heuristic_event_score
    normalized.pop("event_signal_score", None)

    reliability_value = normalized.get("reliability_score")
    if reliability_value is None:
        reliability_value = normalized.get("confidence")
    if reliability_value is not None:
        reliability_value = float(reliability_value)
        normalized["reliability_score"] = reliability_value
        normalized["reliability_label"] = confidence_label(reliability_value)
    else:
        normalized.pop("reliability_score", None)
        normalized.pop("reliability_label", None)

    if event_probability is not None:
        signal_source = normalized.get("signal_source") or normalized.get("probability_source")
    else:
        signal_source = (
            normalized.get("signal_source")
            or normalized.get("probability_source")
            or (HEURISTIC_EVENT_SCORE_SOURCE if heuristic_event_score is not None else None)
        )
        normalized["probability_source"] = None
    normalized["signal_source"] = str(signal_source) if signal_source is not None else None

    normalized.pop("confidence", None)
    normalized.pop("confidence_label", None)
    normalized.pop("confidence_semantics", None)
    if normalized.get("uncertainty_source") in {None, "", "backtest_interval_coverage"}:
        normalized["uncertainty_source"] = BACKTEST_RELIABILITY_PROXY_SOURCE
    if normalized.get("fallback_used") is None and normalized.get("event_probability") is None:
        normalized["fallback_used"] = normalized.get("heuristic_event_score") is not None
    return normalized


@dataclass(frozen=True)
class BurdenForecastPoint:
    target_date: str
    median: float
    lower: float | None = None
    upper: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BurdenForecast:
    target: str
    region: str
    issue_date: str | None
    horizon_days: int
    model_version: str | None
    points: list[BurdenForecastPoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["points"] = [point.to_dict() for point in self.points]
        return payload


@dataclass(frozen=True)
class EventForecast:
    event_key: str
    horizon_days: int
    event_probability: float | None
    threshold_pct: float
    baseline_value: float | None
    threshold_value: float | None
    calibration_method: str
    heuristic_event_score: float | None = None
    brier_score: float | None = None
    ece: float | None = None
    calibration_passed: bool | None = None
    reliability_score: float | None = None
    backtest_quality_score: float | None = None
    probability_source: str | None = None
    calibration_mode: str | None = None
    uncertainty_source: str | None = None
    fallback_reason: str | None = None
    learned_model_version: str | None = None
    fallback_used: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return normalize_event_forecast_payload(asdict(self))


@dataclass(frozen=True)
class ForecastQuality:
    forecast_readiness: str
    drift_status: str
    freshness_status: str
    baseline_deltas: dict[str, Any] = field(default_factory=dict)
    timing_metrics: dict[str, Any] = field(default_factory=dict)
    interval_coverage: dict[str, Any] = field(default_factory=dict)
    promotion_gate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForecastMonitoringSnapshot:
    virus_typ: str
    target_source: str
    monitoring_status: str
    forecast_readiness: str
    drift_status: str
    freshness_status: str
    accuracy_freshness_status: str
    backtest_freshness_status: str
    issue_date: str | None = None
    model_version: str | None = None
    event_forecast: dict[str, Any] = field(default_factory=dict)
    latest_accuracy: dict[str, Any] = field(default_factory=dict)
    latest_backtest: dict[str, Any] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OpportunityAssessment:
    action_class: str
    truth_readiness: str
    forecast_readiness: str
    decision_priority_index: float
    decision_basis_score: float | None = None
    decision_basis_type: str | None = None
    expected_units_lift: float | None = None
    expected_revenue_lift: float | None = None
    lift_interval: dict[str, Any] | None = None
    secondary_modifier: float = 1.0
    explanation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
