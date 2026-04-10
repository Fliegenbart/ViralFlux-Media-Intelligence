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
