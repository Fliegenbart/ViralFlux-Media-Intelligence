"""Signal and threshold helpers for the regional decision engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def thresholds(
    *,
    config: Any,
    action_threshold: float,
) -> dict[str, float]:
    activate_probability = max(float(action_threshold), float(config.activate_probability_threshold))
    prepare_probability = max(
        0.0,
        min(
            activate_probability - float(config.prepare_probability_margin),
            float(config.prepare_probability_threshold),
        ),
    )
    return {
        "activate_probability": activate_probability,
        "prepare_probability": prepare_probability,
        "activate_score": float(config.activate_score_threshold),
        "prepare_score": float(config.prepare_score_threshold),
        "activate_forecast_confidence": float(config.activate_forecast_confidence_threshold),
        "prepare_forecast_confidence": float(config.prepare_forecast_confidence_threshold),
        "activate_freshness": float(config.activate_freshness_threshold),
        "prepare_freshness": float(config.prepare_freshness_threshold),
        "activate_revision_risk_max": float(config.activate_revision_risk_max),
        "prepare_revision_risk_max": float(config.prepare_revision_risk_max),
        "activate_agreement": float(config.activate_agreement_threshold),
        "prepare_agreement": float(config.prepare_agreement_threshold),
        "activate_trend": float(config.activate_trend_threshold),
        "prepare_trend": float(config.prepare_trend_threshold),
    }


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def collect_source_snapshot(
    service: Any,
    *,
    prefixes: tuple[str, ...],
    feature_row: Mapping[str, Any],
    source_prefix_to_config: Mapping[str, str],
    nowcast_source_configs: Mapping[str, Any],
    clamp_fn: Any,
) -> dict[str, Any]:
    freshness_scores: list[float] = []
    freshness_days: list[float] = []
    revision_risks: list[float] = []
    usable_scores: list[float] = []
    coverage_scores: list[float] = []
    prefix_details: list[dict[str, Any]] = []

    for prefix in prefixes:
        freshness = service._safe_float(feature_row.get(f"{prefix}_freshness_days"))
        risk = service._safe_float(feature_row.get(f"{prefix}_revision_risk"))
        usable_confidence = service._safe_float(feature_row.get(f"{prefix}_usable_confidence"))
        coverage_ratio = service._safe_float(feature_row.get(f"{prefix}_coverage_ratio"))
        usable_flag = service._safe_float(feature_row.get(f"{prefix}_usable"))
        if freshness is None and risk is None and usable_confidence is None and coverage_ratio is None:
            continue

        source_id = source_prefix_to_config.get(prefix)
        max_staleness = float(
            nowcast_source_configs[source_id].max_staleness_days
            if source_id in nowcast_source_configs
            else 14
        )
        freshness_score = clamp_fn(1.0 - (max(float(freshness or 0.0), 0.0) / max(max_staleness, 1.0)))
        freshness_scores.append(freshness_score)
        freshness_days.append(max(float(freshness or 0.0), 0.0))
        if risk is not None:
            revision_risks.append(clamp_fn(risk))
        if usable_confidence is not None:
            usable_scores.append(clamp_fn(usable_confidence))
        elif usable_flag is not None:
            usable_scores.append(clamp_fn(usable_flag))
        if coverage_ratio is not None:
            coverage_scores.append(clamp_fn(coverage_ratio))
        prefix_details.append(
            {
                "prefix": prefix,
                "freshness_days": round(max(float(freshness or 0.0), 0.0), 2),
                "freshness_score": round(freshness_score, 4),
                "revision_risk": round(clamp_fn(risk or 0.0), 4),
                "usable_confidence": round(clamp_fn(usable_confidence or usable_flag or 0.0), 4),
                "coverage_ratio": round(clamp_fn(coverage_ratio or 0.0), 4),
            }
        )

    return {
        "freshness_score": round(sum(freshness_scores) / len(freshness_scores), 4) if freshness_scores else 0.0,
        "avg_freshness_days": round(sum(freshness_days) / len(freshness_days), 4) if freshness_days else 0.0,
        "revision_risk": round(sum(revision_risks) / len(revision_risks), 4) if revision_risks else 0.0,
        "usable_share": round(sum(usable_scores) / len(usable_scores), 4) if usable_scores else 0.0,
        "coverage_score": round(sum(coverage_scores) / len(coverage_scores), 4) if coverage_scores else 0.0,
        "sources": prefix_details,
    }


def forecast_confidence_score(
    *,
    prediction: Mapping[str, Any],
    metadata: Mapping[str, Any],
    freshness_score: float,
    usable_share: float,
    coverage_score: float,
    quality_gate: Mapping[str, Any],
    config: Any,
    clamp_fn: Any,
) -> float:
    metrics = dict(metadata.get("aggregate_metrics") or {})
    interval = dict(prediction.get("prediction_interval") or {})
    upper = max(float(interval.get("upper") or 0.0), 0.0)
    lower = max(float(interval.get("lower") or 0.0), 0.0)
    predicted = max(float(prediction.get("expected_next_week_incidence") or 0.0), 0.0)
    current = max(float(prediction.get("current_known_incidence") or 0.0), 0.0)
    width = max(upper - lower, 0.0)
    scale = max(predicted, current, 1.0)
    interval_score = clamp_fn(1.0 - (width / max(2.0 * scale, 1.0)))

    parts = [interval_score]
    if metrics.get("ece") is not None:
        parts.append(clamp_fn(1.0 - (float(metrics["ece"]) / 0.20)))
    if metrics.get("brier_score") is not None:
        parts.append(clamp_fn(1.0 - (float(metrics["brier_score"]) / 0.25)))
    if metrics.get("pr_auc") is not None:
        parts.append(clamp_fn(float(metrics["pr_auc"])))
    parts.append(
        1.0
        if quality_gate.get("overall_passed")
        else float(config.failed_quality_gate_confidence_factor)
    )
    parts.append(clamp_fn((float(freshness_score) + float(usable_share) + float(coverage_score)) / 3.0))
    return round(sum(parts) / len(parts), 4)


def trend_acceleration_bundle(
    service: Any,
    *,
    virus_typ: str,
    feature_row: Mapping[str, Any],
    config: Any,
    clamp_fn: Any,
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    for label, key in (
        ("wastewater_acceleration", "ww_acceleration7d"),
        ("national_wastewater_acceleration", "national_ww_acceleration7d"),
        ("sars_trends_acceleration", "sars_trends_acceleration_7d"),
    ):
        value = service._safe_float(feature_row.get(key))
        if value is None:
            continue
        signals.append({"signal": label, "key": key, "value": round(float(value), 4)})

    if not signals:
        return {"score": 0.0, "raw": 0.0, "signals": []}

    primary = float(signals[0]["value"])
    secondary = [float(item["value"]) for item in signals[1:]]
    blended = primary if not secondary else (0.7 * primary + 0.3 * (sum(secondary) / len(secondary)))
    score = clamp_fn(0.5 + (blended / max(float(config.acceleration_reference), 0.1)))
    if virus_typ == "SARS-CoV-2" and secondary:
        score = clamp_fn(score + 0.05)
    return {
        "score": round(score, 4),
        "raw": round(blended, 4),
        "signals": signals,
    }


def agreement_bundle(
    service: Any,
    *,
    virus_typ: str,
    feature_row: Mapping[str, Any],
    config: Any,
    trend_signal_keys: Mapping[str, Any],
    clamp_fn: Any,
) -> dict[str, Any]:
    keys = trend_signal_keys.get(virus_typ, trend_signal_keys["default"])
    directional_signals: list[dict[str, Any]] = []
    positive = 0
    negative = 0
    for label, key in keys:
        value = service._safe_float(feature_row.get(key))
        if value is None:
            continue
        direction = "flat"
        if value > float(config.agreement_neutral_band):
            direction = "up"
            positive += 1
        elif value < -float(config.agreement_neutral_band):
            direction = "down"
            negative += 1
        directional_signals.append(
            {
                "signal": label,
                "key": key,
                "value": round(float(value), 4),
                "direction": direction,
            }
        )

    active_count = positive + negative
    if active_count < int(config.min_agreement_signal_count):
        if positive > 0:
            return {
                "score": 0.5,
                "support_score": 0.5,
                "direction": "up",
                "signal_count": active_count,
                "signals": directional_signals,
            }
        if negative > 0:
            return {
                "score": 0.5,
                "support_score": 0.0,
                "direction": "down",
                "signal_count": active_count,
                "signals": directional_signals,
            }
        return {
            "score": 0.0,
            "support_score": 0.0,
            "direction": "flat",
            "signal_count": active_count,
            "signals": directional_signals,
        }

    dominant = max(positive, negative)
    agreement_score = clamp_fn(dominant / max(active_count, 1))
    if positive >= negative and positive > 0:
        direction = "up"
        support_score = agreement_score
    else:
        direction = "down" if negative > 0 else "flat"
        support_score = 0.0
    return {
        "score": round(agreement_score, 4),
        "support_score": round(support_score, 4),
        "direction": direction,
        "signal_count": active_count,
        "signals": directional_signals,
    }


def signal_stage(
    *,
    decision_score: float,
    event_probability: float,
    forecast_confidence: float,
    freshness_score: float,
    revision_risk: float,
    trend_score: float,
    agreement_support_score: float,
    agreement_signal_count: int,
    agreement_direction: str,
    thresholds: Mapping[str, float],
    config: Any,
) -> str:
    activate_agreement_ok = (
        agreement_signal_count < int(config.min_agreement_signal_count)
        or agreement_support_score >= float(thresholds["activate_agreement"])
    )
    prepare_agreement_ok = (
        agreement_signal_count < int(config.min_agreement_signal_count)
        or agreement_support_score >= float(thresholds["prepare_agreement"])
    )
    early_prepare_score_floor = max(0.0, float(thresholds["prepare_score"]) - 0.06)
    early_prepare_agreement_ok = (
        prepare_agreement_ok
        or (agreement_signal_count >= 1 and str(agreement_direction).lower() == "up")
    )

    if all(
        (
            decision_score >= float(thresholds["activate_score"]),
            event_probability >= float(thresholds["activate_probability"]),
            forecast_confidence >= float(thresholds["activate_forecast_confidence"]),
            freshness_score >= float(thresholds["activate_freshness"]),
            revision_risk <= float(thresholds["activate_revision_risk_max"]),
            trend_score >= float(thresholds["activate_trend"]),
            activate_agreement_ok,
        )
    ):
        return "activate"
    if all(
        (
            decision_score >= float(thresholds["prepare_score"]),
            event_probability >= float(thresholds["prepare_probability"]),
            forecast_confidence >= float(thresholds["prepare_forecast_confidence"]),
            freshness_score >= float(thresholds["prepare_freshness"]),
            revision_risk <= float(thresholds["prepare_revision_risk_max"]),
            trend_score >= float(thresholds["prepare_trend"]),
            prepare_agreement_ok,
        )
    ):
        return "prepare"
    if all(
        (
            decision_score >= early_prepare_score_floor,
            forecast_confidence >= float(thresholds["prepare_forecast_confidence"]),
            freshness_score >= float(thresholds["prepare_freshness"]),
            revision_risk <= float(thresholds["prepare_revision_risk_max"]),
            trend_score >= float(thresholds["prepare_trend"]),
            early_prepare_agreement_ok,
        )
    ):
        return "prepare_early"
    return "watch"


def policy_stage(
    *,
    signal_stage: str,
    prediction: Mapping[str, Any],
) -> tuple[str, list[str]]:
    overrides: list[str] = []
    activation_policy = str(prediction.get("activation_policy") or "quality_gate")
    quality_gate = dict(prediction.get("quality_gate") or {})
    if signal_stage == "watch":
        return "watch", overrides

    if activation_policy == "watch_only":
        overrides.append("Activation policy 'watch_only' keeps the region in Prepare until budget release is allowed.")
        return "prepare", overrides

    if not quality_gate.get("overall_passed"):
        overrides.append("Regional quality gate blocks Activate, but the region stays visible as Prepare.")
        return "prepare", overrides

    if signal_stage == "prepare_early":
        return "prepare", overrides
    return signal_stage, overrides
