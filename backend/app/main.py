from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import logging
from datetime import datetime

from app.core.config import get_settings
from app.db.session import init_db, get_db, check_db_connection

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
    description="Intelligentes Frühwarnsystem für Labordiagnostik mit KI-gestützter Bedarfsprognose"
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
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down VirusRadar Pro...")


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
    from app.models.database import WastewaterAggregated, GoogleTrendsData, MLForecast
    
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
    
    return {
        "status": "operational",
        "data_freshness": {
            "wastewater": latest_wastewater.created_at if latest_wastewater else None,
            "google_trends": latest_trends.created_at if latest_trends else None,
            "ml_forecast": latest_forecast.created_at if latest_forecast else None
        },
        "timestamp": datetime.utcnow()
    }


# Import API routes
from app.api import dashboard
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
