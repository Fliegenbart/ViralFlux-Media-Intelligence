"""Calibration API — Modell-Kalibrierung via Backtesting.

Endpoints für Upload historischer Bestelldaten, Backtesting-Simulation
und Gewichtsoptimierung.
"""

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO, StringIO
import pandas as pd
import logging

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])
ALLOWED_TABULAR_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

VALID_VIRUS_TYPES = {"Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"}
VALID_MARKET_TARGETS = {
    "RKI_ARE",
    "SURVSTAT",
    "MYCOPLASMA",
    "KEUCHHUSTEN",
    "PNEUMOKOKKEN",
    "H_INFLUENZAE",
}


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


def _validate_upload(file: UploadFile, content: bytes) -> None:
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="Nur CSV oder Excel (.xlsx) Dateien erlaubt")

    content_type = (file.content_type or "").lower().strip()
    if content_type and content_type not in ALLOWED_TABULAR_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Dateityp nicht erlaubt")

    if filename.endswith(".xlsx"):
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(status_code=400, detail="Ungültige Excel-Datei")
        return

    if not content or b"\x00" in content[:2048]:
        raise HTTPException(status_code=400, detail="Ungültige CSV-Datei")


@router.post("/run", dependencies=[Depends(get_current_admin)])
async def run_calibration(
    file: UploadFile = File(...),
    virus_typ: str = Query(default="Influenza A"),
    horizon_days: int = Query(default=7, ge=1, le=60),
    min_train_points: int = Query(default=20, ge=5, le=300),
    strict_vintage_mode: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Kalibierungslauf starten.

    CSV/Excel mit Spalten: datum, menge
    Returns: Metriken, optimierte Gewichte, Chart-Daten, LLM-Insight.
    """
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    content = await file.read()
    _validate_upload(file, content)
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
    if len(df) < 8:
        return {"error": "Mindestens 8 Datenpunkte für OOS-Kalibrierung erforderlich."}

    from app.services.ml.backtester import BacktestService
    service = BacktestService(db)
    return service.run_calibration(
        df,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        strict_vintage_mode=strict_vintage_mode,
    )


@router.post("/preview", dependencies=[Depends(get_current_admin)])
async def preview_calibration_data(
    file: UploadFile = File(...),
):
    """Vorschau der hochgeladenen Kalibrierungsdaten."""
    content = await file.read()
    _validate_upload(file, content)
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


@router.post("/analyze-global", dependencies=[Depends(get_current_admin)])
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


@router.post("/simulate-market", dependencies=[Depends(get_current_admin)])
async def simulate_market_correlation(
    target: str = Query(
        default="RKI_ARE",
        description="Proxy-Target: RKI_ARE, SURVSTAT, MYCOPLASMA, KEUCHHUSTEN, PNEUMOKOKKEN",
    ),
    virus_typ: str = Query(default="Influenza A"),
    days_back: int = Query(default=730, description="Rückblick in Tagen (Default: 2 Jahre)"),
    horizon_days: int = Query(default=14, description="Forecast-Horizont in Tagen (Default: 14)"),
    min_train_points: int = Query(default=20, description="Mindestanzahl Trainingspunkte je Fold"),
    strict_vintage_mode: bool = Query(
        default=True,
        description="Wenn true: nur Daten verwenden, die zum Forecast-Zeitpunkt verfügbar waren",
    ),
    db: Session = Depends(get_db),
):
    """Demo-Modus: Markt-Simulation ohne Kundendaten gegen RKI-Proxy-Wahrheit."""
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    target_key = (target or "RKI_ARE").strip().upper()
    if target_key not in VALID_MARKET_TARGETS and not target_key.startswith("SURVSTAT:"):
        return {
            "error": f"Ungültiges target '{target}'.",
            "allowed_targets": sorted(VALID_MARKET_TARGETS),
            "hint": "Optional auch SURVSTAT:<Suchbegriff> (z.B. SURVSTAT:Mycoplasma)",
        }

    from app.services.ml.backtester import BacktestService
    service = BacktestService(db)
    return service.run_market_simulation(
        virus_typ=virus_typ,
        target_source=target_key,
        days_back=days_back,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        strict_vintage_mode=strict_vintage_mode,
    )
