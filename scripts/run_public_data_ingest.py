#!/usr/bin/env python3
"""Run public data ingestion locally without going through the API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.core.config import get_settings
from app.db.session import get_db_context, init_db
from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.are_konsultation_service import AREKonsultationIngestionService
from app.services.data_ingest.bfarm_service import BfarmIngestionService
from app.services.data_ingest.er_admissions_service import ERAdmissionsIngestionService
from app.services.data_ingest.grippeweb_service import GrippeWebIngestionService
from app.services.data_ingest.holidays_service import SchoolHolidaysService
from app.services.data_ingest.influenza_service import InfluenzaIngestionService
from app.services.data_ingest.pollen_service import PollenService
from app.services.data_ingest.rsv_service import RSVIngestionService
from app.services.data_ingest.survstat_service import SurvstatIngestionService
from app.services.data_ingest.trends_service import GoogleTrendsService
from app.services.data_ingest.weather_service import WeatherService
from app.services.ml.wave_prediction_utils import json_safe

AVAILABLE_SOURCES: tuple[str, ...] = (
    "amelag",
    "grippeweb",
    "are_konsultation",
    "influenza",
    "rsv",
    "er_admissions",
    "holidays",
    "trends",
    "weather",
    "pollen",
    "bfarm",
    "survstat",
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_path = _resolve_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    requested_sources = _resolve_sources(args.sources)
    results: dict[str, Any] = {}
    notes: list[str] = []
    had_failure = False

    init_db()

    for source in requested_sources:
        try:
            if source == "amelag":
                with get_db_context() as db:
                    results[source] = AmelagIngestionService(db).run_full_import()
            elif source == "grippeweb":
                with get_db_context() as db:
                    results[source] = GrippeWebIngestionService(db).run_full_import()
            elif source == "are_konsultation":
                with get_db_context() as db:
                    results[source] = AREKonsultationIngestionService(db).run_full_import()
            elif source == "influenza":
                with get_db_context() as db:
                    results[source] = InfluenzaIngestionService(db).run_full_import()
            elif source == "rsv":
                with get_db_context() as db:
                    results[source] = RSVIngestionService(db).run_full_import()
            elif source == "er_admissions":
                with get_db_context() as db:
                    results[source] = ERAdmissionsIngestionService(db).run_full_import()
            elif source == "holidays":
                with get_db_context() as db:
                    results[source] = SchoolHolidaysService(db).run_full_import()
            elif source == "trends":
                with get_db_context() as db:
                    results[source] = GoogleTrendsService(db).run_full_import(months=args.trends_months)
            elif source == "weather":
                with get_db_context() as db:
                    results[source] = WeatherService(db).run_full_import(include_forecast=True)
            elif source == "pollen":
                with get_db_context() as db:
                    results[source] = PollenService(db).run_full_import()
            elif source == "bfarm":
                results[source] = BfarmIngestionService().run_full_import()
            elif source == "survstat":
                survstat_path = _resolve_survstat_path(args.survstat_folder)
                if survstat_path is None:
                    results[source] = {
                        "success": False,
                        "skipped": True,
                        "reason": "No SurvStat folder provided or found.",
                    }
                    notes.append(
                        "SurvStat import was skipped. Wave evaluation still needs SurvStat truth "
                        "for targets, so the DB-backed wave harness will remain empty until that import exists."
                    )
                else:
                    with get_db_context() as db:
                        results[source] = SurvstatIngestionService(db).run_local_import(str(survstat_path))
            else:
                results[source] = {
                    "success": False,
                    "error": f"Unsupported source '{source}'.",
                }
                had_failure = True
        except Exception as exc:
            results[source] = {
                "success": False,
                "error": str(exc),
            }
            had_failure = True

    if "survstat" not in requested_sources:
        notes.append(
            "This run did not include SurvStat. Public source ingestion can still populate leading indicators, "
            "but wave-v1 backtests need SurvStat truth rows before a DB-backed evaluation can succeed."
        )

    payload = {
        "status": "error" if had_failure else "ok",
        "requested_sources": requested_sources,
        "generated_at": datetime.utcnow().isoformat(),
        "results": results,
        "notes": notes,
    }
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, ensure_ascii=True)

    print(f"Wrote ingestion summary to {output_path}")
    return 1 if had_failure else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run public data ingestion locally.")
    parser.add_argument(
        "--sources",
        default="all",
        help=(
            "Comma-separated source list or 'all'. "
            f"Available: {', '.join(AVAILABLE_SOURCES)}"
        ),
    )
    parser.add_argument(
        "--survstat-folder",
        help="Optional folder for manual SurvStat CSV imports.",
    )
    parser.add_argument(
        "--trends-months",
        type=int,
        default=3,
        help="How many months of Google Trends history to import.",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path. Defaults to data/processed/public_ingest/<timestamp>.json.",
    )
    return parser.parse_args(argv)


def _resolve_sources(raw_sources: str) -> list[str]:
    if raw_sources.strip().lower() == "all":
        return list(AVAILABLE_SOURCES)
    sources = [part.strip() for part in raw_sources.split(",") if part.strip()]
    unknown = sorted(set(sources) - set(AVAILABLE_SOURCES))
    if unknown:
        raise ValueError(f"Unsupported sources requested: {', '.join(unknown)}")
    return sources


def _resolve_output_path(raw_output: str | None) -> Path:
    if raw_output:
        return Path(raw_output).expanduser().resolve()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return (REPO_ROOT / "data" / "processed" / "public_ingest" / f"{timestamp}.json").resolve()


def _resolve_survstat_path(raw_folder: str | None) -> Path | None:
    candidates: list[Path] = []
    if raw_folder:
        candidates.append(Path(raw_folder).expanduser().resolve())
    else:
        default_path = Path(get_settings().SURVSTAT_LOCAL_DIR).expanduser()
        if not default_path.is_absolute():
            default_path = (BACKEND_ROOT / default_path).resolve()
        candidates.append(default_path)

    for path in candidates:
        if path.exists() and path.is_dir():
            return path
    return None


if __name__ == "__main__":
    raise SystemExit(main())
