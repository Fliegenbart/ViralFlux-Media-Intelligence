#!/usr/bin/env python3
"""Run the daily pilot h7 weather vintage shadow job and immediately evaluate its health."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_weather_vintage_shadow_health import run_shadow_health_check
from scripts.run_weather_vintage_pilot_h7_shadow import PilotShadowLockError, run_pilot_h7_shadow


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(BACKEND_ROOT) / "app" / "ml_models" / "weather_vintage_prospective_shadow",
        help="Directory where archive runs and aggregate reports will be written.",
    )
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
        help="Classify the wrapper run. Default is the real scheduled shadow class.",
    )
    parser.add_argument(
        "--lock-path",
        type=Path,
        default=None,
        help="Optional explicit lockfile path. Defaults to <output-root>/pilot_h7_shadow.lock",
    )
    parser.add_argument(
        "--max-run-age-hours",
        type=int,
        default=36,
        help="Warn when the latest scheduled shadow run is older than this many hours.",
    )
    parser.add_argument(
        "--max-days-without-comparable",
        type=int,
        default=14,
        help="Warn when a scope has no comparable run for this many days.",
    )
    parser.add_argument(
        "--max-insufficient-identity-streak",
        type=int,
        default=3,
        help="Warn when too many insufficient_identity runs happen in a row.",
    )
    return parser.parse_args()


def run_pilot_h7_shadow_ops(
    *,
    output_root: Path,
    lookback_days: int,
    run_id: str | None,
    run_purpose: str,
    lock_path: Path | None = None,
    max_run_age_hours: int = 36,
    max_days_without_comparable: int = 14,
    max_insufficient_identity_streak: int = 3,
    shadow_runner=run_pilot_h7_shadow,
    health_runner=run_shadow_health_check,
) -> tuple[int, dict[str, object]]:
    shadow_result = shadow_runner(
        output_root=output_root,
        lookback_days=int(lookback_days),
        run_id=run_id,
        run_purpose=run_purpose,
        lock_path=lock_path,
    )
    health_result = health_runner(
        output_root=output_root,
        run_purposes=["scheduled_shadow"],
        max_run_age_hours=int(max_run_age_hours),
        max_days_without_comparable=int(max_days_without_comparable),
        max_insufficient_identity_streak=int(max_insufficient_identity_streak),
    )
    exit_code = int(health_result.get("exit_code") or 0)
    payload = {
        "status": "success" if exit_code == 0 else "attention_required",
        "shadow_run": shadow_result,
        "health_check": health_result,
    }
    return exit_code, payload


def main() -> int:
    args = _parse_args()
    try:
        exit_code, payload = run_pilot_h7_shadow_ops(
            output_root=args.output_root,
            lookback_days=int(args.lookback_days),
            run_id=args.run_id,
            run_purpose=args.run_purpose,
            lock_path=args.lock_path,
            max_run_age_hours=int(args.max_run_age_hours),
            max_days_without_comparable=int(args.max_days_without_comparable),
            max_insufficient_identity_streak=int(args.max_insufficient_identity_streak),
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
    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
