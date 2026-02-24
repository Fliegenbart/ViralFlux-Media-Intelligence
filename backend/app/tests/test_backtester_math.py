import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.services.ml.backtester import BacktestService


class BacktesterMathTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
