#!/usr/bin/env python3
"""Run the standard prospective weather vintage shadow scopes for the pilot h7 review cycle."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.run_weather_vintage_prospective_shadow import run_prospective_shadow

LOCK_FILENAME = "pilot_h7_shadow.lock"


class PilotShadowLockError(RuntimeError):
    """Raised when the scheduler wrapper detects an overlapping run."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=900,
        help="Historical training window used for every comparison scope.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional explicit run id.",
    )
    parser.add_argument(
        "--run-purpose",
        type=str,
        default="scheduled_shadow",
        choices=["smoke", "manual_eval", "scheduled_shadow"],
        help="Classify the pilot wrapper run. Default is the real scheduled shadow class.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(BACKEND_ROOT) / "app" / "ml_models" / "weather_vintage_prospective_shadow",
        help="Directory where archive runs and aggregate reports will be written.",
    )
    parser.add_argument(
        "--lock-path",
        type=Path,
        default=None,
        help="Optional explicit lockfile path. Defaults to <output-root>/pilot_h7_shadow.lock",
    )
    return parser.parse_args()


def _default_run_id(explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    return datetime.utcnow().strftime("weather_vintage_shadow_%Y%m%dT%H%M%SZ")


def _default_lock_path(output_root: Path, explicit_lock_path: Path | None) -> Path:
    return explicit_lock_path or (output_root / LOCK_FILENAME)


def _environment_marker() -> str | None:
    for key in ("APP_ENV", "ENVIRONMENT", "RAILWAY_ENVIRONMENT", "RENDER_ENVIRONMENT", "CI"):
        value = os.getenv(key)
        if value:
            return f"{key}={value}"
    return None


def acquire_wrapper_lock(lock_path: Path) -> dict[str, object]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": int(os.getpid()),
        "hostname": socket.gethostname(),
        "started_at": datetime.utcnow().isoformat(),
    }
    if lock_path.exists():
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        existing_pid = existing.get("pid")
        existing_host = existing.get("hostname")
        if existing_pid and existing_host == payload["hostname"]:
            try:
                os.kill(int(existing_pid), 0)
                raise PilotShadowLockError(
                    f"Another pilot h7 shadow run is already active (pid={existing_pid}, lock={lock_path})."
                )
            except ProcessLookupError:
                lock_path.unlink(missing_ok=True)
            except PermissionError as exc:
                raise PilotShadowLockError(
                    f"Unable to verify active lock owner for {lock_path}; refusing overlapping run."
                ) from exc
        else:
            raise PilotShadowLockError(
                f"Existing lockfile detected at {lock_path}; refusing overlapping run."
            )
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return payload


def release_wrapper_lock(lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)


def _update_run_manifest(archive_dir: Path, updates: dict[str, object]) -> None:
    manifest_path = archive_dir / "run_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(updates)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def run_pilot_h7_shadow(
    *,
    output_root: Path,
    lookback_days: int,
    run_id: str | None,
    run_purpose: str,
    lock_path: Path | None = None,
    runner=run_prospective_shadow,
) -> dict[str, object]:
    resolved_run_id = _default_run_id(run_id)
    archive_dir = output_root / "runs" / resolved_run_id
    resolved_lock_path = _default_lock_path(output_root, lock_path)
    started_at = datetime.utcnow().isoformat()
    hostname = socket.gethostname()
    environment_marker = _environment_marker()
    acquire_wrapper_lock(resolved_lock_path)
    try:
        result = runner(
            output_root=output_root,
            viruses=["Influenza A", "SARS-CoV-2"],
            horizons=[7],
            lookback_days=int(lookback_days),
            run_id=resolved_run_id,
            run_purpose=run_purpose,
            aggregate_run_purposes=["scheduled_shadow"],
        )
        finished_at = datetime.utcnow().isoformat()
        _update_run_manifest(
            archive_dir,
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "exit_status": 0,
                "hostname": hostname,
                "environment_marker": environment_marker,
                "lock_path": str(resolved_lock_path),
                "scheduler_entrypoint": "run_weather_vintage_pilot_h7_shadow.py",
            },
        )
        return result
    except Exception as exc:
        finished_at = datetime.utcnow().isoformat()
        _update_run_manifest(
            archive_dir,
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "exit_status": 1,
                "hostname": hostname,
                "environment_marker": environment_marker,
                "lock_path": str(resolved_lock_path),
                "scheduler_entrypoint": "run_weather_vintage_pilot_h7_shadow.py",
                "error_message": str(exc),
            },
        )
        raise
    finally:
        release_wrapper_lock(resolved_lock_path)


def main() -> int:
    args = _parse_args()
    try:
        result = run_pilot_h7_shadow(
            output_root=args.output_root,
            lookback_days=int(args.lookback_days),
            run_id=args.run_id,
            run_purpose=args.run_purpose,
            lock_path=args.lock_path,
        )
    except PilotShadowLockError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": "lock_conflict",
                    "message": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": "runtime_error",
                    "message": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
