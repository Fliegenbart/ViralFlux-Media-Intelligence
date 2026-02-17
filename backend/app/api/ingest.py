from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.db.session import get_db, get_db_context
from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.notaufnahme_service import NotaufnahmeIngestionService
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
        # 2. GrippeWeb ARE/ILI Daten
        try:
            from app.services.data_ingest.grippeweb_service import GrippeWebIngestionService
            grippeweb = GrippeWebIngestionService(db)
            results["grippeweb"] = grippeweb.run_full_import()
        except Exception as e:
            logger.error(f"GrippeWeb import failed: {e}")
            results["grippeweb"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 2b. ARE-Konsultationsinzidenz (syndromische Surveillance)
        try:
            from app.services.data_ingest.are_konsultation_service import AREKonsultationIngestionService
            are = AREKonsultationIngestionService(db)
            results["are_konsultation"] = are.run_full_import()
        except Exception as e:
            logger.error(f"ARE-Konsultation import failed: {e}")
            results["are_konsultation"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 3. Notaufnahmesurveillance (AKTIN/RKI)
        try:
            notaufnahme = NotaufnahmeIngestionService(db)
            results["notaufnahme"] = notaufnahme.run_full_import()
        except Exception as e:
            logger.error(f"Notaufnahme import failed: {e}")
            results["notaufnahme"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 4. Schulferien (ferien-api.de, alle 16 Bundesländer)
        try:
            holidays = SchoolHolidaysService(db)
            results["holidays"] = holidays.run_full_import()
        except Exception as e:
            logger.error(f"Holidays import failed: {e}")
            results["holidays"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 5. Google Trends (best-effort, kann rate-limited sein)
        try:
            trends = GoogleTrendsService(db)
            results["trends"] = trends.run_full_import(months=3)
        except Exception as e:
            logger.error(f"Google Trends import failed: {e}")
            results["trends"] = {"success": False, "error": str(e)}

    with get_db_context() as db:
        # 6. Wetterdaten (BrightSky / DWD, kein API Key nötig)
        try:
            weather = WeatherService(db)
            results["weather"] = weather.run_full_import(include_forecast=True)
        except Exception as e:
            logger.error(f"Weather import failed: {e}")
            results["weather"] = {"success": False, "error": str(e)}

    # 7. BfArM Lieferengpass-Daten (statische CSV, kein API-Key)
    try:
        from app.services.data_ingest.bfarm_service import BfarmIngestionService
        bfarm = BfarmIngestionService()
        results["bfarm"] = bfarm.run_full_import()
    except Exception as e:
        logger.error(f"BfArM import failed: {e}")
        results["bfarm"] = {"success": False, "error": str(e)}

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


@router.post("/grippeweb")
async def run_grippeweb_import(db: Session = Depends(get_db)):
    """Importiere GrippeWeb ARE/ILI Surveillance-Daten."""
    from app.services.data_ingest.grippeweb_service import GrippeWebIngestionService
    service = GrippeWebIngestionService(db)
    return service.run_full_import()


@router.post("/are-konsultation")
async def run_are_konsultation_import(db: Session = Depends(get_db)):
    """Importiere RKI ARE-Konsultationsinzidenz Daten."""
    from app.services.data_ingest.are_konsultation_service import AREKonsultationIngestionService
    service = AREKonsultationIngestionService(db)
    return service.run_full_import()


@router.post("/notaufnahme")
async def run_notaufnahme_import(db: Session = Depends(get_db)):
    """Importiere RKI/AKTIN Notaufnahmesurveillance Daten."""
    service = NotaufnahmeIngestionService(db)
    return service.run_full_import()


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
    """Importiere aktuelle Wetterdaten (BrightSky / DWD)."""
    weather = WeatherService(db)
    return weather.run_full_import(include_forecast=True)


@router.post("/weather/backfill")
async def run_weather_backfill(
    background_tasks: BackgroundTasks,
    start: str = "2024-01-01",
    end: str = None,
):
    """Historische Wetterdaten nachladen (BrightSky / DWD).

    Default: 2024-01-01 bis heute. Läuft im Hintergrund (~5 Min für 2 Jahre).
    """
    from datetime import datetime as dt

    start_date = dt.fromisoformat(start)
    end_date = dt.fromisoformat(end) if end else dt.now()

    def _backfill():
        with get_db_context() as db:
            weather = WeatherService(db)
            weather.backfill_history(start_date, end_date)

    background_tasks.add_task(_backfill)
    return {
        "status": "backfill_started",
        "date_range": f"{start_date.date()} bis {end_date.date()}",
        "message": "Historische DWD-Wetterdaten werden im Hintergrund geladen.",
    }


@router.post("/holidays")
async def run_holidays_import(db: Session = Depends(get_db)):
    """Importiere Schulferien-Daten."""
    holidays = SchoolHolidaysService(db)
    return holidays.run_full_import()


@router.post("/bfarm")
async def run_bfarm_import():
    """Importiere aktuelle BfArM Lieferengpass-Daten (statische CSV)."""
    from app.services.data_ingest.bfarm_service import BfarmIngestionService
    service = BfarmIngestionService()
    return service.run_full_import()
