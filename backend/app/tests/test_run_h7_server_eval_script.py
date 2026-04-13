import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run-h7-server-eval.sh"


class RunH7ServerEvalScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        (self.repo / "backend").mkdir(parents=True)
        (self.repo / "server.env").write_text("ENVIRONMENT=production\n")

        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.log_path = self.root / "commands.log"

        self._write_stub("docker", self._docker_stub())
        self._write_stub("git", self._git_stub())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_stub(self, name: str, content: str) -> None:
        path = self.fakebin / name
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _docker_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            echo "docker $*" >> "$TEST_LOG"
            if [ "${1:-}" = "run" ] && [ "${2:-}" = "-d" ]; then
              printf 'fake-container-id\\n'
            fi
            exit 0
            """
        )

    def _git_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            echo "git $*" >> "$TEST_LOG"
            if [ "${1:-}" = "-C" ] && [ "${3:-}" = "rev-parse" ]; then
              printf 'abc1234\\n'
            fi
            exit 0
            """
        )

    def _command_log(self) -> list[str]:
        return self.log_path.read_text().splitlines() if self.log_path.exists() else []

    def test_script_mounts_registry_and_sets_override_env(self) -> None:
        models_root = self.root / "models"
        registry_root = self.root / "forecast_registry"
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.fakebin}:{env['PATH']}",
                "TEST_LOG": str(self.log_path),
                "REPO": str(self.repo),
                "MODELS_ROOT": str(models_root),
                "REGISTRY_ROOT": str(registry_root),
                "RUN_ID": "20260413T120000Z_influenza_b_h7",
                "VIRUS": "Influenza B",
                "DETACH": "true",
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.repo,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        log = "\n".join(self._command_log())
        self.assertIn("docker run -d", log)
        self.assertIn(
            f"-v {registry_root}:/app/backend/app/ml_models/forecast_registry",
            log,
        )
        self.assertIn(
            "-e FORECAST_REGISTRY_DIR=/app/backend/app/ml_models/forecast_registry",
            log,
        )
        self.assertIn(
            "-e MODELS_DIR=/runs/models/20260413T120000Z_influenza_b_h7",
            log,
        )
        self.assertIn(
            f"-v {self.repo / 'backend'}:/app/backend",
            log,
        )


if __name__ == "__main__":
    unittest.main()
