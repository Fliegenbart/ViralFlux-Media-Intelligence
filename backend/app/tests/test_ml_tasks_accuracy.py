import unittest
from types import SimpleNamespace

from app.services.ml.tasks import (
    _compute_accuracy_metrics,
    _select_forecast_accuracy_actual,
)


class ForecastAccuracyTaskTests(unittest.TestCase):
    def test_select_forecast_accuracy_actual_prefers_raw_viruslast(self) -> None:
        row = SimpleNamespace(viruslast=52371.4, viruslast_normalisiert=0.04)

        actual = _select_forecast_accuracy_actual(row)

        self.assertEqual(actual, 52371.4)

    def test_select_forecast_accuracy_actual_skips_normalized_only_rows(self) -> None:
        row = SimpleNamespace(viruslast=None, viruslast_normalisiert=0.04)

        actual = _select_forecast_accuracy_actual(row)

        self.assertIsNone(actual)

    def test_compute_accuracy_metrics_uses_like_for_like_values(self) -> None:
        metrics = _compute_accuracy_metrics(
            predicted=[100.0, 110.0, 120.0],
            actual=[100.0, 100.0, 100.0],
        )

        self.assertAlmostEqual(metrics["mae"], 10.0)
        self.assertAlmostEqual(metrics["rmse"], 12.909944, places=5)
        self.assertAlmostEqual(metrics["mape"], 10.0)


if __name__ == "__main__":
    unittest.main()
