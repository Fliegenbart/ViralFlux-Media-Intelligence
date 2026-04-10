from __future__ import annotations

import unittest
from unittest.mock import ANY, patch

from app.services.ml.regional_trainer import RegionalModelTrainer


class RegionalTrainerRefactorGuardTests(unittest.TestCase):
    @patch("app.services.ml.regional_trainer_backtest.build_backtest_bundle")
    def test_build_backtest_bundle_wrapper_delegates_to_module(self, bundle_mock) -> None:
        bundle_mock.return_value = {"aggregate_metrics": {"pr_auc": 0.61}}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._build_backtest_bundle(
            virus_typ="Influenza A",
            panel="panel-frame",
            feature_columns=["f1", "f2"],
            hierarchy_feature_columns=["h1"],
            ww_only_columns=["ww_1"],
            tau=1.2,
            kappa=0.4,
            action_threshold=0.55,
            horizon_days=7,
            event_config={"name": "resp"},
        )

        self.assertEqual(result, {"aggregate_metrics": {"pr_auc": 0.61}})
        bundle_mock.assert_called_once_with(
            trainer,
            virus_typ="Influenza A",
            panel="panel-frame",
            feature_columns=["f1", "f2"],
            hierarchy_feature_columns=["h1"],
            ww_only_columns=["ww_1"],
            tau=1.2,
            kappa=0.4,
            action_threshold=0.55,
            horizon_days=7,
            event_config={"name": "resp"},
            time_based_panel_splits_fn=ANY,
            quality_gate_from_metrics_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_backtest.aggregate_metrics")
    def test_aggregate_metrics_wrapper_delegates_to_module(self, metrics_mock) -> None:
        metrics_mock.return_value = {"precision_at_top3": 0.5}

        result = RegionalModelTrainer._aggregate_metrics("frame", action_threshold=0.7)

        self.assertEqual(result, {"precision_at_top3": 0.5})
        metrics_mock.assert_called_once_with("frame", action_threshold=0.7)

    @patch("app.services.ml.regional_trainer_backtest.baseline_metrics")
    def test_baseline_metrics_wrapper_delegates_to_module(self, baseline_mock) -> None:
        baseline_mock.return_value = {"persistence": {"pr_auc": 0.41}}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._baseline_metrics("frame", action_threshold=0.65)

        self.assertEqual(result, {"persistence": {"pr_auc": 0.41}})
        baseline_mock.assert_called_once_with(trainer, "frame", action_threshold=0.65)

    @patch("app.services.ml.regional_trainer_backtest.build_backtest_payload")
    def test_build_backtest_payload_wrapper_delegates_to_module(self, payload_mock) -> None:
        payload_mock.return_value = {"ranking": [{"bundesland": "BY"}]}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._build_backtest_payload(
            frame="frame",
            aggregate_metrics={"pr_auc": 0.5},
            baselines={"persistence": {"pr_auc": 0.4}},
            quality_gate={"overall_passed": True},
            tau=1.0,
            kappa=0.3,
            action_threshold=0.55,
            fold_selection_summary=[{"fold": 1}],
        )

        self.assertEqual(result, {"ranking": [{"bundesland": "BY"}]})
        payload_mock.assert_called_once_with(
            trainer,
            frame="frame",
            aggregate_metrics={"pr_auc": 0.5},
            baselines={"persistence": {"pr_auc": 0.4}},
            quality_gate={"overall_passed": True},
            tau=1.0,
            kappa=0.3,
            action_threshold=0.55,
            fold_selection_summary=[{"fold": 1}],
        )

    @patch("app.services.ml.regional_trainer_backtest.activation_mask")
    def test_activation_mask_wrapper_delegates_to_module(self, mask_mock) -> None:
        mask_mock.return_value = [True, False]

        result = RegionalModelTrainer._activation_mask("state-frame", action_threshold=0.6)

        self.assertEqual(result, [True, False])
        mask_mock.assert_called_once_with("state-frame", action_threshold=0.6)

    @patch("app.services.ml.regional_trainer_backtest.state_precision_recall")
    def test_state_precision_recall_wrapper_delegates_to_module(self, metrics_mock) -> None:
        metrics_mock.return_value = (0.75, 0.5)

        result = RegionalModelTrainer._state_precision_recall("state-frame", action_threshold=0.6)

        self.assertEqual(result, (0.75, 0.5))
        metrics_mock.assert_called_once_with("state-frame", action_threshold=0.6)

    @patch("app.services.ml.regional_trainer_hierarchy.hierarchy_reconciled_benchmark_frame")
    def test_hierarchy_reconciled_benchmark_frame_wrapper_delegates_to_module(self, reconcile_mock) -> None:
        reconcile_mock.return_value = {"rows": 3}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._hierarchy_reconciled_benchmark_frame(
            oof_frame="oof-frame",
            source_panel="source-panel",
        )

        self.assertEqual(result, {"rows": 3})
        reconcile_mock.assert_called_once_with(
            trainer,
            oof_frame="oof-frame",
            source_panel="source-panel",
            state_order_from_codes_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_hierarchy.estimate_hierarchy_blend_choice")
    def test_estimate_hierarchy_blend_choice_wrapper_delegates_to_module(self, choice_mock) -> None:
        choice_mock.return_value = {"weight": 0.4, "scope": "same_regime"}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._estimate_hierarchy_blend_choice(
            [{"truth": 10.0}],
            target_as_of_date="2026-03-10",
            target_regime="respiratory_peak",
            target_horizon_days=7,
        )

        self.assertEqual(result, {"weight": 0.4, "scope": "same_regime"})
        choice_mock.assert_called_once_with(
            trainer,
            [{"truth": 10.0}],
            target_as_of_date="2026-03-10",
            target_regime="respiratory_peak",
            target_horizon_days=7,
            min_total_samples=ANY,
            min_regime_samples=ANY,
            weight_grid=ANY,
            blend_epsilon=ANY,
        )

    @patch("app.services.ml.regional_trainer_hierarchy.fit_hierarchy_models")
    def test_fit_hierarchy_models_wrapper_delegates_to_module(self, fit_mock) -> None:
        fit_mock.return_value = ({"cluster": {"median": "reg"}}, {"cluster": "residual_log"})
        trainer = RegionalModelTrainer(db=None)

        result = trainer._fit_hierarchy_models(
            panel="panel-frame",
            feature_columns=["f1"],
            state_feature_columns=["s1"],
            reg_lower="lower-reg",
            reg_median="median-reg",
            reg_upper="upper-reg",
        )

        self.assertEqual(result, ({"cluster": {"median": "reg"}}, {"cluster": "residual_log"}))
        fit_mock.assert_called_once_with(
            trainer,
            panel="panel-frame",
            feature_columns=["f1"],
            state_feature_columns=["s1"],
            reg_lower="lower-reg",
            reg_median="median-reg",
            reg_upper="upper-reg",
            regressor_config=ANY,
        )

    @patch("app.services.ml.regional_trainer_artifacts.build_hierarchy_metadata")
    def test_build_hierarchy_metadata_wrapper_delegates_to_module(self, metadata_mock) -> None:
        metadata_mock.return_value = {"enabled": True, "state_order": ["BY"]}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._build_hierarchy_metadata(
            panel="panel-frame",
            oof_frame="oof-frame",
        )

        self.assertEqual(result, {"enabled": True, "state_order": ["BY"]})
        metadata_mock.assert_called_once_with(
            trainer,
            panel="panel-frame",
            oof_frame="oof-frame",
        )

    @patch("app.services.ml.regional_trainer_artifacts.fit_final_models")
    def test_fit_final_models_wrapper_delegates_to_module(self, final_models_mock) -> None:
        final_models_mock.return_value = {"classifier": "clf", "calibration_mode": "guarded"}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._fit_final_models(
            panel="panel-frame",
            feature_columns=["f1"],
            hierarchy_feature_columns=["h1"],
            oof_frame="oof-frame",
            action_threshold=0.55,
        )

        self.assertEqual(result, {"classifier": "clf", "calibration_mode": "guarded"})
        final_models_mock.assert_called_once_with(
            trainer,
            panel="panel-frame",
            feature_columns=["f1"],
            hierarchy_feature_columns=["h1"],
            oof_frame="oof-frame",
            action_threshold=0.55,
            regressor_config=ANY,
            supported_quantiles=ANY,
            quantile_regressor_config_fn=ANY,
            learned_event_model_cls=ANY,
            calibration_holdout_fraction=ANY,
        )

    @patch("app.services.ml.regional_trainer_artifacts.persist_artifacts")
    def test_persist_artifacts_wrapper_delegates_to_module(self, persist_mock) -> None:
        trainer = RegionalModelTrainer(db=None)

        trainer._persist_artifacts(
            model_dir="model-dir",
            final_artifacts={"classifier": "clf"},
            metadata={"selected_tau": 1.0},
            backtest_payload={"status": "ok"},
            dataset_manifest={"dataset": "v1"},
            point_in_time_manifest={"snapshot": "v1"},
        )

        persist_mock.assert_called_once_with(
            model_dir="model-dir",
            final_artifacts={"classifier": "clf"},
            metadata={"selected_tau": 1.0},
            backtest_payload={"status": "ok"},
            dataset_manifest={"dataset": "v1"},
            point_in_time_manifest={"snapshot": "v1"},
            json_safe_fn=ANY,
            quantile_key_fn=ANY,
            event_definition_version=ANY,
            target_window_days=ANY,
        )
