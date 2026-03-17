"""Explicit, audit-ready regional Watch/Prepare/Activate decision rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.ml.nowcast_revision import NOWCAST_SOURCE_CONFIGS
from app.services.ml.regional_decision_contracts import (
    DecisionComponentScore,
    DecisionReasonTrace,
    RegionalDecision,
    RegionalDecisionRuleConfig,
)


PRIMARY_SOURCE_PREFIXES: dict[str, tuple[str, ...]] = {
    "default": (
        "ww_level",
        "survstat_current_incidence",
        "grippeweb_are",
        "grippeweb_ili",
    ),
    "Influenza A": (
        "ww_level",
        "survstat_current_incidence",
        "grippeweb_are",
        "grippeweb_ili",
        "ifsg_influenza",
    ),
    "Influenza B": (
        "ww_level",
        "survstat_current_incidence",
        "grippeweb_are",
        "grippeweb_ili",
        "ifsg_influenza",
    ),
    "RSV A": (
        "ww_level",
        "survstat_current_incidence",
        "grippeweb_are",
        "grippeweb_ili",
        "ifsg_rsv",
    ),
    "SARS-CoV-2": (
        "ww_level",
        "survstat_current_incidence",
        "grippeweb_are",
        "grippeweb_ili",
        "sars_are",
        "sars_notaufnahme",
        "sars_trends",
    ),
}

SOURCE_PREFIX_TO_CONFIG = {
    "ww_level": "wastewater",
    "survstat_current_incidence": "survstat_kreis",
    "grippeweb_are": "grippeweb",
    "grippeweb_ili": "grippeweb",
    "ifsg_influenza": "ifsg_influenza",
    "ifsg_rsv": "ifsg_rsv",
    "sars_are": "are_konsultation",
    "sars_notaufnahme": "notaufnahme",
    "sars_trends": "google_trends",
}

TREND_SIGNAL_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    "default": (
        ("wastewater", "ww_slope7d"),
        ("survstat", "survstat_momentum_2w"),
        ("grippeweb_are", "grippeweb_are_momentum_1w"),
        ("grippeweb_ili", "grippeweb_ili_momentum_1w"),
    ),
    "Influenza A": (
        ("wastewater", "ww_slope7d"),
        ("survstat", "survstat_momentum_2w"),
        ("grippeweb_are", "grippeweb_are_momentum_1w"),
        ("grippeweb_ili", "grippeweb_ili_momentum_1w"),
        ("ifsg", "ifsg_influenza_momentum_1w"),
    ),
    "Influenza B": (
        ("wastewater", "ww_slope7d"),
        ("survstat", "survstat_momentum_2w"),
        ("grippeweb_are", "grippeweb_are_momentum_1w"),
        ("grippeweb_ili", "grippeweb_ili_momentum_1w"),
        ("ifsg", "ifsg_influenza_momentum_1w"),
    ),
    "RSV A": (
        ("wastewater", "ww_slope7d"),
        ("survstat", "survstat_momentum_2w"),
        ("grippeweb_are", "grippeweb_are_momentum_1w"),
        ("grippeweb_ili", "grippeweb_ili_momentum_1w"),
        ("ifsg", "ifsg_rsv_momentum_1w"),
    ),
    "SARS-CoV-2": (
        ("wastewater", "ww_slope7d"),
        ("survstat", "survstat_momentum_2w"),
        ("grippeweb_are", "grippeweb_are_momentum_1w"),
        ("grippeweb_ili", "grippeweb_ili_momentum_1w"),
        ("are", "sars_are_momentum_1w"),
        ("notaufnahme", "sars_notaufnahme_momentum_7d"),
        ("trends", "sars_trends_momentum_14_28"),
    ),
}

DEFAULT_RULE_CONFIG = RegionalDecisionRuleConfig(
    version="regional_decision_v1",
    weights={
        "event_probability": 0.32,
        "forecast_confidence": 0.20,
        "source_freshness": 0.16,
        "revision_safety": 0.12,
        "trend_acceleration": 0.12,
        "cross_source_agreement": 0.08,
    },
    activate_probability_threshold=0.65,
    prepare_probability_threshold=0.50,
    activate_score_threshold=0.72,
    prepare_score_threshold=0.54,
    activate_forecast_confidence_threshold=0.62,
    prepare_forecast_confidence_threshold=0.48,
    activate_freshness_threshold=0.58,
    prepare_freshness_threshold=0.42,
    activate_revision_risk_max=0.45,
    prepare_revision_risk_max=0.70,
    activate_agreement_threshold=0.60,
    prepare_agreement_threshold=0.45,
    activate_trend_threshold=0.58,
    prepare_trend_threshold=0.45,
)

SARS_RULE_CONFIG = RegionalDecisionRuleConfig(
    **{
        **DEFAULT_RULE_CONFIG.to_dict(),
        "version": "regional_decision_sars_v1",
        "activate_probability_threshold": 0.68,
        "prepare_probability_threshold": 0.52,
        "activate_score_threshold": 0.74,
        "prepare_score_threshold": 0.56,
        "activate_forecast_confidence_threshold": 0.64,
        "prepare_forecast_confidence_threshold": 0.50,
        "activate_agreement_threshold": 0.62,
        "prepare_agreement_threshold": 0.48,
    }
)

RULE_CONFIG_BY_VIRUS = {
    "SARS-CoV-2": SARS_RULE_CONFIG,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


class RegionalDecisionEngine:
    """Deterministic regional decision rules based on forecast and source quality."""

    def __init__(
        self,
        rule_configs: dict[str, RegionalDecisionRuleConfig] | None = None,
        default_config: RegionalDecisionRuleConfig = DEFAULT_RULE_CONFIG,
    ) -> None:
        self.rule_configs = rule_configs or RULE_CONFIG_BY_VIRUS
        self.default_config = default_config

    def get_config(self, virus_typ: str) -> RegionalDecisionRuleConfig:
        return self.rule_configs.get(virus_typ, self.default_config)

    def evaluate(
        self,
        *,
        virus_typ: str,
        prediction: Mapping[str, Any],
        feature_row: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> RegionalDecision:
        config = self.get_config(virus_typ)
        metadata = metadata or {}
        quality_gate = dict(prediction.get("quality_gate") or {})
        prefixes = PRIMARY_SOURCE_PREFIXES.get(virus_typ, PRIMARY_SOURCE_PREFIXES["default"])

        source_snapshot = self._collect_source_snapshot(prefixes=prefixes, feature_row=feature_row)
        freshness_days = source_snapshot["avg_freshness_days"]
        freshness_score = source_snapshot["freshness_score"]
        revision_risk = source_snapshot["revision_risk"]
        usable_share = source_snapshot["usable_share"]
        coverage_score = source_snapshot["coverage_score"]

        event_probability = _clamp(float(prediction.get("event_probability_calibrated") or 0.0))
        forecast_confidence = self._forecast_confidence_score(
            prediction=prediction,
            metadata=metadata,
            freshness_score=freshness_score,
            usable_share=usable_share,
            coverage_score=coverage_score,
            quality_gate=quality_gate,
            config=config,
        )
        trend_bundle = self._trend_acceleration_bundle(virus_typ=virus_typ, feature_row=feature_row, config=config)
        agreement_bundle = self._agreement_bundle(virus_typ=virus_typ, feature_row=feature_row, config=config)
        revision_safety = _clamp(1.0 - revision_risk)

        components = {
            "event_probability": event_probability,
            "forecast_confidence": forecast_confidence,
            "source_freshness": freshness_score,
            "revision_safety": revision_safety,
            "trend_acceleration": trend_bundle["score"],
            "cross_source_agreement": agreement_bundle["support_score"],
        }
        decision_score = round(
            sum(
                float(config.weights.get(key) or 0.0) * float(value)
                for key, value in components.items()
            ),
            4,
        )

        thresholds = self._thresholds(
            config=config,
            action_threshold=float(prediction.get("action_threshold") or 0.6),
        )
        signal_stage = self._signal_stage(
            decision_score=decision_score,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            freshness_score=freshness_score,
            revision_risk=revision_risk,
            trend_score=trend_bundle["score"],
            agreement_support_score=agreement_bundle["support_score"],
            agreement_signal_count=agreement_bundle["signal_count"],
            thresholds=thresholds,
            config=config,
        )
        stage, policy_overrides = self._policy_stage(
            signal_stage=signal_stage,
            prediction=prediction,
        )

        component_trace = self._component_trace(
            components=components,
            config=config,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
            revision_risk=revision_risk,
            freshness_days=freshness_days,
        )
        reason_trace = self._reason_trace(
            signal_stage=signal_stage,
            stage=stage,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            freshness_score=freshness_score,
            freshness_days=freshness_days,
            revision_risk=revision_risk,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
            thresholds=thresholds,
            policy_overrides=policy_overrides,
            component_trace=component_trace,
            quality_gate=quality_gate,
            config=config,
        )

        explanation_summary = self._explanation_summary(
            bundesland_name=str(prediction.get("bundesland_name") or prediction.get("bundesland") or ""),
            stage=stage,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
        )
        uncertainty_summary = self._uncertainty_summary(
            revision_risk=revision_risk,
            freshness_score=freshness_score,
            agreement_bundle=agreement_bundle,
            quality_gate=quality_gate,
            config=config,
        )

        return RegionalDecision(
            bundesland=str(prediction.get("bundesland") or ""),
            bundesland_name=str(prediction.get("bundesland_name") or prediction.get("bundesland") or ""),
            virus_typ=virus_typ,
            horizon_days=int(prediction.get("horizon_days") or 7),
            signal_stage=signal_stage,
            stage=stage,
            decision_score=decision_score,
            event_probability=round(event_probability, 4),
            forecast_confidence=round(forecast_confidence, 4),
            source_freshness_score=round(freshness_score, 4),
            source_freshness_days=round(freshness_days, 2),
            source_revision_risk=round(revision_risk, 4),
            trend_acceleration_score=round(trend_bundle["score"], 4),
            cross_source_agreement_score=round(agreement_bundle["support_score"], 4),
            cross_source_agreement_direction=str(agreement_bundle["direction"]),
            usable_source_share=round(usable_share, 4),
            source_coverage_score=round(coverage_score, 4),
            explanation_summary=explanation_summary,
            uncertainty_summary=uncertainty_summary,
            components={key: round(float(value), 4) for key, value in components.items()},
            thresholds={key: round(float(value), 4) for key, value in thresholds.items()},
            reason_trace=reason_trace,
            metadata={
                "config_version": config.version,
                "action_threshold": round(float(prediction.get("action_threshold") or 0.6), 4),
                "agreement_signal_count": int(agreement_bundle["signal_count"]),
                "agreement_signals": agreement_bundle["signals"],
                "trend_signals": trend_bundle["signals"],
                "avg_source_freshness_days": round(freshness_days, 2),
                "source_prefixes": list(prefixes),
                "quality_gate_passed": bool(quality_gate.get("overall_passed")),
            },
        )

    @staticmethod
    def _thresholds(
        *,
        config: RegionalDecisionRuleConfig,
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

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _collect_source_snapshot(
        self,
        *,
        prefixes: tuple[str, ...],
        feature_row: Mapping[str, Any],
    ) -> dict[str, Any]:
        freshness_scores: list[float] = []
        freshness_days: list[float] = []
        revision_risks: list[float] = []
        usable_scores: list[float] = []
        coverage_scores: list[float] = []
        prefix_details: list[dict[str, Any]] = []

        for prefix in prefixes:
            freshness = self._safe_float(feature_row.get(f"{prefix}_freshness_days"))
            risk = self._safe_float(feature_row.get(f"{prefix}_revision_risk"))
            usable_confidence = self._safe_float(feature_row.get(f"{prefix}_usable_confidence"))
            coverage_ratio = self._safe_float(feature_row.get(f"{prefix}_coverage_ratio"))
            usable_flag = self._safe_float(feature_row.get(f"{prefix}_usable"))
            if freshness is None and risk is None and usable_confidence is None and coverage_ratio is None:
                continue

            source_id = SOURCE_PREFIX_TO_CONFIG.get(prefix)
            max_staleness = float(
                NOWCAST_SOURCE_CONFIGS[source_id].max_staleness_days
                if source_id in NOWCAST_SOURCE_CONFIGS
                else 14
            )
            freshness_score = _clamp(1.0 - (max(float(freshness or 0.0), 0.0) / max(max_staleness, 1.0)))
            freshness_scores.append(freshness_score)
            freshness_days.append(max(float(freshness or 0.0), 0.0))
            if risk is not None:
                revision_risks.append(_clamp(risk))
            if usable_confidence is not None:
                usable_scores.append(_clamp(usable_confidence))
            elif usable_flag is not None:
                usable_scores.append(_clamp(usable_flag))
            if coverage_ratio is not None:
                coverage_scores.append(_clamp(coverage_ratio))
            prefix_details.append(
                {
                    "prefix": prefix,
                    "freshness_days": round(max(float(freshness or 0.0), 0.0), 2),
                    "freshness_score": round(freshness_score, 4),
                    "revision_risk": round(_clamp(risk or 0.0), 4),
                    "usable_confidence": round(_clamp(usable_confidence or usable_flag or 0.0), 4),
                    "coverage_ratio": round(_clamp(coverage_ratio or 0.0), 4),
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

    def _forecast_confidence_score(
        self,
        *,
        prediction: Mapping[str, Any],
        metadata: Mapping[str, Any],
        freshness_score: float,
        usable_share: float,
        coverage_score: float,
        quality_gate: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
    ) -> float:
        metrics = dict(metadata.get("aggregate_metrics") or {})
        interval = dict(prediction.get("prediction_interval") or {})
        upper = max(float(interval.get("upper") or 0.0), 0.0)
        lower = max(float(interval.get("lower") or 0.0), 0.0)
        predicted = max(float(prediction.get("expected_next_week_incidence") or 0.0), 0.0)
        current = max(float(prediction.get("current_known_incidence") or 0.0), 0.0)
        width = max(upper - lower, 0.0)
        scale = max(predicted, current, 1.0)
        interval_score = _clamp(1.0 - (width / max(2.0 * scale, 1.0)))

        parts = [interval_score]
        if metrics.get("ece") is not None:
            parts.append(_clamp(1.0 - (float(metrics["ece"]) / 0.20)))
        if metrics.get("brier_score") is not None:
            parts.append(_clamp(1.0 - (float(metrics["brier_score"]) / 0.25)))
        if metrics.get("pr_auc") is not None:
            parts.append(_clamp(float(metrics["pr_auc"])))
        parts.append(
            1.0
            if quality_gate.get("overall_passed")
            else float(config.failed_quality_gate_confidence_factor)
        )
        parts.append(_clamp((float(freshness_score) + float(usable_share) + float(coverage_score)) / 3.0))
        return round(sum(parts) / len(parts), 4)

    def _trend_acceleration_bundle(
        self,
        *,
        virus_typ: str,
        feature_row: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
    ) -> dict[str, Any]:
        signals: list[dict[str, Any]] = []
        for label, key in (
            ("wastewater_acceleration", "ww_acceleration7d"),
            ("national_wastewater_acceleration", "national_ww_acceleration7d"),
            ("sars_trends_acceleration", "sars_trends_acceleration_7d"),
        ):
            value = self._safe_float(feature_row.get(key))
            if value is None:
                continue
            signals.append({"signal": label, "key": key, "value": round(float(value), 4)})

        if not signals:
            return {"score": 0.0, "raw": 0.0, "signals": []}

        primary = float(signals[0]["value"])
        secondary = [float(item["value"]) for item in signals[1:]]
        blended = primary if not secondary else (0.7 * primary + 0.3 * (sum(secondary) / len(secondary)))
        score = _clamp(0.5 + (blended / max(float(config.acceleration_reference), 0.1)))
        if virus_typ == "SARS-CoV-2" and secondary:
            score = _clamp(score + 0.05)
        return {
            "score": round(score, 4),
            "raw": round(blended, 4),
            "signals": signals,
        }

    def _agreement_bundle(
        self,
        *,
        virus_typ: str,
        feature_row: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
    ) -> dict[str, Any]:
        keys = TREND_SIGNAL_KEYS.get(virus_typ, TREND_SIGNAL_KEYS["default"])
        directional_signals: list[dict[str, Any]] = []
        positive = 0
        negative = 0
        for label, key in keys:
            value = self._safe_float(feature_row.get(key))
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
        agreement_score = _clamp(dominant / max(active_count, 1))
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

    @staticmethod
    def _signal_stage(
        *,
        decision_score: float,
        event_probability: float,
        forecast_confidence: float,
        freshness_score: float,
        revision_risk: float,
        trend_score: float,
        agreement_support_score: float,
        agreement_signal_count: int,
        thresholds: Mapping[str, float],
        config: RegionalDecisionRuleConfig,
    ) -> str:
        activate_agreement_ok = (
            agreement_signal_count < int(config.min_agreement_signal_count)
            or agreement_support_score >= float(thresholds["activate_agreement"])
        )
        prepare_agreement_ok = (
            agreement_signal_count < int(config.min_agreement_signal_count)
            or agreement_support_score >= float(thresholds["prepare_agreement"])
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
        return "watch"

    @staticmethod
    def _policy_stage(
        *,
        signal_stage: str,
        prediction: Mapping[str, Any],
    ) -> tuple[str, list[str]]:
        overrides: list[str] = []
        activation_policy = str(prediction.get("activation_policy") or "quality_gate")
        quality_gate = dict(prediction.get("quality_gate") or {})
        if activation_policy == "watch_only" and signal_stage != "watch":
            overrides.append("Activation policy 'watch_only' downgrades the operational stage to Watch.")
            return "watch", overrides
        if not quality_gate.get("overall_passed") and signal_stage != "watch":
            overrides.append("Regional quality gate is not passed, so activation stays on Watch.")
            return "watch", overrides
        return signal_stage, overrides

    @staticmethod
    def _component_trace(
        *,
        components: Mapping[str, float],
        config: RegionalDecisionRuleConfig,
        trend_bundle: Mapping[str, Any],
        agreement_bundle: Mapping[str, Any],
        revision_risk: float,
        freshness_days: float,
    ) -> list[DecisionComponentScore]:
        trace: list[DecisionComponentScore] = []
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
                DecisionComponentScore(
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

    @staticmethod
    def _reason_trace(
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
        component_trace: list[DecisionComponentScore],
        quality_gate: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
    ) -> DecisionReasonTrace:
        why: list[str] = []
        uncertainty: list[str] = []

        if signal_stage == "activate":
            why.append(
                f"Event probability {event_probability:.2f} clears the Activate threshold {float(thresholds['activate_probability']):.2f}."
            )
        elif signal_stage == "prepare":
            why.append(
                f"Event probability {event_probability:.2f} clears the Prepare threshold {float(thresholds['prepare_probability']):.2f}, but not all Activate conditions are met."
            )
        else:
            why.append(
                f"Event probability {event_probability:.2f} stays below the rule set needed for Prepare/Activate."
            )

        if forecast_confidence >= float(thresholds["activate_forecast_confidence"]):
            why.append(f"Forecast confidence is strong at {forecast_confidence:.2f}.")
        elif forecast_confidence >= float(thresholds["prepare_forecast_confidence"]):
            why.append(f"Forecast confidence is usable at {forecast_confidence:.2f}.")
        else:
            uncertainty.append(f"Forecast confidence is only {forecast_confidence:.2f}.")

        if freshness_score >= float(thresholds["activate_freshness"]):
            why.append(f"Primary sources are fresh on average ({freshness_days:.1f} days old).")
        elif freshness_score < float(thresholds["prepare_freshness"]):
            uncertainty.append(f"Primary-source freshness is weak ({freshness_days:.1f} days average age).")

        if revision_risk > float(thresholds["prepare_revision_risk_max"]):
            uncertainty.append(f"Revision risk is high at {revision_risk:.2f}.")
        elif revision_risk > float(thresholds["activate_revision_risk_max"]):
            uncertainty.append(f"Revision risk is still material at {revision_risk:.2f}.")

        trend_score = float(trend_bundle.get("score") or 0.0)
        trend_raw = float(trend_bundle.get("raw") or 0.0)
        if trend_score >= float(thresholds["activate_trend"]):
            why.append(f"Recent trend acceleration is supportive ({trend_raw:.2f}).")
        elif trend_score < float(thresholds["prepare_trend"]):
            uncertainty.append(f"Trend acceleration is not yet convincing ({trend_raw:.2f}).")

        agreement_signal_count = int(agreement_bundle.get("signal_count") or 0)
        agreement_score = float(agreement_bundle.get("support_score") or 0.0)
        agreement_direction = str(agreement_bundle.get("direction") or "flat")
        if agreement_signal_count < int(config.min_agreement_signal_count):
            uncertainty.append("Cross-source agreement is low-evidence because fewer than two directional source signals are available.")
        elif agreement_direction == "up" and agreement_score >= float(thresholds["prepare_agreement"]):
            why.append(f"{agreement_signal_count} source trends align upward.")
        else:
            uncertainty.append("Cross-source agreement does not clearly confirm an upward move.")

        if not quality_gate.get("overall_passed"):
            uncertainty.append("Regional forecast quality gate is currently not passed.")
        if stage != signal_stage and not policy_overrides:
            uncertainty.append("Final stage differs from the raw signal stage because of a policy overlay.")

        return DecisionReasonTrace(
            why=why,
            contributing_signals=component_trace[:4],
            uncertainty=uncertainty,
            policy_overrides=policy_overrides,
        )

    @staticmethod
    def _explanation_summary(
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

    @staticmethod
    def _uncertainty_summary(
        *,
        revision_risk: float,
        freshness_score: float,
        agreement_bundle: Mapping[str, Any],
        quality_gate: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
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
