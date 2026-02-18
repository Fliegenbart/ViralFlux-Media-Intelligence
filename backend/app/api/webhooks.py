import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.celery_app import celery_app
from app.services.data_ingest.tasks import process_erp_sales_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["System Integrations"])


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """Simple API-key guard for machine-to-machine integrations (ERP/IMS).

    We intentionally do NOT use JWT here: these calls are not from browsers/users.
    """
    expected = os.getenv("M2M_SECRET_KEY", "GELO_ERP_SYNC_2026")
    if not expected:
        logger.error("M2M_SECRET_KEY is empty; refusing all webhook requests.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="M2M auth is not configured.",
        )

    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


class ERPSalesPayload(BaseModel):
    """Normalized ERP/IMS sales payload (strict)."""

    # We forbid unknown fields but still allow ISO-8601 strings for `timestamp`.
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=128)
    region_code: str = Field(min_length=1, max_length=32)
    units_sold: int = Field(gt=0, le=50_000_000)
    revenue: float = Field(ge=0, le=50_000_000_000)
    timestamp: datetime


@router.post("/erp/sales-sync", status_code=status.HTTP_202_ACCEPTED)
async def erp_sales_sync(
    payload: ERPSalesPayload,
    _: None = Depends(verify_api_key),
):
    """Accept ERP/IMS sales data and process asynchronously via Celery."""
    try:
        task = process_erp_sales_sync.delay(payload.model_dump(mode="json"))
    except Exception as exc:
        logger.error(f"Celery enqueue failed for ERP sales sync: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Celery Broker nicht erreichbar. Bitte Redis/Worker starten.",
        ) from exc

    return {
        "message": "ERP sales sync accepted",
        "task_id": task.id,
        "status_url": f"/api/webhooks/status/{task.id}",
    }


@router.get("/status/{task_id}")
async def get_webhook_task_status(
    task_id: str,
    _: None = Depends(verify_api_key),
):
    """Polling endpoint for ERP/IMS callers (PENDING/PROGRESS/SUCCESS/FAILURE)."""
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
        response["error"] = str(task_result.info)

    return response
