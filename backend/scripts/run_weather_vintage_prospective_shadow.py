#!/usr/bin/env python3
"""Archive prospective weather vintage shadow runs and maintain an aggregate review report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import get_db_context
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_vintage_comparison import (
    DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_HORIZONS,
    DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_VIRUS_TYPES,
    DEFAULT_WEATHER_VINTAGE_REVIEW_RUN_PURPOSES,
    SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES,
    WeatherVintageComparisonRunner,
    build_weather_vintage_shadow_aggregate,
    load_weather_vintage_shadow_summaries,
    render_weather_vintage_shadow_aggregate_markdown,
    write_weather_vintage_shadow_archive,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--virus",
        dest="viruses",
        action="append",
        choices=list(SUPPORTED_VIRUS_TYPES),
        help="Run only the selected virus type. Can be passed multiple times.",
    )
    parser.add_argument(
        "--horizon",
        dest="horizons",
        action="append",
        type=int,
        choices=list(SUPPORTED_FORECAST_HORIZONS),
        help="Run only the selected horizon. Can be passed multiple times.",
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
        help="Optional explicit run id. Defaults to a UTC timestamp id.",
    )
    parser.add_argument(
        "--run-purpose",
        type=str,
        default="manual_eval",
        choices=list(SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES),
        help="Classify this run as smoke, manual evaluation, or scheduled shadow evidence.",
    )
    parser.add_argument(
        "--aggregate-run-purpose",
        dest="aggregate_run_purposes",
        action="append",
        choices=list(SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES),
        help="Optional filter for which run classes count towards the review aggregate.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(BACKEND_ROOT) / "app" / "ml_models" / "weather_vintage_prospective_shadow",
        help="Directory where archive runs and aggregate reports will be written.",
    )
    return parser.parse_args()


def _git_commit_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BACKEND_ROOT.parent,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    sha = result.stdout.strip()
    return sha or None


def _default_run_id(explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    return datetime.utcnow().strftime("weather_vintage_shadow_%Y%m%dT%H%M%SZ")


def _alembic_revision(db) -> str | None:
    try:
        value = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    except Exception:
        return None
    return str(value) if value else None


def _scope_manifest_entries(report: dict[str, Any], *, lookback_days: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in report.get("scopes") or []:
        entries.append(
            {
                "virus_typ": item.get("virus_typ"),
                "horizon_days": item.get("horizon_days"),
                "lookback_days": int(lookback_days),
                "comparison_eligibility": item.get("comparison_eligibility"),
                "comparison_verdict": item.get("comparison_verdict"),
                "weather_forecast_vintage_mode": (
                    (item.get("primary_mode_snapshot") or {}).get("weather_forecast_vintage_mode")
                    or "legacy_issue_time_only"
                ),
                "weather_vintage_run_identity_coverage": item.get(
                    "weather_vintage_run_identity_coverage"
                )
                or {},
                "coverage_test": (item.get("weather_vintage_backtest_coverage") or {}).get(
                    "coverage_test"
                ),
                "primary_mode_snapshot": item.get("primary_mode_snapshot") or {},
                "shadow_mode_snapshot": item.get("shadow_mode_snapshot") or {},
            }
        )
    return entries


def run_prospective_shadow(
    *,
    output_root: Path,
    viruses: list[str],
    horizons: list[int],
    lookback_days: int,
    run_id: str | None = None,
    run_purpose: str = "manual_eval",
    aggregate_run_purposes: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    resolved_run_id = _default_run_id(run_id)
    generated_at = datetime.utcnow().isoformat()

    with get_db_context() as db:
        runner = WeatherVintageComparisonRunner(db)
        report = runner.run(
            virus_types=viruses,
            horizon_days_list=horizons,
            lookback_days=lookback_days,
        )
        alembic_revision = _alembic_revision(db)

    archive_dir = output_root / "runs" / resolved_run_id
    manifest = {
        "status": "success",
        "comparison_type": "weather_vintage_prospective_shadow",
        "run_purpose": run_purpose,
        "generated_at": generated_at,
        "output_root": str(output_root),
        "archive_dir": str(archive_dir),
        "git_commit_sha": _git_commit_sha(),
        "alembic_revision": alembic_revision,
        "matrix": {
            "virus_types": viruses,
            "horizon_days_list": horizons,
            "lookback_days": int(lookback_days),
        },
        "legacy_mode_default": "legacy_issue_time_only",
        "shadow_mode": "run_timestamp_v1",
    }
    try:
        written_paths = write_weather_vintage_shadow_archive(
            archive_dir=archive_dir,
            report=report,
            generated_at=generated_at,
            run_id=resolved_run_id,
            manifest=manifest,
        )
    except FileExistsError as exc:
        raise RuntimeError(
            f"Shadow archive already exists for run_id='{resolved_run_id}'. Choose a new run_id or remove the old archive first."
        ) from exc

    effective_aggregate_purposes = tuple(
        aggregate_run_purposes or DEFAULT_WEATHER_VINTAGE_REVIEW_RUN_PURPOSES
    )
    aggregate = build_weather_vintage_shadow_aggregate(
        load_weather_vintage_shadow_summaries(
            output_root,
            included_run_purposes=effective_aggregate_purposes,
        )
    )
    aggregate_json_path = output_root / "aggregate_report.json"
    aggregate_md_path = output_root / "aggregate_report.md"
    output_root.mkdir(parents=True, exist_ok=True)
    aggregate_json_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    aggregate_md_path.write_text(
        render_weather_vintage_shadow_aggregate_markdown(aggregate),
        encoding="utf-8",
    )

    run_manifest_path = written_paths["run_manifest"]
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    run_summary = json.loads(written_paths["summary_json"].read_text(encoding="utf-8"))
    run_manifest.update(
        {
            "comparison_eligibility_counts": (run_summary.get("summary") or {}),
            "scope_runs": _scope_manifest_entries(
                run_summary,
                lookback_days=lookback_days,
            ),
            "run_purpose": run_purpose,
            "aggregate_run_purposes": list(effective_aggregate_purposes),
            "aggregate_report_json": str(aggregate_json_path),
            "aggregate_report_md": str(aggregate_md_path),
        }
    )
    run_manifest_path.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    return {
        "status": "success",
        "run_id": resolved_run_id,
        "archive_dir": str(archive_dir),
        "aggregate_report_json": str(aggregate_json_path),
        "aggregate_report_md": str(aggregate_md_path),
        "alembic_revision": alembic_revision,
        "run_purpose": run_purpose,
        "aggregate_run_purposes": list(effective_aggregate_purposes),
    }


def main() -> int:
    args = _parse_args()
    selected_viruses = args.viruses or list(DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_VIRUS_TYPES)
    selected_horizons = args.horizons or list(DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_HORIZONS)
    result = run_prospective_shadow(
        output_root=args.output_root,
        viruses=selected_viruses,
        horizons=selected_horizons,
        lookback_days=int(args.lookback_days),
        run_id=args.run_id,
        run_purpose=args.run_purpose,
        aggregate_run_purposes=args.aggregate_run_purposes,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
