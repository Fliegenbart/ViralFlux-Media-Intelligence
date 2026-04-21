"""GET / POST / DELETE /api/v1/media/cockpit/media-plan/* — CSV-upload bridge.

The cockpit has always rendered ``mediaPlan.connected = false`` and all
EUR fields as null, because no real GELO-side budget feed existed. This
router exposes a small CSV-upload contract so a PM can paste a per-
Bundesland / channel weekly budget, and the cockpit starts filling
``regions[].currentSpendEur``, ``recommendedShiftEur``, the Hero
"Empfohlener Shift"-Kachel, and ``primaryRecommendation.amountEur`` on
the spot.

Auth reuses the cockpit-gate cookie / M2M header pattern from
``media_routes_cockpit_snapshot`` — the cockpit password unlocks
upload/read/clear in one go.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db
from app.services.media.media_plan_service import (
    aggregate_by_bundesland,
    clear_plan,
    commit_plan,
    current_plan_rows,
    parse_csv,
)


logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_client(client: str) -> str:
    client = (client or "").strip()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client is required",
        )
    if len(client) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client too long (max 64 chars)",
        )
    return client


@router.post(
    "/cockpit/media-plan/upload",
    dependencies=[Depends(require_cockpit_auth)],
)
async def upload_media_plan(
    file: UploadFile = File(..., description="CSV: iso_week,bundesland,channel,eur"),
    client: str = Query("GELO", description="Client label; one plan per client."),
    dry_run: bool = Query(
        False,
        description="If true: only parse and return preview, do not persist.",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client = _validate_client(client)
    try:
        body = await file.read()
    except Exception as exc:
        logger.exception("Failed to read uploaded CSV")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read file: {exc}",
        ) from exc

    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="empty_file",
        )

    result = parse_csv(body)
    summary = result.as_summary()
    if not result.rows:
        return {
            "ok": False,
            "dry_run": dry_run,
            "committed": False,
            "summary": summary,
        }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "committed": False,
            "summary": summary,
        }

    commit_info = commit_plan(
        db, client=client, rows=result.rows, replace_current=True
    )
    logger.info(
        "Media-plan upload committed — client=%s rows=%s upload_id=%s",
        client,
        commit_info["inserted"],
        commit_info["upload_id"],
    )
    return {
        "ok": True,
        "dry_run": False,
        "committed": True,
        "summary": summary,
        "commit": commit_info,
    }


@router.get(
    "/cockpit/media-plan/current",
    dependencies=[Depends(require_cockpit_auth)],
)
async def get_current_media_plan(
    client: str = Query("GELO"),
    iso_year: int | None = Query(None, description="Filter to one ISO year."),
    iso_week: int | None = Query(None, description="Filter to one ISO week."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client = _validate_client(client)
    rows = current_plan_rows(
        db, client=client, iso_year=iso_year, iso_week=iso_week
    )
    iso_weeks = sorted({(r.iso_week_year, r.iso_week) for r in rows})
    return {
        "client": client,
        "row_count": len(rows),
        "total_eur": round(sum(float(r.eur_amount) for r in rows), 2),
        "iso_weeks": [f"{y}-W{w:02d}" for y, w in iso_weeks],
        "by_bundesland": aggregate_by_bundesland(rows),
        "rows": [
            {
                "id": r.id,
                "iso_week": f"{r.iso_week_year}-W{r.iso_week:02d}",
                "iso_week_year": r.iso_week_year,
                "iso_week_number": r.iso_week,
                "bundesland_code": r.bundesland_code,
                "channel": r.channel,
                "eur_amount": float(r.eur_amount),
                "upload_id": r.upload_id,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
            }
            for r in rows
        ],
    }


@router.delete(
    "/cockpit/media-plan/current",
    dependencies=[Depends(require_cockpit_auth)],
)
async def delete_current_media_plan(
    client: str = Query("GELO"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    client = _validate_client(client)
    deleted = clear_plan(db, client=client)
    logger.info("Media-plan cleared — client=%s rows_deleted=%s", client, deleted)
    return {"ok": True, "client": client, "rows_deleted": deleted}
