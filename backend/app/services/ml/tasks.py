"""Celery tasks for ML model training.

Provides background tasks for training and serialising XGBoost
meta-learner models. Follows the same patterns as
``app.services.data_ingest.tasks``.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict

from app.core.celery_app import celery_app
from app.db.session import get_db_context

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Best-effort conversion to JSON-serialisable types."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


@celery_app.task(bind=True, name="train_xgboost_model_task")
def train_xgboost_model_task(
    self,
    virus_typ: str | None = None,
) -> Dict[str, Any]:
    """Train and serialise XGBoost meta-learner models.

    Args:
        virus_typ: Single virus type to train (e.g. ``"Influenza A"``).
            If *None*, trains all four supported virus types.

    Returns:
        JSON-safe dict with training results per virus type.
    """
    from app.services.ml.model_trainer import XGBoostTrainer

    logger.info(f"Celery: XGBoost training started (virus_typ={virus_typ})")

    self.update_state(
        state="PROGRESS",
        meta={"step": "Initializing XGBoost trainer...", "progress": 10},
    )

    with get_db_context() as db:
        trainer = XGBoostTrainer(db)

        if virus_typ:
            self.update_state(
                state="PROGRESS",
                meta={"step": f"Training {virus_typ}...", "progress": 30},
            )
            result = trainer.train(virus_typ=virus_typ)
        else:
            self.update_state(
                state="PROGRESS",
                meta={"step": "Training all virus types...", "progress": 30},
            )
            result = trainer.train_all()

    logger.info("Celery: XGBoost training completed")
    return _json_safe({
        "status": "success",
        "result": result,
        "timestamp": datetime.utcnow().isoformat(),
    })
