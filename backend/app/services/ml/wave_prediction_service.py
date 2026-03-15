"""Stage-1 leakage-safe wave prediction service."""

from __future__ import annotations

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
        trained_at = datetime.utcnow().isoformat()
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

        calibration = None
        calibration_notes: list[str] = []
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

        return {
            "classifier": classifier,
            "calibration": calibration,
            "feature_columns": features,
            "threshold": float(self.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD),
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
                "generated_at": datetime.utcnow().isoformat(),
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
                "generated_at": datetime.utcnow().isoformat(),
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
            "generated_at": datetime.utcnow().isoformat(),
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
        return {
            "wastewater": self.feature_builder._load_wastewater_daily(pathogen, start_date),
            "truth": self.feature_builder._load_truth_series(pathogen, start_date),
            "grippeweb": self.feature_builder._load_grippeweb_signals(start_date, end_date),
            "influenza_ifsg": self.feature_builder._load_influenza_ifsg(start_date, end_date),
            "rsv_ifsg": self.feature_builder._load_rsv_ifsg(start_date, end_date),
            "are_consultation": self.feature_builder._load_are_konsultation(start_date, end_date),
            "weather": self.feature_builder._load_weather(start_date, end_date),
            "holidays": self.feature_builder._load_holidays(),
            "populations": self.feature_builder._load_state_population_map(),
        }

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
        truth = self._coerce_frame(source_frames.get("truth"))
        if truth.empty:
            return []

        wastewater = self._coerce_frame(source_frames.get("wastewater"))
        grippeweb = self._coerce_frame(source_frames.get("grippeweb"))
        influenza_ifsg = self._coerce_frame(source_frames.get("influenza_ifsg"))
        rsv_ifsg = self._coerce_frame(source_frames.get("rsv_ifsg"))
        are_consultation = self._coerce_frame(source_frames.get("are_consultation"))
        weather = self._coerce_frame(source_frames.get("weather"))
        holidays = source_frames.get("holidays") or {}
        populations = source_frames.get("populations") or {}
        label_config = wave_label_config_for_pathogen(pathogen, self.settings)

        truth_by_state = {
            state: frame.sort_values("week_start").reset_index(drop=True)
            for state, frame in truth.groupby("bundesland")
        }
        wastewater_by_state = self._group_by_state(wastewater)
        influenza_by_state = self._group_by_state(influenza_ifsg)
        rsv_by_state = self._group_by_state(rsv_ifsg)
        are_consultation_by_state = self._group_by_state(are_consultation)
        weather_by_state = self._group_by_state(weather)
        grippeweb_by_key = (
            {
                (signal_type, state): frame.sort_values("datum").reset_index(drop=True)
                for (signal_type, state), frame in grippeweb.dropna(subset=["bundesland"]).groupby(["signal_type", "bundesland"])
            }
            if not grippeweb.empty
            else {}
        )

        rows: list[dict[str, Any]] = []
        target_regions = [region_code] if region_code else sorted(truth_by_state.keys())
        date_index = pd.date_range(start_date, end_date, freq="D")
        for state in target_regions:
            truth_state = truth_by_state.get(state)
            if truth_state is None or truth_state.empty:
                continue

            wastewater_state = wastewater_by_state.get(state, pd.DataFrame())
            influenza_state = influenza_by_state.get(state, pd.DataFrame())
            rsv_state = rsv_by_state.get(state, pd.DataFrame())
            are_state = are_consultation_by_state.get(state, pd.DataFrame())
            weather_state = weather_by_state.get(state, pd.DataFrame())
            grippeweb_are_state = grippeweb_by_key.get(("ARE", state), pd.DataFrame())
            grippeweb_ili_state = grippeweb_by_key.get(("ILI", state), pd.DataFrame())

            truth_feature_frame = truth_state.assign(datum=pd.to_datetime(truth_state["available_date"]).dt.normalize())
            for as_of in date_index:
                visible_truth = truth_state.loc[truth_state["available_date"] <= as_of].copy()
                if visible_truth.empty:
                    continue

                target_date = (as_of + pd.Timedelta(days=horizon_days)).normalize()
                target_week_start = target_date - pd.Timedelta(days=target_date.weekday())
                target_row = truth_state.loc[truth_state["week_start"] == target_week_start]
                if target_row.empty:
                    continue

                future_truth = truth_state.loc[
                    (truth_state["week_start"] > as_of) & (truth_state["week_start"] <= as_of + pd.Timedelta(days=horizon_days))
                ].copy()
                current_truth = visible_truth.iloc[-1]
                wave_label, wave_event_date = label_wave_start(future_truth, visible_truth, label_config)

                wastewater_visible = self._visible_as_of(wastewater_state, as_of)
                influenza_visible = self._visible_as_of(influenza_state, as_of)
                rsv_visible = self._visible_as_of(rsv_state, as_of)
                are_visible = self._visible_as_of(are_state, as_of)
                grippeweb_are_visible = self._visible_as_of(grippeweb_are_state, as_of)
                grippeweb_ili_visible = self._visible_as_of(grippeweb_ili_state, as_of)

                truth_features = build_daily_signal_features(
                    truth_feature_frame.loc[truth_feature_frame["available_date"] <= as_of].assign(
                        datum=pd.to_datetime(truth_feature_frame["datum"]).dt.normalize(),
                        value=truth_feature_frame["incidence"].astype(float),
                    ),
                    as_of=as_of,
                    prefix="truth",
                    date_col="datum",
                    value_col="value",
                )
                wastewater_features = build_daily_signal_features(
                    wastewater_visible.assign(
                        signal_date=pd.to_datetime(wastewater_visible["available_time"]).dt.normalize(),
                        value=wastewater_visible["viral_load"].astype(float),
                    ) if not wastewater_visible.empty else wastewater_visible,
                    as_of=as_of,
                    prefix="wastewater",
                    date_col="signal_date",
                    value_col="value",
                )
                symptom_are_features = build_daily_signal_features(
                    grippeweb_are_visible.assign(
                        signal_date=pd.to_datetime(grippeweb_are_visible["available_time"]).dt.normalize(),
                        value=grippeweb_are_visible["incidence"].astype(float),
                    ) if not grippeweb_are_visible.empty else grippeweb_are_visible,
                    as_of=as_of,
                    prefix="grippeweb_are",
                    date_col="signal_date",
                    value_col="value",
                )
                symptom_ili_features = build_daily_signal_features(
                    grippeweb_ili_visible.assign(
                        signal_date=pd.to_datetime(grippeweb_ili_visible["available_time"]).dt.normalize(),
                        value=grippeweb_ili_visible["incidence"].astype(float),
                    ) if not grippeweb_ili_visible.empty else grippeweb_ili_visible,
                    as_of=as_of,
                    prefix="grippeweb_ili",
                    date_col="signal_date",
                    value_col="value",
                )
                consultation_features = build_daily_signal_features(
                    are_visible.assign(
                        signal_date=pd.to_datetime(are_visible["available_time"]).dt.normalize(),
                        value=are_visible["incidence"].astype(float),
                    ) if not are_visible.empty else are_visible,
                    as_of=as_of,
                    prefix="consultation_are",
                    date_col="signal_date",
                    value_col="value",
                )
                virus_ifsg_frame = influenza_visible if pathogen in {"Influenza A", "Influenza B"} else rsv_visible if pathogen == "RSV A" else pd.DataFrame()
                virus_ifsg_features = build_daily_signal_features(
                    virus_ifsg_frame.assign(
                        signal_date=pd.to_datetime(virus_ifsg_frame["available_time"]).dt.normalize(),
                        value=virus_ifsg_frame["incidence"].astype(float),
                    ) if not virus_ifsg_frame.empty else virus_ifsg_frame,
                    as_of=as_of,
                    prefix="virus_ifsg",
                    date_col="signal_date",
                    value_col="value",
                )
                weather_features = weather_context_features(
                    weather_state,
                    as_of=as_of,
                    enable_forecast_weather=bool(self.settings.WAVE_PREDICTION_ENABLE_FORECAST_WEATHER),
                )
                holiday_features = school_holiday_features(
                    holidays.get(state, []),
                    as_of=as_of,
                    horizon_days=horizon_days,
                )

                row = {
                    "as_of_date": as_of,
                    "region": state,
                    "region_name": BUNDESLAND_NAMES.get(state, state),
                    "pathogen": pathogen,
                    "pathogen_slug": _pathogen_slug(pathogen),
                    "horizon_days": horizon_days,
                    "target_date": target_date,
                    "target_week_start": target_week_start,
                    "target_window_end": as_of + pd.Timedelta(days=horizon_days),
                    "source_truth_week_start": pd.Timestamp(current_truth["week_start"]).normalize(),
                    "source_truth_available_date": pd.Timestamp(current_truth["available_date"]).normalize(),
                    "truth_source": str(current_truth.get("truth_source") or "unknown"),
                    "target_regression": float(target_row.iloc[0]["incidence"] or 0.0),
                    "target_regression_log": float(np.log1p(max(float(target_row.iloc[0]["incidence"] or 0.0), 0.0))),
                    "target_wave14": int(wave_label),
                    "wave_event_date": wave_event_date,
                    "wave_event_reason": "ruleset_event" if wave_label else None,
                    "future_truth_max": float(future_truth["incidence"].max() or 0.0) if not future_truth.empty else 0.0,
                    "future_truth_growth_ratio": self._growth_ratio(future_truth),
                    "raw_truth_incidence": float(current_truth["incidence"] or 0.0),
                    "raw_wastewater_level": self._latest_column_value(wastewater_visible, "viral_load"),
                    "raw_grippeweb_are": self._latest_column_value(grippeweb_are_visible, "incidence"),
                    "raw_grippeweb_ili": self._latest_column_value(grippeweb_ili_visible, "incidence"),
                    "raw_consultation_are": self._latest_column_value(are_visible, "incidence"),
                    "raw_virus_ifsg": self._latest_column_value(virus_ifsg_frame, "incidence"),
                    "raw_weather_temp": self._latest_column_value(
                        weather_state.loc[
                            weather_state["datum"] <= as_of
                        ] if not weather_state.empty else weather_state,
                        "temp",
                    ),
                    "raw_weather_humidity": self._latest_column_value(
                        weather_state.loc[
                            weather_state["datum"] <= as_of
                        ] if not weather_state.empty else weather_state,
                        "humidity",
                    ),
                }
                row.update(truth_features)
                row.update(wastewater_features)
                row.update(symptom_are_features)
                row.update(symptom_ili_features)
                row.update(consultation_features)
                row.update(virus_ifsg_features)
                row.update(weather_features)
                row.update(holiday_features)
                if bool(self.settings.WAVE_PREDICTION_ENABLE_DEMOGRAPHICS):
                    row["population"] = float(populations.get(state) or 0.0)
                if bool(self.settings.WAVE_PREDICTION_ENABLE_INTERACTIONS):
                    symptom_level = max(
                        float(row.get("consultation_are_level") or 0.0),
                        float(row.get("grippeweb_are_level") or 0.0),
                    )
                    row["wastewater_x_humidity"] = float(row.get("wastewater_level", 0.0) * row.get("avg_humidity_7", 0.0))
                    row["incidence_x_holiday"] = float(row.get("truth_level", 0.0) * row.get("is_school_holiday", 0.0))
                    row["symptomburden_x_weather"] = float(symptom_level * row.get("avg_temp_7", 0.0))
                    row["wastewater_minus_incidence_zscore"] = float(
                        row.get("wastewater_zscore_28", 0.0) - row.get("truth_zscore_28", 0.0)
                    )

                row["month"] = float(as_of.month)
                row["week_of_year"] = float(as_of.isocalendar().week)
                row["quarter"] = float(as_of.quarter)
                row["day_of_year"] = float(as_of.dayofyear)
                rows.append(row)
        return rows

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
        if frame is None or frame.empty:
            return pd.DataFrame()
        visible = frame.copy()
        if "available_time" in visible.columns:
            visible = visible.loc[pd.to_datetime(visible["available_time"]) <= as_of].copy()
        if "datum" in visible.columns:
            visible = visible.loc[pd.to_datetime(visible["datum"]).dt.normalize() <= as_of].copy()
        return visible.sort_values("datum").reset_index(drop=True)

    @staticmethod
    def _group_by_state(frame: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
        if frame is None or frame.empty or "bundesland" not in frame.columns:
            return {}
        return {
            state: part.sort_values("datum").reset_index(drop=True)
            for state, part in frame.groupby("bundesland")
        }

    @staticmethod
    def _coerce_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
        if frame is None:
            return pd.DataFrame()
        return frame.copy()

    @staticmethod
    def _latest_column_value(frame: pd.DataFrame | None, column: str) -> float:
        if frame is None or frame.empty or column not in frame.columns:
            return 0.0
        return float(frame.iloc[-1][column] or 0.0)

    @staticmethod
    def _growth_ratio(future_truth: pd.DataFrame) -> float:
        if future_truth is None or future_truth.empty or len(future_truth) < 2:
            return 0.0
        values = future_truth["incidence"].astype(float)
        return float((values.iloc[-1] - values.iloc[0]) / max(abs(values.iloc[0]), 1.0))

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
        return pd.Timestamp(datetime.utcnow()).normalize()
