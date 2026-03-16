#!/usr/bin/env python3
"""Backfill SurvStat API data across all available years."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
os.environ.setdefault("POSTGRES_PORT", "15432")
os.environ.setdefault("POSTGRES_USER", "virusradar")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme")
os.environ.setdefault("POSTGRES_DB", "virusradar_db")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "testsecret123")
os.environ.setdefault("ADMIN_EMAIL", "test@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "testpassword123")

from app.db.session import get_db_context
from app.models.database import KreisEinwohner, SurvstatKreisData, SurvstatWeeklyData
from app.services.data_ingest.survstat_api_service import (
    NS_MDX,
    NS_SVC,
    SurvstatApiService,
    _tag,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    years = _resolve_years(args.start_year, args.end_year)
    chunks = [years[i:i + args.chunk_size] for i in range(0, len(years), args.chunk_size)]
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    summary_path = output_dir / f"{run_id}_survstat_backfill.json"

    summary: dict[str, object] = {
        "run_id": run_id,
        "generated_at": datetime.utcnow().isoformat(),
        "years": years,
        "chunk_size": args.chunk_size,
        "reference_sync": None,
        "results": [],
    }

    if not args.skip_ref_sync:
        summary["reference_sync"] = _sync_references()
        _write_summary(summary_path, summary)

    print(
        f"Backfill years {years[0]}-{years[-1]} in {len(chunks)} chunks "
        f"(size={args.chunk_size})",
        flush=True,
    )

    for chunk in chunks:
        print(f"CHUNK_START {chunk[0]}-{chunk[-1]}", flush=True)
        with get_db_context() as db:
            service = SurvstatApiService(db)
            try:
                result = service.run(years=chunk, diseases=None)
            finally:
                db.rollback()
            counts = {
                "kreis_rows": db.query(SurvstatKreisData).count(),
                "weekly_rows": db.query(SurvstatWeeklyData).count(),
                "kreis_ref_rows": db.query(KreisEinwohner).count(),
            }

        chunk_payload = {
            "chunk": chunk,
            "result": result,
            "counts_after_chunk": counts,
        }
        results = summary["results"]
        assert isinstance(results, list)
        results.append(chunk_payload)
        summary["generated_at"] = datetime.utcnow().isoformat()
        _write_summary(summary_path, summary)
        print(json.dumps(chunk_payload, ensure_ascii=True), flush=True)

    print(f"SUMMARY_WRITTEN {summary_path}", flush=True)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a full SurvStat API backfill.")
    parser.add_argument("--start-year", type=int, help="Optional start year.")
    parser.add_argument("--end-year", type=int, help="Optional end year.")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=4,
        help="How many years to fetch per chunk.",
    )
    parser.add_argument(
        "--skip-ref-sync",
        action="store_true",
        help="Skip RKI-Kreis discovery and Destatis population sync.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "data" / "processed" / "survstat_api_bulk"),
        help="Directory for JSON progress summaries.",
    )
    return parser.parse_args(argv)


def _resolve_years(start_year: int | None, end_year: int | None) -> list[int]:
    if start_year is not None and end_year is not None:
        if start_year > end_year:
            raise ValueError("start_year must be <= end_year")
        return list(range(start_year, end_year + 1))

    with get_db_context() as db:
        service = SurvstatApiService(db)
        body = (
            f'<GetAllHierarchyMembers xmlns="{NS_SVC}">'
            f'<request xmlns:d="{NS_MDX}">'
            f"<d:Cube>SurvStat</d:Cube>"
            f"<d:HierarchyId>{service.H_YEAR}</d:HierarchyId>"
            f"<d:Language>German</d:Language>"
            f"</request>"
            f"</GetAllHierarchyMembers>"
        )
        root = service._soap_call("GetAllHierarchyMembers", body)

    years: list[int] = []
    for member in root.iter(_tag(NS_MDX, "HierarchyMember")):
        caption_el = member.find(_tag(NS_MDX, "Caption"))
        caption = (caption_el.text or "").strip() if caption_el is not None else ""
        if re.fullmatch(r"\d{4}", caption):
            years.append(int(caption))

    years = sorted(set(years))
    if not years:
        raise RuntimeError("Could not discover any SurvStat years from the API.")

    if start_year is not None:
        years = [year for year in years if year >= start_year]
    if end_year is not None:
        years = [year for year in years if year <= end_year]
    if not years:
        raise RuntimeError("No SurvStat years left after applying the requested filters.")
    return years


def _sync_references() -> dict[str, object]:
    with get_db_context() as db:
        service = SurvstatApiService(db)
        discover = service.discover_and_seed_kreise()
        sync = service.sync_kreis_einwohner_from_destatis()
        db.rollback()
    return {
        "discover": discover,
        "sync": sync,
    }


def _write_summary(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
