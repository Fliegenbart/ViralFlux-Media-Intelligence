import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.registry import DEFAULT_METRIC_SEMANTICS_VERSION
from app.services.ml.regional_trainer import RegionalModelTrainer
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
)


class RegionalTrainerPromotionTests(unittest.TestCase):
    def test_train_single_horizon_surfaces_fail_closed_promotion_evidence(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=200, freq="D"),
                "target_date": pd.date_range("2026-01-08", periods=200, freq="D"),
                "current_known_incidence": np.linspace(1.0, 200.0, 200),
                "next_week_incidence": np.linspace(2.0, 201.0, 200),
                "bundesland": ["BY"] * 200,
                "bundesland_name": ["Bayern"] * 200,
                "f1": np.linspace(0.0, 1.0, 200),
            }
        )

        class _Registry:
            def __init__(self) -> None:
                self.evidence_kwargs: dict[str, object] | None = None
                self.record_metadata: dict[str, object] | None = None

            def load_scope(self, **_kwargs):
                return {
                    "champion": {
                        "metrics": {"relative_wis": 0.98, "crps": 1.4},
                        "metadata": {
                            "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                            "sample_count": 24,
                        },
                    }
                }

            def evaluate_promotion(self, **kwargs):
                self.evidence_kwargs = kwargs
                return {
                    "quality_gate_overall_passed": False,
                    "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                    "minimum_sample_count": 12,
                    "candidate_metrics_present": True,
                    "champion_metrics_present": True,
                    "promotion_allowed": False,
                    "promotion_blockers": ["quality_gate_not_passed"],
                }

            def record_evaluation(self, **kwargs):
                self.record_metadata = kwargs.get("metadata") or {}
                return {"champion": None, "history": []}

        trainer.registry = _Registry()
        trainer.feature_builder = SimpleNamespace(
            build_panel_training_data=lambda **_kwargs: panel.copy(),
            dataset_manifest=lambda **_kwargs: {"rows": 200, "states": 1, "source_coverage": {}},
            point_in_time_snapshot_manifest=lambda **_kwargs: {
                "snapshot_type": "training_panel_visible_data",
                "captured_at": "2026-03-17T08:00:00",
                "unique_as_of_dates": 200,
            },
        )
        trainer.load_artifacts = lambda **_kwargs: {}
        trainer._prepare_horizon_panel = lambda frame, horizon_days: frame.copy()
        trainer._feature_columns = lambda frame: ["f1"]
        trainer._ww_only_feature_columns = lambda feature_columns: []
        trainer._select_event_definition = lambda **_kwargs: {
            "tau": 1.0,
            "kappa": 0.5,
            "action_threshold": 0.6,
        }
        trainer._event_labels = lambda frame, **_kwargs: np.zeros(len(frame), dtype=int)
        trainer._build_backtest_bundle = lambda **_kwargs: {
            "oof_frame": panel.copy(),
            "aggregate_metrics": {"relative_wis": 0.94, "crps": 1.2},
            "benchmark_summary": {
                "metrics": {"relative_wis": 0.94, "crps": 1.2},
                "candidate_summaries": [
                    {"candidate": "regional_pooled_panel", "metrics": {"relative_wis": 0.94}, "samples": 24}
                ],
            },
            "quality_gate": {
                "overall_passed": False,
                "forecast_readiness": "WATCH",
                "profile": "strict_v1",
                "failed_checks": ["quality_gate_not_passed"],
            },
            "backtest_payload": {"details": {"BY": {"bundesland_name": "Bayern"}}},
        }
        trainer._rollout_metadata = lambda **_kwargs: {
            "signal_bundle_version": "core_panel_v1",
            "rollout_mode": "gated",
            "activation_policy": "quality_gate",
            "shadow_evaluation": None,
        }
        trainer._fit_final_models = lambda **_kwargs: {
            "calibration_mode": "isotonic",
            "calibration": object(),
            "learned_event_model": None,
            "hierarchy_model_modes": {},
        }
        trainer._build_hierarchy_metadata = lambda **_kwargs: {
            "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            "reconciliation_method": "none",
            "hierarchy_consistency_status": "coherent",
        }

        result = trainer._train_single_horizon(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=False,
            horizon_days=7,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["registry_status"], "challenger")
        self.assertFalse(result["promotion_evidence"]["promotion_allowed"])
        self.assertIn("quality_gate_not_passed", result["promotion_evidence"]["promotion_blockers"])
        self.assertEqual(
            trainer.registry.evidence_kwargs["candidate_metadata"]["metric_semantics_version"],
            DEFAULT_METRIC_SEMANTICS_VERSION,
        )
        self.assertEqual(
            trainer.registry.record_metadata["promotion_evidence"]["promotion_blockers"],
            ["quality_gate_not_passed"],
        )

    def test_train_single_horizon_blocks_promotion_for_inactive_rsv_scope(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=200, freq="D"),
                "target_date": pd.date_range("2026-01-08", periods=200, freq="D"),
                "current_known_incidence": np.linspace(1.0, 200.0, 200),
                "next_week_incidence": np.linspace(2.0, 201.0, 200),
                "bundesland": ["BY"] * 200,
                "bundesland_name": ["Bayern"] * 200,
                "f1": np.linspace(0.0, 1.0, 200),
            }
        )

        class _Registry:
            def load_scope(self, **_kwargs):
                return {"champion": None}

            def evaluate_promotion(self, **_kwargs):
                return {
                    "quality_gate_overall_passed": True,
                    "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                    "minimum_sample_count": 12,
                    "candidate_metrics_present": True,
                    "champion_metrics_present": False,
                    "promotion_allowed": True,
                    "promotion_blockers": [],
                }

            def record_evaluation(self, **kwargs):
                return {"metadata": kwargs.get("metadata") or {}, "champion": None, "history": []}

        trainer.registry = _Registry()
        trainer.feature_builder = SimpleNamespace(
            build_panel_training_data=lambda **_kwargs: panel.copy(),
            dataset_manifest=lambda **_kwargs: {"rows": 200, "states": 1, "source_coverage": {}},
            point_in_time_snapshot_manifest=lambda **_kwargs: {
                "snapshot_type": "training_panel_visible_data",
                "captured_at": "2026-03-17T08:00:00",
                "unique_as_of_dates": 200,
            },
        )
        trainer.load_artifacts = lambda **_kwargs: {}
        trainer._prepare_horizon_panel = lambda frame, horizon_days: frame.copy()
        trainer._feature_columns = lambda frame: ["f1"]
        trainer._ww_only_feature_columns = lambda feature_columns: []
        trainer._select_event_definition = lambda **_kwargs: {
            "tau": 1.0,
            "kappa": 0.5,
            "action_threshold": 0.6,
        }
        trainer._event_labels = lambda frame, **_kwargs: np.zeros(len(frame), dtype=int)
        trainer._build_backtest_bundle = lambda **_kwargs: {
            "oof_frame": panel.copy(),
            "aggregate_metrics": {"relative_wis": 0.94, "crps": 1.2},
            "benchmark_summary": {
                "metrics": {"relative_wis": 0.94, "crps": 1.2},
                "candidate_summaries": [
                    {"candidate": "regional_pooled_panel", "metrics": {"relative_wis": 0.94}, "samples": 24}
                ],
                "fold_viability": {"passed": True},
            },
            "quality_gate": {
                "overall_passed": True,
                "forecast_readiness": "GO",
                "profile": "strict_v1",
                "failed_checks": [],
            },
            "backtest_payload": {"details": {"BY": {"bundesland_name": "Bayern"}}},
        }
        trainer._rollout_metadata = lambda **_kwargs: {
            "signal_bundle_version": "core_panel_v1",
            "rollout_mode": "gated",
            "activation_policy": "quality_gate",
            "shadow_evaluation": None,
        }
        trainer._fit_final_models = lambda **_kwargs: {
            "calibration_mode": "isotonic",
            "calibration": object(),
            "learned_event_model": None,
            "hierarchy_model_modes": {},
        }
        trainer._build_hierarchy_metadata = lambda **_kwargs: {
            "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            "reconciliation_method": "none",
            "hierarchy_consistency_status": "coherent",
        }

        result = trainer._train_single_horizon(
            virus_typ="RSV A",
            lookback_days=900,
            persist=False,
            horizon_days=7,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["registry_status"], "challenger")
        self.assertFalse(result["promotion_evidence"]["promotion_allowed"])
        self.assertIn("champion_scope_inactive", result["promotion_evidence"]["promotion_blockers"])

    def test_train_single_horizon_weather_vintage_comparison_runs_shadow_mode_only_when_enabled(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        base_panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=200, freq="D"),
                "target_date": pd.date_range("2026-01-08", periods=200, freq="D"),
                "current_known_incidence": np.linspace(1.0, 200.0, 200),
                "next_week_incidence": np.linspace(2.0, 201.0, 200),
                "bundesland": ["BY"] * 200,
                "bundesland_name": ["Bayern"] * 200,
                "f1": np.linspace(0.0, 1.0, 200),
            }
        )

        class _FeatureBuilder:
            def __init__(self) -> None:
                self.calls: list[object] = []

            def build_panel_training_data(self, **kwargs):
                mode = kwargs.get("weather_forecast_vintage_mode", "__missing__")
                self.calls.append(mode)
                resolved_mode = (
                    WEATHER_FORECAST_VINTAGE_DISABLED
                    if mode == "__missing__" or mode is None
                    else str(mode)
                )
                frame = base_panel.copy()
                frame["weather_mode_marker"] = resolved_mode
                return frame

            def dataset_manifest(self, virus_typ: str, panel: pd.DataFrame):
                del virus_typ
                mode = str(panel["weather_mode_marker"].iloc[0])
                return {
                    "rows": len(panel),
                    "states": 1,
                    "source_coverage": {},
                    "weather_forecast_vintage_mode": mode,
                    "weather_forecast_run_identity_present": mode == WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
                    "exogenous_feature_semantics_version": "regional_exogenous_semantics_v1",
                }

            def point_in_time_snapshot_manifest(self, virus_typ: str, panel: pd.DataFrame):
                del virus_typ
                return {
                    "snapshot_type": "training_panel_visible_data",
                    "captured_at": "2026-03-17T08:00:00",
                    "unique_as_of_dates": int(panel["as_of_date"].nunique()),
                }

        class _Registry:
            def load_scope(self, **_kwargs):
                return {"champion": None}

            def evaluate_promotion(self, **_kwargs):
                return {
                    "quality_gate_overall_passed": True,
                    "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                    "minimum_sample_count": 12,
                    "candidate_metrics_present": True,
                    "champion_metrics_present": False,
                    "promotion_allowed": True,
                    "promotion_blockers": [],
                }

            def record_evaluation(self, **_kwargs):
                return {"champion": {}, "history": []}

        def _prepared_panel(frame: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
            del horizon_days
            prepared = frame.copy()
            prepared["weather_mode_marker"] = frame["weather_mode_marker"].values
            return prepared

        def _backtest_bundle(panel: pd.DataFrame, **_kwargs):
            mode = str(panel["weather_mode_marker"].iloc[0])
            relative_wis = 0.97 if mode == WEATHER_FORECAST_VINTAGE_DISABLED else 0.91
            crps = 1.30 if mode == WEATHER_FORECAST_VINTAGE_DISABLED else 1.18
            metrics = {"relative_wis": relative_wis, "crps": crps, "brier_score": 0.08}
            return {
                "oof_frame": panel.copy(),
                "aggregate_metrics": metrics,
                "benchmark_summary": {
                    "metrics": metrics,
                    "candidate_summaries": [
                        {"candidate": "regional_pooled_panel", "metrics": metrics, "samples": int(len(panel))}
                    ],
                },
                "quality_gate": {
                    "overall_passed": True,
                    "forecast_readiness": "GO",
                    "profile": "strict_v1",
                    "failed_checks": [],
                },
                "backtest_payload": {"details": {"BY": {"bundesland_name": "Bayern"}}},
            }

        trainer.registry = _Registry()
        trainer.feature_builder = _FeatureBuilder()
        trainer.load_artifacts = lambda **_kwargs: {}
        trainer._prepare_horizon_panel = _prepared_panel
        trainer._feature_columns = lambda frame: ["f1"]
        trainer._ww_only_feature_columns = lambda feature_columns: []
        trainer._select_event_definition = lambda **_kwargs: {
            "tau": 1.0,
            "kappa": 0.5,
            "action_threshold": 0.6,
        }
        trainer._event_labels = lambda frame, **_kwargs: np.zeros(len(frame), dtype=int)
        trainer._build_backtest_bundle = _backtest_bundle
        trainer._rollout_metadata = lambda **_kwargs: {
            "signal_bundle_version": "core_panel_v1",
            "rollout_mode": "gated",
            "activation_policy": "quality_gate",
            "shadow_evaluation": None,
        }
        trainer._fit_final_models = lambda **_kwargs: {
            "calibration_mode": "isotonic",
            "calibration": object(),
            "learned_event_model": None,
            "hierarchy_model_modes": {},
        }
        trainer._build_hierarchy_metadata = lambda **_kwargs: {
            "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            "reconciliation_method": "none",
            "hierarchy_consistency_status": "coherent",
        }

        result = trainer._train_single_horizon(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=False,
            horizon_days=7,
            weather_vintage_comparison=True,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            trainer.feature_builder.calls,
            ["__missing__", WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1],
        )
        self.assertEqual(result["weather_forecast_vintage_mode"], WEATHER_FORECAST_VINTAGE_DISABLED)
        comparison = result["weather_vintage_comparison"]
        self.assertEqual(comparison["comparison_status"], "ok")
        self.assertIn(WEATHER_FORECAST_VINTAGE_DISABLED, comparison["modes"])
        self.assertIn(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, comparison["modes"])
        self.assertEqual(
            comparison["modes"][WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1]["exogenous_feature_semantics_version"],
            "regional_exogenous_semantics_v1",
        )
        self.assertEqual(
            comparison["legacy_vs_vintage_metric_delta"]["relative_wis"],
            -0.06,
        )
        self.assertTrue(
            comparison["weather_vintage_run_identity_coverage"][WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1]["run_identity_present"]
        )

    def test_train_single_horizon_keeps_legacy_default_when_weather_comparison_is_disabled(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=200, freq="D"),
                "target_date": pd.date_range("2026-01-08", periods=200, freq="D"),
                "current_known_incidence": np.linspace(1.0, 200.0, 200),
                "next_week_incidence": np.linspace(2.0, 201.0, 200),
                "bundesland": ["BY"] * 200,
                "bundesland_name": ["Bayern"] * 200,
                "f1": np.linspace(0.0, 1.0, 200),
            }
        )

        class _FeatureBuilder:
            def __init__(self) -> None:
                self.calls: list[object] = []

            def build_panel_training_data(self, **kwargs):
                self.calls.append(kwargs.get("weather_forecast_vintage_mode", "__missing__"))
                frame = panel.copy()
                frame["weather_mode_marker"] = WEATHER_FORECAST_VINTAGE_DISABLED
                return frame

            def dataset_manifest(self, **_kwargs):
                return {
                    "rows": 200,
                    "states": 1,
                    "source_coverage": {},
                    "weather_forecast_vintage_mode": WEATHER_FORECAST_VINTAGE_DISABLED,
                    "weather_forecast_run_identity_present": False,
                    "exogenous_feature_semantics_version": "regional_exogenous_semantics_v1",
                }

            def point_in_time_snapshot_manifest(self, **_kwargs):
                return {
                    "snapshot_type": "training_panel_visible_data",
                    "captured_at": "2026-03-17T08:00:00",
                    "unique_as_of_dates": 200,
                }

        trainer.registry = SimpleNamespace(
            load_scope=lambda **_kwargs: {"champion": None},
            evaluate_promotion=lambda **_kwargs: {
                "quality_gate_overall_passed": True,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "minimum_sample_count": 12,
                "candidate_metrics_present": True,
                "champion_metrics_present": False,
                "promotion_allowed": True,
                "promotion_blockers": [],
            },
            record_evaluation=lambda **_kwargs: {"champion": {}, "history": []},
        )
        trainer.feature_builder = _FeatureBuilder()
        trainer.load_artifacts = lambda **_kwargs: {}
        trainer._prepare_horizon_panel = lambda frame, horizon_days: frame.copy()
        trainer._feature_columns = lambda frame: ["f1"]
        trainer._ww_only_feature_columns = lambda feature_columns: []
        trainer._select_event_definition = lambda **_kwargs: {
            "tau": 1.0,
            "kappa": 0.5,
            "action_threshold": 0.6,
        }
        trainer._event_labels = lambda frame, **_kwargs: np.zeros(len(frame), dtype=int)
        trainer._build_backtest_bundle = lambda **_kwargs: {
            "oof_frame": panel.copy(),
            "aggregate_metrics": {"relative_wis": 0.94, "crps": 1.2},
            "benchmark_summary": {
                "metrics": {"relative_wis": 0.94, "crps": 1.2},
                "candidate_summaries": [
                    {"candidate": "regional_pooled_panel", "metrics": {"relative_wis": 0.94}, "samples": 24}
                ],
            },
            "quality_gate": {
                "overall_passed": True,
                "forecast_readiness": "GO",
                "profile": "strict_v1",
                "failed_checks": [],
            },
            "backtest_payload": {"details": {"BY": {"bundesland_name": "Bayern"}}},
        }
        trainer._rollout_metadata = lambda **_kwargs: {
            "signal_bundle_version": "core_panel_v1",
            "rollout_mode": "gated",
            "activation_policy": "quality_gate",
            "shadow_evaluation": None,
        }
        trainer._fit_final_models = lambda **_kwargs: {
            "calibration_mode": "isotonic",
            "calibration": object(),
            "learned_event_model": None,
            "hierarchy_model_modes": {},
        }
        trainer._build_hierarchy_metadata = lambda **_kwargs: {
            "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            "reconciliation_method": "none",
            "hierarchy_consistency_status": "coherent",
        }

        result = trainer._train_single_horizon(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=False,
            horizon_days=7,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(trainer.feature_builder.calls, ["__missing__"])
        self.assertEqual(result["weather_forecast_vintage_mode"], WEATHER_FORECAST_VINTAGE_DISABLED)
        self.assertIsNone(result["weather_vintage_comparison"])


if __name__ == "__main__":
    unittest.main()
