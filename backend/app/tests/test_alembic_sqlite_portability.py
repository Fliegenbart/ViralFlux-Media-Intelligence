import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


class AlembicSQLitePortabilityTests(unittest.TestCase):
    def _alembic_command(self) -> list[str]:
        repo_root = Path(__file__).resolve().parents[3]
        candidate_paths = [
            repo_root / ".venv-backend311" / "bin" / "alembic",
            repo_root / "backend" / ".venv" / "bin" / "alembic",
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                return [str(candidate)]

        alembic_bin = shutil.which("alembic")
        if alembic_bin:
            return [alembic_bin]

        self.skipTest("Alembic executable is not available in this test environment.")

    def test_forecast_accuracy_log_migration_runs_on_sqlite(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

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
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

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
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

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

            self.assertIsNotNone(version_row)
            self.assertEqual(version_row[0], "c8d1e2f3a4b5")


if __name__ == "__main__":
    unittest.main()
