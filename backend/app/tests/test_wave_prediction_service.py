import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.services.ml.wave_prediction_service import WavePredictionService
from app.services.ml.wave_prediction_utils import (
    WaveLabelConfig,
    build_backtest_splits,
    get_classification_feature_columns,
    label_wave_start,
)


TEST_SETTINGS = SimpleNamespace(
    WAVE_PREDICTION_HORIZON_DAYS=14,
    WAVE_PREDICTION_LOOKBACK_DAYS=120,
    WAVE_PREDICTION_MIN_TRAIN_ROWS=20,
    WAVE_PREDICTION_MIN_POSITIVE_ROWS=2,
    WAVE_PREDICTION_MODEL_VERSION="wave_prediction_v1",
    WAVE_PREDICTION_BACKTEST_FOLDS=3,
    WAVE_PREDICTION_MIN_TRAIN_PERIODS=30,
    WAVE_PREDICTION_MIN_TEST_PERIODS=7,
    WAVE_PREDICTION_CLASSIFICATION_THRESHOLD=0.5,
    WAVE_PREDICTION_ENABLE_FORECAST_WEATHER=True,
    WAVE_PREDICTION_ENABLE_DEMOGRAPHICS=True,
    WAVE_PREDICTION_ENABLE_INTERACTIONS=True,
    WAVE_PREDICTION_LABEL_ABSOLUTE_THRESHOLD=10.0,
    WAVE_PREDICTION_LABEL_SEASONAL_ZSCORE=1.5,
    WAVE_PREDICTION_LABEL_GROWTH_OBSERVATIONS=2,
    WAVE_PREDICTION_LABEL_GROWTH_MIN_RELATIVE_INCREASE=0.2,
    WAVE_PREDICTION_LABEL_MAD_FLOOR=1.0,
    WAVE_PREDICTION_CALIBRATION_HOLDOUT_FRACTION=0.2,
    WAVE_PREDICTION_MIN_CALIBRATION_ROWS=10,
    WAVE_PREDICTION_MIN_CALIBRATION_POSITIVES=2,
)


class _FakeWavePredictionService(WavePredictionService):
    def __init__(self):
        super().__init__(db=None, settings=TEST_SETTINGS)

    def _load_source_frames(self, *, pathogen: str, start_date: pd.Timestamp, end_date: pd.Timestamp) -> dict:
        del pathogen
        truth_rows = []
        for week_start, incidence in [
            ("2025-12-29", 6.0),
            ("2026-01-05", 7.0),
            ("2026-01-12", 8.0),
            ("2026-01-19", 9.0),
            ("2026-01-26", 11.0),
            ("2026-02-02", 13.0),
            ("2026-02-09", 12.0),
            ("2026-02-16", 10.0),
        ]:
            truth_rows.append(
                {
                    "bundesland": "BY",
                    "week_start": pd.Timestamp(week_start),
                    "available_date": pd.Timestamp(week_start) + pd.Timedelta(days=7),
                    "incidence": incidence,
                    "truth_source": "survstat_weekly",
                }
            )
        wastewater_dates = pd.date_range(start_date, end_date, freq="D")
        wastewater = pd.DataFrame(
            {
                "bundesland": ["BY"] * len(wastewater_dates),
                "datum": wastewater_dates,
                "available_time": wastewater_dates,
                "viral_load": np.linspace(1.0, 5.0, len(wastewater_dates)),
            }
        )
        grippeweb = pd.DataFrame(
            {
                "bundesland": ["BY", "BY"],
                "datum": [pd.Timestamp("2026-01-12"), pd.Timestamp("2026-01-19")],
                "available_time": [pd.Timestamp("2026-01-19"), pd.Timestamp("2026-01-26")],
                "signal_type": ["ARE", "ILI"],
                "incidence": [120.0, 70.0],
            }
        )
        are = pd.DataFrame(
            {
                "bundesland": ["BY", "BY"],
                "datum": [pd.Timestamp("2026-01-14"), pd.Timestamp("2026-01-21")],
                "available_time": [pd.Timestamp("2026-01-21"), pd.Timestamp("2026-01-28")],
                "incidence": [90.0, 95.0],
            }
        )
        weather = pd.DataFrame(
            {
                "bundesland": ["BY"] * 20,
                "datum": pd.date_range("2026-01-01", periods=20, freq="D"),
                "available_time": pd.date_range("2026-01-01", periods=20, freq="D"),
                "data_type": ["CURRENT"] * 13 + ["DAILY_FORECAST"] * 7,
                "temp": [2.0] * 20,
                "humidity": [70.0] * 20,
            }
        )
        return {
            "wastewater": wastewater,
            "truth": pd.DataFrame(truth_rows),
            "grippeweb": grippeweb,
            "influenza_ifsg": pd.DataFrame(),
            "rsv_ifsg": pd.DataFrame(),
            "are_consultation": are,
            "weather": weather,
            "holidays": {"BY": [(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-06"))]},
            "populations": {"BY": 13_500_000.0},
        }


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
        early_row = panel.loc[panel["as_of_date"] == pd.Timestamp("2026-01-10")].tail(1)
        self.assertFalse(early_row.empty)
        self.assertEqual(float(early_row.iloc[0]["truth_level"]), 6.0)
        later_row = panel.loc[panel["as_of_date"] == pd.Timestamp("2026-01-13")].tail(1)
        self.assertFalse(later_row.empty)
        self.assertEqual(float(later_row.iloc[0]["truth_level"]), 7.0)

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
