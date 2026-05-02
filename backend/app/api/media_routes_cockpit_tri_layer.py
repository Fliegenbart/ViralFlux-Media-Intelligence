"""GET /api/v1/media/cockpit/tri-layer/snapshot."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db
from app.services.media.cockpit.tri_layer_evidence import (
    TriLayerSnapshotResponse,
    build_tri_layer_snapshot,
)
from app.services.research.tri_layer.backtest import (
    read_latest_tri_layer_backtest_report,
    read_tri_layer_backtest_report,
)
from app.services.research.tri_layer.tasks import run_tri_layer_backtest_task

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"RSV A", "Influenza A", "Influenza B", "SARS-CoV-2"}
_SUPPORTED_HORIZONS = {3, 7, 14}
_SUPPORTED_MODES = {"research", "shadow"}
_SUPPORTED_BACKTEST_MODES = {"historical_cutoff"}


class TriLayerBacktestRequest(BaseModel):
    virus_typ: str = "Influenza A"
    brand: str = "gelo"
    horizon_days: int = Field(default=7)
    start_date: str
    end_date: str
    mode: Literal["historical_cutoff"] = "historical_cutoff"
    include_sales: bool = False

    @model_validator(mode="after")
    def validate_backtest_request(self) -> "TriLayerBacktestRequest":
        if self.virus_typ not in _SUPPORTED_VIRUSES:
            raise ValueError(f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}")
        if int(self.horizon_days) not in _SUPPORTED_HORIZONS:
            raise ValueError(f"horizon_days must be one of {sorted(_SUPPORTED_HORIZONS)}")
        if self.mode not in _SUPPORTED_BACKTEST_MODES:
            raise ValueError(f"mode must be one of {sorted(_SUPPORTED_BACKTEST_MODES)}")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


@router.get(
    "/cockpit/tri-layer/snapshot",
    dependencies=[Depends(require_cockpit_auth)],
    response_model=TriLayerSnapshotResponse,
)
async def get_cockpit_tri_layer_snapshot(
    virus_typ: str = Query("Influenza A", description="Virus scope for the experimental tri-layer snapshot."),
    horizon_days: int = Query(7, description="Evidence horizon in days. Allowed: 3, 7, 14."),
    brand: str = Query("gelo", description="Brand key for optional commercial evidence lookup."),
    client: str = Query("GELO", description="Client label for cockpit context."),
    mode: Literal["research", "shadow"] = Query("research", description="Experimental display mode."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )
    if int(horizon_days) not in _SUPPORTED_HORIZONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"horizon_days must be one of {sorted(_SUPPORTED_HORIZONS)}",
        )
    if mode not in _SUPPORTED_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode must be one of {sorted(_SUPPORTED_MODES)}",
        )
    try:
        payload = build_tri_layer_snapshot(
            db,
            virus_typ=virus_typ,
            horizon_days=int(horizon_days),
            brand=brand,
            client=client,
            mode=mode,
        )
        return payload.model_dump(mode="json")
    except Exception as exc:  # pragma: no cover - endpoint safety net
        logger.exception("cockpit/tri-layer/snapshot payload build failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tri-Layer Evidence Fusion konnte nicht erzeugt werden: {exc}",
        ) from exc


@router.post(
    "/cockpit/tri-layer/backtest",
    dependencies=[Depends(require_cockpit_auth)],
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_cockpit_tri_layer_backtest(body: TriLayerBacktestRequest) -> dict[str, str]:
    try:
        task = run_tri_layer_backtest_task.delay(
            virus_typ=body.virus_typ,
            brand=body.brand,
            horizon_days=int(body.horizon_days),
            start_date=body.start_date,
            end_date=body.end_date,
            mode=body.mode,
            include_sales=bool(body.include_sales),
        )
    except Exception as exc:
        logger.exception("Could not enqueue Tri-Layer research backtest")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Celery broker not reachable: {exc}",
        ) from exc

    return {
        "status": "started",
        "run_id": str(task.id),
        "status_url": f"/api/v1/media/cockpit/tri-layer/backtest/{task.id}",
    }


@router.get(
    "/cockpit/tri-layer/backtest/latest",
    dependencies=[Depends(require_cockpit_auth)],
)
async def get_latest_cockpit_tri_layer_backtest(
    virus_typ: str = Query("Influenza A"),
    horizon_days: int = Query(7),
) -> dict[str, Any]:
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )
    if int(horizon_days) not in _SUPPORTED_HORIZONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"horizon_days must be one of {sorted(_SUPPORTED_HORIZONS)}",
        )
    report = read_latest_tri_layer_backtest_report(
        virus_typ=virus_typ,
        horizon_days=int(horizon_days),
    )
    return {"report": report}


@router.get(
    "/cockpit/tri-layer/backtest/{run_id}",
    dependencies=[Depends(require_cockpit_auth)],
)
async def get_cockpit_tri_layer_backtest_status(run_id: str) -> dict[str, Any]:
    task_result = celery_app.AsyncResult(run_id)
    response: dict[str, Any] = {
        "run_id": run_id,
        "status": task_result.status,
    }
    if task_result.status == "PROGRESS":
        response["meta"] = task_result.info
    elif task_result.status == "SUCCESS":
        response["report"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.result)
    else:
        report = read_tri_layer_backtest_report(run_id)
        if report is not None:
            response["status"] = "SUCCESS"
            response["report"] = report
    return response
