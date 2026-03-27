import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.services.ml.weather_vintage_comparison import build_weather_vintage_shadow_health_report
from scripts.check_weather_vintage_shadow_health import main, run_shadow_health_check


def _write_summary(output_root: Path, run_id: str, payload: dict) -> None:
    summary_path = output_root / "runs" / run_id / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _scope(
    virus_typ: str,
    horizon_days: int,
    generated_at: str,
    comparison_eligibility: str,
) -> dict:
    return {
        "virus_typ": virus_typ,
        "horizon_days": horizon_days,
        "generated_at": generated_at,
        "comparison_eligibility": comparison_eligibility,
        "weather_vintage_backtest_coverage": {
            "coverage_test": 0.92 if comparison_eligibility == "comparable" else 0.0,
            "coverage_overall": 0.9 if comparison_eligibility == "comparable" else 0.0,
        },
        "legacy_vs_vintage_metric_delta": {
            "relative_wis": -0.02 if comparison_eligibility == "comparable" else 0.0,
            "crps": -0.01 if comparison_eligibility == "comparable" else 0.0,
        },
        "quality_gate_change": {
            "legacy_forecast_readiness": "GO",
            "vintage_forecast_readiness": "GO",
        },
    }


def _summary(
    *,
    run_id: str,
    generated_at: str,
    scopes: list[dict],
    run_purpose: str = "scheduled_shadow",
    failed_scopes: int = 0,
) -> dict:
    return {
        "run_id": run_id,
        "run_purpose": run_purpose,
        "generated_at": generated_at,
        "status": "success",
        "summary": {
            "archived_scopes": len(scopes),
            "comparable_scopes": sum(
                1 for scope in scopes if scope.get("comparison_eligibility") == "comparable"
            ),
            "insufficient_identity_scopes": sum(
                1
                for scope in scopes
                if scope.get("comparison_eligibility") == "insufficient_identity"
            ),
            "failed_scopes": failed_scopes,
        },
        "scopes": scopes,
    }


class WeatherVintageShadowHealthTests(unittest.TestCase):
    def test_health_report_marks_missing_recent_run_as_critical(self) -> None:
        report = build_weather_vintage_shadow_health_report([], now=datetime(2026, 3, 27, 12, 0, 0))
        self.assertEqual(report["status"], "critical")
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(report["findings"][0]["code"], "no_scheduled_shadow_runs")

    def test_health_report_marks_latest_failed_run_as_critical(self) -> None:
        now = datetime(2026, 3, 27, 12, 0, 0)
        generated_at = (now - timedelta(hours=2)).isoformat()
        report = build_weather_vintage_shadow_health_report(
            [
                _summary(
                    run_id="run_failed",
                    generated_at=generated_at,
                    scopes=[
                        _scope("Influenza A", 7, generated_at, "failed"),
                        _scope("SARS-CoV-2", 7, generated_at, "failed"),
                    ],
                    failed_scopes=2,
                )
            ],
            now=now,
        )
        self.assertEqual(report["status"], "critical")
        self.assertTrue(any(item["code"] == "latest_run_failed" for item in report["findings"]))

    def test_health_report_marks_healthy_shadow_runs_as_ok(self) -> None:
        now = datetime(2026, 3, 27, 12, 0, 0)
        summaries = []
        for index in range(6):
            generated_at = (now - timedelta(hours=12 - index)).isoformat()
            scopes = [
                _scope("Influenza A", 7, generated_at, "comparable"),
                _scope("SARS-CoV-2", 7, generated_at, "comparable"),
            ]
            summaries.append(
                _summary(
                    run_id=f"run_{index}",
                    generated_at=generated_at,
                    scopes=scopes,
                )
            )
        report = build_weather_vintage_shadow_health_report(summaries, now=now)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["summary"]["comparable_scopes"], 2)

    def test_health_check_cli_filters_smoke_runs_out_of_default_monitoring(self) -> None:
        now = datetime(2026, 3, 27, 12, 0, 0)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)
            _write_summary(
                output_root,
                "smoke_run",
                _summary(
                    run_id="smoke_run",
                    generated_at=(now - timedelta(hours=1)).isoformat(),
                    scopes=[_scope("Influenza A", 7, now.isoformat(), "comparable")],
                    run_purpose="smoke",
                ),
            )
            report = run_shadow_health_check(output_root=output_root)
            self.assertEqual(report["status"], "critical")
            self.assertEqual(report["summary"]["total_runs"], 0)

    def test_health_check_cli_returns_warning_for_insufficient_identity_streak(self) -> None:
        now = datetime.utcnow()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)
            for index in range(3):
                generated_at = (now - timedelta(days=index + 1)).isoformat()
                _write_summary(
                    output_root,
                    f"run_{index}",
                    _summary(
                        run_id=f"run_{index}",
                        generated_at=generated_at,
                        scopes=[_scope("Influenza A", 7, generated_at, "insufficient_identity")],
                    ),
                )
            stdout = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "check_weather_vintage_shadow_health.py",
                    "--output-root",
                    str(output_root),
                ],
            ):
                with redirect_stdout(stdout):
                    exit_code = main()
            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["status"], "warning")


if __name__ == "__main__":
    unittest.main()
