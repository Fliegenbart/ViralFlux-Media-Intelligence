from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.db.session import get_db, get_db_context
from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.trends_service import GoogleTrendsService
from app.services.data_ingest.weather_service import WeatherService
from app.services.data_ingest.holidays_service import SchoolHolidaysService

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_import_all():
    """Background task: alle Datenquellen importieren."""
    logger.info("=== Starting full data import ===")
    results = {}

    with get_db_context() as db:
        # 1. AMELAG Abwasserdaten (Hauptdatenquelle)
        try:
            amelag = AmelagIngestionService(db)
            results["amelag"] = amelag.run_full_import()
        except Exception as e:
            logger.error(f"AMELAG import failed: {e}")
            results["amelag"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 2. Schulferien (statische Daten)
        try:
            holidays = SchoolHolidaysService(db)
            results["holidays"] = holidays.run_full_import()
        except Exception as e:
            logger.error(f"Holidays import failed: {e}")
            results["holidays"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 3. Google Trends (best-effort, kann rate-limited sein)
        try:
            trends = GoogleTrendsService(db)
            results["trends"] = trends.run_full_import(months=3)
        except Exception as e:
            logger.error(f"Google Trends import failed: {e}")
            results["trends"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 4. Wetterdaten (optional, braucht API Key)
        try:
            weather = WeatherService(db)
            results["weather"] = weather.run_full_import(include_forecast=False)
        except Exception as e:
            logger.error(f"Weather import failed: {e}")
            results["weather"] = {"success": False, "error": str(e)}

    logger.info(f"=== Full data import completed: {results} ===")
    return results


@router.post("/run-all")
async def run_full_import(background_tasks: BackgroundTasks):
    """Starte vollständigen Datenimport im Hintergrund."""
    background_tasks.add_task(_run_import_all)
    return {
        "status": "import_started",
        "message": "Datenimport läuft im Hintergrund. Prüfe /health und /api/v1/status für Fortschritt.",
        "timestamp": datetime.utcnow()
    }


@router.post("/amelag")
async def run_amelag_import(db: Session = Depends(get_db)):
    """Importiere nur AMELAG Abwasserdaten."""
    amelag = AmelagIngestionService(db)
    return amelag.run_full_import()


@router.post("/trends")
async def run_trends_import(
    background_tasks: BackgroundTasks,
    months: int = 3,
):
    """Importiere Google Trends Daten (im Hintergrund wegen Rate-Limiting)."""
    def _import():
        with get_db_context() as db:
            trends = GoogleTrendsService(db)
            trends.run_full_import(months=months)
    background_tasks.add_task(_import)
    return {"status": "import_started", "months": months}


@router.post("/weather")
async def run_weather_import(db: Session = Depends(get_db)):
    """Importiere aktuelle Wetterdaten."""
    weather = WeatherService(db)
    return weather.run_full_import(include_forecast=True)


@router.post("/holidays")
async def run_holidays_import(db: Session = Depends(get_db)):
    """Importiere Schulferien-Daten."""
    holidays = SchoolHolidaysService(db)
    return holidays.run_full_import()
