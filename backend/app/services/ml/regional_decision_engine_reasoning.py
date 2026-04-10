"""Reasoning and explanation helpers for the regional decision engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def reason_detail(code: str, message: str, **params: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "params": params or {}}


def policy_override_detail(message: str) -> dict[str, Any]:
    normalized = message.lower()
    if "watch_only" in normalized:
        return reason_detail(
            "policy_override_watch_only",
            message,
            final_stage="prepare",
        )
    if "quality gate" in normalized:
        return reason_detail(
            "policy_override_quality_gate",
            message,
            final_stage="prepare",
        )
    return reason_detail("policy_override", message)


def component_trace(
    *,
    components: Mapping[str, float],
    config: Any,
    trend_bundle: Mapping[str, Any],
    agreement_bundle: Mapping[str, Any],
    revision_risk: float,
    freshness_days: float,
    decision_component_score_cls: Any,
) -> list[Any]:
    trace: list[Any] = []
    details = {
        "event_probability": f"Calibrated event probability in the 3-7 day window is {components['event_probability']:.2f}.",
        "forecast_confidence": f"Confidence combines interval width, backtest quality and live source usability ({components['forecast_confidence']:.2f}).",
        "source_freshness": f"Average primary-source freshness is {freshness_days:.1f} days ({components['source_freshness']:.2f}).",
        "revision_safety": f"Average revision risk is {revision_risk:.2f}, leaving safety at {components['revision_safety']:.2f}.",
        "trend_acceleration": f"Recent acceleration score is {components['trend_acceleration']:.2f} from {trend_bundle.get('signals') or []}.",
        "cross_source_agreement": f"Cross-source agreement score is {components['cross_source_agreement']:.2f} with direction {agreement_bundle.get('direction')}.",
    }
    for key, value in components.items():
        weight = float(config.weights.get(key) or 0.0)
        status = "positive" if float(value) >= 0.6 else "mixed" if float(value) >= 0.4 else "negative"
        trace.append(
            decision_component_score_cls(
                key=key,
                value=round(float(value), 4),
                score=round(float(value), 4),
                weight=round(weight, 4),
                weighted_contribution=round(weight * float(value), 4),
                status=status,
                detail=details[key],
            )
        )
    trace.sort(key=lambda item: item.weighted_contribution, reverse=True)
    return trace


def reason_trace(
    *,
    signal_stage: str,
    stage: str,
    event_probability: float,
    forecast_confidence: float,
    freshness_score: float,
    freshness_days: float,
    revision_risk: float,
    trend_bundle: Mapping[str, Any],
    agreement_bundle: Mapping[str, Any],
    thresholds: Mapping[str, float],
    policy_overrides: list[str],
    component_trace: list[Any],
    quality_gate: Mapping[str, Any],
    config: Any,
    decision_reason_trace_cls: Any,
) -> Any:
    why: list[str] = []
    why_details: list[dict[str, Any]] = []
    uncertainty: list[str] = []
    uncertainty_details: list[dict[str, Any]] = []

    if signal_stage == "activate":
        message = (
            f"Event probability {event_probability:.2f} clears the Activate threshold {float(thresholds['activate_probability']):.2f}."
        )
        why.append(message)
        why_details.append(
            reason_detail(
                "event_probability_activate_threshold",
                message,
                event_probability=round(event_probability, 4),
                threshold=round(float(thresholds["activate_probability"]), 4),
            )
        )
    elif signal_stage == "prepare":
        message = (
            f"Event probability {event_probability:.2f} clears the Prepare threshold {float(thresholds['prepare_probability']):.2f}, but not all Activate conditions are met."
        )
        why.append(message)
        why_details.append(
            reason_detail(
                "event_probability_prepare_threshold",
                message,
                event_probability=round(event_probability, 4),
                threshold=round(float(thresholds["prepare_probability"]), 4),
            )
        )
    elif signal_stage == "prepare_early":
        message = (
            f"Event probability {event_probability:.2f} is below the full Prepare threshold {float(thresholds['prepare_probability']):.2f}, but early-warning signals are strong enough for a visible Prepare stage."
        )
        why.append(message)
        why_details.append(
            reason_detail(
                "event_probability_prepare_early_threshold",
                message,
                event_probability=round(event_probability, 4),
                threshold=round(float(thresholds["prepare_probability"]), 4),
            )
        )
    else:
        message = (
            f"Event probability {event_probability:.2f} stays below the rule set needed for Prepare/Activate."
        )
        why.append(message)
        why_details.append(
            reason_detail(
                "event_probability_below_prepare_threshold",
                message,
                event_probability=round(event_probability, 4),
            )
        )

    if forecast_confidence >= float(thresholds["activate_forecast_confidence"]):
        message = f"Forecast confidence is strong at {forecast_confidence:.2f}."
        why.append(message)
        why_details.append(
            reason_detail(
                "forecast_confidence_strong",
                message,
                forecast_confidence=round(forecast_confidence, 4),
            )
        )
    elif forecast_confidence >= float(thresholds["prepare_forecast_confidence"]):
        message = f"Forecast confidence is usable at {forecast_confidence:.2f}."
        why.append(message)
        why_details.append(
            reason_detail(
                "forecast_confidence_usable",
                message,
                forecast_confidence=round(forecast_confidence, 4),
            )
        )
    else:
        message = f"Forecast confidence is only {forecast_confidence:.2f}."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "forecast_confidence_low",
                message,
                forecast_confidence=round(forecast_confidence, 4),
            )
        )

    if freshness_score >= float(thresholds["activate_freshness"]):
        message = f"Primary sources are fresh on average ({freshness_days:.1f} days old)."
        why.append(message)
        why_details.append(
            reason_detail(
                "primary_sources_fresh",
                message,
                freshness_days=round(freshness_days, 2),
                freshness_score=round(freshness_score, 4),
            )
        )
    elif freshness_score < float(thresholds["prepare_freshness"]):
        message = f"Primary-source freshness is weak ({freshness_days:.1f} days average age)."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "primary_sources_stale",
                message,
                freshness_days=round(freshness_days, 2),
                freshness_score=round(freshness_score, 4),
            )
        )

    if revision_risk > float(thresholds["prepare_revision_risk_max"]):
        message = f"Revision risk is high at {revision_risk:.2f}."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "revision_risk_high",
                message,
                revision_risk=round(revision_risk, 4),
            )
        )
    elif revision_risk > float(thresholds["activate_revision_risk_max"]):
        message = f"Revision risk is still material at {revision_risk:.2f}."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "revision_risk_material",
                message,
                revision_risk=round(revision_risk, 4),
            )
        )

    trend_score = float(trend_bundle.get("score") or 0.0)
    trend_raw = float(trend_bundle.get("raw") or 0.0)
    if trend_score >= float(thresholds["activate_trend"]):
        message = f"Recent trend acceleration is supportive ({trend_raw:.2f})."
        why.append(message)
        why_details.append(
            reason_detail(
                "trend_acceleration_supportive",
                message,
                trend_raw=round(trend_raw, 4),
                trend_score=round(trend_score, 4),
            )
        )
    elif trend_score < float(thresholds["prepare_trend"]):
        message = f"Trend acceleration is not yet convincing ({trend_raw:.2f})."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "trend_acceleration_not_convincing",
                message,
                trend_raw=round(trend_raw, 4),
                trend_score=round(trend_score, 4),
            )
        )

    agreement_signal_count = int(agreement_bundle.get("signal_count") or 0)
    agreement_score = float(agreement_bundle.get("support_score") or 0.0)
    agreement_direction = str(agreement_bundle.get("direction") or "flat")
    if agreement_signal_count < int(config.min_agreement_signal_count):
        message = "Cross-source agreement is low-evidence because fewer than two directional source signals are available."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "cross_source_agreement_low_evidence",
                message,
                signal_count=agreement_signal_count,
            )
        )
    elif agreement_direction == "up" and agreement_score >= float(thresholds["prepare_agreement"]):
        message = f"{agreement_signal_count} source trends align upward."
        why.append(message)
        why_details.append(
            reason_detail(
                "cross_source_agreement_upward",
                message,
                signal_count=agreement_signal_count,
                agreement_score=round(agreement_score, 4),
                direction=agreement_direction,
            )
        )
    else:
        message = "Cross-source agreement does not clearly confirm an upward move."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "cross_source_agreement_not_upward",
                message,
                signal_count=agreement_signal_count,
                agreement_score=round(agreement_score, 4),
                direction=agreement_direction,
            )
        )

    if not quality_gate.get("overall_passed"):
        message = "Regional forecast quality gate is currently not passed."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "quality_gate_not_passed",
                message,
            )
        )
    if stage != signal_stage and not policy_overrides and signal_stage != "prepare_early":
        message = "Final stage differs from the raw signal stage because of a policy overlay."
        uncertainty.append(message)
        uncertainty_details.append(
            reason_detail(
                "final_stage_policy_overlay",
                message,
                signal_stage=signal_stage,
                final_stage=stage,
            )
        )

    return decision_reason_trace_cls(
        why=why,
        why_details=why_details,
        contributing_signals=component_trace[:4],
        uncertainty=uncertainty,
        uncertainty_details=uncertainty_details,
        policy_overrides=policy_overrides,
        policy_override_details=[
            policy_override_detail(item)
            for item in policy_overrides
        ],
    )


def explanation_summary(
    *,
    bundesland_name: str,
    stage: str,
    event_probability: float,
    forecast_confidence: float,
    trend_bundle: Mapping[str, Any],
    agreement_bundle: Mapping[str, Any],
) -> str:
    trend_raw = float(trend_bundle.get("raw") or 0.0)
    agreement_direction = str(agreement_bundle.get("direction") or "flat")
    return (
        f"{bundesland_name}: {stage.title()} because event probability is {event_probability:.2f}, "
        f"forecast confidence is {forecast_confidence:.2f}, trend acceleration is {trend_raw:.2f}, "
        f"and cross-source direction is {agreement_direction}."
    )


def explanation_summary_detail(
    *,
    bundesland_name: str,
    stage: str,
    event_probability: float,
    forecast_confidence: float,
    trend_bundle: Mapping[str, Any],
    agreement_bundle: Mapping[str, Any],
    message: str,
) -> dict[str, Any]:
    return reason_detail(
        "decision_summary",
        message,
        bundesland_name=bundesland_name,
        stage=stage,
        event_probability=round(event_probability, 4),
        forecast_confidence=round(forecast_confidence, 4),
        trend_raw=round(float(trend_bundle.get("raw") or 0.0), 4),
        agreement_direction=str(agreement_bundle.get("direction") or "flat"),
    )


def uncertainty_summary(
    *,
    revision_risk: float,
    freshness_score: float,
    agreement_bundle: Mapping[str, Any],
    quality_gate: Mapping[str, Any],
    config: Any,
) -> str:
    parts: list[str] = []
    if revision_risk >= float(config.uncertainty_revision_risk_threshold):
        parts.append(f"revision risk {revision_risk:.2f}")
    if freshness_score < float(config.uncertainty_freshness_threshold):
        parts.append(f"freshness score {freshness_score:.2f}")
    if int(agreement_bundle.get("signal_count") or 0) < int(config.min_agreement_signal_count):
        parts.append("thin agreement evidence")
    elif str(agreement_bundle.get("direction") or "flat") != "up":
        parts.append("no positive cross-source agreement")
    if not quality_gate.get("overall_passed"):
        parts.append("quality gate not passed")
    if not parts:
        return "Residual uncertainty is currently limited."
    return "Remaining uncertainty: " + ", ".join(parts) + "."


def uncertainty_summary_detail(
    *,
    revision_risk: float,
    freshness_score: float,
    agreement_bundle: Mapping[str, Any],
    quality_gate: Mapping[str, Any],
    config: Any,
    message: str,
) -> dict[str, Any]:
    parts: list[str] = []
    if revision_risk >= float(config.uncertainty_revision_risk_threshold):
        parts.append("revision_risk")
    if freshness_score < float(config.uncertainty_freshness_threshold):
        parts.append("freshness_score")
    if int(agreement_bundle.get("signal_count") or 0) < int(config.min_agreement_signal_count):
        parts.append("thin_agreement_evidence")
    elif str(agreement_bundle.get("direction") or "flat") != "up":
        parts.append("no_positive_cross_source_agreement")
    if not quality_gate.get("overall_passed"):
        parts.append("quality_gate_not_passed")
    return reason_detail(
        "uncertainty_summary",
        message,
        parts=parts,
        revision_risk=round(revision_risk, 4),
        freshness_score=round(freshness_score, 4),
        agreement_signal_count=int(agreement_bundle.get("signal_count") or 0),
        agreement_direction=str(agreement_bundle.get("direction") or "flat"),
    )
