import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.run_weather_vintage_pilot_h7_ops import main, run_pilot_h7_shadow_ops
from scripts.run_weather_vintage_pilot_h7_shadow import PilotShadowLockError


class WeatherVintagePilotOpsWrapperTests(unittest.TestCase):
    def test_combined_wrapper_propagates_success(self) -> None:
        def _fake_shadow_runner(**kwargs):
            return {
                "status": "success",
                "run_id": kwargs["run_id"],
                "archive_dir": str(Path(kwargs["output_root"]) / "runs" / kwargs["run_id"]),
            }

        def _fake_health_runner(**_kwargs):
            return {
                "status": "ok",
                "exit_code": 0,
                "summary": {"total_runs": 1},
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, payload = run_pilot_h7_shadow_ops(
                output_root=Path(tmpdir),
                lookback_days=900,
                run_id="scheduled_run_001",
                run_purpose="scheduled_shadow",
                shadow_runner=_fake_shadow_runner,
                health_runner=_fake_health_runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["health_check"]["status"], "ok")

    def test_combined_wrapper_propagates_health_warning(self) -> None:
        def _fake_shadow_runner(**kwargs):
            return {"status": "success", "run_id": kwargs["run_id"]}

        def _fake_health_runner(**_kwargs):
            return {
                "status": "warning",
                "exit_code": 1,
                "summary": {"total_runs": 3},
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, payload = run_pilot_h7_shadow_ops(
                output_root=Path(tmpdir),
                lookback_days=900,
                run_id="scheduled_run_002",
                run_purpose="scheduled_shadow",
                shadow_runner=_fake_shadow_runner,
                health_runner=_fake_health_runner,
            )
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "attention_required")
        self.assertEqual(payload["health_check"]["status"], "warning")

    def test_main_returns_non_zero_when_health_check_is_critical(self) -> None:
        stdout = io.StringIO()
        with patch(
            "scripts.run_weather_vintage_pilot_h7_ops.run_pilot_h7_shadow_ops",
            return_value=(2, {"status": "attention_required", "health_check": {"status": "critical"}}),
        ):
            with patch(
                "sys.argv",
                ["run_weather_vintage_pilot_h7_ops.py", "--run-id", "ops_run_001"],
            ):
                with redirect_stdout(stdout):
                    exit_code = main()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["health_check"]["status"], "critical")

    def test_main_keeps_lock_conflicts_visible(self) -> None:
        stderr = io.StringIO()
        with patch(
            "scripts.run_weather_vintage_pilot_h7_ops.run_pilot_h7_shadow_ops",
            side_effect=PilotShadowLockError("locked"),
        ):
            with patch(
                "sys.argv",
                ["run_weather_vintage_pilot_h7_ops.py", "--run-id", "ops_locked"],
            ):
                with redirect_stderr(stderr):
                    exit_code = main()
        self.assertEqual(exit_code, 2)
        self.assertIn("lock_conflict", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
