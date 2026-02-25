import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.services.ml.backtester import BacktestService


class BacktesterMathTests(unittest.TestCase):
    def test_build_planning_curve_includes_issue_and_target_dates(self) -> None:
        class FakeQuery:
            def __init__(self, rows):
                self._rows = rows

            def filter(self, *args, **kwargs):
                return self

            def group_by(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return self._rows

        class FakeDB:
            def __init__(self, rows):
                self._rows = rows

            def query(self, *args, **kwargs):
                return FakeQuery(self._rows)

        weeks = pd.date_range("2024-01-01", periods=20, freq="W-MON")
        ww_rows = [
            SimpleNamespace(week=week.to_pydatetime(), avg_vl=float(idx + 1))
            for idx, week in enumerate(weeks)
        ]
        target_df = pd.DataFrame({
            "datum": weeks,
            "menge": np.linspace(10.0, 40.0, len(weeks)),
        })

        service = BacktestService(db=FakeDB(ww_rows))
        planning = service._build_planning_curve(target_df=target_df, virus_typ="Influenza A", days_back=4000)

        self.assertTrue(planning["curve"])
        first_point = planning["curve"][0]
        self.assertIn("issue_date", first_point)
        self.assertIn("target_date", first_point)
        self.assertEqual(first_point["date"], first_point["target_date"])
        self.assertEqual(first_point["based_on"], first_point["issue_date"])

    def test_augment_lead_lag_adds_horizon_to_relative_lag(self) -> None:
        lead_lag = {"best_lag_days": 0, "lag_correlation": 0.82}
        enriched = BacktestService._augment_lead_lag_with_horizon(lead_lag, horizon_days=7)

        self.assertEqual(enriched["relative_lag_days"], 0)
        self.assertEqual(enriched["effective_lead_days"], 7)
        self.assertTrue(enriched["bio_leads_target_effective"])
        self.assertFalse(enriched["target_leads_bio_effective"])

    def test_augment_lead_lag_detects_target_lead_when_effective_negative(self) -> None:
        lead_lag = {"best_lag_days": -10, "lag_correlation": 0.55}
        enriched = BacktestService._augment_lead_lag_with_horizon(lead_lag, horizon_days=7)

        self.assertEqual(enriched["effective_lead_days"], -3)
        self.assertFalse(enriched["bio_leads_target_effective"])
        self.assertTrue(enriched["target_leads_bio_effective"])

    def test_augment_lead_lag_requires_positive_correlation_for_lead_flags(self) -> None:
        lead_lag = {"best_lag_days": 4, "lag_correlation": -0.4}
        enriched = BacktestService._augment_lead_lag_with_horizon(lead_lag, horizon_days=7)

        self.assertEqual(enriched["effective_lead_days"], 11)
        self.assertFalse(enriched["bio_leads_target_effective"])
        self.assertFalse(enriched["target_leads_bio_effective"])

    def test_compute_forecast_metrics_smape_zero_for_perfect_forecast(self) -> None:
        y_true = np.array([10.0, 20.0, 30.0])
        y_pred = np.array([10.0, 20.0, 30.0])

        metrics = BacktestService._compute_forecast_metrics(y_true, y_pred)
        self.assertEqual(metrics["smape"], 0.0)
        self.assertEqual(metrics["mae"], 0.0)
        self.assertEqual(metrics["rmse"], 0.0)

    def test_compute_vintage_metrics_uses_lead_days_and_abs_error(self) -> None:
        records = [
            {"issue_date": "2024-01-01", "target_date": "2024-01-08", "y_hat": 105.0, "y_true": 100.0},
            {"issue_date": "2024-01-08", "target_date": "2024-01-15", "y_hat": 95.0, "y_true": 100.0},
            {"issue_date": "2024-01-15", "target_date": "2024-01-22", "y_hat": 102.0, "y_true": 100.0},
        ]

        metrics = BacktestService._compute_vintage_metrics(records, configured_horizon_days=7)
        self.assertEqual(metrics["configured_horizon_days"], 7)
        self.assertEqual(metrics["median_lead_days"], 7)
        self.assertEqual(metrics["oos_points"], 3)
        self.assertGreater(metrics["p90_abs_error"], 0.0)

    def test_compute_decision_metrics_counts_hits_false_alarms_and_misses(self) -> None:
        records = [
            {"issue_date": "2024-01-01", "target_date": "2024-01-08", "y_hat": 110.0, "y_true": 100.0},
            {"issue_date": "2024-01-08", "target_date": "2024-01-15", "y_hat": 130.0, "y_true": 140.0},  # hit
            {"issue_date": "2024-01-15", "target_date": "2024-01-22", "y_hat": 150.0, "y_true": 120.0},  # false alarm
            {"issue_date": "2024-01-22", "target_date": "2024-01-29", "y_hat": 110.0, "y_true": 150.0},  # miss
        ]

        metrics = BacktestService._compute_decision_metrics(records, threshold_pct=25.0)

        self.assertEqual(metrics["event_threshold_pct"], 25.0)
        self.assertEqual(metrics["alerts"], 2)
        self.assertEqual(metrics["events"], 2)
        self.assertEqual(metrics["hits"], 1)
        self.assertEqual(metrics["false_alarms"], 1)
        self.assertEqual(metrics["misses"], 1)
        self.assertEqual(metrics["hit_rate_pct"], 50.0)
        self.assertEqual(metrics["recall_pct"], 50.0)
        self.assertEqual(metrics["false_alarm_rate_pct"], 50.0)
        self.assertEqual(metrics["median_ttd_days"], 7)
        self.assertGreater(metrics["p90_abs_error"], 0.0)

    def test_compute_timing_metrics_detects_positive_lead(self) -> None:
        signal = [3.0, 1.0, 4.0, 2.0, 5.0, 0.5, 6.0, 1.5]
        records = [
            {
                "issue_date": (pd.Timestamp("2024-01-01") + pd.Timedelta(days=7 * idx)).strftime("%Y-%m-%d"),
                "target_date": (pd.Timestamp("2024-01-15") + pd.Timedelta(days=7 * idx)).strftime("%Y-%m-%d"),
                "y_hat": signal[idx],
                "y_true": signal[idx],
            }
            for idx in range(len(signal))
        ]

        timing = BacktestService._compute_timing_metrics(records, horizon_days=14)
        self.assertEqual(timing["configured_horizon_days"], 14)
        self.assertEqual(timing["best_lag_days"], 14)
        self.assertTrue(timing["lead_passed"])
        self.assertGreaterEqual(timing["corr_at_best_lag"], timing["corr_at_horizon"])

    def test_quality_gate_flags_pass_and_fail_conditions(self) -> None:
        passed = BacktestService._build_quality_gate(
            {
                "median_ttd_days": 14,
                "hit_rate_pct": 80.0,
                "error_relative_pct": 20.0,
            },
            timing_metrics={"best_lag_days": 14},
        )
        failed = BacktestService._build_quality_gate(
            {
                "median_ttd_days": 7,
                "hit_rate_pct": 60.0,
                "error_relative_pct": 50.0,
            },
            timing_metrics={"best_lag_days": 0},
        )

        self.assertTrue(passed["ttd_passed"])
        self.assertTrue(passed["hit_rate_passed"])
        self.assertTrue(passed["error_passed"])
        self.assertTrue(passed["lead_passed"])
        self.assertTrue(passed["overall_passed"])

        self.assertFalse(failed["ttd_passed"])
        self.assertFalse(failed["hit_rate_passed"])
        self.assertFalse(failed["error_passed"])
        self.assertFalse(failed["lead_passed"])
        self.assertFalse(failed["overall_passed"])

    def test_best_bio_lag_prefers_positive_alignment_over_stronger_negative(self) -> None:
        service = BacktestService(db=None)
        bio = np.array([
            1.764, 0.4, 0.979, 2.241, 1.868, -0.977, 0.95, -0.151, -0.103, 0.411,
            0.144, 1.454, 0.761, 0.122, 0.444, 0.334, 1.494, -0.205, 0.313, -0.854,
        ])
        target = np.array([
            -2.275, -0.269, 0.605, -2.069, -0.631, 2.479, 0.553, -0.668, 1.17, -0.238,
            -0.196, -1.05, -0.389, -0.676, -0.473, -0.924, -1.471, 0.541, -0.211, 0.722,
        ])
        dates = pd.date_range("2024-01-01", periods=len(bio), freq="D")
        df = pd.DataFrame({"date": dates, "bio": bio, "real_qty": target})

        lead_lag = service._best_bio_lead_lag(df, max_lag_points=6)
        lag0_corr = float(np.corrcoef(bio, target)[0, 1])

        self.assertLess(lag0_corr, 0.0)
        self.assertGreater(abs(lag0_corr), lead_lag["lag_correlation"])
        self.assertGreater(lead_lag["lag_correlation"], 0.0)

    def test_canonicalize_factor_weights_maps_enhanced_features(self) -> None:
        service = BacktestService(db=None)
        raw_weights = {
            "ww_lag0w": 0.4,
            "positivity_raw": 0.2,
            "target_level": 0.2,
            "trends_raw": 0.1,
            "weather_temp": 0.1,
        }

        canonical = service._canonicalize_factor_weights(raw_weights)

        self.assertEqual(set(canonical.keys()), {"bio", "market", "psycho", "context"})
        self.assertAlmostEqual(sum(canonical.values()), 1.0, places=2)
        self.assertGreater(canonical["bio"], canonical["psycho"])

    @patch("app.services.llm.vllm_service.generate_text_sync", side_effect=RuntimeError("vLLM down"))
    def test_generate_llm_insight_handles_noncanonical_weights(self, _llm_mock) -> None:
        service = BacktestService(db=None)
        text = service._generate_llm_insight(
            weights={
                "seasonal_baseline": 0.3,
                "ww_lag0w": 0.4,
                "target_level": 0.2,
                "trends_raw": 0.1,
            },
            r2=0.42,
            correlation=0.65,
            mae=12.0,
            n_samples=24,
            virus_typ="Influenza A",
        )

        self.assertIsInstance(text, str)
        self.assertIn("stärkste Einflussfaktor", text)

    @patch("app.services.ml.backtester.BacktestService._generate_llm_insight")
    @patch("app.services.ml.backtester.BacktestService._run_walk_forward_market_backtest")
    def test_run_calibration_uses_walk_forward_and_returns_oos_metadata(
        self,
        run_walk_forward_mock,
        llm_mock,
    ) -> None:
        llm_mock.return_value = "ok"
        run_walk_forward_mock.return_value = {
            "metrics": {
                "r2_score": 0.42,
                "correlation": 0.65,
                "correlation_pct": 65.0,
                "mae": 12.0,
                "smape": 18.5,
                "data_points": 10,
            },
            "optimized_weights": {"bio": 0.5, "market": 0.1, "psycho": 0.2, "context": 0.2},
            "default_weights": {"bio": 0.35, "market": 0.35, "psycho": 0.1, "context": 0.2},
            "chart_data": [
                {"date": "2024-01-01", "bio": 0.1, "real_qty": 10.0, "predicted_qty": 11.0},
                {"date": "2024-01-02", "bio": 0.2, "real_qty": 11.0, "predicted_qty": 12.0},
                {"date": "2024-01-03", "bio": 0.3, "real_qty": 12.0, "predicted_qty": 12.5},
                {"date": "2024-01-04", "bio": 0.2, "real_qty": 11.0, "predicted_qty": 11.2},
                {"date": "2024-01-05", "bio": 0.4, "real_qty": 14.0, "predicted_qty": 13.2},
                {"date": "2024-01-06", "bio": 0.5, "real_qty": 15.0, "predicted_qty": 14.4},
                {"date": "2024-01-07", "bio": 0.45, "real_qty": 14.5, "predicted_qty": 14.0},
                {"date": "2024-01-08", "bio": 0.35, "real_qty": 13.0, "predicted_qty": 13.4},
                {"date": "2024-01-09", "bio": 0.3, "real_qty": 12.5, "predicted_qty": 12.8},
                {"date": "2024-01-10", "bio": 0.25, "real_qty": 12.0, "predicted_qty": 12.2},
            ],
            "walk_forward": {"enabled": True, "folds": 10, "horizon_days": 7, "min_train_points": 5},
        }

        service = BacktestService(db=None)
        df = pd.DataFrame({
            "datum": pd.date_range("2024-01-01", periods=12, freq="D"),
            "menge": np.linspace(10, 21, 12),
        })

        result = service.run_calibration(
            df,
            virus_typ="Influenza A",
            horizon_days=7,
            min_train_points=20,
            strict_vintage_mode=True,
        )

        self.assertEqual(result["mode"], "CALIBRATION_OOS")
        self.assertIn("proof_text", result)
        self.assertIn("llm_insight", result)
        self.assertTrue(result["walk_forward"]["enabled"])
        self.assertEqual(result["walk_forward"]["calibration_mode"], "WALK_FORWARD_OOS")
        self.assertIn("lead_lag", result)
        run_walk_forward_mock.assert_called()

    def test_run_calibration_rejects_too_few_rows_for_oos(self) -> None:
        service = BacktestService(db=None)
        df = pd.DataFrame({
            "datum": pd.date_range("2024-01-01", periods=7, freq="D"),
            "menge": np.arange(7),
        })

        result = service.run_calibration(df, virus_typ="Influenza A")
        self.assertIn("error", result)

    @patch("app.services.ml.backtester.BacktestService._persist_backtest_result", return_value=None)
    @patch("app.services.ml.backtester.BacktestService._run_walk_forward_market_backtest")
    def test_run_customer_simulation_ignores_future_rows_for_metrics(
        self,
        run_walk_forward_mock,
        _persist_mock,
    ) -> None:
        run_walk_forward_mock.return_value = {
            "metrics": {"r2_score": 0.5},
            "chart_data": [
                {
                    "date": "2024-01-01",
                    "issue_date": "2023-12-25",
                    "target_date": "2024-01-01",
                    "real_qty": 10.0,
                    "predicted_qty": 11.0,
                    "baseline_persistence": 9.0,
                    "baseline_seasonal": 8.0,
                    "bio": 0.1,
                    "is_forecast": False,
                },
                {
                    "date": "2024-01-08",
                    "issue_date": "2024-01-01",
                    "target_date": "2024-01-08",
                    "real_qty": 20.0,
                    "predicted_qty": 19.0,
                    "baseline_persistence": 10.0,
                    "baseline_seasonal": 11.0,
                    "bio": 0.2,
                    "is_forecast": False,
                },
                {
                    "date": "2024-01-15",
                    "issue_date": "2024-01-08",
                    "target_date": "2024-01-15",
                    "forecast_qty": 22.0,
                    "is_forecast": True,
                },
            ],
            "forecast_records": [
                {"issue_date": "2023-12-25", "target_date": "2024-01-01", "lead_days": 7, "y_hat": 11.0, "y_true": 10.0, "horizon_days": 7},
                {"issue_date": "2024-01-01", "target_date": "2024-01-08", "lead_days": 7, "y_hat": 19.0, "y_true": 20.0, "horizon_days": 7},
            ],
            "walk_forward": {"enabled": True, "horizon_days": 7, "folds": 2},
        }

        service = BacktestService(db=None)
        df = pd.DataFrame({
            "datum": pd.date_range("2024-01-01", periods=8, freq="D"),
            "menge": np.linspace(10, 17, 8),
            "region": ["Gesamt"] * 8,
        })
        result = service.run_customer_simulation(
            customer_df=df,
            virus_typ="Influenza A",
            horizon_days=7,
            min_train_points=5,
            strict_vintage_mode=True,
        )

        self.assertEqual(result["metrics"]["data_points"], 2)
        self.assertIn("forecast_records", result)
        self.assertEqual(len(result["forecast_records"]), 2)
        self.assertEqual(result["forecast_records"][0]["lead_days"], 7)
        self.assertEqual(result["vintage_metrics"]["oos_points"], 2)


if __name__ == "__main__":
    unittest.main()
