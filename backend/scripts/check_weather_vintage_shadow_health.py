#!/usr/bin/env python3
"""Check the health of archived prospective weather vintage shadow runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ml.weather_vintage_comparison import (
    DEFAULT_WEATHER_VINTAGE_REVIEW_RUN_PURPOSES,
    SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES,
    WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE,
    WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK,
    WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS,
    build_weather_vintage_shadow_health_report,
    load_weather_vintage_shadow_summaries,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(BACKEND_ROOT) / "app" / "ml_models" / "weather_vintage_prospective_shadow",
        help="Root directory that contains archived shadow runs.",
    )
    parser.add_argument(
        "--run-purpose",
        dest="run_purposes",
        action="append",
        choices=list(SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES),
        help="Optional run classes to include. Defaults to scheduled_shadow only.",
    )
    parser.add_argument(
        "--max-run-age-hours",
        type=int,
        default=WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS,
        help="Warn when the latest scheduled shadow run is older than this many hours.",
    )
    parser.add_argument(
        "--max-days-without-comparable",
        type=int,
        default=WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE,
        help="Warn when a scope has no comparable run for this many days.",
    )
    parser.add_argument(
        "--max-insufficient-identity-streak",
        type=int,
        default=WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK,
        help="Warn when too many insufficient_identity runs happen in a row.",
    )
    return parser.parse_args()


def run_shadow_health_check(
    *,
    output_root: Path,
    run_purposes: tuple[str, ...] | list[str] | None = None,
    max_run_age_hours: int = WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS,
    max_days_without_comparable: int = WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE,
    max_insufficient_identity_streak: int = WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK,
) -> dict[str, object]:
    summaries = load_weather_vintage_shadow_summaries(
        output_root,
        included_run_purposes=tuple(run_purposes or DEFAULT_WEATHER_VINTAGE_REVIEW_RUN_PURPOSES),
    )
    return build_weather_vintage_shadow_health_report(
        summaries,
        max_run_age_hours=max_run_age_hours,
        max_days_without_comparable=max_days_without_comparable,
        max_insufficient_identity_streak=max_insufficient_identity_streak,
    )


def main() -> int:
    args = _parse_args()
    report = run_shadow_health_check(
        output_root=args.output_root,
        run_purposes=args.run_purposes,
        max_run_age_hours=int(args.max_run_age_hours),
        max_days_without_comparable=int(args.max_days_without_comparable),
        max_insufficient_identity_streak=int(args.max_insufficient_identity_streak),
    )
    print(json.dumps(report, indent=2))
    return int(report.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
