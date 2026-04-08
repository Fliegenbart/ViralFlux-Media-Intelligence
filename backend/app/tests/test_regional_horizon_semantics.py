import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.services.ml.forecast_horizon_utils import (
    regional_horizon_pilot_status,
    regional_horizon_support_status,
)
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.regional_trainer import RegionalModelTrainer

_BACKTEST_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_regional_hierarchy_backtest.py"
_build_report = None
_BACKTEST_SCRIPT_IMPORT_ERROR: str | None = None
try:
    if not _BACKTEST_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing helper script: {_BACKTEST_SCRIPT_PATH}")
    _BACKTEST_SCRIPT_SPEC = importlib.util.spec_from_file_location(
        "run_regional_hierarchy_backtest",
        _BACKTEST_SCRIPT_PATH,
    )
    assert _BACKTEST_SCRIPT_SPEC is not None and _BACKTEST_SCRIPT_SPEC.loader is not None
    _BACKTEST_SCRIPT_MODULE = importlib.util.module_from_spec(_BACKTEST_SCRIPT_SPEC)
    _BACKTEST_SCRIPT_SPEC.loader.exec_module(_BACKTEST_SCRIPT_MODULE)
    _build_report = _BACKTEST_SCRIPT_MODULE._build_report
except Exception as exc:  # pragma: no cover - exercised via skip path when helper is absent.
    # This test module should still collect when the optional report helper is absent.
    _BACKTEST_SCRIPT_IMPORT_ERROR = str(exc)


class _LoadableModel:
    def __init__(self) -> None:
        self.loaded_path: str | None = None

    def load_model(self, path: str) -> None:
        self.loaded_path = path


class RegionalHorizonSemanticsTests(unittest.TestCase):
    def test_default_support_matrix_marks_rsv_h3_as_unsupported(self) -> None:
        support = regional_horizon_support_status("RSV A", 3)

        self.assertFalse(support["supported"])
        self.assertEqual(support["supported_horizons"], [5, 7])
        self.assertIn("pooled panel", support["reason"])

    def test_day_one_pilot_matrix_supports_only_selected_scopes(self) -> None:
        influenza = regional_horizon_pilot_status("Influenza A", 7)
        sars = regional_horizon_pilot_status("SARS-CoV-2", 7)

        self.assertTrue(influenza["pilot_supported"])
        self.assertEqual(influenza["pilot_supported_horizons"], [7])
        self.assertFalse(sars["pilot_supported"])
        self.assertIn("shadow-only", sars["reason"])

    def test_prepare_horizon_panel_uses_future_current_incidence_as_target(self) -> None:
        panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BY", "BY"],
                "as_of_date": [
                    pd.Timestamp("2026-03-01"),
                    pd.Timestamp("2026-03-04"),
                    pd.Timestamp("2026-03-07"),
                ],
                "target_date": [
                    pd.Timestamp("2026-03-04"),
                    pd.Timestamp("2026-03-07"),
                    pd.Timestamp("2026-03-10"),
                ],
                "target_window_days": [[3, 3], [3, 3], [3, 3]],
                "current_known_incidence": [10.0, 16.0, 22.0],
                "truth_source": ["survstat_kreis", "survstat_kreis", "survstat_kreis"],
                "f1": [1.0, 2.0, 3.0],
            }
        )

        prepared = RegionalModelTrainer._prepare_horizon_panel(panel, horizon_days=3)

        self.assertEqual(len(prepared), 2)
        self.assertEqual(prepared.iloc[0]["next_week_incidence"], 16.0)
        self.assertEqual(prepared.iloc[1]["next_week_incidence"], 22.0)
        self.assertEqual(prepared.iloc[0]["target_window_days"], [3, 3])
        self.assertEqual(prepared.iloc[0]["horizon_days"], 3.0)

    def test_feature_columns_exclude_training_only_target_incidence(self) -> None:
        panel = pd.DataFrame(
            {
                "bundesland": ["BY"],
                "bundesland_name": ["Bayern"],
                "as_of_date": [pd.Timestamp("2026-03-01")],
                "target_date": [pd.Timestamp("2026-03-04")],
                "target_week_start": [pd.Timestamp("2026-03-02")],
                "target_window_days": [[3, 3]],
                "horizon_days": [3.0],
                "truth_source": ["survstat_kreis"],
                "target_truth_source": ["survstat_kreis"],
                "current_known_incidence": [10.0],
                "target_incidence": [16.0],
                "next_week_incidence": [16.0],
                "seasonal_baseline": [8.0],
                "seasonal_mad": [2.0],
                "event_label": [1.0],
                "y_next_log": [1.0],
                "f1": [1.0],
                "f2": [2.0],
            }
        )

        trainer = RegionalModelTrainer(db=None)
        feature_columns = trainer._feature_columns(panel)

        self.assertEqual(feature_columns, ["f1", "f2"])

    def test_train_single_horizon_returns_structured_error_payload_when_backtest_fails(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=200, freq="D"),
                "next_week_incidence": np.linspace(1.0, 200.0, 200),
                "current_known_incidence": np.linspace(1.0, 200.0, 200),
                "bundesland": ["BY"] * 200,
                "bundesland_name": ["Bayern"] * 200,
                "f1": np.linspace(0.0, 1.0, 200),
            }
        )
        trainer.feature_builder = SimpleNamespace(
            build_panel_training_data=lambda **_kwargs: panel.copy(),
        )
        trainer.load_artifacts = lambda **_kwargs: {}
        trainer._prepare_horizon_panel = lambda frame, horizon_days: frame.copy()
        trainer._feature_columns = lambda frame: ["f1"]
        trainer._select_event_definition = lambda **_kwargs: {
            "tau": 1.0,
            "kappa": 0.5,
            "action_threshold": 0.6,
        }
        trainer._event_labels = lambda frame, **_kwargs: np.zeros(len(frame), dtype=int)
        trainer._build_backtest_bundle = lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Regional backtest produced no valid folds.")
        )

        result = trainer._train_single_horizon(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=False,
            horizon_days=3,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertEqual(result["error_stage"], "train_single_horizon")
        self.assertIn("no valid folds", result["error"].lower())
        self.assertIn("zeit-folds", result["diagnostic_hint"].lower())
        self.assertTrue(result["traceback_tail"])

    def test_backtest_report_renders_structured_error_payload(self) -> None:
        if _build_report is None:
            self.skipTest(_BACKTEST_SCRIPT_IMPORT_ERROR or "regional backtest report helper unavailable")
        report = _build_report(
            {
                "status": "error",
                "virus_typ": "Influenza A",
                "horizon_days": 3,
                "error_type": "ValueError",
                "error": "Regional backtest produced no valid folds.",
                "diagnostic_hint": "Bitte Fold-Bildung prüfen.",
                "traceback_tail": ["ValueError: Regional backtest produced no valid folds."],
            }
        )

        self.assertIn("- Status: `error`", report)
        self.assertIn("- Error type: `ValueError`", report)
        self.assertIn("## Traceback Tail", report)

    @patch("app.services.ml.regional_trainer.quality_gate_from_metrics")
    @patch("app.services.ml.regional_trainer.time_based_panel_splits")
    def test_build_backtest_bundle_passes_requested_horizon_into_quality_gate(
        self,
        splits_mock,
        quality_gate_mock,
    ) -> None:
        class _Classifier:
            def predict_proba(self, values):
                probs = np.full(len(values), 0.6, dtype=float)
                return np.column_stack([1.0 - probs, probs])

        class _Regressor:
            def predict(self, values):
                return np.log1p(np.full(len(values), 20.0, dtype=float))

        trainer = RegionalModelTrainer(db=None)
        dates = pd.to_datetime(
            [
                "2026-01-01",
                "2026-01-08",
                "2026-01-15",
                "2026-01-22",
                "2026-01-29",
                "2026-02-05",
            ]
        )
        panel = pd.DataFrame(
            {
                "virus_typ": ["Influenza A"] * 6,
                "bundesland": ["BY"] * 6,
                "bundesland_name": ["Bayern"] * 6,
                "as_of_date": dates,
                "target_date": dates + pd.Timedelta(days=5),
                "target_week_start": dates,
                "horizon_days": [5.0] * 6,
                "current_known_incidence": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
                "next_week_incidence": [12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
                "seasonal_baseline": [8.0] * 6,
                "seasonal_mad": [1.5] * 6,
                "y_next_log": np.log1p([12.0, 13.0, 14.0, 15.0, 16.0, 17.0]),
                "f1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            }
        )
        splits_mock.return_value = [(dates[:4], dates[4:])]
        quality_gate_mock.return_value = {
            "profile": "pilot_v1",
            "overall_passed": True,
            "forecast_readiness": "GO",
            "checks": {},
            "baseline_metrics": {},
            "failed_checks": [],
            "thresholds": {},
        }
        trainer._event_labels = lambda frame, **_: pd.Series(
            [idx % 2 for idx in range(len(frame))],
            index=frame.index,
            dtype=int,
        )
        trainer._calibration_split_dates = lambda train_dates: (train_dates[:2], train_dates[2:])
        trainer._fit_classifier = lambda *_args, **_kwargs: _Classifier()
        trainer._fit_isotonic = lambda *_args, **_kwargs: object()
        trainer._apply_calibration = lambda _calibration, raw_prob: raw_prob
        trainer._amelag_only_probabilities = lambda *, train_df, test_df, feature_columns: np.full(
            len(test_df), 0.25, dtype=float
        )
        trainer._fit_regressor = lambda *_args, **_kwargs: _Regressor()
        trainer._event_probability_from_prediction = lambda **kwargs: np.full(
            len(kwargs["predicted_next"]), 0.3, dtype=float
        )
        trainer._aggregate_metrics = lambda **_kwargs: {
            "precision_at_top3": 0.61,
            "activation_false_positive_rate": 0.2,
            "pr_auc": 0.66,
            "brier_score": 0.1,
            "ece": 0.04,
        }
        trainer._baseline_metrics = lambda **_kwargs: {
            "best_baseline": 0.6,
            "climatology_brier": 0.11,
        }
        trainer._build_backtest_payload = lambda **kwargs: {"baselines": kwargs["baselines"]}

        bundle = trainer._build_backtest_bundle(
            virus_typ="Influenza A",
            panel=panel,
            feature_columns=["f1"],
            hierarchy_feature_columns=["f1"],
            ww_only_columns=[],
            tau=1.1,
            kappa=0.5,
            action_threshold=0.42,
            horizon_days=5,
        )

        self.assertEqual(bundle["quality_gate"]["profile"], "pilot_v1")
        self.assertEqual(quality_gate_mock.call_args.kwargs["virus_typ"], "Influenza A")
        self.assertEqual(quality_gate_mock.call_args.kwargs["horizon_days"], 5)

    def test_select_guarded_calibration_keeps_isotonic_when_guard_metrics_improve(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        labels = np.array([0, 1] * 10, dtype=int)
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": np.where(labels == 1, 0.58, 0.42),
            }
        )

        calibration_token = object()
        trainer._fit_isotonic = lambda *_args, **_kwargs: calibration_token
        trainer._apply_calibration = lambda calibration, raw_probabilities: (
            np.clip(np.asarray(raw_probabilities, dtype=float), 0.001, 0.999)
            if calibration is None
            else np.where(np.asarray(raw_probabilities, dtype=float) >= 0.5, 0.85, 0.15)
        )

        calibration, mode = trainer._select_guarded_calibration(
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
        )

        self.assertIs(calibration, calibration_token)
        self.assertEqual(mode, "isotonic_guarded")

    def test_select_guarded_calibration_rejects_isotonic_when_guard_metrics_degrade(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        labels = np.array([0, 1] * 10, dtype=int)
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": np.where(labels == 1, 0.58, 0.42),
            }
        )

        trainer._fit_isotonic = lambda *_args, **_kwargs: object()
        trainer._apply_calibration = lambda calibration, raw_probabilities: (
            np.clip(np.asarray(raw_probabilities, dtype=float), 0.001, 0.999)
            if calibration is None
            else np.where(np.asarray(raw_probabilities, dtype=float) >= 0.5, 0.55, 0.65)
        )

        calibration, mode = trainer._select_guarded_calibration(
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
        )

        self.assertIsNone(calibration)
        self.assertEqual(mode, "raw_passthrough")

    def test_train_single_horizon_uses_final_calibration_mode_in_metadata(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        dates = pd.date_range("2025-01-01", periods=220, freq="D")
        panel = pd.DataFrame(
            {
                "virus_typ": ["Influenza A"] * len(dates),
                "bundesland": ["BY"] * len(dates),
                "bundesland_name": ["Bayern"] * len(dates),
                "as_of_date": dates,
                "target_date": dates + pd.Timedelta(days=7),
                "target_week_start": dates,
                "horizon_days": [7.0] * len(dates),
                "truth_source": ["survstat_kreis"] * len(dates),
                "target_truth_source": ["survstat_kreis"] * len(dates),
                "current_known_incidence": np.linspace(5.0, 15.0, len(dates)),
                "next_week_incidence": np.linspace(6.0, 16.0, len(dates)),
                "seasonal_baseline": np.full(len(dates), 8.0, dtype=float),
                "seasonal_mad": np.full(len(dates), 1.5, dtype=float),
                "f1": np.linspace(0.1, 0.9, len(dates)),
            }
        )

        trainer.load_artifacts = lambda *_args, **_kwargs: {}
        trainer.feature_builder.build_panel_training_data = lambda **_kwargs: panel.copy()
        trainer.feature_builder.dataset_manifest = lambda **_kwargs: {}
        trainer.feature_builder.point_in_time_snapshot_manifest = lambda **_kwargs: {}
        trainer._prepare_horizon_panel = lambda frame, horizon_days: frame.copy()
        trainer._feature_columns = lambda _frame: ["f1"]
        trainer._ww_only_feature_columns = lambda _columns: []
        trainer._select_event_definition = lambda **_kwargs: {
            "tau": 1.0,
            "kappa": 0.5,
            "action_threshold": 0.65,
        }
        trainer._event_labels = lambda frame, **_kwargs: pd.Series(
            [idx % 2 for idx in range(len(frame))],
            index=frame.index,
            dtype=int,
        )
        trainer._build_backtest_bundle = lambda **_kwargs: {
            "oof_frame": pd.DataFrame(
                {
                    "as_of_date": dates[:20],
                    "event_label": [idx % 2 for idx in range(20)],
                    "event_probability_raw": np.linspace(0.2, 0.8, 20),
                }
            ),
            "aggregate_metrics": {
                "precision_at_top3": 0.7,
                "activation_false_positive_rate": 0.05,
                "pr_auc": 0.55,
                "brier_score": 0.08,
                "ece": 0.04,
            },
            "quality_gate": {
                "profile": "pilot_v1",
                "overall_passed": False,
                "forecast_readiness": "WATCH",
                "checks": {},
                "failed_checks": [],
                "thresholds": {},
            },
            "backtest_payload": {
                "baselines": {},
                "details": {"BY": {"bundesland": "BY"}},
            },
        }
        trainer._rollout_metadata = lambda **_kwargs: {
            "signal_bundle_version": "core_panel_v1",
            "rollout_mode": "gated",
            "activation_policy": "quality_gate",
            "shadow_evaluation": None,
        }
        trainer._fit_final_models = lambda **_kwargs: {
            "classifier": None,
            "calibration": None,
            "calibration_mode": "raw_passthrough",
            "regressor_median": None,
            "regressor_lower": None,
            "regressor_upper": None,
        }
        captured: dict[str, object] = {}
        trainer._persist_artifacts = lambda **kwargs: captured.update(kwargs)

        payload = trainer._train_single_horizon(
            virus_typ="Influenza A",
            lookback_days=900,
            persist=True,
            horizon_days=7,
        )

        self.assertEqual(payload["status"], "success")
        self.assertIn("metadata", captured)
        self.assertTrue(
            str((captured["metadata"] or {}).get("calibration_version")).startswith("raw_passthrough:h7:")
        )

    def test_trainer_load_artifacts_reads_horizon_specific_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            model_dir = base / "influenza_a" / "horizon_5"
            model_dir.mkdir(parents=True)
            (model_dir / "metadata.json").write_text(json.dumps({"trained_at": "2026-03-15T12:00:00", "horizon_days": 5}))
            (model_dir / "backtest.json").write_text(json.dumps({"total_regions": 16, "horizon_days": 5}))
            (model_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 100, "horizon_days": 5}))

            trainer = RegionalModelTrainer(db=None, models_dir=base)
            payload = trainer.load_artifacts("Influenza A", horizon_days=5)

            self.assertEqual(payload["metadata"]["horizon_days"], 5)
            self.assertEqual(payload["metadata"]["target_window_days"], [5, 5])
            self.assertEqual(payload["backtest"]["horizon_days"], 5)

    @patch("app.services.ml.regional_forecast.pickle.load", return_value="calibration")
    @patch("app.services.ml.regional_forecast.XGBRegressor", side_effect=lambda: _LoadableModel())
    @patch("app.services.ml.regional_forecast.XGBClassifier", side_effect=lambda: _LoadableModel())
    def test_forecast_loader_requires_horizon_metadata_for_scoped_artifacts(
        self,
        _classifier_cls,
        _regressor_cls,
        _pickle_load,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            model_dir = base / "influenza_a" / "horizon_5"
            model_dir.mkdir(parents=True)
            for name in [
                "classifier.json",
                "regressor_median.json",
                "regressor_lower.json",
                "regressor_upper.json",
                "calibration.pkl",
            ]:
                (model_dir / name).write_text("{}")
            (model_dir / "metadata.json").write_text(json.dumps({"feature_columns": ["f1"]}))
            (model_dir / "dataset_manifest.json").write_text(json.dumps({"rows": 10}))
            (model_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 10}))

            service = RegionalForecastService(db=None, models_dir=base)
            payload = service._load_artifacts("Influenza A", horizon_days=5)

            self.assertIn("load_error", payload)
            self.assertIn("horizon_days", payload["load_error"])

    @patch("app.services.ml.regional_forecast.pickle.load", return_value="calibration")
    @patch("app.services.ml.regional_forecast.XGBRegressor", side_effect=lambda: _LoadableModel())
    @patch("app.services.ml.regional_forecast.XGBClassifier", side_effect=lambda: _LoadableModel())
    def test_forecast_loader_uses_explicit_legacy_transition_for_h7_fallback(
        self,
        _classifier_cls,
        _regressor_cls,
        _pickle_load,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            legacy_dir = base / "influenza_a"
            legacy_dir.mkdir(parents=True)
            for name in [
                "classifier.json",
                "regressor_median.json",
                "regressor_lower.json",
                "regressor_upper.json",
                "calibration.pkl",
            ]:
                (legacy_dir / name).write_text("{}")
            (legacy_dir / "metadata.json").write_text(json.dumps({"feature_columns": ["f1"]}))
            (legacy_dir / "dataset_manifest.json").write_text(json.dumps({"rows": 10}))
            (legacy_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 10}))

            service = RegionalForecastService(db=None, models_dir=base)
            payload = service._load_artifacts("Influenza A", horizon_days=7)

            self.assertEqual(payload["artifact_transition_mode"], "legacy_default_window_fallback")
            self.assertEqual(payload["metadata"]["horizon_days"], 7)
            self.assertEqual(payload["metadata"]["requested_horizon_days"], 7)

    @patch("app.services.ml.regional_forecast.pickle.load", return_value="calibration")
    @patch("app.services.ml.regional_forecast.XGBRegressor", side_effect=lambda: _LoadableModel())
    @patch("app.services.ml.regional_forecast.XGBClassifier", side_effect=lambda: _LoadableModel())
    def test_forecast_loader_rejects_training_only_feature_columns(
        self,
        _classifier_cls,
        _regressor_cls,
        _pickle_load,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            model_dir = base / "influenza_a" / "horizon_7"
            model_dir.mkdir(parents=True)
            for name in [
                "classifier.json",
                "regressor_median.json",
                "regressor_lower.json",
                "regressor_upper.json",
                "calibration.pkl",
            ]:
                (model_dir / name).write_text("{}")
            (model_dir / "metadata.json").write_text(
                json.dumps({"feature_columns": ["f1", "target_incidence"], "horizon_days": 7})
            )
            (model_dir / "dataset_manifest.json").write_text(json.dumps({"rows": 10}))
            (model_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 10}))

            service = RegionalForecastService(db=None, models_dir=base)
            payload = service._load_artifacts("Influenza A", horizon_days=7)

            self.assertIn("load_error", payload)
            self.assertIn("target_incidence", payload["load_error"])

    def test_predict_all_regions_returns_explicit_unsupported_scope_when_configured(self) -> None:
        service = RegionalForecastService(db=None)

        with patch.dict(
            "app.services.ml.forecast_horizon_utils.REGIONAL_UNSUPPORTED_HORIZON_REASONS",
            {"Influenza A": {3: "Pilot supports only h5/h7 for this virus."}},
            clear=False,
        ):
            payload = service.predict_all_regions("Influenza A", horizon_days=3)

        self.assertEqual(payload["status"], "unsupported")
        self.assertEqual(payload["horizon_days"], 3)
        self.assertEqual(payload["supported_horizon_days_for_virus"], [5, 7])
        self.assertEqual(payload["predictions"], [])


if __name__ == "__main__":
    unittest.main()
