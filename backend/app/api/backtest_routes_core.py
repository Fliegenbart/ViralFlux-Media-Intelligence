"""Core Backtest API routes."""

from __future__ import annotations

from io import BytesIO, StringIO

import pandas as pd
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.database import SurvstatWeeklyData
from app.services.ml.backtester import BacktestService

router = APIRouter()

VALID_VIRUS_TYPES = {"Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"}
VALID_MARKET_TARGETS = {
    "ATEMWEGSINDEX",
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

    df.columns = [column.strip().lower().replace(" ", "_") for column in df.columns]
    return df


@router.post("/market", dependencies=[Depends(get_current_admin)])
async def run_market_backtest(
    target_source: str = Query(default="RKI_ARE"),
    virus_typ: str = Query(default="Influenza A"),
    days_back: int = Query(default=2500, ge=60, le=3000),
    horizon_days: int = Query(default=7, ge=0, le=60),
    min_train_points: int = Query(default=0, ge=0, le=300),
    strict_vintage_mode: bool = Query(default=True),
    bundesland: str = Query(default="", description="Bundesland-Filter (leer=Bundesweit)"),
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
        bundesland=bundesland.strip(),
    )


@router.get("/top-regions", dependencies=[Depends(get_current_user)])
async def top_regions(
    target_source: str = Query(default="MYCOPLASMA"),
    n: int = Query(default=5, ge=1, le=16),
    db: Session = Depends(get_db),
):
    """Top-N Bundesländer nach aktuellem Signal (letzte verfügbare Woche)."""
    token = (target_source or "MYCOPLASMA").strip().upper()

    service = BacktestService(db)
    if token == "ATEMWEGSINDEX":
        diseases = list(service.GELO_ATEMWEG_DISEASES)
    elif token == "RKI_ARE":
        diseases = ["Influenza, saisonal"]
    else:
        alias = service.SURVSTAT_TARGET_ALIASES.get(token, token)
        disease = service._resolve_survstat_disease(alias)
        if not disease:
            return {"error": f"Unbekanntes target_source: {target_source}"}
        diseases = [disease]

    latest_week = db.query(func.max(SurvstatWeeklyData.week_label)).filter(
        SurvstatWeeklyData.disease.in_(diseases),
        SurvstatWeeklyData.bundesland != "Gesamt",
    ).scalar()

    if not latest_week:
        return {"week": None, "disease": ", ".join(diseases), "regions": []}

    if token == "ATEMWEGSINDEX":
        rows = (
            db.query(
                SurvstatWeeklyData.bundesland,
                func.sum(SurvstatWeeklyData.incidence).label("total"),
            )
            .filter(
                SurvstatWeeklyData.disease.in_(diseases),
                SurvstatWeeklyData.week_label == latest_week,
                SurvstatWeeklyData.bundesland != "Gesamt",
                or_(SurvstatWeeklyData.age_group == "Gesamt", SurvstatWeeklyData.age_group.is_(None)),
            )
            .group_by(SurvstatWeeklyData.bundesland)
            .order_by(func.sum(SurvstatWeeklyData.incidence).desc())
            .limit(n)
            .all()
        )

        return {
            "week": latest_week,
            "disease": "Atemwegsindex",
            "regions": [
                {"bundesland": row.bundesland, "incidence": round(float(row.total or 0), 2)}
                for row in rows
            ],
        }

    rows = (
        db.query(SurvstatWeeklyData)
        .filter(
            SurvstatWeeklyData.disease.in_(diseases),
            SurvstatWeeklyData.week_label == latest_week,
            SurvstatWeeklyData.bundesland != "Gesamt",
            or_(SurvstatWeeklyData.age_group == "Gesamt", SurvstatWeeklyData.age_group.is_(None)),
        )
        .order_by(SurvstatWeeklyData.incidence.desc())
        .limit(n)
        .all()
    )

    return {
        "week": latest_week,
        "disease": diseases[0],
        "regions": [
            {"bundesland": row.bundesland, "incidence": round(float(row.incidence or 0), 2)}
            for row in rows
        ],
    }


@router.post("/customer", dependencies=[Depends(get_current_admin)])
async def run_customer_backtest(
    file: UploadFile = File(...),
    virus_typ: str = Query(default="Influenza A"),
    horizon_days: int = Query(default=7, ge=0, le=60),
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


@router.post("/business-pitch", dependencies=[Depends(get_current_admin)])
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
    """Business Pitch Report: ML-Frühsignal-Vorteil vs. RKI-Meldung."""
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    service = BacktestService(db)
    return service.generate_business_pitch_report(
        disease=disease,
        virus_typ=virus_typ,
        season_start=season_start,
        season_end=season_end,
    )


@router.get("/runs", dependencies=[Depends(get_current_user)])
async def list_backtest_runs(
    mode: str | None = Query(default=None, description="MARKET_CHECK oder CUSTOMER_CHECK"),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Historie persistierter Backtests."""
    service = BacktestService(db)
    runs = service.list_backtest_runs(mode=mode, limit=limit)
    return {"total": len(runs), "runs": runs}


@router.get("/runs/{run_id}", dependencies=[Depends(get_current_user)])
async def get_backtest_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Detailansicht für einen persistierten Backtest-Lauf inklusive Chart-Daten."""
    service = BacktestService(db)
    run = service.get_backtest_run(run_id)
    if not run:
        return {"detail": f"Backtest-Run {run_id} nicht gefunden."}
    return run
