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
        self.assertEqual(features["hw_pred"], 10.0)
        self.assertEqual(features["prophet_pred"], 12.0)


if __name__ == "__main__":
    unittest.main()
