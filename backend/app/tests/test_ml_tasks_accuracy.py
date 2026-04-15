from contextlib import contextmanager
from datetime import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.ml.tasks import (
    _compute_accuracy_metrics,
    _select_forecast_accuracy_actual,
    compute_forecast_accuracy_task,
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

    def test_compute_forecast_accuracy_uses_midnight_window_start_for_boundary_day(self) -> None:
        db = MagicMock()
        forecast_query = MagicMock()
        forecast_query.filter.return_value.order_by.return_value.all.return_value = []
        db.query.return_value = forecast_query

        @contextmanager
        def _db_context():
            yield db

        fixed_now = datetime(2026, 4, 15, 10, 14, 16)

        with (
            patch.object(compute_forecast_accuracy_task, "update_state"),
            patch("app.services.ml.tasks.get_db_context", return_value=_db_context()),
            patch("app.services.ml.tasks.SUPPORTED_VIRUS_TYPES", ("Influenza A",)),
            patch("app.services.ml.tasks.utc_now", return_value=fixed_now),
        ):
            compute_forecast_accuracy_task.run()

        filter_args = forecast_query.filter.call_args.args
        lower_bound = filter_args[2].right.value
        self.assertEqual(lower_bound, datetime(2026, 4, 1, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
