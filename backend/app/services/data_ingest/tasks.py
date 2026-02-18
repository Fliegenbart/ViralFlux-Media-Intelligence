import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict

from app.core.celery_app import celery_app
from app.db.session import get_db_context

from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.notaufnahme_service import NotaufnahmeIngestionService
from app.services.data_ingest.trends_service import GoogleTrendsService
from app.services.data_ingest.weather_service import WeatherService
from app.services.data_ingest.holidays_service import SchoolHolidaysService
from app.services.data_ingest.pollen_service import PollenService

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Best-effort Konvertierung zu JSON-serialisierbaren Typen."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    # numpy/pandas scalars often provide .item()
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


@celery_app.task(bind=True, name="run_full_ingestion_pipeline")
def run_full_ingestion_pipeline(self, region_code: str = "ALL") -> Dict[str, Any]:
    """
    Vollpipeline fuer Daten-Ingestion.
    Laeuft komplett entkoppelt vom Webserver im Hintergrund.
    """
    logger.info(f"Starte asynchrone Daten-Ingestion fuer Region: {region_code}")
    results: dict[str, Any] = {}

    try:
        # 1. AMELAG Abwasserdaten (Hauptdatenquelle)
        self.update_state(
            state="PROGRESS",
            meta={"step": "AMELAG Abwasserdaten abrufen...", "progress": 10},
        )
        with get_db_context() as db:
            amelag = AmelagIngestionService(db)
            results["amelag"] = amelag.run_full_import()

        # 2. GrippeWeb + ARE-Konsultation (syndromische Surveillance)
        self.update_state(
            state="PROGRESS",
            meta={"step": "RKI GrippeWeb + ARE-Konsultation abrufen...", "progress": 30},
        )
        with get_db_context() as db:
            from app.services.data_ingest.grippeweb_service import GrippeWebIngestionService

            grippeweb = GrippeWebIngestionService(db)
            results["grippeweb"] = grippeweb.run_full_import()

        with get_db_context() as db:
            from app.services.data_ingest.are_konsultation_service import (
                AREKonsultationIngestionService,
            )

            are = AREKonsultationIngestionService(db)
            results["are_konsultation"] = are.run_full_import()

        # 3. Notaufnahme + Schulferien + Trends
        self.update_state(
            state="PROGRESS",
            meta={"step": "Notaufnahme, Schulferien & Trends abrufen...", "progress": 50},
        )
        with get_db_context() as db:
            notaufnahme = NotaufnahmeIngestionService(db)
            results["notaufnahme"] = notaufnahme.run_full_import()

        with get_db_context() as db:
            holidays = SchoolHolidaysService(db)
            results["holidays"] = holidays.run_full_import()

        with get_db_context() as db:
            trends = GoogleTrendsService(db)
            results["trends"] = trends.run_full_import(months=3)

        # 4. Wetter + Pollen
        self.update_state(
            state="PROGRESS",
            meta={"step": "Wetter- und Pollen-Daten abrufen...", "progress": 75},
        )
        with get_db_context() as db:
            weather = WeatherService(db)
            results["weather"] = weather.run_full_import(include_forecast=True)

        with get_db_context() as db:
            pollen = PollenService(db)
            results["pollen"] = pollen.run_full_import()

        # 5. BfArM Lieferengpass-Daten (statische CSV, kein API-Key)
        self.update_state(
            state="PROGRESS",
            meta={"step": "BfArM Lieferengpaesse abrufen...", "progress": 95},
        )
        try:
            from app.services.data_ingest.bfarm_service import BfarmIngestionService

            bfarm = BfarmIngestionService()
            results["bfarm"] = bfarm.run_full_import()
        except Exception as exc:
            logger.error(f"BfArM import failed: {exc}")
            results["bfarm"] = {"success": False, "error": str(exc)}

        logger.info("Ingestion erfolgreich abgeschlossen.")
        return _json_safe(
            {
                "status": "success",
                "region": region_code,
                "message": "Alle Datenquellen synchronisiert und berechnet.",
                "results": results,
                "timestamp": datetime.utcnow(),
            }
        )

    except Exception as exc:
        logger.exception(f"Fehler bei Ingestion: {exc}")
        raise RuntimeError(f"Ingestion fehlgeschlagen: {exc}") from exc

