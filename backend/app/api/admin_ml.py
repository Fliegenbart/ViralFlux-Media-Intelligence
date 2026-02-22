"""Admin-only endpoints for ML model management.

Provides a secured trigger for XGBoost meta-learner training
and a status polling endpoint for Celery task progress.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_admin
from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)
router = APIRouter()


class TrainXGBoostRequest(BaseModel):
    virus_typ: Optional[str] = None  # None → train all four virus types


@router.post("/train-xgboost", status_code=status.HTTP_202_ACCEPTED)
async def train_xgboost(
    request: TrainXGBoostRequest = Body(default_factory=TrainXGBoostRequest),
    current_user: dict = Depends(get_current_admin),
):
    """Trigger XGBoost meta-learner training (async via Celery).

    Admin-only. Returns 202 Accepted with a ``task_id`` for polling.
    """
    from app.services.ml.tasks import train_xgboost_model_task

    try:
        task = train_xgboost_model_task.delay(virus_typ=request.virus_typ)
    except Exception as exc:
        logger.error(f"Celery enqueue failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Celery Broker nicht erreichbar. Bitte Redis/Worker pruefen.",
        ) from exc

    return {
        "message": "XGBoost training gestartet",
        "task_id": task.id,
        "virus_typ": request.virus_typ or "all",
        "status_url": f"/api/v1/admin/ml/status/{task.id}",
    }


@router.get("/status/{task_id}")
async def get_training_status(task_id: str):
    """Poll Celery task status for a training run."""
    task_result = celery_app.AsyncResult(task_id)

    response: dict = {
        "task_id": task_id,
        "status": task_result.status,
    }

    if task_result.status == "PROGRESS":
        response["meta"] = task_result.info
    elif task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.result)

    return response
