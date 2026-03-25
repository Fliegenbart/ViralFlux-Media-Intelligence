from app.core.time import utc_now
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.db.schema_contracts import MLForecastSchemaMismatchError
from app.db.session import get_db, get_db_context
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_horizon_utils import ensure_supported_horizon
from app.services.ml.forecast_service import ForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)
router = APIRouter()


def _validated_regional_horizon(
    horizon_days: int = Query(7, description="Explizit unterstützte regionale Forecast-Horizonte in Tagen."),
) -> int:
    try:
        return ensure_supported_horizon(horizon_days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        "timestamp": utc_now()
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
        "timestamp": utc_now()
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
    for virus in SUPPORTED_VIRUS_TYPES:
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

    return {"forecasts": status, "timestamp": utc_now()}


@router.get("/monitoring/{virus_typ}")
async def get_forecast_monitoring(
    virus_typ: str,
    target_source: str = "RKI_ARE",
    db: Session = Depends(get_db),
):
    """Forecast monitoring snapshot with readiness, drift and calibration gates."""
    try:
        return ForecastDecisionService(db).build_monitoring_snapshot(
            virus_typ=virus_typ,
            target_source=target_source,
        )
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/monitoring")
async def get_all_forecast_monitoring(
    target_source: str = "RKI_ARE",
    db: Session = Depends(get_db),
):
    """Monitoring overview for all supported virus types."""
    service = ForecastDecisionService(db)
    try:
        monitoring = {
            virus: service.build_monitoring_snapshot(
                virus_typ=virus,
                target_source=target_source,
            )
            for virus in SUPPORTED_VIRUS_TYPES
        }
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    any_warning = any(
        snapshot.get("monitoring_status") in {"warning", "critical"}
        for snapshot in monitoring.values()
    )
    return {
        "monitoring": monitoring,
        "any_warning": any_warning,
        "timestamp": utc_now(),
    }


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

    result = {}
    for virus in SUPPORTED_VIRUS_TYPES:
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
        "timestamp": utc_now(),
    }


@router.get("/regional/status")
async def get_regional_feature_status(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Diagnostic endpoint: check which Bundesländer have sufficient data for regional forecasting."""
    from app.services.ml.regional_features import RegionalFeatureBuilder, BUNDESLAND_NAMES

    builder = RegionalFeatureBuilder(db)
    panel = builder.build_panel_training_data(virus_typ=virus_typ, lookback_days=900)
    available = builder.get_available_bundeslaender(virus_typ)

    details = {}
    for bl_code in sorted(available):
        df = panel.loc[panel["bundesland"] == bl_code].copy() if not panel.empty else panel
        details[bl_code] = {
            "name": BUNDESLAND_NAMES.get(bl_code, bl_code),
            "rows": len(df),
            "sufficient": len(df) >= 30,
            "features": list(df.columns) if not df.empty else [],
            "date_range": {
                "start": str(df["as_of_date"].min()) if not df.empty else None,
                "end": str(df["as_of_date"].max()) if not df.empty else None,
            },
        }

    sufficient_count = sum(1 for d in details.values() if d["sufficient"])

    return {
        "virus_typ": virus_typ,
        "total_bundeslaender": 16,
        "with_wastewater_data": len(available),
        "sufficient_for_training": sufficient_count,
        "details": details,
        "timestamp": utc_now(),
    }


@router.get("/regional")
async def get_regional_predictions_alias(
    virus_typ: str = "Influenza A",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Alias for pooled regional predictions including operational decision signals."""
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)


@router.get("/regional/predict")
async def get_regional_predictions(
    virus_typ: str = "Influenza A",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Get pooled per-state outbreak predictions with decision output per region.

    Core question:
    "Which regions are most likely to enter a relevant wave at the requested 3/5/7-day horizon?"

    The response now includes, per region:
    - decision_label: Watch / Prepare / Activate
    - priority_score
    - reason_trace
    - uncertainty_summary
    """
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)


@router.get("/regional/decisions")
async def get_regional_decisions(
    virus_typ: str = "Influenza A",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Decision-focused alias for regional forecasts.

    Returns the same regional forecast payload as ``/regional/predict``, but is
    intended for dashboard consumers that primarily render Watch/Prepare/Activate
    outputs and their audit trail.
    """
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)


@router.get("/regional/media-activation")
async def get_media_activation(
    virus_typ: str = "Influenza A",
    weekly_budget_eur: float = 50000,
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Generate gated regional media recommendations for GELO products.

    Returns per-Bundesland recommendations with:
    - Action: activate / prepare / watch
    - Heuristic regional budget allocation and priority ranks
    - Channel mix (Banner, CLP, Meta, LinkedIn)
    - Product recommendation
    - Activation timeline plus quality-gate context
    - Reason trace, confidence and spend readiness
    """
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.generate_media_allocation(
        virus_typ=virus_typ,
        weekly_budget_eur=weekly_budget_eur,
        horizon_days=horizon_days,
    )


@router.get("/regional/media-allocation")
async def get_media_allocation(
    virus_typ: str = "Influenza A",
    weekly_budget_eur: float = 50000,
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Decision-driven media allocation alias for dashboard consumers.

    Returns the same payload as ``/regional/media-activation``, but is named
    explicitly for budget share and prioritization use cases.
    """
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.generate_media_allocation(
        virus_typ=virus_typ,
        weekly_budget_eur=weekly_budget_eur,
        horizon_days=horizon_days,
    )


@router.get("/regional/campaign-recommendations")
async def get_campaign_recommendations(
    virus_typ: str = "Influenza A",
    weekly_budget_eur: float = 50000,
    horizon_days: int = Depends(_validated_regional_horizon),
    top_n: int = 12,
    db: Session = Depends(get_db),
):
    """Turn allocation into discussion-ready campaign recommendations for PEIX / GELO.

    Returns per region:
    - recommended product cluster
    - recommended keyword cluster
    - activation level and budget suggestion
    - recommendation rationale and evidence class
    - guardrail status for immediate discussion
    """
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.generate_campaign_recommendations(
        virus_typ=virus_typ,
        weekly_budget_eur=weekly_budget_eur,
        horizon_days=horizon_days,
        top_n=top_n,
    )


@router.get("/regional/benchmark")
async def get_regional_benchmark(
    reference_virus: str = "Influenza A",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Compare supported regional virus models against a shared benchmark virus."""
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.benchmark_supported_viruses(
        reference_virus=reference_virus,
        horizon_days=horizon_days,
    )


@router.get("/regional/portfolio")
async def get_regional_portfolio(
    horizon_days: int = Depends(_validated_regional_horizon),
    top_n: int = 12,
    reference_virus: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Prioritize regional opportunities across all supported virus lines."""
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.build_portfolio_view(
        horizon_days=horizon_days,
        top_n=top_n,
        reference_virus=reference_virus,
    )


@router.get("/regional/validation")
async def get_regional_business_validation(
    virus_typ: str = "Influenza A",
    brand: str = "gelo",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Expose the commercial GELO truth status separately from forecast quality.

    Returns:
    - Business gate / evidence tier
    - Operator context (PEIX) and truth partner (brand)
    - Holdout / activation-cycle readiness
    - Model lineage fragments relevant for due diligence
    """
    from app.services.ml.regional_forecast import RegionalForecastService

    service = RegionalForecastService(db)
    return service.get_validation_summary(
        virus_typ=virus_typ,
        brand=brand,
        horizon_days=horizon_days,
    )


@router.get("/regional/backtest")
async def run_regional_backtest(
    virus_typ: str = "Influenza A",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Run leakage-safe walk-forward backtest for the pooled regional panel model.

    Returns calibration and activation metrics such as:
    - precision@top3 / precision@top5
    - PR-AUC
    - Brier score
    - ECE
    - median lead days
    - activation false-positive rate
    """
    from app.services.ml.regional_backtest import RegionalBacktester

    backtester = RegionalBacktester(db)
    return backtester.backtest_all_regions(
        virus_typ=virus_typ,
        horizon_days=horizon_days,
    )


@router.get("/regional/backtest/{bundesland}")
async def run_region_backtest(
    bundesland: str,
    virus_typ: str = "Influenza A",
    horizon_days: int = Depends(_validated_regional_horizon),
    db: Session = Depends(get_db),
):
    """Run backtest for a single Bundesland with detailed timeline."""
    from app.services.ml.regional_backtest import RegionalBacktester

    backtester = RegionalBacktester(db)
    return backtester.backtest_region(
        virus_typ=virus_typ,
        bundesland=bundesland.upper(),
        horizon_days=horizon_days,
    )
