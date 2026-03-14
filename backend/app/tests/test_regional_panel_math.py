import unittest
from datetime import datetime

import pandas as pd

from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    activation_false_positive_rate,
    build_event_label,
    choose_action_threshold,
    compute_ece,
    effective_available_time,
    first_week_start_in_window,
    median_lead_days,
    precision_at_k,
    seasonal_baseline_and_mad,
    time_based_panel_splits,
)


class RegionalPanelMathTests(unittest.TestCase):
    def test_effective_available_time_uses_source_lag_when_missing(self) -> None:
        reference = datetime(2026, 3, 3)
        effective = effective_available_time(reference, None, lag_days=7)
        self.assertEqual(str(effective.date()), "2026-03-10")

    def test_first_week_start_in_window_returns_week_inside_3_to_7_day_range(self) -> None:
        as_of = pd.Timestamp("2026-03-06")
        week_starts = [pd.Timestamp("2026-03-09"), pd.Timestamp("2026-03-16")]
        target = first_week_start_in_window(as_of, week_starts)
        self.assertEqual(target, pd.Timestamp("2026-03-09"))

    def test_build_event_label_requires_absolute_floor_for_small_bases(self) -> None:
        label = build_event_label(
            current_known_incidence=0.1,
            next_week_incidence=0.8,
            seasonal_baseline=0.2,
            seasonal_mad=0.1,
            tau=0.10,
            kappa=0.0,
        )
        self.assertEqual(label, 0)

    def test_build_event_label_requires_relative_and_absolute_jump(self) -> None:
        label = build_event_label(
            current_known_incidence=20.0,
            next_week_incidence=36.0,
            seasonal_baseline=22.0,
            seasonal_mad=4.0,
            tau=0.20,
            kappa=0.5,
        )
        self.assertEqual(label, 1)

    def test_seasonal_baseline_and_mad_handles_year_boundary(self) -> None:
        truth = pd.DataFrame(
            {
                "week_start": pd.to_datetime(
                    ["2023-12-25", "2024-01-01", "2024-12-30", "2025-01-06", "2025-12-29"]
                ),
                "incidence": [10.0, 12.0, 14.0, 16.0, 18.0],
            }
        )
        baseline, mad = seasonal_baseline_and_mad(truth, pd.Timestamp("2026-01-05"))
        self.assertGreaterEqual(baseline, 12.0)
        self.assertGreaterEqual(mad, 1.0)

    def test_time_based_panel_splits_never_use_future_dates_in_training(self) -> None:
        dates = pd.date_range("2024-01-01", periods=180, freq="D")
        splits = time_based_panel_splits(dates, n_splits=4, min_train_periods=90, min_test_periods=14)
        self.assertTrue(splits)
        for train_dates, test_dates in splits:
            self.assertLess(max(train_dates), min(test_dates))

    def test_choose_action_threshold_honours_minimum_recall(self) -> None:
        probabilities = [0.9, 0.8, 0.75, 0.6, 0.55, 0.3]
        labels = [1, 1, 0, 1, 0, 0]
        threshold, precision, recall = choose_action_threshold(probabilities, labels, min_recall=0.5)
        self.assertGreaterEqual(recall, 0.5)
        self.assertGreaterEqual(precision, 0.5)
        self.assertGreaterEqual(threshold, 0.35)

    def test_precision_at_k_and_false_positive_rate_work_per_snapshot(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(
                    ["2026-03-01", "2026-03-01", "2026-03-01", "2026-03-08", "2026-03-08", "2026-03-08"]
                ),
                "event_probability_calibrated": [0.8, 0.7, 0.2, 0.9, 0.6, 0.4],
                "event_label": [1, 0, 0, 1, 1, 0],
            }
        )
        self.assertAlmostEqual(precision_at_k(frame, k=2), 0.75, places=6)
        self.assertAlmostEqual(
            activation_false_positive_rate(frame, threshold=0.65),
            1.0 / 3.0,
            places=6,
        )

    def test_precision_at_k_uses_tie_breaker_column_for_stable_ranking(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(["2026-03-01", "2026-03-01", "2026-03-01"]),
                "event_probability_calibrated": [0.5, 0.5, 0.4],
                "event_probability_raw": [0.1, 0.9, 0.8],
                "event_label": [0, 1, 1],
            }
        )
        self.assertAlmostEqual(
            precision_at_k(
                frame,
                k=1,
                tie_breaker_col="event_probability_raw",
            ),
            1.0,
            places=6,
        )

    def test_compute_ece_zero_when_probabilities_match_observations_per_bin(self) -> None:
        y_true = [0, 0, 1, 1]
        probabilities = [0.0, 0.0, 1.0, 1.0]
        self.assertEqual(compute_ece(y_true, probabilities), 0.0)

    def test_compute_ece_accepts_pandas_series(self) -> None:
        y_true = pd.Series([0, 1, 1])
        probabilities = pd.Series([0.1, 0.8, 0.9])
        self.assertGreaterEqual(compute_ece(y_true, probabilities), 0.0)

    def test_dynamic_threshold_metrics_use_row_specific_thresholds(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(["2026-03-01", "2026-03-01", "2026-03-08"]),
                "target_week_start": pd.to_datetime(["2026-03-06", "2026-03-06", "2026-03-13"]),
                "event_probability_calibrated": [0.61, 0.59, 0.72],
                "event_label": [1, 0, 0],
                "action_threshold": [0.60, 0.60, 0.75],
            }
        )
        self.assertAlmostEqual(activation_false_positive_rate(frame, threshold=None), 0.0, places=6)
        self.assertAlmostEqual(median_lead_days(frame, threshold=None), 5.0, places=6)


class RegionalFeatureBuilderInferenceTests(unittest.TestCase):
    def test_inference_panel_uses_latest_available_row_when_as_of_has_no_exact_wastewater_date(self) -> None:
        class _FakeBuilder(RegionalFeatureBuilder):
            def __init__(self):
                self.db = None

            def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                for state in ("BY", "BE"):
                    for offset, value_date in enumerate(pd.date_range("2026-03-03", periods=10, freq="D"), start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp(value_date),
                                "available_time": pd.Timestamp(value_date),
                                "viral_load": float(5 + offset),
                                "site_count": 5,
                                "under_bg_share": 0.2,
                                "viral_std": 1.0,
                            }
                        )
                return pd.DataFrame(rows)

            def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                weeks = pd.date_range("2025-12-29", periods=12, freq="7D")
                for state in ("BY", "BE"):
                    for idx, week_start in enumerate(weeks, start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "week_start": pd.Timestamp(week_start),
                                "available_date": pd.Timestamp(week_start),
                                "incidence": float(idx * 5),
                                "truth_source": "survstat_weekly",
                            }
                        )
                return pd.DataFrame(rows)

            def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY", "BE"],
                        "datum": [pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-14")],
                        "available_time": [pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-14")],
                        "data_type": ["CURRENT", "CURRENT"],
                        "temp": [8.0, 7.0],
                        "humidity": [70.0, 72.0],
                    }
                )

            def _load_pollen(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY", "BE"],
                        "datum": [pd.Timestamp("2026-03-12"), pd.Timestamp("2026-03-12")],
                        "available_time": [pd.Timestamp("2026-03-12"), pd.Timestamp("2026-03-12")],
                        "pollen_index": [1.0, 2.0],
                    }
                )

            def _load_holidays(self) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
                return {}

        builder = _FakeBuilder()
        panel = builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        )

        self.assertEqual(len(panel), 2)
        self.assertEqual(sorted(panel["bundesland"].tolist()), ["BE", "BY"])
        self.assertTrue((panel["as_of_date"] == pd.Timestamp("2026-03-12")).all())


if __name__ == "__main__":
    unittest.main()
