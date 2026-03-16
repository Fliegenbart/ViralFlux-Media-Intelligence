import unittest

import numpy as np
import pandas as pd

from app.services.ml.wave_prediction_fixtures import (
    FIXTURE_WAVE_SETTINGS,
    FixtureWavePredictionService,
)
from app.services.ml.wave_prediction_utils import (
    WaveLabelConfig,
    build_backtest_splits,
    get_classification_feature_columns,
    label_wave_start,
    weather_context_features,
)


TEST_SETTINGS = FIXTURE_WAVE_SETTINGS


class _FakeWavePredictionService(FixtureWavePredictionService):
    def __init__(self, fixture: str = "default"):
        super().__init__(fixture=fixture, settings=TEST_SETTINGS)


class WavePredictionUtilsTests(unittest.TestCase):
    def test_label_wave_start_triggers_on_absolute_threshold(self) -> None:
        future = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2026-01-12", "2026-01-19"]),
                "incidence": [8.0, 12.0],
            }
        )
        history = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2025-12-29", "2026-01-05"]),
                "incidence": [4.0, 5.0],
            }
        )
        label, event_date = label_wave_start(
            future,
            history,
            WaveLabelConfig(absolute_threshold=10.0, seasonal_zscore_threshold=10.0, growth_observations=2, growth_min_relative_increase=10.0),
        )
        self.assertEqual(label, 1)
        self.assertEqual(event_date, pd.Timestamp("2026-01-19"))

    def test_label_wave_start_triggers_on_seasonal_zscore(self) -> None:
        future = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2026-01-12"]),
                "incidence": [9.0],
            }
        )
        history = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2025-01-13", "2025-01-20", "2025-01-27"]),
                "incidence": [2.0, 2.0, 2.0],
            }
        )
        label, event_date = label_wave_start(
            future,
            history,
            WaveLabelConfig(absolute_threshold=20.0, seasonal_zscore_threshold=1.5, growth_observations=2, growth_min_relative_increase=0.5),
        )
        self.assertEqual(label, 1)
        self.assertEqual(event_date, pd.Timestamp("2026-01-12"))

    def test_label_wave_start_triggers_on_sustained_growth(self) -> None:
        future = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2026-01-12", "2026-01-19", "2026-01-26"]),
                "incidence": [4.0, 5.0, 7.0],
            }
        )
        history = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2025-12-29", "2026-01-05"]),
                "incidence": [3.0, 3.0],
            }
        )
        label, event_date = label_wave_start(
            future,
            history,
            WaveLabelConfig(absolute_threshold=20.0, seasonal_zscore_threshold=5.0, growth_observations=3, growth_min_relative_increase=0.5),
        )
        self.assertEqual(label, 1)
        self.assertEqual(event_date, pd.Timestamp("2026-01-12"))

    def test_label_wave_start_returns_negative_when_rules_do_not_fire(self) -> None:
        future = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2026-01-12", "2026-01-19"]),
                "incidence": [4.0, 4.0],
            }
        )
        history = pd.DataFrame(
            {
                "week_start": pd.to_datetime(["2025-12-29", "2026-01-05"]),
                "incidence": [4.0, 4.0],
            }
        )
        label, event_date = label_wave_start(
            future,
            history,
            WaveLabelConfig(absolute_threshold=20.0, seasonal_zscore_threshold=5.0, growth_observations=2, growth_min_relative_increase=0.5),
        )
        self.assertEqual(label, 0)
        self.assertIsNone(event_date)

    def test_walk_forward_splits_are_time_ordered(self) -> None:
        dates = pd.date_range("2026-01-01", periods=60, freq="D")
        splits = build_backtest_splits(dates, n_splits=3, min_train_periods=20, min_test_periods=7)
        self.assertTrue(splits)
        for train_dates, test_dates in splits:
            self.assertLess(max(train_dates), min(test_dates))


class WavePredictionServiceTests(unittest.TestCase):
    def test_panel_builder_preserves_as_of_safety_for_weekly_truth(self) -> None:
        service = _FakeWavePredictionService()
        panel = service.build_wave_panel(
            pathogen="Influenza A",
            region="BY",
            lookback_days=25,
            horizon_days=14,
        )
        self.assertFalse(panel.empty)
        early_row = panel.loc[panel["as_of_date"] == pd.Timestamp("2025-12-21")].tail(1)
        self.assertFalse(early_row.empty)
        self.assertEqual(float(early_row.iloc[0]["truth_level"]), 15.044)
        later_row = panel.loc[panel["as_of_date"] == pd.Timestamp("2025-12-22")].tail(1)
        self.assertFalse(later_row.empty)
        self.assertEqual(float(later_row.iloc[0]["truth_level"]), 14.513)
        self.assertLessEqual(
            pd.Timestamp(later_row.iloc[0]["source_truth_available_date"]),
            pd.Timestamp(later_row.iloc[0]["as_of_date"]),
        )

    def test_panel_builder_handles_missing_optional_sources(self) -> None:
        class _SparseService(_FakeWavePredictionService):
            def _load_source_frames(self, *, pathogen: str, start_date: pd.Timestamp, end_date: pd.Timestamp) -> dict:
                payload = super()._load_source_frames(pathogen=pathogen, start_date=start_date, end_date=end_date)
                payload["grippeweb"] = pd.DataFrame()
                payload["are_consultation"] = pd.DataFrame()
                return payload

        service = _SparseService()
        panel = service.build_wave_panel(pathogen="Influenza A", region="BY", lookback_days=20, horizon_days=14)
        self.assertFalse(panel.empty)
        self.assertIn("grippeweb_are_available", panel.columns)
        self.assertEqual(float(panel.iloc[-1]["grippeweb_are_available"]), 0.0)

    def test_feature_whitelist_excludes_targets_and_identifiers(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(["2026-01-01"]),
                "region": ["BY"],
                "pathogen": ["Influenza A"],
                "target_regression": [10.0],
                "target_wave14": [1],
                "wave_event_date": [pd.Timestamp("2026-01-10")],
                "truth_level": [3.0],
                "wastewater_level": [2.0],
            }
        )
        features = get_classification_feature_columns(frame)
        self.assertEqual(features, ["truth_level", "wastewater_level"])

    def test_backtest_omits_oof_predictions_by_default(self) -> None:
        service = _FakeWavePredictionService()
        panel = service.build_wave_panel(
            pathogen="Influenza A",
            region="BY",
            lookback_days=TEST_SETTINGS.WAVE_PREDICTION_LOOKBACK_DAYS,
            horizon_days=14,
        )
        training_frame = panel.dropna(subset=["target_regression", "target_wave14"]).copy()
        result = service.run_wave_backtest(
            pathogen="Influenza A",
            region="BY",
            horizon_days=14,
            panel=training_frame,
        )
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("oof_predictions", result)

    def test_backtest_returns_serialized_oof_predictions_when_requested(self) -> None:
        service = _FakeWavePredictionService()
        panel = service.build_wave_panel(
            pathogen="Influenza A",
            region="BY",
            lookback_days=TEST_SETTINGS.WAVE_PREDICTION_LOOKBACK_DAYS,
            horizon_days=14,
        )
        training_frame = panel.dropna(subset=["target_regression", "target_wave14"]).copy()
        result = service.run_wave_backtest(
            pathogen="Influenza A",
            region="BY",
            horizon_days=14,
            panel=training_frame,
            include_oof_predictions=True,
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("oof_predictions", result)
        self.assertGreater(len(result["oof_predictions"]), 0)
        first_row = result["oof_predictions"][0]
        self.assertIn("fold", first_row)
        self.assertIn("decision_score", first_row)
        self.assertIn("score_output_field", first_row)
        self.assertIn(first_row["score_output_field"], {"wave_probability", "wave_score"})
        self.assertIn("tp", result["folds"][0])
        self.assertIn("confusion_matrix", result["aggregate_metrics"])

    def test_weather_forecast_features_ignore_rows_not_yet_available(self) -> None:
        weather = pd.DataFrame(
            {
                "bundesland": ["BY"] * 4,
                "datum": pd.to_datetime(["2026-01-10", "2026-01-11", "2026-01-12", "2026-01-13"]),
                "available_time": pd.to_datetime(["2026-01-10", "2026-01-08", "2026-01-15", "2026-01-09"]),
                "data_type": ["CURRENT", "DAILY_FORECAST", "DAILY_FORECAST", "DAILY_FORECAST"],
                "temp": [2.0, 10.0, 99.0, 12.0],
                "humidity": [70.0, 60.0, 5.0, 58.0],
            }
        )

        features = weather_context_features(
            weather,
            as_of=pd.Timestamp("2026-01-10"),
            enable_forecast_weather=True,
        )

        self.assertAlmostEqual(features["weather_forecast_avg_temp_next_7"], 11.0, places=6)
        self.assertAlmostEqual(features["weather_forecast_avg_humidity_next_7"], 59.0, places=6)

    def test_select_classification_threshold_can_tune_below_default(self) -> None:
        service = _FakeWavePredictionService()
        threshold = service._select_classification_threshold(
            np.array([1, 1, 0, 0]),
            np.array([0.08, 0.07, 0.02, 0.01]),
            default_threshold=0.5,
        )
        self.assertLess(threshold, 0.5)
        self.assertAlmostEqual(threshold, 0.07, places=6)

    def test_resolve_decision_strategy_drops_calibration_when_holdout_f1_gets_worse(self) -> None:
        service = _FakeWavePredictionService()

        class _BadCalibration:
            def predict(self, scores):
                del scores
                return np.array([0.0, 0.0, 1.0, 1.0])

        result = service._resolve_decision_strategy(
            y_true=np.array([1, 1, 0, 0]),
            raw_scores=np.array([0.08, 0.07, 0.02, 0.01]),
            calibration=_BadCalibration(),
            default_threshold=0.5,
        )

        self.assertFalse(result["use_calibration"])
        self.assertLess(result["threshold"], 0.5)
        self.assertTrue(any("degraded holdout decision quality" in note for note in result["notes"]))

    def test_prediction_uses_wave_score_when_calibration_missing(self) -> None:
        service = _FakeWavePredictionService()
        row = pd.DataFrame(
            {
                "truth_level": [1.0],
                "wastewater_level": [2.0],
                "as_of_date": [pd.Timestamp("2026-01-20")],
                "region": ["BY"],
                "pathogen": ["Influenza A"],
            }
        )

        class _DummyClassifier:
            def predict_proba(self, X):
                del X
                return np.array([[0.2, 0.8]])

        class _DummyRegressor:
            def predict(self, X):
                del X
                return np.array([np.log1p(15.0)])

        service.build_wave_panel = lambda **kwargs: row  # type: ignore[assignment]
        service._load_artifacts = lambda pathogen: {  # type: ignore[assignment]
            "classifier": _DummyClassifier(),
            "regressor": _DummyRegressor(),
            "calibration": None,
            "metadata": {
                "regression_feature_columns": ["truth_level", "wastewater_level"],
                "classification_feature_columns": ["truth_level", "wastewater_level"],
                "classification_threshold": 0.5,
                "model_version": "wave_prediction_v1:test",
                "top_features": {"wastewater_level": 0.8},
            },
        }
        payload = service.run_wave_prediction(pathogen="Influenza A", region="BY", horizon_days=14)
        self.assertIn("wave_score", payload)
        self.assertNotIn("wave_probability", payload)
        self.assertTrue(any("wave_score" in note for note in payload["notes"]))

    def test_prediction_uses_wave_probability_when_calibration_exists(self) -> None:
        service = _FakeWavePredictionService()
        row = pd.DataFrame(
            {
                "truth_level": [1.0],
                "wastewater_level": [2.0],
                "as_of_date": [pd.Timestamp("2026-01-20")],
                "region": ["BY"],
                "pathogen": ["Influenza A"],
            }
        )

        class _DummyClassifier:
            def predict_proba(self, X):
                del X
                return np.array([[0.4, 0.6]])

        class _DummyRegressor:
            def predict(self, X):
                del X
                return np.array([np.log1p(12.0)])

        class _DummyCalibration:
            def predict(self, scores):
                return np.asarray(scores) * 0.5

        service.build_wave_panel = lambda **kwargs: row  # type: ignore[assignment]
        service._load_artifacts = lambda pathogen: {  # type: ignore[assignment]
            "classifier": _DummyClassifier(),
            "regressor": _DummyRegressor(),
            "calibration": _DummyCalibration(),
            "metadata": {
                "regression_feature_columns": ["truth_level", "wastewater_level"],
                "classification_feature_columns": ["truth_level", "wastewater_level"],
                "classification_threshold": 0.2,
                "model_version": "wave_prediction_v1:test",
                "top_features": {"truth_level": 0.7},
            },
        }
        payload = service.run_wave_prediction(pathogen="Influenza A", region="BY", horizon_days=14)
        self.assertIn("wave_probability", payload)
        self.assertNotIn("wave_score", payload)

    def test_prediction_payload_contains_expected_metadata(self) -> None:
        service = _FakeWavePredictionService()
        row = pd.DataFrame(
            {
                "truth_level": [1.0],
                "wastewater_level": [2.0],
                "as_of_date": [pd.Timestamp("2026-01-20")],
                "region": ["BY"],
                "pathogen": ["Influenza A"],
            }
        )

        class _DummyClassifier:
            def predict_proba(self, X):
                del X
                return np.array([[0.4, 0.6]])

        class _DummyRegressor:
            def predict(self, X):
                del X
                return np.array([np.log1p(12.0)])

        service.build_wave_panel = lambda **kwargs: row  # type: ignore[assignment]
        service._load_artifacts = lambda pathogen: {  # type: ignore[assignment]
            "classifier": _DummyClassifier(),
            "regressor": _DummyRegressor(),
            "calibration": None,
            "metadata": {
                "regression_feature_columns": ["truth_level", "wastewater_level"],
                "classification_feature_columns": ["truth_level", "wastewater_level"],
                "classification_threshold": 0.2,
                "model_version": "wave_prediction_v1:test",
                "top_features": {"truth_level": 0.7},
            },
        }
        payload = service.run_wave_prediction(pathogen="Influenza A", region="BY", horizon_days=14)
        self.assertEqual(payload["pathogen"], "Influenza A")
        self.assertEqual(payload["region"], "BY")
        self.assertEqual(payload["horizon_days"], 14)
        self.assertIn("regression_forecast", payload)
        self.assertIn("wave_flag", payload)
        self.assertIn("model_version", payload)
        self.assertIn("top_features", payload)
