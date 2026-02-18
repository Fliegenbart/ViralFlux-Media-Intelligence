from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
import logging
from datetime import datetime

import threading
from app.core.config import get_settings
from app.db.session import get_db, check_db_connection

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Behördlich getriebene Media-Intelligence für Pharma-Marken mit 14-Tage-Frühsignal"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    
    # Enterprise: DB schema creation is handled exclusively by Alembic migrations.
    # We only verify connectivity here.
    db_healthy = await check_db_connection()
    if not db_healthy:
        raise RuntimeError("Database connection check failed on startup.")
    logger.info("Database connection verified.")

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
    """Cleanup on shutdown."""
    logger.info("Shutting down ViralFlux Media Intelligence...")


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
    """Health check endpoint."""
    db_healthy = await check_db_connection()
    
    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow(),
        "components": {
            "database": "up" if db_healthy else "down",
            "api": "up"
        }
    }


@app.get("/api/v1/status")
async def get_status(db: Session = Depends(get_db)):
    """Get system status and data freshness."""
    from app.models.database import (
        WastewaterAggregated,
        GoogleTrendsData,
        MLForecast,
        NotaufnahmeSyndromData,
        SurvstatWeeklyData,
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
    
    return {
        "status": "operational",
        "data_freshness": {
            "wastewater": latest_wastewater.created_at if latest_wastewater else None,
            "google_trends": latest_trends.created_at if latest_trends else None,
            "ml_forecast": latest_forecast.created_at if latest_forecast else None,
            "notaufnahme": latest_notaufnahme.created_at if latest_notaufnahme else None,
            "survstat": latest_survstat.created_at if latest_survstat else None,
        },
        "timestamp": datetime.utcnow()
    }


# Rate Limiting (slowapi)
from app.api.public_api import limiter
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
    public_api,
    calibration,
    media,
    backtest,
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
app.include_router(public_api.router, prefix="/api/v1/public", tags=["Public API"])
app.include_router(calibration.router, prefix="/api/v1/calibration", tags=["Calibration"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtest"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
