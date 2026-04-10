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
from app.services.ml import forecast_service_internal_history
from app.services.ml import forecast_service_event_probability
from app.services.ml import forecast_service_inference
from app.services.ml import forecast_service_direct_training
from app.services.ml import forecast_service_quality_contracts
from app.services.ml import forecast_service_pipeline
from app.services.ml import forecast_service_backtest
from app.services.ml import forecast_service_estimators
from app.services.ml import forecast_service_preparation
from app.services.ml import forecast_service_sources

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


def _loaded_model_expected_feature_count(model: Any | None) -> int | None:
    if model is None:
        return None
    try:
        booster = model.get_booster()
        return int(booster.num_features())
    except Exception:
        return None


def _resolve_loaded_model_feature_names(
    *,
    metadata: dict[str, Any],
    live_feature_row: dict[str, Any],
    model: Any | None,
) -> list[str]:
    explicit_feature_names = list(metadata.get("feature_names") or [])
    if explicit_feature_names:
        return explicit_feature_names

    feature_names = list(META_FEATURES)
    if "horizon_days" in live_feature_row and "horizon_days" not in feature_names:
        expected_feature_count = _loaded_model_expected_feature_count(model)
        if expected_feature_count is None or expected_feature_count >= len(feature_names) + 1:
            feature_names.append("horizon_days")
    return feature_names


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
        return forecast_service_preparation.prepare_training_data(
            self,
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            include_internal_history=include_internal_history,
            region=region,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            cross_disease_map=CROSS_DISEASE_MAP,
            survstat_virus_map=SURVSTAT_VIRUS_MAP,
            wastewater_aggregated_model=WastewaterAggregated,
            survstat_weekly_data_model=SurvstatWeeklyData,
            func_module=func,
            pd_module=pd,
            np_module=np,
            datetime_cls=datetime,
            timedelta_cls=timedelta,
            logger=logger,
        )

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
        return forecast_service_sources.region_variants(
            region,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            bundesland_names=BUNDESLAND_NAMES,
        )

    @classmethod
    def _survstat_region_values(cls, region: str) -> list[str]:
        return forecast_service_sources.survstat_region_values(
            region,
            region_variants_fn=cls._region_variants,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
        )

    def _load_wastewater_training_frame(
        self,
        *,
        virus_typ: str,
        start_date: datetime,
        region: str,
    ) -> pd.DataFrame:
        return forecast_service_sources.load_wastewater_training_frame(
            self,
            virus_typ=virus_typ,
            start_date=start_date,
            region=region,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            region_variants_fn=self._region_variants,
            wastewater_aggregated_model=WastewaterAggregated,
            wastewater_data_model=WastewaterData,
            func_module=func,
            pd_module=pd,
        )

    def _load_google_trends_rows(
        self,
        *,
        keywords: list[str],
        start_date: datetime,
        region: str,
    ) -> list[GoogleTrendsData]:
        return forecast_service_sources.load_google_trends_rows(
            self,
            keywords=keywords,
            start_date=start_date,
            region=region,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            region_variants_fn=self._region_variants,
            google_trends_data_model=GoogleTrendsData,
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
        return forecast_service_internal_history.augment_with_internal_history(
            self,
            df=df,
            virus_typ=virus_typ,
            start_date=start_date,
            region=region,
        )

    def _load_internal_history_frame(
        self,
        *,
        virus_typ: str,
        start_date: datetime,
        region: str,
    ) -> pd.DataFrame:
        return forecast_service_internal_history.load_internal_history_frame(
            self,
            virus_typ=virus_typ,
            start_date=start_date,
            region=region,
            internal_history_test_map=INTERNAL_HISTORY_TEST_MAP,
            ganzimmun_model=GanzimmunData,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            func_module=func,
            timedelta_cls=timedelta,
            pd_module=pd,
        )

    @staticmethod
    def _build_internal_history_feature_frame(
        ds_index: pd.Series,
        history_df: pd.DataFrame,
    ) -> pd.DataFrame:
        return forecast_service_internal_history.build_internal_history_feature_frame(
            ds_index,
            history_df,
            pd_module=pd,
            timedelta_cls=timedelta,
        )

    def _is_holiday(self, datum: datetime, *, region: str = DEFAULT_FORECAST_REGION) -> bool:
        """Check if date falls in school holidays."""
        return forecast_service_sources.is_holiday(
            self,
            datum,
            region=region,
            normalize_forecast_region_fn=normalize_forecast_region,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            region_variants_fn=self._region_variants,
            school_holidays_model=SchoolHolidays,
        )

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
        return forecast_service_estimators.fit_holt_winters(
            y,
            n_steps,
            np_module=np,
            exponential_smoothing_cls=ExponentialSmoothing,
            logger=logger,
        )

    def _fit_ridge(
        self,
        df: pd.DataFrame,
        y: np.ndarray,
        n_steps: int,
    ) -> tuple[np.ndarray, dict[str, float]]:
        """Base estimator 2: Ridge Regression on lag/trend features."""
        return forecast_service_estimators.fit_ridge(
            df,
            y,
            n_steps,
            np_module=np,
            ridge_cls=Ridge,
            logger=logger,
        )

    def _fit_prophet(
        self,
        virus_typ: str,
        n_steps: int,
    ) -> np.ndarray | None:
        """Base estimator 3: Facebook Prophet with regressors."""
        return forecast_service_estimators.fit_prophet(
            self,
            virus_typ,
            n_steps,
            np_module=np,
            logger=logger,
        )

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
        return forecast_service_event_probability.fit_event_classifier_model(
            train_df,
            feature_names=feature_names,
            model_family=model_family,
            np_module=np,
            empirical_event_classifier_cls=EmpiricalEventClassifier,
            default_event_classifier_config=DEFAULT_EVENT_CLASSIFIER_CONFIG,
            pipeline_cls=Pipeline,
            standard_scaler_cls=StandardScaler,
            logistic_regression_cls=LogisticRegression,
        )

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
        return forecast_service_event_probability.build_event_oof_predictions(
            self,
            panel,
            feature_names=feature_names,
            model_family=model_family,
            walk_forward_stride=walk_forward_stride,
            max_splits=max_splits,
            min_train_points=min_train_points,
            default_walk_forward_stride=DEFAULT_WALK_FORWARD_STRIDE,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            build_walk_forward_splits_fn=build_walk_forward_splits,
            np_module=np,
            pd_module=pd,
        )

    @staticmethod
    def _select_best_event_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        return forecast_service_event_probability.select_best_event_candidate(
            candidates,
            pd_module=pd,
        )

    def _build_event_probability_model_from_panel(
        self,
        panel: pd.DataFrame,
        *,
        walk_forward_stride: int = DEFAULT_WALK_FORWARD_STRIDE,
        max_splits: int | None = None,
    ) -> dict[str, Any]:
        return forecast_service_event_probability.build_event_probability_model_from_panel(
            self,
            panel,
            walk_forward_stride=walk_forward_stride,
            max_splits=max_splits,
            default_walk_forward_stride=DEFAULT_WALK_FORWARD_STRIDE,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            learned_probability_model_cls=LearnedProbabilityModel,
            empirical_event_classifier_cls=EmpiricalEventClassifier,
            compute_classification_metrics_fn=compute_classification_metrics,
            select_probability_calibration_fn=select_probability_calibration,
            apply_probability_calibration_fn=apply_probability_calibration,
            reliability_score_from_metrics_fn=reliability_score_from_metrics,
            np_module=np,
            pd_module=pd,
        )

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
        return forecast_service_direct_training.build_direct_training_panel_from_frame(
            self,
            raw,
            horizon_days=horizon_days,
            n_splits=n_splits,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            build_direct_target_frame_fn=build_direct_target_frame,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            ridge_cls=Ridge,
            time_series_split_cls=TimeSeriesSplit,
            np_module=np,
            pd_module=pd,
        )

    def _build_live_direct_feature_row(
        self,
        raw: pd.DataFrame,
        *,
        virus_typ: str,
        horizon_days: int,
        region: str = DEFAULT_FORECAST_REGION,
    ) -> dict[str, float]:
        return forecast_service_direct_training.build_live_direct_feature_row(
            self,
            raw,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            region=region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            normalize_forecast_region_fn=normalize_forecast_region,
            build_direct_target_frame_fn=build_direct_target_frame,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            ridge_cls=Ridge,
            np_module=np,
        )

    def _fit_xgboost_meta_from_panel(
        self,
        panel: pd.DataFrame,
        *,
        target_column: str = "y_target",
        model_config: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[Any, Any, Any, list[str], dict[str, float]]:
        return forecast_service_direct_training.fit_xgboost_meta_from_panel(
            self,
            panel,
            target_column=target_column,
            model_config=model_config,
            meta_features=META_FEATURES,
            np_module=np,
        )

    # ═══════════════════════════════════════════════════════════════════
    #  XGBOOST META-LEARNER
    # ═══════════════════════════════════════════════════════════════════

    def _generate_oof_predictions(
        self,
        df: pd.DataFrame,
        n_splits: int = 5,
    ) -> pd.DataFrame:
        return forecast_service_direct_training.generate_oof_predictions(
            self,
            df,
            n_splits=n_splits,
            time_series_split_cls=TimeSeriesSplit,
            np_module=np,
            pd_module=pd,
        )

    def _fit_xgboost_meta(
        self,
        df: pd.DataFrame,
        oof: pd.DataFrame,
        model_config: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[Any, Any, Any, dict[str, float]]:
        return forecast_service_direct_training.fit_xgboost_meta(
            self,
            df,
            oof,
            model_config=model_config,
            meta_features=META_FEATURES,
            np_module=np,
            logger=logger,
        )

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
        return forecast_service_backtest.evaluate_training_candidate(
            self,
            virus_typ,
            include_internal_history=include_internal_history,
            model_config=model_config,
            n_windows=n_windows,
            walk_forward_stride=walk_forward_stride,
            max_splits=max_splits,
            region=region,
            horizon_days=horizon_days,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            default_decision_horizon_days=DEFAULT_DECISION_HORIZON_DAYS,
            default_walk_forward_stride=DEFAULT_WALK_FORWARD_STRIDE,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            build_walk_forward_splits_fn=build_walk_forward_splits,
            compute_regression_metrics_fn=compute_regression_metrics,
            compute_classification_metrics_fn=compute_classification_metrics,
            summarize_probabilistic_metrics_fn=summarize_probabilistic_metrics,
            np_module=np,
            pd_module=pd,
        )

    @staticmethod
    def _compute_regression_metrics(
        predicted: list[float],
        actual: list[float],
    ) -> dict[str, float]:
        return forecast_service_quality_contracts.compute_regression_metrics(
            predicted,
            actual,
            np_module=np,
        )

    @staticmethod
    def _backtest_quality_score(backtest_metrics: dict[str, Any] | None) -> float | None:
        return forecast_service_quality_contracts.backtest_quality_score(backtest_metrics)

    @staticmethod
    def _calibration_passed(backtest_metrics: dict[str, Any] | None) -> bool | None:
        return forecast_service_quality_contracts.calibration_passed(backtest_metrics)

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
        return forecast_service_quality_contracts.quality_meta_from_backtest(
            self,
            backtest_metrics=backtest_metrics,
            event_probability=event_probability,
            probability_source=probability_source,
            calibration_mode=calibration_mode,
            fallback_reason=fallback_reason,
            learned_model_version=learned_model_version,
            forecast_ready=forecast_ready,
            drift_status=drift_status,
            baseline_deltas=baseline_deltas,
            timing_metrics=timing_metrics,
            interval_coverage=interval_coverage,
            promotion_gate=promotion_gate,
            reliability_score_from_metrics_fn=reliability_score_from_metrics,
            confidence_semantics_alias=CONFIDENCE_SEMANTICS_ALIAS,
            backtest_reliability_proxy_source=BACKTEST_RELIABILITY_PROXY_SOURCE,
        )

    def _compute_outbreak_risk(
        self,
        prediction: float,
        y_history: np.ndarray,
        window: int = 30,
    ) -> float:
        """Compute outbreak risk score (0.0 – 1.0) via z-score sigmoid."""
        return forecast_service_quality_contracts.compute_outbreak_risk(
            prediction,
            y_history,
            window=window,
            np_module=np,
            sigmoid_fn=_sigmoid,
        )

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
        return forecast_service_quality_contracts.build_contracts(
            self,
            virus_typ=virus_typ,
            region=region,
            horizon_days=horizon_days,
            forecast_records=forecast_records,
            model_version=model_version,
            y_history=y_history,
            issue_date=issue_date,
            quality_meta=quality_meta,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            burden_forecast_cls=BurdenForecast,
            burden_forecast_point_cls=BurdenForecastPoint,
            event_forecast_cls=EventForecast,
            forecast_quality_cls=ForecastQuality,
            confidence_label_fn=confidence_label,
            backtest_reliability_proxy_source=BACKTEST_RELIABILITY_PROXY_SOURCE,
            confidence_semantics_alias=CONFIDENCE_SEMANTICS_ALIAS,
            default_decision_event_threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            utc_now_fn=utc_now,
            np_module=np,
        )

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
        return forecast_service_inference.predict(
            self,
            virus_typ=virus_typ,
            region=region,
            horizon_days=horizon_days,
            include_internal_history=include_internal_history,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            load_cached_models_fn=_load_cached_models,
            is_model_feature_compatibility_error_fn=_is_model_feature_compatibility_error,
            logger=logger,
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
        """Generate forecast using pre-loaded XGBoost models."""
        return forecast_service_inference.inference_from_loaded_models(
            self,
            virus_typ=virus_typ,
            model_med=model_med,
            model_lo=model_lo,
            model_hi=model_hi,
            metadata=metadata,
            event_model=event_model,
            region=region,
            horizon_days=horizon_days,
            include_internal_history=include_internal_history,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            np_module=np,
            pd_module=pd,
            timedelta_cls=timedelta,
            utc_now_fn=utc_now,
            logger=logger,
        )

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
        return forecast_service_pipeline.train_and_forecast(
            self,
            virus_typ=virus_typ,
            region=region,
            horizon_days=horizon_days,
            include_internal_history=include_internal_history,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            min_direct_train_points=MIN_DIRECT_TRAIN_POINTS,
            utc_now_fn=utc_now,
            timedelta_cls=timedelta,
            np_module=np,
            pd_module=pd,
            logger=logger,
        )

    # ═══════════════════════════════════════════════════════════════════
    #  PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════

    def save_forecast(self, forecast_data: dict[str, Any]) -> int:
        """Save forecast to database including new stacking fields."""
        return forecast_service_pipeline.save_forecast(
            self,
            forecast_data,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            normalize_event_forecast_payload_fn=normalize_event_forecast_payload,
            default_decision_horizon_days=DEFAULT_DECISION_HORIZON_DAYS,
            ml_forecast_cls=MLForecast,
            logger=logger,
        )

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
        return forecast_service_pipeline.run_forecasts_for_all_viruses(
            self,
            region=region,
            horizon_days=horizon_days,
            include_internal_history=include_internal_history,
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            default_forecast_region=DEFAULT_FORECAST_REGION,
            default_decision_horizon_days=DEFAULT_DECISION_HORIZON_DAYS,
            logger=logger,
        )
