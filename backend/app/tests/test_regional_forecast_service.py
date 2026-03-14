import unittest

import numpy as np
import pandas as pd

from app.services.ml.regional_forecast import RegionalForecastService


class _DummyClassifier:
    def __init__(self, probabilities):
        self._probabilities = np.asarray(probabilities, dtype=float)

    def predict_proba(self, X):
        probs = self._probabilities[: len(X)]
        return np.column_stack([1.0 - probs, probs])


class _DummyRegressor:
    def __init__(self, outputs):
        self._outputs = np.asarray(outputs, dtype=float)

    def predict(self, X):
        return self._outputs[: len(X)]


class _FakeFeatureBuilder:
    def __init__(self, frame: pd.DataFrame, as_of_date: str):
        self._frame = frame
        self._as_of_date = pd.Timestamp(as_of_date)

    def latest_available_as_of_date(self, virus_typ: str = "Influenza A") -> pd.Timestamp:
        return self._as_of_date

    def build_inference_panel(
        self,
        virus_typ: str = "Influenza A",
        as_of_date=None,
        lookback_days: int = 180,
    ) -> pd.DataFrame:
        del virus_typ, as_of_date, lookback_days
        return self._frame.copy()


class RegionalForecastServiceTests(unittest.TestCase):
    def _make_service(self, *, quality_gate_passed: bool = True) -> RegionalForecastService:
        inference_panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BE"],
                "bundesland_name": ["Bayern", "Berlin"],
                "as_of_date": [pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-14")],
                "target_week_start": [pd.Timestamp("2026-03-16"), pd.Timestamp("2026-03-16")],
                "current_known_incidence": [10.0, 14.0],
                "seasonal_baseline": [8.0, 9.0],
                "seasonal_mad": [2.0, 2.5],
                "pollen_context_score": [1.5, 0.5],
                "f1": [1.0, 0.2],
                "f2": [0.1, 0.8],
            }
        )

        quality_gate = {
            "overall_passed": quality_gate_passed,
            "forecast_readiness": "GO" if quality_gate_passed else "WATCH",
        }
        metadata = {
            "feature_columns": ["f1", "f2"],
            "action_threshold": 0.6,
            "event_definition_version": "regional_survstat_v1",
            "quality_gate": quality_gate,
        }

        service = RegionalForecastService(db=None)
        service.feature_builder = _FakeFeatureBuilder(inference_panel, as_of_date="2026-03-14")
        service._load_artifacts = lambda virus_typ: {
            "classifier": _DummyClassifier([0.82, 0.41]),
            "regressor_median": _DummyRegressor(np.log1p([28.0, 12.0])),
            "regressor_lower": _DummyRegressor(np.log1p([24.0, 10.0])),
            "regressor_upper": _DummyRegressor(np.log1p([32.0, 15.0])),
            "calibration": None,
            "metadata": metadata,
        }
        return service

    def test_predict_all_regions_returns_calibrated_panel_payload(self) -> None:
        service = self._make_service(quality_gate_passed=True)

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

        self.assertEqual(result["virus_typ"], "Influenza A")
        self.assertEqual(result["target_window_days"], [3, 7])
        self.assertEqual(result["quality_gate"]["forecast_readiness"], "GO")
        self.assertEqual(result["total_regions"], 2)
        self.assertEqual(result["top_5"][0]["bundesland"], "BY")

        top = result["predictions"][0]
        self.assertEqual(top["event_definition_version"], "regional_survstat_v1")
        self.assertIn("event_probability_calibrated", top)
        self.assertIn("expected_next_week_incidence", top)
        self.assertEqual(top["prediction_interval"], {"lower": 24.0, "upper": 32.0})
        self.assertTrue(top["activation_candidate"])
        self.assertEqual(top["rank"], 1)

    def test_media_activation_downgrades_to_watch_when_quality_gate_fails(self) -> None:
        service = self._make_service(quality_gate_passed=False)

        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        self.assertEqual(result["summary"]["quality_gate"]["forecast_readiness"], "WATCH")
        self.assertEqual(result["summary"]["total_budget_allocated"], 0.0)
        self.assertTrue(all(item["action"] == "watch" for item in result["recommendations"]))
        self.assertTrue(all(item["budget_eur"] == 0.0 for item in result["recommendations"]))

    def test_predict_all_regions_breaks_calibrated_probability_ties_with_raw_score(self) -> None:
        inference_panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BE"],
                "bundesland_name": ["Bayern", "Berlin"],
                "as_of_date": [pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-14")],
                "target_week_start": [pd.Timestamp("2026-03-16"), pd.Timestamp("2026-03-16")],
                "current_known_incidence": [10.0, 14.0],
                "seasonal_baseline": [8.0, 9.0],
                "seasonal_mad": [2.0, 2.5],
                "pollen_context_score": [1.5, 0.5],
                "f1": [1.0, 0.2],
                "f2": [0.1, 0.8],
            }
        )
        metadata = {
            "feature_columns": ["f1", "f2"],
            "action_threshold": 0.6,
            "event_definition_version": "regional_survstat_v1",
            "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
        }

        class _FlatCalibration:
            def predict(self, values):
                return np.full(len(values), 0.5)

        service = RegionalForecastService(db=None)
        service.feature_builder = _FakeFeatureBuilder(inference_panel, as_of_date="2026-03-14")
        service._load_artifacts = lambda virus_typ: {
            "classifier": _DummyClassifier([0.35, 0.75]),
            "regressor_median": _DummyRegressor(np.log1p([28.0, 12.0])),
            "regressor_lower": _DummyRegressor(np.log1p([24.0, 10.0])),
            "regressor_upper": _DummyRegressor(np.log1p([32.0, 15.0])),
            "calibration": _FlatCalibration(),
            "metadata": metadata,
        }

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

        self.assertEqual(result["predictions"][0]["bundesland"], "BE")
        self.assertEqual(result["predictions"][0]["rank"], 1)
        self.assertEqual(result["predictions"][1]["bundesland"], "BY")


if __name__ == "__main__":
    unittest.main()
