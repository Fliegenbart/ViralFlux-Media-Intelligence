from contextlib import contextmanager
from datetime import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.ml.tasks import (
    _compute_accuracy_metrics,
    _persist_historical_backfill_rows,
    _resolve_accuracy_window_start,
    _select_forecast_accuracy_actual,
    _select_missing_backfill_targets,
    compute_forecast_accuracy_task,
)


class ForecastAccuracyTaskTests(unittest.TestCase):
    def test_persist_historical_backfill_rows_only_inserts_missing_targets(self) -> None:
        class _ForecastRow:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        db = MagicMock()
        existing_dates = {datetime(2026, 4, 2, 0, 0, 0)}
        windows = [
            {
                "issue_date": "2026-03-26T00:00:00",
                "target_date": "2026-04-02T00:00:00",
                "predicted": 100.0,
                "actual": 110.0,
                "event_probability": 0.3,
                "fold": 1,
            },
            {
                "issue_date": "2026-03-27T00:00:00",
                "target_date": "2026-04-03T00:00:00",
                "predicted": 120.0,
                "actual": 130.0,
                "event_probability": 0.6,
                "fold": 2,
            },
        ]

        result = _persist_historical_backfill_rows(
            db,
            windows=windows,
            existing_scope_dates=existing_dates,
            virus_typ="Influenza A",
            region="DE",
            horizon_days=7,
            model_version="historical_backfill_reconstructed_h7",
            ml_forecast_cls=_ForecastRow,
        )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped_existing"], 1)
        inserted_row = db.add.call_args.args[0]
        self.assertEqual(inserted_row.forecast_date, datetime(2026, 4, 3, 0, 0, 0))
        self.assertEqual(inserted_row.predicted_value, 120.0)
        self.assertEqual(inserted_row.model_version, "historical_backfill_reconstructed_h7")
        self.assertEqual(inserted_row.features_used["backfill_source"], "walk_forward_reconstruction")
        db.commit.assert_called_once_with()

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

    def test_select_missing_backfill_targets_respects_weekly_candidate_dates(self) -> None:
        result = _select_missing_backfill_targets(
            candidate_target_dates=[
                datetime(2026, 4, 1, 0, 0, 0),
                datetime(2026, 4, 8, 0, 0, 0),
                datetime(2026, 4, 15, 0, 0, 0),
            ],
            existing_scope_dates={datetime(2026, 4, 1, 0, 0, 0)},
            window_start=datetime(2026, 4, 1, 0, 0, 0),
            window_end=datetime(2026, 4, 8, 0, 0, 0),
        )

        self.assertEqual(result, [datetime(2026, 4, 8, 0, 0, 0)])

    def test_resolve_accuracy_window_start_anchors_to_minimum_recent_forecast_dates(self) -> None:
        fixed_now = datetime(2026, 4, 15, 10, 14, 16)
        recent_forecast_rows = [
            SimpleNamespace(forecast_date=datetime(2026, 4, 15, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 8, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 1, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 25, 0, 0, 0)),
        ]

        window_start = _resolve_accuracy_window_start(
            cutoff=fixed_now,
            recent_forecast_rows=recent_forecast_rows,
            default_days=14,
            minimum_pairs=3,
        )

        self.assertEqual(window_start, datetime(2026, 4, 1, 0, 0, 0))

    def test_resolve_accuracy_window_start_skips_unmatchable_latest_forecasts(self) -> None:
        fixed_now = datetime(2026, 4, 15, 10, 14, 16)
        recent_forecast_rows = [
            SimpleNamespace(forecast_date=datetime(2026, 4, 15, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 1, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 18, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 11, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 10, 0, 0, 0)),
        ]

        window_start = _resolve_accuracy_window_start(
            cutoff=fixed_now,
            recent_forecast_rows=recent_forecast_rows,
            actual_max_date=datetime(2026, 4, 8, 0, 0, 0),
            default_days=14,
            minimum_pairs=3,
        )

        self.assertEqual(window_start, datetime(2026, 3, 11, 0, 0, 0))

    def test_resolve_accuracy_window_start_prefers_deeper_evidence_when_available(self) -> None:
        fixed_now = datetime(2026, 4, 15, 10, 14, 16)
        recent_forecast_rows = [
            SimpleNamespace(forecast_date=datetime(2026, 4, 15, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 8, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 1, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 25, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 18, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 11, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 4, 0, 0, 0)),
        ]

        window_start = _resolve_accuracy_window_start(
            cutoff=fixed_now,
            recent_forecast_rows=recent_forecast_rows,
            default_days=14,
            minimum_pairs=3,
            target_pairs=7,
        )

        self.assertEqual(window_start, datetime(2026, 3, 4, 0, 0, 0))

    def test_resolve_accuracy_window_start_prefers_truly_comparable_dates(self) -> None:
        fixed_now = datetime(2026, 4, 15, 10, 14, 16)
        recent_forecast_rows = [
            SimpleNamespace(forecast_date=datetime(2026, 4, 15, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 1, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 18, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 11, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 10, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 9, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 8, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 7, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 6, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 5, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 4, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 2, 25, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 2, 18, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 2, 11, 0, 0, 0)),
        ]

        window_start = _resolve_accuracy_window_start(
            cutoff=fixed_now,
            recent_forecast_rows=recent_forecast_rows,
            actual_dates=[
                datetime(2026, 4, 8, 0, 0, 0),
                datetime(2026, 4, 1, 0, 0, 0),
                datetime(2026, 3, 25, 0, 0, 0),
                datetime(2026, 3, 18, 0, 0, 0),
                datetime(2026, 3, 11, 0, 0, 0),
                datetime(2026, 3, 4, 0, 0, 0),
                datetime(2026, 2, 25, 0, 0, 0),
                datetime(2026, 2, 18, 0, 0, 0),
                datetime(2026, 2, 11, 0, 0, 0),
            ],
            default_days=14,
            minimum_pairs=3,
            target_pairs=7,
        )

        self.assertEqual(window_start, datetime(2026, 2, 25, 0, 0, 0))

    def test_compute_forecast_accuracy_uses_frequency_aware_window_start(self) -> None:
        db = MagicMock()
        actual_max_query = MagicMock()
        actual_max_query.filter.return_value.scalar.return_value = datetime(2026, 4, 15, 0, 0, 0)
        recent_scope_query = MagicMock()
        recent_scope_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(forecast_date=datetime(2026, 4, 15, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 8, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 1, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 25, 0, 0, 0)),
        ]
        recent_actual_dates_query = MagicMock()
        recent_actual_dates_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            (datetime(2026, 4, 15, 0, 0, 0),),
            (datetime(2026, 4, 8, 0, 0, 0),),
            (datetime(2026, 4, 1, 0, 0, 0),),
            (datetime(2026, 3, 25, 0, 0, 0),),
        ]
        forecast_query = MagicMock()
        forecast_query.filter.return_value.order_by.return_value.all.return_value = []
        db.query.side_effect = [
            actual_max_query,
            recent_scope_query,
            recent_actual_dates_query,
            forecast_query,
        ]

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
        lower_bound = min(
            condition.right.value
            for condition in filter_args
            if isinstance(getattr(getattr(condition, "right", None), "value", None), datetime)
        )
        self.assertEqual(lower_bound, datetime(2026, 3, 25, 0, 0, 0))

    def test_compute_forecast_accuracy_skips_forecasts_without_actuals_when_resolving_window(self) -> None:
        db = MagicMock()
        recent_scope_query = MagicMock()
        recent_scope_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(forecast_date=datetime(2026, 4, 15, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 4, 1, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 18, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 11, 0, 0, 0)),
            SimpleNamespace(forecast_date=datetime(2026, 3, 10, 0, 0, 0)),
        ]
        actual_max_query = MagicMock()
        actual_max_query.filter.return_value.scalar.return_value = datetime(2026, 4, 8, 0, 0, 0)
        recent_actual_dates_query = MagicMock()
        recent_actual_dates_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            (datetime(2026, 4, 8, 0, 0, 0),),
            (datetime(2026, 4, 1, 0, 0, 0),),
            (datetime(2026, 3, 18, 0, 0, 0),),
            (datetime(2026, 3, 11, 0, 0, 0),),
        ]
        forecast_query = MagicMock()
        forecast_query.filter.return_value.order_by.return_value.all.return_value = []
        db.query.side_effect = [
            actual_max_query,
            recent_scope_query,
            recent_actual_dates_query,
            forecast_query,
        ]

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
        lower_bound = min(
            condition.right.value
            for condition in filter_args
            if isinstance(getattr(getattr(condition, "right", None), "value", None), datetime)
        )
        self.assertEqual(lower_bound, datetime(2026, 3, 10, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
