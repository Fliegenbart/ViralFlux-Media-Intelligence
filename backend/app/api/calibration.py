"""Calibration API — Modell-Kalibrierung via Backtesting.

Endpoints für Upload historischer Bestelldaten, Backtesting-Simulation
und Gewichtsoptimierung.
"""

from fastapi import APIRouter, Depends, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO, StringIO
import pandas as pd
import logging

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_VIRUS_TYPES = {"Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"}


def _read_upload(content: bytes, filename: str) -> pd.DataFrame:
    """CSV oder Excel lesen, Spalten normalisieren."""
    if filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
    else:
        text = content.decode("utf-8", errors="replace")
        sep = ";" if ";" in text[:500] else ","
        df = pd.read_csv(StringIO(text), sep=sep)

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


@router.post("/run")
async def run_calibration(
    file: UploadFile = File(...),
    virus_typ: str = Query(default="Influenza A"),
    db: Session = Depends(get_db),
):
    """Kalibierungslauf starten.

    CSV/Excel mit Spalten: datum, menge
    Returns: Metriken, optimierte Gewichte, Chart-Daten, LLM-Insight.
    """
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    content = await file.read()
    df = _read_upload(content, file.filename or "data.csv")

    # Spalten-Validierung
    required = {"datum", "menge"}
    missing = required - set(df.columns)
    if missing:
        return {
            "error": f"Fehlende Spalten: {', '.join(missing)}",
            "found_columns": list(df.columns),
            "expected": ["datum", "menge"],
        }

    # Leere Zeilen entfernen
    df = df.dropna(subset=["datum", "menge"])
    if len(df) < 5:
        return {"error": "Mindestens 5 Datenpunkte erforderlich."}

    from app.services.ml.backtester import BacktestService
    service = BacktestService(db)
    return service.run_calibration(df, virus_typ=virus_typ)


@router.post("/preview")
async def preview_calibration_data(
    file: UploadFile = File(...),
):
    """Vorschau der hochgeladenen Kalibrierungsdaten."""
    content = await file.read()
    df = _read_upload(content, file.filename or "data.csv")

    required = {"datum", "menge"}
    missing = required - set(df.columns)

    return {
        "filename": file.filename,
        "total_rows": len(df),
        "columns": list(df.columns),
        "columns_valid": len(missing) == 0,
        "missing_columns": list(missing),
        "preview": df.head(5).fillna("").to_dict(orient="records"),
    }


@router.get("/template")
async def download_template():
    """Beispiel-CSV für Kalibrierung herunterladen."""
    csv_content = """datum;menge
2025-01-06;120
2025-01-13;135
2025-01-20;180
2025-01-27;210
2025-02-03;195
2025-02-10;160
2025-02-17;140
2025-02-24;130
2025-03-03;125
2025-03-10;110
2025-03-17;95
2025-03-24;85
2025-03-31;80
2025-04-07;70
2025-04-14;65
2025-04-21;60
2025-04-28;55
2025-05-05;50
2025-06-02;40
2025-07-07;35
2025-08-04;30
2025-09-01;45
2025-09-08;65
2025-09-15;90
2025-10-06;130
2025-10-13;155
2025-10-20;175
2025-10-27;200
2025-11-03;230
2025-11-10;260
2025-11-17;280
2025-11-24;310
2025-12-01;340
2025-12-08;365
2025-12-15;380
2025-12-22;350
"""
    return StreamingResponse(
        BytesIO(csv_content.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=labpulse_kalibrierung_vorlage.csv"},
    )


@router.post("/analyze-global")
async def analyze_global_correlations(
    virus_typ: str = Query(default="Influenza A"),
    days_back: int = Query(default=1095, description="Rückblick in Tagen (Default: 3 Jahre)"),
    db: Session = Depends(get_db),
):
    """Globale Kalibrierung: Optimiert System-Gewichte auf Basis historischer Daten.

    Nutzt interne Verkaufsdaten (wenn verfügbar) oder RKI-Abwasserdaten als Fallback.
    Standard-Rückblick: 1095 Tage (3 Jahre) für robuste saisonale Analyse.
    """
    from app.services.ml.backtester import BacktestService
    service = BacktestService(db)
    return service.run_global_calibration(virus_typ=virus_typ, days_back=days_back)
