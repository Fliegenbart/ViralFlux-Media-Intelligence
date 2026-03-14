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
    event_definition_config_for_virus,
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

    def test_sars_cov_2_baseline_uses_recent_capped_history(self) -> None:
        truth = pd.DataFrame(
            {
                "week_start": pd.to_datetime(
                    [
                        "2022-06-06",
                        "2023-06-05",
                        "2024-06-03",
                        "2025-06-02",
                        "2025-06-09",
                        "2025-06-16",
                        "2025-06-23",
                        "2025-06-30",
                        "2025-07-07",
                        "2025-07-14",
                    ]
                ),
                "incidence": [160.0, 120.0, 80.0, 6.0, 7.0, 5.0, 6.0, 4.0, 5.0, 6.0],
            }
        )
        default_baseline, _ = seasonal_baseline_and_mad(truth, pd.Timestamp("2026-06-08"))
        sars_config = event_definition_config_for_virus("SARS-CoV-2")
        sars_baseline, sars_mad = seasonal_baseline_and_mad(
            truth,
            pd.Timestamp("2026-06-08"),
            max_history_weeks=sars_config.baseline_max_history_weeks,
            upper_quantile_cap=sars_config.baseline_upper_quantile_cap,
        )
        self.assertGreater(default_baseline, 40.0)
        self.assertLess(sars_baseline, default_baseline)
        self.assertLess(sars_baseline, 10.0)
        self.assertGreaterEqual(sars_mad, 1.0)

    def test_event_definition_config_exposes_sars_specific_override(self) -> None:
        default_config = event_definition_config_for_virus("Influenza A")
        sars_config = event_definition_config_for_virus("SARS-CoV-2")
        self.assertIsNone(default_config.baseline_max_history_weeks)
        self.assertEqual(sars_config.baseline_max_history_weeks, 104)
        self.assertEqual(sars_config.baseline_upper_quantile_cap, 0.75)
        self.assertIn(0.05, sars_config.tau_grid)

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
    def test_point_in_time_snapshot_manifest_tracks_as_of_range_and_signal_coverage(self) -> None:
        builder = RegionalFeatureBuilder(db=None)
        panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BE", "BY"],
                "as_of_date": pd.to_datetime(["2026-03-01", "2026-03-01", "2026-03-02"]),
                "truth_source": ["survstat_kreis", "survstat_kreis", "survstat_kreis"],
                "grippeweb_are_available": [1.0, 0.0, 1.0],
                "ifsg_influenza_available": [1.0, 1.0, 0.0],
                "ww_level": [2.0, 3.0, 4.0],
            }
        )

        snapshot = builder.point_in_time_snapshot_manifest("Influenza A", panel)

        self.assertEqual(snapshot["snapshot_type"], "regional_panel_as_of_training")
        self.assertEqual(snapshot["unique_as_of_dates"], 2)
        self.assertEqual(snapshot["dataset_manifest"]["source_coverage"]["grippeweb_are_available"], 0.6667)
        self.assertIn("ifsg_influenza_available", snapshot["dataset_manifest"]["source_coverage"])

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

            def _load_state_population_map(self) -> dict[str, float]:
                return {"BY": 13_500_000.0, "BE": 3_800_000.0}

        builder = _FakeBuilder()
        panel = builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        )

        self.assertEqual(len(panel), 2)
        self.assertEqual(sorted(panel["bundesland"].tolist()), ["BE", "BY"])
        self.assertTrue((panel["as_of_date"] == pd.Timestamp("2026-03-12")).all())

    def test_inference_panel_exposes_quality_spillover_and_cross_virus_features(self) -> None:
        class _FakeBuilder(RegionalFeatureBuilder):
            def __init__(self):
                self.db = None

            def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del start_date
                virus_offsets = {
                    "Influenza A": 10.0,
                    "Influenza B": 3.0,
                    "SARS-CoV-2": 6.0,
                    "RSV A": 4.0,
                }
                rows = []
                for state, site_base in (("BY", 6), ("BE", 4)):
                    for offset, value_date in enumerate(pd.date_range("2026-03-03", periods=10, freq="D"), start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp(value_date),
                                "available_time": pd.Timestamp(value_date),
                                "viral_load": float(virus_offsets[virus_typ] + offset),
                                "site_count": int(site_base + (offset % 3)),
                                "under_bg_share": float(max(0.0, 0.6 - offset * 0.03)),
                                "viral_std": float(0.5 + offset * 0.1),
                            }
                        )
                return pd.DataFrame(rows)

            def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                weeks = pd.date_range("2025-12-29", periods=12, freq="7D")
                for state, base in (("BY", 12.0), ("BE", 8.0)):
                    for idx, week_start in enumerate(weeks, start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "week_start": pd.Timestamp(week_start),
                                "available_date": pd.Timestamp(week_start),
                                "incidence": float(base + idx * 4),
                                "truth_source": "survstat_weekly",
                            }
                        )
                return pd.DataFrame(rows)

            def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY", "BE", "BY", "BE"],
                        "datum": [
                            pd.Timestamp("2026-03-11"),
                            pd.Timestamp("2026-03-11"),
                            pd.Timestamp("2026-03-15"),
                            pd.Timestamp("2026-03-15"),
                        ],
                        "available_time": [
                            pd.Timestamp("2026-03-11"),
                            pd.Timestamp("2026-03-11"),
                            pd.Timestamp("2026-03-12"),
                            pd.Timestamp("2026-03-12"),
                        ],
                        "data_type": ["CURRENT", "CURRENT", "DAILY_FORECAST", "DAILY_FORECAST"],
                        "temp": [7.0, 6.0, 10.0, 9.0],
                        "humidity": [72.0, 70.0, 64.0, 66.0],
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
                return {"BY": [(pd.Timestamp("2026-03-16"), pd.Timestamp("2026-03-18"))]}

            def _load_state_population_map(self) -> dict[str, float]:
                return {"BY": 13_500_000.0, "BE": 3_800_000.0}

        builder = _FakeBuilder()
        panel = builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        )

        self.assertIn("ww_site_count_delta7d", panel.columns)
        self.assertIn("ww_missing_days7d", panel.columns)
        self.assertIn("ww_under_bg_trend7d", panel.columns)
        self.assertIn("national_ww_slope7d", panel.columns)
        self.assertIn("ww_relative_to_national", panel.columns)
        self.assertIn("state_population_millions", panel.columns)
        self.assertIn("ww_sites_per_million", panel.columns)
        self.assertIn("xdisease_state_level_sars_cov_2", panel.columns)
        self.assertIn("xdisease_national_slope7d_rsv_a", panel.columns)

        by_row = panel.loc[panel["bundesland"] == "BY"].iloc[0]
        self.assertGreater(by_row["ww_site_count_delta7d"], 0.0)
        self.assertGreaterEqual(by_row["ww_missing_days7d"], 0.0)
        self.assertLess(by_row["ww_under_bg_trend7d"], 0.0)
        self.assertGreater(by_row["state_population_millions"], 10.0)
        self.assertGreater(by_row["xdisease_state_level_sars_cov_2"], 0.0)
        self.assertGreater(by_row["xdisease_national_level_influenza_b"], 0.0)

    def test_sars_inference_panel_exposes_hybrid_context_features_without_future_leakage(self) -> None:
        class _FakeBuilder(RegionalFeatureBuilder):
            def __init__(self):
                self.db = None

            def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del start_date
                rows = []
                for state, base in (("BY", 8.0), ("BE", 5.0)):
                    for offset, value_date in enumerate(pd.date_range("2026-03-03", periods=10, freq="D"), start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp(value_date),
                                "available_time": pd.Timestamp(value_date),
                                "viral_load": float(base + offset),
                                "site_count": 5 + (offset % 2),
                                "under_bg_share": float(0.5 - offset * 0.02),
                                "viral_std": float(0.4 + offset * 0.05),
                            }
                        )
                return pd.DataFrame(rows)

            def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                weeks = pd.date_range("2025-12-29", periods=12, freq="7D")
                for state, base in (("BY", 11.0), ("BE", 9.0)):
                    for idx, week_start in enumerate(weeks, start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "week_start": pd.Timestamp(week_start),
                                "available_date": pd.Timestamp(week_start),
                                "incidence": float(base + idx * 3),
                                "truth_source": "survstat_weekly",
                            }
                        )
                return pd.DataFrame(rows)

            def _load_are_konsultation(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY", "BY", "BE", "BE", "BY"],
                        "datum": pd.to_datetime(
                            ["2026-03-03", "2026-03-10", "2026-03-03", "2026-03-10", "2026-03-14"]
                        ),
                        "available_time": pd.to_datetime(
                            ["2026-03-04", "2026-03-11", "2026-03-04", "2026-03-11", "2026-03-16"]
                        ),
                        "incidence": [16.0, 22.0, 13.0, 15.0, 28.0],
                    }
                )

            def _load_notaufnahme_covid(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "datum": pd.to_datetime(["2026-03-05", "2026-03-12", "2026-03-14"]),
                        "available_time": pd.to_datetime(["2026-03-05", "2026-03-12", "2026-03-16"]),
                        "level": [0.09, 0.14, 0.30],
                        "ma7": [0.10, 0.16, 0.34],
                        "expected_value": [0.08, 0.11, 0.20],
                        "expected_upperbound": [0.12, 0.15, 0.25],
                    }
                )

            def _load_corona_test_trends(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                days = pd.date_range("2026-02-15", periods=29, freq="D")
                scores = [22 + (idx % 5) for idx in range(28)] + [90]
                available_times = list(days[:28]) + [pd.Timestamp("2026-03-16")]
                return pd.DataFrame(
                    {
                        "datum": days,
                        "available_time": available_times,
                        "interest_score": scores,
                    }
                )

            def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_pollen(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_holidays(self) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
                return {}

            def _load_state_population_map(self) -> dict[str, float]:
                return {"BY": 13_500_000.0, "BE": 3_800_000.0}

        builder = _FakeBuilder()
        panel = builder.build_inference_panel(
            virus_typ="SARS-CoV-2",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        )

        self.assertIn("sars_are_level", panel.columns)
        self.assertIn("sars_notaufnahme_ma7", panel.columns)
        self.assertIn("sars_trends_momentum_14_28", panel.columns)
        self.assertIn("sars_ww_are_log_gap", panel.columns)
        self.assertNotIn("sars_are_level", builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        ).columns)

        by_row = panel.loc[panel["bundesland"] == "BY"].iloc[0]
        self.assertAlmostEqual(by_row["sars_are_level"], 22.0, places=6)
        self.assertAlmostEqual(by_row["sars_notaufnahme_ma7"], 0.16, places=6)
        self.assertLess(by_row["sars_notaufnahme_upper_gap"], 0.02)
        self.assertEqual(by_row["sars_notaufnahme_breach_flag"], 1.0)
        self.assertLess(by_row["sars_trends_level"], 40.0)
        self.assertGreater(by_row["sars_ww_are_log_gap"], -2.0)

    def test_influenza_panel_exposes_grippeweb_and_ifsg_features_without_future_leakage(self) -> None:
        class _FakeBuilder(RegionalFeatureBuilder):
            def __init__(self):
                self.db = None

            def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                for state, base in (("BY", 10.0), ("BE", 7.0)):
                    for offset, value_date in enumerate(pd.date_range("2026-03-03", periods=10, freq="D"), start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp(value_date),
                                "available_time": pd.Timestamp(value_date),
                                "viral_load": float(base + offset),
                                "site_count": 5,
                                "under_bg_share": float(0.4 - offset * 0.02),
                                "viral_std": float(0.5 + offset * 0.05),
                            }
                        )
                return pd.DataFrame(rows)

            def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                weeks = pd.date_range("2025-12-29", periods=12, freq="7D")
                for state, base in (("BY", 9.0), ("BE", 6.0)):
                    for idx, week_start in enumerate(weeks, start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "week_start": pd.Timestamp(week_start),
                                "available_date": pd.Timestamp(week_start),
                                "incidence": float(base + idx * 2),
                                "truth_source": "survstat_weekly",
                            }
                        )
                return pd.DataFrame(rows)

            def _load_grippeweb_signals(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY", "BY", "BE", None, None],
                        "datum": pd.to_datetime(
                            ["2026-03-07", "2026-03-14", "2026-03-07", "2026-03-07", "2026-03-07"]
                        ),
                        "available_time": pd.to_datetime(
                            ["2026-03-08", "2026-03-16", "2026-03-08", "2026-03-08", "2026-03-08"]
                        ),
                        "signal_type": ["ARE", "ARE", "ARE", "ARE", "ILI"],
                        "incidence": [18.0, 40.0, 14.0, 12.0, 6.0],
                    }
                )

            def _load_influenza_ifsg(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY", "BY", "BE"],
                        "datum": pd.to_datetime(["2026-03-07", "2026-03-14", "2026-03-07"]),
                        "available_time": pd.to_datetime(["2026-03-08", "2026-03-16", "2026-03-08"]),
                        "incidence": [15.0, 50.0, 11.0],
                    }
                )

            def _load_rsv_ifsg(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame(
                    {
                        "bundesland": ["BY"],
                        "datum": [pd.Timestamp("2026-03-07")],
                        "available_time": [pd.Timestamp("2026-03-08")],
                        "incidence": [4.0],
                    }
                )

            def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_pollen(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_holidays(self) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
                return {}

            def _load_state_population_map(self) -> dict[str, float]:
                return {"BY": 13_500_000.0, "BE": 3_800_000.0}

        builder = _FakeBuilder()
        influenza_panel = builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        )
        sars_panel = builder.build_inference_panel(
            virus_typ="SARS-CoV-2",
            as_of_date=datetime(2026, 3, 14),
            lookback_days=90,
        )

        self.assertIn("grippeweb_are_level", influenza_panel.columns)
        self.assertIn("grippeweb_ili_level", influenza_panel.columns)
        self.assertIn("ifsg_influenza_level", influenza_panel.columns)
        self.assertNotIn("ifsg_rsv_level", influenza_panel.columns)
        self.assertNotIn("ifsg_influenza_level", sars_panel.columns)

        by_row = influenza_panel.loc[influenza_panel["bundesland"] == "BY"].iloc[0]
        self.assertAlmostEqual(by_row["grippeweb_are_level"], 18.0, places=6)
        self.assertAlmostEqual(by_row["ifsg_influenza_level"], 15.0, places=6)
        self.assertAlmostEqual(by_row["grippeweb_ili_level"], 6.0, places=6)
        self.assertEqual(by_row["grippeweb_are_available"], 1.0)
        self.assertEqual(by_row["ifsg_influenza_available"], 1.0)


if __name__ == "__main__":
    unittest.main()
