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

    @patch("app.services.ml.regional_trainer_training.train_single_horizon")
    def test_train_single_horizon_wrapper_delegates_to_module(self, train_mock) -> None:
        train_mock.return_value = {"status": "success", "trained": 16}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._train_single_horizon(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=True,
            horizon_days=7,
            weather_forecast_vintage_mode="matching_as_of",
            weather_vintage_comparison=True,
        )

        self.assertEqual(result, {"status": "success", "trained": 16})
        train_mock.assert_called_once_with(
            trainer,
            virus_typ="Influenza A",
            lookback_days=900,
            persist=True,
            horizon_days=7,
            weather_forecast_vintage_mode="matching_as_of",
            weather_vintage_comparison=True,
            target_window_for_horizon_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            regional_horizon_support_status_fn=ANY,
            supported_forecast_horizons=ANY,
            canonical_forecast_quantiles=ANY,
            default_metric_semantics_version=ANY,
            default_promotion_min_sample_count=ANY,
            event_definition_version=ANY,
            all_bundeslaender=ANY,
            normalize_weather_forecast_vintage_mode_fn=ANY,
            regional_model_artifact_dir_fn=ANY,
            json_safe_fn=ANY,
            utc_now_fn=ANY,
            logger=ANY,
            traceback_module=ANY,
        )

    @patch("app.services.ml.regional_trainer_training.training_error_payload")
    def test_training_error_payload_wrapper_delegates_to_module(self, error_mock) -> None:
        error_mock.return_value = {"status": "error", "error_type": "ValueError"}

        result = RegionalModelTrainer._training_error_payload(
            virus_typ="Influenza A",
            horizon_days=7,
            exc=ValueError("kaputt"),
            lookback_days=900,
        )

        self.assertEqual(result, {"status": "error", "error_type": "ValueError"})
        error_mock.assert_called_once_with(
            virus_typ="Influenza A",
            horizon_days=7,
            exc=ANY,
            lookback_days=900,
            target_window_for_horizon_fn=ANY,
            all_bundeslaender=ANY,
            traceback_module=ANY,
        )

    @patch("app.services.ml.regional_trainer_rollout.weather_vintage_metrics_delta")
    def test_weather_vintage_metrics_delta_wrapper_delegates_to_module(self, delta_mock) -> None:
        delta_mock.return_value = {"pr_auc": 0.05}

        result = RegionalModelTrainer._weather_vintage_metrics_delta(
            {"pr_auc": 0.2},
            {"pr_auc": 0.25},
        )

        self.assertEqual(result, {"pr_auc": 0.05})
        delta_mock.assert_called_once_with({"pr_auc": 0.2}, {"pr_auc": 0.25})

    @patch("app.services.ml.regional_trainer_rollout.weather_vintage_mode_summary")
    def test_weather_vintage_mode_summary_wrapper_delegates_to_module(self, summary_mock) -> None:
        summary_mock.return_value = {"weather_forecast_vintage_mode": "matching_as_of"}

        result = RegionalModelTrainer._weather_vintage_mode_summary(
            weather_forecast_vintage_mode="matching_as_of",
            dataset_manifest={"rows": 10},
            backtest_bundle={"aggregate_metrics": {}},
            selection={"tau": 1.0},
            calibration_mode="raw_passthrough",
        )

        self.assertEqual(result, {"weather_forecast_vintage_mode": "matching_as_of"})
        summary_mock.assert_called_once_with(
            weather_forecast_vintage_mode="matching_as_of",
            dataset_manifest={"rows": 10},
            backtest_bundle={"aggregate_metrics": {}},
            selection={"tau": 1.0},
            calibration_mode="raw_passthrough",
            json_safe_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_rollout.build_weather_vintage_comparison")
    def test_build_weather_vintage_comparison_wrapper_delegates_to_module(self, comparison_mock) -> None:
        comparison_mock.return_value = {"comparison_status": "ok"}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._build_weather_vintage_comparison(
            virus_typ="Influenza A",
            lookback_days=900,
            horizon_days=7,
            primary_summary={"weather_forecast_vintage_mode": "disabled"},
            event_config={"name": "resp"},
        )

        self.assertEqual(result, {"comparison_status": "ok"})
        comparison_mock.assert_called_once_with(
            trainer,
            virus_typ="Influenza A",
            lookback_days=900,
            horizon_days=7,
            primary_summary={"weather_forecast_vintage_mode": "disabled"},
            event_config={"name": "resp"},
            normalize_weather_forecast_vintage_mode_fn=ANY,
            weather_forecast_vintage_run_timestamp_v1=ANY,
            weather_forecast_vintage_disabled=ANY,
            target_window_for_horizon_fn=ANY,
            json_safe_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_rollout.rollout_metadata")
    def test_rollout_metadata_wrapper_delegates_to_module(self, rollout_mock) -> None:
        rollout_mock.return_value = {"rollout_mode": "shadow"}
        trainer = RegionalModelTrainer(db=None)

        result = trainer._rollout_metadata(
            virus_typ="SARS-CoV-2",
            horizon_days=7,
            aggregate_metrics={"pr_auc": 0.3},
            baseline_metrics={"persistence": {}},
            previous_artifact={"metadata": {}},
        )

        self.assertEqual(result, {"rollout_mode": "shadow"})
        rollout_mock.assert_called_once_with(
            virus_typ="SARS-CoV-2",
            horizon_days=7,
            aggregate_metrics={"pr_auc": 0.3},
            baseline_metrics={"persistence": {}},
            previous_artifact={"metadata": {}},
            rollout_mode_for_virus_fn=ANY,
            activation_policy_for_virus_fn=ANY,
            signal_bundle_version_for_virus_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_orchestration.train_all_regions")
    def test_train_all_regions_wrapper_delegates_to_module(self, train_mock) -> None:
        train_mock.return_value = {"status": "success", "trained": 16}
        trainer = RegionalModelTrainer(db=None)

        result = trainer.train_all_regions(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=False,
            horizon_days=7,
            horizon_days_list=[7, 14],
            weather_forecast_vintage_mode="matching_as_of",
            weather_vintage_comparison=True,
        )

        self.assertEqual(result, {"status": "success", "trained": 16})
        train_mock.assert_called_once_with(
            trainer,
            virus_typ="Influenza A",
            lookback_days=900,
            persist=False,
            horizon_days=7,
            horizon_days_list=[7, 14],
            weather_forecast_vintage_mode="matching_as_of",
            weather_vintage_comparison=True,
        )

    @patch("app.services.ml.regional_trainer_orchestration.train_all_viruses_all_regions")
    def test_train_all_viruses_wrapper_delegates_to_module(self, train_mock) -> None:
        train_mock.return_value = {"Influenza A": {"trained": 16}}
        trainer = RegionalModelTrainer(db=None)

        result = trainer.train_all_viruses_all_regions(
            lookback_days=1200,
            horizon_days=14,
            weather_forecast_vintage_mode="disabled",
            weather_vintage_comparison=True,
        )

        self.assertEqual(result, {"Influenza A": {"trained": 16}})
        train_mock.assert_called_once_with(
            trainer,
            lookback_days=1200,
            horizon_days=14,
            weather_forecast_vintage_mode="disabled",
            weather_vintage_comparison=True,
            supported_virus_types=ANY,
        )

    @patch("app.services.ml.regional_trainer_orchestration.train_selected_viruses_all_regions")
    def test_train_selected_viruses_wrapper_delegates_to_module(self, train_mock) -> None:
        train_mock.return_value = {"Influenza A": {"trained": 16}}
        trainer = RegionalModelTrainer(db=None)

        result = trainer.train_selected_viruses_all_regions(
            virus_types=["Influenza A", "RSV A"],
            lookback_days=1000,
            horizon_days=7,
            horizon_days_list=[7],
            weather_forecast_vintage_mode="matching_as_of",
            weather_vintage_comparison=False,
        )

        self.assertEqual(result, {"Influenza A": {"trained": 16}})
        train_mock.assert_called_once_with(
            trainer,
            virus_types=["Influenza A", "RSV A"],
            lookback_days=1000,
            horizon_days=7,
            horizon_days_list=[7],
            weather_forecast_vintage_mode="matching_as_of",
            weather_vintage_comparison=False,
        )

    @patch("app.services.ml.regional_trainer_orchestration.load_artifacts")
    def test_load_artifacts_wrapper_delegates_to_module(self, load_mock) -> None:
        load_mock.return_value = {"metadata": {"horizon_days": 7}}
        trainer = RegionalModelTrainer(db=None)

        result = trainer.load_artifacts("Influenza A", horizon_days=7)

        self.assertEqual(result, {"metadata": {"horizon_days": 7}})
        load_mock.assert_called_once_with(
            trainer,
            virus_typ="Influenza A",
            horizon_days=7,
            ensure_supported_horizon_fn=ANY,
            regional_model_artifact_dir_fn=ANY,
            target_window_for_horizon_fn=ANY,
            supported_forecast_horizons=ANY,
            training_only_panel_columns=ANY,
            virus_slug_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_orchestration.artifact_payload_from_dir")
    def test_artifact_payload_from_dir_wrapper_delegates_to_module(self, payload_mock) -> None:
        payload_mock.return_value = {"metadata": {"trained_at": "2026-04-10T12:00:00"}}

        result = RegionalModelTrainer._artifact_payload_from_dir("model-dir")

        self.assertEqual(result, {"metadata": {"trained_at": "2026-04-10T12:00:00"}})
        payload_mock.assert_called_once_with("model-dir", json_module=ANY)

    @patch("app.services.ml.regional_trainer_calibration.calibration_guard_metrics")
    def test_calibration_guard_metrics_wrapper_delegates_to_module(self, metrics_mock) -> None:
        metrics_mock.return_value = {"brier_score": 0.12, "ece": 0.03}

        result = RegionalModelTrainer._calibration_guard_metrics(
            as_of_dates=["2026-04-01", "2026-04-02"],
            labels=[0, 1],
            probabilities=[0.2, 0.8],
            action_threshold=0.55,
        )

        self.assertEqual(result, {"brier_score": 0.12, "ece": 0.03})
        metrics_mock.assert_called_once_with(
            as_of_dates=["2026-04-01", "2026-04-02"],
            labels=[0, 1],
            probabilities=[0.2, 0.8],
            action_threshold=0.55,
            apply_calibration_fn=ANY,
            pd_module=ANY,
            np_module=ANY,
            brier_score_safe_fn=ANY,
            compute_ece_fn=ANY,
            precision_at_k_fn=ANY,
            activation_false_positive_rate_fn=ANY,
        )

    @patch("app.services.ml.regional_trainer_calibration.select_guarded_calibration")
    def test_select_guarded_calibration_wrapper_delegates_to_module(self, calibration_mock) -> None:
        calibration_mock.return_value = ("calibration-token", "isotonic_guarded")
        trainer = RegionalModelTrainer(db=None)

        result = trainer._select_guarded_calibration(
            calibration_frame="calibration-frame",
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
            min_recall_for_threshold=0.4,
            label_col="event_label",
            date_col="as_of_date",
        )

        self.assertEqual(result, ("calibration-token", "isotonic_guarded"))
        calibration_mock.assert_called_once_with(
            trainer,
            calibration_frame="calibration-frame",
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
            min_recall_for_threshold=0.4,
            label_col="event_label",
            date_col="as_of_date",
            calibration_guard_epsilon=ANY,
            choose_action_threshold_fn=ANY,
        )
