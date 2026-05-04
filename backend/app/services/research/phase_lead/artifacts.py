"""Load cached manual phase-lead MAP artifacts for cockpit snapshots."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PHASE_LEAD_ARTIFACT_DIR_ENV = "PHASE_LEAD_ARTIFACT_DIR"
DEFAULT_PHASE_LEAD_ARTIFACT_DIRS = (
    Path("/app/data/phase_lead"),
    Path("artifacts/phase_lead"),
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _coerce_iso_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value[:10]


def _artifact_dirs() -> list[Path]:
    paths: list[Path] = []
    configured = os.getenv(PHASE_LEAD_ARTIFACT_DIR_ENV, "").strip()
    if configured:
        paths.append(Path(configured))
    paths.extend(DEFAULT_PHASE_LEAD_ARTIFACT_DIRS)
    return paths


def _candidate_paths(virus_typ: str) -> list[Path]:
    slug = _slug(virus_typ)
    candidates: list[Path] = []
    for directory in _artifact_dirs():
        latest = directory / f"manual_phase_lead_{slug}_latest.json"
        candidates.append(latest)
        if directory.exists():
            candidates.extend(
                sorted(
                    directory.glob(f"manual_phase_lead_{slug}_map_iter*_*.json"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _matches_request(
    artifact: dict[str, Any],
    *,
    virus_typ: str,
    issue_date: date | datetime | str | None,
    window_days: int,
    n_samples: int,
    region_codes: list[str] | None,
) -> bool:
    if region_codes:
        return False

    snapshot = artifact.get("snapshot") if "snapshot" in artifact else artifact
    if not isinstance(snapshot, dict):
        return False
    summary = snapshot.get("summary") or {}
    manual_run = artifact.get("manual_run") or {}

    if snapshot.get("virus_typ") != virus_typ:
        return False
    if summary.get("fit_mode") != "map_optimization":
        return False
    if manual_run.get("virus_typ") and manual_run.get("virus_typ") != virus_typ:
        return False
    if int(manual_run.get("window_days") or window_days) != int(window_days):
        return False
    if int(manual_run.get("n_samples") or n_samples) != int(n_samples):
        return False

    requested_issue_date = _coerce_iso_date(issue_date)
    if requested_issue_date and snapshot.get("as_of") != requested_issue_date:
        return False
    return True


def load_cached_phase_lead_map_snapshot(
    *,
    virus_typ: str,
    issue_date: date | datetime | str | None = None,
    window_days: int = 70,
    region_codes: list[str] | None = None,
    n_samples: int = 80,
) -> dict[str, Any] | None:
    """Return the newest matching manual MAP snapshot, if one is available."""

    for path in _candidate_paths(virus_typ):
        if not path.exists():
            continue
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping unreadable phase-lead artifact %s: %s", path, exc)
            continue
        if not _matches_request(
            artifact,
            virus_typ=virus_typ,
            issue_date=issue_date,
            window_days=window_days,
            n_samples=n_samples,
            region_codes=region_codes,
        ):
            continue
        snapshot = artifact.get("snapshot") if "snapshot" in artifact else artifact
        return dict(snapshot)
    return None
