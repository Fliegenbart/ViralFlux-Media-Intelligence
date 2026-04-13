import unittest

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.services.ml.regional_trainer_backtest import build_backtest_payload
from app.services.ml import regional_trainer_events
from app.services.ml.regional_panel_utils import absolute_incidence_threshold


class H7EvidenceReportingTests(unittest.TestCase):
    def test_summarize_probabilistic_metrics_adds_reliability_and_baseline_crps(self) -> None:
        metrics = summarize_probabilistic_metrics(
            y_true=[10.0, 12.0, 14.0, 16.0, 18.0],
            quantile_predictions={
                0.1: [8.0, 10.0, 12.0, 14.0, 16.0],
                0.5: [10.0, 12.0, 14.0, 16.0, 18.0],
                0.9: [12.0, 14.0, 16.0, 18.0, 20.0],
            },
            baseline_quantiles={
                0.1: [7.0, 9.0, 11.0, 13.0, 15.0],
                0.5: [9.0, 11.0, 13.0, 15.0, 17.0],
                0.9: [11.0, 13.0, 15.0, 17.0, 19.0],
            },
            event_labels=[0, 0, 1, 1, 1],
            event_probabilities=[0.05, 0.15, 0.55, 0.75, 0.85],
            action_threshold=0.6,
        )

        self.assertIn("baseline_crps", metrics)
        self.assertIn("relative_crps", metrics)
        self.assertIn("reliability_curve_bins", metrics)
        self.assertIn("brier_reliability", metrics)
        self.assertIn("brier_resolution", metrics)
        self.assertIn("brier_uncertainty", metrics)
        self.assertEqual(len(metrics["reliability_curve_bins"]), 5)
        self.assertEqual(
            sum(int(item["count"]) for item in metrics["reliability_curve_bins"]),
            5,
        )
        reconstructed_brier = (
            float(metrics["brier_reliability"])
            - float(metrics["brier_resolution"])
            + float(metrics["brier_uncertainty"])
        )
        self.assertAlmostEqual(reconstructed_brier, float(metrics["brier_score"]), places=5)

    def test_event_threshold_matches_current_label_contract(self) -> None:
        thresholds = regional_trainer_events.event_threshold_from_context(
            current_known=[10.0],
            baseline=[8.0],
            mad=[2.0],
            tau=0.5,
            kappa=1.5,
            min_absolute_incidence=5.0,
            np_module=np,
            absolute_incidence_threshold_fn=absolute_incidence_threshold,
        )

        self.assertAlmostEqual(float(thresholds[0]), 17.135933977701413, places=6)

    def test_forecast_implied_event_probability_falls_when_tau_raises_threshold(self) -> None:
        probabilities_low_tau = regional_trainer_events.forecast_implied_event_probability(
            quantile_predictions={
                0.1: [12.0],
                0.5: [18.0],
                0.9: [30.0],
            },
            current_known=[10.0],
            baseline=[8.0],
            mad=[2.0],
            tau=0.1,
            kappa=0.5,
            min_absolute_incidence=5.0,
            np_module=np,
            absolute_incidence_threshold_fn=absolute_incidence_threshold,
        )
        probabilities_high_tau = regional_trainer_events.forecast_implied_event_probability(
            quantile_predictions={
                0.1: [12.0],
                0.5: [18.0],
                0.9: [30.0],
            },
            current_known=[10.0],
            baseline=[8.0],
            mad=[2.0],
            tau=0.8,
            kappa=0.5,
            min_absolute_incidence=5.0,
            np_module=np,
            absolute_incidence_threshold_fn=absolute_incidence_threshold,
        )

        self.assertGreater(float(probabilities_low_tau[0]), float(probabilities_high_tau[0]))

    def test_backtest_payload_surfaces_fold_identifiability_and_delta_confidence_intervals(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "fold": 0,
                    "virus_typ": "Influenza A",
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "as_of_date": pd.Timestamp("2026-01-01"),
                    "target_week_start": pd.Timestamp("2026-01-08"),
                    "horizon_days": 7,
                    "event_label": 0,
                    "event_probability_calibrated": 0.15,
                    "forecast_implied_event_probability": 0.22,
                    "persistence_probability": 0.30,
                    "climatology_probability": 0.05,
                    "amelag_only_probability": 0.10,
                    "absolute_error": 1.0,
                    "residual": -0.5,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 0,
                    "virus_typ": "Influenza A",
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "as_of_date": pd.Timestamp("2026-01-01"),
                    "target_week_start": pd.Timestamp("2026-01-08"),
                    "horizon_days": 7,
                    "event_label": 0,
                    "event_probability_calibrated": 0.12,
                    "forecast_implied_event_probability": 0.18,
                    "persistence_probability": 0.32,
                    "climatology_probability": 0.04,
                    "amelag_only_probability": 0.09,
                    "absolute_error": 1.2,
                    "residual": -0.4,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 1,
                    "virus_typ": "Influenza A",
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "as_of_date": pd.Timestamp("2026-01-02"),
                    "target_week_start": pd.Timestamp("2026-01-09"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.91,
                    "forecast_implied_event_probability": 0.87,
                    "persistence_probability": 0.55,
                    "climatology_probability": 0.08,
                    "amelag_only_probability": 0.25,
                    "absolute_error": 0.8,
                    "residual": 0.3,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 1,
                    "virus_typ": "Influenza A",
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "as_of_date": pd.Timestamp("2026-01-03"),
                    "target_week_start": pd.Timestamp("2026-01-10"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.88,
                    "forecast_implied_event_probability": 0.81,
                    "persistence_probability": 0.58,
                    "climatology_probability": 0.08,
                    "amelag_only_probability": 0.24,
                    "absolute_error": 0.7,
                    "residual": 0.2,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 1,
                    "virus_typ": "Influenza A",
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "as_of_date": pd.Timestamp("2026-01-03"),
                    "target_week_start": pd.Timestamp("2026-01-10"),
                    "horizon_days": 7,
                    "event_label": 0,
                    "event_probability_calibrated": 0.20,
                    "forecast_implied_event_probability": 0.27,
                    "persistence_probability": 0.45,
                    "climatology_probability": 0.06,
                    "amelag_only_probability": 0.15,
                    "absolute_error": 1.5,
                    "residual": -0.2,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 2,
                    "virus_typ": "Influenza A",
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "as_of_date": pd.Timestamp("2026-01-04"),
                    "target_week_start": pd.Timestamp("2026-01-11"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.93,
                    "forecast_implied_event_probability": 0.90,
                    "persistence_probability": 0.60,
                    "climatology_probability": 0.10,
                    "amelag_only_probability": 0.28,
                    "absolute_error": 0.4,
                    "residual": 0.1,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 2,
                    "virus_typ": "Influenza A",
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "as_of_date": pd.Timestamp("2026-01-04"),
                    "target_week_start": pd.Timestamp("2026-01-11"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.89,
                    "forecast_implied_event_probability": 0.84,
                    "persistence_probability": 0.57,
                    "climatology_probability": 0.09,
                    "amelag_only_probability": 0.26,
                    "absolute_error": 0.5,
                    "residual": 0.0,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 2,
                    "virus_typ": "Influenza A",
                    "bundesland": "HB",
                    "bundesland_name": "Bremen",
                    "as_of_date": pd.Timestamp("2026-01-05"),
                    "target_week_start": pd.Timestamp("2026-01-12"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.86,
                    "forecast_implied_event_probability": 0.80,
                    "persistence_probability": 0.56,
                    "climatology_probability": 0.09,
                    "amelag_only_probability": 0.27,
                    "absolute_error": 0.6,
                    "residual": 0.1,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 2,
                    "virus_typ": "Influenza A",
                    "bundesland": "HH",
                    "bundesland_name": "Hamburg",
                    "as_of_date": pd.Timestamp("2026-01-05"),
                    "target_week_start": pd.Timestamp("2026-01-12"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.82,
                    "forecast_implied_event_probability": 0.77,
                    "persistence_probability": 0.54,
                    "climatology_probability": 0.09,
                    "amelag_only_probability": 0.25,
                    "absolute_error": 0.7,
                    "residual": 0.2,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 2,
                    "virus_typ": "Influenza A",
                    "bundesland": "TH",
                    "bundesland_name": "Thüringen",
                    "as_of_date": pd.Timestamp("2026-01-06"),
                    "target_week_start": pd.Timestamp("2026-01-13"),
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": 0.80,
                    "forecast_implied_event_probability": 0.74,
                    "persistence_probability": 0.53,
                    "climatology_probability": 0.09,
                    "amelag_only_probability": 0.24,
                    "absolute_error": 0.9,
                    "residual": 0.3,
                    "action_threshold": 0.5,
                },
                {
                    "fold": 2,
                    "virus_typ": "Influenza A",
                    "bundesland": "SN",
                    "bundesland_name": "Sachsen",
                    "as_of_date": pd.Timestamp("2026-01-06"),
                    "target_week_start": pd.Timestamp("2026-01-13"),
                    "horizon_days": 7,
                    "event_label": 0,
                    "event_probability_calibrated": 0.24,
                    "forecast_implied_event_probability": 0.29,
                    "persistence_probability": 0.50,
                    "climatology_probability": 0.08,
                    "amelag_only_probability": 0.18,
                    "absolute_error": 1.1,
                    "residual": -0.3,
                    "action_threshold": 0.5,
                },
            ]
        )

        payload = build_backtest_payload(
            trainer=None,
            frame=frame,
            aggregate_metrics={"pr_auc": 0.8},
            baselines={"persistence": {"pr_auc": 0.5}},
            quality_gate={"overall_passed": False},
            tau=0.2,
            kappa=0.5,
            action_threshold=0.5,
            fold_selection_summary=[],
        )

        diagnostics_by_fold = {
            int(item["fold"]): item
            for item in payload["fold_diagnostics"]
        }

        self.assertEqual(diagnostics_by_fold[0]["positive_count"], 0)
        self.assertEqual(diagnostics_by_fold[0]["positive_regions"], 0)
        self.assertTrue(diagnostics_by_fold[0]["degeneration_flag"])
        self.assertFalse(diagnostics_by_fold[0]["low_information_flag"])

        self.assertEqual(diagnostics_by_fold[1]["positive_count"], 2)
        self.assertEqual(diagnostics_by_fold[1]["positive_regions"], 1)
        self.assertTrue(diagnostics_by_fold[1]["degeneration_flag"])
        self.assertTrue(diagnostics_by_fold[1]["low_information_flag"])

        self.assertEqual(diagnostics_by_fold[2]["positive_count"], 5)
        self.assertEqual(diagnostics_by_fold[2]["positive_regions"], 5)
        self.assertFalse(diagnostics_by_fold[2]["degeneration_flag"])
        self.assertFalse(diagnostics_by_fold[2]["low_information_flag"])

        self.assertIn("delta_vs_persistence", payload)
        self.assertIn("delta_ci_95", payload)
        self.assertIn("event_model", payload["delta_vs_persistence"])
        self.assertIn("persistence", payload["delta_ci_95"]["event_model"])
        self.assertIn("pr_auc", payload["delta_ci_95"]["event_model"]["persistence"])
        self.assertEqual(
            len(payload["delta_ci_95"]["event_model"]["persistence"]["pr_auc"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
