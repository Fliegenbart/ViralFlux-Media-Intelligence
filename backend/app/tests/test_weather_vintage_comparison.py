import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app.services.ml.weather_vintage_comparison as weather_module
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
)
from app.services.ml.weather_vintage_comparison import (
    WeatherVintageComparisonRunner,
    build_weather_vintage_report_summary,
    build_weather_vintage_shadow_aggregate,
    build_weather_vintage_shadow_summary,
    load_weather_vintage_shadow_summaries,
    render_weather_vintage_markdown,
    render_weather_vintage_shadow_aggregate_markdown,
    scope_report_from_training_result,
    write_weather_vintage_shadow_archive,
)


def _comparison_payload(relative_wis_delta: float = -0.04, crps_delta: float = -0.02):
    return {
        "status": "success",
        "weather_forecast_vintage_mode": WEATHER_FORECAST_VINTAGE_DISABLED,
        "exogenous_feature_semantics_version": "regional_exogenous_semantics_v1",
        "weather_vintage_comparison": {
            "comparison_status": "ok",
            "legacy_vs_vintage_metric_delta": {
                "relative_wis": relative_wis_delta,
                "crps": crps_delta,
            },
            "quality_gate_change": {
                "legacy_forecast_readiness": "GO",
                "vintage_forecast_readiness": "GO",
                "overall_passed_changed": False,
            },
            "threshold_change": 0.0,
            "calibration_change": {
                "legacy": "isotonic",
                "vintage": "isotonic",
                "changed": False,
            },
            "weather_vintage_run_identity_coverage": {
                WEATHER_FORECAST_VINTAGE_DISABLED: {
                    "run_identity_present": False,
                    "coverage_ratio": 0.0,
                },
                WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1: {
                    "run_identity_present": True,
                    "coverage_ratio": 1.0,
                },
            },
            "modes": {
                WEATHER_FORECAST_VINTAGE_DISABLED: {
                    "weather_forecast_vintage_mode": WEATHER_FORECAST_VINTAGE_DISABLED,
                    "exogenous_feature_semantics_version": "regional_exogenous_semantics_v1",
                    "aggregate_metrics": {"relative_wis": 0.98, "crps": 1.24},
                    "benchmark_metrics": {"relative_wis": 0.98, "crps": 1.24},
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "selected_tau": 0.1,
                    "selected_kappa": 0.2,
                    "action_threshold": 0.6,
                    "calibration_mode": "isotonic",
                    "weather_forecast_run_identity_present": False,
                },
                WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1: {
                    "weather_forecast_vintage_mode": WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
                    "exogenous_feature_semantics_version": "regional_exogenous_semantics_v1",
                    "aggregate_metrics": {"relative_wis": 0.94, "crps": 1.22},
                    "benchmark_metrics": {"relative_wis": 0.94, "crps": 1.22},
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "selected_tau": 0.12,
                    "selected_kappa": 0.25,
                    "action_threshold": 0.58,
                    "calibration_mode": "isotonic",
                    "weather_forecast_run_identity_present": True,
                },
            },
        },
    }


class WeatherVintageComparisonTests(unittest.TestCase):
    def test_scope_report_wrapper_delegates_to_module(self) -> None:
        sentinel = {"virus_typ": "Influenza A", "verdict": "better"}

        with patch(
            "app.services.ml.weather_vintage_reporting.scope_report_from_training_result",
            return_value=sentinel,
        ) as mocked:
            result = scope_report_from_training_result(
                virus_typ="Influenza A",
                horizon_days=7,
                result=_comparison_payload(),
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            virus_typ="Influenza A",
            horizon_days=7,
            result=_comparison_payload(),
            weather_forecast_vintage_disabled=weather_module.WEATHER_FORECAST_VINTAGE_DISABLED,
            weather_forecast_vintage_run_timestamp_v1=weather_module.WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            json_safe_fn=weather_module._json_safe,
            classify_weather_vintage_result_fn=weather_module.classify_weather_vintage_result,
        )

    def test_shadow_summary_wrapper_delegates_to_module(self) -> None:
        sentinel = {"run_id": "run_001"}
        report = {"scopes": []}

        with patch(
            "app.services.ml.weather_vintage_reporting.build_weather_vintage_shadow_summary",
            return_value=sentinel,
        ) as mocked:
            result = build_weather_vintage_shadow_summary(
                report=report,
                generated_at="2026-03-26T10:00:00",
                run_id="run_001",
                run_purpose="scheduled_shadow",
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            report=report,
            generated_at="2026-03-26T10:00:00",
            run_id="run_001",
            run_purpose="scheduled_shadow",
            json_safe_fn=weather_module._json_safe,
            determine_weather_vintage_comparison_eligibility_fn=weather_module.determine_weather_vintage_comparison_eligibility,
            extract_mode_snapshot_fn=weather_module._extract_mode_snapshot,
            weather_forecast_vintage_disabled=weather_module.WEATHER_FORECAST_VINTAGE_DISABLED,
            weather_forecast_vintage_run_timestamp_v1=weather_module.WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
        )

    def test_shadow_aggregate_wrapper_delegates_to_module(self) -> None:
        sentinel = {"archived_runs": 1}

        with patch(
            "app.services.ml.weather_vintage_reporting.build_weather_vintage_shadow_aggregate",
            return_value=sentinel,
        ) as mocked:
            result = build_weather_vintage_shadow_aggregate([{"run_id": "run_001"}])

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            [{"run_id": "run_001"}],
            gate_rank_fn=weather_module._gate_rank,
            json_safe_fn=weather_module._json_safe,
            determine_weather_vintage_review_status_fn=weather_module.determine_weather_vintage_review_status,
            scope_review_recommendation_fn=weather_module._scope_review_recommendation,
            pd_module=weather_module.pd,
        )

    def test_shadow_archive_wrapper_delegates_to_module(self) -> None:
        sentinel = {"summary_json": Path("/tmp/summary.json")}

        with patch(
            "app.services.ml.weather_vintage_reporting.write_weather_vintage_shadow_archive",
            return_value=sentinel,
        ) as mocked:
            result = write_weather_vintage_shadow_archive(
                archive_dir=Path("/tmp/run_001"),
                report={"status": "ok"},
                generated_at="2026-03-26T10:00:00",
                run_id="run_001",
                manifest={"run_purpose": "scheduled_shadow"},
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            archive_dir=Path("/tmp/run_001"),
            report={"status": "ok"},
            generated_at="2026-03-26T10:00:00",
            run_id="run_001",
            manifest={"run_purpose": "scheduled_shadow"},
            json_module=weather_module.json,
            json_safe_fn=weather_module._json_safe,
            render_weather_vintage_markdown_fn=weather_module.render_weather_vintage_markdown,
            build_weather_vintage_shadow_summary_fn=weather_module.build_weather_vintage_shadow_summary,
        )

    def test_shadow_health_wrapper_delegates_to_module(self) -> None:
        sentinel = {"status": "ok"}
        now = datetime(2026, 3, 27, 12, 0, 0)

        with patch(
            "app.services.ml.weather_vintage_health.build_weather_vintage_shadow_health_report",
            return_value=sentinel,
        ) as mocked:
            result = weather_module.build_weather_vintage_shadow_health_report(
                [{"run_id": "run_001"}],
                now=now,
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            [{"run_id": "run_001"}],
            now=now,
            max_run_age_hours=weather_module.WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS,
            max_days_without_comparable=weather_module.WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE,
            max_insufficient_identity_streak=weather_module.WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK,
            parse_generated_at_fn=weather_module._parse_generated_at,
            weather_health_status_exit_code_fn=weather_module._weather_health_status_exit_code,
            combine_weather_health_status_fn=weather_module._combine_weather_health_status,
            json_safe_fn=weather_module._json_safe,
        )

    def test_load_weather_identity_wrapper_delegates_to_module(self) -> None:
        sentinel = pd.DataFrame([{"datum": "2026-03-27"}])
        runner = WeatherVintageComparisonRunner(db="db")
        start_date = pd.Timestamp("2026-03-01")
        end_date = pd.Timestamp("2026-03-31")

        with patch(
            "app.services.ml.weather_vintage_coverage.load_weather_identity_frame",
            return_value=sentinel,
        ) as mocked:
            result = runner._load_weather_identity_frame(
                start_date=start_date,
                end_date=end_date,
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            "db",
            start_date=start_date,
            end_date=end_date,
            weather_data_model=weather_module.WeatherData,
            pd_module=weather_module.pd,
        )

    def test_coverage_summary_wrapper_delegates_to_module(self) -> None:
        sentinel = {"coverage_status": "sufficient"}
        panel = pd.DataFrame({"as_of_date": ["2026-01-01"]})
        weather_frame = pd.DataFrame({"datum": ["2026-01-08"]})

        with patch(
            "app.services.ml.weather_vintage_coverage.summarize_backtest_weather_identity_coverage",
            return_value=sentinel,
        ) as mocked:
            result = WeatherVintageComparisonRunner.summarize_backtest_weather_identity_coverage(
                panel=panel,
                weather_frame=weather_frame,
                horizon_days=7,
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once_with(
            panel=panel,
            weather_frame=weather_frame,
            horizon_days=7,
            time_based_panel_splits_fn=weather_module.time_based_panel_splits,
            min_test_coverage=weather_module.WEATHER_VINTAGE_MIN_TEST_COVERAGE,
            min_train_coverage=weather_module.WEATHER_VINTAGE_MIN_TRAIN_COVERAGE,
            time_block_days=weather_module.WEATHER_VINTAGE_TIME_BLOCK_DAYS,
            json_safe_fn=weather_module._json_safe,
            pd_module=weather_module.pd,
        )

    def test_coverage_analyzer_wrapper_delegates_to_module(self) -> None:
        sentinel = {"coverage_status": "sufficient"}
        runner = WeatherVintageComparisonRunner(db="db")
        trainer = object()

        with patch(
            "app.services.ml.weather_vintage_coverage.analyze_scope_coverage",
            return_value=sentinel,
        ) as mocked:
            result = runner._analyze_scope_coverage(
                trainer,
                "Influenza A",
                7,
                900,
            )

        self.assertIs(result, sentinel)
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args, ())
        self.assertIs(kwargs["trainer"], trainer)
        self.assertEqual(kwargs["virus_typ"], "Influenza A")
        self.assertEqual(kwargs["horizon_days"], 7)
        self.assertEqual(kwargs["lookback_days"], 900)
        self.assertEqual(
            kwargs["weather_forecast_vintage_run_timestamp_v1"],
            weather_module.WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
        )
        self.assertIs(kwargs["pd_module"], weather_module.pd)
        self.assertEqual(
            kwargs["load_weather_identity_frame_fn"].__func__,
            runner._load_weather_identity_frame.__func__,
        )
        self.assertIs(kwargs["load_weather_identity_frame_fn"].__self__, runner)
        self.assertIs(
            kwargs["summarize_backtest_weather_identity_coverage_fn"],
            runner.summarize_backtest_weather_identity_coverage,
        )

    def test_shadow_archive_writes_expected_file_set(self) -> None:
        report = {
            "status": "ok",
            "comparison_type": "weather_vintage_end_to_end_training_backtest",
            "matrix": {
                "virus_types": ["Influenza A"],
                "horizon_days_list": [7],
                "lookback_days": 900,
                "active_training_mode_default": WEATHER_FORECAST_VINTAGE_DISABLED,
                "shadow_mode": WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            },
            "scopes": [
                {
                    **scope_report_from_training_result(
                        virus_typ="Influenza A",
                        horizon_days=7,
                        result=_comparison_payload(),
                    ),
                    "weather_vintage_backtest_coverage": {
                        "coverage_status": "sufficient",
                        "insufficient_for_comparison": False,
                        "coverage_overall": 0.9,
                        "coverage_train": 0.88,
                        "coverage_test": 0.91,
                    },
                }
            ],
            "summary": {"total_scopes": 1, "verdict_counts": {"better": 1}},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir) / "runs" / "run_001"
            paths = write_weather_vintage_shadow_archive(
                archive_dir=archive_dir,
                report=report,
                generated_at="2026-03-26T10:00:00",
                run_id="run_001",
                manifest={"status": "success", "output_root": tmpdir, "run_purpose": "scheduled_shadow"},
            )

            self.assertTrue(paths["summary_json"].exists())
            self.assertTrue(paths["report_json"].exists())
            self.assertTrue(paths["report_md"].exists())
            self.assertTrue(paths["run_manifest"].exists())

            summary = json.loads(paths["summary_json"].read_text(encoding="utf-8"))
            self.assertEqual(summary["summary"]["comparable_scopes"], 1)
            self.assertEqual(summary["scopes"][0]["comparison_eligibility"], "comparable")
            self.assertEqual(summary["run_purpose"], "scheduled_shadow")
            manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
            self.assertIn("files_written", manifest)
            self.assertEqual(manifest["run_purpose"], "scheduled_shadow")

    def test_coverage_analysis_counts_real_backtest_window_coverage(self) -> None:
        panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=200, freq="D"),
                "target_date": pd.date_range("2026-01-08", periods=200, freq="D"),
            }
        )
        weather_rows = []
        for as_of_date in pd.date_range("2026-06-08", periods=42, freq="D"):
            target_date = as_of_date + pd.Timedelta(days=7)
            weather_rows.append(
                {
                    "datum": target_date,
                    "available_time": as_of_date,
                    "forecast_run_timestamp": as_of_date,
                    "forecast_run_id": f"run:{as_of_date.date()}",
                    "forecast_run_identity_source": "persisted_weather_ingest_run_v1",
                    "forecast_run_identity_quality": "stable_persisted_batch",
                    "data_type": "DAILY_FORECAST",
                }
            )
        weather_frame = pd.DataFrame(weather_rows)

        summary = WeatherVintageComparisonRunner.summarize_backtest_weather_identity_coverage(
            panel=panel,
            weather_frame=weather_frame,
            horizon_days=7,
        )

        self.assertGreater(summary["coverage_overall"], 0.0)
        self.assertGreater(summary["coverage_test"], 0.0)
        self.assertEqual(summary["first_available_run_identity_date"], "2026-06-15 00:00:00")
        self.assertEqual(summary["first_covered_as_of_date"], "2026-06-08 00:00:00")
        self.assertTrue(summary["coverage_by_fold"])

    def test_coverage_analysis_marks_current_reingest_as_historically_unusable(self) -> None:
        panel = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2025-09-08", periods=200, freq="D"),
                "target_date": pd.date_range("2025-09-15", periods=200, freq="D"),
            }
        )
        future_targets = pd.date_range("2026-03-27", periods=8, freq="D")
        weather_frame = pd.DataFrame(
            {
                "datum": future_targets,
                "available_time": [pd.Timestamp("2026-03-26 20:20:00")] * len(future_targets),
                "forecast_run_timestamp": [pd.Timestamp("2026-03-26 20:20:00")] * len(future_targets),
                "forecast_run_id": [f"run:{idx}" for idx in range(len(future_targets))],
                "forecast_run_identity_source": ["persisted_weather_ingest_run_v1"] * len(future_targets),
                "forecast_run_identity_quality": ["stable_persisted_batch"] * len(future_targets),
                "data_type": ["DAILY_FORECAST"] * len(future_targets),
            }
        )

        summary = WeatherVintageComparisonRunner.summarize_backtest_weather_identity_coverage(
            panel=panel,
            weather_frame=weather_frame,
            horizon_days=7,
        )

        self.assertEqual(summary["coverage_status"], "none")
        self.assertTrue(summary["insufficient_for_comparison"])
        self.assertEqual(summary["coverage_overall"], 0.0)
        self.assertEqual(summary["coverage_train"], 0.0)
        self.assertEqual(summary["coverage_test"], 0.0)
        self.assertIsNone(summary["first_covered_as_of_date"])
        self.assertEqual(summary["first_available_run_identity_date"], "2026-03-27 00:00:00")

    def test_scope_report_extracts_deltas_and_diagnosis_fields(self) -> None:
        report = scope_report_from_training_result(
            virus_typ="Influenza A",
            horizon_days=7,
            result=_comparison_payload(),
        )

        self.assertEqual(report["virus_typ"], "Influenza A")
        self.assertEqual(report["weather_forecast_vintage_mode"], WEATHER_FORECAST_VINTAGE_DISABLED)
        self.assertEqual(report["legacy_vs_vintage_metric_delta"]["relative_wis"], -0.04)
        self.assertEqual(report["quality_gate_change"]["legacy_forecast_readiness"], "GO")
        self.assertEqual(report["threshold_change"], 0.0)
        self.assertEqual(report["calibration_change"]["legacy"], "isotonic")
        self.assertEqual(report["verdict"], "better")
        self.assertIn("selected_tau", report["modes"][WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1])

    def test_report_summary_counts_better_and_worse_scopes(self) -> None:
        better = scope_report_from_training_result(
            virus_typ="Influenza A",
            horizon_days=7,
            result=_comparison_payload(relative_wis_delta=-0.04, crps_delta=-0.02),
        )
        worse = scope_report_from_training_result(
            virus_typ="SARS-CoV-2",
            horizon_days=3,
            result=_comparison_payload(relative_wis_delta=0.04, crps_delta=0.02),
        )

        summary = build_weather_vintage_report_summary([better, worse])

        self.assertEqual(summary["total_scopes"], 2)
        self.assertEqual(summary["verdict_counts"]["better"], 1)
        self.assertEqual(summary["verdict_counts"]["worse"], 1)

    def test_shadow_aggregate_ignores_insufficient_identity_for_metric_rollups(self) -> None:
        comparable_report = {
            "status": "ok",
            "matrix": {"virus_types": ["Influenza A"], "horizon_days_list": [7]},
            "scopes": [
                {
                    **scope_report_from_training_result(
                        virus_typ="Influenza A",
                        horizon_days=7,
                        result=_comparison_payload(relative_wis_delta=-0.03, crps_delta=-0.02),
                    ),
                    "weather_vintage_backtest_coverage": {
                        "coverage_status": "sufficient",
                        "insufficient_for_comparison": False,
                        "coverage_overall": 0.9,
                        "coverage_train": 0.88,
                        "coverage_test": 0.91,
                    },
                }
            ],
            "summary": {},
        }
        insufficient_payload = _comparison_payload(relative_wis_delta=0.2, crps_delta=0.2)
        insufficient_payload["weather_vintage_comparison"]["weather_vintage_run_identity_coverage"][
            WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1
        ] = {
            "run_identity_present": False,
            "coverage_ratio": 0.0,
        }
        insufficient_report = {
            "status": "ok",
            "matrix": {"virus_types": ["Influenza A"], "horizon_days_list": [7]},
            "scopes": [
                {
                    **scope_report_from_training_result(
                        virus_typ="Influenza A",
                        horizon_days=7,
                        result=insufficient_payload,
                    ),
                    "weather_vintage_backtest_coverage": {
                        "coverage_status": "none",
                        "insufficient_for_comparison": True,
                        "coverage_overall": 0.0,
                        "coverage_train": 0.0,
                        "coverage_test": 0.0,
                    },
                }
            ],
            "summary": {},
        }

        run_summaries = [
            build_weather_vintage_shadow_summary(
                report=comparable_report,
                generated_at="2026-03-26T10:00:00",
                run_id="run_001",
                run_purpose="scheduled_shadow",
            ),
            build_weather_vintage_shadow_summary(
                report=insufficient_report,
                generated_at="2026-03-27T10:00:00",
                run_id="run_002",
                run_purpose="scheduled_shadow",
            ),
        ]

        aggregate = build_weather_vintage_shadow_aggregate(run_summaries)

        self.assertEqual(aggregate["archived_runs"], 2)
        scope = aggregate["scopes"][0]
        self.assertEqual(scope["archived_runs"], 2)
        self.assertEqual(scope["comparable_runs"], 1)
        self.assertEqual(scope["insufficient_identity_runs"], 1)
        self.assertEqual(scope["average_relative_wis_delta"], -0.03)
        self.assertEqual(scope["average_crps_delta"], -0.02)
        self.assertEqual(scope["overall_recommendation"], "keep_legacy_default")

        markdown = render_weather_vintage_shadow_aggregate_markdown(aggregate)
        self.assertIn("insufficient_identity_scope_runs", markdown)
        self.assertIn("Influenza A / h7", markdown)
        self.assertEqual(scope["review_status"], "still_collecting_evidence")

    def test_runner_executes_matrix_with_shadow_comparison_and_writes_outputs(self) -> None:
        calls = []

        class _FakeTrainer:
            def train_all_regions(self, **kwargs):
                calls.append(kwargs)
                return _comparison_payload()

        runner = WeatherVintageComparisonRunner(
            db=None,
            trainer_factory=lambda _db: _FakeTrainer(),
            coverage_analyzer=lambda *_args: {
                "coverage_status": "sufficient",
                "insufficient_for_comparison": False,
                "coverage_overall": 0.92,
                "coverage_train": 0.88,
                "coverage_test": 0.95,
                "coverage_by_fold": [{"fold": 1, "coverage_train": 0.9, "coverage_test": 1.0}],
                "coverage_by_time_block": [{"start": "2026-01-01", "end": "2026-03-31", "coverage": 0.92}],
                "first_available_run_identity_date": "2026-01-08 00:00:00",
                "last_available_run_identity_date": "2026-07-01 00:00:00",
                "first_covered_as_of_date": "2026-01-01 00:00:00",
                "last_covered_as_of_date": "2026-06-30 00:00:00",
                "unique_as_of_dates": 180,
                "rows_in_panel": 2880,
                "weather_rows_with_run_identity": 1440,
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            json_output = Path(tmpdir) / "report.json"
            markdown_output = Path(tmpdir) / "report.md"
            report = runner.run(
                virus_types=["Influenza A", "SARS-CoV-2"],
                horizon_days_list=[3, 7],
                lookback_days=365,
                output_json=json_output,
                output_markdown=markdown_output,
            )

            self.assertEqual(len(calls), 4)
            self.assertTrue(all(call["weather_vintage_comparison"] for call in calls))
            self.assertTrue(all(call["persist"] is False for call in calls))
            self.assertTrue(all(call.get("weather_forecast_vintage_mode") is None for call in calls))
            self.assertTrue(json_output.exists())
            self.assertTrue(markdown_output.exists())

            payload = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertEqual(payload["matrix"]["active_training_mode_default"], WEATHER_FORECAST_VINTAGE_DISABLED)
            self.assertEqual(payload["matrix"]["shadow_mode"], WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1)
            self.assertEqual(len(payload["scopes"]), 4)
            self.assertIn("weather_vintage_run_identity_coverage", payload["scopes"][0])
            self.assertIn("legacy_vs_vintage_metric_delta", payload["scopes"][0])
            self.assertIn("weather_vintage_backtest_coverage", payload["scopes"][0])
            self.assertEqual(
                payload["scopes"][0]["weather_vintage_backtest_coverage"]["coverage_test"],
                0.95,
            )
            self.assertEqual(report["summary"]["verdict_counts"]["better"], 4)
            self.assertEqual(report["summary"]["coverage_status_counts"]["sufficient"], 4)

            markdown = markdown_output.read_text(encoding="utf-8")
            self.assertIn("Weather Vintage Comparison", markdown)
            self.assertIn("Influenza A / h3", markdown)
            self.assertIn("Coverage test", markdown)

    def test_runner_is_opt_in_and_does_not_touch_trainer_when_unused(self) -> None:
        calls = []

        class _FakeTrainer:
            def train_all_regions(self, **kwargs):
                calls.append(kwargs)
                return _comparison_payload()

        runner = WeatherVintageComparisonRunner(
            db=None,
            trainer_factory=lambda _db: _FakeTrainer(),
        )

        self.assertEqual(calls, [])
        report = render_weather_vintage_markdown(
            {
                "summary": {"total_scopes": 0, "verdict_counts": {}},
                "scopes": [],
            }
        )
        self.assertIn("Total scopes: 0", report)
        self.assertEqual(calls, [])

    def test_shadow_archive_loader_keeps_multiple_runs_separate(self) -> None:
        report = {
            "status": "ok",
            "comparison_type": "weather_vintage_end_to_end_training_backtest",
            "matrix": {"virus_types": ["Influenza A"], "horizon_days_list": [7], "lookback_days": 900},
            "scopes": [
                {
                    **scope_report_from_training_result(
                        virus_typ="Influenza A",
                        horizon_days=7,
                        result=_comparison_payload(),
                    ),
                    "weather_vintage_backtest_coverage": {
                        "coverage_status": "sufficient",
                        "insufficient_for_comparison": False,
                        "coverage_overall": 0.91,
                        "coverage_train": 0.88,
                        "coverage_test": 0.9,
                    },
                }
            ],
            "summary": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_weather_vintage_shadow_archive(
                archive_dir=root / "runs" / "run_001",
                report=report,
                generated_at="2026-03-26T10:00:00",
                run_id="run_001",
                manifest={"status": "success", "output_root": tmpdir, "run_purpose": "scheduled_shadow"},
            )
            write_weather_vintage_shadow_archive(
                archive_dir=root / "runs" / "run_002",
                report=report,
                generated_at="2026-03-27T10:00:00",
                run_id="run_002",
                manifest={"status": "success", "output_root": tmpdir, "run_purpose": "scheduled_shadow"},
            )

            summaries = load_weather_vintage_shadow_summaries(root)
            self.assertEqual(len(summaries), 2)
            self.assertEqual([item["run_id"] for item in summaries], ["run_001", "run_002"])

    def test_shadow_archive_filters_review_stats_to_scheduled_runs(self) -> None:
        report = {
            "status": "ok",
            "comparison_type": "weather_vintage_end_to_end_training_backtest",
            "matrix": {"virus_types": ["Influenza A"], "horizon_days_list": [7], "lookback_days": 900},
            "scopes": [
                {
                    **scope_report_from_training_result(
                        virus_typ="Influenza A",
                        horizon_days=7,
                        result=_comparison_payload(relative_wis_delta=-0.03, crps_delta=-0.02),
                    ),
                    "weather_vintage_backtest_coverage": {
                        "coverage_status": "sufficient",
                        "insufficient_for_comparison": False,
                        "coverage_overall": 0.9,
                        "coverage_train": 0.88,
                        "coverage_test": 0.91,
                    },
                }
            ],
            "summary": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_weather_vintage_shadow_archive(
                archive_dir=root / "runs" / "run_smoke",
                report=report,
                generated_at="2026-03-26T10:00:00",
                run_id="run_smoke",
                manifest={"status": "success", "output_root": tmpdir, "run_purpose": "smoke"},
            )
            write_weather_vintage_shadow_archive(
                archive_dir=root / "runs" / "run_sched",
                report=report,
                generated_at="2026-03-27T10:00:00",
                run_id="run_sched",
                manifest={
                    "status": "success",
                    "output_root": tmpdir,
                    "run_purpose": "scheduled_shadow",
                },
            )

            filtered = load_weather_vintage_shadow_summaries(
                root,
                included_run_purposes=("scheduled_shadow",),
            )
            aggregate = build_weather_vintage_shadow_aggregate(filtered)
            scope = aggregate["scopes"][0]

            self.assertEqual(aggregate["archived_runs"], 1)
            self.assertEqual(scope["archived_runs"], 1)
            self.assertEqual(aggregate["included_run_purposes"], ["scheduled_shadow"])

    def test_shadow_archive_fail_fast_on_duplicate_run_directory(self) -> None:
        report = {
            "status": "ok",
            "comparison_type": "weather_vintage_end_to_end_training_backtest",
            "matrix": {"virus_types": ["Influenza A"], "horizon_days_list": [7], "lookback_days": 900},
            "scopes": [],
            "summary": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir) / "runs" / "duplicate"
            write_weather_vintage_shadow_archive(
                archive_dir=archive_dir,
                report=report,
                generated_at="2026-03-26T10:00:00",
                run_id="duplicate",
                manifest={"status": "success", "output_root": tmpdir, "run_purpose": "scheduled_shadow"},
            )
            with self.assertRaises(FileExistsError):
                write_weather_vintage_shadow_archive(
                    archive_dir=archive_dir,
                    report=report,
                    generated_at="2026-03-26T10:05:00",
                    run_id="duplicate",
                    manifest={
                        "status": "success",
                        "output_root": tmpdir,
                        "run_purpose": "scheduled_shadow",
                    },
                )

    def test_shadow_aggregate_becomes_review_ready_only_after_minimum_comparable_runs(self) -> None:
        run_summaries = []
        for idx in range(6):
            report = {
                "status": "ok",
                "matrix": {"virus_types": ["Influenza A"], "horizon_days_list": [7]},
                "scopes": [
                    {
                        **scope_report_from_training_result(
                            virus_typ="Influenza A",
                            horizon_days=7,
                            result=_comparison_payload(relative_wis_delta=-0.002, crps_delta=-0.0005),
                        ),
                        "weather_vintage_backtest_coverage": {
                            "coverage_status": "sufficient",
                            "insufficient_for_comparison": False,
                            "coverage_overall": 0.92,
                            "coverage_train": 0.86,
                            "coverage_test": 0.9,
                        },
                    }
                ],
                "summary": {},
            }
            run_summaries.append(
                build_weather_vintage_shadow_summary(
                    report=report,
                    generated_at=f"2026-03-{26 + idx:02d}T10:00:00",
                    run_id=f"run_{idx}",
                    run_purpose="scheduled_shadow",
                )
            )

        aggregate = build_weather_vintage_shadow_aggregate(run_summaries)
        scope = aggregate["scopes"][0]
        self.assertEqual(scope["comparable_runs"], 6)
        self.assertEqual(scope["review_status"], "review_ready")
        self.assertEqual(scope["overall_recommendation"], "expand_shadow_only")


if __name__ == "__main__":
    unittest.main()
