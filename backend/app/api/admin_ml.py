"""Admin-only endpoints for ML model management.

Provides a secured trigger for XGBoost meta-learner training
and a status polling endpoint for Celery task progress.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, model_validator

from app.api.deps import get_current_admin
from app.core.rate_limit import limiter
from app.core.celery_app import celery_app
from app.services.ml.training_contract import normalize_training_selection

logger = logging.getLogger(__name__)
router = APIRouter()


class TrainXGBoostRequest(BaseModel):
    virus_typ: Optional[str] = None  # None → train all four virus types
    virus_types: Optional[list[str]] = None
    include_internal_history: bool = True
    research_mode: bool = False

    @model_validator(mode="after")
    def validate_training_selection(self) -> "TrainXGBoostRequest":
        normalize_training_selection(
            virus_typ=self.virus_typ,
            virus_types=self.virus_types,
        )
        return self

    def normalized_selection(self):
        return normalize_training_selection(
            virus_typ=self.virus_typ,
            virus_types=self.virus_types,
        )


class TrainRegionalModelsRequest(BaseModel):
    virus_typ: Optional[str] = None  # None → train all supported regional virus models
    virus_types: Optional[list[str]] = None

    @model_validator(mode="after")
    def validate_training_selection(self) -> "TrainRegionalModelsRequest":
        normalize_training_selection(
            virus_typ=self.virus_typ,
            virus_types=self.virus_types,
        )
        return self

    def normalized_selection(self):
        return normalize_training_selection(
            virus_typ=self.virus_typ,
            virus_types=self.virus_types,
        )


@router.post("/train-xgboost", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def train_xgboost(
    request: Request,
    body: TrainXGBoostRequest = Body(default_factory=TrainXGBoostRequest),
    current_user: dict = Depends(get_current_admin),
):
    """Trigger XGBoost meta-learner training (async via Celery).

    Admin-only. Returns 202 Accepted with a ``task_id`` for polling.
    """
    from app.services.ml.tasks import train_xgboost_model_task
    selection = body.normalized_selection()

    try:
        task = train_xgboost_model_task.delay(
            virus_types=list(selection.virus_types),
            include_internal_history=body.include_internal_history,
            research_mode=body.research_mode,
        )
    except Exception as exc:
        logger.error(f"Celery enqueue failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Celery Broker nicht erreichbar. Bitte Redis/Worker prüfen.",
        ) from exc

    return {
        "message": "XGBoost training gestartet",
        "task_id": task.id,
        "virus_typ": selection.virus_typ,
        "virus_types": list(selection.virus_types),
        "selection_mode": selection.mode,
        "include_internal_history": body.include_internal_history,
        "research_mode": body.research_mode,
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


@router.post("/train-regional", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def train_regional_models(
    request: Request,
    body: TrainRegionalModelsRequest = Body(default_factory=TrainRegionalModelsRequest),
    current_user: dict = Depends(get_current_admin),
):
    """Train pooled regional panel models for one, many, or all supported virus types."""
    selection = body.normalized_selection()
    try:
        task = celery_app.send_task(
            "train_regional_models_task",
            kwargs={"virus_types": list(selection.virus_types)},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Celery broker not reachable: {exc}",
        ) from exc

    return {
        "status": "regional_training_started",
        "virus_typ": selection.virus_typ,
        "virus_types": list(selection.virus_types),
        "selection_mode": selection.mode,
        "task_id": task.id,
        "status_url": f"/api/v1/admin/ml/status/{task.id}",
    }


@router.get("/regional/accuracy")
async def get_regional_accuracy(
    virus_typ: str = "Influenza A",
    current_user: dict = Depends(get_current_admin),
):
    """Get per-state accuracy summaries from the pooled regional panel backtest."""
    from app.db.session import get_db_context
    from app.services.ml.regional_trainer import RegionalModelTrainer

    with get_db_context() as db:
        trainer = RegionalModelTrainer(db)
        summaries = trainer.get_regional_accuracy_summary(virus_typ)

    return {
        "virus_typ": virus_typ,
        "models": summaries,
        "total": len(summaries),
    }
