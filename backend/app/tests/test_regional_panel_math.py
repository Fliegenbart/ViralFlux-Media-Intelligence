import unittest
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.time import utc_now
from app.models.database import Base, KreisEinwohner, SurvstatKreisData, WeatherData
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
    quality_gate_from_metrics,
    seasonal_baseline_and_mad,
    time_based_panel_splits,
)
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_ISSUE_TIME_SEMANTICS,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
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

    def test_event_definition_config_exposes_influenza_b_and_rsv_specific_overrides(self) -> None:
        influenza_a_config = event_definition_config_for_virus("Influenza A")
        influenza_b_config = event_definition_config_for_virus("Influenza B")
        rsv_config = event_definition_config_for_virus("RSV A")

        self.assertEqual(influenza_a_config.min_absolute_incidence, 5.0)
        self.assertEqual(influenza_a_config.tau_grid, (0.10, 0.15, 0.20, 0.25, 0.30))
        self.assertEqual(influenza_a_config.kappa_grid, (0.0, 0.5, 1.0))
        self.assertEqual(influenza_a_config.min_recall_for_selection, 0.35)

        self.assertEqual(influenza_b_config.min_absolute_incidence, 4.0)
        self.assertIn(0.05, influenza_b_config.tau_grid)
        self.assertEqual(influenza_b_config.kappa_grid, (0.0, 0.25, 0.5))
        self.assertEqual(influenza_b_config.min_recall_for_selection, 0.25)

        self.assertEqual(rsv_config.min_absolute_incidence, 3.0)
        self.assertIn(0.05, rsv_config.tau_grid)
        self.assertEqual(rsv_config.kappa_grid, (0.0, 0.25, 0.5))
        self.assertEqual(rsv_config.min_recall_for_selection, 0.25)

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
        self.assertGreaterEqual(threshold, 0.05)

    def test_choose_action_threshold_can_select_below_legacy_floor_when_needed(self) -> None:
        probabilities = [0.22, 0.18, 0.07, 0.05]
        labels = [1, 1, 0, 0]

        threshold, precision, recall = choose_action_threshold(probabilities, labels, min_recall=0.5)

        self.assertLess(threshold, 0.35)
        self.assertGreaterEqual(recall, 0.5)
        self.assertGreaterEqual(precision, 0.5)

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

    def test_quality_gate_keeps_strict_profile_compatible_by_default(self) -> None:
        result = quality_gate_from_metrics(
            metrics={
                "precision_at_top3": 0.70,
                "activation_false_positive_rate": 0.25,
                "pr_auc": 0.60,
                "brier_score": 0.09,
                "ece": 0.05,
            },
            baseline_metrics={
                "persistence": {"pr_auc": 0.52},
                "climatology": {"pr_auc": 0.50, "brier_score": 0.10},
                "amelag_only": {"pr_auc": 0.48},
            },
        )

        self.assertTrue(result["overall_passed"])
        self.assertEqual(result["forecast_readiness"], "GO")
        self.assertEqual(result["profile"], "strict_v1")
        self.assertEqual(result["failed_checks"], [])

    def test_quality_gate_treats_zero_false_positive_rate_as_valid_signal(self) -> None:
        result = quality_gate_from_metrics(
            metrics={
                "precision_at_top3": 0.70,
                "activation_false_positive_rate": 0.0,
                "pr_auc": 0.60,
                "brier_score": 0.09,
                "ece": 0.05,
            },
            baseline_metrics={
                "persistence": {"pr_auc": 0.52},
                "climatology": {"pr_auc": 0.50, "brier_score": 0.10},
                "amelag_only": {"pr_auc": 0.48},
            },
        )

        self.assertTrue(result["checks"]["activation_fp_rate_passed"])
        self.assertTrue(result["overall_passed"])

    def test_quality_gate_uses_pilot_profile_only_for_day_one_pilot_scope(self) -> None:
        metrics = {
            "precision_at_top3": 0.63,
            "activation_false_positive_rate": 0.24,
            "pr_auc": 0.55,
            "brier_score": 0.096,
            "ece": 0.05,
        }
        baseline_metrics = {
            "persistence": {"pr_auc": 0.52},
            "climatology": {"pr_auc": 0.50, "brier_score": 0.10},
            "amelag_only": {"pr_auc": 0.48},
        }

        pilot_result = quality_gate_from_metrics(
            metrics=metrics,
            baseline_metrics=baseline_metrics,
            virus_typ="Influenza A",
            horizon_days=7,
        )
        strict_result = quality_gate_from_metrics(
            metrics=metrics,
            baseline_metrics=baseline_metrics,
            virus_typ="Influenza A",
            horizon_days=5,
        )

        self.assertEqual(pilot_result["profile"], "pilot_v1")
        self.assertTrue(pilot_result["overall_passed"])
        self.assertEqual(strict_result["profile"], "strict_v1")
        self.assertFalse(strict_result["overall_passed"])
        self.assertIn("precision_at_top3_passed", strict_result["failed_checks"])
        self.assertIn("brier_passed", strict_result["failed_checks"])


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
        self.assertEqual(
            snapshot["dataset_manifest"]["exogenous_feature_semantics_version"],
            "regional_exogenous_semantics_v1",
        )
        self.assertEqual(snapshot["unique_as_of_dates"], 2)
        self.assertEqual(snapshot["dataset_manifest"]["source_coverage"]["grippeweb_are_available"], 0.6667)
        self.assertEqual(snapshot["dataset_manifest"]["training_source_coverage"]["grippeweb_are_available"], 0.6667)
        self.assertIn("ifsg_influenza_available", snapshot["dataset_manifest"]["source_coverage"])
        self.assertEqual(
            snapshot["dataset_manifest"]["exogenous_feature_semantics"]["feature_categories"]["weather_daily_forecast"]["category"],
            "issue_time_forecast_allowed",
        )

    def test_weather_forecast_feature_requires_issue_time_semantics(self) -> None:
        as_of = pd.Timestamp("2026-03-12")
        weather_frame = pd.DataFrame(
            {
                "bundesland": ["BY", "BY"],
                "datum": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-15")],
                "available_time": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-12")],
                "data_type": ["CURRENT", "DAILY_FORECAST"],
                "temp": [7.0, 20.0],
                "humidity": [70.0, 40.0],
            }
        )

        features = RegionalFeatureBuilder._weather_features(
            weather_frame,
            as_of,
            horizon_days=3,
        )

        self.assertEqual(features["weather_forecast_temp_3_7"], 7.0)
        self.assertEqual(features["weather_forecast_humidity_3_7"], 70.0)
        self.assertEqual(features["weather_temp_anomaly_3_7"], 0.0)

    def test_weather_forecast_feature_allows_future_signal_with_issue_time(self) -> None:
        as_of = pd.Timestamp("2026-03-12")
        weather_frame = pd.DataFrame(
            {
                "bundesland": ["BY", "BY"],
                "datum": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-15")],
                "available_time": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-12")],
                "issue_time": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-12")],
                "data_type": ["CURRENT", "DAILY_FORECAST"],
                "temp": [7.0, 20.0],
                "humidity": [70.0, 40.0],
            }
        )

        features = RegionalFeatureBuilder._weather_features(
            weather_frame,
            as_of,
            horizon_days=3,
        )

        self.assertEqual(features["weather_forecast_temp_3_7"], 20.0)
        self.assertEqual(features["weather_forecast_humidity_3_7"], 40.0)
        self.assertEqual(features["weather_temp_anomaly_3_7"], 13.0)

    def test_weather_forecast_vintage_mode_picks_reproducible_run_for_same_as_of(self) -> None:
        as_of = pd.Timestamp("2026-03-12 09:00:00")
        baseline_frame = pd.DataFrame(
            {
                "bundesland": ["BY", "BY", "BY"],
                "datum": [
                    pd.Timestamp("2026-03-11"),
                    pd.Timestamp("2026-03-15"),
                    pd.Timestamp("2026-03-15"),
                ],
                "available_time": [
                    pd.Timestamp("2026-03-11 00:00:00"),
                    pd.Timestamp("2026-03-12 08:00:00"),
                    pd.Timestamp("2026-03-12 10:00:00"),
                ],
                "data_type": ["CURRENT", "DAILY_FORECAST", "DAILY_FORECAST"],
                "temp": [7.0, 14.0, 23.0],
                "humidity": [70.0, 52.0, 35.0],
                "forecast_run_timestamp": [
                    pd.NaT,
                    pd.Timestamp("2026-03-12 08:00:00"),
                    pd.Timestamp("2026-03-12 10:00:00"),
                ],
                "forecast_run_id": [
                    None,
                    "weather_run:2026-03-12T08:00:00",
                    "weather_run:2026-03-12T10:00:00",
                ],
            }
        )
        future_run_frame = pd.concat(
            [
                baseline_frame,
                pd.DataFrame(
                    {
                        "bundesland": ["BY"],
                        "datum": [pd.Timestamp("2026-03-15")],
                        "available_time": [pd.Timestamp("2026-03-13 07:00:00")],
                        "data_type": ["DAILY_FORECAST"],
                        "temp": [30.0],
                        "humidity": [20.0],
                        "forecast_run_timestamp": [pd.Timestamp("2026-03-13 07:00:00")],
                        "forecast_run_id": ["weather_run:2026-03-13T07:00:00"],
                    }
                ),
            ],
            ignore_index=True,
        )

        first_metadata: dict[str, object] = {}
        second_metadata: dict[str, object] = {}

        first_features = RegionalFeatureBuilder._weather_features(
            baseline_frame,
            as_of,
            horizon_days=3,
            vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            vintage_metadata=first_metadata,
        )
        second_features = RegionalFeatureBuilder._weather_features(
            future_run_frame,
            as_of,
            horizon_days=3,
            vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            vintage_metadata=second_metadata,
        )

        self.assertEqual(first_features, second_features)
        self.assertEqual(first_features["weather_forecast_temp_3_7"], 14.0)
        self.assertEqual(
            first_metadata["weather_forecast_selected_run_timestamp"],
            "2026-03-12T08:00:00",
        )
        self.assertEqual(
            second_metadata["weather_forecast_selected_run_timestamp"],
            "2026-03-12T08:00:00",
        )
        self.assertTrue(first_metadata["weather_forecast_run_identity_present"])
        self.assertFalse(first_metadata["weather_forecast_vintage_degraded"])

    def test_weather_forecast_vintage_mode_degrades_without_run_identity(self) -> None:
        as_of = pd.Timestamp("2026-03-12")
        weather_frame = pd.DataFrame(
            {
                "bundesland": ["BY", "BY"],
                "datum": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-15")],
                "available_time": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-12")],
                "data_type": ["CURRENT", "DAILY_FORECAST"],
                "temp": [7.0, 20.0],
                "humidity": [70.0, 40.0],
            }
        )

        metadata: dict[str, object] = {}
        features = RegionalFeatureBuilder._weather_features(
            weather_frame,
            as_of,
            horizon_days=3,
            vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            vintage_metadata=metadata,
        )

        self.assertEqual(features["weather_forecast_temp_3_7"], 7.0)
        self.assertEqual(features["weather_forecast_humidity_3_7"], 70.0)
        self.assertTrue(metadata["weather_forecast_vintage_degraded"])
        self.assertFalse(metadata["weather_forecast_run_identity_present"])

    def test_pollen_context_ignores_future_values_even_when_available_early(self) -> None:
        as_of = pd.Timestamp("2026-03-12")
        pollen_frame = pd.DataFrame(
            {
                "bundesland": ["BY", "BY"],
                "datum": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-15")],
                "available_time": [pd.Timestamp("2026-03-11"), pd.Timestamp("2026-03-12")],
                "pollen_index": [1.0, 3.0],
            }
        )

        pollen_context = RegionalFeatureBuilder._pollen_context(pollen_frame, as_of)

        self.assertEqual(pollen_context, 1.0)

    def test_inference_panel_manifest_tracks_weather_vintage_metadata(self) -> None:
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
                rows = []
                for state in ("BY", "BE"):
                    rows.extend(
                        [
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp("2026-03-11"),
                                "available_time": pd.Timestamp("2026-03-11"),
                                "data_type": "CURRENT",
                                "temp": 7.0,
                                "humidity": 70.0,
                                "issue_time": pd.Timestamp("2026-03-11 06:00:00"),
                                "forecast_run_timestamp": pd.Timestamp("2026-03-11 06:00:00"),
                                "forecast_run_id": "weather_run:2026-03-11T06:00:00",
                                "forecast_run_identity_source": "persisted_weather_ingest_run_v1",
                                "forecast_run_identity_quality": "stable_persisted_batch",
                            },
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp("2026-03-15"),
                                "available_time": pd.Timestamp("2026-03-12 00:00:00"),
                                "data_type": "DAILY_FORECAST",
                                "temp": 14.0,
                                "humidity": 52.0,
                                "issue_time": pd.Timestamp("2026-03-12 00:00:00"),
                                "forecast_run_timestamp": pd.Timestamp("2026-03-12 00:00:00"),
                                "forecast_run_id": "weather_run:2026-03-12T00:00:00",
                                "forecast_run_identity_source": "persisted_weather_ingest_run_v1",
                                "forecast_run_identity_quality": "stable_persisted_batch",
                            },
                        ]
                    )
                return pd.DataFrame(rows)

            def _load_supported_wastewater_context(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                return pd.DataFrame()

            def _load_grippeweb_signals(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_influenza_ifsg(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_rsv_ifsg(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_holidays(self) -> pd.DataFrame:
                return pd.DataFrame()

            def _load_state_population_map(self) -> dict[str, int]:
                return {"BY": 1000000, "BE": 500000}

            def _load_pollen(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

        builder = _FakeBuilder()
        panel = builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=pd.Timestamp("2026-03-12 09:00:00"),
            lookback_days=10,
            horizon_days=3,
            weather_forecast_vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
        )

        manifest = builder.dataset_manifest("Influenza A", panel)

        self.assertEqual(manifest["weather_forecast_vintage_mode"], WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1)
        self.assertEqual(
            manifest["weather_forecast_issue_time_semantics"],
            WEATHER_FORECAST_ISSUE_TIME_SEMANTICS,
        )
        self.assertTrue(manifest["weather_forecast_run_identity_present"])
        self.assertEqual(
            manifest["weather_forecast_run_identity_source"],
            "persisted_weather_ingest_run_v1",
        )
        self.assertEqual(
            manifest["weather_forecast_run_identity_quality"],
            "stable_persisted_batch",
        )

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

    def test_inference_panel_keeps_stale_region_for_explicit_coverage_decision(self) -> None:
        class _FakeBuilder(RegionalFeatureBuilder):
            def __init__(self):
                self.db = None

            def _load_wastewater_daily(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                for state, dates in {
                    "BY": pd.date_range("2026-03-10", periods=10, freq="D"),
                    "HH": pd.date_range("2026-02-20", periods=10, freq="D"),
                }.items():
                    for offset, value_date in enumerate(dates, start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "datum": pd.Timestamp(value_date),
                                "available_time": pd.Timestamp(value_date),
                                "viral_load": float(10 + offset),
                                "site_count": 5,
                                "under_bg_share": 0.2,
                                "viral_std": 1.0,
                            }
                        )
                return pd.DataFrame(rows)

            def _load_truth_series(self, virus_typ: str, start_date: pd.Timestamp) -> pd.DataFrame:
                del virus_typ, start_date
                rows = []
                weeks = pd.date_range("2025-12-22", periods=14, freq="7D")
                for state in ("BY", "HH"):
                    for idx, week_start in enumerate(weeks, start=1):
                        rows.append(
                            {
                                "bundesland": state,
                                "week_start": pd.Timestamp(week_start),
                                "available_date": pd.Timestamp(week_start),
                                "incidence": float(idx * 3),
                                "truth_source": "survstat_weekly",
                            }
                        )
                return pd.DataFrame(rows)

            def _load_weather(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_pollen(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
                del start_date, end_date
                return pd.DataFrame()

            def _load_holidays(self) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
                return {}

            def _load_state_population_map(self) -> dict[str, float]:
                return {"BY": 13_500_000.0, "HH": 1_900_000.0}

        builder = _FakeBuilder()
        panel = builder.build_inference_panel(
            virus_typ="Influenza A",
            as_of_date=datetime(2026, 3, 20),
            lookback_days=90,
            horizon_days=7,
        )

        self.assertEqual(sorted(panel["bundesland"].tolist()), ["BY", "HH"])
        as_of_by_state = dict(zip(panel["bundesland"], panel["as_of_date"], strict=True))
        self.assertEqual(as_of_by_state["BY"], pd.Timestamp("2026-03-19"))
        self.assertEqual(as_of_by_state["HH"], pd.Timestamp("2026-03-01"))

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

            def _load_notaufnahme_syndrome(
                self,
                start_date: pd.Timestamp,
                end_date: pd.Timestamp,
                syndrome: str,
            ) -> pd.DataFrame:
                del syndrome
                return self._load_notaufnahme_covid(start_date, end_date)

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

            def _load_trends_keywords(
                self,
                start_date: pd.Timestamp,
                end_date: pd.Timestamp,
                keywords: tuple[str, ...],
            ) -> pd.DataFrame:
                del keywords
                return self._load_corona_test_trends(start_date, end_date)

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


class RegionalLandkreisTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_load_landkreis_truth_series_exposes_available_date_and_skips_missing_population(self) -> None:
        self.db.add_all(
            [
                KreisEinwohner(
                    kreis_name="LK Ahrweiler",
                    ags="07131",
                    bundesland="Rheinland-Pfalz",
                    einwohner=132170,
                ),
                KreisEinwohner(
                    kreis_name="SK Berlin Mitte",
                    ags="11001",
                    bundesland="Berlin",
                    einwohner=0,
                ),
                SurvstatKreisData(
                    year=2026,
                    week=10,
                    week_label="2026_10",
                    kreis="LK Ahrweiler",
                    disease="influenza, saisonal",
                    fallzahl=132,
                    inzidenz=None,
                    created_at=utc_now(),
                ),
                SurvstatKreisData(
                    year=2026,
                    week=10,
                    week_label="2026_10",
                    kreis="SK Berlin Mitte",
                    disease="influenza, saisonal",
                    fallzahl=75,
                    inzidenz=None,
                    created_at=utc_now(),
                ),
                SurvstatKreisData(
                    year=2026,
                    week=11,
                    week_label="2026_11",
                    kreis="LK Ahrweiler",
                    disease="influenza, saisonal",
                    fallzahl=165,
                    inzidenz=None,
                    created_at=utc_now(),
                ),
            ]
        )
        self.db.commit()

        builder = RegionalFeatureBuilder(self.db)
        truth = builder.load_landkreis_truth_series("Influenza A", pd.Timestamp("2026-01-01"))

        self.assertEqual(sorted(truth["geo_unit_id"].unique().tolist()), ["07131"])
        self.assertTrue((truth["population"] > 0).all())
        self.assertEqual(truth["parent_bundesland"].iloc[0], "RP")
        self.assertEqual(str(truth["available_date"].iloc[0].date()), "2026-03-09")

        visible = truth.loc[truth["available_date"] <= pd.Timestamp("2026-03-10")].copy()
        self.assertEqual(len(visible), 1)
        self.assertEqual(str(visible["week_start"].iloc[0].date()), "2026-03-02")

    def test_load_weather_keeps_multiple_forecast_runs_separate_and_marks_identity_quality(self) -> None:
        self.db.add_all(
            [
                WeatherData(
                    city="München",
                    datum=datetime(2026, 3, 15, 12, 0),
                    available_time=datetime(2026, 3, 12, 8, 0),
                    temperatur=14.0,
                    luftfeuchtigkeit=52.0,
                    data_type="DAILY_FORECAST",
                    forecast_run_timestamp=datetime(2026, 3, 12, 8, 0),
                    forecast_run_id="weather_forecast_run:2026-03-12T08:00:00",
                    forecast_run_identity_source="persisted_weather_ingest_run_v1",
                    forecast_run_identity_quality="stable_persisted_batch",
                    created_at=datetime(2026, 3, 12, 8, 0),
                ),
                WeatherData(
                    city="München",
                    datum=datetime(2026, 3, 15, 12, 0),
                    available_time=datetime(2026, 3, 12, 10, 0),
                    temperatur=23.0,
                    luftfeuchtigkeit=35.0,
                    data_type="DAILY_FORECAST",
                    forecast_run_timestamp=datetime(2026, 3, 12, 10, 0),
                    forecast_run_id="weather_forecast_run:2026-03-12T10:00:00",
                    forecast_run_identity_source="persisted_weather_ingest_run_v1",
                    forecast_run_identity_quality="stable_persisted_batch",
                    created_at=datetime(2026, 3, 12, 10, 0),
                ),
            ]
        )
        self.db.commit()

        builder = RegionalFeatureBuilder(self.db)
        frame = builder._load_weather(pd.Timestamp("2026-03-10"), pd.Timestamp("2026-03-20"))

        forecast_rows = frame.loc[frame["data_type"] == "DAILY_FORECAST"].sort_values(
            "forecast_run_timestamp"
        )
        self.assertEqual(len(forecast_rows), 2)
        self.assertEqual(
            forecast_rows["forecast_run_id"].tolist(),
            [
                "weather_forecast_run:2026-03-12T08:00:00",
                "weather_forecast_run:2026-03-12T10:00:00",
            ],
        )
        self.assertEqual(
            forecast_rows["forecast_run_identity_source"].tolist(),
            ["persisted_weather_ingest_run_v1", "persisted_weather_ingest_run_v1"],
        )
        self.assertEqual(
            forecast_rows["forecast_run_identity_quality"].tolist(),
            ["stable_persisted_batch", "stable_persisted_batch"],
        )

        metadata: dict[str, object] = {}
        features = RegionalFeatureBuilder._weather_features(
            forecast_rows,
            pd.Timestamp("2026-03-12 09:00:00"),
            horizon_days=3,
            vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            vintage_metadata=metadata,
        )
        self.assertEqual(features["weather_forecast_temp_3_7"], 14.0)
        self.assertEqual(
            metadata["weather_forecast_selected_run_timestamp"],
            "2026-03-12T08:00:00",
        )
        self.assertEqual(
            metadata["weather_forecast_run_identity_source"],
            "persisted_weather_ingest_run_v1",
        )
        self.assertEqual(
            metadata["weather_forecast_run_identity_quality"],
            "stable_persisted_batch",
        )

    def test_load_weather_marks_legacy_forecast_rows_as_missing_identity_but_keeps_legacy_issue_time(self) -> None:
        self.db.add(
            WeatherData(
                city="München",
                datum=datetime(2026, 3, 15, 12, 0),
                available_time=datetime(2026, 3, 12, 8, 0),
                temperatur=16.0,
                luftfeuchtigkeit=60.0,
                data_type="DAILY_FORECAST",
                created_at=datetime(2026, 3, 12, 8, 0),
            )
        )
        self.db.commit()

        builder = RegionalFeatureBuilder(self.db)
        frame = builder._load_weather(pd.Timestamp("2026-03-10"), pd.Timestamp("2026-03-20"))

        self.assertEqual(len(frame), 1)
        self.assertTrue(pd.isna(frame.iloc[0]["forecast_run_timestamp"]))
        self.assertEqual(frame.iloc[0]["forecast_run_identity_source"], "missing")
        self.assertEqual(frame.iloc[0]["forecast_run_identity_quality"], "missing")
        self.assertEqual(frame.iloc[0]["issue_time"], pd.Timestamp("2026-03-12 08:00:00"))

        legacy_metadata: dict[str, object] = {}
        legacy_features = RegionalFeatureBuilder._weather_features(
            frame,
            pd.Timestamp("2026-03-12 09:00:00"),
            horizon_days=3,
            vintage_metadata=legacy_metadata,
        )
        self.assertEqual(legacy_features["weather_forecast_temp_3_7"], 16.0)
        self.assertEqual(
            legacy_metadata["weather_forecast_run_identity_source"],
            "legacy_created_at_fallback",
        )
        self.assertEqual(
            legacy_metadata["weather_forecast_run_identity_quality"],
            "legacy_unstable",
        )

        vintage_metadata: dict[str, object] = {}
        vintage_features = RegionalFeatureBuilder._weather_features(
            frame,
            pd.Timestamp("2026-03-12 09:00:00"),
            horizon_days=3,
            vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            vintage_metadata=vintage_metadata,
        )
        self.assertEqual(vintage_features["weather_forecast_temp_3_7"], 0.0)
        self.assertFalse(vintage_metadata["weather_forecast_run_identity_present"])
        self.assertEqual(vintage_metadata["weather_forecast_run_identity_source"], "missing")
        self.assertEqual(vintage_metadata["weather_forecast_run_identity_quality"], "missing")


if __name__ == "__main__":
    unittest.main()
