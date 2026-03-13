import asyncio
import logging
import time
import threading
from datetime import datetime

from fastapi import FastAPI, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import (
    setup_logging,
    correlation_id,
    generate_correlation_id,
)
from app.core.metrics import (
    app_info,
    http_requests_total,
    http_request_duration_seconds,
)
from app.db.session import get_db, check_db_connection, init_db

# Setup structured logging BEFORE anything else
settings = get_settings()
setup_logging(
    level=settings.LOG_LEVEL,
    json_format=settings.LOG_FORMAT == "json",
)
logger = logging.getLogger(__name__)

# FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Behördlich getriebene Media-Intelligence für Pharma-Marken mit 14-Tage-Frühsignal"
)

# Publish app info to Prometheus
app_info.info({
    "version": settings.APP_VERSION,
    "environment": settings.ENVIRONMENT,
})

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware: Correlation ID + Prometheus Metrics ──────────────
@app.middleware("http")
async def observability_middleware(request: Request, call_next) -> Response:
    cid = request.headers.get("X-Correlation-ID") or generate_correlation_id()
    token = correlation_id.set(cid)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start
        endpoint = request.url.path
        http_requests_total.labels(request.method, endpoint, "500").inc()
        http_request_duration_seconds.labels(request.method, endpoint).observe(duration)
        raise
    finally:
        correlation_id.reset(token)

    duration = time.perf_counter() - start
    endpoint = request.url.path
    http_requests_total.labels(request.method, endpoint, str(response.status_code)).inc()
    http_request_duration_seconds.labels(request.method, endpoint).observe(duration)

    response.headers["X-Correlation-ID"] = cid
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    logger.info("Environment: %s", settings.ENVIRONMENT)
    
    # Runtime safety-net: initialize schema when database is empty / fresh
    # (migrations are still managed separately).
    db_healthy = await check_db_connection()
    if not db_healthy:
        raise RuntimeError("Database connection check failed on startup.")
    logger.info("Database connection verified.")
    try:
        init_db()
        logger.info("Database schema check/initialization completed.")
    except Exception as e:
        logger.warning("Database schema initialization skipped: %s", e)

    # BfArM Lieferengpass-Daten im Hintergrund laden (non-blocking)
    def _bfarm_startup():
        try:
            from app.services.data_ingest.bfarm_service import BfarmIngestionService
            service = BfarmIngestionService()
            result = service.run_full_import()
            logger.info(
                f"BfArM Startup-Pull: {result.get('relevant_records', 0)} Meldungen, "
                f"Score {result.get('risk_score', 0)}"
            )
        except Exception as e:
            logger.warning(f"BfArM Startup-Pull fehlgeschlagen (nicht kritisch): {e}")

    threading.Thread(target=_bfarm_startup, daemon=True).start()


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown: allow in-flight requests to complete."""
    logger.info("Shutting down ViralFlux Media Intelligence...")
    await asyncio.sleep(2)
    logger.info("Shutdown complete.")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint with forecast monitoring summary."""
    db_healthy = await check_db_connection()

    drift_info: dict = {}
    monitoring_info: dict = {}
    if db_healthy:
        try:
            from app.services.ml.forecast_decision_service import ForecastDecisionService
            from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
            from app.db.session import get_db_context
            with get_db_context() as db:
                service = ForecastDecisionService(db)
                for virus_typ in SUPPORTED_VIRUS_TYPES:
                    snapshot = service.build_monitoring_snapshot(
                        virus_typ=virus_typ,
                        target_source="RKI_ARE",
                    )
                    latest_accuracy = snapshot.get("latest_accuracy") or {}
                    drift_info[virus_typ] = {
                        "mape": latest_accuracy.get("mape"),
                        "drift": snapshot.get("drift_status") == "warning",
                    }
                    monitoring_info[virus_typ] = {
                        "monitoring_status": snapshot.get("monitoring_status"),
                        "forecast_readiness": snapshot.get("forecast_readiness"),
                        "drift_status": snapshot.get("drift_status"),
                        "freshness_status": snapshot.get("freshness_status"),
                        "accuracy_freshness_status": snapshot.get("accuracy_freshness_status"),
                        "backtest_freshness_status": snapshot.get("backtest_freshness_status"),
                        "mape": latest_accuracy.get("mape"),
                        "samples": latest_accuracy.get("samples"),
                    }
        except Exception:
            pass

    any_drift = any(v.get("drift") for v in drift_info.values())
    any_monitoring_warning = any(
        value.get("monitoring_status") in {"warning", "critical"}
        for value in monitoring_info.values()
    )

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow(),
        "components": {
            "database": "up" if db_healthy else "down",
            "api": "up",
            "ml_drift": "warning" if any_drift else "ok",
            "forecast_monitoring": (
                "warning"
                if any_monitoring_warning
                else ("ok" if monitoring_info else "unknown")
            ),
        },
        "ml_accuracy": drift_info or None,
        "forecast_monitoring": monitoring_info or None,
    }


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/api/v1/status")
async def get_status(db: Session = Depends(get_db)):
    """Get system status and data freshness."""
    from app.models.database import (
        WastewaterAggregated,
        GoogleTrendsData,
        MLForecast,
        NotaufnahmeSyndromData,
        SurvstatWeeklyData,
        SurvstatKreisData,
    )

    # Check latest data timestamps
    latest_wastewater = db.query(WastewaterAggregated).order_by(
        WastewaterAggregated.created_at.desc()
    ).first()

    latest_trends = db.query(GoogleTrendsData).order_by(
        GoogleTrendsData.created_at.desc()
    ).first()

    latest_forecast = db.query(MLForecast).order_by(
        MLForecast.created_at.desc()
    ).first()

    latest_notaufnahme = db.query(NotaufnahmeSyndromData).order_by(
        NotaufnahmeSyndromData.created_at.desc()
    ).first()

    latest_survstat = db.query(SurvstatWeeklyData).order_by(
        SurvstatWeeklyData.created_at.desc()
    ).first()

    latest_survstat_kreis = db.query(SurvstatKreisData).order_by(
        SurvstatKreisData.created_at.desc()
    ).first()

    return {
        "status": "operational",
        "data_freshness": {
            "wastewater": latest_wastewater.created_at if latest_wastewater else None,
            "google_trends": latest_trends.created_at if latest_trends else None,
            "ml_forecast": latest_forecast.created_at if latest_forecast else None,
            "notaufnahme": latest_notaufnahme.created_at if latest_notaufnahme else None,
            "survstat": latest_survstat.created_at if latest_survstat else None,
            "survstat_kreis": latest_survstat_kreis.created_at if latest_survstat_kreis else None,
        },
        "timestamp": datetime.utcnow()
    }


# Rate Limiting (slowapi) — shared limiter from core module
from app.core.rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Import API routes
from app.api import (
    auth,
    dashboard,
    ingest,
    forecast,
    recommendations,
    inventory,
    map_data,
    ordering,
    drug_shortage,
    outbreak_score,
    marketing,
    data_import,
    webhooks,
    public_api,
    calibration,
    media,
    backtest,
    admin_ml,
)
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(ingest.router, prefix="/api/v1/ingest", tags=["Data Ingestion"])
app.include_router(forecast.router, prefix="/api/v1/forecast", tags=["ML Forecast"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["Inventory"])
app.include_router(map_data.router, prefix="/api/v1/map", tags=["Map Data"])
app.include_router(ordering.router, prefix="/api/v1/ordering", tags=["Ordering"])
app.include_router(drug_shortage.router, prefix="/api/v1/drug-shortage", tags=["Drug Shortage"])
app.include_router(outbreak_score.router, prefix="/api/v1/outbreak-score", tags=["Outbreak Score"])
app.include_router(marketing.router, prefix="/api/v1/marketing", tags=["Marketing"])
app.include_router(media.router, prefix="/api/v1/media", tags=["Media"])
app.include_router(data_import.router, prefix="/api/v1/data-import", tags=["Data Import"])
app.include_router(webhooks.router)
app.include_router(public_api.router, prefix="/api/v1/public", tags=["Public API"])
app.include_router(calibration.router, prefix="/api/v1/calibration", tags=["Calibration"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtest"])
app.include_router(admin_ml.router, prefix="/api/v1/admin/ml", tags=["Admin ML"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
