from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from tempfile import TemporaryDirectory
from pathlib import Path
import logging

from app.db.session import get_db, get_db_context
from app.core.config import get_settings
from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.notaufnahme_service import NotaufnahmeIngestionService
from app.services.data_ingest.survstat_service import SurvstatIngestionService
from app.services.data_ingest.trends_service import GoogleTrendsService
from app.services.data_ingest.weather_service import WeatherService
from app.services.data_ingest.holidays_service import SchoolHolidaysService

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


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


@router.post("/survstat-local")
async def run_survstat_local_import(
    folder_path: str | None = None,
    db: Session = Depends(get_db),
):
    """Importiere lokale SURVSTAT-Dateien (manuell, Woche für Woche)."""
    service = SurvstatIngestionService(db)
    target_path = folder_path or settings.SURVSTAT_LOCAL_DIR
    return service.run_local_import(target_path)


@router.post("/survstat-upload")
async def run_survstat_upload_import(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Importiert manuell hochgeladene SURVSTAT Wochen-Dateien (YYYY_WW.csv)."""
    if not files:
        raise HTTPException(status_code=400, detail="Keine Dateien übergeben.")

    service = SurvstatIngestionService(db)
    all_records = []
    errors = []
    parsed_files = 0

    with TemporaryDirectory(prefix="survstat_upload_") as tmp_dir:
        base = Path(tmp_dir)
        for upload in files:
            filename = (upload.filename or "").strip()
            if not filename:
                errors.append({"file": "<unknown>", "error": "Leerer Dateiname"})
                continue

            if not filename.lower().endswith(".csv"):
                errors.append({"file": filename, "error": "Nur .csv Dateien erlaubt"})
                continue

            target = base / filename
            content = await upload.read()
            target.write_bytes(content)

            try:
                records = service.parse_file(target)
                all_records.extend(records)
                parsed_files += 1
            except Exception as exc:
                logger.warning(f"SURVSTAT Upload parse failed for {filename}: {exc}")
                errors.append({"file": filename, "error": str(exc)})

    inserted, updated = service.import_records(all_records)
    latest_week = service._latest_week_label(all_records)

    return {
        "success": inserted + updated > 0 and len(errors) == 0,
        "files_received": len(files),
        "files_parsed": parsed_files,
        "records_total": len(all_records),
        "imported": inserted,
        "updated": updated,
        "latest_week": latest_week,
        "errors": errors,
        "timestamp": datetime.utcnow().isoformat(),
    }


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
