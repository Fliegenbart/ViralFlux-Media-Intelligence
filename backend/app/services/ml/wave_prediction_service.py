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
from app.services.ml import wave_prediction_sources
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
        normalized_pathogen = normalize_virus_type(pathogen)
        panel = self.build_wave_panel(
            pathogen=normalized_pathogen,
            region=region,
            lookback_days=lookback_days or self.settings.WAVE_PREDICTION_LOOKBACK_DAYS,
            horizon_days=horizon_days or self.settings.WAVE_PREDICTION_HORIZON_DAYS,
        )
        if panel.empty:
            return {"status": "error", "pathogen": normalized_pathogen, "error": "No panel rows available."}

        training_frame = panel.dropna(subset=["target_regression"]).copy()
        if len(training_frame) < int(self.settings.WAVE_PREDICTION_MIN_TRAIN_ROWS):
            return {
                "status": "error",
                "pathogen": normalized_pathogen,
                "error": f"Insufficient training rows ({len(training_frame)}).",
            }

        positives = int(training_frame["target_wave14"].sum())
        if positives < int(self.settings.WAVE_PREDICTION_MIN_POSITIVE_ROWS):
            return {
                "status": "error",
                "pathogen": normalized_pathogen,
                "error": f"Insufficient positive rows ({positives}).",
            }

        backtest = self.run_wave_backtest(
            pathogen=normalized_pathogen,
            region=region,
            lookback_days=lookback_days or self.settings.WAVE_PREDICTION_LOOKBACK_DAYS,
            horizon_days=horizon_days or self.settings.WAVE_PREDICTION_HORIZON_DAYS,
            panel=training_frame,
        )
        regression_columns = get_regression_feature_columns(training_frame)
        classification_columns = get_classification_feature_columns(training_frame)
        regressor_bundle = self.train_regression_model(training_frame, feature_columns=regression_columns)
        classifier_bundle = self.train_wave_classifier(training_frame, feature_columns=classification_columns)
        trained_at = utc_now().isoformat()
        top_features = top_feature_importance(
            classifier=classifier_bundle["classifier"],
            regressor=regressor_bundle["regressor"],
            feature_columns=classification_columns,
        )

        metadata = {
            "pathogen": normalized_pathogen,
            "region_scope": normalize_state_code(region) if region else "ALL",
            "trained_at": trained_at,
            "model_version": f"{self.settings.WAVE_PREDICTION_MODEL_VERSION}:{trained_at}",
            "training_window": {
                "start": str(training_frame["as_of_date"].min()),
                "end": str(training_frame["as_of_date"].max()),
                "rows": int(len(training_frame)),
            },
            "horizon_days": int(horizon_days or self.settings.WAVE_PREDICTION_HORIZON_DAYS),
            "target_definition": {
                "regression_target": "SurvStat incidence at the week containing t + horizon_days",
                "event_target": "Wave start within next 14 days",
                "label_config": wave_label_config_for_pathogen(normalized_pathogen, self.settings).to_manifest(),
            },
            "regression_feature_columns": regression_columns,
            "classification_feature_columns": classification_columns,
            "calibration_status": {
                "available": bool(classifier_bundle.get("calibration")),
                "version": (
                    f"isotonic:{trained_at}" if classifier_bundle.get("calibration") else None
                ),
            },
            "metrics": backtest.get("aggregate_metrics") or {},
            "top_features": top_features,
        }
        dataset_manifest = self._dataset_manifest(training_frame)

        if persist:
            self._persist_artifacts(
                pathogen=normalized_pathogen,
                regressor_bundle=regressor_bundle,
                classifier_bundle=classifier_bundle,
                metadata=metadata,
                backtest=backtest,
                dataset_manifest=dataset_manifest,
            )

        return {
            "status": "ok",
            "pathogen": normalized_pathogen,
            "trained_at": trained_at,
            "rows": int(len(training_frame)),
            "positives": positives,
            "metadata": metadata,
            "backtest": backtest,
            "dataset_manifest": dataset_manifest,
        }

    def train_regression_model(
        self,
        panel: pd.DataFrame,
        *,
        feature_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        features = feature_columns or get_regression_feature_columns(panel)
        frame = panel.dropna(subset=["target_regression"]).copy()
        X = frame[features].fillna(0.0).to_numpy(dtype=float)
        y = np.log1p(frame["target_regression"].astype(float).clip(lower=0.0).to_numpy())
        regressor = XGBRegressor(**REGRESSOR_CONFIG)
        regressor.fit(X, y)
        train_pred = np.expm1(regressor.predict(X))
        metrics = {
            "mae_train": float(mean_absolute_error(frame["target_regression"], train_pred)),
            "rmse_train": float(np.sqrt(np.mean((frame["target_regression"].to_numpy() - train_pred) ** 2))),
            "mape_train": safe_mape(frame["target_regression"], train_pred),
        }
        return {
            "regressor": regressor,
            "feature_columns": features,
            "metrics": metrics,
        }

    def train_wave_classifier(
        self,
        panel: pd.DataFrame,
        *,
        feature_columns: list[str] | None = None,
        sample_weights: np.ndarray | None = None,
    ) -> dict[str, Any]:
        features = feature_columns or get_classification_feature_columns(panel)
        frame = panel.dropna(subset=["target_wave14"]).sort_values("as_of_date").reset_index(drop=True)
        unique_dates = sorted(pd.to_datetime(frame["as_of_date"]).dt.normalize().unique())
        calibration_days = max(
            int(round(len(unique_dates) * float(self.settings.WAVE_PREDICTION_CALIBRATION_HOLDOUT_FRACTION))),
            int(self.settings.WAVE_PREDICTION_MIN_TEST_PERIODS),
        )
        calibration_dates = set(unique_dates[-calibration_days:]) if len(unique_dates) > calibration_days else set()
        calibration_frame = frame.loc[frame["as_of_date"].isin(calibration_dates)].copy()
        train_frame = frame.loc[~frame["as_of_date"].isin(calibration_dates)].copy()
        if train_frame.empty:
            train_frame = frame.copy()
            calibration_frame = pd.DataFrame(columns=frame.columns)

        X_train = train_frame[features].fillna(0.0).to_numpy(dtype=float)
        y_train = train_frame["target_wave14"].astype(int).to_numpy()
        if train_frame["target_wave14"].nunique() < 2:
            constant_classifier = _ConstantBinaryClassifier(
                positive_probability=float(y_train[0]) if len(y_train) else 0.0,
                feature_count=len(features),
            )
            return {
                "classifier": constant_classifier,
                "calibration": None,
                "feature_columns": features,
                "threshold": float(self.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD),
                "notes": [
                    "Single-class training window detected; using a constant classifier fallback."
                ],
            }
        positives = int(np.sum(y_train == 1))
        negatives = int(np.sum(y_train == 0))
        scale_pos_weight = float(negatives / positives) if positives > 0 else 1.0
        classifier = XGBClassifier(**(CLASSIFIER_CONFIG | {"scale_pos_weight": scale_pos_weight}))
        fit_sample_weights = None
        if sample_weights is not None and len(sample_weights) == len(train_frame):
            fit_sample_weights = sample_weights
        classifier.fit(X_train, y_train, sample_weight=fit_sample_weights)

        default_threshold = float(self.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD)
        calibration = None
        calibration_notes: list[str] = []
        holdout_scores = None
        holdout_labels = None
        if not calibration_frame.empty and calibration_frame["target_wave14"].nunique() > 1:
            X_holdout = calibration_frame[features].fillna(0.0).to_numpy(dtype=float)
            holdout_labels = calibration_frame["target_wave14"].astype(int).to_numpy()
            holdout_scores = classifier.predict_proba(X_holdout)[:, 1]
        if (
            not calibration_frame.empty
            and len(calibration_frame) >= int(self.settings.WAVE_PREDICTION_MIN_CALIBRATION_ROWS)
            and int(calibration_frame["target_wave14"].sum()) >= int(self.settings.WAVE_PREDICTION_MIN_CALIBRATION_POSITIVES)
            and calibration_frame["target_wave14"].nunique() > 1
        ):
            calibration = self._fit_calibration(
                classifier=classifier,
                calibration_frame=calibration_frame,
                feature_columns=features,
            )
        else:
            calibration_notes.append(
                "Calibration skipped; classifier output must be exposed as wave_score, not wave_probability."
            )

        threshold = default_threshold
        if holdout_scores is not None and holdout_labels is not None:
            strategy = self._resolve_decision_strategy(
                y_true=holdout_labels,
                raw_scores=holdout_scores,
                calibration=calibration,
                default_threshold=default_threshold,
            )
            threshold = float(strategy["threshold"])
            if not bool(strategy["use_calibration"]):
                calibration = None
            calibration_notes.extend(strategy["notes"])

        return {
            "classifier": classifier,
            "calibration": calibration,
            "feature_columns": features,
            "threshold": threshold,
            "notes": calibration_notes,
        }

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
        normalized_pathogen = normalize_virus_type(pathogen)
        frame = panel.copy() if panel is not None else self.build_wave_panel(
            pathogen=normalized_pathogen,
            region=region,
            lookback_days=lookback_days or self.settings.WAVE_PREDICTION_LOOKBACK_DAYS,
            horizon_days=horizon_days or self.settings.WAVE_PREDICTION_HORIZON_DAYS,
        )
        frame = frame.dropna(subset=["target_regression", "target_wave14"]).copy()
        if frame.empty:
            return {"status": "error", "pathogen": normalized_pathogen, "error": "No backtest rows available."}

        regression_columns = get_regression_feature_columns(frame)
        classification_columns = get_classification_feature_columns(frame)
        unique_dates = sorted(pd.to_datetime(frame["as_of_date"]).dt.normalize().unique())
        splits = build_backtest_splits(
            unique_dates,
            n_splits=int(self.settings.WAVE_PREDICTION_BACKTEST_FOLDS),
            min_train_periods=int(self.settings.WAVE_PREDICTION_MIN_TRAIN_PERIODS),
            min_test_periods=int(self.settings.WAVE_PREDICTION_MIN_TEST_PERIODS),
        )
        if not splits:
            return {
                "status": "error",
                "pathogen": normalized_pathogen,
                "error": "Insufficient periods for walk-forward validation.",
            }

        fold_metrics: list[dict[str, Any]] = []
        oof_rows: list[pd.DataFrame] = []
        for fold_idx, (train_dates, test_dates) in enumerate(splits, start=1):
            train_frame = frame.loc[frame["as_of_date"].isin(train_dates)].copy()
            test_frame = frame.loc[frame["as_of_date"].isin(test_dates)].copy()
            if train_frame.empty or test_frame.empty:
                continue

            regressor_bundle = self.train_regression_model(train_frame, feature_columns=regression_columns)
            classifier_bundle = self.train_wave_classifier(train_frame, feature_columns=classification_columns)
            regressor = regressor_bundle["regressor"]
            classifier = classifier_bundle["classifier"]
            calibration = classifier_bundle.get("calibration")
            threshold = float(classifier_bundle["threshold"])

            X_reg = test_frame[regression_columns].fillna(0.0).to_numpy(dtype=float)
            X_clf = test_frame[classification_columns].fillna(0.0).to_numpy(dtype=float)
            regression_pred = np.expm1(regressor.predict(X_reg))
            raw_scores = classifier.predict_proba(X_clf)[:, 1]
            probabilities = self._apply_calibration(calibration, raw_scores) if calibration is not None else None
            decision_scores = probabilities if probabilities is not None else raw_scores
            predicted_flags = (decision_scores >= threshold).astype(int)
            output_field = "wave_probability" if probabilities is not None else "wave_score"

            test_frame = test_frame.copy()
            test_frame["fold"] = fold_idx
            test_frame["regression_prediction"] = regression_pred
            test_frame["wave_score_raw"] = raw_scores
            test_frame["decision_score"] = decision_scores
            test_frame["score_output_field"] = output_field
            if probabilities is not None:
                test_frame["wave_probability"] = probabilities
            else:
                test_frame["wave_score"] = raw_scores
            test_frame["wave_flag"] = predicted_flags
            oof_rows.append(test_frame)

            y_true = test_frame["target_wave14"].astype(int).to_numpy()
            score_values = probabilities if probabilities is not None else raw_scores
            tp = int(np.sum((y_true == 1) & (predicted_flags == 1)))
            fp = int(np.sum((y_true == 0) & (predicted_flags == 1)))
            tn = int(np.sum((y_true == 0) & (predicted_flags == 0)))
            fn = int(np.sum((y_true == 1) & (predicted_flags == 0)))
            fold_metrics.append(
                {
                    "fold": fold_idx,
                    "train_start": str(min(train_dates)),
                    "train_end": str(max(train_dates)),
                    "test_start": str(min(test_dates)),
                    "test_end": str(max(test_dates)),
                    "rows": int(len(test_frame)),
                    "positive_rows": int(np.sum(y_true == 1)),
                    "mae": float(mean_absolute_error(test_frame["target_regression"], regression_pred)),
                    "rmse": float(np.sqrt(np.mean((test_frame["target_regression"].to_numpy() - regression_pred) ** 2))),
                    "mape": safe_mape(test_frame["target_regression"], regression_pred),
                    "roc_auc": safe_roc_auc(y_true, score_values),
                    "pr_auc": safe_pr_auc(y_true, score_values),
                    "brier_score": (
                        float(brier_score_loss(y_true, score_values))
                        if len(np.unique(y_true)) > 1
                        else None
                    ),
                    "precision": float(precision_score(y_true, predicted_flags, zero_division=0)),
                    "recall": float(recall_score(y_true, predicted_flags, zero_division=0)),
                    "f1": float(f1_score(y_true, predicted_flags, zero_division=0)),
                    "ece": (
                        float(
                            self._compute_calibration_summary(y_true, score_values)
                        )
                        if probabilities is not None
                        else None
                    ),
                    "false_alarm_rate": false_alarm_rate(y_true, predicted_flags),
                    "mean_lead_time_days": mean_lead_time_days(
                        test_frame["as_of_date"],
                        test_frame["wave_event_date"],
                        y_true,
                        predicted_flags,
                    ),
                    "probability_output": bool(probabilities is not None),
                    "output_field": output_field,
                    "tp": tp,
                    "fp": fp,
                    "tn": tn,
                    "fn": fn,
                }
            )

        aggregate = self._aggregate_fold_metrics(fold_metrics)
        oof_frame = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
        payload = {
            "status": "ok",
            "pathogen": normalized_pathogen,
            "horizon_days": int(horizon_days or self.settings.WAVE_PREDICTION_HORIZON_DAYS),
            "folds": fold_metrics,
            "aggregate_metrics": aggregate,
            "oof_rows": int(len(oof_frame.index)),
        }
        if include_oof_predictions:
            payload["oof_predictions"] = json_safe(oof_frame.to_dict(orient="records"))
        return payload

    def run_wave_prediction(
        self,
        pathogen: str,
        region: str,
        horizon_days: int = 14,
    ) -> dict[str, Any]:
        normalized_pathogen = normalize_virus_type(pathogen)
        region_code = normalize_state_code(region) or region.upper()
        artifacts = self._load_artifacts(normalized_pathogen)
        metadata = artifacts.get("metadata") or {}
        regressor: XGBRegressor | None = artifacts.get("regressor")
        classifier: XGBClassifier | None = artifacts.get("classifier")
        if regressor is None or classifier is None:
            return {
                "pathogen": normalized_pathogen,
                "region": region_code,
                "generated_at": utc_now().isoformat(),
                "horizon_days": int(horizon_days),
                "model_version": None,
                "top_features": {},
                "notes": ["No trained wave prediction artifacts available."],
            }

        panel = self.build_wave_panel(
            pathogen=normalized_pathogen,
            region=region_code,
            lookback_days=max(int(self.settings.WAVE_PREDICTION_MIN_TRAIN_PERIODS), 90),
            horizon_days=horizon_days,
        )
        if panel.empty:
            return {
                "pathogen": normalized_pathogen,
                "region": region_code,
                "generated_at": utc_now().isoformat(),
                "horizon_days": int(horizon_days),
                "model_version": metadata.get("model_version"),
                "top_features": metadata.get("top_features") or {},
                "notes": ["No inference row could be built for the requested region."],
            }

        row = panel.sort_values("as_of_date").tail(1).reset_index(drop=True)
        regression_columns = metadata.get("regression_feature_columns") or get_regression_feature_columns(row)
        classification_columns = metadata.get("classification_feature_columns") or get_classification_feature_columns(row)
        X_reg = row[regression_columns].fillna(0.0).to_numpy(dtype=float)
        X_clf = row[classification_columns].fillna(0.0).to_numpy(dtype=float)
        regression_forecast = float(np.expm1(regressor.predict(X_reg))[0])
        raw_score = float(classifier.predict_proba(X_clf)[:, 1][0])
        calibration = artifacts.get("calibration")
        threshold = float(metadata.get("classification_threshold") or self.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD)
        notes: list[str] = []
        payload = {
            "pathogen": normalized_pathogen,
            "region": region_code,
            "generated_at": utc_now().isoformat(),
            "horizon_days": int(horizon_days),
            "regression_forecast": round(max(regression_forecast, 0.0), 4),
            "model_version": metadata.get("model_version"),
            "top_features": metadata.get("top_features") or {},
            "notes": notes,
        }
        if calibration is not None:
            wave_probability = float(np.clip(self._apply_calibration(calibration, np.array([raw_score]))[0], 0.0, 1.0))
            payload["wave_probability"] = round(wave_probability, 6)
            payload["wave_flag"] = bool(wave_probability >= threshold)
        else:
            payload["wave_score"] = round(raw_score, 6)
            payload["wave_flag"] = bool(raw_score >= threshold)
            notes.append(
                "Classifier output is uncalibrated; returning wave_score instead of wave_probability."
            )
        return payload

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
        model_dir = self.models_dir / _pathogen_slug(pathogen)
        model_dir.mkdir(parents=True, exist_ok=True)

        self._atomic_save_model(regressor_bundle["regressor"], model_dir / "regressor.json")
        self._atomic_save_model(classifier_bundle["classifier"], model_dir / "classifier.json")
        if classifier_bundle.get("calibration") is not None:
            atomic_pickle_dump(classifier_bundle["calibration"], model_dir / "calibration.pkl")
        elif (model_dir / "calibration.pkl").exists():
            (model_dir / "calibration.pkl").unlink()

        atomic_json_dump(metadata, model_dir / "metadata.json")
        atomic_json_dump(backtest, model_dir / "backtest.json")
        atomic_json_dump(dataset_manifest, model_dir / "dataset_manifest.json")

    def _load_artifacts(self, pathogen: str) -> dict[str, Any]:
        model_dir = self.models_dir / _pathogen_slug(pathogen)
        if not model_dir.exists():
            return {}
        paths = {
            "regressor": model_dir / "regressor.json",
            "classifier": model_dir / "classifier.json",
            "calibration": model_dir / "calibration.pkl",
            "metadata": model_dir / "metadata.json",
            "backtest": model_dir / "backtest.json",
            "dataset_manifest": model_dir / "dataset_manifest.json",
        }
        if not paths["regressor"].exists() or not paths["classifier"].exists():
            return {}

        regressor = XGBRegressor()
        regressor.load_model(str(paths["regressor"]))
        classifier = XGBClassifier()
        classifier.load_model(str(paths["classifier"]))
        calibration = None
        if paths["calibration"].exists():
            with open(paths["calibration"], "rb") as handle:
                calibration = pickle.load(handle)

        metadata = self._load_json(paths["metadata"])
        backtest = self._load_json(paths["backtest"])
        dataset_manifest = self._load_json(paths["dataset_manifest"])
        return {
            "regressor": regressor,
            "classifier": classifier,
            "calibration": calibration,
            "metadata": metadata,
            "backtest": backtest,
            "dataset_manifest": dataset_manifest,
        }

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
        X_cal = calibration_frame[feature_columns].fillna(0.0).to_numpy(dtype=float)
        y_cal = calibration_frame["target_wave14"].astype(int).to_numpy()
        if len(np.unique(y_cal)) < 2:
            return None
        raw_scores = classifier.predict_proba(X_cal)[:, 1]
        calibration = IsotonicRegression(out_of_bounds="clip")
        calibration.fit(raw_scores, y_cal)
        return calibration

    @staticmethod
    def _apply_calibration(calibration: IsotonicRegression | None, raw_scores: np.ndarray) -> np.ndarray:
        if calibration is None:
            return raw_scores.astype(float)
        return np.clip(np.asarray(calibration.predict(raw_scores), dtype=float), 0.0, 1.0)

    @staticmethod
    def _select_classification_threshold(
        y_true: np.ndarray,
        score_values: np.ndarray,
        *,
        default_threshold: float,
    ) -> float:
        labels = np.asarray(y_true, dtype=int)
        scores = np.clip(np.asarray(score_values, dtype=float), 0.0, 1.0)
        if len(scores) == 0 or len(np.unique(labels)) < 2:
            return float(default_threshold)

        candidates = {
            float(np.clip(default_threshold, 0.0, 1.0)),
            0.0,
            1.0,
            *[float(value) for value in np.unique(np.round(scores, 6))],
        }
        best_key = None
        best_threshold = float(default_threshold)
        for threshold in sorted(candidates):
            predictions = (scores >= threshold).astype(int)
            precision = float(precision_score(labels, predictions, zero_division=0))
            recall = float(recall_score(labels, predictions, zero_division=0))
            f1 = float(f1_score(labels, predictions, zero_division=0))
            far = false_alarm_rate(labels, predictions)
            candidate = (
                round(f1, 12),
                round(precision, 12),
                round(recall, 12),
                -round(far if far is not None else 1.0, 12),
                round(threshold, 12),
            )
            if best_key is None or candidate > best_key:
                best_key = candidate
                best_threshold = float(threshold)
        return best_threshold

    def _resolve_decision_strategy(
        self,
        *,
        y_true: np.ndarray,
        raw_scores: np.ndarray,
        calibration: IsotonicRegression | None,
        default_threshold: float,
    ) -> dict[str, Any]:
        labels = np.asarray(y_true, dtype=int)
        raw = np.clip(np.asarray(raw_scores, dtype=float), 0.0, 1.0)
        raw_threshold = self._select_classification_threshold(
            labels,
            raw,
            default_threshold=default_threshold,
        )
        raw_predictions = (raw >= raw_threshold).astype(int)
        raw_f1 = float(f1_score(labels, raw_predictions, zero_division=0))
        notes: list[str] = []

        if calibration is None:
            if abs(raw_threshold - float(default_threshold)) > 1e-6:
                notes.append(
                    f"Classification threshold tuned on holdout window: {raw_threshold:.3f}."
                )
            return {
                "use_calibration": False,
                "threshold": raw_threshold,
                "notes": notes,
            }

        calibrated = self._apply_calibration(calibration, raw)
        calibrated_threshold = self._select_classification_threshold(
            labels,
            calibrated,
            default_threshold=default_threshold,
        )
        calibrated_predictions = (calibrated >= calibrated_threshold).astype(int)
        calibrated_f1 = float(f1_score(labels, calibrated_predictions, zero_division=0))
        raw_brier = float(brier_score_loss(labels, raw))
        calibrated_brier = float(brier_score_loss(labels, calibrated))

        if calibrated_brier <= raw_brier + 1e-6 and calibrated_f1 >= raw_f1 - 1e-6:
            if abs(calibrated_threshold - float(default_threshold)) > 1e-6:
                notes.append(
                    f"Classification threshold tuned on calibrated holdout scores: {calibrated_threshold:.3f}."
                )
            return {
                "use_calibration": True,
                "threshold": calibrated_threshold,
                "notes": notes,
            }

        notes.append(
            "Calibration skipped; isotonic mapping degraded holdout decision quality."
        )
        if abs(raw_threshold - float(default_threshold)) > 1e-6:
            notes.append(
                f"Classification threshold tuned on holdout window: {raw_threshold:.3f}."
            )
        return {
            "use_calibration": False,
            "threshold": raw_threshold,
            "notes": notes,
        }

    @staticmethod
    def _compute_calibration_summary(y_true: np.ndarray, probabilities: np.ndarray) -> float:
        from app.services.ml.regional_panel_utils import compute_ece

        return float(compute_ece(y_true, probabilities))

    def _aggregate_fold_metrics(self, folds: list[dict[str, Any]]) -> dict[str, Any]:
        if not folds:
            return {}
        numeric_keys = [
            "mae",
            "rmse",
            "mape",
            "roc_auc",
            "pr_auc",
            "brier_score",
            "precision",
            "recall",
            "f1",
            "ece",
            "false_alarm_rate",
            "mean_lead_time_days",
        ]
        aggregate: dict[str, Any] = {"fold_count": len(folds)}
        for key in numeric_keys:
            values = [float(item[key]) for item in folds if item.get(key) is not None]
            aggregate[key] = float(np.mean(values)) if values else None
        count_keys = ["rows", "positive_rows", "tp", "fp", "tn", "fn"]
        for key in count_keys:
            aggregate[key] = int(sum(int(item.get(key) or 0) for item in folds))
        aggregate["probability_output_folds"] = int(sum(1 for item in folds if item.get("probability_output")))
        aggregate["confusion_matrix"] = {
            "tp": aggregate["tp"],
            "fp": aggregate["fp"],
            "tn": aggregate["tn"],
            "fn": aggregate["fn"],
        }
        return aggregate

    def _dataset_manifest(self, panel: pd.DataFrame) -> dict[str, Any]:
        source_coverage = {
            column: round(float(panel[column].mean()), 4)
            for column in panel.columns
            if column.endswith("_available")
        }
        return {
            "rows": int(len(panel)),
            "pathogens": sorted(str(value) for value in panel["pathogen"].dropna().unique()),
            "regions": sorted(str(value) for value in panel["region"].dropna().unique()),
            "date_range": {
                "start": str(panel["as_of_date"].min()),
                "end": str(panel["as_of_date"].max()),
            },
            "source_coverage": source_coverage,
        }

    @staticmethod
    def _atomic_save_model(model: Any, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp.json")
        os.close(fd)
        try:
            model.save_model(tmp_path)
            os.replace(tmp_path, target)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

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
