from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from tempfile import TemporaryDirectory
from pathlib import Path
import logging

from app.db.session import get_db, get_db_context
from app.core.config import get_settings
from app.core.celery_app import celery_app
from app.api.deps import get_current_admin
from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.er_admissions_service import ERAdmissionsIngestionService
from app.services.data_ingest.survstat_service import SurvstatIngestionService
from app.services.data_ingest.trends_service import GoogleTrendsService
from app.services.data_ingest.weather_service import WeatherService
from app.services.data_ingest.holidays_service import SchoolHolidaysService
from app.services.data_ingest.pollen_service import PollenService
from app.services.data_ingest.tasks import run_full_ingestion_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

class IngestRequest(BaseModel):
    region_code: str = "ALL"


def _enqueue_full_ingestion(region_code: str) -> str:
    try:
        task = run_full_ingestion_pipeline.delay(region_code=region_code)
        return task.id
    except Exception as exc:
        logger.error(f"Celery enqueue failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Celery Broker nicht erreichbar. Bitte Redis/Worker starten.",
        ) from exc


@router.post("/run-all", status_code=status.HTTP_202_ACCEPTED)
async def run_full_import(
    request: IngestRequest = Body(default_factory=IngestRequest),
    current_user: dict = Depends(get_current_admin),
):
    """Starte vollständigen Datenimport asynchron (Celery) und gib ein Ticket zurück."""
    task_id = _enqueue_full_ingestion(request.region_code)
    return {
        "message": "Ingestion Pipeline gestartet",
        "task_id": task_id,
        "status_url": f"/api/v1/ingest/status/{task_id}",
    }


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(
    request: IngestRequest = Body(default_factory=IngestRequest),
    current_user: dict = Depends(get_current_admin),
):
    """Alias für /run-all (kompatibel mit Celery Ticketing)."""
    task_id = _enqueue_full_ingestion(request.region_code)
    return {
        "message": "Ingestion Pipeline gestartet",
        "task_id": task_id,
        "status_url": f"/api/v1/ingest/status/{task_id}",
    }


@router.get("/status/{task_id}")
async def get_ingestion_status(task_id: str):
    """Frontend Polling Endpoint für Task Status + Progress Meta."""
    task_result = celery_app.AsyncResult(task_id)

    response: dict = {
        "task_id": task_id,
        "status": task_result.status,  # PENDING, STARTED, PROGRESS, SUCCESS, FAILURE
    }

    if task_result.status == "PROGRESS":
        response["meta"] = task_result.info
    elif task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.info)

    return response


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
    service = ERAdmissionsIngestionService(db)
    return service.run_full_import()


@router.post("/influenza")
async def run_influenza_import(db: Session = Depends(get_db)):
    """Importiere RKI IfSG Influenza-Meldedaten."""
    from app.services.data_ingest.influenza_service import InfluenzaIngestionService
    service = InfluenzaIngestionService(db)
    return service.run_full_import()


@router.post("/rsv")
async def run_rsv_import(db: Session = Depends(get_db)):
    """Importiere RKI IfSG RSV-Meldedaten."""
    from app.services.data_ingest.rsv_service import RSVIngestionService
    service = RSVIngestionService(db)
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


@router.post("/pollen")
async def run_pollen_import(db: Session = Depends(get_db)):
    """Importiere aktuelle DWD-Pollenwerte."""
    service = PollenService(db)
    return service.run_full_import()


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
