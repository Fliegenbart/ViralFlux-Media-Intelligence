from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.db.session import get_db, get_db_context
from app.services.ml.forecast_service import ForecastService

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_forecasts():
    """Background task: run stacking forecasts (HW+Ridge+Prophet→XGBoost) for all virus types."""
    logger.info("=== Starting ML forecast run ===")
    with get_db_context() as db:
        service = ForecastService(db)
        results = service.run_forecasts_for_all_viruses()
    logger.info(f"=== Forecast run completed: {list(results.keys())} ===")
    return results


@router.post("/run")
async def run_forecasts(background_tasks: BackgroundTasks):
    """Run ML stacking forecasts for all virus types (background)."""
    background_tasks.add_task(_run_forecasts)
    return {
        "status": "forecast_started",
        "message": "XGBoost stacking forecasts running in background for all virus types.",
        "timestamp": datetime.utcnow()
    }


@router.post("/run-sync")
async def run_forecasts_sync(db: Session = Depends(get_db)):
    """Run ML stacking forecasts synchronously (may take 30-60s)."""
    service = ForecastService(db)
    results = {}
    for virus in ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']:
        try:
            forecast = service.predict(virus_typ=virus)
            if 'error' not in forecast:
                service.save_forecast(forecast)
                results[virus] = {
                    "success": True,
                    "forecast_days": len(forecast.get('forecast', [])),
                    "training_samples": forecast.get('training_samples', 0)
                }
            else:
                results[virus] = {"success": False, "error": forecast['error']}
        except Exception as e:
            logger.error(f"Forecast failed for {virus}: {e}")
            results[virus] = {"success": False, "error": str(e)}

    return {
        "results": results,
        "timestamp": datetime.utcnow()
    }


@router.get("/latest/{virus_typ}")
async def get_latest_forecast(
    virus_typ: str,
    db: Session = Depends(get_db)
):
    """Get the latest forecast for a specific virus type."""
    from app.models.database import MLForecast

    forecasts = db.query(MLForecast).filter(
        MLForecast.virus_typ == virus_typ,
        MLForecast.forecast_date >= datetime.now()
    ).order_by(MLForecast.forecast_date.asc()).limit(14).all()

    if not forecasts:
        return {"virus_typ": virus_typ, "forecast": [], "message": "No forecast available"}

    return {
        "virus_typ": virus_typ,
        "forecast": [
            {
                "date": f.forecast_date.isoformat(),
                "predicted_value": round(f.predicted_value, 1),
                "lower_bound": round(f.lower_bound, 1) if f.lower_bound else None,
                "upper_bound": round(f.upper_bound, 1) if f.upper_bound else None,
                "confidence": f.confidence,
                "model_version": f.model_version,
                "trend_momentum_7d": round(f.trend_momentum_7d, 4) if f.trend_momentum_7d is not None else None,
                "outbreak_risk_score": round(f.outbreak_risk_score, 3) if f.outbreak_risk_score is not None else None,
            }
            for f in forecasts
        ],
        "created_at": forecasts[0].created_at.isoformat() if forecasts else None,
        "model_version": forecasts[0].model_version if forecasts else None
    }


@router.get("/status")
async def get_forecast_status(db: Session = Depends(get_db)):
    """Get the status of all forecasts."""
    from app.models.database import MLForecast
    from sqlalchemy import func

    status = {}
    for virus in ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']:
        latest = db.query(MLForecast).filter(
            MLForecast.virus_typ == virus
        ).order_by(MLForecast.created_at.desc()).first()

        future_count = db.query(func.count(MLForecast.id)).filter(
            MLForecast.virus_typ == virus,
            MLForecast.forecast_date >= datetime.now()
        ).scalar()

        status[virus] = {
            "has_forecast": latest is not None,
            "last_run": latest.created_at.isoformat() if latest else None,
            "future_days": future_count or 0,
            "model_version": latest.model_version if latest else None
        }

    return {"forecasts": status, "timestamp": datetime.utcnow()}


@router.get("/accuracy/{virus_typ}")
async def get_forecast_accuracy(virus_typ: str, limit: int = 14, db: Session = Depends(get_db)):
    """Rolling forecast accuracy metrics for a virus type.

    Returns the latest accuracy log entries showing MAE, RMSE, MAPE,
    correlation, and drift detection status.
    """
    from app.models.database import ForecastAccuracyLog

    logs = (
        db.query(ForecastAccuracyLog)
        .filter(ForecastAccuracyLog.virus_typ == virus_typ)
        .order_by(ForecastAccuracyLog.computed_at.desc())
        .limit(limit)
        .all()
    )

    if not logs:
        return {
            "virus_typ": virus_typ,
            "accuracy": [],
            "drift_active": False,
            "message": "Noch keine Accuracy-Daten vorhanden. Täglicher Check läuft um 08:00.",
        }

    latest = logs[0]
    return {
        "virus_typ": virus_typ,
        "drift_active": latest.drift_detected,
        "latest": {
            "computed_at": latest.computed_at.isoformat(),
            "samples": latest.samples,
            "mae": latest.mae,
            "rmse": latest.rmse,
            "mape": latest.mape,
            "correlation": latest.correlation,
            "drift_detected": latest.drift_detected,
        },
        "history": [
            {
                "computed_at": log.computed_at.isoformat(),
                "samples": log.samples,
                "mae": log.mae,
                "rmse": log.rmse,
                "mape": log.mape,
                "correlation": log.correlation,
                "drift_detected": log.drift_detected,
            }
            for log in logs
        ],
    }


@router.get("/accuracy")
async def get_all_forecast_accuracy(db: Session = Depends(get_db)):
    """Accuracy overview for all virus types (latest entry each)."""
    from app.models.database import ForecastAccuracyLog
    from sqlalchemy import func

    result = {}
    for virus in ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']:
        latest = (
            db.query(ForecastAccuracyLog)
            .filter(ForecastAccuracyLog.virus_typ == virus)
            .order_by(ForecastAccuracyLog.computed_at.desc())
            .first()
        )
        if latest:
            result[virus] = {
                "computed_at": latest.computed_at.isoformat(),
                "samples": latest.samples,
                "mae": latest.mae,
                "rmse": latest.rmse,
                "mape": latest.mape,
                "correlation": latest.correlation,
                "drift_detected": latest.drift_detected,
            }
        else:
            result[virus] = None

    any_drift = any(v and v.get("drift_detected") for v in result.values())
    return {
        "accuracy": result,
        "any_drift": any_drift,
        "timestamp": datetime.utcnow(),
    }
