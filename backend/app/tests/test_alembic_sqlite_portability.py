import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


class AlembicSQLitePortabilityTests(unittest.TestCase):
    def _backend_dir(self) -> Path:
        resolved = Path(__file__).resolve()
        for parent in [*resolved.parents]:
            if (parent / "alembic.ini").exists() and (parent / "alembic").exists():
                return parent
            candidate = parent / "backend"
            if (candidate / "alembic.ini").exists() and (candidate / "alembic").exists():
                return candidate
        self.fail("Could not locate backend Alembic directory.")

    def _alembic_command(self) -> list[str]:
        backend_dir = self._backend_dir()
        repo_root = backend_dir.parent
        candidate_paths = [
            repo_root / ".venv-backend311" / "bin" / "alembic",
            backend_dir / ".venv" / "bin" / "alembic",
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                return [str(candidate)]

        alembic_bin = shutil.which("alembic")
        if alembic_bin:
            return [alembic_bin]

        self.skipTest("Alembic executable is not available in this test environment.")

    def test_forecast_accuracy_log_migration_runs_on_sqlite(self) -> None:
        backend_dir = self._backend_dir()

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "sqlite-migration-check.db"
            env = os.environ.copy()
            env["DATABASE_URL"] = f"sqlite:///{db_path}"

            result = subprocess.run(
                [*self._alembic_command(), "upgrade", "e6a1b4c8d2f3"],
                cwd=backend_dir,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"{result.stdout}\n{result.stderr}",
            )

            with sqlite3.connect(db_path) as conn:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info('forecast_accuracy_log')")
                }

            self.assertIn("computed_at", columns)
            self.assertIn("virus_typ", columns)
            self.assertIn("window_days", columns)

    def test_mlforecast_scope_migration_runs_on_sqlite(self) -> None:
        backend_dir = self._backend_dir()

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "sqlite-mlforecast-scope.db"
            env = os.environ.copy()
            env["DATABASE_URL"] = f"sqlite:///{db_path}"

            result = subprocess.run(
                [*self._alembic_command(), "upgrade", "f1a2b3c4d5e6"],
                cwd=backend_dir,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"{result.stdout}\n{result.stderr}",
            )

            with sqlite3.connect(db_path) as conn:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info('ml_forecasts')")
                }

            self.assertIn("region", columns)
            self.assertIn("horizon_days", columns)

    def test_full_migration_chain_reaches_head_on_sqlite(self) -> None:
        backend_dir = self._backend_dir()

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "sqlite-head.db"
            env = os.environ.copy()
            env["DATABASE_URL"] = f"sqlite:///{db_path}"

            result = subprocess.run(
                [*self._alembic_command(), "upgrade", "head"],
                cwd=backend_dir,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"{result.stdout}\n{result.stderr}",
            )

            with sqlite3.connect(db_path) as conn:
                version_row = conn.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()
                outbreak_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info('outbreak_scores')")
                }
                wave_evidence_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info('virus_wave_evidence')")
                }
                wastewater_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(wastewater_data)")
                }

            self.assertIsNotNone(version_row)
            self.assertEqual(version_row[0], "ad14bc25d678")
            self.assertIn("decision_priority_index", outbreak_columns)
            self.assertNotIn("decision_signal_index", outbreak_columns)
            self.assertIn("effective_weights_json", wave_evidence_columns)
            self.assertIn("budget_can_change", wave_evidence_columns)
            self.assertIn("laborwechsel", wastewater_columns)

            backtest_result_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info('virus_wave_backtest_results')")
            }
            self.assertIn("onset_detection_gain_days", backtest_result_columns)
            self.assertIn("false_early_warning_rate", backtest_result_columns)


if __name__ == "__main__":
    unittest.main()
