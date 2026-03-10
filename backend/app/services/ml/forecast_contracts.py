from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any


DEFAULT_DECISION_HORIZON_DAYS = 7
DEFAULT_DECISION_BASELINE_WINDOW_DAYS = 84
DEFAULT_DECISION_EVENT_THRESHOLD_PCT = 25.0


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


def event_probability_from_forecast(
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


def normalized_expected_value_index(
    *,
    event_probability: float | None,
    modifier: float = 1.0,
) -> float:
    probability = float(event_probability or 0.0)
    adjusted = clamp(probability * float(modifier), 0.0, 1.0)
    return round(adjusted * 100.0, 1)


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
    brier_score: float | None = None
    ece: float | None = None
    calibration_passed: bool | None = None
    confidence: float | None = None
    confidence_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload.get("confidence_label") is None:
            payload["confidence_label"] = confidence_label(self.confidence)
        return payload


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
class OpportunityAssessment:
    action_class: str
    truth_readiness: str
    forecast_readiness: str
    expected_value_index: float
    expected_units_lift: float | None = None
    expected_revenue_lift: float | None = None
    lift_interval: dict[str, Any] | None = None
    secondary_modifier: float = 1.0
    explanation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
