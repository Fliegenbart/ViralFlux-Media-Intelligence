import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "deploy-live.sh"


class DeployLiveScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "backend" / "scripts").mkdir(parents=True)
        (self.repo / "docker").mkdir(parents=True)
        (self.repo / "docker-compose.prod.yml").write_text("services: {}\n")
        (self.repo / "backend" / "scripts" / "smoke_test_release.py").write_text("print('stub')\n")
        (self.repo / "docker" / "Dockerfile.frontend").write_text("FROM scratch\n")

        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()
        (self.state_dir / "current_commit").write_text("prev-commit\n")
        self.log_path = self.root / "commands.log"
        self.lock_path = self.root / "deploy.lock"

        self._write_stub("git", self._git_stub())
        self._write_stub("docker", self._docker_stub())
        self._write_stub("curl", self._curl_stub())
        self._write_stub("python3", self._python_stub())
        self._write_stub("flock", self._flock_stub())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_stub(self, name: str, content: str) -> None:
        path = self.fakebin / name
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _run_script(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.fakebin}:{env['PATH']}",
                "REPO": str(self.repo),
                "LOCKFILE": str(self.lock_path),
                "MAX_HEALTH_RETRIES": "1",
                "HEALTH_INTERVAL": "0",
                "TEST_LOG": str(self.log_path),
                "TEST_GIT_STATE_DIR": str(self.state_dir),
                "TEST_ORIGIN_COMMIT": "new-commit",
                "TEST_CURL_HTTP_CODE": "200",
                "TEST_SMOKE_EXIT": "0",
            }
        )
        env.update(overrides)
        return subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.repo,
        )

    def _command_log(self) -> list[str]:
        return self.log_path.read_text().splitlines() if self.log_path.exists() else []

    def _git_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            echo "git $*" >> "$TEST_LOG"
            state_dir="${TEST_GIT_STATE_DIR}"
            current_commit_file="${state_dir}/current_commit"
            cmd="${1:-}"
            shift || true
            case "$cmd" in
              rev-parse)
                cat "$current_commit_file"
                ;;
              fetch|checkout)
                ;;
              reset)
                if [ "${1:-}" = "--hard" ]; then
                  target="${2:-}"
                  if [ "$target" = "origin/main" ]; then
                    printf '%s\n' "$TEST_ORIGIN_COMMIT" > "$current_commit_file"
                  else
                    printf '%s\n' "$target" > "$current_commit_file"
                  fi
                fi
                ;;
            esac
            """
        )

    def _docker_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            echo "docker $*" >> "$TEST_LOG"

            if [ "${1:-}" = "build" ]; then
              exit 0
            fi

            if [ "${1:-}" = "rm" ] || [ "${1:-}" = "start" ] || [ "${1:-}" = "ps" ]; then
              exit 0
            fi

            if [ "${1:-}" = "inspect" ]; then
              if [ "${2:-}" = "-f" ]; then
                format="${3:-}"
                if [[ "$format" == *".Config.Env"* ]]; then
                  cat <<'EOF'
            ENVIRONMENT=production
            DB_AUTO_CREATE_SCHEMA=false
            DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false
            STARTUP_STRICT_READINESS=true
            READINESS_REQUIRE_BROKER=true
            ADMIN_EMAIL=admin@example.com
            ADMIN_PASSWORD=VeryStrongPassword123!
            EOF
                  exit 0
                fi
                if [[ "$format" == *".Mounts"* ]]; then
                  exit 0
                fi
              fi

              case "${2:-}" in
                virusradar_db|viralflux_redis)
                  exit 0
                  ;;
                *)
                  exit 1
                  ;;
              esac
            fi

            if [ "${1:-}" = "compose" ]; then
              args="$*"
              if [[ "$args" == *" run --rm --no-deps backend alembic upgrade head"* ]]; then
                if [ "${TEST_FAIL_MIGRATION:-0}" = "1" ]; then
                  echo "migration failed" >&2
                  exit 1
                fi
                exit 0
              fi
              exit 0
            fi

            exit 0
            """
        )

    def _curl_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            echo "curl $*" >> "$TEST_LOG"
            printf '%s' "${TEST_CURL_HTTP_CODE:-200}"
            """
        )

    def _python_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            echo "python3 $*" >> "$TEST_LOG"
            if [ "${1:-}" = "backend/scripts/smoke_test_release.py" ]; then
              printf '{"status":"stub"}\n'
              exit "${TEST_SMOKE_EXIT:-0}"
            fi
            /usr/bin/env python3 "$@"
            """
        )

    def _flock_stub(self) -> str:
        return textwrap.dedent(
            """\
            #!/usr/bin/env bash
            exit 0
            """
        )

    def test_failed_migration_aborts_before_app_containers_are_replaced(self) -> None:
        result = self._run_script(TEST_FAIL_MIGRATION="1")

        self.assertNotEqual(result.returncode, 0)
        log = self._command_log()
        self.assertTrue(
            any("docker compose" in line and "run --rm --no-deps backend alembic upgrade head" in line for line in log)
        )
        self.assertFalse(any(line.startswith("docker rm -f ") for line in log))
        self.assertEqual((self.state_dir / "current_commit").read_text().strip(), "prev-commit")

    def test_smoke_failure_rolls_back_and_rebuilds_previous_release_images(self) -> None:
        result = self._run_script(TEST_SMOKE_EXIT="20")

        self.assertNotEqual(result.returncode, 0)
        log = self._command_log()

        frontend_builds = [idx for idx, line in enumerate(log) if line.startswith("docker build -t viralflux-media-frontend")]
        backend_builds = [
            idx
            for idx, line in enumerate(log)
            if "docker compose" in line and " build backend celery_worker celery_beat" in line
        ]
        rollback_resets = [idx for idx, line in enumerate(log) if line == "git reset --hard prev-commit"]

        self.assertEqual(len(frontend_builds), 2, msg="\n".join(log))
        self.assertEqual(len(backend_builds), 2, msg="\n".join(log))
        self.assertEqual(len(rollback_resets), 1, msg="\n".join(log))
        self.assertGreater(frontend_builds[1], rollback_resets[0], msg="\n".join(log))
        self.assertGreater(backend_builds[1], rollback_resets[0], msg="\n".join(log))
        self.assertEqual((self.state_dir / "current_commit").read_text().strip(), "prev-commit")


if __name__ == "__main__":
    unittest.main()
