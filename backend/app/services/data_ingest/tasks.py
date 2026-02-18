import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict

from app.core.celery_app import celery_app
from app.db.session import get_db_context

from app.services.data_ingest.amelag_service import AmelagIngestionService
from app.services.data_ingest.er_admissions_service import ERAdmissionsIngestionService
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
            er_admissions = ERAdmissionsIngestionService(db)
            results["er_admissions"] = er_admissions.run_full_import()

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


@celery_app.task(bind=True, name="process_erp_sales_sync")
def process_erp_sales_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist ERP/IMS sales payload asynchronously.

    We store normalized sales signals in GanzimmunData because downstream
    analyzers/backtests already understand this table as "internal" signals.
    """
    try:
        product_id = str(payload.get("product_id", "")).strip()
        region_code = str(payload.get("region_code", "")).strip()
        units_sold = int(payload.get("units_sold"))
        revenue = float(payload.get("revenue"))

        ts_raw = payload.get("timestamp")
        if not ts_raw:
            raise ValueError("timestamp is required")
        if isinstance(ts_raw, str):
            # Accept both "+00:00" and "Z" forms.
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        else:
            ts = datetime.fromisoformat(str(ts_raw))

        if not product_id:
            raise ValueError("product_id is required")
        if not region_code:
            raise ValueError("region_code is required")

        from app.models.database import AuditLog, GanzimmunData

        inserted = 0
        updated = 0

        extra_data = {
            "source": "erp_sales_sync",
            "units_sold": units_sold,
            "revenue": revenue,
            "region_code": region_code,
            "received_at": datetime.utcnow().isoformat(),
        }

        with get_db_context() as db:
            # Idempotency best-effort: treat (timestamp, product_id, region_code) as unique.
            existing = (
                db.query(GanzimmunData)
                .filter(
                    GanzimmunData.datum == ts,
                    GanzimmunData.test_typ == product_id,
                    GanzimmunData.region == region_code,
                    GanzimmunData.extra_data.isnot(None),
                )
                .first()
            )

            if existing:
                existing.available_time = ts
                existing.anzahl_tests = units_sold
                existing.positive_ergebnisse = None
                existing.extra_data = extra_data
                updated = 1
            else:
                db.add(
                    GanzimmunData(
                        datum=ts,
                        available_time=ts,
                        test_typ=product_id,
                        anzahl_tests=units_sold,
                        positive_ergebnisse=None,
                        region=region_code,
                        extra_data=extra_data,
                    )
                )
                inserted = 1

            # Annex 11/22-ish audit trail for automated integrations.
            db.add(
                AuditLog(
                    user="m2m",
                    action="erp_sales_sync",
                    entity_type="ganzimmun_data",
                    entity_id=None,
                    old_value=None,
                    new_value=payload,
                    reason="ERP/IMS webhook",
                    ip_address=None,
                )
            )

        logger.info(
            f"ERP sales sync persisted: product_id={product_id} region={region_code} "
            f"units_sold={units_sold} revenue={revenue} ts={ts.isoformat()} "
            f"(inserted={inserted}, updated={updated})"
        )
        return _json_safe(
            {
                "status": "success",
                "inserted": inserted,
                "updated": updated,
                "product_id": product_id,
                "region_code": region_code,
                "units_sold": units_sold,
                "revenue": revenue,
                "timestamp": ts,
            }
        )
    except Exception as exc:
        logger.exception(f"ERP sales sync processing failed: {exc}")
        raise RuntimeError(f"ERP sales sync failed: {exc}") from exc
