"""Explicit, audit-ready regional Watch/Prepare/Activate decision rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.ml.nowcast_revision import NOWCAST_SOURCE_CONFIGS
from app.services.ml import regional_decision_engine_reasoning
from app.services.ml import regional_decision_engine_signals
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
            agreement_direction=agreement_bundle["direction"],
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
        explanation_summary_detail = self._explanation_summary_detail(
            bundesland_name=str(prediction.get("bundesland_name") or prediction.get("bundesland") or ""),
            stage=stage,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
            message=explanation_summary,
        )
        uncertainty_summary = self._uncertainty_summary(
            revision_risk=revision_risk,
            freshness_score=freshness_score,
            agreement_bundle=agreement_bundle,
            quality_gate=quality_gate,
            config=config,
        )
        uncertainty_summary_detail = self._uncertainty_summary_detail(
            revision_risk=revision_risk,
            freshness_score=freshness_score,
            agreement_bundle=agreement_bundle,
            quality_gate=quality_gate,
            config=config,
            message=uncertainty_summary,
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
            explanation_summary_detail=explanation_summary_detail,
            uncertainty_summary=uncertainty_summary,
            uncertainty_summary_detail=uncertainty_summary_detail,
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
        return regional_decision_engine_signals.thresholds(
            config=config,
            action_threshold=action_threshold,
        )

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        return regional_decision_engine_signals.safe_float(value)

    def _collect_source_snapshot(
        self,
        *,
        prefixes: tuple[str, ...],
        feature_row: Mapping[str, Any],
    ) -> dict[str, Any]:
        return regional_decision_engine_signals.collect_source_snapshot(
            self,
            prefixes=prefixes,
            feature_row=feature_row,
            source_prefix_to_config=SOURCE_PREFIX_TO_CONFIG,
            nowcast_source_configs=NOWCAST_SOURCE_CONFIGS,
            clamp_fn=_clamp,
        )

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
        return regional_decision_engine_signals.forecast_confidence_score(
            prediction=prediction,
            metadata=metadata,
            freshness_score=freshness_score,
            usable_share=usable_share,
            coverage_score=coverage_score,
            quality_gate=quality_gate,
            config=config,
            clamp_fn=_clamp,
        )

    def _trend_acceleration_bundle(
        self,
        *,
        virus_typ: str,
        feature_row: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
    ) -> dict[str, Any]:
        return regional_decision_engine_signals.trend_acceleration_bundle(
            self,
            virus_typ=virus_typ,
            feature_row=feature_row,
            config=config,
            clamp_fn=_clamp,
        )

    def _agreement_bundle(
        self,
        *,
        virus_typ: str,
        feature_row: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
    ) -> dict[str, Any]:
        return regional_decision_engine_signals.agreement_bundle(
            self,
            virus_typ=virus_typ,
            feature_row=feature_row,
            config=config,
            trend_signal_keys=TREND_SIGNAL_KEYS,
            clamp_fn=_clamp,
        )

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
        agreement_direction: str,
        thresholds: Mapping[str, float],
        config: RegionalDecisionRuleConfig,
    ) -> str:
        return regional_decision_engine_signals.signal_stage(
            decision_score=decision_score,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            freshness_score=freshness_score,
            revision_risk=revision_risk,
            trend_score=trend_score,
            agreement_support_score=agreement_support_score,
            agreement_signal_count=agreement_signal_count,
            agreement_direction=agreement_direction,
            thresholds=thresholds,
            config=config,
        )

    @staticmethod
    def _policy_stage(
        *,
        signal_stage: str,
        prediction: Mapping[str, Any],
    ) -> tuple[str, list[str]]:
        return regional_decision_engine_signals.policy_stage(
            signal_stage=signal_stage,
            prediction=prediction,
        )

    @staticmethod
    def _reason_detail(code: str, message: str, **params: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": code, "message": message}
        if params:
            payload["params"] = params
        return payload

    @classmethod
    def _policy_override_detail(cls, message: str) -> dict[str, Any]:
        normalized = message.strip().lower()
        if "watch_only" in normalized:
            return cls._reason_detail(
                "policy_override_watch_only",
                message,
                final_stage="prepare",
            )
        if "quality gate" in normalized:
            return cls._reason_detail(
                "policy_override_quality_gate",
                message,
                final_stage="prepare",
            )
        return cls._reason_detail("policy_override", message)

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
        return regional_decision_engine_reasoning.component_trace(
            components=components,
            config=config,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
            revision_risk=revision_risk,
            freshness_days=freshness_days,
            decision_component_score_cls=DecisionComponentScore,
        )

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
        return regional_decision_engine_reasoning.reason_trace(
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
            decision_reason_trace_cls=DecisionReasonTrace,
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
        return regional_decision_engine_reasoning.explanation_summary(
            bundesland_name=bundesland_name,
            stage=stage,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
        )

    @classmethod
    def _explanation_summary_detail(
        cls,
        *,
        bundesland_name: str,
        stage: str,
        event_probability: float,
        forecast_confidence: float,
        trend_bundle: Mapping[str, Any],
        agreement_bundle: Mapping[str, Any],
        message: str,
    ) -> dict[str, Any]:
        return regional_decision_engine_reasoning.explanation_summary_detail(
            bundesland_name=bundesland_name,
            stage=stage,
            event_probability=event_probability,
            forecast_confidence=forecast_confidence,
            trend_bundle=trend_bundle,
            agreement_bundle=agreement_bundle,
            message=message,
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
        return regional_decision_engine_reasoning.uncertainty_summary(
            revision_risk=revision_risk,
            freshness_score=freshness_score,
            agreement_bundle=agreement_bundle,
            quality_gate=quality_gate,
            config=config,
        )

    @classmethod
    def _uncertainty_summary_detail(
        cls,
        *,
        revision_risk: float,
        freshness_score: float,
        agreement_bundle: Mapping[str, Any],
        quality_gate: Mapping[str, Any],
        config: RegionalDecisionRuleConfig,
        message: str,
    ) -> dict[str, Any]:
        return regional_decision_engine_reasoning.uncertainty_summary_detail(
            revision_risk=revision_risk,
            freshness_score=freshness_score,
            agreement_bundle=agreement_bundle,
            quality_gate=quality_gate,
            config=config,
            message=message,
        )
