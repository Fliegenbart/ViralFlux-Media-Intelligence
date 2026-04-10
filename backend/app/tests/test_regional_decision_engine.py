import unittest
from unittest.mock import patch

import app.services.ml.regional_decision_engine as decision_module
from app.services.ml.regional_decision_engine import DEFAULT_RULE_CONFIG, RegionalDecisionEngine


class RegionalDecisionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RegionalDecisionEngine()

    @staticmethod
    def _prediction(
        *,
        event_probability: float = 0.82,
        lower: float = 24.0,
        upper: float = 32.0,
        predicted: float = 28.0,
        current: float = 10.0,
        quality_gate_passed: bool = True,
        activation_policy: str = "quality_gate",
        action_threshold: float = 0.6,
        horizon_days: int = 7,
    ) -> dict:
        return {
            "bundesland": "BY",
            "bundesland_name": "Bayern",
            "event_probability_calibrated": event_probability,
            "prediction_interval": {"lower": lower, "upper": upper},
            "expected_next_week_incidence": predicted,
            "current_known_incidence": current,
            "quality_gate": {
                "overall_passed": quality_gate_passed,
                "forecast_readiness": "GO" if quality_gate_passed else "WATCH",
            },
            "activation_policy": activation_policy,
            "action_threshold": action_threshold,
            "horizon_days": horizon_days,
        }

    @staticmethod
    def _metadata(
        *,
        ece: float = 0.05,
        brier_score: float = 0.09,
        pr_auc: float = 0.71,
    ) -> dict:
        return {
            "aggregate_metrics": {
                "ece": ece,
                "brier_score": brier_score,
                "pr_auc": pr_auc,
            }
        }

    @staticmethod
    def _feature_row(
        *,
        trend_raw: float = 0.16,
        secondary_trend_raw: float = 0.10,
        signal_value: float = 0.22,
        freshness_days: float = 1.0,
        revision_risk: float = 0.08,
        usable_confidence: float = 0.94,
        coverage_ratio: float = 0.95,
    ) -> dict:
        feature_row = {
            "ww_acceleration7d": trend_raw,
            "national_ww_acceleration7d": secondary_trend_raw,
            "survstat_momentum_2w": signal_value,
            "grippeweb_are_momentum_1w": signal_value,
            "grippeweb_ili_momentum_1w": signal_value,
            "ifsg_influenza_momentum_1w": signal_value,
        }
        for prefix in (
            "ww_level",
            "survstat_current_incidence",
            "grippeweb_are",
            "grippeweb_ili",
            "ifsg_influenza",
        ):
            feature_row[f"{prefix}_freshness_days"] = freshness_days
            feature_row[f"{prefix}_revision_risk"] = revision_risk
            feature_row[f"{prefix}_usable_confidence"] = usable_confidence
            feature_row[f"{prefix}_coverage_ratio"] = coverage_ratio
        return feature_row

    def test_evaluate_assigns_activate_for_strong_signal_bundle(self) -> None:
        decision = self.engine.evaluate(
            virus_typ="Influenza A",
            prediction=self._prediction(),
            feature_row=self._feature_row(),
            metadata=self._metadata(),
        )

        self.assertEqual(decision.signal_stage, "activate")
        self.assertEqual(decision.stage, "activate")
        self.assertGreaterEqual(decision.decision_score, DEFAULT_RULE_CONFIG.activate_score_threshold)
        self.assertTrue(decision.reason_trace.why)
        self.assertTrue(decision.reason_trace.why_details)
        self.assertEqual(decision.reason_trace.why_details[0]["code"], "event_probability_activate_threshold")
        self.assertEqual(decision.reason_trace.policy_overrides, [])
        self.assertEqual(decision.uncertainty_summary, "Residual uncertainty is currently limited.")
        self.assertEqual(decision.explanation_summary_detail["code"], "decision_summary")
        self.assertEqual(decision.uncertainty_summary_detail["code"], "uncertainty_summary")

    def test_evaluate_assigns_prepare_for_mid_strength_signal_bundle(self) -> None:
        decision = self.engine.evaluate(
            virus_typ="Influenza A",
            prediction=self._prediction(
                event_probability=0.57,
                lower=18.0,
                upper=24.0,
                predicted=21.0,
            ),
            feature_row=self._feature_row(
                trend_raw=0.05,
                secondary_trend_raw=0.03,
                signal_value=0.10,
            ),
            metadata=self._metadata(
                ece=0.06,
                brier_score=0.11,
                pr_auc=0.64,
            ),
        )

        self.assertEqual(decision.signal_stage, "prepare")
        self.assertEqual(decision.stage, "prepare")
        self.assertGreaterEqual(decision.decision_score, DEFAULT_RULE_CONFIG.prepare_score_threshold)
        self.assertLess(decision.event_probability, decision.thresholds["activate_probability"])

    def test_evaluate_marks_sparse_low_confidence_region_as_watch(self) -> None:
        decision = self.engine.evaluate(
            virus_typ="Influenza A",
            prediction=self._prediction(
                event_probability=0.61,
                lower=5.0,
                upper=17.0,
                predicted=8.0,
                current=6.0,
            ),
            feature_row={
                "ww_acceleration7d": 0.0,
                "national_ww_acceleration7d": 0.0,
                "survstat_momentum_2w": 0.0,
            },
            metadata={"aggregate_metrics": {}},
        )

        self.assertEqual(decision.signal_stage, "watch")
        self.assertEqual(decision.stage, "watch")
        self.assertLess(decision.forecast_confidence, DEFAULT_RULE_CONFIG.prepare_forecast_confidence_threshold)
        self.assertTrue(decision.reason_trace.uncertainty)
        self.assertIn("thin agreement evidence", decision.uncertainty_summary)

    def test_quality_gate_downgrades_activate_signal_to_watch(self) -> None:
        decision = self.engine.evaluate(
            virus_typ="Influenza A",
            prediction=self._prediction(quality_gate_passed=False),
            feature_row=self._feature_row(),
            metadata=self._metadata(),
        )

        self.assertEqual(decision.signal_stage, "activate")
        self.assertEqual(decision.stage, "watch")
        self.assertTrue(decision.reason_trace.policy_overrides)
        self.assertIn("quality gate", decision.reason_trace.policy_overrides[0].lower())
        self.assertIn("quality gate not passed", decision.uncertainty_summary)

    def test_watch_only_policy_downgrades_final_stage_without_hiding_signal_stage(self) -> None:
        decision = self.engine.evaluate(
            virus_typ="Influenza A",
            prediction=self._prediction(activation_policy="watch_only"),
            feature_row=self._feature_row(),
            metadata=self._metadata(),
        )

        self.assertEqual(decision.signal_stage, "activate")
        self.assertEqual(decision.stage, "watch")
        self.assertIn("watch_only", decision.reason_trace.policy_overrides[0])
        self.assertTrue(decision.reason_trace.why)

    def test_reason_trace_and_uncertainty_summary_are_present_for_mixed_case(self) -> None:
        decision = self.engine.evaluate(
            virus_typ="Influenza A",
            prediction=self._prediction(
                event_probability=0.52,
                lower=14.0,
                upper=24.0,
                predicted=19.0,
            ),
            feature_row=self._feature_row(
                trend_raw=0.04,
                secondary_trend_raw=0.01,
                signal_value=-0.08,
                freshness_days=4.0,
                revision_risk=0.46,
                usable_confidence=0.72,
                coverage_ratio=0.70,
            ),
            metadata=self._metadata(
                ece=0.08,
                brier_score=0.14,
                pr_auc=0.58,
            ),
        )

        self.assertTrue(decision.reason_trace.why)
        self.assertTrue(decision.reason_trace.uncertainty)
        self.assertTrue(decision.reason_trace.why_details)
        self.assertTrue(decision.reason_trace.uncertainty_details)
        self.assertGreaterEqual(len(decision.reason_trace.contributing_signals), 1)
        self.assertTrue(decision.uncertainty_summary.startswith("Remaining uncertainty:"))

    def test_signal_stage_threshold_boundaries_are_inclusive(self) -> None:
        config = self.engine.get_config("Influenza A")
        thresholds = self.engine._thresholds(config=config, action_threshold=0.6)

        activate_stage = self.engine._signal_stage(
            decision_score=thresholds["activate_score"],
            event_probability=thresholds["activate_probability"],
            forecast_confidence=thresholds["activate_forecast_confidence"],
            freshness_score=thresholds["activate_freshness"],
            revision_risk=thresholds["activate_revision_risk_max"],
            trend_score=thresholds["activate_trend"],
            agreement_support_score=thresholds["activate_agreement"],
            agreement_signal_count=config.min_agreement_signal_count,
            thresholds=thresholds,
            config=config,
        )
        prepare_stage = self.engine._signal_stage(
            decision_score=thresholds["prepare_score"],
            event_probability=thresholds["prepare_probability"],
            forecast_confidence=thresholds["prepare_forecast_confidence"],
            freshness_score=thresholds["prepare_freshness"],
            revision_risk=thresholds["prepare_revision_risk_max"],
            trend_score=thresholds["prepare_trend"],
            agreement_support_score=thresholds["prepare_agreement"],
            agreement_signal_count=config.min_agreement_signal_count,
            thresholds=thresholds,
            config=config,
        )
        watch_stage = self.engine._signal_stage(
            decision_score=thresholds["prepare_score"],
            event_probability=thresholds["prepare_probability"] - 0.0001,
            forecast_confidence=thresholds["prepare_forecast_confidence"],
            freshness_score=thresholds["prepare_freshness"],
            revision_risk=thresholds["prepare_revision_risk_max"],
            trend_score=thresholds["prepare_trend"],
            agreement_support_score=thresholds["prepare_agreement"],
            agreement_signal_count=config.min_agreement_signal_count,
            thresholds=thresholds,
            config=config,
        )

        self.assertEqual(activate_stage, "activate")
        self.assertEqual(prepare_stage, "prepare")
        self.assertEqual(watch_stage, "watch")

    def test_sars_uses_stricter_virus_specific_threshold_config(self) -> None:
        default_config = self.engine.get_config("Influenza A")
        sars_config = self.engine.get_config("SARS-CoV-2")

        self.assertEqual(sars_config.version, "regional_decision_sars_v1")
        self.assertGreater(sars_config.activate_probability_threshold, default_config.activate_probability_threshold)
        self.assertGreater(sars_config.activate_score_threshold, default_config.activate_score_threshold)

    def test_component_trace_wrapper_delegates_to_module(self) -> None:
        sentinel = ["trace"]

        with patch(
            "app.services.ml.regional_decision_engine_reasoning.component_trace",
            return_value=sentinel,
        ) as mocked:
            result = self.engine._component_trace(
                components={"event_probability": 0.8},
                config=DEFAULT_RULE_CONFIG,
                trend_bundle={"signals": []},
                agreement_bundle={"direction": "up"},
                revision_risk=0.1,
                freshness_days=1.0,
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            components={"event_probability": 0.8},
            config=DEFAULT_RULE_CONFIG,
            trend_bundle={"signals": []},
            agreement_bundle={"direction": "up"},
            revision_risk=0.1,
            freshness_days=1.0,
            decision_component_score_cls=decision_module.DecisionComponentScore,
        )

    def test_reason_trace_wrapper_delegates_to_module(self) -> None:
        sentinel = object()

        with patch(
            "app.services.ml.regional_decision_engine_reasoning.reason_trace",
            return_value=sentinel,
        ) as mocked:
            result = self.engine._reason_trace(
                signal_stage="activate",
                stage="activate",
                event_probability=0.8,
                forecast_confidence=0.7,
                freshness_score=0.7,
                freshness_days=1.0,
                revision_risk=0.1,
                trend_bundle={"score": 0.7, "raw": 0.2},
                agreement_bundle={"support_score": 0.7, "signal_count": 2, "direction": "up"},
                thresholds={"activate_probability": 0.65, "activate_forecast_confidence": 0.62, "activate_freshness": 0.58, "prepare_freshness": 0.42, "prepare_revision_risk_max": 0.70, "activate_revision_risk_max": 0.45, "activate_trend": 0.58, "prepare_trend": 0.45, "prepare_agreement": 0.45},
                policy_overrides=[],
                component_trace=[],
                quality_gate={"overall_passed": True},
                config=DEFAULT_RULE_CONFIG,
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            signal_stage="activate",
            stage="activate",
            event_probability=0.8,
            forecast_confidence=0.7,
            freshness_score=0.7,
            freshness_days=1.0,
            revision_risk=0.1,
            trend_bundle={"score": 0.7, "raw": 0.2},
            agreement_bundle={"support_score": 0.7, "signal_count": 2, "direction": "up"},
            thresholds={"activate_probability": 0.65, "activate_forecast_confidence": 0.62, "activate_freshness": 0.58, "prepare_freshness": 0.42, "prepare_revision_risk_max": 0.70, "activate_revision_risk_max": 0.45, "activate_trend": 0.58, "prepare_trend": 0.45, "prepare_agreement": 0.45},
            policy_overrides=[],
            component_trace=[],
            quality_gate={"overall_passed": True},
            config=DEFAULT_RULE_CONFIG,
            decision_reason_trace_cls=decision_module.DecisionReasonTrace,
        )

    def test_explanation_summary_wrapper_delegates_to_module(self) -> None:
        with patch(
            "app.services.ml.regional_decision_engine_reasoning.explanation_summary",
            return_value="summary",
        ) as mocked:
            result = self.engine._explanation_summary(
                bundesland_name="Bayern",
                stage="activate",
                event_probability=0.8,
                forecast_confidence=0.7,
                trend_bundle={"raw": 0.2},
                agreement_bundle={"direction": "up"},
            )

        self.assertEqual(result, "summary")
        mocked.assert_called_once_with(
            bundesland_name="Bayern",
            stage="activate",
            event_probability=0.8,
            forecast_confidence=0.7,
            trend_bundle={"raw": 0.2},
            agreement_bundle={"direction": "up"},
        )

    def test_uncertainty_summary_wrapper_delegates_to_module(self) -> None:
        with patch(
            "app.services.ml.regional_decision_engine_reasoning.uncertainty_summary",
            return_value="uncertain",
        ) as mocked:
            result = self.engine._uncertainty_summary(
                revision_risk=0.3,
                freshness_score=0.5,
                agreement_bundle={"signal_count": 1, "direction": "flat"},
                quality_gate={"overall_passed": False},
                config=DEFAULT_RULE_CONFIG,
            )

        self.assertEqual(result, "uncertain")
        mocked.assert_called_once_with(
            revision_risk=0.3,
            freshness_score=0.5,
            agreement_bundle={"signal_count": 1, "direction": "flat"},
            quality_gate={"overall_passed": False},
            config=DEFAULT_RULE_CONFIG,
        )

    def test_collect_source_snapshot_wrapper_delegates_to_module(self) -> None:
        sentinel = {"freshness_score": 0.8}

        with patch(
            "app.services.ml.regional_decision_engine_signals.collect_source_snapshot",
            return_value=sentinel,
        ) as mocked:
            result = self.engine._collect_source_snapshot(
                prefixes=("ww_level",),
                feature_row={"ww_level_freshness_days": 1.0},
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            self.engine,
            prefixes=("ww_level",),
            feature_row={"ww_level_freshness_days": 1.0},
            source_prefix_to_config=decision_module.SOURCE_PREFIX_TO_CONFIG,
            nowcast_source_configs=decision_module.NOWCAST_SOURCE_CONFIGS,
            clamp_fn=decision_module._clamp,
        )

    def test_forecast_confidence_score_wrapper_delegates_to_module(self) -> None:
        with patch(
            "app.services.ml.regional_decision_engine_signals.forecast_confidence_score",
            return_value=0.77,
        ) as mocked:
            result = self.engine._forecast_confidence_score(
                prediction=self._prediction(),
                metadata=self._metadata(),
                freshness_score=0.8,
                usable_share=0.9,
                coverage_score=0.95,
                quality_gate={"overall_passed": True},
                config=DEFAULT_RULE_CONFIG,
            )

        self.assertEqual(result, 0.77)
        mocked.assert_called_once_with(
            prediction=self._prediction(),
            metadata=self._metadata(),
            freshness_score=0.8,
            usable_share=0.9,
            coverage_score=0.95,
            quality_gate={"overall_passed": True},
            config=DEFAULT_RULE_CONFIG,
            clamp_fn=decision_module._clamp,
        )

    def test_signal_stage_wrapper_delegates_to_module(self) -> None:
        with patch(
            "app.services.ml.regional_decision_engine_signals.signal_stage",
            return_value="prepare",
        ) as mocked:
            result = self.engine._signal_stage(
                decision_score=0.6,
                event_probability=0.6,
                forecast_confidence=0.6,
                freshness_score=0.6,
                revision_risk=0.2,
                trend_score=0.5,
                agreement_support_score=0.6,
                agreement_signal_count=2,
                thresholds={"prepare_score": 0.5, "prepare_probability": 0.5, "prepare_forecast_confidence": 0.48, "prepare_freshness": 0.42, "prepare_revision_risk_max": 0.70, "prepare_trend": 0.45, "prepare_agreement": 0.45, "activate_score": 0.72, "activate_probability": 0.65, "activate_forecast_confidence": 0.62, "activate_freshness": 0.58, "activate_revision_risk_max": 0.45, "activate_trend": 0.58, "activate_agreement": 0.60},
                config=DEFAULT_RULE_CONFIG,
            )

        self.assertEqual(result, "prepare")
        mocked.assert_called_once_with(
            decision_score=0.6,
            event_probability=0.6,
            forecast_confidence=0.6,
            freshness_score=0.6,
            revision_risk=0.2,
            trend_score=0.5,
            agreement_support_score=0.6,
            agreement_signal_count=2,
            thresholds={"prepare_score": 0.5, "prepare_probability": 0.5, "prepare_forecast_confidence": 0.48, "prepare_freshness": 0.42, "prepare_revision_risk_max": 0.70, "prepare_trend": 0.45, "prepare_agreement": 0.45, "activate_score": 0.72, "activate_probability": 0.65, "activate_forecast_confidence": 0.62, "activate_freshness": 0.58, "activate_revision_risk_max": 0.45, "activate_trend": 0.58, "activate_agreement": 0.60},
            config=DEFAULT_RULE_CONFIG,
        )

    def test_policy_stage_wrapper_delegates_to_module(self) -> None:
        sentinel = ("watch", ["forced"])

        with patch(
            "app.services.ml.regional_decision_engine_signals.policy_stage",
            return_value=sentinel,
        ) as mocked:
            result = self.engine._policy_stage(
                signal_stage="activate",
                prediction=self._prediction(activation_policy="watch_only"),
            )

        self.assertEqual(result, sentinel)
        mocked.assert_called_once_with(
            signal_stage="activate",
            prediction=self._prediction(activation_policy="watch_only"),
        )


if __name__ == "__main__":
    unittest.main()
