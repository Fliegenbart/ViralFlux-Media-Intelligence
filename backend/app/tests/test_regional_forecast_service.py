import unittest

import numpy as np
import pandas as pd

from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES


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

    def test_benchmark_supported_viruses_ranks_by_quality_and_metrics(self) -> None:
        service = RegionalForecastService(db=None)

        artifact_payloads = {
            "Influenza A": {
                "metadata": {
                    "trained_at": "2026-03-14T17:00:00",
                    "dataset_manifest": {"states": 16, "rows": 2083, "truth_source": "survstat_kreis"},
                    "aggregate_metrics": {
                        "precision_at_top3": 0.18,
                        "precision_at_top5": 0.17,
                        "pr_auc": 0.51,
                        "brier_score": 0.10,
                        "ece": 0.06,
                        "activation_false_positive_rate": 0.20,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "label_selection": {"tau": 0.15},
                }
            },
            "Influenza B": {
                "metadata": {
                    "trained_at": "2026-03-14T17:00:00",
                    "dataset_manifest": {"states": 16, "rows": 2081, "truth_source": "survstat_kreis"},
                    "aggregate_metrics": {
                        "precision_at_top3": 0.17,
                        "precision_at_top5": 0.16,
                        "pr_auc": 0.49,
                        "brier_score": 0.10,
                        "ece": 0.05,
                        "activation_false_positive_rate": 0.19,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "label_selection": {"tau": 0.10},
                }
            },
            "SARS-CoV-2": {
                "metadata": {
                    "trained_at": "2026-03-14T17:00:00",
                    "dataset_manifest": {"states": 16, "rows": 4042, "truth_source": "survstat_kreis"},
                    "aggregate_metrics": {
                        "precision_at_top3": 0.0,
                        "precision_at_top5": 0.0,
                        "pr_auc": 0.0,
                        "brier_score": 0.01,
                        "ece": 0.004,
                        "activation_false_positive_rate": 1.0,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "label_selection": {"tau": 0.10},
                }
            },
        }
        service._load_artifacts = lambda virus_typ: artifact_payloads.get(virus_typ, {})

        result = service.benchmark_supported_viruses(reference_virus="Influenza A")

        self.assertEqual(result["reference_virus"], "Influenza A")
        self.assertEqual(result["trained_viruses"], 3)
        self.assertEqual(result["benchmark"][0]["virus_typ"], "Influenza A")
        self.assertEqual(result["benchmark"][1]["virus_typ"], "Influenza B")
        self.assertEqual(result["benchmark"][-1]["virus_typ"], "RSV A")
        influenza_b = next(item for item in result["benchmark"] if item["virus_typ"] == "Influenza B")
        self.assertAlmostEqual(influenza_b["delta_vs_reference"]["precision_at_top3"], -0.01, places=6)

    def test_build_portfolio_view_prioritizes_cross_virus_opportunities(self) -> None:
        service = RegionalForecastService(db=None)

        artifact_payloads = {
            "Influenza A": {
                "metadata": {
                    "aggregate_metrics": {
                        "precision_at_top3": 0.18,
                        "precision_at_top5": 0.17,
                        "pr_auc": 0.51,
                        "brier_score": 0.10,
                        "ece": 0.06,
                        "activation_false_positive_rate": 0.20,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                }
            },
            "Influenza B": {
                "metadata": {
                    "aggregate_metrics": {
                        "precision_at_top3": 0.17,
                        "precision_at_top5": 0.16,
                        "pr_auc": 0.49,
                        "brier_score": 0.10,
                        "ece": 0.05,
                        "activation_false_positive_rate": 0.19,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                }
            },
        }
        service._load_artifacts = lambda virus_typ: artifact_payloads.get(virus_typ, {})
        service.predict_all_regions = lambda virus_typ, horizon_days=7: {
            "virus_typ": virus_typ,
            "as_of_date": "2026-03-06 00:00:00",
            "predictions": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "rank": 1,
                    "event_probability_calibrated": 0.62 if virus_typ == "Influenza A" else 0.67,
                    "expected_next_week_incidence": 28.0,
                    "prediction_interval": {"lower": 24.0, "upper": 32.0},
                    "current_known_incidence": 10.0,
                    "change_pct": 35.0 if virus_typ == "Influenza B" else 22.0,
                    "trend": "steigend",
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "action_threshold": 0.6,
                    "as_of_date": "2026-03-06 00:00:00",
                    "target_week_start": "2026-03-09 00:00:00",
                },
                {
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "rank": 2,
                    "event_probability_calibrated": 0.45,
                    "expected_next_week_incidence": 15.0,
                    "prediction_interval": {"lower": 12.0, "upper": 18.0},
                    "current_known_incidence": 11.0,
                    "change_pct": 9.0,
                    "trend": "stabil",
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "action_threshold": 0.6,
                    "as_of_date": "2026-03-06 00:00:00",
                    "target_week_start": "2026-03-09 00:00:00",
                },
            ],
        }

        result = service.build_portfolio_view(top_n=4, reference_virus="Influenza A")

        self.assertEqual(result["summary"]["trained_viruses"], 2)
        self.assertEqual(result["top_opportunities"][0]["virus_typ"], "Influenza B")
        self.assertEqual(result["top_opportunities"][0]["bundesland"], "BY")
        self.assertEqual(result["top_opportunities"][0]["portfolio_action"], "prioritize")
        self.assertEqual(result["region_rollup"][0]["leading_virus"], "Influenza B")
        self.assertIn("GeloMyrtol forte", result["top_opportunities"][0]["products"])
        self.assertEqual(len(result["benchmark"]), len(SUPPORTED_VIRUS_TYPES))


if __name__ == "__main__":
    unittest.main()
