"""Pooled regional panel trainer for leakage-safe outbreak forecasting."""

from __future__ import annotations
from app.core.time import utc_now

import json
import logging
import pickle
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier, XGBRegressor

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES, quantile_key
from app.services.ml.benchmarking.leaderboard import build_leaderboard
from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.services.ml.benchmarking.registry import (
    DEFAULT_METRIC_SEMANTICS_VERSION,
    DEFAULT_PROMOTION_MIN_SAMPLE_COUNT,
    ForecastRegistry,
)
from app.services.ml.forecast_orchestrator import ForecastOrchestrator
from app.services.ml.forecast_horizon_utils import (
    apply_probability_calibration,
    build_calibration_guard_split_dates,
    build_calibration_split_dates,
    fit_isotonic_calibrator,
    SUPPORTED_FORECAST_HORIZONS,
    ensure_supported_horizon,
    regional_horizon_support_status,
    regional_model_artifact_dir,
)
from app.services.ml.models.event_classifier import LearnedEventModel
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    TARGET_WINDOW_DAYS,
    activation_policy_for_virus,
    absolute_incidence_threshold,
    activation_false_positive_rate,
    average_precision_safe,
    brier_score_safe,
    build_event_label,
    choose_action_threshold,
    compute_ece,
    event_definition_config_for_virus,
    median_lead_days,
    precision_at_k,
    quality_gate_from_metrics,
    rollout_mode_for_virus,
    signal_bundle_version_for_virus,
    time_based_panel_splits,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
    normalize_weather_forecast_vintage_mode,
)
from app.services.ml import (
    regional_trainer_artifacts,
    regional_trainer_backtest,
    regional_trainer_calibration,
    regional_trainer_hierarchy,
    regional_trainer_orchestration,
    regional_trainer_rollout,
    regional_trainer_training,
)

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"
_REGISTRY_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "forecast_registry"

CALIBRATION_HOLDOUT_FRACTION = 0.20
CALIBRATION_GUARD_FRACTION = 0.35
MIN_CALIBRATION_GUARD_DATES = 7
CALIBRATION_GUARD_EPSILON = 1e-6
HIERARCHY_BLEND_WEIGHT_GRID = tuple(round(value, 2) for value in np.linspace(0.0, 1.0, 11))
HIERARCHY_BLEND_MIN_TOTAL_SAMPLES = 12
HIERARCHY_BLEND_MIN_REGIME_SAMPLES = 6
HIERARCHY_BLEND_EPSILON = 1e-6

REGIONAL_CLASSIFIER_CONFIG: dict[str, Any] = {
    "n_estimators": 160,
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

REGIONAL_REGRESSOR_CONFIG: dict[str, dict[str, Any]] = {
    "median": {
        "n_estimators": 140,
        "max_depth": 4,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.5,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "lower": {
        "n_estimators": 100,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.1,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "upper": {
        "n_estimators": 100,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.9,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
}

EXCLUDED_MODEL_COLUMNS = {
    "virus_typ",
    "bundesland",
    "bundesland_name",
    "as_of_date",
    "target_date",
    "target_week_start",
    "target_window_days",
    "horizon_days",
    "event_definition_version",
    "truth_source",
    "target_truth_source",
    "target_incidence",
    "current_known_incidence",
    "next_week_incidence",
    "seasonal_baseline",
    "seasonal_mad",
    "event_label",
    "y_next_log",
}

TRAINING_ONLY_PANEL_COLUMNS = {
    "target_incidence",
}


def _virus_slug(virus_typ: str) -> str:
    return virus_typ.lower().replace(" ", "_").replace("-", "_")


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _target_window_for_horizon(horizon_days: int) -> list[int]:
    horizon = ensure_supported_horizon(horizon_days)
    return [horizon, horizon]


def _quantile_regressor_config(quantile: float) -> dict[str, Any]:
    if np.isclose(quantile, 0.5):
        config = dict(REGIONAL_REGRESSOR_CONFIG["median"])
    elif quantile < 0.5:
        config = dict(REGIONAL_REGRESSOR_CONFIG["lower"])
    else:
        config = dict(REGIONAL_REGRESSOR_CONFIG["upper"])
    config["quantile_alpha"] = float(quantile)
    return config


def _state_order_from_codes(values: list[str]) -> list[str]:
    present = {str(value) for value in values if str(value)}
    ordered = [state for state in ALL_BUNDESLAENDER if state in present]
    if ordered:
        return ordered
    return sorted(present)


class RegionalModelTrainer:
    """Train pooled per-virus panel models across all Bundesländer."""

    def __init__(self, db, models_dir: Path | None = None) -> None:
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.feature_builder = RegionalFeatureBuilder(db)
        self.registry = ForecastRegistry(registry_root=_REGISTRY_DIR)
        self.orchestrator = ForecastOrchestrator(registry_root=_REGISTRY_DIR)

    def train_region(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        lookback_days: int = 900,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        summary = self.train_all_regions(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
        )
        details = (summary.get("backtest") or {}).get("details") or {}
        return details.get(bundesland.upper(), {"error": f"No summary available for {bundesland.upper()}"})

    def train_all_regions(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
        persist: bool = True,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        return regional_trainer_orchestration.train_all_regions(
            self,
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            persist=persist,
            horizon_days=horizon_days,
            horizon_days_list=horizon_days_list,
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            weather_vintage_comparison=weather_vintage_comparison,
        )

    def _train_single_horizon(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        persist: bool,
        horizon_days: int,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        return regional_trainer_training.train_single_horizon(
            self,
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            persist=persist,
            horizon_days=horizon_days,
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            weather_vintage_comparison=weather_vintage_comparison,
            target_window_for_horizon_fn=_target_window_for_horizon,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            regional_horizon_support_status_fn=regional_horizon_support_status,
            supported_forecast_horizons=SUPPORTED_FORECAST_HORIZONS,
            canonical_forecast_quantiles=CANONICAL_FORECAST_QUANTILES,
            default_metric_semantics_version=DEFAULT_METRIC_SEMANTICS_VERSION,
            default_promotion_min_sample_count=DEFAULT_PROMOTION_MIN_SAMPLE_COUNT,
            event_definition_version=EVENT_DEFINITION_VERSION,
            all_bundeslaender=ALL_BUNDESLAENDER,
            normalize_weather_forecast_vintage_mode_fn=normalize_weather_forecast_vintage_mode,
            regional_model_artifact_dir_fn=regional_model_artifact_dir,
            json_safe_fn=_json_safe,
            utc_now_fn=utc_now,
            logger=logger,
            traceback_module=traceback,
        )

    @staticmethod
    def _training_error_payload(
        *,
        virus_typ: str,
        horizon_days: int,
        exc: Exception,
        lookback_days: int,
    ) -> dict[str, Any]:
        return regional_trainer_training.training_error_payload(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            exc=exc,
            lookback_days=lookback_days,
            target_window_for_horizon_fn=_target_window_for_horizon,
            all_bundeslaender=ALL_BUNDESLAENDER,
            traceback_module=traceback,
        )

    def train_all_viruses_all_regions(
        self,
        lookback_days: int = 900,
        horizon_days: int = 7,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        return regional_trainer_orchestration.train_all_viruses_all_regions(
            self,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            weather_vintage_comparison=weather_vintage_comparison,
            supported_virus_types=SUPPORTED_VIRUS_TYPES,
        )

    def train_selected_viruses_all_regions(
        self,
        *,
        virus_types: list[str] | tuple[str, ...],
        lookback_days: int = 900,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        return regional_trainer_orchestration.train_selected_viruses_all_regions(
            self,
            virus_types=virus_types,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            horizon_days_list=horizon_days_list,
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            weather_vintage_comparison=weather_vintage_comparison,
        )

    @staticmethod
    def _selected_horizons(
        *,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
    ) -> tuple[int, ...]:
        if horizon_days_list is None:
            return (ensure_supported_horizon(horizon_days),)

        normalized: list[int] = []
        seen: set[int] = set()
        for value in horizon_days_list:
            horizon = ensure_supported_horizon(value)
            if horizon in seen:
                continue
            seen.add(horizon)
            normalized.append(horizon)
        if not normalized:
            raise ValueError("horizon_days_list must not be empty")
        return tuple(normalized)

    def _build_training_panel(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        horizon_days: int,
        weather_forecast_vintage_mode: str | None = None,
    ) -> pd.DataFrame:
        builder_kwargs: dict[str, Any] = {
            "virus_typ": virus_typ,
            "lookback_days": lookback_days,
            "horizon_days": horizon_days,
            "include_nowcast": True,
            "use_revision_adjusted": False,
            "revision_policy": "raw",
        }
        if weather_forecast_vintage_mode is not None:
            builder_kwargs["weather_forecast_vintage_mode"] = weather_forecast_vintage_mode
        return self.feature_builder.build_panel_training_data(**builder_kwargs)

    @staticmethod
    def _weather_vintage_metrics_delta(
        legacy_metrics: dict[str, Any],
        vintage_metrics: dict[str, Any],
    ) -> dict[str, float]:
        return regional_trainer_rollout.weather_vintage_metrics_delta(
            legacy_metrics,
            vintage_metrics,
        )

    @staticmethod
    def _weather_vintage_mode_summary(
        *,
        weather_forecast_vintage_mode: str,
        dataset_manifest: dict[str, Any],
        backtest_bundle: dict[str, Any],
        selection: dict[str, Any],
        calibration_mode: str,
    ) -> dict[str, Any]:
        return regional_trainer_rollout.weather_vintage_mode_summary(
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            dataset_manifest=dataset_manifest,
            backtest_bundle=backtest_bundle,
            selection=selection,
            calibration_mode=calibration_mode,
            json_safe_fn=_json_safe,
        )

    def _build_weather_vintage_comparison(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        horizon_days: int,
        primary_summary: dict[str, Any],
        event_config,
    ) -> dict[str, Any]:
        return regional_trainer_rollout.build_weather_vintage_comparison(
            self,
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            primary_summary=primary_summary,
            event_config=event_config,
            normalize_weather_forecast_vintage_mode_fn=normalize_weather_forecast_vintage_mode,
            weather_forecast_vintage_run_timestamp_v1=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            weather_forecast_vintage_disabled=WEATHER_FORECAST_VINTAGE_DISABLED,
            target_window_for_horizon_fn=_target_window_for_horizon,
            json_safe_fn=_json_safe,
        )

    @staticmethod
    def _prepare_horizon_panel(
        panel: pd.DataFrame,
        *,
        horizon_days: int,
    ) -> pd.DataFrame:
        horizon = ensure_supported_horizon(horizon_days)
        if panel.empty:
            return panel.copy()

        working = panel.copy()
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        if "target_date" not in working.columns:
            working["target_date"] = working["as_of_date"] + pd.Timedelta(days=horizon)
        working["target_date"] = pd.to_datetime(working["target_date"]).dt.normalize()
        working["target_window_days"] = [_target_window_for_horizon(horizon)] * len(working)
        working["horizon_days"] = float(horizon)

        future_targets = working[
            ["bundesland", "as_of_date", "current_known_incidence", "truth_source"]
        ].rename(
            columns={
                "as_of_date": "target_date",
                "current_known_incidence": "target_incidence",
                "truth_source": "target_truth_source",
            }
        )
        merged = working.merge(
            future_targets,
            on=["bundesland", "target_date"],
            how="left",
        )
        merged["next_week_incidence"] = merged["target_incidence"]
        merged["truth_source"] = merged["target_truth_source"].fillna(merged["truth_source"])
        merged = merged.loc[merged["target_incidence"].notna()].copy()
        return merged.reset_index(drop=True)

    @staticmethod
    def _state_order_from_panel(panel: pd.DataFrame) -> list[str]:
        present = {str(value) for value in panel.get("bundesland", pd.Series(dtype=str)).dropna().astype(str).tolist()}
        ordered = [state for state in ALL_BUNDESLAENDER if state in present]
        if ordered:
            return ordered
        return sorted(present)

    def _build_hierarchy_metadata(
        self,
        *,
        panel: pd.DataFrame,
        oof_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        return regional_trainer_artifacts.build_hierarchy_metadata(
            self,
            panel=panel,
            oof_frame=oof_frame,
        )

    def get_regional_accuracy_summary(
        self,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
    ) -> list[dict]:
        artifact = self.load_artifacts(virus_typ=virus_typ, horizon_days=horizon_days)
        backtest = artifact.get("backtest") or {}
        details = backtest.get("details") or {}
        summaries: list[dict] = []
        for code, payload in sorted(details.items()):
            metrics = payload.get("metrics") or {}
            summaries.append(
                {
                    "bundesland": code,
                    "name": payload.get("bundesland_name", BUNDESLAND_NAMES.get(code, code)),
                    "horizon_days": int((artifact.get("metadata") or {}).get("horizon_days") or horizon_days),
                    "samples": int(payload.get("total_windows") or 0),
                    "precision": metrics.get("precision"),
                    "recall": metrics.get("recall"),
                    "pr_auc": metrics.get("pr_auc"),
                    "brier_score": metrics.get("brier_score"),
                    "trained_at": (artifact.get("metadata") or {}).get("trained_at"),
                }
            )
        return summaries

    def load_artifacts(self, virus_typ: str, horizon_days: int = 7) -> dict[str, Any]:
        return regional_trainer_orchestration.load_artifacts(
            self,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            regional_model_artifact_dir_fn=regional_model_artifact_dir,
            target_window_for_horizon_fn=_target_window_for_horizon,
            supported_forecast_horizons=SUPPORTED_FORECAST_HORIZONS,
            training_only_panel_columns=TRAINING_ONLY_PANEL_COLUMNS,
            virus_slug_fn=_virus_slug,
        )

    @staticmethod
    def _artifact_payload_from_dir(model_dir: Path) -> dict[str, Any]:
        return regional_trainer_orchestration.artifact_payload_from_dir(
            model_dir,
            json_module=json,
        )

    def _feature_columns(self, panel: pd.DataFrame) -> list[str]:
        columns = [
            column
            for column in panel.columns
            if column not in EXCLUDED_MODEL_COLUMNS and column != "pollen_context_score"
        ]
        return sorted(columns)

    @staticmethod
    def _ww_only_feature_columns(feature_columns: list[str]) -> list[str]:
        return [
            column
            for column in feature_columns
            if column.startswith("ww_")
            or column in {
                "neighbor_ww_level",
                "neighbor_ww_slope7d",
                "national_ww_level",
                "national_ww_slope7d",
                "national_ww_acceleration7d",
            }
        ]

    @staticmethod
    def _invalid_inference_feature_columns(feature_columns: list[str]) -> list[str]:
        return sorted(
            {
                str(column)
                for column in feature_columns
                if str(column) in TRAINING_ONLY_PANEL_COLUMNS
            }
        )

    def _rollout_metadata(
        self,
        *,
        virus_typ: str,
        horizon_days: int = 7,
        aggregate_metrics: dict[str, Any],
        baseline_metrics: dict[str, dict[str, Any]],
        previous_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        return regional_trainer_rollout.rollout_metadata(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            aggregate_metrics=aggregate_metrics,
            baseline_metrics=baseline_metrics,
            previous_artifact=previous_artifact,
            rollout_mode_for_virus_fn=rollout_mode_for_virus,
            activation_policy_for_virus_fn=activation_policy_for_virus,
            signal_bundle_version_for_virus_fn=signal_bundle_version_for_virus,
        )

    @staticmethod
    def _event_labels(
        panel: pd.DataFrame,
        *,
        virus_typ: str,
        tau: float,
        kappa: float,
        event_config=None,
    ) -> np.ndarray:
        config = event_config or event_definition_config_for_virus(virus_typ)
        return np.asarray(
            [
                build_event_label(
                    current_known_incidence=row.current_known_incidence,
                    next_week_incidence=row.next_week_incidence,
                    seasonal_baseline=row.seasonal_baseline,
                    seasonal_mad=row.seasonal_mad,
                    tau=tau,
                    kappa=kappa,
                    min_absolute_incidence=config.min_absolute_incidence,
                )
                for row in panel.itertuples()
            ],
            dtype=int,
        )

    def _select_event_definition(
        self,
        *,
        virus_typ: str,
        panel: pd.DataFrame,
        feature_columns: list[str],
        event_config=None,
    ) -> dict[str, Any]:
        config = event_config or event_definition_config_for_virus(virus_typ)
        best: dict[str, Any] | None = None

        for tau in config.tau_grid:
            for kappa in config.kappa_grid:
                labels = self._event_labels(
                    panel,
                    virus_typ=virus_typ,
                    tau=tau,
                    kappa=kappa,
                    event_config=config,
                )
                if labels.sum() < 12:
                    continue
                evaluation = self._oof_classification_predictions(
                    panel=panel,
                    labels=labels,
                    feature_columns=feature_columns,
                    min_recall_for_threshold=config.min_recall_for_selection,
                )
                if evaluation is None:
                    continue
                threshold, precision, recall = choose_action_threshold(
                    evaluation["event_probability_calibrated"],
                    evaluation["event_label"],
                    min_recall=config.min_recall_for_selection,
                )
                candidate = {
                    "tau": tau,
                    "kappa": kappa,
                    "action_threshold": threshold,
                    "precision": precision,
                    "recall": recall,
                    "pr_auc": average_precision_safe(
                        evaluation["event_label"],
                        evaluation["event_probability_calibrated"],
                    ),
                    "positive_rate": float(np.mean(labels)),
                }
                if best is None:
                    best = candidate
                    continue
                if candidate["precision"] > best["precision"]:
                    best = candidate
                elif np.isclose(candidate["precision"], best["precision"]):
                    if candidate["pr_auc"] > best["pr_auc"] or (
                        np.isclose(candidate["pr_auc"], best["pr_auc"]) and candidate["recall"] > best["recall"]
                    ):
                        best = candidate

        if best is None:
            best = {
                "tau": float(config.tau_grid[min(len(config.tau_grid) // 2, len(config.tau_grid) - 1)]),
                "kappa": float(config.kappa_grid[min(len(config.kappa_grid) // 2, len(config.kappa_grid) - 1)]),
                "action_threshold": 0.6,
                "precision": 0.0,
                "recall": 0.0,
                "pr_auc": 0.0,
                "positive_rate": 0.0,
            }
        return best

    def _oof_classification_predictions(
        self,
        *,
        panel: pd.DataFrame,
        labels: np.ndarray,
        feature_columns: list[str],
        min_recall_for_threshold: float = 0.35,
    ) -> pd.DataFrame | None:
        working = panel.copy()
        working["event_label"] = labels.astype(int)
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        splits = time_based_panel_splits(
            working["as_of_date"],
            n_splits=5,
            min_train_periods=90,
            min_test_periods=21,
        )
        if not splits:
            return None

        oof_frames: list[pd.DataFrame] = []
        for fold_idx, (train_dates, test_dates) in enumerate(splits):
            train_mask = working["as_of_date"].isin(train_dates)
            test_mask = working["as_of_date"].isin(test_dates)
            train_df = working.loc[train_mask].copy()
            test_df = working.loc[test_mask].copy()
            if train_df.empty or test_df.empty or train_df["event_label"].nunique() < 2:
                continue

            calib_split = self._calibration_split_dates(train_dates)
            if not calib_split:
                continue
            model_train_dates, cal_dates = calib_split
            model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
            cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
            if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
                continue

            classifier = self._fit_classifier_from_frame(model_train_df, feature_columns)
            calibration, _calibration_mode = self._select_guarded_calibration(
                calibration_frame=pd.DataFrame(
                    {
                        "as_of_date": cal_df["as_of_date"].values,
                        "event_label": cal_df["event_label"].values.astype(int),
                        "event_probability_raw": classifier.predict_proba(
                            cal_df[feature_columns].to_numpy()
                        )[:, 1],
                    }
                ),
                raw_probability_col="event_probability_raw",
                min_recall_for_threshold=min_recall_for_threshold,
            )
            raw_probs = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
            calibrated_probs = self._apply_calibration(calibration, raw_probs)

            oof_frames.append(
                pd.DataFrame(
                    {
                        "fold": fold_idx,
                        "as_of_date": test_df["as_of_date"].values,
                        "event_label": test_df["event_label"].values,
                        "event_probability_calibrated": calibrated_probs,
                    }
                )
            )

        if not oof_frames:
            return None
        return pd.concat(oof_frames, ignore_index=True)

    def _build_backtest_bundle(
        self,
        *,
        virus_typ: str,
        panel: pd.DataFrame,
        feature_columns: list[str],
        hierarchy_feature_columns: list[str],
        ww_only_columns: list[str],
        tau: float,
        kappa: float,
        action_threshold: float,
        horizon_days: int = 7,
        event_config=None,
    ) -> dict[str, Any]:
        return regional_trainer_backtest.build_backtest_bundle(
            self,
            virus_typ=virus_typ,
            panel=panel,
            feature_columns=feature_columns,
            hierarchy_feature_columns=hierarchy_feature_columns,
            ww_only_columns=ww_only_columns,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            horizon_days=horizon_days,
            event_config=event_config,
            time_based_panel_splits_fn=time_based_panel_splits,
            quality_gate_from_metrics_fn=quality_gate_from_metrics,
        )

    def _hierarchy_reconciled_benchmark_frame(
        self,
        *,
        oof_frame: pd.DataFrame,
        source_panel: pd.DataFrame,
    ) -> pd.DataFrame:
        return regional_trainer_hierarchy.hierarchy_reconciled_benchmark_frame(
            self,
            oof_frame=oof_frame,
            source_panel=source_panel,
            state_order_from_codes_fn=_state_order_from_codes,
        )

    @staticmethod
    def _prepare_hierarchy_history_frame(
        history_rows: list[dict[str, Any]],
    ) -> pd.DataFrame:
        return regional_trainer_hierarchy.prepare_hierarchy_history_frame(history_rows)

    @staticmethod
    def _quantile_blend_metrics(
        history: pd.DataFrame,
        *,
        blend_weight: float,
    ) -> dict[str, float]:
        return regional_trainer_hierarchy.quantile_blend_metrics(
            history,
            blend_weight=blend_weight,
        )

    @staticmethod
    def _blend_weight_improves(
        *,
        baseline_metrics: dict[str, float],
        candidate_metrics: dict[str, float],
    ) -> bool:
        return regional_trainer_hierarchy.blend_weight_improves(
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            epsilon=HIERARCHY_BLEND_EPSILON,
        )

    def _estimate_hierarchy_blend_choice(
        self,
        history_rows: list[dict[str, Any]],
        *,
        target_as_of_date: pd.Timestamp | None = None,
        target_regime: str | None = None,
        target_horizon_days: int | None = None,
        min_total_samples: int = HIERARCHY_BLEND_MIN_TOTAL_SAMPLES,
        min_regime_samples: int = HIERARCHY_BLEND_MIN_REGIME_SAMPLES,
    ) -> dict[str, Any]:
        return regional_trainer_hierarchy.estimate_hierarchy_blend_choice(
            self,
            history_rows,
            target_as_of_date=target_as_of_date,
            target_regime=target_regime,
            target_horizon_days=target_horizon_days,
            min_total_samples=min_total_samples,
            min_regime_samples=min_regime_samples,
            weight_grid=HIERARCHY_BLEND_WEIGHT_GRID,
            blend_epsilon=HIERARCHY_BLEND_EPSILON,
        )

    def _build_hierarchy_blend_policy(
        self,
        history_rows: list[dict[str, Any]],
        *,
        horizon_days: int | None,
    ) -> dict[str, Any]:
        return regional_trainer_hierarchy.build_hierarchy_blend_policy(
            self,
            history_rows,
            horizon_days=horizon_days,
            min_total_samples=HIERARCHY_BLEND_MIN_TOTAL_SAMPLES,
            min_regime_samples=HIERARCHY_BLEND_MIN_REGIME_SAMPLES,
            weight_grid=HIERARCHY_BLEND_WEIGHT_GRID,
            blend_epsilon=HIERARCHY_BLEND_EPSILON,
        )

    def _estimate_hierarchy_blend_weight(
        self,
        history_rows: list[dict[str, Any]],
        *,
        min_samples: int = HIERARCHY_BLEND_MIN_TOTAL_SAMPLES,
    ) -> float:
        return regional_trainer_hierarchy.estimate_hierarchy_blend_weight(
            self,
            history_rows,
            min_samples=min_samples,
            min_regime_samples=HIERARCHY_BLEND_MIN_REGIME_SAMPLES,
            weight_grid=HIERARCHY_BLEND_WEIGHT_GRID,
            blend_epsilon=HIERARCHY_BLEND_EPSILON,
        )

    @staticmethod
    def _blend_hierarchy_quantiles(
        *,
        model_quantiles: dict[float, np.ndarray] | None,
        baseline_quantiles: dict[float, np.ndarray],
        blend_weight: float,
    ) -> dict[float, np.ndarray]:
        return regional_trainer_hierarchy.blend_hierarchy_quantiles(
            model_quantiles=model_quantiles,
            baseline_quantiles=baseline_quantiles,
            blend_weight=blend_weight,
        )

    def _hierarchy_component_diagnostics(
        self,
        *,
        oof_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        return regional_trainer_hierarchy.hierarchy_component_diagnostics(
            self,
            oof_frame=oof_frame,
            min_total_samples=HIERARCHY_BLEND_MIN_TOTAL_SAMPLES,
            min_regime_samples=HIERARCHY_BLEND_MIN_REGIME_SAMPLES,
            weight_grid=HIERARCHY_BLEND_WEIGHT_GRID,
            blend_epsilon=HIERARCHY_BLEND_EPSILON,
        )

    def _predict_hierarchy_aggregate_quantiles(
        self,
        *,
        frame: pd.DataFrame,
        source_panel: pd.DataFrame,
        feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
        hierarchy_models: dict[str, dict[str, XGBRegressor] | None] | None = None,
        state_feature_columns: list[str] | None = None,
        hierarchy_model_modes: dict[str, str] | None = None,
    ) -> dict[str, list[Any]]:
        return regional_trainer_hierarchy.predict_hierarchy_aggregate_quantiles(
            self,
            frame=frame,
            source_panel=source_panel,
            feature_columns=feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
            hierarchy_models=hierarchy_models,
            state_feature_columns=state_feature_columns,
            hierarchy_model_modes=hierarchy_model_modes,
        )

    @staticmethod
    def _hierarchy_apply_residual_prediction(
        *,
        baseline: np.ndarray,
        residual_log: np.ndarray,
    ) -> np.ndarray:
        return regional_trainer_hierarchy.hierarchy_apply_residual_prediction(
            baseline=baseline,
            residual_log=residual_log,
        )

    def _hierarchy_state_baseline_features(
        self,
        *,
        date_slice: pd.DataFrame,
        cluster_assignments: dict[str, str],
        state_feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
    ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
        return regional_trainer_hierarchy.hierarchy_state_baseline_features(
            date_slice=date_slice,
            cluster_assignments=cluster_assignments,
            state_feature_columns=state_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
        )

    @staticmethod
    def _apply_hierarchy_baseline_map(
        frame: pd.DataFrame,
        *,
        baseline_map: dict[str, dict[str, float]],
    ) -> pd.DataFrame:
        return regional_trainer_hierarchy.apply_hierarchy_baseline_map(
            frame,
            baseline_map=baseline_map,
        )

    def _build_hierarchy_training_frame(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        state_feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
        level: str,
        target_mode: str = "direct_log",
    ) -> pd.DataFrame:
        return regional_trainer_hierarchy.build_hierarchy_training_frame(
            self,
            panel=panel,
            feature_columns=feature_columns,
            state_feature_columns=state_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
            level=level,
            target_mode=target_mode,
        )

    def _fit_hierarchy_models(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        state_feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
    ) -> tuple[dict[str, dict[str, XGBRegressor] | None], dict[str, str]]:
        return regional_trainer_hierarchy.fit_hierarchy_models(
            self,
            panel=panel,
            feature_columns=feature_columns,
            state_feature_columns=state_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
            regressor_config=REGIONAL_REGRESSOR_CONFIG,
        )

    def _fit_final_models(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        hierarchy_feature_columns: list[str],
        oof_frame: pd.DataFrame,
        action_threshold: float = 0.5,
    ) -> dict[str, Any]:
        return regional_trainer_artifacts.fit_final_models(
            self,
            panel=panel,
            feature_columns=feature_columns,
            hierarchy_feature_columns=hierarchy_feature_columns,
            oof_frame=oof_frame,
            action_threshold=action_threshold,
            regressor_config=REGIONAL_REGRESSOR_CONFIG,
            supported_quantiles=CANONICAL_FORECAST_QUANTILES,
            quantile_regressor_config_fn=_quantile_regressor_config,
            learned_event_model_cls=LearnedEventModel,
            calibration_holdout_fraction=CALIBRATION_HOLDOUT_FRACTION,
        )

    def _persist_artifacts(
        self,
        *,
        model_dir: Path,
        final_artifacts: dict[str, Any],
        metadata: dict[str, Any],
        backtest_payload: dict[str, Any],
        dataset_manifest: dict[str, Any],
        point_in_time_manifest: dict[str, Any],
    ) -> None:
        regional_trainer_artifacts.persist_artifacts(
            model_dir=model_dir,
            final_artifacts=final_artifacts,
            metadata=metadata,
            backtest_payload=backtest_payload,
            dataset_manifest=dataset_manifest,
            point_in_time_manifest=point_in_time_manifest,
            json_safe_fn=_json_safe,
            quantile_key_fn=quantile_key,
            event_definition_version=EVENT_DEFINITION_VERSION,
            target_window_days=TARGET_WINDOW_DAYS,
        )

    @staticmethod
    def _calibration_split_dates(train_dates: list[pd.Timestamp]) -> tuple[list[pd.Timestamp], list[pd.Timestamp]] | None:
        return build_calibration_split_dates(
            train_dates,
            holdout_fraction=CALIBRATION_HOLDOUT_FRACTION,
            min_total_dates=35,
            min_holdout_dates=14,
            min_train_dates=20,
        )

    @staticmethod
    def _calibration_guard_split_dates(
        calibration_dates: list[pd.Timestamp],
    ) -> tuple[list[pd.Timestamp], list[pd.Timestamp]] | None:
        return build_calibration_guard_split_dates(
            calibration_dates,
            guard_fraction=CALIBRATION_GUARD_FRACTION,
            min_guard_dates=MIN_CALIBRATION_GUARD_DATES,
        )

    @staticmethod
    def _fit_classifier(
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> XGBClassifier:
        positives = max(int(np.sum(y == 1)), 1)
        negatives = max(int(np.sum(y == 0)), 1)
        config = dict(REGIONAL_CLASSIFIER_CONFIG)
        config["scale_pos_weight"] = float(negatives / positives)
        model = XGBClassifier(**config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    @staticmethod
    def _fit_regressor(
        X: np.ndarray,
        y: np.ndarray,
        *,
        config: dict[str, Any],
        sample_weight: np.ndarray | None = None,
    ) -> XGBRegressor:
        model = XGBRegressor(**config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    def _sample_weights(self, frame: pd.DataFrame) -> np.ndarray | None:
        return None

    def _fit_classifier_from_frame(self, frame: pd.DataFrame, feature_columns: list[str]) -> XGBClassifier:
        return self._fit_classifier(
            frame[feature_columns].to_numpy(),
            frame["event_label"].to_numpy(),
            sample_weight=self._sample_weights(frame),
        )

    def _fit_regressor_from_frame(
        self,
        frame: pd.DataFrame,
        feature_columns: list[str],
        config: dict[str, Any],
        target_col: str = "y_next_log",
    ) -> XGBRegressor:
        return self._fit_regressor(
            frame[feature_columns].to_numpy(),
            frame[target_col].to_numpy(),
            config=config,
            sample_weight=self._sample_weights(frame),
        )

    @staticmethod
    def _fit_isotonic(raw_probabilities: np.ndarray, labels: np.ndarray) -> IsotonicRegression | None:
        return fit_isotonic_calibrator(
            raw_probabilities,
            labels,
            min_samples=20,
            min_class_support=1,
        )

    @staticmethod
    def _apply_calibration(calibration: IsotonicRegression | None, raw_probabilities: np.ndarray) -> np.ndarray:
        return apply_probability_calibration(calibration, raw_probabilities)

    @staticmethod
    def _calibration_guard_metrics(
        *,
        as_of_dates: Any,
        labels: np.ndarray,
        probabilities: np.ndarray,
        action_threshold: float,
    ) -> dict[str, float]:
        return regional_trainer_calibration.calibration_guard_metrics(
            as_of_dates=as_of_dates,
            labels=labels,
            probabilities=probabilities,
            action_threshold=action_threshold,
            apply_calibration_fn=RegionalModelTrainer._apply_calibration,
            pd_module=pd,
            np_module=np,
            brier_score_safe_fn=brier_score_safe,
            compute_ece_fn=compute_ece,
            precision_at_k_fn=precision_at_k,
            activation_false_positive_rate_fn=activation_false_positive_rate,
        )

    def _select_guarded_calibration(
        self,
        *,
        calibration_frame: pd.DataFrame,
        raw_probability_col: str,
        action_threshold: float | None = None,
        min_recall_for_threshold: float = 0.35,
        label_col: str = "event_label",
        date_col: str = "as_of_date",
    ) -> tuple[IsotonicRegression | None, str]:
        return regional_trainer_calibration.select_guarded_calibration(
            self,
            calibration_frame=calibration_frame,
            raw_probability_col=raw_probability_col,
            action_threshold=action_threshold,
            min_recall_for_threshold=min_recall_for_threshold,
            label_col=label_col,
            date_col=date_col,
            calibration_guard_epsilon=CALIBRATION_GUARD_EPSILON,
            choose_action_threshold_fn=choose_action_threshold,
        )

    def _amelag_only_probabilities(
        self,
        *,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        feature_columns: list[str],
    ) -> np.ndarray:
        if not feature_columns or train_df["event_label"].nunique() < 2:
            base_rate = float(train_df["event_label"].mean() or 0.0)
            return np.full(len(test_df), base_rate, dtype=float)

        classifier = self._fit_classifier_from_frame(train_df, feature_columns)
        raw_prob = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
        train_raw = classifier.predict_proba(train_df[feature_columns].to_numpy())[:, 1]
        calibration = self._fit_isotonic(train_raw, train_df["event_label"].to_numpy())
        return self._apply_calibration(calibration, raw_prob)

    @staticmethod
    def _event_probability_from_prediction(
        *,
        predicted_next: np.ndarray,
        current_known: np.ndarray,
        baseline: np.ndarray,
        mad: np.ndarray,
        tau: float,
        kappa: float,
        min_absolute_incidence: float,
    ) -> np.ndarray:
        predicted_next = np.asarray(predicted_next, dtype=float)
        current_known = np.asarray(current_known, dtype=float)
        baseline = np.asarray(baseline, dtype=float)
        mad = np.maximum(np.asarray(mad, dtype=float), 1.0)

        relative_gap = np.log1p(np.maximum(predicted_next, 0.0)) - np.log1p(np.maximum(current_known, 0.0)) - tau
        absolute_threshold = np.asarray(
            [
                absolute_incidence_threshold(
                    seasonal_baseline=baseline_value,
                    seasonal_mad=mad_value,
                    kappa=kappa,
                    min_absolute_incidence=min_absolute_incidence,
                )
                for baseline_value, mad_value in zip(baseline, mad, strict=False)
            ],
            dtype=float,
        )
        absolute_gap = (predicted_next - absolute_threshold) / mad
        logits = np.minimum(relative_gap / max(tau, 0.05), absolute_gap)
        return 1.0 / (1.0 + np.exp(-logits))

    @staticmethod
    def _aggregate_metrics(frame: pd.DataFrame, *, action_threshold: float) -> dict[str, float]:
        return regional_trainer_backtest.aggregate_metrics(
            frame,
            action_threshold=action_threshold,
        )

    def _baseline_metrics(self, frame: pd.DataFrame, *, action_threshold: float) -> dict[str, dict[str, float]]:
        return regional_trainer_backtest.baseline_metrics(
            self,
            frame,
            action_threshold=action_threshold,
        )

    def _build_backtest_payload(
        self,
        *,
        frame: pd.DataFrame,
        aggregate_metrics: dict[str, float],
        baselines: dict[str, dict[str, float]],
        quality_gate: dict[str, Any],
        tau: float,
        kappa: float,
        action_threshold: float,
        fold_selection_summary: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return regional_trainer_backtest.build_backtest_payload(
            self,
            frame=frame,
            aggregate_metrics=aggregate_metrics,
            baselines=baselines,
            quality_gate=quality_gate,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            fold_selection_summary=fold_selection_summary,
        )

    @staticmethod
    def _activation_mask(state_frame: pd.DataFrame, *, action_threshold: float) -> pd.Series:
        return regional_trainer_backtest.activation_mask(
            state_frame,
            action_threshold=action_threshold,
        )

    @staticmethod
    def _state_precision_recall(state_frame: pd.DataFrame, *, action_threshold: float) -> tuple[float, float]:
        return regional_trainer_backtest.state_precision_recall(
            state_frame,
            action_threshold=action_threshold,
        )


# Backward-compatible alias for scripts and older imports.
RegionalTrainer = RegionalModelTrainer
