import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.run_weather_vintage_pilot_h7_shadow import (
    PilotShadowLockError,
    acquire_wrapper_lock,
    main,
    release_wrapper_lock,
    run_pilot_h7_shadow,
)


class WeatherVintagePilotWrapperTests(unittest.TestCase):
    def test_run_pilot_h7_shadow_updates_manifest_for_normal_run(self) -> None:
        def _fake_runner(**kwargs):
            archive_dir = Path(kwargs["output_root"]) / "runs" / kwargs["run_id"]
            archive_dir.mkdir(parents=True, exist_ok=False)
            manifest_path = archive_dir / "run_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": kwargs["run_id"],
                        "run_purpose": kwargs["run_purpose"],
                        "status": "success",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {
                "status": "success",
                "run_id": kwargs["run_id"],
                "archive_dir": str(archive_dir),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_pilot_h7_shadow(
                output_root=Path(tmpdir),
                lookback_days=900,
                run_id="scheduled_run_001",
                run_purpose="scheduled_shadow",
                runner=_fake_runner,
            )

            self.assertEqual(result["status"], "success")
            manifest = json.loads(
                (Path(tmpdir) / "runs" / "scheduled_run_001" / "run_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["run_purpose"], "scheduled_shadow")
            self.assertEqual(manifest["exit_status"], 0)
            self.assertIn("started_at", manifest)
            self.assertIn("finished_at", manifest)
            self.assertEqual(
                manifest["scheduler_entrypoint"],
                "run_weather_vintage_pilot_h7_shadow.py",
            )

    def test_acquire_wrapper_lock_blocks_parallel_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "pilot.lock"
            acquire_wrapper_lock(lock_path)
            try:
                with self.assertRaises(PilotShadowLockError):
                    acquire_wrapper_lock(lock_path)
            finally:
                release_wrapper_lock(lock_path)

    def test_main_returns_non_zero_for_runtime_error(self) -> None:
        stderr = io.StringIO()
        with patch(
            "scripts.run_weather_vintage_pilot_h7_shadow.run_pilot_h7_shadow",
            side_effect=RuntimeError("boom"),
        ):
            with patch(
                "sys.argv",
                ["run_weather_vintage_pilot_h7_shadow.py", "--run-id", "failing_run"],
            ):
                with redirect_stderr(stderr):
                    exit_code = main()
        self.assertEqual(exit_code, 1)
        self.assertIn("runtime_error", stderr.getvalue())

    def test_main_returns_lock_conflict_exit_code(self) -> None:
        stderr = io.StringIO()
        with patch(
            "scripts.run_weather_vintage_pilot_h7_shadow.run_pilot_h7_shadow",
            side_effect=PilotShadowLockError("locked"),
        ):
            with patch(
                "sys.argv",
                ["run_weather_vintage_pilot_h7_shadow.py", "--run-id", "locked_run"],
            ):
                with redirect_stderr(stderr):
                    exit_code = main()
        self.assertEqual(exit_code, 2)
        self.assertIn("lock_conflict", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
