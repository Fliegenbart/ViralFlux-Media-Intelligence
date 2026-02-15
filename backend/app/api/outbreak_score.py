"""Outbreak Score API — Ganz Immun Fusion Engine.

Endpoints für den Outbreak Risk Score, Prophet-Vorhersagen,
historische Labordaten-Import und Meta-Learner-Training.
"""

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
from io import StringIO
import logging

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Singleton für DrugShortage-Cache ──────────────────────────────────────
_cached_shortage_signals: dict | None = None


def _get_shortage_signals() -> dict | None:
    """Drug-Shortage-Signale aus dem Cache oder vom Analyzer holen."""
    global _cached_shortage_signals
    if _cached_shortage_signals:
        return _cached_shortage_signals
    try:
        from app.api.drug_shortage import _analyzer
        if _analyzer and _analyzer.df is not None and not _analyzer.df.empty:
            signals = _analyzer.get_infection_signals()
            _cached_shortage_signals = signals
            return signals
    except Exception:
        pass
    return None


@router.get("/current")
async def get_outbreak_score(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Aktuellen Ganz Immun Outbreak Score berechnen.

    Schnelle Berechnung aus gecachten/gespeicherten Daten.
    Prophet-Prognosen werden aus der DB gelesen (nicht neu berechnet).
    """
    from app.services.fusion_engine.risk_engine import RiskEngine

    engine = RiskEngine(db)
    shortage = _get_shortage_signals()

    return engine.compute_outbreak_score(
        virus_typ=virus_typ,
        shortage_signals=shortage,
    )


@router.get("/all")
async def get_all_outbreak_scores(db: Session = Depends(get_db)):
    """Outbreak Scores für alle Virus-Typen berechnen."""
    from app.services.fusion_engine.risk_engine import RiskEngine

    engine = RiskEngine(db)
    shortage = _get_shortage_signals()

    return engine.compute_all_viruses(shortage_signals=shortage)


@router.get("/history")
async def get_score_history(
    virus_typ: str = None,
    days: int = 90,
    db: Session = Depends(get_db),
):
    """Historische Outbreak Scores abrufen."""
    from app.services.fusion_engine.risk_engine import RiskEngine

    engine = RiskEngine(db)
    return engine.get_score_history(virus_typ=virus_typ, days=days)


@router.post("/compute-prophet")
async def compute_with_prophet(
    virus_typ: str = "Influenza A",
    forecast_days: int = 28,
    db: Session = Depends(get_db),
):
    """Outbreak Score mit frischer Prophet-Vorhersage berechnen (langsam, ~30s).

    Trainiert Prophet neu und berechnet dann den Score.
    """
    from app.services.fusion_engine.risk_engine import RiskEngine
    from app.services.fusion_engine.prophet_predictor import ProphetPredictor

    prophet_result = None
    prophet_error = None

    try:
        predictor = ProphetPredictor(db)
        prophet_result = predictor.fit_and_predict(
            virus_typ=virus_typ,
            forecast_days=forecast_days,
        )
    except Exception as e:
        prophet_error = str(e)
        logger.warning(f"Prophet fehlgeschlagen: {e}")

    engine = RiskEngine(db)
    shortage = _get_shortage_signals()

    score = engine.compute_outbreak_score(
        virus_typ=virus_typ,
        shortage_signals=shortage,
        prophet_result=prophet_result,
    )

    return {
        **score,
        "prophet_status": "success" if prophet_result else "failed",
        "prophet_error": prophet_error,
        "prophet_forecast_days": prophet_result.get('forecast_days') if prophet_result else None,
    }


@router.post("/train-meta-learner")
async def train_meta_learner(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """XGBoost Meta-Learner trainieren (Phase B aktivieren)."""
    from app.services.fusion_engine.risk_engine import RiskEngine

    engine = RiskEngine(db)
    return engine.train_meta_learner(virus_typ=virus_typ)


@router.post("/upload-lab-history")
async def upload_lab_history(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Interne Labordaten (Ground Truth) hochladen.

    CSV-Format: datum, test_type, total_tests, positive_tests [, region]
    """
    from app.services.fusion_engine.baseline_analyzer import BaselineAnalyzer

    content = await file.read()
    # Auto-detect encoding & separator
    text = content.decode('utf-8', errors='replace')
    sep = ';' if ';' in text[:500] else ','
    df = pd.read_csv(StringIO(text), sep=sep)

    analyzer = BaselineAnalyzer(db)
    result = analyzer.ingest_internal_history(df)

    return {
        "success": True,
        "filename": file.filename,
        **result,
    }


@router.post("/upload-orders")
async def upload_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """ERP-Bestelldaten (Fallback Signal) hochladen.

    CSV-Format: order_date, article_id, quantity [, customer_id]
    """
    from app.services.fusion_engine.order_signal_analyzer import OrderSignalAnalyzer

    content = await file.read()
    text = content.decode('utf-8', errors='replace')
    sep = ';' if ';' in text[:500] else ','
    df = pd.read_csv(StringIO(text), sep=sep)

    analyzer = OrderSignalAnalyzer(db)
    result = analyzer.ingest_orders(df)

    return {
        "success": True,
        "filename": file.filename,
        **result,
    }


@router.get("/baseline")
async def get_seasonal_baseline(
    test_typ: str = None,
    db: Session = Depends(get_db),
):
    """Saisonales Baseline-Profil aus internen Labordaten."""
    from app.services.fusion_engine.baseline_analyzer import BaselineAnalyzer

    analyzer = BaselineAnalyzer(db)
    return analyzer.calculate_seasonal_baseline(test_typ=test_typ)


@router.get("/order-velocity")
async def get_order_velocity(
    article_id: str = None,
    db: Session = Depends(get_db),
):
    """Aktuelle Bestellgeschwindigkeit (Order Velocity)."""
    from app.services.fusion_engine.order_signal_analyzer import OrderSignalAnalyzer

    analyzer = OrderSignalAnalyzer(db)
    if article_id:
        return analyzer.calculate_order_velocity(article_id=article_id)
    return analyzer.get_summary()
