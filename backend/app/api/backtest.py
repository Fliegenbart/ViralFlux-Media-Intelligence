"""Backtest API: Twin-Mode (Market + Customer)."""

from __future__ import annotations

from io import BytesIO, StringIO

import pandas as pd
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.ml.backtester import BacktestService


router = APIRouter()

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
    if filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
    else:
        text = content.decode("utf-8", errors="replace")
        sep = ";" if ";" in text[:500] else ","
        df = pd.read_csv(StringIO(text), sep=sep)

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


@router.post("/market")
async def run_market_backtest(
    target_source: str = Query(default="RKI_ARE"),
    virus_typ: str = Query(default="Influenza A"),
    days_back: int = Query(default=730, ge=60, le=2000),
    horizon_days: int = Query(default=14, ge=0, le=60),
    min_train_points: int = Query(default=20, ge=5, le=300),
    strict_vintage_mode: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Mode A: Markt-Check ohne Kundendaten."""
    target_key = (target_source or "RKI_ARE").strip().upper()
    if target_key not in VALID_MARKET_TARGETS and not target_key.startswith("SURVSTAT:"):
        return {
            "error": f"Ungültiges target_source '{target_source}'.",
            "allowed_targets": sorted(VALID_MARKET_TARGETS),
        }

    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    service = BacktestService(db)
    return service.run_market_simulation(
        virus_typ=virus_typ,
        target_source=target_key,
        days_back=days_back,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        strict_vintage_mode=strict_vintage_mode,
    )


@router.post("/customer")
async def run_customer_backtest(
    file: UploadFile = File(...),
    virus_typ: str = Query(default="Influenza A"),
    horizon_days: int = Query(default=14, ge=0, le=60),
    min_train_points: int = Query(default=20, ge=5, le=300),
    strict_vintage_mode: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Mode B: Realitäts-Check mit Kundendaten (CSV/XLSX)."""
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    content = await file.read()
    df = _read_upload(content, file.filename or "customer.csv")

    if "datum" not in df.columns or "menge" not in df.columns:
        return {
            "error": "Fehlende Pflichtspalten. Erwartet: datum, menge",
            "found_columns": list(df.columns),
            "hint": "Optional zusätzlich: region",
        }

    service = BacktestService(db)
    return service.run_customer_simulation(
        customer_df=df,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        strict_vintage_mode=strict_vintage_mode,
    )


@router.post("/business-pitch")
async def run_business_pitch_report(
    disease: str = Query(
        default="GELO_ATEMWEG",
        description=(
            "Krankheit(en) als Ground Truth. "
            "'GELO_ATEMWEG' = aggregierte Atemwegsinfekte (Influenza+RSV+Keuchhusten+Mycoplasma+Parainfluenza). "
            "Oder ein einzelner Krankheitsname aus SurvStat."
        ),
    ),
    virus_typ: str = Query(default="Influenza A"),
    season_start: str = Query(default="2024-10-01"),
    season_end: str = Query(default="2025-03-31"),
    db: Session = Depends(get_db),
):
    """Business Pitch Report: ML-Frühsignal-Vorteil vs. RKI-Meldung.

    Berechnet für die gewählte Saison wochenweise den ML-Risikoscore
    und vergleicht das erste Warnsignal mit dem tatsächlichen RKI-Peak.
    Default: Gelo-relevante Atemwegsinfekte.
    """
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    service = BacktestService(db)
    return service.generate_business_pitch_report(
        disease=disease,
        virus_typ=virus_typ,
        season_start=season_start,
        season_end=season_end,
    )


@router.get("/runs")
async def list_backtest_runs(
    mode: str | None = Query(default=None, description="MARKET_CHECK oder CUSTOMER_CHECK"),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Historie persistierter Backtests."""
    service = BacktestService(db)
    runs = service.list_backtest_runs(mode=mode, limit=limit)
    return {"total": len(runs), "runs": runs}
