"""Outbreak Score API — Fusion Engine.

Endpoints für den Outbreak Risk Score, Prophet-Vorhersagen,
historische Labordaten-Import und Meta-Learner-Training.
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import pandas as pd
from io import StringIO
import logging

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.services.media.ranking_signal_service import RankingSignalService

logger = logging.getLogger(__name__)
router = APIRouter()
ALLOWED_CSV_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
}
PUBLIC_PEIX_REGION_FIELDS = (
    "region_code",
    "region_name",
    "score_0_100",
    "risk_band",
    "impact_probability",
    "score_semantics",
    "impact_probability_semantics",
    "impact_probability_deprecated",
)


# ─── Singleton für DrugShortage-Cache ──────────────────────────────────────
_cached_shortage_signals: dict | None = None


def _get_shortage_signals() -> dict | None:
    """Drug-Shortage-Signale aus Cache, Analyzer oder BfArM Auto-Pull."""
    global _cached_shortage_signals
    if _cached_shortage_signals:
        return _cached_shortage_signals

    # Versuch 1: Bestehender Analyzer (manueller Upload oder auto-refresh)
    try:
        from app.api.drug_shortage import _ensure_analyzer
        analyzer = _ensure_analyzer()
        if analyzer and analyzer.df is not None and not analyzer.df.empty:
            signals = analyzer.get_infection_signals()
            _cached_shortage_signals = signals
            return signals
    except Exception:
        pass

    # Versuch 2: Cached Signals vom BfArM Auto-Pull Service
    try:
        from app.services.data_ingest.bfarm_service import get_cached_signals
        cached = get_cached_signals()
        if cached:
            _cached_shortage_signals = cached
            return cached
    except Exception:
        pass

    return None


def _validate_csv_upload(file: UploadFile, content: bytes) -> None:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Nur CSV-Dateien erlaubt")

    content_type = (file.content_type or "").lower().strip()
    if content_type and content_type not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Dateityp nicht erlaubt")

    if not content or b"\x00" in content[:2048]:
        raise HTTPException(status_code=400, detail="Ungültige CSV-Datei")


def _to_public_peix_payload(payload: dict) -> dict:
    regions = payload.get("regions")
    safe_regions: dict[str, dict] = {}

    if isinstance(regions, dict):
        for code, region in regions.items():
            if not isinstance(region, dict):
                continue
            safe_regions[code] = {
                field: region[field]
                for field in PUBLIC_PEIX_REGION_FIELDS
                if field in region
            }

    public_payload = {
        "national_score": payload.get("national_score"),
        "national_band": payload.get("national_band"),
        "national_impact_probability": payload.get("national_impact_probability"),
        "score_semantics": payload.get("score_semantics"),
        "impact_probability_semantics": payload.get("impact_probability_semantics"),
        "impact_probability_deprecated": payload.get("impact_probability_deprecated"),
        "generated_at": payload.get("generated_at"),
        "regions": safe_regions,
    }
    return {key: value for key, value in public_payload.items() if value is not None}


@router.get("/current", dependencies=[Depends(get_current_user)])
async def get_outbreak_score(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Aktuellen Outbreak Score berechnen.

    Schnelle Berechnung aus gecachten/gespeicherten Daten.
    Prophet-Prognosen werden aus der DB gelesen (nicht neu berechnet).
    """
    from app.services.ml.forecast_decision_service import ForecastDecisionService

    return ForecastDecisionService(db).build_legacy_outbreak_score(
        virus_typ=virus_typ,
    )


@router.get("/peix-score")
async def get_peix_score(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Öffentliche Kurzfassung des PeixEpiScore für die Landing-Page."""
    service = RankingSignalService(db)
    return _to_public_peix_payload(service.build(virus_typ=virus_typ))


@router.get("/peix-score/full", dependencies=[Depends(get_current_user)])
async def get_peix_score_full(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Vollständiger PeixEpiScore für authentifizierte Innenansichten."""
    service = RankingSignalService(db)
    return service.build(virus_typ=virus_typ)


@router.get("/all", dependencies=[Depends(get_current_user)])
async def get_all_outbreak_scores(db: Session = Depends(get_db)):
    """Outbreak Scores für alle Virus-Typen (delegiert an PeixEpiScore)."""
    service = RankingSignalService(db)
    peix = service.build()

    # Backward-kompatible Response-Struktur
    return {
        "overall_score": peix["national_score"],
        "overall_risk_level": peix["national_band"].upper(),
        "virus_scores": {
            v: {
                "score": round(info["epi_score"] * 100, 1),
                "risk_level": service._score_to_band(info["epi_score"] * 100).upper(),
            }
            for v, info in peix.get("virus_scores", {}).items()
        },
        "peix_epi_score": peix,
    }


@router.get("/history", dependencies=[Depends(get_current_user)])
async def get_score_history(
    virus_typ: str = None,
    days: int = 90,
    db: Session = Depends(get_db),
):
    """Historische Outbreak Scores abrufen."""
    from app.services.ml.forecast_decision_service import ForecastDecisionService

    target_virus = virus_typ or "Influenza A"
    return ForecastDecisionService(db).get_legacy_score_history(
        virus_typ=target_virus,
        days=days,
    )


@router.post("/compute-prophet", dependencies=[Depends(get_current_admin)])
async def compute_with_prophet(
    virus_typ: str = "Influenza A",
    forecast_days: int = 28,
    db: Session = Depends(get_db),
):
    """Outbreak Score mit frischer Prophet-Vorhersage berechnen (langsam, ~30s).

    Trainiert Prophet neu und berechnet dann den Score.
    """
    from app.services.ml.forecast_decision_service import ForecastDecisionService
    from app.services.ml.forecast_service import ForecastService

    forecast = ForecastService(db).predict(virus_typ=virus_typ)
    return {
        "status": "success" if "error" not in forecast else "failed",
        "message": "Prophet ist kein produktiver Promotion-Pfad mehr; geliefert wird der Forecast-First-Stack.",
        "forecast_days_requested": forecast_days,
        "forecast": forecast,
        "risk_adapter": ForecastDecisionService(db).build_legacy_outbreak_score(
            virus_typ=virus_typ,
        ),
    }


@router.post("/train-meta-learner", dependencies=[Depends(get_current_admin)])
async def train_meta_learner(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """XGBoost Meta-Learner trainieren (Phase B aktivieren)."""
    from app.services.ml.model_trainer import XGBoostTrainer

    return XGBoostTrainer(db).train(virus_typ=virus_typ)


@router.post("/upload-lab-history", dependencies=[Depends(get_current_admin)])
async def upload_lab_history(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Interne Labordaten (Ground Truth) hochladen.

    CSV-Format: datum, test_type, total_tests, positive_tests [, region]
    """
    from app.services.fusion_engine.baseline_analyzer import BaselineAnalyzer

    content = await file.read()
    _validate_csv_upload(file, content)
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


@router.post("/upload-orders", dependencies=[Depends(get_current_admin)])
async def upload_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """ERP-Bestelldaten (Fallback Signal) hochladen.

    CSV-Format: order_date, article_id, quantity [, customer_id]
    """
    from app.services.fusion_engine.order_signal_analyzer import OrderSignalAnalyzer

    content = await file.read()
    _validate_csv_upload(file, content)
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


@router.get("/baseline", dependencies=[Depends(get_current_user)])
async def get_seasonal_baseline(
    test_typ: str = None,
    db: Session = Depends(get_db),
):
    """Saisonales Baseline-Profil aus internen Labordaten."""
    from app.services.fusion_engine.baseline_analyzer import BaselineAnalyzer

    analyzer = BaselineAnalyzer(db)
    return analyzer.calculate_seasonal_baseline(test_typ=test_typ)


@router.get("/order-velocity", dependencies=[Depends(get_current_user)])
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
