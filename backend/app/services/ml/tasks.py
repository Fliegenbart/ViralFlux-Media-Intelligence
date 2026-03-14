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
from app.services.ml.training_contract import (
    SUPPORTED_VIRUS_TYPES,
    normalize_training_selection,
)

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


def _select_forecast_accuracy_actual(row: Any) -> float | None:
    """Return the actual series value on the same scale as MLForecast.

    The forecasting model is trained on raw ``viruslast`` values, not on
    ``viruslast_normalisiert``. If the raw value is missing we skip the pair
    instead of silently comparing different scales.
    """
    raw_value = getattr(row, "viruslast", None)
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    return value if value == value else None


def _compute_accuracy_metrics(predicted: list[float], actual: list[float]) -> dict[str, float]:
    """Compute accuracy metrics for a list of like-for-like forecast pairs."""
    import numpy as np

    pred_arr = np.asarray(predicted, dtype=float)
    act_arr = np.asarray(actual, dtype=float)
    errors = pred_arr - act_arr

    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    nonzero = act_arr != 0
    mape = float(np.mean(np.abs(errors[nonzero] / act_arr[nonzero])) * 100) if nonzero.any() else 0.0
    if len(pred_arr) >= 3 and float(np.std(pred_arr)) > 0.0 and float(np.std(act_arr)) > 0.0:
        corr = float(np.corrcoef(pred_arr, act_arr)[0, 1])
    else:
        corr = 0.0

    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "correlation": corr,
    }


@celery_app.task(bind=True, name="train_xgboost_model_task")
def train_xgboost_model_task(
    self,
    virus_typ: str | None = None,
    virus_types: list[str] | None = None,
    include_internal_history: bool = True,
    research_mode: bool = False,
) -> Dict[str, Any]:
    """Train and serialise XGBoost meta-learner models.

    Args:
        virus_typ: Single virus type to train (e.g. ``"Influenza A"``).
        virus_types: Optional explicit list of virus types.
        include_internal_history: Whether to include Ganzimmun history features.
        research_mode: Whether to evaluate the fixed candidate set before promotion.

    Returns:
        JSON-safe dict with training results per virus type.
    """
    from app.services.ml.model_trainer import XGBoostTrainer
    selection = normalize_training_selection(
        virus_typ=virus_typ,
        virus_types=virus_types,
    )

    logger.info(
        "Celery: XGBoost training started (virus_types=%s, mode=%s, internal=%s, research=%s)",
        list(selection.virus_types),
        selection.mode,
        include_internal_history,
        research_mode,
    )

    self.update_state(
        state="PROGRESS",
        meta={"step": "Initializing XGBoost trainer...", "progress": 10},
    )

    with get_db_context() as db:
        trainer = XGBoostTrainer(db)

        if len(selection.virus_types) == 1:
            target_virus = selection.virus_typ or selection.virus_types[0]
            self.update_state(
                state="PROGRESS",
                meta={"step": f"Training {target_virus}...", "progress": 30},
            )
            result = trainer.train(
                virus_typ=target_virus,
                include_internal_history=include_internal_history,
                research_mode=research_mode,
            )
        else:
            self.update_state(
                state="PROGRESS",
                meta={
                    "step": (
                        "Training all virus types..."
                        if selection.mode == "all"
                        else "Training selected virus types..."
                    ),
                    "progress": 30,
                },
            )
            result = trainer.train_all(
                virus_types=list(selection.virus_types),
                include_internal_history=include_internal_history,
                research_mode=research_mode,
            )

    logger.info("Celery: XGBoost training completed")
    return _json_safe({
        "status": "success",
        "result": result,
        "virus_typ": selection.virus_typ,
        "virus_types": list(selection.virus_types),
        "selection_mode": selection.mode,
        "include_internal_history": include_internal_history,
        "research_mode": research_mode,
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
    logger.info("Celery: Forecast accuracy check started")
    self.update_state(state="PROGRESS", meta={"step": "Computing accuracy...", "progress": 10})

    results = {}
    virus_types = list(SUPPORTED_VIRUS_TYPES)

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
                actual_value = _select_forecast_accuracy_actual(ww) if ww else None
                if actual_value is not None:
                    predicted.append(fc.predicted_value)
                    actual.append(actual_value)
                    pairs.append({
                        "date": fc.forecast_date.isoformat(),
                        "predicted": round(fc.predicted_value, 2),
                        "actual": round(actual_value, 2),
                    })

            n = len(predicted)
            if n < 3:
                results[virus] = {"samples": n, "message": "Zu wenige Paare"}
                continue

            metrics = _compute_accuracy_metrics(predicted, actual)
            mae = metrics["mae"]
            rmse = metrics["rmse"]
            mape = metrics["mape"]
            corr = metrics["correlation"]

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
                "target_scale": "viruslast",
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
                mapes = [entry.mape for entry in recent_logs if entry.mape is not None]
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


@celery_app.task(bind=True, name="train_regional_models_task")
def train_regional_models_task(
    self,
    virus_typ: str = "Influenza A",
) -> Dict[str, Any]:
    """Train per-Bundesland XGBoost regional forecast models.

    Trains one model per Bundesland that has sufficient AMELAG wastewater data.
    Each model uses regional features (wastewater, SurvStat, weather, pollen, holidays).
    """
    from app.services.ml.regional_trainer import RegionalModelTrainer

    logger.info("Celery: Starting regional model training for %s", virus_typ)

    self.update_state(
        state="PROGRESS",
        meta={"step": f"Training regional models for {virus_typ}...", "progress": 10},
    )

    with get_db_context() as db:
        trainer = RegionalModelTrainer(db)
        result = trainer.train_all_regions(virus_typ=virus_typ)

    trained = result.get("trained", 0)
    failed = result.get("failed", 0)
    logger.info(
        "Celery: Regional training complete for %s — %d trained, %d failed",
        virus_typ, trained, failed,
    )

    return _json_safe({
        "status": "success",
        "virus_typ": virus_typ,
        "trained": trained,
        "failed": failed,
        "timestamp": datetime.utcnow().isoformat(),
    })
