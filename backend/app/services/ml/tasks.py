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


@celery_app.task(bind=True, name="compute_forecast_accuracy_task")
def compute_forecast_accuracy_task(self) -> Dict[str, Any]:
    """Tägliches Monitoring: vergangene Forecasts mit tatsächlichen Abwasserdaten vergleichen.

    Für jeden Virustyp werden MLForecast-Einträge, deren forecast_date
    in der Vergangenheit liegt, mit WastewaterAggregated-Werten gejoint.
    MAE, RMSE, MAPE und Korrelation werden in ForecastAccuracyLog persistiert.
    Bei MAPE > 35% wird drift_detected=True gesetzt.
    """
    import numpy as np

    logger.info("Celery: Forecast accuracy check started")
    self.update_state(state="PROGRESS", meta={"step": "Computing accuracy...", "progress": 10})

    results = {}
    virus_types = ["Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"]

    with get_db_context() as db:
        from app.models.database import MLForecast, WastewaterAggregated, ForecastAccuracyLog
        from datetime import timedelta

        for virus in virus_types:
            # Forecasts der letzten 14 Tage, die jetzt in der Vergangenheit liegen
            cutoff = datetime.utcnow()
            window_start = cutoff - timedelta(days=14)
            forecasts = (
                db.query(MLForecast)
                .filter(
                    MLForecast.virus_typ == virus,
                    MLForecast.forecast_date < cutoff,
                    MLForecast.forecast_date >= window_start,
                )
                .order_by(MLForecast.forecast_date.asc())
                .all()
            )

            if not forecasts:
                results[virus] = {"samples": 0, "message": "Keine vergangenen Forecasts"}
                continue

            predicted = []
            actual = []
            pairs = []

            for fc in forecasts:
                # Nächsten WastewaterAggregated-Wert finden (+-1 Tag Toleranz)
                ww = (
                    db.query(WastewaterAggregated)
                    .filter(
                        WastewaterAggregated.virus_typ == virus,
                        WastewaterAggregated.datum >= fc.forecast_date - timedelta(days=1),
                        WastewaterAggregated.datum <= fc.forecast_date + timedelta(days=1),
                    )
                    .order_by(WastewaterAggregated.datum.asc())
                    .first()
                )
                if ww and ww.viruslast_normalisiert is not None:
                    predicted.append(fc.predicted_value)
                    actual.append(ww.viruslast_normalisiert)
                    pairs.append({
                        "date": fc.forecast_date.isoformat(),
                        "predicted": round(fc.predicted_value, 2),
                        "actual": round(ww.viruslast_normalisiert, 2),
                    })

            n = len(predicted)
            if n < 3:
                results[virus] = {"samples": n, "message": "Zu wenige Paare"}
                continue

            pred_arr = np.array(predicted)
            act_arr = np.array(actual)
            errors = pred_arr - act_arr

            mae = float(np.mean(np.abs(errors)))
            rmse = float(np.sqrt(np.mean(errors ** 2)))
            # MAPE mit Schutz gegen Division durch 0
            nonzero = act_arr != 0
            mape = float(np.mean(np.abs(errors[nonzero] / act_arr[nonzero])) * 100) if nonzero.any() else 0.0
            corr = float(np.corrcoef(pred_arr, act_arr)[0, 1]) if n >= 3 else 0.0

            drift = mape > 35.0

            log_entry = ForecastAccuracyLog(
                virus_typ=virus,
                window_days=14,
                samples=n,
                mae=round(mae, 3),
                rmse=round(rmse, 3),
                mape=round(mape, 1),
                correlation=round(corr, 4),
                drift_detected=drift,
                details={"pairs": pairs[:14]},
            )
            db.add(log_entry)

            results[virus] = {
                "samples": n,
                "mae": round(mae, 3),
                "rmse": round(rmse, 3),
                "mape": round(mape, 1),
                "correlation": round(corr, 4),
                "drift_detected": drift,
            }

            # Trend-Analyse: letzte 3 Logs vergleichen
            recent_logs = (
                db.query(ForecastAccuracyLog)
                .filter(ForecastAccuracyLog.virus_typ == virus)
                .order_by(ForecastAccuracyLog.computed_at.desc())
                .limit(3)
                .all()
            )
            if len(recent_logs) >= 2:
                mapes = [l.mape for l in recent_logs if l.mape is not None]
                if len(mapes) >= 2 and all(m > 35 for m in mapes[:2]):
                    results[virus]["consecutive_drift"] = True
                    logger.warning(
                        "PERSISTENT DRIFT for %s: MAPE>35%% for %d consecutive windows",
                        virus, len([m for m in mapes if m > 35]),
                    )

            if drift:
                logger.warning("DRIFT DETECTED for %s: MAPE=%.1f%% > 35%% threshold", virus, mape)

        db.commit()

    logger.info(f"Celery: Forecast accuracy check completed: {results}")
    return _json_safe({
        "status": "success",
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    })
