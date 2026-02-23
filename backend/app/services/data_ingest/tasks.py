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
        source_system = str(payload.get("source_system") or "").strip().lower() or "unknown"
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
            "source_system": source_system,
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
            f"system={source_system} units_sold={units_sold} revenue={revenue} ts={ts.isoformat()} "
            f"(inserted={inserted}, updated={updated})"
        )
        return _json_safe(
            {
                "status": "success",
                "inserted": inserted,
                "updated": updated,
                "source_system": source_system,
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


@celery_app.task(bind=True, name="backfill_wastewater_coordinates")
def backfill_wastewater_coordinates(self) -> Dict[str, Any]:
    """Einmaliger Task: Bestehende wastewater_data Rows mit Koordinaten befüllen.

    Liest alle Rows ohne latitude und setzt die Koordinaten aus dem
    statischen Kläranlagen-Mapping.
    """
    from app.models.database import WastewaterData
    from app.services.data_ingest.klaeranlage_coordinates import get_coordinates

    logger.info("Wastewater coordinates backfill: Starte...")

    with get_db_context() as db:
        rows = (
            db.query(WastewaterData)
            .filter(WastewaterData.latitude.is_(None))
            .all()
        )

        updated = 0
        unmapped: set[str] = set()
        for row in rows:
            coords = get_coordinates(row.standort)
            if coords:
                row.latitude = coords[0]
                row.longitude = coords[1]
                updated += 1
            else:
                unmapped.add(row.standort)

        if updated:
            db.commit()

    if unmapped:
        logger.warning("Wastewater backfill: %s unmapped Standorte: %s", len(unmapped), unmapped)

    logger.info("Wastewater backfill: %s rows updated, %s unmapped Standorte", updated, len(unmapped))
    return _json_safe({
        "status": "success",
        "rows_updated": updated,
        "total_without_coords": len(rows),
        "unmapped_standorte": sorted(unmapped),
    })


@celery_app.task(bind=True, name="import_survstat_web_exports")
def import_survstat_web_exports(
    self,
    folder_path: str = "/app/data/raw/survstat/peix_exports",
    year: int = 2025,
) -> Dict[str, Any]:
    """Import der drei SurvStat Web-Export-Formate (Meldewoche, Bundesland, Landkreis).

    Erwartet Unterordner: nach_meldewoche/, nach_bundesland/, nach_landkreis/
    """
    from app.services.data_ingest.survstat_export_importer import import_survstat_exports

    logger.info("SurvStat Web-Export Import: Starte aus %s (year=%d)", folder_path, year)

    with get_db_context() as db:
        result = import_survstat_exports(db, folder_path, year=year)

    logger.info(
        "SurvStat Web-Export: %s inserted, %s updated",
        result.get("total_inserted", 0),
        result.get("total_updated", 0),
    )
    return _json_safe(result)


@celery_app.task(bind=True, name="backfill_survstat_from_folder")
def backfill_survstat_from_folder(
    self,
    folder_path: str = "/app/data/raw/survstat/backfill",
) -> Dict[str, Any]:
    """Batch-Import historischer SURVSTAT-CSVs mit OTC-Filtering.

    Verarbeitet einen Ordner mit vorab heruntergeladenen RKI SurvStat
    CSV-Dateien (z.B. 2019_01.csv bis 2026_08.csv). Filtert auf
    OTC-relevante Krankheiten und weist Cluster zu.

    Kein API-Call — nur lokale Dateien. Rate-Limiting nicht nötig.
    """
    from app.services.data_ingest.survstat_service import SurvstatIngestionService

    logger.info(f"SURVSTAT backfill: Starte aus {folder_path}")

    with get_db_context() as db:
        service = SurvstatIngestionService(db)
        result = service.run_local_import(folder_path)

    logger.info(
        "SURVSTAT backfill: %s records, %s imported, %s updated",
        result.get("records_total", 0),
        result.get("imported", 0),
        result.get("updated", 0),
    )
    return _json_safe(result)


@celery_app.task(bind=True, name="backfill_survstat_clusters")
def backfill_survstat_clusters(self) -> Dict[str, Any]:
    """Einmaliger Task: Bestehende SurvStat-Daten mit OTC-Clustern taggen.

    Liest alle Rows ohne disease_cluster und weist ihnen den passenden
    Cluster zu. Rows, die nicht in der OTC-Whitelist sind, bleiben
    mit disease_cluster=NULL (können optional gelöscht werden).
    """
    from app.services.data_ingest.survstat_service import SurvstatIngestionService

    logger.info("SURVSTAT cluster backfill: Starte...")

    with get_db_context() as db:
        service = SurvstatIngestionService(db)
        updated = service.backfill_clusters()

    logger.info("SURVSTAT cluster backfill: %s rows updated", updated)
    return _json_safe({"status": "success", "rows_clustered": updated})


@celery_app.task(bind=True, name="fetch_survstat_kreis_api")
def fetch_survstat_kreis_api(
    self,
    years: list | None = None,
    diseases: list | None = None,
) -> Dict[str, Any]:
    """RKI SurvStat OLAP-API: Landkreis-Level Fallzahlen abrufen.

    Micro-Cubing mit Rate-Limiting (1.5s pro Request).
    Laufzeit ca. 1-2 Min. pro Krankheit/Jahr.
    """
    from app.services.data_ingest.survstat_api_service import SurvstatApiService

    logger.info(
        "SurvStat Kreis-API Pipeline gestartet (years=%s, diseases=%s)",
        years,
        "all" if diseases is None else len(diseases),
    )

    def _progress(state, meta):
        self.update_state(state=state, meta=meta)

    with get_db_context() as db:
        service = SurvstatApiService(db)
        result = service.run(
            years=years,
            diseases=diseases,
            progress_callback=_progress,
        )

    if not result.get("success"):
        raise RuntimeError(f"SurvStat Kreis-API fehlgeschlagen: {result}")

    logger.info(
        "SurvStat Kreis-API: %s Datenpunkte in %ss",
        result.get("total_records", 0),
        result.get("elapsed_seconds", "?"),
    )
    return _json_safe(result)
