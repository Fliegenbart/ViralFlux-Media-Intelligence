"""ML Stacking Forecast Service.

Architecture: XGBoost Meta-Learner stacking three base estimators
(Holt-Winters, Ridge Regression, Prophet) with AMELAG lagged features
and asymmetric loss (quantile regression at 80th percentile).

**Inference flow (decoupled from training):**

1. ``predict()`` checks for pre-trained models on disk
   (serialised by ``model_trainer.XGBoostTrainer``).
2. If found, loads them into a thread-safe in-memory cache and
   runs inference-only (base estimators + XGBoost ``.predict()``).
3. If no model file exists, falls back to the original
   ``train_and_forecast()`` which trains in-memory.
"""

from __future__ import annotations
from app.core.time import utc_now

import json
import logging
import math
import pickle
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import func
from sqlalchemy.orm import Session
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.core.config import get_settings
from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.models.database import (
    GanzimmunData,
    GoogleTrendsData,
    MLForecast,
    SchoolHolidays,
    SurvstatWeeklyData,
    WastewaterAggregated,
    WastewaterData,
)
from app.services.ml.forecast_contracts import (
    BACKTEST_RELIABILITY_PROXY_SOURCE,
    CONFIDENCE_SEMANTICS_ALIAS,
    DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
    DEFAULT_DECISION_HORIZON_DAYS,
    BurdenForecast,
    BurdenForecastPoint,
    EventForecast,
    ForecastQuality,
    confidence_label,
    normalize_event_forecast_payload,
)
from app.services.ml.forecast_horizon_utils import (
    DEFAULT_FORECAST_REGION,
    DEFAULT_WALK_FORWARD_STRIDE,
    LearnedProbabilityModel,
    apply_probability_calibration,
    MIN_DIRECT_TRAIN_POINTS,
    build_direct_target_frame,
    build_walk_forward_splits,
    compute_classification_metrics,
    compute_regression_metrics,
    ensure_supported_horizon,
    model_artifact_dir,
    normalize_forecast_region,
    reliability_score_from_metrics,
    select_probability_calibration,
)
from app.services.ml.regional_panel_utils import BUNDESLAND_NAMES
from app.services.ml.training_contract import INTERNAL_HISTORY_TEST_MAP

logger = logging.getLogger(__name__)
settings = get_settings()

# Features used by the XGBoost meta-learner
META_FEATURES: list[str] = [
    "hw_pred",
    "ridge_pred",
    "prophet_pred",
    "amelag_lag4",
    "amelag_lag7",
    "trend_momentum_7d",
    "schulferien",
    "trends_score",
    "xdisease_lag7",
    "xdisease_lag14",
    "survstat_incidence",
    "survstat_lag7",
    "survstat_lag14",
    "lab_positivity_rate",
    "lab_signal_available",
    "lab_baseline_mean",
    "lab_baseline_zscore",
    "lab_positivity_lag7",
]

RIDGE_DIRECT_FEATURES: list[str] = [
    "lag1",
    "lag2",
    "lag3",
    "ma3",
    "ma5",
    "roc",
    "trend_momentum_7d",
    "amelag_lag4",
    "amelag_lag7",
    "trends_score",
    "schulferien",
    "xdisease_lag7",
    "xdisease_lag14",
    "survstat_incidence",
    "survstat_lag7",
    "survstat_lag14",
    "lab_positivity_rate",
    "lab_signal_available",
    "lab_baseline_mean",
    "lab_baseline_zscore",
    "lab_positivity_lag7",
]

LEAKAGE_SAFE_WARMUP_ROWS = 14

# Cross-disease pairs: epidemiologisch sinnvolle Korrelationen.
# Key = Zielvirus, Value = Liste von Indikator-Viren (deren Aktivitaet
# oft zeitlich vorlaufend oder co-zirkulierend ist).
CROSS_DISEASE_MAP: dict[str, list[str]] = {
    "Influenza A": ["RSV A", "SARS-CoV-2"],
    "Influenza B": ["Influenza A", "SARS-CoV-2"],
    "SARS-CoV-2": ["Influenza A", "Influenza B"],
    "RSV A": ["Influenza A", "Influenza B"],
}

# SurvStat-Krankheiten pro Virus (laborbestätigte RKI-Meldedaten)
SURVSTAT_VIRUS_MAP: dict[str, list[str]] = {
    "Influenza A": ["influenza, saisonal"],
    "Influenza B": ["influenza, saisonal"],
    "SARS-CoV-2": ["covid-19"],
    "RSV A": ["rsv (meldepflicht gemäß ifsg)"],
}

DEFAULT_XGB_QUANTILE_CONFIG: dict[str, dict[str, Any]] = {
    "median": {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.5,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "lower": {
        "n_estimators": 100,
        "max_depth": 4,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.1,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "upper": {
        "n_estimators": 100,
        "max_depth": 4,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.9,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
}

DEFAULT_EVENT_CLASSIFIER_CONFIG: dict[str, Any] = {
    "n_estimators": 120,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": 1,
}

EVENT_MODEL_ARTIFACT_NAME = "event_probability_model.pkl"

# ═══════════════════════════════════════════════════════════════════════
#  MODEL LOADING & CACHING (module-level, shared across requests)
# ═══════════════════════════════════════════════════════════════════════

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models"

# Thread-safe cache: {virus|region|horizon: (model_med, model_lo, model_hi, metadata, event_model)}
_model_cache: dict[str, tuple[Any, Any, Any, dict[str, Any], LearnedProbabilityModel | None]] = {}
_cache_lock = threading.Lock()


def _virus_slug(virus_typ: str) -> str:
    """Normalise virus name to filesystem-safe slug."""
    return virus_typ.lower().replace(" ", "_").replace("-", "_")


def _load_cached_models(
    virus_typ: str,
    *,
    region: str = DEFAULT_FORECAST_REGION,
    horizon_days: int = DEFAULT_DECISION_HORIZON_DAYS,
) -> tuple[Any, Any, Any, dict[str, Any], LearnedProbabilityModel | None] | None:
    """Load XGBoost models from disk with in-memory caching.

    Returns ``(model_median, model_lower, model_upper, metadata)``
    or *None* when no serialised model exists for *virus_typ*.
    """
    from xgboost import XGBRegressor

    slug = _virus_slug(virus_typ)
    region_code = normalize_forecast_region(region)
    horizon = ensure_supported_horizon(horizon_days)
    cache_key = f"{slug}|{region_code}|{horizon}"

    with _cache_lock:
        if cache_key in _model_cache:
            return _model_cache[cache_key]

    model_dir = model_artifact_dir(
        _ML_MODELS_DIR,
        virus_typ=virus_typ,
        region=region_code,
        horizon_days=horizon,
    )
    metadata_path = model_dir / "metadata.json"

    if not metadata_path.exists() and region_code == DEFAULT_FORECAST_REGION and horizon == DEFAULT_DECISION_HORIZON_DAYS:
        legacy_dir = _ML_MODELS_DIR / slug
        legacy_metadata = legacy_dir / "metadata.json"
        if legacy_metadata.exists():
            model_dir = legacy_dir
            metadata_path = legacy_metadata

    if not metadata_path.exists():
        return None

    try:
        with open(metadata_path) as f:
            metadata = json.load(f)

        model_med = XGBRegressor()
        model_med.load_model(str(model_dir / "model_median.json"))

        model_lo = XGBRegressor()
        model_lo.load_model(str(model_dir / "model_lower.json"))

        model_hi = XGBRegressor()
        model_hi.load_model(str(model_dir / "model_upper.json"))

        event_model: LearnedProbabilityModel | None = None
        event_model_path = model_dir / EVENT_MODEL_ARTIFACT_NAME
        if event_model_path.exists():
            with open(event_model_path, "rb") as handle:
                loaded = pickle.load(handle)
            if isinstance(loaded, LearnedProbabilityModel):
                event_model = loaded

        result = (model_med, model_lo, model_hi, metadata, event_model)

        with _cache_lock:
            _model_cache[cache_key] = result

        logger.info(
            f"Loaded XGBoost models from disk for {virus_typ}/{region_code}/h{horizon} "
            f"(version={metadata.get('version')}, "
            f"trained_at={metadata.get('trained_at')})"
        )
        return result

    except Exception as e:
        logger.warning(f"Failed to load models for {virus_typ}: {e}")
        return None


def invalidate_model_cache(virus_typ: str | None = None) -> None:
    """Clear cached models so the next ``predict()`` reloads from disk.

    Called by ``XGBoostTrainer`` after writing fresh artefacts.
    """
    with _cache_lock:
        if virus_typ:
            prefix = f"{_virus_slug(virus_typ)}|"
            for key in list(_model_cache.keys()):
                if key.startswith(prefix):
                    _model_cache.pop(key, None)
        else:
            _model_cache.clear()


def _is_model_feature_compatibility_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "feature shape mismatch" in message
        or "number of columns does not match" in message
        or "feature_names mismatch" in message
    )


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


class EmpiricalEventClassifier:
    def __init__(self, probability: float) -> None:
        self.probability = float(np.clip(probability, 0.001, 0.999))

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        n_rows = len(np.asarray(X))
        probs = np.full(n_rows, self.probability, dtype=float)
        return np.column_stack([1.0 - probs, probs])


class ForecastService:
    """ML Stacking Forecast: HW + Ridge + Prophet → XGBoost Meta-Learner."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.forecast_days: int = settings.FORECAST_DAYS
        self.confidence_level: float = settings.CONFIDENCE_LEVEL

    # ═══════════════════════════════════════════════════════════════════
    #  DATA PREPARATION
    # ═══════════════════════════════════════════════════════════════════

    def prepare_training_data(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
        include_internal_history: bool = True,
        region: str = DEFAULT_FORECAST_REGION,
    ) -> pd.DataFrame:
        """Build feature DataFrame from wastewater, trends, holidays, AMELAG."""
        region_code = normalize_forecast_region(region)
        logger.info(f"Preparing training data for {virus_typ}/{region_code}")
        start_date = datetime.now() - timedelta(days=lookback_days)

        # 1. Wastewater viral load (target) + AMELAG vorhersage
        df = self._load_wastewater_training_frame(
            virus_typ=virus_typ,
            start_date=start_date,
            region=region_code,
        )
        if df.empty:
            logger.warning(f"No wastewater data found for {virus_typ}")
            return pd.DataFrame()

        df = df.sort_values("ds").reset_index(drop=True)
        df["ds"] = pd.to_datetime(df["ds"])

        # 2. Google Trends
        trends_keywords = ["Grippe", "Erkältung", "Fieber"]
        trends = self._load_google_trends_rows(
            keywords=trends_keywords,
            start_date=start_date,
            region=region_code,
        )

        if trends:
            trends_df = pd.DataFrame(
                [{"ds": pd.to_datetime(t.datum), "interest_score": t.interest_score} for t in trends]
            )
            trends_avg = trends_df.groupby("ds")["interest_score"].mean().reset_index()
            trends_avg.columns = ["ds", "trends_score"]
            df = df.merge(trends_avg, on="ds", how="left")
        else:
            df["trends_score"] = 0.0

        # 3. School holidays
        df["schulferien"] = df["ds"].apply(
            lambda d: 1.0 if self._is_holiday(d, region=region_code) else 0.0
        )

        if include_internal_history:
            df = self._augment_with_internal_history(
                df=df,
                virus_typ=virus_typ,
                start_date=start_date,
                region=region_code,
            )
        else:
            df["lab_positivity_rate"] = 0.0
            df["lab_signal_available"] = 0.0
            df["lab_baseline_mean"] = 0.0
            df["lab_baseline_zscore"] = 0.0
            df["lab_positivity_lag7"] = 0.0

        # 4. Lag features
        df["lag1"] = df["y"].shift(1)
        df["lag2"] = df["y"].shift(2)
        df["lag3"] = df["y"].shift(3)

        # 5. Moving averages (shifted by 1 to avoid target leakage)
        df["ma3"] = df["y"].rolling(window=3, min_periods=1).mean().shift(1)
        df["ma5"] = df["y"].rolling(window=5, min_periods=1).mean().shift(1)

        # 6. Rate of change (shifted by 1 to avoid target leakage)
        df["roc"] = df["y"].pct_change().shift(1)

        # 7. Trend momentum (7-day slope as 1st derivative)
        y_shifted = df["y"].shift(7).replace(0, np.nan)
        df["trend_momentum_7d"] = df["y"].diff(periods=7) / y_shifted

        # 8. AMELAG vorhersage time-lagged features (wastewater leads demand by 4-7 days)
        df["amelag_lag4"] = df["amelag_pred"].shift(4)
        df["amelag_lag7"] = df["amelag_pred"].shift(7)

        # 9. Cross-disease features: aggregierte Viruslast anderer Erreger
        xdisease_viruses = CROSS_DISEASE_MAP.get(virus_typ, [])
        if xdisease_viruses:
            xd_data = (
                self.db.query(
                    WastewaterAggregated.datum,
                    func.avg(WastewaterAggregated.viruslast_normalisiert).label("xd_load"),
                )
                .filter(
                    WastewaterAggregated.virus_typ.in_(xdisease_viruses),
                    WastewaterAggregated.datum >= start_date,
                )
                .group_by(WastewaterAggregated.datum)
                .all()
            )
            if xd_data:
                xd_df = pd.DataFrame(
                    [{"ds": pd.to_datetime(r.datum), "xd_load": float(r.xd_load or 0)} for r in xd_data]
                )
                df = df.merge(xd_df, on="ds", how="left")
                df["xd_load"] = df["xd_load"].fillna(0.0)
            else:
                df["xd_load"] = 0.0
        else:
            df["xd_load"] = 0.0
        df["xdisease_lag7"] = df["xd_load"].shift(7)
        df["xdisease_lag14"] = df["xd_load"].shift(14)

        # 10. SurvStat RKI-Meldeinzidenzen (wöchentlich → forward-fill auf Tagesauflösung)
        survstat_diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
        if survstat_diseases:
            surv_rows = (
                self.db.query(
                    SurvstatWeeklyData.week_start,
                    func.sum(SurvstatWeeklyData.incidence).label("total_incidence"),
                )
                .filter(
                    func.lower(SurvstatWeeklyData.disease).in_(survstat_diseases),
                    SurvstatWeeklyData.bundesland.in_(self._survstat_region_values(region_code)),
                    SurvstatWeeklyData.week > 0,
                    SurvstatWeeklyData.week_start >= start_date,
                )
                .group_by(SurvstatWeeklyData.week_start)
                .order_by(SurvstatWeeklyData.week_start.asc())
                .all()
            )
            if surv_rows:
                surv_df = pd.DataFrame(
                    [{"ds": pd.to_datetime(r.week_start), "survstat_raw": float(r.total_incidence or 0)}
                     for r in surv_rows]
                )
                # Max-Normalisierung auf [0, 1]
                surv_max = surv_df["survstat_raw"].max() or 1.0
                surv_df["survstat_incidence"] = surv_df["survstat_raw"] / surv_max
                surv_df = surv_df[["ds", "survstat_incidence"]]
                df = df.merge(surv_df, on="ds", how="left")
                df["survstat_incidence"] = df["survstat_incidence"].ffill().fillna(0.0)
            else:
                df["survstat_incidence"] = 0.0
        else:
            df["survstat_incidence"] = 0.0
        df["survstat_lag7"] = df["survstat_incidence"].shift(7)
        df["survstat_lag14"] = df["survstat_incidence"].shift(14)

        df = self._finalize_training_frame(df)
        df["region"] = region_code

        logger.info(f"Training data prepared: {len(df)} rows, {len(df.columns)} features")
        return df

    @staticmethod
    def _finalize_training_frame(df: pd.DataFrame) -> pd.DataFrame:
        """Leakage-safe post processing for engineered training features.

        We explicitly avoid backfilling lagged or rolling features from the
        future into the past. Instead we:
        1. forward-fill a small set of source signals that are naturally held
           until a newer observation arrives,
        2. drop the warm-up rows required by the largest lag (14 days),
        3. zero-fill any remaining gaps.
        """
        cleaned = df.copy()
        cleaned = cleaned.sort_values("ds").reset_index(drop=True)
        cleaned = cleaned.replace([np.inf, -np.inf], np.nan)

        held_signal_cols = [
            "trends_score",
            "schulferien",
            "amelag_pred",
            "xd_load",
            "survstat_incidence",
            "lab_positivity_rate",
            "lab_signal_available",
            "lab_baseline_mean",
            "lab_baseline_zscore",
        ]
        for col in held_signal_cols:
            if col in cleaned.columns:
                cleaned[col] = cleaned[col].ffill()

        if len(cleaned) > LEAKAGE_SAFE_WARMUP_ROWS:
            cleaned = cleaned.iloc[LEAKAGE_SAFE_WARMUP_ROWS:].copy()

        cleaned = cleaned.fillna(0.0).reset_index(drop=True)
        return cleaned

    @staticmethod
    def _region_variants(region: str) -> list[str]:
        region_code = normalize_forecast_region(region)
        if region_code == DEFAULT_FORECAST_REGION:
            return [DEFAULT_FORECAST_REGION]

        variants = [region_code]
        state_name = BUNDESLAND_NAMES.get(region_code)
        if state_name:
            variants.append(state_name)
        return variants

    @classmethod
    def _survstat_region_values(cls, region: str) -> list[str]:
        region_code = normalize_forecast_region(region)
        if region_code == DEFAULT_FORECAST_REGION:
            return ["Gesamt", DEFAULT_FORECAST_REGION]
        values = cls._region_variants(region_code)
        if "Gesamt" not in values:
            values.append("Gesamt")
        return values

    def _load_wastewater_training_frame(
        self,
        *,
        virus_typ: str,
        start_date: datetime,
        region: str,
    ) -> pd.DataFrame:
        region_code = normalize_forecast_region(region)
        if region_code == DEFAULT_FORECAST_REGION:
            wastewater = (
                self.db.query(WastewaterAggregated)
                .filter(
                    WastewaterAggregated.virus_typ == virus_typ,
                    WastewaterAggregated.datum >= start_date,
                )
                .order_by(WastewaterAggregated.datum.asc())
                .all()
            )
            return pd.DataFrame(
                [
                    {
                        "ds": w.datum,
                        "y": w.viruslast,
                        "viruslast_normalized": w.viruslast_normalisiert,
                        "amelag_pred": w.vorhersage,
                    }
                    for w in wastewater
                ]
            )

        wastewater = (
            self.db.query(
                WastewaterData.datum.label("ds"),
                func.avg(WastewaterData.viruslast).label("y"),
                func.avg(WastewaterData.viruslast_normalisiert).label("viruslast_normalized"),
                func.avg(WastewaterData.vorhersage).label("amelag_pred"),
            )
            .filter(
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.datum >= start_date,
                WastewaterData.bundesland.in_(self._region_variants(region_code)),
            )
            .group_by(WastewaterData.datum)
            .order_by(WastewaterData.datum.asc())
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "ds": row.ds,
                    "y": float(row.y or 0.0),
                    "viruslast_normalized": float(row.viruslast_normalized or 0.0),
                    "amelag_pred": float(row.amelag_pred or 0.0),
                }
                for row in wastewater
            ]
        )

    def _load_google_trends_rows(
        self,
        *,
        keywords: list[str],
        start_date: datetime,
        region: str,
    ) -> list[GoogleTrendsData]:
        region_code = normalize_forecast_region(region)
        region_variants = self._region_variants(region_code)

        if region_code != DEFAULT_FORECAST_REGION:
            region_rows = (
                self.db.query(GoogleTrendsData)
                .filter(
                    GoogleTrendsData.keyword.in_(keywords),
                    GoogleTrendsData.datum >= start_date,
                    GoogleTrendsData.region.in_(region_variants),
                )
                .all()
            )
            if region_rows:
                return region_rows

        return (
            self.db.query(GoogleTrendsData)
            .filter(
                GoogleTrendsData.keyword.in_(keywords),
                GoogleTrendsData.datum >= start_date,
                GoogleTrendsData.region == DEFAULT_FORECAST_REGION,
            )
            .all()
        )

    @staticmethod
    def _build_meta_feature_row(
        last_row: pd.Series,
        *,
        hw_pred: float,
        ridge_pred: float,
        prophet_pred: float,
    ) -> dict[str, float]:
        """Build one inference row for the XGBoost meta-learner."""
        return {
            "hw_pred": float(hw_pred),
            "ridge_pred": float(ridge_pred),
            "prophet_pred": float(prophet_pred),
            "amelag_lag4": float(last_row.get("amelag_lag4", 0.0)),
            "amelag_lag7": float(last_row.get("amelag_lag7", 0.0)),
            "trend_momentum_7d": float(last_row.get("trend_momentum_7d", 0.0)),
            "schulferien": float(last_row.get("schulferien", 0.0)),
            "trends_score": float(last_row.get("trends_score", 0.0)),
            "xdisease_lag7": float(last_row.get("xdisease_lag7", 0.0)),
            "xdisease_lag14": float(last_row.get("xdisease_lag14", 0.0)),
            "survstat_incidence": float(last_row.get("survstat_incidence", 0.0)),
            "survstat_lag7": float(last_row.get("survstat_lag7", 0.0)),
            "survstat_lag14": float(last_row.get("survstat_lag14", 0.0)),
            "lab_positivity_rate": float(last_row.get("lab_positivity_rate", 0.0)),
            "lab_signal_available": float(last_row.get("lab_signal_available", 0.0)),
            "lab_baseline_mean": float(last_row.get("lab_baseline_mean", 0.0)),
            "lab_baseline_zscore": float(last_row.get("lab_baseline_zscore", 0.0)),
            "lab_positivity_lag7": float(last_row.get("lab_positivity_lag7", 0.0)),
        }

    def _augment_with_internal_history(
        self,
        *,
        df: pd.DataFrame,
        virus_typ: str,
        start_date: datetime,
        region: str,
    ) -> pd.DataFrame:
        history_df = self._load_internal_history_frame(
            virus_typ=virus_typ,
            start_date=start_date,
            region=region,
        )
        features = self._build_internal_history_feature_frame(df["ds"], history_df)
        combined = pd.concat([df.reset_index(drop=True), features], axis=1)
        combined["lab_positivity_lag7"] = combined["lab_positivity_rate"].shift(7)
        return combined

    def _load_internal_history_frame(
        self,
        *,
        virus_typ: str,
        start_date: datetime,
        region: str,
    ) -> pd.DataFrame:
        aliases = INTERNAL_HISTORY_TEST_MAP.get(virus_typ, [])
        if not aliases:
            return pd.DataFrame()

        query = (
            self.db.query(GanzimmunData)
            .filter(
                GanzimmunData.datum >= start_date - timedelta(days=365 * 5),
                GanzimmunData.anzahl_tests.isnot(None),
                GanzimmunData.anzahl_tests > 0,
                func.lower(GanzimmunData.test_typ).in_(aliases),
            )
        )
        region_code = normalize_forecast_region(region)
        if region_code != DEFAULT_FORECAST_REGION:
            query = query.filter(
                GanzimmunData.region.in_(self._region_variants(region_code)),
            )
        rows = query.order_by(GanzimmunData.datum.asc()).all()
        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "datum": pd.to_datetime(row.datum),
                    "available_time": pd.to_datetime(row.available_time) if row.available_time else pd.NaT,
                    "anzahl_tests": int(row.anzahl_tests or 0),
                    "positive_ergebnisse": int(row.positive_ergebnisse or 0),
                }
                for row in rows
            ]
        )

    @staticmethod
    def _build_internal_history_feature_frame(
        ds_index: pd.Series,
        history_df: pd.DataFrame,
    ) -> pd.DataFrame:
        columns = [
            "lab_positivity_rate",
            "lab_signal_available",
            "lab_baseline_mean",
            "lab_baseline_zscore",
        ]
        if history_df.empty:
            return pd.DataFrame(0.0, index=range(len(ds_index)), columns=columns)

        history = history_df.copy()
        history["datum"] = pd.to_datetime(history["datum"])
        history["available_time"] = pd.to_datetime(history["available_time"])
        history["effective_available"] = history["available_time"].fillna(history["datum"])
        history["anzahl_tests"] = pd.to_numeric(
            history["anzahl_tests"], errors="coerce",
        ).fillna(0).clip(lower=0)
        history["positive_ergebnisse"] = pd.to_numeric(
            history["positive_ergebnisse"], errors="coerce",
        ).fillna(0).clip(lower=0)
        history = history.loc[history["anzahl_tests"] > 0].copy()
        if history.empty:
            return pd.DataFrame(0.0, index=range(len(ds_index)), columns=columns)

        history["rate"] = history["positive_ergebnisse"] / history["anzahl_tests"]
        iso = history["datum"].dt.isocalendar()
        history["iso_week"] = iso.week.astype(int)
        history["iso_year"] = iso.year.astype(int)

        rows: list[dict[str, float]] = []
        for ds in pd.to_datetime(ds_index):
            visible = history.loc[
                (history["datum"] <= ds)
                & (history["effective_available"] <= ds)
            ]
            if visible.empty:
                rows.append({name: 0.0 for name in columns})
                continue

            recent = visible.loc[visible["datum"] > ds - timedelta(days=14)]
            total_tests = float(recent["anzahl_tests"].sum())
            positivity = float(recent["positive_ergebnisse"].sum() / total_tests) if total_tests > 0 else 0.0

            ds_iso = ds.isocalendar()
            baseline_pool = visible.loc[
                (visible["iso_week"] == int(ds_iso.week))
                & (visible["iso_year"] < int(ds_iso.year))
            ]
            if len(baseline_pool) >= 2:
                baseline_mean = float(baseline_pool["rate"].mean())
                baseline_std = float(baseline_pool["rate"].std()) or 0.01
                z_score = (positivity - baseline_mean) / baseline_std
            else:
                baseline_mean = 0.0
                z_score = 0.0

            rows.append(
                {
                    "lab_positivity_rate": positivity,
                    "lab_signal_available": 1.0 if total_tests > 0 else 0.0,
                    "lab_baseline_mean": baseline_mean,
                    "lab_baseline_zscore": float(z_score),
                }
            )

        return pd.DataFrame(rows, columns=columns)

    def _is_holiday(self, datum: datetime, *, region: str = DEFAULT_FORECAST_REGION) -> bool:
        """Check if date falls in school holidays."""
        query = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= datum,
            SchoolHolidays.end_datum >= datum,
        )
        region_code = normalize_forecast_region(region)
        if region_code != DEFAULT_FORECAST_REGION:
            query = query.filter(
                SchoolHolidays.bundesland.in_(self._region_variants(region_code)),
            )
        return query.first() is not None

    # ═══════════════════════════════════════════════════════════════════
    #  BASE ESTIMATORS
    # ═══════════════════════════════════════════════════════════════════

    def _fit_holt_winters(self, y: np.ndarray, n_steps: int) -> np.ndarray:
        """Holt-Winters forecast with improved fallback chain.

        Model selection:
        - n >= 104: Multiplicative seasonal (2+ years -> robust seasonal decomposition)
        - n >= 8:   Additive seasonal (min seasonal_periods=4)
        - n >= 4:   Damped trend only (short series, prevents divergence)
        - n < 4:    Simple moving average extrapolation
        """
        n = len(y)
        try:
            if n >= 104:
                # 2+ years: multiplicative seasonal captures amplitude changes
                sp = min(52, n // 2)
                hw_model = ExponentialSmoothing(
                    y, trend="add", seasonal="mul",
                    seasonal_periods=sp,
                    initialization_method="estimated",
                )
            elif n >= 8:
                # Additive seasonal with capped period
                sp = min(52, n // 2)
                hw_model = ExponentialSmoothing(
                    y, trend="add", seasonal="add",
                    seasonal_periods=sp,
                    initialization_method="estimated",
                )
            elif n >= 4:
                # Damped trend — no seasonal, but prevents linear divergence
                hw_model = ExponentialSmoothing(
                    y, trend="add", damped_trend=True,
                    initialization_method="estimated",
                )
            else:
                # Too few points — use moving average extrapolation
                recent_mean = float(np.mean(y[-min(3, n):]))
                return np.full(n_steps, max(0.0, recent_mean))

            hw_fit = hw_model.fit(optimized=True)
            forecast = hw_fit.forecast(n_steps)
            # Clip to prevent implausible values
            max_hist = float(np.max(y)) if len(y) > 0 else 1.0
            forecast = np.clip(forecast, 0.0, max_hist * 3.0)
            return forecast

        except Exception as e:
            logger.warning(f"Holt-Winters failed, using damped extrapolation: {e}")
            # Damped linear extrapolation from recent points
            recent = y[-min(5, n):]
            slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
            # Damping factor reduces slope influence over time
            base = float(y[-1])
            max_hist = float(np.max(y)) if len(y) > 0 else 1.0
            forecast = np.array([
                base + slope * (i + 1) * (0.85 ** i)
                for i in range(n_steps)
            ])
            return np.clip(forecast, 0.0, max_hist * 3.0)

    def _fit_ridge(
        self,
        df: pd.DataFrame,
        y: np.ndarray,
        n_steps: int,
    ) -> tuple[np.ndarray, dict[str, float]]:
        """Base estimator 2: Ridge Regression on lag/trend features."""
        feature_cols = [
            "lag1",
            "lag2",
            "lag3",
            "ma3",
            "ma5",
            "trends_score",
            "schulferien",
            "roc",
            "lab_positivity_rate",
            "lab_signal_available",
            "lab_baseline_mean",
            "lab_baseline_zscore",
        ]
        available = [c for c in feature_cols if c in df.columns]

        if len(available) < 2:
            return np.full(n_steps, y[-1]), {}

        try:
            X = df[available].values
            ridge = Ridge(alpha=1.0)
            ridge.fit(X, y)

            forecast: list[float] = []
            last_row = df[available].iloc[-1].values.copy()
            last_vals = list(y[-5:])

            for _ in range(n_steps):
                pred = float(ridge.predict(last_row.reshape(1, -1))[0])
                forecast.append(pred)
                last_vals.append(pred)
                if "lag1" in available:
                    last_row[available.index("lag1")] = pred
                if "lag2" in available:
                    last_row[available.index("lag2")] = last_vals[-2] if len(last_vals) >= 2 else pred
                if "lag3" in available:
                    last_row[available.index("lag3")] = last_vals[-3] if len(last_vals) >= 3 else pred
                if "ma3" in available:
                    last_row[available.index("ma3")] = np.mean(last_vals[-3:])
                if "ma5" in available:
                    last_row[available.index("ma5")] = np.mean(last_vals[-5:])
                if "roc" in available:
                    prev = last_vals[-2] if len(last_vals) >= 2 else 1.0
                    last_row[available.index("roc")] = (pred - prev) / prev if prev != 0 else 0.0

            importance: dict[str, float] = {}
            total_abs = float(np.sum(np.abs(ridge.coef_))) + 1e-9
            for fname, coef in zip(available, ridge.coef_):
                importance[fname] = round(abs(float(coef)) / total_abs, 3)

            return np.array(forecast), importance
        except Exception as e:
            logger.warning(f"Ridge regression failed: {e}")
            return np.full(n_steps, y[-1]), {}

    def _fit_prophet(
        self,
        virus_typ: str,
        n_steps: int,
    ) -> np.ndarray | None:
        """Base estimator 3: Facebook Prophet with regressors."""
        try:
            from app.services.fusion_engine.prophet_predictor import ProphetPredictor

            predictor = ProphetPredictor(self.db)
            result = predictor.fit_and_predict(
                virus_typ=virus_typ,
                forecast_days=n_steps,
            )

            if result and "forecast" in result and result["forecast"]:
                preds = [max(0.0, item["yhat"]) for item in result["forecast"]]
                return np.array(preds[:n_steps])
        except Exception as e:
            logger.warning(f"Prophet failed for {virus_typ}: {e}")

        return None

    @staticmethod
    def _direct_ridge_feature_columns(frame: pd.DataFrame) -> list[str]:
        return [column for column in RIDGE_DIRECT_FEATURES if column in frame.columns]

    @staticmethod
    def _event_feature_columns(frame: pd.DataFrame) -> list[str]:
        columns: list[str] = []
        if "current_y" in frame.columns:
            columns.append("current_y")
        for name in META_FEATURES:
            if name in frame.columns and name not in columns:
                columns.append(name)
        if "horizon_days" in frame.columns and "horizon_days" not in columns:
            columns.append("horizon_days")
        return columns

    @staticmethod
    def _build_live_event_feature_row(
        *,
        raw: pd.DataFrame,
        live_feature_row: dict[str, float],
        horizon_days: int,
    ) -> dict[str, float]:
        feature_row = dict(live_feature_row)
        feature_row["current_y"] = float(raw["y"].iloc[-1]) if not raw.empty else 0.0
        feature_row["horizon_days"] = float(horizon_days)
        return feature_row

    @staticmethod
    def _event_model_candidates() -> list[str]:
        candidates = ["logistic_regression"]
        try:
            from xgboost import XGBClassifier  # noqa: F401

            candidates.append("xgb_classifier")
        except Exception:
            pass
        return candidates

    @staticmethod
    def _fit_event_classifier_model(
        train_df: pd.DataFrame,
        *,
        feature_names: list[str],
        model_family: str,
    ) -> Any:
        X_train = train_df[feature_names].to_numpy(dtype=float)
        y_train = train_df["event_target"].to_numpy(dtype=int)
        positives = int(np.sum(y_train == 1))
        negatives = int(np.sum(y_train == 0))
        if min(positives, negatives) <= 0:
            return EmpiricalEventClassifier(float(np.mean(y_train) if len(y_train) else 0.0))

        if model_family == "xgb_classifier":
            from xgboost import XGBClassifier

            config = dict(DEFAULT_EVENT_CLASSIFIER_CONFIG)
            config["scale_pos_weight"] = float(negatives / max(positives, 1))
            model = XGBClassifier(**config)
            model.fit(X_train, y_train)
            return model

        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        solver="lbfgs",
                    ),
                ),
            ]
        )
        model.fit(X_train, y_train)
        return model

    def _build_event_oof_predictions(
        self,
        panel: pd.DataFrame,
        *,
        feature_names: list[str],
        model_family: str,
        walk_forward_stride: int = DEFAULT_WALK_FORWARD_STRIDE,
        max_splits: int | None = None,
        min_train_points: int = max(MIN_DIRECT_TRAIN_POINTS, 24),
    ) -> pd.DataFrame:
        splits = build_walk_forward_splits(
            len(panel),
            min_train_points=min_train_points,
            stride=walk_forward_stride,
            max_splits=max_splits,
        )
        if not splits:
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for fold_idx, split in enumerate(splits, start=1):
            train_df = panel.iloc[: split.train_end_idx].copy()
            test_df = panel.iloc[[split.test_idx]].copy()
            if len(train_df) < min_train_points or test_df.empty:
                continue
            if train_df["event_target"].nunique() < 2:
                raw_prob = np.full(len(test_df), float(train_df["event_target"].mean() or 0.0), dtype=float)
            else:
                model = self._fit_event_classifier_model(
                    train_df,
                    feature_names=feature_names,
                    model_family=model_family,
                )
                raw_prob = np.asarray(
                    model.predict_proba(test_df[feature_names].to_numpy(dtype=float))[:, 1],
                    dtype=float,
                )
            frames.append(
                pd.DataFrame(
                    {
                        "fold": fold_idx,
                        "issue_date": pd.to_datetime(test_df["issue_date"]).dt.normalize().values,
                        "target_date": pd.to_datetime(test_df["target_date"]).dt.normalize().values,
                        "event_target": test_df["event_target"].to_numpy(dtype=int),
                        "event_probability_raw": np.clip(raw_prob, 0.001, 0.999),
                    }
                )
            )

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _select_best_event_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        valid = [
            candidate
            for candidate in candidates
            if isinstance(candidate.get("oof_frame"), pd.DataFrame) and not candidate["oof_frame"].empty
        ]
        if not valid:
            return None
        return min(
            valid,
            key=lambda item: (
                float((item.get("raw_metrics") or {}).get("logloss", float("inf"))),
                float((item.get("raw_metrics") or {}).get("brier_score", float("inf"))),
                -float((item.get("raw_metrics") or {}).get("pr_auc", float("-inf"))),
                -float((item.get("raw_metrics") or {}).get("sample_count", 0.0)),
                str(item.get("model_family") or ""),
            ),
        )

    def _build_event_probability_model_from_panel(
        self,
        panel: pd.DataFrame,
        *,
        walk_forward_stride: int = DEFAULT_WALK_FORWARD_STRIDE,
        max_splits: int | None = None,
    ) -> dict[str, Any]:
        if panel.empty or "event_target" not in panel.columns:
            prevalence = float(panel["event_target"].mean()) if "event_target" in panel.columns and not panel.empty else 0.0
            fallback_model = LearnedProbabilityModel(
                classifier=EmpiricalEventClassifier(prevalence),
                feature_names=[],
                model_family="empirical_prevalence",
                calibration=None,
                calibration_mode="raw_probability",
                probability_source="empirical_event_prevalence",
                fallback_reason="event_training_panel_empty",
                metadata={"prevalence": round(prevalence, 6)},
            )
            return {
                "model": fallback_model,
                "model_family": "empirical_prevalence",
                "feature_names": [],
                "calibration_mode": "raw_probability",
                "probability_source": "empirical_event_prevalence",
                "fallback_reason": "event_training_panel_empty",
                "oof_frame": pd.DataFrame(),
                "raw_metrics": {
                    "prevalence": round(prevalence, 6),
                    "sample_count": float(len(panel)),
                    "positive_count": float(np.sum(panel["event_target"] == 1)) if "event_target" in panel.columns else 0.0,
                    "negative_count": float(np.sum(panel["event_target"] == 0)) if "event_target" in panel.columns else 0.0,
                },
                "calibrated_metrics": {},
                "reliability_metrics": {},
                "reliability_source": "unavailable",
                "reliability_score": None,
            }

        feature_names = self._event_feature_columns(panel)
        if not feature_names:
            prevalence = float(panel["event_target"].mean() or 0.0)
            fallback_model = LearnedProbabilityModel(
                classifier=EmpiricalEventClassifier(prevalence),
                feature_names=[],
                model_family="empirical_prevalence",
                calibration=None,
                calibration_mode="raw_probability",
                probability_source="empirical_event_prevalence",
                fallback_reason="event_feature_columns_missing",
                metadata={"prevalence": round(prevalence, 6)},
            )
            return {
                "model": fallback_model,
                "model_family": "empirical_prevalence",
                "feature_names": [],
                "calibration_mode": "raw_probability",
                "probability_source": "empirical_event_prevalence",
                "fallback_reason": "event_feature_columns_missing",
                "oof_frame": pd.DataFrame(),
                "raw_metrics": {
                    "prevalence": round(prevalence, 6),
                    "sample_count": float(len(panel)),
                    "positive_count": float(np.sum(panel["event_target"] == 1)),
                    "negative_count": float(np.sum(panel["event_target"] == 0)),
                },
                "calibrated_metrics": {},
                "reliability_metrics": {},
                "reliability_source": "unavailable",
                "reliability_score": None,
            }

        candidate_payloads: list[dict[str, Any]] = []
        min_train_points = max(MIN_DIRECT_TRAIN_POINTS, 24)
        for model_family in self._event_model_candidates():
            oof_frame = self._build_event_oof_predictions(
                panel,
                feature_names=feature_names,
                model_family=model_family,
                walk_forward_stride=walk_forward_stride,
                max_splits=max_splits,
                min_train_points=min_train_points,
            )
            if oof_frame.empty:
                continue
            raw_metrics = compute_classification_metrics(
                oof_frame["event_probability_raw"].to_numpy(dtype=float),
                oof_frame["event_target"].to_numpy(dtype=int),
            )
            candidate_payloads.append(
                {
                    "model_family": model_family,
                    "feature_names": feature_names,
                    "oof_frame": oof_frame,
                    "raw_metrics": raw_metrics,
                }
            )

        selected = self._select_best_event_candidate(candidate_payloads)
        if selected is None:
            prevalence = float(panel["event_target"].mean() or 0.0)
            fallback_model = LearnedProbabilityModel(
                classifier=EmpiricalEventClassifier(prevalence),
                feature_names=feature_names,
                model_family="empirical_prevalence",
                calibration=None,
                calibration_mode="raw_probability",
                probability_source="empirical_event_prevalence",
                fallback_reason="insufficient_valid_event_oof_rows",
                metadata={"prevalence": round(prevalence, 6)},
            )
            fallback_metrics = compute_classification_metrics(
                np.full(len(panel), prevalence, dtype=float),
                panel["event_target"].to_numpy(dtype=int),
            )
            return {
                "model": fallback_model,
                "model_family": "empirical_prevalence",
                "feature_names": feature_names,
                "calibration_mode": "raw_probability",
                "probability_source": "empirical_event_prevalence",
                "fallback_reason": "insufficient_valid_event_oof_rows",
                "oof_frame": pd.DataFrame(),
                "raw_metrics": fallback_metrics,
                "calibrated_metrics": fallback_metrics,
                "reliability_metrics": fallback_metrics,
                "reliability_source": "oof_full_sample",
                "reliability_score": reliability_score_from_metrics(fallback_metrics),
            }

        calibration_payload = select_probability_calibration(
            selected["oof_frame"][["issue_date", "event_target", "event_probability_raw"]].rename(
                columns={"issue_date": "as_of_date", "event_target": "event_label"}
            ),
            raw_probability_col="event_probability_raw",
            label_col="event_label",
            date_col="as_of_date",
        )
        # Guarded selection happens inside select_probability_calibration(). If a
        # calibrator hurts the later temporal guard slice, we stay on raw_probability.
        calibration = calibration_payload.get("calibration")
        calibrated_probs = apply_probability_calibration(
            calibration,
            selected["oof_frame"]["event_probability_raw"].to_numpy(dtype=float),
        )
        calibrated_metrics = compute_classification_metrics(
            calibrated_probs,
            selected["oof_frame"]["event_target"].to_numpy(dtype=int),
        )
        oof_frame = selected["oof_frame"].copy()
        oof_frame["event_probability_calibrated"] = calibrated_probs

        if panel["event_target"].nunique() < 2:
            final_classifier = EmpiricalEventClassifier(float(panel["event_target"].mean() or 0.0))
        else:
            final_classifier = self._fit_event_classifier_model(
                panel,
                feature_names=feature_names,
                model_family=str(selected["model_family"]),
            )

        probability_source = f"learned_exceedance_{selected['model_family']}"
        model = LearnedProbabilityModel(
            classifier=final_classifier,
            feature_names=list(feature_names),
            model_family=str(selected["model_family"]),
            calibration=calibration,
            calibration_mode=str(calibration_payload.get("calibration_mode") or "raw_probability"),
            probability_source=probability_source,
            fallback_reason=calibration_payload.get("fallback_reason"),
            metadata={
                "oof_row_count": int(len(oof_frame)),
                "raw_metrics": selected["raw_metrics"],
                "calibrated_metrics": calibrated_metrics,
                "reliability_metrics": calibration_payload.get("reliability_metrics") or calibrated_metrics,
                "reliability_source": calibration_payload.get("reliability_source"),
            },
        )
        reliability_metrics = calibration_payload.get("reliability_metrics") or calibrated_metrics
        return {
            "model": model,
            "model_family": str(selected["model_family"]),
            "feature_names": list(feature_names),
            "calibration_mode": str(calibration_payload.get("calibration_mode") or "raw_probability"),
            "probability_source": probability_source,
            "fallback_reason": calibration_payload.get("fallback_reason"),
            "oof_frame": oof_frame,
            "raw_metrics": selected["raw_metrics"],
            "calibrated_metrics": calibrated_metrics,
            "reliability_metrics": reliability_metrics,
            "reliability_source": calibration_payload.get("reliability_source"),
            "reliability_score": reliability_score_from_metrics(reliability_metrics),
        }

    def build_direct_training_panel(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        region: str = DEFAULT_FORECAST_REGION,
        include_internal_history: bool = True,
        lookback_days: int = 900,
        n_splits: int = 5,
    ) -> pd.DataFrame:
        horizon = ensure_supported_horizon(horizon_days)
        raw = self.prepare_training_data(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            include_internal_history=include_internal_history,
            region=region,
        )
        return self._build_direct_training_panel_from_frame(
            raw,
            horizon_days=horizon,
            n_splits=n_splits,
        )

    def _build_direct_training_panel_from_frame(
        self,
        raw: pd.DataFrame,
        *,
        horizon_days: int,
        n_splits: int = 5,
    ) -> pd.DataFrame:
        horizon = ensure_supported_horizon(horizon_days)
        direct = build_direct_target_frame(raw, horizon_days=horizon)
        if direct.empty:
            return direct

        prophet_proxy = (
            direct["current_y"]
            .rolling(window=7, min_periods=1)
            .mean()
            .shift(1)
        )
        # Keep this fallback causal: the direct panel predicts a future target, so
        # current_y is known at issue time, but any backward fill from later rows would leak.
        direct["prophet_pred"] = prophet_proxy.fillna(direct["current_y"]).astype(float)

        oof = pd.DataFrame(index=direct.index, columns=["hw_pred", "ridge_pred"], dtype=float)
        feature_cols = self._direct_ridge_feature_columns(direct)
        n_time_splits = min(max(2, int(n_splits)), max(len(direct) // 8, 2))

        try:
            tscv = TimeSeriesSplit(n_splits=n_time_splits)
            split_iter = list(tscv.split(direct))
        except ValueError:
            split_iter = []

        for train_idx, val_idx in split_iter:
            if len(train_idx) < max(MIN_DIRECT_TRAIN_POINTS, 12) or len(val_idx) < 1:
                continue

            train_panel = direct.iloc[train_idx].copy()
            val_panel = direct.iloc[val_idx].copy()

            if feature_cols:
                ridge = Ridge(alpha=1.0)
                ridge.fit(
                    train_panel[feature_cols].to_numpy(dtype=float),
                    train_panel["y_target"].to_numpy(dtype=float),
                )
                ridge_preds = np.maximum(
                    ridge.predict(val_panel[feature_cols].to_numpy(dtype=float)),
                    0.0,
                )
                oof.loc[val_idx, "ridge_pred"] = ridge_preds

            for idx in val_idx:
                issue_date = pd.Timestamp(direct.iloc[idx]["issue_date"])
                history = raw.loc[raw["ds"] <= issue_date, "y"].to_numpy(dtype=float)
                if len(history) == 0:
                    oof.loc[idx, "hw_pred"] = 0.0
                    continue
                hw_forecast = self._fit_holt_winters(history, horizon)
                hw_step = min(horizon - 1, max(len(hw_forecast) - 1, 0))
                oof.loc[idx, "hw_pred"] = max(0.0, float(hw_forecast[hw_step]))

        # Never backward-fill OOF features: that would copy later fold predictions
        # into earlier issue dates and create a hidden temporal leak.
        causal_oof_fallback = direct["current_y"].astype(float)
        direct["hw_pred"] = (
            oof["hw_pred"]
            .ffill()
            .fillna(causal_oof_fallback)
            .astype(float)
        )
        direct["ridge_pred"] = (
            oof["ridge_pred"]
            .ffill()
            .fillna(causal_oof_fallback)
            .astype(float)
        )
        direct = direct.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return direct.reset_index(drop=True)

    def _build_live_direct_feature_row(
        self,
        raw: pd.DataFrame,
        *,
        virus_typ: str,
        horizon_days: int,
        region: str = DEFAULT_FORECAST_REGION,
    ) -> dict[str, float]:
        horizon = ensure_supported_horizon(horizon_days)
        if raw.empty:
            return {}

        last_row = raw.iloc[-1].copy()
        history = raw["y"].to_numpy(dtype=float)
        hw_forecast = self._fit_holt_winters(history, horizon)
        hw_pred = max(0.0, float(hw_forecast[min(horizon - 1, max(len(hw_forecast) - 1, 0))]))

        direct_train = build_direct_target_frame(raw, horizon_days=horizon)
        feature_cols = self._direct_ridge_feature_columns(direct_train) if not direct_train.empty else []
        if feature_cols and len(direct_train) >= max(MIN_DIRECT_TRAIN_POINTS, 12):
            ridge = Ridge(alpha=1.0)
            ridge.fit(
                direct_train[feature_cols].to_numpy(dtype=float),
                direct_train["y_target"].to_numpy(dtype=float),
            )
            ridge_row = np.array([[float(last_row.get(name, 0.0)) for name in feature_cols]], dtype=float)
            ridge_pred = max(0.0, float(ridge.predict(ridge_row)[0]))
        else:
            ridge_pred = max(0.0, float(last_row.get("y", 0.0)))

        prophet_forecast = self._fit_prophet(virus_typ, horizon) if normalize_forecast_region(region) == DEFAULT_FORECAST_REGION else None
        if prophet_forecast is not None and len(prophet_forecast) >= horizon:
            prophet_pred = max(0.0, float(prophet_forecast[horizon - 1]))
        else:
            prophet_pred = float(
                raw["y"]
                .tail(min(7, len(raw)))
                .mean()
            )

        feature_row = self._build_meta_feature_row(
            last_row,
            hw_pred=hw_pred,
            ridge_pred=ridge_pred,
            prophet_pred=prophet_pred,
        )
        feature_row["horizon_days"] = float(horizon)
        return feature_row

    def _fit_xgboost_meta_from_panel(
        self,
        panel: pd.DataFrame,
        *,
        target_column: str = "y_target",
        model_config: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[Any, Any, Any, list[str], dict[str, float]]:
        from xgboost import XGBRegressor

        available_meta = [f for f in META_FEATURES if f in panel.columns]
        if "horizon_days" in panel.columns and "horizon_days" not in available_meta:
            available_meta.append("horizon_days")
        if not available_meta:
            raise ValueError("No direct meta features available for XGBoost fitting.")

        X = panel[available_meta].to_numpy(dtype=float)
        y = panel[target_column].to_numpy(dtype=float)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        cfg = self._resolve_xgb_quantile_config(model_config)

        model_median = XGBRegressor(**cfg["median"])
        model_median.fit(X, y)

        model_lower = XGBRegressor(**cfg["lower"])
        model_lower.fit(X, y)

        model_upper = XGBRegressor(**cfg["upper"])
        model_upper.fit(X, y)

        importance_raw = model_median.feature_importances_
        total = float(np.sum(importance_raw)) + 1e-9
        feature_importance = {
            fname: round(float(imp) / total, 3)
            for fname, imp in zip(available_meta, importance_raw)
        }
        return model_median, model_lower, model_upper, available_meta, feature_importance

    # ═══════════════════════════════════════════════════════════════════
    #  XGBOOST META-LEARNER
    # ═══════════════════════════════════════════════════════════════════

    def _generate_oof_predictions(
        self,
        df: pd.DataFrame,
        n_splits: int = 5,
    ) -> pd.DataFrame:
        """Generate out-of-fold predictions from base estimators using TimeSeriesSplit.

        For each fold, HW and Ridge are trained on the train split and
        predicted on the validation split. Prophet predictions are estimated
        from the last known training values (simplified — Prophet is expensive).
        """
        y = df["y"].values
        tscv = TimeSeriesSplit(n_splits=n_splits)

        oof = pd.DataFrame(index=df.index, columns=["hw_pred", "ridge_pred"], dtype=float)
        oof[:] = np.nan

        for train_idx, val_idx in tscv.split(df):
            if len(train_idx) < 10 or len(val_idx) < 1:
                continue

            y_train = y[train_idx]
            n_val = len(val_idx)

            # HW
            hw_preds = self._fit_holt_winters(y_train, n_val)
            oof.loc[val_idx, "hw_pred"] = hw_preds[:n_val]

            # Ridge
            df_train = df.iloc[train_idx]
            ridge_preds, _ = self._fit_ridge(df_train, y_train, n_val)
            oof.loc[val_idx, "ridge_pred"] = ridge_preds[:n_val]

        history_series = pd.Series(y, index=df.index, dtype=float).ffill()
        causal_history_fallback = history_series.shift(1).fillna(0.0)

        # Keep OOF fallback strictly historical: no backward fill and never use
        # the final series value, because both would leak future information.
        oof["hw_pred"] = oof["hw_pred"].ffill().fillna(causal_history_fallback).astype(float)
        oof["ridge_pred"] = oof["ridge_pred"].ffill().fillna(causal_history_fallback).astype(float)

        return oof

    def _fit_xgboost_meta(
        self,
        df: pd.DataFrame,
        oof: pd.DataFrame,
        model_config: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[Any, Any, Any, dict[str, float]]:
        """Train XGBoost meta-learner with quantile regression (asymmetric loss).

        Returns (model_median, model_lower, model_upper, feature_importance).
        """
        from xgboost import XGBRegressor

        # Merge OOF predictions into feature DataFrame
        df_meta = df.copy()
        df_meta["hw_pred"] = oof["hw_pred"].values
        df_meta["ridge_pred"] = oof["ridge_pred"].values
        # Prophet OOF proxy: 7-day rolling mean shifted by forecast horizon (14d)
        # to prevent target leakage during training.  With shift(1) the rolling
        # window contained data the model wouldn't have at prediction time.
        df_meta["prophet_pred"] = df_meta["y"].rolling(window=7, min_periods=1).mean().shift(14)

        # Build feature matrix
        available_meta = [f for f in META_FEATURES if f in df_meta.columns]
        X = df_meta[available_meta].values
        y = df_meta["y"].values

        # Replace any remaining NaN/inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        cfg = self._resolve_xgb_quantile_config(model_config)

        # ── Median model (main prediction — 50th percentile) ──
        model_median = XGBRegressor(**cfg["median"])
        model_median.fit(X, y)

        # ── Lower bound (10th percentile) ──
        model_lower = XGBRegressor(**cfg["lower"])
        model_lower.fit(X, y)

        # ── Upper bound (90th percentile) ──
        model_upper = XGBRegressor(**cfg["upper"])
        model_upper.fit(X, y)

        # Feature importance from median model
        importance_raw = model_median.feature_importances_
        total = float(np.sum(importance_raw)) + 1e-9
        feature_importance = {
            fname: round(float(imp) / total, 3)
            for fname, imp in zip(available_meta, importance_raw)
        }

        logger.info(f"XGBoost meta-learner trained on {len(y)} samples, {len(available_meta)} features")
        return model_median, model_lower, model_upper, feature_importance

    @staticmethod
    def _resolve_xgb_quantile_config(
        model_config: dict[str, dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        resolved = {name: params.copy() for name, params in DEFAULT_XGB_QUANTILE_CONFIG.items()}
        if not model_config:
            return resolved

        for name, overrides in model_config.items():
            if name in resolved and overrides:
                resolved[name].update(overrides)
        return resolved

    def evaluate_training_candidate(
        self,
        virus_typ: str,
        *,
        include_internal_history: bool = True,
        model_config: dict[str, dict[str, Any]] | None = None,
        n_windows: int | None = None,
        walk_forward_stride: int = DEFAULT_WALK_FORWARD_STRIDE,
        max_splits: int | None = None,
        region: str = DEFAULT_FORECAST_REGION,
        horizon_days: int = DEFAULT_DECISION_HORIZON_DAYS,
    ) -> dict[str, Any]:
        """Run a deterministic walk-forward backtest for direct horizon promotion."""
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        effective_max_splits = int(max_splits) if max_splits is not None else (
            int(n_windows) if n_windows is not None else None
        )
        df = self.prepare_training_data(
            virus_typ=virus_typ,
            include_internal_history=include_internal_history,
            region=region_code,
        )

        panel = self._build_direct_training_panel_from_frame(
            df,
            horizon_days=horizon,
            n_splits=max(int(effective_max_splits or 5), 3),
        )

        if panel.empty or len(panel) < max(MIN_DIRECT_TRAIN_POINTS, 24):
            return {
                "error": f"Insufficient training data ({len(panel) if not panel.empty else 0} rows)",
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
                "include_internal_history": include_internal_history,
            }

        predictions: list[float] = []
        predictions_lo: list[float] = []
        predictions_hi: list[float] = []
        baseline_predictions: list[float] = []
        baseline_predictions_lo: list[float] = []
        baseline_predictions_hi: list[float] = []
        actuals: list[float] = []
        labels: list[float] = []
        windows: list[dict[str, Any]] = []
        event_bundle = self._build_event_probability_model_from_panel(
            panel,
            walk_forward_stride=walk_forward_stride,
            max_splits=effective_max_splits,
        )
        event_oof = event_bundle.get("oof_frame")
        probability_by_issue_date = {}
        if isinstance(event_oof, pd.DataFrame) and not event_oof.empty:
            ordered_event_oof = event_oof.sort_values("issue_date").drop_duplicates("issue_date", keep="last")
            probability_by_issue_date = {
                pd.Timestamp(row["issue_date"]).normalize(): float(row["event_probability_calibrated"])
                for _, row in ordered_event_oof.iterrows()
            }
        splits = build_walk_forward_splits(
            len(panel),
            min_train_points=max(MIN_DIRECT_TRAIN_POINTS, 24),
            stride=walk_forward_stride,
            max_splits=effective_max_splits,
        )
        for fold, split in enumerate(splits, start=1):
            train_panel = panel.iloc[: split.train_end_idx].copy()
            test_panel = panel.iloc[[split.test_idx]].copy()
            if len(train_panel) < max(MIN_DIRECT_TRAIN_POINTS, 24) or test_panel.empty:
                continue

            model_med, model_lo, model_hi, feature_names, _ = self._fit_xgboost_meta_from_panel(
                train_panel,
                target_column="y_target",
                model_config=model_config,
            )
            X_test = test_panel[feature_names].to_numpy(dtype=float)
            X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

            pred = max(0.0, float(model_med.predict(X_test)[0]))
            pred_lo = max(0.0, float(model_lo.predict(X_test)[0]))
            pred_hi = max(0.0, float(model_hi.predict(X_test)[0]))
            actual = float(test_panel.iloc[0]["y_target"])
            current = max(float(test_panel.iloc[0]["current_y"]), 1.0)
            persistence_scale = max(float(np.std(train_panel["y_target"].to_numpy(dtype=float))) if len(train_panel) > 1 else 1.0, 1.0)
            issue_date_value = pd.Timestamp(test_panel.iloc[0]["issue_date"]).normalize()
            event_probability = probability_by_issue_date.get(issue_date_value)
            if event_probability is None:
                event_probability = float(event_bundle.get("calibrated_metrics", {}).get("prevalence") or 0.0)

            predictions.append(pred)
            predictions_lo.append(pred_lo)
            predictions_hi.append(pred_hi)
            baseline_predictions.append(current)
            baseline_predictions_lo.append(max(current - persistence_scale, 0.0))
            baseline_predictions_hi.append(current + persistence_scale)
            actuals.append(actual)
            labels.append(float(test_panel.iloc[0]["event_target"]))
            windows.append(
                {
                    "fold": fold,
                    "issue_date": issue_date_value.isoformat(),
                    "target_date": pd.Timestamp(test_panel.iloc[0]["target_date"]).isoformat(),
                    "predicted": round(pred, 4),
                    "actual": round(actual, 4),
                    "event_probability": round(float(event_probability), 4),
                }
            )

        if not predictions:
            return {
                "error": "No validation windows available",
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
                "include_internal_history": include_internal_history,
            }

        metrics = compute_regression_metrics(predictions, actuals)
        event_probabilities = [float(item["event_probability"]) for item in windows]
        metrics.update(compute_classification_metrics(event_probabilities, labels))
        metrics.update(
            summarize_probabilistic_metrics(
                y_true=actuals,
                quantile_predictions={
                    0.1: predictions_lo,
                    0.5: predictions,
                    0.9: predictions_hi,
                },
                baseline_quantiles={
                    0.1: baseline_predictions_lo,
                    0.5: baseline_predictions,
                    0.9: baseline_predictions_hi,
                },
                event_labels=labels,
                event_probabilities=event_probabilities,
                action_threshold=0.5,
            )
        )
        metrics["windows"] = windows
        metrics["window_count"] = len(windows)
        metrics["horizon_days"] = horizon
        metrics["region"] = region_code
        metrics["training_window"] = {
            "start": df["ds"].min().isoformat(),
            "end": df["ds"].max().isoformat(),
            "samples": int(len(df)),
            "panel_rows": int(len(panel)),
        }
        metrics["walk_forward"] = {
            "enabled": True,
            "folds": len(windows),
            "min_train_points": max(MIN_DIRECT_TRAIN_POINTS, 24),
            "horizon_days": horizon,
            "region": region_code,
            "strategy": "direct",
            "stride": max(int(walk_forward_stride), 1),
            "max_splits": effective_max_splits,
        }
        metrics["probability_source"] = event_bundle.get("probability_source")
        metrics["event_model_family"] = event_bundle.get("model_family")
        metrics["calibration_mode"] = event_bundle.get("calibration_mode")
        metrics["fallback_reason"] = event_bundle.get("fallback_reason")
        metrics["reliability_metrics"] = event_bundle.get("reliability_metrics") or {}
        metrics["reliability_source"] = event_bundle.get("reliability_source")
        metrics["reliability_score"] = event_bundle.get("reliability_score")
        metrics["include_internal_history"] = include_internal_history
        return metrics

    @staticmethod
    def _compute_regression_metrics(
        predicted: list[float],
        actual: list[float],
    ) -> dict[str, float]:
        pred_arr = np.asarray(predicted, dtype=float)
        act_arr = np.asarray(actual, dtype=float)
        errors = pred_arr - act_arr
        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        nonzero = act_arr != 0
        mape = float(np.mean(np.abs(errors[nonzero] / act_arr[nonzero])) * 100) if nonzero.any() else 0.0
        return {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 2),
        }

    @staticmethod
    def _backtest_quality_score(backtest_metrics: dict[str, Any] | None) -> float | None:
        if not backtest_metrics:
            return None
        mape = backtest_metrics.get("mape")
        if mape is None:
            return None
        return round(max(0.0, min(1.0, 1.0 - (float(mape) / 100.0))), 4)

    @staticmethod
    def _calibration_passed(backtest_metrics: dict[str, Any] | None) -> bool | None:
        if not backtest_metrics:
            return None
        brier = backtest_metrics.get("brier_score")
        ece = backtest_metrics.get("ece")
        logloss_value = backtest_metrics.get("logloss")
        checks: list[bool] = []
        if brier is not None:
            checks.append(float(brier) <= 0.25)
        if ece is not None:
            checks.append(float(ece) <= 0.10)
        if logloss_value is not None:
            checks.append(float(logloss_value) <= 0.70)
        if not checks:
            return None
        return all(checks)

    def _quality_meta_from_backtest(
        self,
        *,
        backtest_metrics: dict[str, Any] | None,
        event_probability: float | None,
        probability_source: str,
        calibration_mode: str,
        fallback_reason: str | None = None,
        learned_model_version: str | None = None,
        forecast_ready: bool,
        drift_status: str,
        baseline_deltas: dict[str, Any] | None = None,
        timing_metrics: dict[str, Any] | None = None,
        interval_coverage: dict[str, Any] | None = None,
        promotion_gate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metrics = dict(backtest_metrics or {})
        reliability_score = metrics.get("reliability_score")
        if reliability_score is None:
            reliability_score = reliability_score_from_metrics(
                metrics,
                coverage_metrics=metrics,
            )
        return {
            "event_probability": event_probability,
            "forecast_ready": forecast_ready,
            "drift_status": drift_status,
            "baseline_deltas": baseline_deltas or {},
            "timing_metrics": timing_metrics or {},
            "interval_coverage": interval_coverage or {},
            "promotion_gate": promotion_gate or {},
            "confidence": reliability_score,
            "reliability_score": reliability_score,
            "confidence_semantics": CONFIDENCE_SEMANTICS_ALIAS,
            "backtest_quality_score": self._backtest_quality_score(metrics),
            "brier_score": metrics.get("brier_score"),
            "ece": metrics.get("ece"),
            "calibration_passed": self._calibration_passed(metrics),
            "probability_source": probability_source,
            "calibration_mode": calibration_mode,
            "calibration_method": f"{probability_source}:{calibration_mode}",
            # This is not per-forecast predictive uncertainty. It only tells the
            # consumer that the score comes from backtest reliability evidence.
            "uncertainty_source": BACKTEST_RELIABILITY_PROXY_SOURCE,
            "fallback_reason": fallback_reason,
            "learned_model_version": learned_model_version,
            "fallback_used": fallback_reason is not None,
        }

    def _compute_outbreak_risk(
        self,
        prediction: float,
        y_history: np.ndarray,
        window: int = 30,
    ) -> float:
        """Compute outbreak risk score (0.0 – 1.0) via z-score sigmoid."""
        recent = y_history[-min(window, len(y_history)) :]
        mean_val = float(np.mean(recent))
        std_val = float(np.std(recent))
        if std_val < 1e-9:
            return 0.5
        z = (prediction - mean_val) / std_val
        return round(_sigmoid(z), 3)

    def _build_contracts(
        self,
        *,
        virus_typ: str,
        region: str,
        horizon_days: int,
        forecast_records: list[dict[str, Any]],
        model_version: str,
        y_history: np.ndarray,
        issue_date: datetime | None = None,
        quality_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        issue_ts = issue_date or utc_now()
        burden = BurdenForecast(
            target=virus_typ,
            region=region_code,
            issue_date=issue_ts.isoformat(),
            horizon_days=horizon,
            model_version=model_version,
            points=[
                BurdenForecastPoint(
                    target_date=item["ds"].isoformat() if item.get("ds") else "",
                    median=float(item.get("yhat") or 0.0),
                    lower=(
                        float(item["yhat_lower"])
                        if item.get("yhat_lower") is not None
                        else None
                    ),
                    upper=(
                        float(item["yhat_upper"])
                        if item.get("yhat_upper") is not None
                        else None
                    ),
                )
                for item in forecast_records
            ],
        )

        baseline = float(np.median(y_history[-min(len(y_history), 84) :])) if len(y_history) > 0 else 0.0
        event_probability = quality_meta.get("event_probability") if quality_meta else None
        reliability_score = (
            quality_meta.get("reliability_score")
            if quality_meta and quality_meta.get("reliability_score") is not None
            else (quality_meta.get("confidence") if quality_meta else None)
        )
        confidence_value = reliability_score
        backtest_quality_score = quality_meta.get("backtest_quality_score") if quality_meta else None
        calibration_mode = (quality_meta.get("calibration_mode") if quality_meta else None) or "raw_probability"
        probability_source = (quality_meta.get("probability_source") if quality_meta else None) or "empirical_event_prevalence"
        fallback_reason = quality_meta.get("fallback_reason") if quality_meta else None
        event = EventForecast(
            event_key=f"{virus_typ.lower().replace(' ', '_')}_growth_h{horizon}",
            horizon_days=horizon,
            event_probability=event_probability,
            threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            baseline_value=round(baseline, 3) if baseline > 0 else None,
            threshold_value=round(baseline * 1.25, 3) if baseline > 0 else None,
            calibration_method=(quality_meta.get("calibration_method") if quality_meta else None)
            or f"{probability_source}:{calibration_mode}",
            brier_score=quality_meta.get("brier_score") if quality_meta else None,
            ece=quality_meta.get("ece") if quality_meta else None,
            calibration_passed=quality_meta.get("calibration_passed") if quality_meta else None,
            confidence=confidence_value,
            confidence_label=(
                confidence_label(confidence_value)
                if confidence_value is not None
                else None
            ),
            reliability_score=reliability_score,
            backtest_quality_score=backtest_quality_score,
            probability_source=probability_source,
            calibration_mode=calibration_mode,
            uncertainty_source=(
                (quality_meta.get("uncertainty_source") if quality_meta else None)
                or BACKTEST_RELIABILITY_PROXY_SOURCE
            ),
            confidence_semantics=(
                (quality_meta.get("confidence_semantics") if quality_meta else None)
                or CONFIDENCE_SEMANTICS_ALIAS
            ),
            fallback_reason=fallback_reason,
            learned_model_version=(quality_meta.get("learned_model_version") if quality_meta else None),
            fallback_used=bool((quality_meta.get("fallback_used") if quality_meta else fallback_reason is not None)),
        )
        forecast_quality = ForecastQuality(
            forecast_readiness="GO" if quality_meta and quality_meta.get("forecast_ready") else "WATCH",
            drift_status=str(quality_meta.get("drift_status") or "unknown") if quality_meta else "unknown",
            freshness_status="fresh",
            baseline_deltas=quality_meta.get("baseline_deltas") or {} if quality_meta else {},
            timing_metrics=quality_meta.get("timing_metrics") or {} if quality_meta else {},
            interval_coverage=quality_meta.get("interval_coverage") or {} if quality_meta else {},
            promotion_gate=quality_meta.get("promotion_gate") or {} if quality_meta else {},
        )
        return {
            "burden_forecast": burden.to_dict(),
            "event_forecast": event.to_dict(),
            "forecast_quality": forecast_quality.to_dict(),
        }

    # ═══════════════════════════════════════════════════════════════════
    #  INFERENCE (loads pre-trained models from disk)
    # ═══════════════════════════════════════════════════════════════════

    def predict(
        self,
        virus_typ: str = "Influenza A",
        *,
        region: str = DEFAULT_FORECAST_REGION,
        horizon_days: int = DEFAULT_DECISION_HORIZON_DAYS,
        include_internal_history: bool = True,
    ) -> dict[str, Any]:
        """Run forecast using pre-trained models from disk.

        Falls back to :meth:`train_and_forecast` when no serialised
        model exists (e.g. fresh deployment before first training).
        """
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        cached = _load_cached_models(
            virus_typ,
            region=region_code,
            horizon_days=horizon,
        )

        if cached is None:
            logger.info(
                f"No pre-trained model found for {virus_typ}/{region_code}/h{horizon}, "
                f"falling back to in-memory train_and_forecast()"
            )
            return self.train_and_forecast(
                virus_typ=virus_typ,
                region=region_code,
                horizon_days=horizon,
                include_internal_history=include_internal_history,
            )

        model_med, model_lo, model_hi, metadata, event_model = cached
        try:
            return self._inference_from_loaded_models(
                virus_typ=virus_typ,
                model_med=model_med,
                model_lo=model_lo,
                model_hi=model_hi,
                metadata=metadata,
                event_model=event_model,
                region=region_code,
                horizon_days=horizon,
                include_internal_history=include_internal_history,
            )
        except Exception as exc:
            if not _is_model_feature_compatibility_error(exc):
                raise

            logger.warning(
                "Cached forecast model for %s/%s/h%s is incompatible with current features (%s). "
                "Falling back to in-memory train_and_forecast().",
                virus_typ,
                region_code,
                horizon,
                exc,
            )
            return self.train_and_forecast(
                virus_typ=virus_typ,
                region=region_code,
                horizon_days=horizon,
                include_internal_history=include_internal_history,
            )

    def _inference_from_loaded_models(
        self,
        virus_typ: str,
        model_med: Any,
        model_lo: Any,
        model_hi: Any,
        metadata: dict[str, Any],
        event_model: LearnedProbabilityModel | None,
        *,
        region: str = DEFAULT_FORECAST_REGION,
        horizon_days: int = DEFAULT_DECISION_HORIZON_DAYS,
        include_internal_history: bool = True,
    ) -> dict[str, Any]:
        """Generate forecast using pre-loaded XGBoost models.

        Mirrors the forecast-generation portion of
        :meth:`train_and_forecast` (Steps 1, 4, 5, 6) but skips
        Steps 2-3 (OOF generation + XGBoost training).
        """
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        logger.info(
            f"=== Inference for {virus_typ}/{region_code}/h{horizon} "
            f"(model={metadata.get('version')}) ==="
        )

        internal_history_enabled = bool(
            metadata.get("data_sources", {}).get("internal_history", include_internal_history)
        )
        df = self.prepare_training_data(
            virus_typ=virus_typ,
            include_internal_history=internal_history_enabled,
            region=region_code,
        )

        if df.empty or len(df) < max(MIN_DIRECT_TRAIN_POINTS, 10):
            logger.error(
                "Insufficient data for inference (%s rows) for %s/%s/h%s",
                len(df),
                virus_typ,
                region_code,
                horizon,
            )
            return {
                "error": "Insufficient data for inference",
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
            }

        y = df["y"].values
        feature_names = list(metadata.get("feature_names") or META_FEATURES)
        live_feature_row = self._build_live_direct_feature_row(
            df,
            virus_typ=virus_typ,
            horizon_days=horizon,
            region=region_code,
        )
        if not live_feature_row:
            return {
                "error": "Failed to build live direct feature row",
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
            }

        if "horizon_days" in live_feature_row and "horizon_days" not in feature_names:
            feature_names.append("horizon_days")

        X_row = np.array([[live_feature_row.get(name, 0.0) for name in feature_names]], dtype=float)
        X_row = np.nan_to_num(X_row, nan=0.0, posinf=0.0, neginf=0.0)

        prediction = max(0.0, float(model_med.predict(X_row)[0]))
        lower_bound = max(0.0, float(model_lo.predict(X_row)[0]))
        upper_bound = max(0.0, float(model_hi.predict(X_row)[0]))
        lower_bound = min(lower_bound, prediction)
        upper_bound = max(upper_bound, prediction)

        issue_date = pd.Timestamp(df["ds"].max()).to_pydatetime()
        target_date = issue_date + timedelta(days=horizon)
        last_momentum = float(df["trend_momentum_7d"].iloc[-1]) if "trend_momentum_7d" in df.columns else 0.0
        forecast_records: list[dict[str, Any]] = []
        risk = self._compute_outbreak_risk(prediction, y)
        forecast_records.append(
            {
                "ds": target_date,
                "yhat": prediction,
                "yhat_lower": lower_bound,
                "yhat_upper": upper_bound,
                "trend_momentum_7d": last_momentum,
                "outbreak_risk_score": risk,
            }
        )

        model_version = metadata.get("version", "xgb_stack_v1_loaded")
        backtest_metrics = dict(metadata.get("backtest_metrics") or {})
        live_event_feature_row = self._build_live_event_feature_row(
            raw=df,
            live_feature_row=live_feature_row,
            horizon_days=horizon,
        )
        event_bundle: dict[str, Any] | None = None
        if event_model is None:
            panel = self._build_direct_training_panel_from_frame(
                df,
                horizon_days=horizon,
                n_splits=max(int(metadata.get("event_oof_splits") or 5), 3),
            )
            if not panel.empty:
                event_bundle = self._build_event_probability_model_from_panel(panel)
                event_model = event_bundle.get("model")
                backtest_metrics.update(event_bundle.get("calibrated_metrics") or {})
                backtest_metrics["probability_source"] = event_bundle.get("probability_source")
                backtest_metrics["calibration_mode"] = event_bundle.get("calibration_mode")
                backtest_metrics["fallback_reason"] = event_bundle.get("fallback_reason")
                backtest_metrics["reliability_score"] = event_bundle.get("reliability_score")

        probability_source = str(
            (event_bundle or {}).get("probability_source")
            or getattr(event_model, "probability_source", None)
            or backtest_metrics.get("probability_source")
            or metadata.get("event_probability_source")
            or "empirical_event_prevalence"
        )
        calibration_mode = str(
            (event_bundle or {}).get("calibration_mode")
            or getattr(event_model, "calibration_mode", None)
            or backtest_metrics.get("calibration_mode")
            or metadata.get("event_calibration_mode")
            or "raw_probability"
        )
        fallback_reason = (
            (event_bundle or {}).get("fallback_reason")
            or getattr(event_model, "fallback_reason", None)
            or metadata.get("event_fallback_reason")
        )
        event_probability: float | None = None
        if event_model is not None:
            event_feature_names = list(getattr(event_model, "feature_names", []) or [])
            X_event = np.array(
                [[live_event_feature_row.get(name, 0.0) for name in (event_feature_names or ["current_y"])]],
                dtype=float,
            )
            X_event = np.nan_to_num(X_event, nan=0.0, posinf=0.0, neginf=0.0)
            event_probability = float(event_model.predict_proba(X_event)[0])
        contracts = self._build_contracts(
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
            forecast_records=forecast_records,
            model_version=model_version,
            y_history=y,
            issue_date=issue_date,
            quality_meta=self._quality_meta_from_backtest(
                backtest_metrics=backtest_metrics,
                event_probability=event_probability,
                probability_source=probability_source,
                calibration_mode=calibration_mode,
                fallback_reason=fallback_reason,
                learned_model_version=model_version,
                forecast_ready="error" not in backtest_metrics,
                drift_status="ok" if "error" not in backtest_metrics else "unknown",
            ),
        )

        result: dict[str, Any] = {
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
            "training_samples": metadata.get("training_samples", len(df)),
            "forecast_days": horizon,
            "data_frequency_days": horizon,
            "forecast": forecast_records,
            "feature_names": feature_names,
            "feature_importance": metadata.get("feature_importance", {}),
            "model_version": model_version,
            "confidence": contracts["event_forecast"].get("confidence"),
            "training_window": metadata.get("training_window"),
            "backtest_metrics": backtest_metrics,
            "contracts": contracts,
            "timestamp": utc_now(),
        }

        logger.info(
            f"Inference completed for {virus_typ}/{region_code}/h{horizon}: "
            f"target_date={target_date.date()}, model={model_version}"
        )
        return result

    # ═══════════════════════════════════════════════════════════════════
    #  MAIN FORECAST PIPELINE (fallback: trains in-memory)
    # ═══════════════════════════════════════════════════════════════════

    def train_and_forecast(
        self,
        virus_typ: str = "Influenza A",
        *,
        region: str = DEFAULT_FORECAST_REGION,
        horizon_days: int = DEFAULT_DECISION_HORIZON_DAYS,
        include_internal_history: bool = True,
    ) -> dict[str, Any]:
        """Train a direct multi-horizon stack in-memory and return one forecast point."""
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        logger.info(f"=== Direct stacking forecast for {virus_typ}/{region_code}/h{horizon} ===")

        df = self.prepare_training_data(
            virus_typ=virus_typ,
            include_internal_history=include_internal_history,
            region=region_code,
        )

        panel = self._build_direct_training_panel_from_frame(
            df,
            horizon_days=horizon,
            n_splits=5,
        )
        if panel.empty or len(panel) < max(MIN_DIRECT_TRAIN_POINTS, 24):
            logger.error(
                "Insufficient data for direct training (%s rows) for %s/%s/h%s",
                len(panel) if not panel.empty else 0,
                virus_typ,
                region_code,
                horizon,
            )
            return {
                "error": "Insufficient training data",
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
            }

        model_med, model_lo, model_hi, feature_names, feature_importance = (
            self._fit_xgboost_meta_from_panel(panel, target_column="y_target")
        )
        live_feature_row = self._build_live_direct_feature_row(
            df,
            virus_typ=virus_typ,
            horizon_days=horizon,
            region=region_code,
        )
        X_row = np.array([[live_feature_row.get(name, 0.0) for name in feature_names]], dtype=float)
        X_row = np.nan_to_num(X_row, nan=0.0, posinf=0.0, neginf=0.0)

        prediction = max(0.0, float(model_med.predict(X_row)[0]))
        lower_bound = max(0.0, float(model_lo.predict(X_row)[0]))
        upper_bound = max(0.0, float(model_hi.predict(X_row)[0]))
        lower_bound = min(lower_bound, prediction)
        upper_bound = max(upper_bound, prediction)

        y = df["y"].to_numpy(dtype=float)
        issue_date = pd.Timestamp(df["ds"].max()).to_pydatetime()
        target_date = issue_date + timedelta(days=horizon)
        last_momentum = float(df["trend_momentum_7d"].iloc[-1]) if "trend_momentum_7d" in df.columns else 0.0
        forecast_records = [
            {
                "ds": target_date,
                "yhat": prediction,
                "yhat_lower": lower_bound,
                "yhat_upper": upper_bound,
                "trend_momentum_7d": last_momentum,
                "outbreak_risk_score": self._compute_outbreak_risk(prediction, y),
            }
        ]
        event_bundle = self._build_event_probability_model_from_panel(panel)
        event_model = event_bundle.get("model")
        live_event_feature_row = self._build_live_event_feature_row(
            raw=df,
            live_feature_row=live_feature_row,
            horizon_days=horizon,
        )
        event_probability: float | None = None
        if event_model is not None:
            event_feature_names = list(getattr(event_model, "feature_names", []) or [])
            X_event = np.array(
                [[live_event_feature_row.get(name, 0.0) for name in (event_feature_names or ["current_y"])]],
                dtype=float,
            )
            X_event = np.nan_to_num(X_event, nan=0.0, posinf=0.0, neginf=0.0)
            event_probability = float(event_model.predict_proba(X_event)[0])
        try:
            backtest_metrics = self.evaluate_training_candidate(
                virus_typ=virus_typ,
                include_internal_history=include_internal_history,
                region=region_code,
                horizon_days=horizon,
            )
        except Exception as exc:
            logger.warning("Backtest evaluation failed for %s/%s/h%s: %s", virus_typ, region_code, horizon, exc)
            backtest_metrics = {"error": str(exc)}

        if "error" not in backtest_metrics:
            backtest_metrics.update(event_bundle.get("calibrated_metrics") or {})
            backtest_metrics["probability_source"] = event_bundle.get("probability_source")
            backtest_metrics["event_model_family"] = event_bundle.get("model_family")
            backtest_metrics["calibration_mode"] = event_bundle.get("calibration_mode")
            backtest_metrics["fallback_reason"] = event_bundle.get("fallback_reason")
            backtest_metrics["reliability_metrics"] = event_bundle.get("reliability_metrics") or {}
            backtest_metrics["reliability_source"] = event_bundle.get("reliability_source")
            backtest_metrics["reliability_score"] = event_bundle.get("reliability_score")

        model_version = f"xgb_stack_direct_h{horizon}_inline"
        contracts = self._build_contracts(
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
            forecast_records=forecast_records,
            model_version=model_version,
            y_history=y,
            issue_date=issue_date,
            quality_meta=self._quality_meta_from_backtest(
                backtest_metrics=backtest_metrics,
                event_probability=event_probability,
                probability_source=str(event_bundle.get("probability_source") or "empirical_event_prevalence"),
                calibration_mode=str(event_bundle.get("calibration_mode") or "raw_probability"),
                fallback_reason=event_bundle.get("fallback_reason"),
                learned_model_version=model_version,
                forecast_ready="error" not in backtest_metrics,
                drift_status="unknown",
            ),
        )

        result: dict[str, Any] = {
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
            "training_samples": len(df),
            "forecast_days": horizon,
            "data_frequency_days": horizon,
            "forecast": forecast_records,
            "feature_names": feature_names,
            "feature_importance": feature_importance,
            "model_version": model_version,
            "confidence": contracts["event_forecast"].get("confidence"),
            "training_window": {
                "start": df["ds"].min().isoformat(),
                "end": df["ds"].max().isoformat(),
                "samples": int(len(df)),
                "panel_rows": int(len(panel)),
            },
            "backtest_metrics": backtest_metrics,
            "contracts": contracts,
            "timestamp": utc_now(),
        }

        logger.info(
            "Forecast completed for %s/%s/h%s: target_date=%s, features=%s",
            virus_typ,
            region_code,
            horizon,
            target_date.date(),
            len(feature_importance),
        )
        return result

    # ═══════════════════════════════════════════════════════════════════
    #  PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════

    def save_forecast(self, forecast_data: dict[str, Any]) -> int:
        """Save forecast to database including new stacking fields."""
        logger.info("Saving forecast to database...")
        count = 0
        region_code = normalize_forecast_region(forecast_data.get("region"))
        horizon = ensure_supported_horizon(forecast_data.get("horizon_days", DEFAULT_DECISION_HORIZON_DAYS))
        contracts_payload = forecast_data.get("contracts") or {}
        raw_event_forecast = (contracts_payload.get("event_forecast") or {})
        normalized_event_forecast = normalize_event_forecast_payload(raw_event_forecast)
        stored_confidence = normalized_event_forecast.get("confidence")
        if stored_confidence is None and forecast_data.get("confidence") is not None:
            normalized_event_forecast["confidence"] = float(forecast_data["confidence"])
            normalized_event_forecast = normalize_event_forecast_payload(normalized_event_forecast)
            stored_confidence = normalized_event_forecast.get("confidence")
        if stored_confidence is None:
            stored_confidence = forecast_data.get("confidence", 0.95)

        for item in forecast_data["forecast"]:
            existing = (
                self.db.query(MLForecast)
                .filter(
                    MLForecast.forecast_date == item["ds"],
                    MLForecast.virus_typ == forecast_data["virus_typ"],
                    MLForecast.region == region_code,
                    MLForecast.horizon_days == horizon,
                )
                .first()
            )

            kwargs = {
                "predicted_value": item["yhat"],
                "lower_bound": item["yhat_lower"],
                "upper_bound": item["yhat_upper"],
                "confidence": stored_confidence,
                "model_version": forecast_data["model_version"],
                "features_used": {
                    "feature_names": forecast_data.get("feature_names", []),
                    "feature_importance": forecast_data.get("feature_importance", {}),
                    "training_window": forecast_data.get("training_window"),
                    "backtest_metrics": forecast_data.get("backtest_metrics"),
                    "event_forecast": normalized_event_forecast,
                    "forecast_quality": ((forecast_data.get("contracts") or {}).get("forecast_quality") or {}),
                },
                "trend_momentum_7d": item.get("trend_momentum_7d"),
                "outbreak_risk_score": item.get("outbreak_risk_score"),
            }

            if existing:
                for key, val in kwargs.items():
                    setattr(existing, key, val)
            else:
                forecast_record = MLForecast(
                    forecast_date=item["ds"],
                    virus_typ=forecast_data["virus_typ"],
                    region=region_code,
                    horizon_days=horizon,
                    **kwargs,
                )
                self.db.add(forecast_record)
                count += 1

        self.db.commit()
        logger.info(f"Saved {count} new forecast records")
        return count

    def run_forecasts_for_all_viruses(
        self,
        *,
        region: str = DEFAULT_FORECAST_REGION,
        horizon_days: int = DEFAULT_DECISION_HORIZON_DAYS,
        include_internal_history: bool = True,
    ) -> dict[str, Any]:
        """Run forecasts for all relevant virus types.

        Uses :meth:`predict` which loads pre-trained models from disk
        when available, falling back to in-memory training otherwise.
        """
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        virus_types = ["Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"]

        results: dict[str, Any] = {}
        for virus in virus_types:
            logger.info(f"Processing forecast for {virus}/{region_code}/h{horizon}...")
            try:
                forecast = self.predict(
                    virus_typ=virus,
                    region=region_code,
                    horizon_days=horizon,
                    include_internal_history=include_internal_history,
                )
                if "error" not in forecast:
                    self.save_forecast(forecast)
                results[virus] = forecast
            except Exception as e:
                logger.error(f"Forecast failed for {virus}: {e}")
                results[virus] = {"error": str(e)}

        return results
