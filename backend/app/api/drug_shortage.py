"""API-Endpunkte für BfArM Lieferengpass-Analyse."""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import pandas as pd
import tempfile
import os
import logging
import threading

from app.api.deps import get_current_admin, get_current_user
from app.services.data_ingest.drug_shortage_service import DrugShortageAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])
ALLOWED_CSV_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
}

# Singleton-Instanz für gecachte Analyse
_analyzer: DrugShortageAnalyzer | None = None
_auto_refresh_lock = threading.Lock()
_auto_refresh_attempted = False


def _ensure_analyzer() -> DrugShortageAnalyzer | None:
    """Lazy-load BfArM data if no analyzer is cached (multi-worker safety)."""
    global _analyzer, _auto_refresh_attempted
    if _analyzer is not None and _analyzer.df_filtered is not None:
        return _analyzer
    if _auto_refresh_attempted:
        return _analyzer
    with _auto_refresh_lock:
        if _analyzer is not None and _analyzer.df_filtered is not None:
            return _analyzer
        if _auto_refresh_attempted:
            return _analyzer
        _auto_refresh_attempted = True
        try:
            from app.services.data_ingest.bfarm_service import BfarmIngestionService
            logger.info("Auto-Refresh: BfArM-Daten werden nachgeladen (Worker hatte keine Daten)")
            service = BfarmIngestionService()
            service.run_full_import()
            logger.info("Auto-Refresh: BfArM-Daten erfolgreich geladen")
        except Exception as e:
            logger.warning(f"Auto-Refresh fehlgeschlagen: {e}")
    return _analyzer


def _validate_csv_upload(file: UploadFile, content: bytes) -> None:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Nur CSV-Dateien erlaubt")

    content_type = (file.content_type or "").lower().strip()
    if content_type and content_type not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Dateityp nicht erlaubt")

    if not content or b"\x00" in content[:2048]:
        raise HTTPException(status_code=400, detail="Ungültige CSV-Datei")


@router.post("/upload", dependencies=[Depends(get_current_admin)])
async def upload_shortage_csv(file: UploadFile = File(...)):
    """Upload und Analyse einer BfArM LEMeldungen CSV-Datei.

    Akzeptiert eine CSV-Datei (Semikolon-getrennt, Latin-1), filtert nach
    aktuell relevanten Engpässen und berechnet Infektionswellen-Signale.
    """
    global _analyzer

    # Temporäre Datei schreiben
    try:
        content = await file.read()
        _validate_csv_upload(file, content)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        analyzer = DrugShortageAnalyzer()
        df = analyzer.load_and_clean(tmp_path)

        _analyzer = analyzer

        signals = analyzer.get_infection_signals()
        summary = analyzer.get_summary_text()

        return {
            "status": "success",
            "filename": file.filename,
            "rows_loaded": len(df),
            "signals": signals,
            "summary": summary,
        }

    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Engpass-CSV: {e}")
        raise HTTPException(status_code=500, detail="Datei konnte nicht verarbeitet werden.")
    finally:
        if 'tmp_path' in locals():
            os.unlink(tmp_path)


@router.get("/signals")
async def get_infection_signals():
    """Gibt die zuletzt berechneten Infektionswellen-Signale zurück."""
    analyzer = _ensure_analyzer()
    if analyzer is None or analyzer.df_filtered is None:
        raise HTTPException(
            status_code=404,
            detail="Keine Daten geladen. Bitte zuerst POST /upload mit CSV-Datei aufrufen."
        )

    return {
        "signals": analyzer.get_infection_signals(),
        "summary": analyzer.get_summary_text(),
    }


@router.get("/weekly-trend")
async def get_weekly_trend():
    """Gibt die wöchentliche Engpass-Aggregation zurück."""
    analyzer = _ensure_analyzer()
    if analyzer is None or analyzer.df_filtered is None:
        raise HTTPException(
            status_code=404,
            detail="Keine Daten geladen. Bitte zuerst POST /upload mit CSV-Datei aufrufen."
        )

    return {
        "trend": analyzer.get_weekly_trend(),
    }


@router.get("/details")
async def get_shortage_details(
    category: str | None = None,
    signal_type: str | None = None,
    pediatric_only: bool = False,
):
    """Gibt detaillierte Engpass-Meldungen zurück, optional gefiltert."""
    analyzer = _ensure_analyzer()
    if analyzer is None or analyzer.df_filtered is None:
        raise HTTPException(
            status_code=404,
            detail="Keine Daten geladen. Bitte zuerst POST /upload mit CSV-Datei aufrufen."
        )

    df = analyzer.df_filtered.copy()

    if category:
        df = df[df['category'] == category]
    if signal_type:
        df = df[df['signal_type'] == signal_type]
    if pediatric_only:
        df = df[df['is_pediatric']]

    # Dedupliziere nach Bearbeitungsnummer für saubere Ausgabe
    if 'Bearbeitungsnummer' in df.columns:
        df_dedup = df.drop_duplicates(subset=['Bearbeitungsnummer'])
    else:
        df_dedup = df.drop_duplicates(subset=['Arzneimittlbezeichnung'])

    records = []
    for _, row in df_dedup.iterrows():
        records.append({
            'arzneimittel': row.get('Arzneimittlbezeichnung', ''),
            'wirkstoffe': row.get('Wirkstoffe', ''),
            'grund': row.get('Grund', ''),
            'beginn': row['Beginn'].isoformat() if pd.notna(row.get('Beginn')) else None,
            'ende': row['Ende'].isoformat() if pd.notna(row.get('Ende')) else None,
            'darreichungsform': row.get('Darreichungsform', ''),
            'category': row.get('category', ''),
            'signal_type': row.get('signal_type', ''),
            'is_pediatric': bool(row.get('is_pediatric', False)),
            'zulassungsinhaber': row.get('Zulassungsinhaber', ''),
            'krankenhausrelevant': row.get('Krankenhausrelevant', ''),
        })

    return {
        'total': len(records),
        'filter': {
            'category': category,
            'signal_type': signal_type,
            'pediatric_only': pediatric_only,
        },
        'shortages': records,
    }
