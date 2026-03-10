import unittest

import numpy as np
import pandas as pd

from app.services.ml.forecast_service import ForecastService


class ForecastServiceGuardTests(unittest.TestCase):
    def test_finalize_training_frame_drops_warmup_rows_without_backfill(self) -> None:
        base = pd.Series(np.arange(20, dtype=float))
        raw = pd.DataFrame(
            {
                "ds": pd.date_range("2024-01-01", periods=20, freq="D"),
                "y": base,
                "trends_score": [np.nan] + [10.0] * 19,
                "schulferien": [0.0] * 20,
                "amelag_pred": base + 100.0,
                "xd_load": base / 10.0,
                "survstat_incidence": base / 20.0,
                "lag1": base.shift(1),
                "lag2": base.shift(2),
                "lag3": base.shift(3),
                "ma3": base.rolling(window=3, min_periods=1).mean().shift(1),
                "ma5": base.rolling(window=5, min_periods=1).mean().shift(1),
                "roc": base.pct_change().shift(1),
                "trend_momentum_7d": base.diff(periods=7) / base.shift(7).replace(0, np.nan),
                "amelag_lag4": (base + 100.0).shift(4),
                "amelag_lag7": (base + 100.0).shift(7),
                "xdisease_lag7": (base / 10.0).shift(7),
                "xdisease_lag14": (base / 10.0).shift(14),
                "survstat_lag7": (base / 20.0).shift(7),
                "survstat_lag14": (base / 20.0).shift(14),
            }
        )

        clean = ForecastService._finalize_training_frame(raw)

        self.assertEqual(len(clean), 6)
        self.assertEqual(clean.iloc[0]["ds"], raw.iloc[14]["ds"])
        self.assertEqual(clean.iloc[0]["lag1"], raw.iloc[14]["lag1"])
        self.assertFalse(clean.isna().any().any())

    def test_build_meta_feature_row_keeps_cross_disease_lags(self) -> None:
        row = pd.Series(
            {
                "amelag_lag4": 1.4,
                "amelag_lag7": 1.7,
                "trend_momentum_7d": 0.2,
                "schulferien": 1.0,
                "trends_score": 24.0,
                "xdisease_lag7": 0.7,
                "xdisease_lag14": 0.4,
                "survstat_incidence": 0.9,
                "survstat_lag7": 0.8,
                "survstat_lag14": 0.6,
                "lab_positivity_rate": 0.18,
                "lab_signal_available": 1.0,
                "lab_baseline_mean": 0.12,
                "lab_baseline_zscore": 1.5,
                "lab_positivity_lag7": 0.15,
            }
        )

        features = ForecastService._build_meta_feature_row(
            row,
            hw_pred=10.0,
            ridge_pred=11.0,
            prophet_pred=12.0,
        )

        self.assertEqual(features["xdisease_lag7"], 0.7)
        self.assertEqual(features["xdisease_lag14"], 0.4)
        self.assertEqual(features["lab_positivity_rate"], 0.18)
        self.assertEqual(features["lab_baseline_zscore"], 1.5)
        self.assertEqual(features["hw_pred"], 10.0)
        self.assertEqual(features["prophet_pred"], 12.0)

    def test_build_internal_history_feature_frame_respects_available_time(self) -> None:
        ds = pd.Series(pd.to_datetime(["2024-01-10", "2024-01-20"]))
        history = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2024-01-05", "2024-01-12", "2023-01-18", "2023-01-19"]),
                "available_time": pd.to_datetime(["2024-01-06", "2024-01-15", "2023-01-18", "2023-01-19"]),
                "anzahl_tests": [100, 200, 100, 120],
                "positive_ergebnisse": [20, 100, 10, 12],
            }
        )

        features = ForecastService._build_internal_history_feature_frame(ds, history)

        self.assertAlmostEqual(features.iloc[0]["lab_positivity_rate"], 0.2)
        self.assertAlmostEqual(features.iloc[1]["lab_positivity_rate"], 0.5)
        self.assertGreater(features.iloc[1]["lab_baseline_mean"], 0.0)
        self.assertNotEqual(features.iloc[1]["lab_baseline_zscore"], 0.0)

    def test_build_internal_history_feature_frame_falls_back_to_zero_without_history(self) -> None:
        ds = pd.Series(pd.to_datetime(["2024-01-10", "2024-01-20"]))

        features = ForecastService._build_internal_history_feature_frame(ds, pd.DataFrame())

        self.assertTrue((features == 0.0).all().all())


if __name__ == "__main__":
    unittest.main()
