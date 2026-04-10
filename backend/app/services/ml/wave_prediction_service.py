"""Stage-1 leakage-safe wave prediction service."""

from __future__ import annotations
from app.core.time import utc_now

import json
import logging
import os
import pickle
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, f1_score, mean_absolute_error, precision_score, recall_score
from sqlalchemy.orm import Session
from xgboost import XGBClassifier, XGBRegressor

from app.core.config import get_settings
from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    BUNDESLAND_NAMES,
    normalize_state_code,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES, normalize_virus_type
from app.services.ml import wave_prediction_artifacts
from app.services.ml import wave_prediction_backtest
from app.services.ml import wave_prediction_metrics
from app.services.ml import wave_prediction_sources
from app.services.ml import wave_prediction_training
from app.services.ml.wave_prediction_utils import (
    WaveLabelConfig,
    atomic_json_dump,
    atomic_pickle_dump,
    build_backtest_splits,
    build_daily_signal_features,
    false_alarm_rate,
    get_classification_feature_columns,
    get_regression_feature_columns,
    json_safe,
    label_wave_start,
    mean_lead_time_days,
    safe_mape,
    safe_pr_auc,
    safe_roc_auc,
    school_holiday_features,
    top_feature_importance,
    wave_label_config_for_pathogen,
    weather_context_features,
)

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "wave_prediction"

REGRESSOR_CONFIG: dict[str, Any] = {
    "n_estimators": 180,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "reg:squarederror",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": 1,
}

CLASSIFIER_CONFIG: dict[str, Any] = {
    "n_estimators": 180,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": 1,
}


class _ConstantBinaryClassifier:
    """Fallback classifier for single-class training windows."""

    def __init__(self, positive_probability: float, feature_count: int) -> None:
        self.positive_probability = float(np.clip(positive_probability, 0.0, 1.0))
        self.feature_importances_ = np.zeros(max(int(feature_count), 0), dtype=float)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        rows = len(X)
        positive = np.full(rows, self.positive_probability, dtype=float)
        negative = 1.0 - positive
        return np.column_stack([negative, positive])


@dataclass(frozen=True)
class _WaveRuntimeSettings:
    WAVE_PREDICTION_HORIZON_DAYS: int = 14
    WAVE_PREDICTION_LOOKBACK_DAYS: int = 900
    WAVE_PREDICTION_MIN_TRAIN_ROWS: int = 240
    WAVE_PREDICTION_MIN_POSITIVE_ROWS: int = 12
    WAVE_PREDICTION_MODEL_VERSION: str = "wave_prediction_v1"
    WAVE_PREDICTION_BACKTEST_FOLDS: int = 4
    WAVE_PREDICTION_MIN_TRAIN_PERIODS: int = 180
    WAVE_PREDICTION_MIN_TEST_PERIODS: int = 28
    WAVE_PREDICTION_CLASSIFICATION_THRESHOLD: float = 0.5
    WAVE_PREDICTION_ENABLE_FORECAST_WEATHER: bool = True
    WAVE_PREDICTION_ENABLE_DEMOGRAPHICS: bool = True
    WAVE_PREDICTION_ENABLE_INTERACTIONS: bool = True
    WAVE_PREDICTION_LABEL_ABSOLUTE_THRESHOLD: float = 10.0
    WAVE_PREDICTION_LABEL_SEASONAL_ZSCORE: float = 1.5
    WAVE_PREDICTION_LABEL_GROWTH_OBSERVATIONS: int = 2
    WAVE_PREDICTION_LABEL_GROWTH_MIN_RELATIVE_INCREASE: float = 0.2
    WAVE_PREDICTION_LABEL_MAD_FLOOR: float = 1.0
    WAVE_PREDICTION_CALIBRATION_HOLDOUT_FRACTION: float = 0.2
    WAVE_PREDICTION_MIN_CALIBRATION_ROWS: int = 28
    WAVE_PREDICTION_MIN_CALIBRATION_POSITIVES: int = 6


def _pathogen_slug(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


class WavePredictionService:
    """Stage-1 wave prediction service using tabular gradient boosting."""

    def __init__(
        self,
        db: Session | None,
        models_dir: Path | None = None,
        settings: Any | None = None,
    ) -> None:
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.settings = self._resolve_settings(settings)
        self.feature_builder = RegionalFeatureBuilder(db)

    def build_wave_panel(
        self,
        pathogen: str | None = None,
        region: str | None = None,
        lookback_days: int = 900,
        horizon_days: int = 14,
    ) -> pd.DataFrame:
        """Build a leakage-safe daily as-of panel across pathogens and Bundesländer."""

        lookback = max(int(lookback_days or self.settings.WAVE_PREDICTION_LOOKBACK_DAYS), 90)
        horizon = max(int(horizon_days or self.settings.WAVE_PREDICTION_HORIZON_DAYS), 1)
        region_code = normalize_state_code(region) if region else None
        pathogens = (
            (normalize_virus_type(pathogen),)
            if pathogen is not None
            else SUPPORTED_VIRUS_TYPES
        )

        end_date = self._panel_end_date()
        start_date = end_date - pd.Timedelta(days=lookback)
        history_start = start_date - pd.Timedelta(days=730)

        all_rows: list[dict[str, Any]] = []
        for pathogen_name in pathogens:
            source_frames = self._load_source_frames(
                pathogen=pathogen_name,
                start_date=history_start,
                end_date=end_date + pd.Timedelta(days=horizon),
            )
            all_rows.extend(
                self._build_rows_for_pathogen(
                    pathogen=pathogen_name,
                    source_frames=source_frames,
                    start_date=start_date,
                    end_date=end_date,
                    horizon_days=horizon,
                    region_code=region_code,
                )
            )

        if not all_rows:
            return pd.DataFrame()

        frame = pd.DataFrame(all_rows).sort_values(["pathogen", "region", "as_of_date"]).reset_index(drop=True)
        return frame

    def train_models(
        self,
        *,
        pathogen: str,
        region: str | None = None,
        lookback_days: int | None = None,
        horizon_days: int | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        return wave_prediction_training.train_models(
            self,
            pathogen=pathogen,
            region=region,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            persist=persist,
            normalize_virus_type_fn=normalize_virus_type,
            get_regression_feature_columns_fn=get_regression_feature_columns,
            get_classification_feature_columns_fn=get_classification_feature_columns,
            wave_label_config_for_pathogen_fn=wave_label_config_for_pathogen,
            top_feature_importance_fn=top_feature_importance,
            utc_now_fn=utc_now,
        )

    def train_regression_model(
        self,
        panel: pd.DataFrame,
        *,
        feature_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        return wave_prediction_training.train_regression_model(
            panel,
            feature_columns=feature_columns,
            get_regression_feature_columns_fn=get_regression_feature_columns,
            regressor_config=REGRESSOR_CONFIG,
            xgb_regressor_cls=XGBRegressor,
            mean_absolute_error_fn=mean_absolute_error,
            safe_mape_fn=safe_mape,
            np_module=np,
        )

    def train_wave_classifier(
        self,
        panel: pd.DataFrame,
        *,
        feature_columns: list[str] | None = None,
        sample_weights: np.ndarray | None = None,
    ) -> dict[str, Any]:
        return wave_prediction_training.train_wave_classifier(
            self,
            panel,
            feature_columns=feature_columns,
            sample_weights=sample_weights,
            get_classification_feature_columns_fn=get_classification_feature_columns,
            constant_classifier_cls=_ConstantBinaryClassifier,
            classifier_config=CLASSIFIER_CONFIG,
            xgb_classifier_cls=XGBClassifier,
            np_module=np,
            pd_module=pd,
        )

    def run_wave_backtest(
        self,
        *,
        pathogen: str,
        region: str | None = None,
        lookback_days: int | None = None,
        horizon_days: int | None = None,
        panel: pd.DataFrame | None = None,
        include_oof_predictions: bool = False,
    ) -> dict[str, Any]:
        return wave_prediction_backtest.run_wave_backtest(
            self,
            pathogen=pathogen,
            region=region,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            panel=panel,
            include_oof_predictions=include_oof_predictions,
            normalize_virus_type_fn=normalize_virus_type,
            get_regression_feature_columns_fn=get_regression_feature_columns,
            get_classification_feature_columns_fn=get_classification_feature_columns,
            build_backtest_splits_fn=build_backtest_splits,
            mean_absolute_error_fn=mean_absolute_error,
            false_alarm_rate_fn=false_alarm_rate,
            mean_lead_time_days_fn=mean_lead_time_days,
            safe_mape_fn=safe_mape,
            safe_pr_auc_fn=safe_pr_auc,
            safe_roc_auc_fn=safe_roc_auc,
            precision_score_fn=precision_score,
            recall_score_fn=recall_score,
            f1_score_fn=f1_score,
            brier_score_loss_fn=brier_score_loss,
            json_safe_fn=json_safe,
            np_module=np,
            pd_module=pd,
        )

    def run_wave_prediction(
        self,
        pathogen: str,
        region: str,
        horizon_days: int = 14,
    ) -> dict[str, Any]:
        return wave_prediction_artifacts.run_wave_prediction(
            self,
            pathogen=pathogen,
            region=region,
            horizon_days=horizon_days,
            normalize_virus_type_fn=normalize_virus_type,
            normalize_state_code_fn=normalize_state_code,
            get_regression_feature_columns_fn=get_regression_feature_columns,
            get_classification_feature_columns_fn=get_classification_feature_columns,
            utc_now_fn=utc_now,
            np_module=np,
        )

    def _load_source_frames(
        self,
        *,
        pathogen: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> dict[str, Any]:
        return wave_prediction_sources.load_source_frames(
            self,
            pathogen=pathogen,
            start_date=start_date,
            end_date=end_date,
        )

    def _build_rows_for_pathogen(
        self,
        *,
        pathogen: str,
        source_frames: dict[str, Any],
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        horizon_days: int,
        region_code: str | None,
    ) -> list[dict[str, Any]]:
        return wave_prediction_sources.build_rows_for_pathogen(
            self,
            pathogen=pathogen,
            source_frames=source_frames,
            start_date=start_date,
            end_date=end_date,
            horizon_days=horizon_days,
            region_code=region_code,
            wave_label_config_for_pathogen_fn=wave_label_config_for_pathogen,
            build_daily_signal_features_fn=build_daily_signal_features,
            weather_context_features_fn=weather_context_features,
            school_holiday_features_fn=school_holiday_features,
            bundesland_names=BUNDESLAND_NAMES,
            pathogen_slug_fn=_pathogen_slug,
            pd_module=pd,
            np_module=np,
        )

    def _persist_artifacts(
        self,
        *,
        pathogen: str,
        regressor_bundle: dict[str, Any],
        classifier_bundle: dict[str, Any],
        metadata: dict[str, Any],
        backtest: dict[str, Any],
        dataset_manifest: dict[str, Any],
    ) -> None:
        wave_prediction_artifacts.persist_artifacts(
            self,
            pathogen=pathogen,
            regressor_bundle=regressor_bundle,
            classifier_bundle=classifier_bundle,
            metadata=metadata,
            backtest=backtest,
            dataset_manifest=dataset_manifest,
            pathogen_slug_fn=_pathogen_slug,
            atomic_pickle_dump_fn=atomic_pickle_dump,
            atomic_json_dump_fn=atomic_json_dump,
        )

    def _load_artifacts(self, pathogen: str) -> dict[str, Any]:
        return wave_prediction_artifacts.load_artifacts(
            self,
            pathogen,
            pathogen_slug_fn=_pathogen_slug,
            regressor_cls=XGBRegressor,
            classifier_cls=XGBClassifier,
            pickle_module=pickle,
        )

    @staticmethod
    def _visible_as_of(frame: pd.DataFrame | None, as_of: pd.Timestamp) -> pd.DataFrame:
        return wave_prediction_sources.visible_as_of(frame, as_of, pd_module=pd)

    @staticmethod
    def _group_by_state(frame: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
        return wave_prediction_sources.group_by_state(frame)

    @staticmethod
    def _coerce_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
        return wave_prediction_sources.coerce_frame(frame)

    @staticmethod
    def _latest_column_value(frame: pd.DataFrame | None, column: str) -> float:
        return wave_prediction_sources.latest_column_value(frame, column)

    @staticmethod
    def _growth_ratio(future_truth: pd.DataFrame) -> float:
        return wave_prediction_sources.growth_ratio(future_truth)

    @staticmethod
    def _fit_calibration(
        *,
        classifier: XGBClassifier,
        calibration_frame: pd.DataFrame,
        feature_columns: list[str],
    ) -> IsotonicRegression | None:
        return wave_prediction_metrics.fit_calibration(
            classifier=classifier,
            calibration_frame=calibration_frame,
            feature_columns=feature_columns,
            np_module=np,
        )

    @staticmethod
    def _apply_calibration(calibration: IsotonicRegression | None, raw_scores: np.ndarray) -> np.ndarray:
        return wave_prediction_metrics.apply_calibration(
            calibration,
            raw_scores,
            np_module=np,
        )

    @staticmethod
    def _select_classification_threshold(
        y_true: np.ndarray,
        score_values: np.ndarray,
        *,
        default_threshold: float,
    ) -> float:
        return wave_prediction_metrics.select_classification_threshold(
            y_true,
            score_values,
            default_threshold=default_threshold,
            precision_score_fn=precision_score,
            recall_score_fn=recall_score,
            f1_score_fn=f1_score,
            false_alarm_rate_fn=false_alarm_rate,
            np_module=np,
        )

    def _resolve_decision_strategy(
        self,
        *,
        y_true: np.ndarray,
        raw_scores: np.ndarray,
        calibration: IsotonicRegression | None,
        default_threshold: float,
    ) -> dict[str, Any]:
        return wave_prediction_metrics.resolve_decision_strategy(
            self,
            y_true=y_true,
            raw_scores=raw_scores,
            calibration=calibration,
            default_threshold=default_threshold,
            f1_score_fn=f1_score,
            brier_score_loss_fn=brier_score_loss,
            np_module=np,
        )

    @staticmethod
    def _compute_calibration_summary(y_true: np.ndarray, probabilities: np.ndarray) -> float:
        return wave_prediction_metrics.compute_calibration_summary(y_true, probabilities)

    def _aggregate_fold_metrics(self, folds: list[dict[str, Any]]) -> dict[str, Any]:
        return wave_prediction_metrics.aggregate_fold_metrics(folds, np_module=np)

    def _dataset_manifest(self, panel: pd.DataFrame) -> dict[str, Any]:
        return wave_prediction_metrics.dataset_manifest(panel)

    @staticmethod
    def _atomic_save_model(model: Any, target: Path) -> None:
        wave_prediction_artifacts.atomic_save_model(model, target)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        return wave_prediction_artifacts.load_json(path)

    @staticmethod
    def _resolve_settings(settings: Any | None) -> Any:
        if settings is not None:
            return settings
        try:
            return get_settings()
        except Exception:
            logger.warning("Falling back to default wave prediction settings because app settings could not be loaded.")
            return SimpleNamespace(**_WaveRuntimeSettings().__dict__)

    @staticmethod
    def _panel_end_date() -> pd.Timestamp:
        return pd.Timestamp(utc_now()).normalize()
