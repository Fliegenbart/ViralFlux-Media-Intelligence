"""Datenimport API — Upload historischer Bestell- und Labordaten.

Unterstützt CSV und Excel (.xlsx) mit Auto-Detection von Encoding und Separator.
Uploads werden in UploadHistory persistiert und fließen über BaselineAnalyzer
bzw. OrderSignalAnalyzer in den Confidence Score der Fusion Engine ein.
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import pandas as pd
from io import StringIO, BytesIO
import logging
from datetime import datetime

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.database import UploadHistory

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TABULAR_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Mapping: article_id keywords → virus type for auto-calibration
_ARTICLE_TO_VIRUS = {
    "influenza": "Influenza A",
    "sars": "SARS-CoV-2",
    "covid": "SARS-CoV-2",
    "rsv": "RSV A",
}


def _infer_virus_type(df: pd.DataFrame) -> str:
    """Infer dominant virus type from article_id column."""
    if "article_id" not in df.columns:
        return "Influenza A"
    article_counts = df.groupby("article_id")["quantity"].sum()
    for aid in article_counts.sort_values(ascending=False).index:
        lower = str(aid).lower()
        for keyword, virus in _ARTICLE_TO_VIRUS.items():
            if keyword in lower:
                return virus
    return "Influenza A"


def _read_file_to_df(content: bytes, filename: str) -> pd.DataFrame:
    """Read CSV or Excel file content into a DataFrame.

    Auto-detects file format by extension, encoding (UTF-8/Latin-1),
    and CSV separator (; vs ,). Normalizes column names.
    """
    if filename.lower().endswith(".xlsx"):
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
    else:
        # CSV: auto-detect encoding and separator
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        sep = ";" if ";" in text[:500] else ","
        df = pd.read_csv(StringIO(text), sep=sep)

    # Normalize column names: lowercase, strip whitespace, spaces→underscores
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df


def _looks_like_csv(content: bytes) -> bool:
    if not content or b"\x00" in content[:2048]:
        return False
    try:
        content[:4096].decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            content[:4096].decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


def _validate_tabular_upload(file: UploadFile, content: bytes) -> None:
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx")):
        raise HTTPException(400, "Nur CSV oder Excel (.xlsx) Dateien erlaubt")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Datei zu groß (max. 10 MB)")

    content_type = (file.content_type or "").lower().strip()
    if content_type and content_type not in ALLOWED_TABULAR_CONTENT_TYPES:
        raise HTTPException(400, "Dateityp nicht erlaubt")

    if filename.endswith(".xlsx"):
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(400, "Ungültige Excel-Datei")
        return

    if not _looks_like_csv(content):
        raise HTTPException(400, "Ungültige CSV-Datei")


def _record_upload(
    db: Session,
    filename: str,
    upload_type: str,
    df: pd.DataFrame,
    result: dict,
    date_column: str,
    status: str = "success",
    error_message: str = None,
) -> dict:
    """Record upload in UploadHistory table and return summary."""
    file_format = "xlsx" if filename.lower().endswith(".xlsx") else "csv"

    date_range_start = None
    date_range_end = None
    if date_column in df.columns:
        dates = pd.to_datetime(df[date_column], errors="coerce").dropna()
        if not dates.empty:
            date_range_start = dates.min().to_pydatetime()
            date_range_end = dates.max().to_pydatetime()

    entry = UploadHistory(
        filename=filename,
        upload_type=upload_type,
        file_format=file_format,
        row_count=len(df),
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        status=status,
        error_message=error_message,
        summary=result,
    )
    db.add(entry)
    db.commit()

    return {
        "upload_id": entry.id,
        "filename": filename,
        "file_format": file_format,
        "row_count": len(df),
        "date_range": {
            "start": date_range_start.isoformat() if date_range_start else None,
            "end": date_range_end.isoformat() if date_range_end else None,
        },
    }


@router.post("/upload/lab-results", dependencies=[Depends(get_current_admin)])
async def upload_lab_results(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload anonymisierte Laborergebnisse (CSV oder Excel).

    Spalten: datum, test_type, total_tests, positive_tests [, region]
    """
    from app.services.fusion_engine.baseline_analyzer import BaselineAnalyzer

    content = await file.read()
    _validate_tabular_upload(file, content)

    try:
        df = _read_file_to_df(content, file.filename)
    except Exception as e:
        logger.warning("Lab results upload could not be parsed: %s", e)
        raise HTTPException(400, "Datei konnte nicht gelesen werden.")

    required = {"datum", "test_type", "total_tests", "positive_tests"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Fehlende Spalten: {', '.join(missing)}")

    try:
        analyzer = BaselineAnalyzer(db)
        result = analyzer.ingest_internal_history(df)

        summary = _record_upload(
            db, file.filename, "lab_results", df, result, "datum"
        )

        return {"success": True, **summary, "import_result": result}
    except Exception as e:
        logger.error(f"Lab results import failed: {e}")
        _record_upload(
            db, file.filename, "lab_results", df, {},
            "datum", status="error", error_message=str(e),
        )
        raise HTTPException(500, "Import fehlgeschlagen.")


@router.post("/upload/orders", dependencies=[Depends(get_current_admin)])
async def upload_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload historische Bestelldaten (CSV oder Excel).

    Spalten: order_date, article_id, quantity [, customer_id]
    """
    from app.services.fusion_engine.order_signal_analyzer import OrderSignalAnalyzer

    content = await file.read()
    _validate_tabular_upload(file, content)

    try:
        df = _read_file_to_df(content, file.filename)
    except Exception as e:
        logger.warning("Orders upload could not be parsed: %s", e)
        raise HTTPException(400, "Datei konnte nicht gelesen werden.")

    required = {"order_date", "article_id", "quantity"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Fehlende Spalten: {', '.join(missing)}")

    try:
        analyzer = OrderSignalAnalyzer(db)
        result = analyzer.ingest_orders(df)

        summary = _record_upload(
            db, file.filename, "orders", df, result, "order_date"
        )

        # Auto-Kalibrierung: Bestelldaten aggregieren → BacktestService
        calibration_result = None
        try:
            cal_df = (
                df.groupby("order_date")["quantity"]
                .sum()
                .reset_index()
            )
            cal_df.columns = ["datum", "menge"]
            cal_df = cal_df.dropna(subset=["datum", "menge"])

            if len(cal_df) >= 8:
                from app.services.ml.backtester import BacktestService

                virus_typ = _infer_virus_type(df)
                backtest = BacktestService(db)
                calibration_result = backtest.run_calibration(
                    cal_df,
                    virus_typ=virus_typ,
                    horizon_days=7,
                    min_train_points=20,
                    strict_vintage_mode=True,
                )
                logger.info(
                    f"Auto-Kalibrierung: R²={calibration_result.get('metrics', {}).get('r2_score', '?')}, "
                    f"Virus={virus_typ}, Punkte={len(cal_df)}"
                )
            else:
                logger.info(
                    f"Auto-Kalibrierung übersprungen: nur {len(cal_df)} Datenpunkte (min. 8)"
                )
        except Exception as e:
            logger.warning(f"Auto-Kalibrierung fehlgeschlagen (nicht kritisch): {e}")
            calibration_result = {"error": str(e)}

        return {
            "success": True,
            **summary,
            "import_result": result,
            "calibration": calibration_result,
        }
    except Exception as e:
        logger.error(f"Orders import failed: {e}")
        _record_upload(
            db, file.filename, "orders", df, {},
            "order_date", status="error", error_message=str(e),
        )
        raise HTTPException(500, "Import fehlgeschlagen.")


@router.post("/preview", dependencies=[Depends(get_current_admin)])
async def preview_file(
    file: UploadFile = File(...),
    upload_type: str = Query(..., pattern="^(lab_results|orders)$"),
):
    """Vorschau: erste 5 Zeilen + Spaltenvalidierung (ohne Import)."""
    content = await file.read()
    _validate_tabular_upload(file, content)

    try:
        df = _read_file_to_df(content, file.filename)
    except Exception as e:
        logger.warning("Upload preview could not be parsed: %s", e)
        raise HTTPException(400, "Datei konnte nicht gelesen werden.")

    if upload_type == "lab_results":
        required = {"datum", "test_type", "total_tests", "positive_tests"}
        optional = {"region"}
    else:
        required = {"order_date", "article_id", "quantity"}
        optional = {"customer_id"}

    found_cols = set(df.columns)
    missing = required - found_cols
    extra = found_cols - required - optional

    preview_rows = df.head(5).fillna("").astype(str).to_dict(orient="records")

    return {
        "filename": file.filename,
        "total_rows": len(df),
        "columns": list(df.columns),
        "columns_valid": len(missing) == 0,
        "missing_columns": list(missing),
        "extra_columns": list(extra),
        "preview": preview_rows,
    }


@router.get("/history")
async def get_upload_history(
    upload_type: str = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Upload-Verlauf abrufen."""
    query = db.query(UploadHistory).order_by(desc(UploadHistory.created_at))

    if upload_type:
        query = query.filter(UploadHistory.upload_type == upload_type)

    uploads = query.limit(limit).all()

    return [
        {
            "id": u.id,
            "filename": u.filename,
            "upload_type": u.upload_type,
            "file_format": u.file_format,
            "row_count": u.row_count,
            "date_range_start": u.date_range_start.isoformat() if u.date_range_start else None,
            "date_range_end": u.date_range_end.isoformat() if u.date_range_end else None,
            "status": u.status,
            "error_message": u.error_message,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in uploads
    ]


@router.get("/template/{upload_type}")
async def download_template(upload_type: str):
    """Beispiel-CSV-Vorlage herunterladen."""
    if upload_type == "lab_results":
        csv_content = "datum;test_type;total_tests;positive_tests;region\n"
        csv_content += "2024-01-15;Influenza A;1250;187;Hessen\n"
        csv_content += "2024-01-15;SARS-CoV-2;980;45;Hessen\n"
        csv_content += "2024-01-22;Influenza A;1340;210;Hessen\n"
        csv_content += "2024-01-22;RSV;560;89;Hessen\n"
        filename = "labpulse_laborergebnisse_vorlage.csv"
    elif upload_type == "orders":
        csv_content = "order_date;article_id;quantity;customer_id\n"
        csv_content += "2024-01-15;Influenza A/B Schnelltest;25;K00123\n"
        csv_content += "2024-01-16;SARS-CoV-2 PCR;50;K00456\n"
        csv_content += "2024-01-17;RSV Schnelltest;15;K00789\n"
        csv_content += "2024-01-18;CRP Schnelltest;30;K00123\n"
        filename = "labpulse_bestelldaten_vorlage.csv"
    else:
        raise HTTPException(400, "upload_type muss 'lab_results' oder 'orders' sein")

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── RKI SurvStat Landkreis-API ─────────────────────────────────────


@router.post("/survstat-export", dependencies=[Depends(get_current_admin)])
async def import_survstat_exports(
    folder: str = Query(..., description="Pfad zum Ordner mit SurvStat-Exports"),
    year: int = Query(2025, description="Datenjahr (Standard: 2025)"),
    db: Session = Depends(get_db),
):
    """RKI SurvStat Web-Export importieren (3 Formate).

    Erwartet Unterordner: nach_meldewoche/, nach_bundesland/, nach_landkreis/
    mit jeweils einer UTF-16 TSV Data*.csv Datei.
    """
    from app.services.data_ingest.survstat_export_importer import (
        import_survstat_exports as _do_import,
    )

    try:
        result = _do_import(db, folder, year=year)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("SurvStat export import failed: %s", exc)
        raise HTTPException(500, "Import fehlgeschlagen.")

    return result


@router.post("/survstat-api", dependencies=[Depends(get_current_admin)])
async def trigger_survstat_api_fetch(
    years: list[int] | None = None,
    diseases: list[str] | None = None,
):
    """RKI SurvStat OLAP-API Abruf triggern (Landkreis-Ebene).

    Micro-Cubing mit Rate-Limiting. Laufzeit: ~1-2 Min. pro Krankheit/Jahr.
    Async via Celery — gibt sofort task_id zurück.

    - ``years``: Liste der Jahre (Default: Vorjahr + aktuelles Jahr)
    - ``diseases``: Krankheits-Filter (Default: alle 22 OTC-Krankheiten)
    """
    from app.services.data_ingest.tasks import fetch_survstat_kreis_api

    try:
        task = fetch_survstat_kreis_api.delay(years=years, diseases=diseases)
    except Exception as exc:
        logger.error(f"Celery-Enqueue fehlgeschlagen: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Celery Broker nicht erreichbar. Bitte Redis/Worker prüfen.",
        )

    return {
        "task_id": task.id,
        "status": "started",
        "years": years or "default (current-1, current)",
        "diseases": diseases or "all OTC (22)",
        "status_url": f"/api/v1/admin/ml/status/{task.id}",
    }


@router.post("/survstat-api/discover-kreise", dependencies=[Depends(get_current_admin)])
async def discover_kreise(db: Session = Depends(get_db)):
    """Landkreis-Namen aus RKI-Hierarchie entdecken und in kreis_einwohner seeden."""
    from app.services.data_ingest.survstat_api_service import SurvstatApiService

    service = SurvstatApiService(db)
    result = service.discover_and_seed_kreise()

    return {
        "success": True,
        "new_kreise_discovered": result["new_seeded"],
        "details": result,
        "message": (
            f"{result['new_seeded']} neue Kreise geseedet. "
            "Einwohner-Daten müssen separat gepflegt werden."
        ),
    }


@router.post("/survstat-api/sync-kreis-einwohner", dependencies=[Depends(get_current_admin)])
async def sync_kreis_einwohner(
    source_url: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Kreis-Einwohner aus dem offiziellen Destatis-Gemeindeverzeichnis synchronisieren."""
    from app.services.data_ingest.survstat_api_service import SurvstatApiService

    service = SurvstatApiService(db)
    result = service.sync_kreis_einwohner_from_destatis(source_url=source_url)

    return {
        "success": True,
        **result,
    }
