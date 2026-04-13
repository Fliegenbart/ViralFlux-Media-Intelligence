from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.baselines import persistence_quantiles, seasonal_quantiles
from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.core.time import utc_now
from app.services.ml.benchmarking.leaderboard import build_leaderboard
from app.services.ml.benchmarking.metrics import brier_decomposition, summarize_probabilistic_metrics
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.regional_residual_forecast import (
    apply_residual_quantiles,
    baseline_center_log,
    mixture_quantiles_via_cdf,
    optimize_baseline_weights,
    optimize_persistence_mix_weight,
)
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    TARGET_WINDOW_DAYS,
    activation_false_positive_rate,
    average_precision_safe,
    brier_score_safe,
    compute_ece,
    event_definition_config_for_virus,
    median_lead_days,
    precision_at_k,
    quality_gate_from_metrics,
    time_based_panel_splits,
)

EVENT_DELTA_METRICS: tuple[str, ...] = (
    "pr_auc",
    "brier_score",
    "ece",
    "precision_at_top3",
)
LOSS_METRICS: frozenset[str] = frozenset(
    {
        "wis",
        "crps",
        "brier_score",
        "ece",
        "activation_false_positive_rate",
    }
)
BOOTSTRAP_RANDOM_SEED = 42
BOOTSTRAP_ITERATIONS = max(int(os.getenv("REGIONAL_EVENT_BOOTSTRAP_ITERATIONS", "2000")), 1)
FOLD_VIABILITY_MIN_POSITIVE_EVENTS = 5
FOLD_VIABILITY_MIN_POSITIVE_REGIONS = 2
EVENT_EVALUATION_MODE = "viable_folds_discrimination_v1"
EVENT_DISCRIMINATION_CHECKS: frozenset[str] = frozenset(
    {"precision_at_top3_passed", "pr_auc_passed"}
)


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
    horizon = int(horizon_days)
    return [horizon, horizon]


def _minimum_viable_event_folds(total_folds: int) -> int:
    total = max(int(total_folds), 0)
    if total <= 1:
        return total
    # Allow one seasonally degenerate fold without invalidating the whole event task.
    return max(1, total - 1)


def _event_viability_reason(*, positive_count: int, positive_regions: int) -> str:
    if positive_count <= 0:
        return "no_positive_events"
    if positive_regions <= 0:
        return "no_positive_regions"
    return "insufficient_positive_support"


def _summarize_event_fold_viability(frame: pd.DataFrame) -> dict[str, Any]:
    fold_rows: list[dict[str, Any]] = []
    for fold, fold_frame in frame.groupby("fold", dropna=False):
        positives = fold_frame.loc[fold_frame["event_label"] == 1]
        positive_count = int(len(positives))
        positive_regions = int(positives["bundesland"].astype(str).nunique())
        event_viable = (
            positive_count >= FOLD_VIABILITY_MIN_POSITIVE_EVENTS
            and positive_regions >= FOLD_VIABILITY_MIN_POSITIVE_REGIONS
        )
        fold_rows.append(
            {
                "fold": int(fold),
                "positive_count": positive_count,
                "positive_regions": positive_regions,
                "event_viable": bool(event_viable),
                "event_viability_reason": (
                    "sufficient_positive_support"
                    if event_viable
                    else _event_viability_reason(
                        positive_count=positive_count,
                        positive_regions=positive_regions,
                    )
                ),
            }
        )
    fold_rows.sort(key=lambda item: int(item["fold"]))
    total_folds = len(fold_rows)
    viable_fold_ids = [int(item["fold"]) for item in fold_rows if bool(item["event_viable"])]
    non_viable_fold_ids = [int(item["fold"]) for item in fold_rows if not bool(item["event_viable"])]
    minimum_viable_folds = _minimum_viable_event_folds(total_folds)
    viable_fold_count = len(viable_fold_ids)
    return {
        "mode": EVENT_EVALUATION_MODE,
        "min_positive_events": FOLD_VIABILITY_MIN_POSITIVE_EVENTS,
        "min_positive_regions": FOLD_VIABILITY_MIN_POSITIVE_REGIONS,
        "minimum_viable_folds": minimum_viable_folds,
        "total_folds": total_folds,
        "viable_fold_count": viable_fold_count,
        "non_viable_fold_count": len(non_viable_fold_ids),
        "passed": viable_fold_count >= minimum_viable_folds,
        "viable_folds": viable_fold_ids,
        "non_viable_folds": non_viable_fold_ids,
        "folds": [
            {
                "fold": int(item["fold"]),
                "positive_count": int(item["positive_count"]),
                "positive_regions": int(item["positive_regions"]),
                "passed": bool(item["event_viable"]),
                "event_viable": bool(item["event_viable"]),
                "event_viability_reason": str(item["event_viability_reason"]),
            }
            for item in fold_rows
        ],
    }


def _event_evaluation_frames(
    frame: pd.DataFrame,
    *,
    fold_viability: dict[str, Any] | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = fold_viability or _summarize_event_fold_viability(frame)
    viable_folds = {int(value) for value in (summary.get("viable_folds") or [])}
    non_viable_folds = {int(value) for value in (summary.get("non_viable_folds") or [])}
    viable_frame = (
        frame.loc[frame["fold"].isin(viable_folds)].copy()
        if viable_folds and "fold" in frame.columns
        else frame.iloc[0:0].copy()
    )
    non_viable_frame = (
        frame.loc[frame["fold"].isin(non_viable_folds)].copy()
        if non_viable_folds and "fold" in frame.columns
        else frame.iloc[0:0].copy()
    )
    return viable_frame, non_viable_frame


def _event_path_metrics(
    frame: pd.DataFrame,
    *,
    score_col: str,
    action_threshold: float | None,
    fold_viability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = _event_probability_metrics(
        frame,
        score_col=score_col,
        action_threshold=action_threshold,
    )
    viable_frame, _ = _event_evaluation_frames(frame, fold_viability=fold_viability)
    discrimination_available = not viable_frame.empty and viable_frame["event_label"].nunique() >= 2
    if discrimination_available:
        viable_metrics = _event_probability_metrics(
            viable_frame,
            score_col=score_col,
            action_threshold=action_threshold,
        )
        metrics["precision_at_top3"] = viable_metrics["precision_at_top3"]
        metrics["pr_auc"] = viable_metrics["pr_auc"]
    else:
        metrics["precision_at_top3"] = 0.0
        metrics["pr_auc"] = 0.0
    metrics["event_discrimination_available"] = bool(discrimination_available)
    metrics["event_evaluation_mode"] = EVENT_EVALUATION_MODE
    metrics["event_viable_fold_count"] = int((fold_viability or {}).get("viable_fold_count") or 0)
    metrics["event_non_viable_fold_count"] = int((fold_viability or {}).get("non_viable_fold_count") or 0)
    metrics["event_minimum_viable_folds"] = int((fold_viability or {}).get("minimum_viable_folds") or 0)
    metrics["event_viability_passed"] = bool((fold_viability or {}).get("passed"))
    metrics["event_discrimination_rows"] = int(len(viable_frame))
    metrics["event_discrimination_positive_count"] = int(viable_frame["event_label"].sum()) if not viable_frame.empty else 0
    return metrics


def _non_viable_fold_monitoring(
    frame: pd.DataFrame,
    *,
    score_col: str,
    action_threshold: float | None,
    fold_viability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _, non_viable_frame = _event_evaluation_frames(frame, fold_viability=fold_viability)
    if non_viable_frame.empty:
        return {
            "available": False,
            "fold_count": 0,
            "rows": 0,
        }
    probabilities = non_viable_frame[score_col].to_numpy(dtype=float)
    if action_threshold is None and "action_threshold" in non_viable_frame.columns:
        thresholds = non_viable_frame["action_threshold"].to_numpy(dtype=float)
        activations = int(np.sum(probabilities >= thresholds))
    else:
        effective_threshold = float(action_threshold or 0.5)
        activations = int(np.sum(probabilities >= effective_threshold))
    return {
        "available": True,
        "fold_count": int(non_viable_frame["fold"].nunique()),
        "rows": int(len(non_viable_frame)),
        "mean_probability": round(float(np.mean(probabilities)), 6),
        "max_probability": round(float(np.max(probabilities)), 6),
        "activation_rate": round(float(activations / max(len(non_viable_frame), 1)), 6),
        "activation_false_positive_rate": activation_false_positive_rate(
            non_viable_frame,
            threshold=action_threshold,
            score_col=score_col,
        ),
        "brier_score": round(
            brier_score_safe(
                non_viable_frame["event_label"].to_numpy(dtype=int),
                probabilities,
            ),
            6,
        ),
        "ece": round(
            compute_ece(
                non_viable_frame["event_label"].to_numpy(dtype=int),
                probabilities,
            ),
            6,
        ),
    }


def _regressor_config_for_quantile(quantile: float) -> dict[str, Any]:
    if np.isclose(float(quantile), 0.5):
        return {
            "n_estimators": 140,
            "max_depth": 4,
            "learning_rate": 0.05,
            "objective": "reg:quantileerror",
            "quantile_alpha": 0.5,
            "random_state": 42,
            "verbosity": 0,
            "n_jobs": 1,
        }
    if float(quantile) < 0.5:
        return {
            "n_estimators": 100,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "reg:quantileerror",
            "quantile_alpha": float(quantile),
            "random_state": 42,
            "verbosity": 0,
            "n_jobs": 1,
        }
    return {
        "n_estimators": 100,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": float(quantile),
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    }


def _quantile_column_name(prefix: str, quantile: float) -> str:
    return f"{prefix}_q_{float(quantile):g}"


def _assign_quantile_columns(
    frame: pd.DataFrame,
    *,
    prefix: str,
    quantile_predictions: dict[float, Any],
) -> None:
    for quantile, values in sorted(quantile_predictions.items()):
        frame[_quantile_column_name(prefix, float(quantile))] = np.asarray(values, dtype=float)


def _extract_quantile_columns(
    frame: pd.DataFrame,
    *,
    prefix: str,
    quantiles: tuple[float, ...] = CANONICAL_FORECAST_QUANTILES,
) -> dict[float, np.ndarray]:
    return {
        float(quantile): frame[_quantile_column_name(prefix, float(quantile))].to_numpy(dtype=float)
        for quantile in quantiles
        if _quantile_column_name(prefix, float(quantile)) in frame.columns
    }


def _residual_quantile_predictions(
    trainer,
    *,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    baseline_weights: dict[str, float],
    quantiles: tuple[float, ...] = CANONICAL_FORECAST_QUANTILES,
) -> tuple[dict[float, Any], dict[float, np.ndarray]]:
    training = train_df.copy()
    train_baseline_log = baseline_center_log(training, weights=baseline_weights)
    training["residual_target_log"] = training["y_next_log"].to_numpy(dtype=float) - train_baseline_log
    test_baseline_log = baseline_center_log(test_df, weights=baseline_weights)
    X_test = test_df[feature_columns].to_numpy(dtype=float)
    models: dict[float, Any] = {}
    predictions: dict[float, np.ndarray] = {}
    for quantile in quantiles:
        model = trainer._fit_regressor_from_frame(
            training,
            feature_columns,
            _regressor_config_for_quantile(float(quantile)),
            target_col="residual_target_log",
        )
        models[float(quantile)] = model
        predictions[float(quantile)] = np.maximum(
            np.expm1(test_baseline_log + model.predict(X_test)),
            0.0,
        )
    return models, predictions


def build_backtest_bundle(
    trainer,
    *,
    virus_typ: str,
    panel: pd.DataFrame,
    feature_columns: list[str],
    event_feature_columns: list[str] | None = None,
    hierarchy_feature_columns: list[str],
    ww_only_columns: list[str],
    tau: float,
    kappa: float,
    action_threshold: float,
    horizon_days: int = 7,
    event_config=None,
    time_based_panel_splits_fn=time_based_panel_splits,
    quality_gate_from_metrics_fn=quality_gate_from_metrics,
) -> dict[str, Any]:
    config = event_config or event_definition_config_for_virus(virus_typ)
    effective_event_feature_columns = list(event_feature_columns or feature_columns)
    working = panel.copy()
    working["event_label"] = trainer._event_labels(
        working,
        virus_typ=virus_typ,
        tau=tau,
        kappa=kappa,
        event_config=config,
    )
    working["y_next_log"] = np.log1p(working["next_week_incidence"].astype(float).clip(lower=0.0))
    working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
    working["target_week_start"] = pd.to_datetime(working["target_week_start"]).dt.normalize()

    splits = time_based_panel_splits_fn(
        working["as_of_date"],
        n_splits=5,
        min_train_periods=90,
        min_test_periods=21,
    )
    if not splits:
        raise ValueError("Unable to build time-based backtest splits for regional panel.")

    fold_frames: list[pd.DataFrame] = []
    fold_selection_summary: list[dict[str, Any]] = []
    for fold_idx, (train_dates, test_dates) in enumerate(splits):
        train_df = working.loc[working["as_of_date"].isin(train_dates)].copy()
        test_df = working.loc[working["as_of_date"].isin(test_dates)].copy()
        if train_df.empty or test_df.empty:
            continue

        fold_selection = trainer._select_event_definition(
            virus_typ=virus_typ,
            panel=train_df,
            feature_columns=effective_event_feature_columns,
            event_config=config,
        )
        fold_tau = float(fold_selection["tau"])
        fold_kappa = float(fold_selection["kappa"])
        fold_threshold = float(fold_selection["action_threshold"])

        train_df["event_label"] = trainer._event_labels(
            train_df,
            virus_typ=virus_typ,
            tau=fold_tau,
            kappa=fold_kappa,
            event_config=config,
        )
        test_df["event_label"] = trainer._event_labels(
            test_df,
            virus_typ=virus_typ,
            tau=fold_tau,
            kappa=fold_kappa,
            event_config=config,
        )
        if train_df.empty or test_df.empty:
            continue

        calib_split = trainer._calibration_split_dates(train_dates)
        if not calib_split:
            continue
        model_train_dates, cal_dates = calib_split
        model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
        cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
        if model_train_df.empty:
            continue

        calibration_mode = "raw_passthrough"
        shadow_raw_prob = np.full(len(test_df), 0.5, dtype=float)
        shadow_calibrated_prob = np.full(len(test_df), 0.5, dtype=float)
        if model_train_df["event_label"].nunique() >= 2:
            classifier = trainer._fit_classifier_from_frame(
                model_train_df,
                effective_event_feature_columns,
                sample_weight=trainer._event_sample_weights(model_train_df, virus_typ=virus_typ),
            )
            shadow_raw_prob = classifier.predict_proba(test_df[effective_event_feature_columns].to_numpy())[:, 1]
            shadow_calibration = None
            if not cal_df.empty and cal_df["event_label"].nunique() >= 2:
                shadow_calibration, calibration_mode = trainer._select_guarded_calibration(
                    calibration_frame=pd.DataFrame(
                        {
                            "as_of_date": cal_df["as_of_date"].values,
                            "event_label": cal_df["event_label"].values.astype(int),
                            "event_probability_raw": classifier.predict_proba(
                                cal_df[effective_event_feature_columns].to_numpy()
                            )[:, 1],
                        }
                    ),
                    raw_probability_col="event_probability_raw",
                    action_threshold=fold_threshold,
                )
            shadow_calibrated_prob = trainer._apply_calibration(shadow_calibration, shadow_raw_prob)

        ww_prob = trainer._amelag_only_probabilities(
            train_df=train_df,
            test_df=test_df,
            feature_columns=ww_only_columns,
        )
        baseline_result = optimize_baseline_weights(
            model_train_df,
            quantiles=CANONICAL_FORECAST_QUANTILES,
        )
        baseline_weights = {
            "current_log": float((baseline_result.get("weights") or {}).get("current_log") or 0.0),
            "seasonal_log": float((baseline_result.get("weights") or {}).get("seasonal_log") or 0.0),
            "pooled_log": float((baseline_result.get("weights") or {}).get("pooled_log") or 0.0),
        }
        baseline_test_log = baseline_center_log(test_df, weights=baseline_weights)
        baseline_only_quantiles = apply_residual_quantiles(
            baseline_test_log,
            baseline_result.get("residual_quantiles") or {},
        )
        model_quantile_models, model_quantiles = _residual_quantile_predictions(
            trainer,
            train_df=model_train_df,
            test_df=test_df,
            feature_columns=feature_columns,
            baseline_weights=baseline_weights,
            quantiles=CANONICAL_FORECAST_QUANTILES,
        )
        previous_baseline_weights = getattr(trainer, "_active_residual_baseline_weights", None)
        trainer._active_residual_baseline_weights = baseline_weights
        try:
            hierarchy_models, hierarchy_model_modes = trainer._fit_hierarchy_models(
                panel=model_train_df,
                feature_columns=hierarchy_feature_columns,
                state_feature_columns=feature_columns,
                reg_lower=model_quantile_models[0.1],
                reg_median=model_quantile_models[0.5],
                reg_upper=model_quantile_models[0.9],
            )
        finally:
            if previous_baseline_weights is None:
                delattr(trainer, "_active_residual_baseline_weights")
            else:
                trainer._active_residual_baseline_weights = previous_baseline_weights

        hierarchy_inputs = trainer._predict_hierarchy_aggregate_quantiles(
            frame=test_df,
            source_panel=working,
            feature_columns=hierarchy_feature_columns,
            reg_lower=model_quantile_models[0.1],
            reg_median=model_quantile_models[0.5],
            reg_upper=model_quantile_models[0.9],
            hierarchy_models=hierarchy_models,
            state_feature_columns=feature_columns,
            hierarchy_model_modes=hierarchy_model_modes,
        )
        persistence_scale = np.maximum(test_df["seasonal_mad"].to_numpy(dtype=float), 1.0)
        persistence_quantile_predictions = persistence_quantiles(
            current_values=test_df["current_known_incidence"].to_numpy(dtype=float),
            residual_scale=persistence_scale,
        )

        persistence_prob = trainer._event_probability_from_prediction(
            predicted_next=test_df["current_known_incidence"].to_numpy(),
            current_known=test_df["current_known_incidence"].to_numpy(),
            baseline=test_df["seasonal_baseline"].to_numpy(),
            mad=test_df["seasonal_mad"].to_numpy(),
            tau=fold_tau,
            kappa=fold_kappa,
            min_absolute_incidence=config.min_absolute_incidence,
        )
        climatology_prob = trainer._event_probability_from_prediction(
            predicted_next=test_df["seasonal_baseline"].to_numpy(),
            current_known=test_df["current_known_incidence"].to_numpy(),
            baseline=test_df["seasonal_baseline"].to_numpy(),
            mad=test_df["seasonal_mad"].to_numpy(),
            tau=fold_tau,
            kappa=fold_kappa,
            min_absolute_incidence=config.min_absolute_incidence,
        )

        fold_selection_summary.append(
            {
                "fold": fold_idx,
                "train_start": str(min(train_dates)),
                "train_end": str(max(train_dates)),
                "test_start": str(min(test_dates)),
                "test_end": str(max(test_dates)),
                "selected_tau": fold_tau,
                "selected_kappa": fold_kappa,
                "action_threshold": fold_threshold,
                "selection_precision": fold_selection.get("precision"),
                "selection_recall": fold_selection.get("recall"),
                "selection_pr_auc": fold_selection.get("pr_auc"),
                "selection_brier_score": fold_selection.get("brier_score"),
                "selection_ece": fold_selection.get("ece"),
                "calibration_mode": calibration_mode,
                "baseline_weights": baseline_weights,
                "baseline_weight_diagnostics": baseline_result.get("diagnostics") or {},
            }
        )
        fold_frame = pd.DataFrame(
            {
                "fold": fold_idx,
                "virus_typ": test_df["virus_typ"].values,
                "bundesland": test_df["bundesland"].values,
                "bundesland_name": test_df["bundesland_name"].values,
                "as_of_date": test_df["as_of_date"].values,
                "target_date": test_df["target_date"].values if "target_date" in test_df.columns else None,
                "target_week_start": test_df["target_week_start"].values,
                "horizon_days": (
                    test_df["horizon_days"].values.astype(int)
                    if "horizon_days" in test_df.columns
                    else np.full(len(test_df), TARGET_WINDOW_DAYS[1], dtype=int)
                ),
                "event_label": test_df["event_label"].values.astype(int),
                "event_probability_calibrated": np.full(len(test_df), np.nan, dtype=float),
                "event_probability_raw": np.full(len(test_df), np.nan, dtype=float),
                "forecast_implied_event_probability": np.full(len(test_df), np.nan, dtype=float),
                "forecast_implied_event_probability_calibrated": np.full(len(test_df), np.nan, dtype=float),
                "shadow_event_probability_raw": shadow_raw_prob,
                "shadow_event_probability_calibrated": shadow_calibrated_prob,
                "amelag_only_probability": ww_prob,
                "persistence_probability": persistence_prob,
                "climatology_probability": climatology_prob,
                "current_known_incidence": test_df["current_known_incidence"].values.astype(float),
                "seasonal_baseline": test_df["seasonal_baseline"].values.astype(float),
                "seasonal_mad": test_df["seasonal_mad"].values.astype(float),
                "next_week_incidence": test_df["next_week_incidence"].values.astype(float),
                "expected_next_week_incidence": np.asarray(model_quantiles[0.5], dtype=float),
                "expected_target_incidence": np.asarray(model_quantiles[0.5], dtype=float),
                "prediction_interval_lower": np.asarray(model_quantiles[0.1], dtype=float),
                "prediction_interval_upper": np.asarray(model_quantiles[0.9], dtype=float),
                "state_population_millions": (
                    test_df["state_population_millions"].values.astype(float)
                    if "state_population_millions" in test_df.columns
                    else np.full(len(test_df), 1.0, dtype=float)
                ),
                "cluster_id": hierarchy_inputs["cluster_ids"],
                "cluster_prediction_interval_lower": hierarchy_inputs["cluster_lower"],
                "cluster_expected_target_incidence": hierarchy_inputs["cluster_median"],
                "cluster_prediction_interval_upper": hierarchy_inputs["cluster_upper"],
                "national_prediction_interval_lower": hierarchy_inputs["national_lower"],
                "national_expected_target_incidence": hierarchy_inputs["national_median"],
                "national_prediction_interval_upper": hierarchy_inputs["national_upper"],
                "residual": test_df["next_week_incidence"].values.astype(float)
                - np.asarray(model_quantiles[0.5], dtype=float),
                "absolute_error": np.abs(
                    test_df["next_week_incidence"].values.astype(float)
                    - np.asarray(model_quantiles[0.5], dtype=float)
                ),
                "selected_tau": fold_tau,
                "selected_kappa": fold_kappa,
                "action_threshold": fold_threshold,
                "calibration_mode": calibration_mode,
            }
        )
        _assign_quantile_columns(
            fold_frame,
            prefix="baseline_only",
            quantile_predictions=baseline_only_quantiles,
        )
        _assign_quantile_columns(
            fold_frame,
            prefix="model",
            quantile_predictions=model_quantiles,
        )
        _assign_quantile_columns(
            fold_frame,
            prefix="persistence",
            quantile_predictions=persistence_quantile_predictions,
        )
        fold_frames.append(fold_frame)

    if not fold_frames:
        raise ValueError("Regional backtest produced no valid folds.")

    oof_frame = pd.concat(fold_frames, ignore_index=True)
    baseline_only_quantiles = _extract_quantile_columns(oof_frame, prefix="baseline_only")
    model_quantiles = _extract_quantile_columns(oof_frame, prefix="model")
    persistence_quantile_predictions = _extract_quantile_columns(oof_frame, prefix="persistence")
    persistence_mix = optimize_persistence_mix_weight(
        y_true=oof_frame["next_week_incidence"].to_numpy(dtype=float),
        model_quantiles=model_quantiles,
        persistence_quantiles=persistence_quantile_predictions,
    )
    persistence_mix_weight = float(persistence_mix.get("weight") or 1.0)
    mixed_quantiles = mixture_quantiles_via_cdf(
        model_quantiles=model_quantiles,
        baseline_quantiles=persistence_quantile_predictions,
        mixture_weight=persistence_mix_weight,
        output_quantiles=tuple(sorted(float(value) for value in model_quantiles)),
    )
    _assign_quantile_columns(
        oof_frame,
        prefix="mixed",
        quantile_predictions=mixed_quantiles,
    )
    oof_frame["expected_target_incidence"] = np.asarray(mixed_quantiles[0.5], dtype=float)
    oof_frame["expected_next_week_incidence"] = np.asarray(mixed_quantiles[0.5], dtype=float)
    oof_frame["prediction_interval_lower"] = np.asarray(mixed_quantiles[0.1], dtype=float)
    oof_frame["prediction_interval_upper"] = np.asarray(mixed_quantiles[0.9], dtype=float)
    oof_frame["residual"] = (
        oof_frame["next_week_incidence"].to_numpy(dtype=float)
        - np.asarray(mixed_quantiles[0.5], dtype=float)
    )
    oof_frame["absolute_error"] = np.abs(oof_frame["residual"].to_numpy(dtype=float))
    forecast_implied_raw = trainer._forecast_implied_event_probability(
        quantile_predictions=mixed_quantiles,
        current_known=oof_frame["current_known_incidence"].to_numpy(dtype=float),
        baseline=oof_frame["seasonal_baseline"].to_numpy(dtype=float),
        mad=oof_frame["seasonal_mad"].to_numpy(dtype=float),
        tau=tau,
        kappa=kappa,
        min_absolute_incidence=config.min_absolute_incidence,
    )
    oof_frame["forecast_implied_event_probability"] = forecast_implied_raw
    forecast_implied_calibration, forecast_implied_calibration_mode = trainer._select_guarded_calibration(
        calibration_frame=pd.DataFrame(
            {
                "as_of_date": oof_frame["as_of_date"].values,
                "event_label": oof_frame["event_label"].values.astype(int),
                "forecast_implied_event_probability": forecast_implied_raw,
            }
        ),
        raw_probability_col="forecast_implied_event_probability",
        action_threshold=action_threshold,
    )
    forecast_implied_calibrated = trainer._apply_calibration(
        forecast_implied_calibration,
        forecast_implied_raw,
    )
    oof_frame["forecast_implied_event_probability_calibrated"] = forecast_implied_calibrated
    oof_frame["event_probability_raw"] = forecast_implied_raw
    oof_frame["event_probability_calibrated"] = forecast_implied_calibrated
    oof_frame["event_probability_source"] = (
        "forecast_implied_calibrated"
        if forecast_implied_calibration is not None
        else "forecast_implied"
    )
    oof_frame.attrs["persistence_mix_weight"] = persistence_mix_weight
    oof_frame.attrs["persistence_mix_diagnostics"] = persistence_mix
    oof_frame.attrs["forecast_implied_calibration_mode"] = forecast_implied_calibration_mode
    event_fold_viability = _summarize_event_fold_viability(oof_frame)

    aggregate = trainer._aggregate_metrics(
        frame=oof_frame,
        action_threshold=action_threshold,
        fold_viability=event_fold_viability,
    )
    baselines = trainer._baseline_metrics(
        frame=oof_frame,
        action_threshold=action_threshold,
        fold_viability=event_fold_viability,
    )
    benchmark_frame = oof_frame.copy()
    benchmark_frame["candidate"] = "regional_pooled_panel"
    benchmark_frame["y_true"] = benchmark_frame["next_week_incidence"].astype(float)
    benchmark_frame["q_0.1"] = np.asarray(mixed_quantiles[0.1], dtype=float)
    benchmark_frame["q_0.5"] = np.asarray(mixed_quantiles[0.5], dtype=float)
    benchmark_frame["q_0.9"] = np.asarray(mixed_quantiles[0.9], dtype=float)
    benchmark_frame["event_probability"] = benchmark_frame["event_probability_calibrated"].astype(float)
    benchmark_frame = _attach_persistence_baseline_quantiles(benchmark_frame)
    persistence_baseline_quantile_predictions = {
        0.1: benchmark_frame["baseline_q_0.1"].to_numpy(dtype=float),
        0.5: benchmark_frame["baseline_q_0.5"].to_numpy(dtype=float),
        0.9: benchmark_frame["baseline_q_0.9"].to_numpy(dtype=float),
    }
    climatology_baseline_quantile_predictions = seasonal_quantiles(
        seasonal_baseline=benchmark_frame["seasonal_baseline"].to_numpy(dtype=float),
        seasonal_scale=np.maximum(benchmark_frame["seasonal_mad"].to_numpy(dtype=float), 1.0),
    )
    hierarchy_benchmark_frame = trainer._hierarchy_reconciled_benchmark_frame(
        oof_frame=oof_frame,
        source_panel=working,
    )
    hierarchy_benchmark_frame = _attach_persistence_baseline_quantiles(hierarchy_benchmark_frame)
    combined_benchmark_frame = pd.concat(
        [benchmark_frame, hierarchy_benchmark_frame],
        ignore_index=True,
    ) if not hierarchy_benchmark_frame.empty else benchmark_frame.copy()
    benchmark_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=mixed_quantiles,
        baseline_quantiles=persistence_baseline_quantile_predictions,
        event_labels=benchmark_frame["event_label"].to_numpy(dtype=int),
        event_probabilities=benchmark_frame["event_probability"].to_numpy(dtype=float),
        action_threshold=action_threshold,
    )
    persistence_forecast_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=persistence_quantile_predictions,
    )
    climatology_forecast_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=climatology_baseline_quantile_predictions,
    )
    baseline_only_forecast_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=baseline_only_quantiles,
        baseline_quantiles=persistence_quantile_predictions,
    )
    residual_forecast_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=model_quantiles,
        baseline_quantiles=persistence_quantile_predictions,
    )
    benchmark_leaderboard = build_leaderboard(
        combined_benchmark_frame,
        group_by=("virus_typ", "horizon_days", "bundesland"),
        action_threshold=action_threshold,
    )
    candidate_summaries = [
        {
            "candidate": "regional_baseline_only",
            "metrics": baseline_only_forecast_metrics,
            "samples": int(len(oof_frame)),
        },
        {
            "candidate": "regional_residual_model",
            "metrics": residual_forecast_metrics,
            "samples": int(len(oof_frame)),
        },
        {
            "candidate": "regional_pooled_panel",
            "metrics": benchmark_metrics,
            "samples": int(len(oof_frame)),
        },
    ]
    if not hierarchy_benchmark_frame.empty:
        candidate_summaries.append(
            {
                "candidate": "regional_pooled_panel_mint",
                "metrics": summarize_probabilistic_metrics(
                    y_true=hierarchy_benchmark_frame["y_true"].to_numpy(dtype=float),
                    quantile_predictions={
                        0.1: hierarchy_benchmark_frame["q_0.1"].to_numpy(dtype=float),
                        0.5: hierarchy_benchmark_frame["q_0.5"].to_numpy(dtype=float),
                        0.9: hierarchy_benchmark_frame["q_0.9"].to_numpy(dtype=float),
                    },
                    baseline_quantiles={
                        0.1: hierarchy_benchmark_frame["baseline_q_0.1"].to_numpy(dtype=float),
                        0.5: hierarchy_benchmark_frame["baseline_q_0.5"].to_numpy(dtype=float),
                        0.9: hierarchy_benchmark_frame["baseline_q_0.9"].to_numpy(dtype=float),
                    },
                    event_labels=hierarchy_benchmark_frame["event_label"].to_numpy(dtype=int),
                    event_probabilities=hierarchy_benchmark_frame["event_probability"].to_numpy(dtype=float),
                    action_threshold=action_threshold,
                ),
                "samples": int(len(hierarchy_benchmark_frame)),
            }
        )
    candidate_metrics_map = {
        str(item.get("candidate")): item.get("metrics") or {}
        for item in candidate_summaries
    }
    hierarchy_diagnostics = trainer._hierarchy_component_diagnostics(oof_frame=oof_frame)
    cluster_homogeneity = GeoHierarchyHelper.cluster_homogeneity_diagnostics(
        working,
        state_col="bundesland",
        value_col="current_known_incidence",
        date_col="as_of_date",
    )
    raw_candidate_metrics = candidate_metrics_map.get("regional_pooled_panel") or {}
    hierarchy_candidate_metrics = candidate_metrics_map.get("regional_pooled_panel_mint") or {}
    hierarchy_comparison = {
        "wis_delta": round(
            float(hierarchy_candidate_metrics.get("wis", 0.0) or 0.0)
            - float(raw_candidate_metrics.get("wis", 0.0) or 0.0),
            6,
        ),
        "crps_delta": round(
            float(hierarchy_candidate_metrics.get("crps", 0.0) or 0.0)
            - float(raw_candidate_metrics.get("crps", 0.0) or 0.0),
            6,
        ),
        "coverage_80_delta": round(
            float(hierarchy_candidate_metrics.get("coverage_80", 0.0) or 0.0)
            - float(raw_candidate_metrics.get("coverage_80", 0.0) or 0.0),
            6,
        ),
    }
    hierarchy_promote = (
        not hierarchy_benchmark_frame.empty
        and hierarchy_comparison["wis_delta"] <= -0.001
        and hierarchy_comparison["crps_delta"] <= 0.0
        and hierarchy_comparison["coverage_80_delta"] >= -0.02
    )
    quality_gate = quality_gate_from_metrics_fn(
        metrics=aggregate,
        baseline_metrics=baselines,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
    )
    fold_viability_passed = bool(event_fold_viability.get("passed"))
    if not fold_viability_passed:
        quality_gate = dict(quality_gate)
        failed_checks = list(quality_gate.get("failed_checks") or [])
        if "fold_viability_passed" not in failed_checks:
            failed_checks.append("fold_viability_passed")
        quality_gate["overall_passed"] = False
        quality_gate["failed_checks"] = failed_checks
    backtest_payload = trainer._build_backtest_payload(
        frame=oof_frame,
        aggregate_metrics=aggregate,
        baselines=baselines,
        quality_gate=quality_gate,
        tau=tau,
        kappa=kappa,
        action_threshold=action_threshold,
        fold_selection_summary=fold_selection_summary,
    )
    return {
        "oof_frame": oof_frame,
        "aggregate_metrics": aggregate,
        "benchmark_summary": {
            "primary_metric": "relative_wis",
            "leaderboard": benchmark_leaderboard,
            "metrics": benchmark_metrics,
            "forecast_baselines": {
                "persistence": persistence_forecast_metrics,
                "climatology": climatology_forecast_metrics,
                "baseline_only": baseline_only_forecast_metrics,
                "residual_model": residual_forecast_metrics,
            },
            "forecast_core_deltas": _forecast_core_delta_summary(
                candidate_metrics=benchmark_metrics,
                persistence_metrics=persistence_forecast_metrics,
                climatology_metrics=climatology_forecast_metrics,
            ),
            "ablation_report": {
                "A_baseline_only": baseline_only_forecast_metrics,
                "B_residual_quantiles": residual_forecast_metrics,
                "C_mixed_champion": benchmark_metrics,
                "D_event_paths": {
                    "forecast_implied_raw": _event_path_metrics(
                        oof_frame,
                        score_col="forecast_implied_event_probability",
                        action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                        fold_viability=event_fold_viability,
                    ),
                    "forecast_implied_calibrated": _event_path_metrics(
                        oof_frame,
                        score_col="forecast_implied_event_probability_calibrated",
                        action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                        fold_viability=event_fold_viability,
                    ),
                    "shadow_classifier": _event_path_metrics(
                        oof_frame,
                        score_col="shadow_event_probability_calibrated",
                        action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                        fold_viability=event_fold_viability,
                    ),
                },
            },
            "baseline_weight_source": "oof_wis_simplex_v1",
            "persistence_mix_weight": persistence_mix_weight,
            "persistence_mix_diagnostics": persistence_mix,
            "forecast_implied_calibration_mode": forecast_implied_calibration_mode,
            "event_evaluation_mode": EVENT_EVALUATION_MODE,
            "fold_viability": event_fold_viability,
            "non_viable_fold_monitoring": {
                "event_model": _non_viable_fold_monitoring(
                    oof_frame,
                    score_col="event_probability_calibrated",
                    action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                    fold_viability=event_fold_viability,
                ),
                "forecast_implied": _non_viable_fold_monitoring(
                    oof_frame,
                    score_col="forecast_implied_event_probability",
                    action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                    fold_viability=event_fold_viability,
                ),
                "forecast_implied_calibrated": _non_viable_fold_monitoring(
                    oof_frame,
                    score_col="forecast_implied_event_probability_calibrated",
                    action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                    fold_viability=event_fold_viability,
                ),
                "shadow_classifier": _non_viable_fold_monitoring(
                    oof_frame,
                    score_col="shadow_event_probability_calibrated",
                    action_threshold=None if "action_threshold" in oof_frame.columns else action_threshold,
                    fold_viability=event_fold_viability,
                ),
            },
            "candidate_summaries": candidate_summaries,
            "hierarchy_diagnostics": hierarchy_diagnostics,
            "cluster_homogeneity": cluster_homogeneity,
            "hierarchy_benchmark": {
                "enabled": not hierarchy_benchmark_frame.empty,
                "candidate_name": "regional_pooled_panel_mint",
                "promote_reconciliation": hierarchy_promote,
                "selection_basis": (
                    "benchmark_passed"
                    if hierarchy_promote
                    else "benchmark_rejected_inferior_wis_or_crps"
                ),
                "comparison": hierarchy_comparison,
                "leaderboard": [
                    item for item in benchmark_leaderboard
                    if str(item.get("candidate") or "").startswith("regional_pooled_panel")
                ],
            },
        },
        "quality_gate": quality_gate,
        "backtest_payload": backtest_payload,
    }


def aggregate_metrics(
    frame: pd.DataFrame,
    *,
    action_threshold: float,
    fold_viability: dict[str, Any] | None = None,
) -> dict[str, float]:
    effective_threshold = None if "action_threshold" in frame.columns else action_threshold
    event_fold_viability = fold_viability or _summarize_event_fold_viability(frame)
    viable_frame, _ = _event_evaluation_frames(frame, fold_viability=event_fold_viability)
    discrimination_frame = viable_frame if not viable_frame.empty else frame.iloc[0:0].copy()
    metrics = _event_path_metrics(
        frame,
        score_col="event_probability_calibrated",
        action_threshold=effective_threshold,
        fold_viability=event_fold_viability,
    )
    metrics.update(
        {
            "precision_at_top5": (
                precision_at_k(discrimination_frame, k=5)
                if not discrimination_frame.empty
                else 0.0
            ),
            "median_lead_days": (
                median_lead_days(discrimination_frame, threshold=effective_threshold)
                if not discrimination_frame.empty
                else 0.0
            ),
            "action_threshold": round(float(action_threshold), 4),
        }
    )
    return metrics


def _event_probability_metrics(
    frame: pd.DataFrame,
    *,
    score_col: str,
    action_threshold: float | None,
) -> dict[str, Any]:
    score_frame = frame if score_col in frame.columns else frame.assign(**{score_col: 0.0})
    labels = score_frame["event_label"].to_numpy(dtype=int)
    probabilities = score_frame[score_col].to_numpy(dtype=float)
    metrics: dict[str, Any] = {
        "precision_at_top3": precision_at_k(score_frame, k=3, score_col=score_col),
        "pr_auc": round(
            average_precision_safe(labels, probabilities),
            6,
        ),
        "brier_score": round(
            brier_score_safe(labels, probabilities),
            6,
        ),
        "ece": round(
            compute_ece(labels, probabilities),
            6,
        ),
        "activation_false_positive_rate": activation_false_positive_rate(
            score_frame,
            threshold=action_threshold,
            score_col=score_col,
        ),
    }
    metrics.update(
        brier_decomposition(
            labels,
            probabilities,
            target_bins=10,
            min_bin_size=20,
        )
    )
    return metrics


def _metric_delta(candidate_value: float | None, baseline_value: float | None, metric_name: str) -> float:
    candidate = float(candidate_value or 0.0)
    baseline = float(baseline_value or 0.0)
    if metric_name in LOSS_METRICS:
        return round(baseline - candidate, 6)
    return round(candidate - baseline, 6)


def _event_metric_deltas(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    metric_names: tuple[str, ...] = EVENT_DELTA_METRICS,
) -> dict[str, float]:
    return {
        metric_name: _metric_delta(
            candidate_metrics.get(metric_name),
            baseline_metrics.get(metric_name),
            metric_name,
        )
        for metric_name in metric_names
    }


def _fold_metric_deltas(
    frame: pd.DataFrame,
    *,
    candidate_col: str,
    baseline_col: str,
    action_threshold: float | None,
    fold_viability: dict[str, Any] | None = None,
    metric_names: tuple[str, ...] = EVENT_DELTA_METRICS,
) -> list[dict[str, Any]]:
    viable_folds = {int(value) for value in ((fold_viability or {}).get("viable_folds") or [])}
    rows: list[dict[str, Any]] = []
    for fold, fold_frame in frame.groupby("fold", dropna=False):
        candidate_metrics = _event_path_metrics(
            fold_frame,
            score_col=candidate_col,
            action_threshold=action_threshold,
            fold_viability={
                "viable_folds": [int(fold)] if int(fold) in viable_folds else [],
                "non_viable_folds": [] if int(fold) in viable_folds else [int(fold)],
                "viable_fold_count": 1 if int(fold) in viable_folds else 0,
                "non_viable_fold_count": 0 if int(fold) in viable_folds else 1,
                "minimum_viable_folds": 1,
                "passed": bool(int(fold) in viable_folds),
            },
        )
        baseline_metrics = _event_path_metrics(
            fold_frame,
            score_col=baseline_col,
            action_threshold=action_threshold,
            fold_viability={
                "viable_folds": [int(fold)] if int(fold) in viable_folds else [],
                "non_viable_folds": [] if int(fold) in viable_folds else [int(fold)],
                "viable_fold_count": 1 if int(fold) in viable_folds else 0,
                "non_viable_fold_count": 0 if int(fold) in viable_folds else 1,
                "minimum_viable_folds": 1,
                "passed": bool(int(fold) in viable_folds),
            },
        )
        row = {
            "fold": int(fold),
            "event_viable": bool(int(fold) in viable_folds),
        }
        row.update(
            {
                metric_name: (
                    None
                    if metric_name in {"precision_at_top3", "pr_auc"} and int(fold) not in viable_folds
                    else _metric_delta(
                        candidate_metrics.get(metric_name),
                        baseline_metrics.get(metric_name),
                        metric_name,
                    )
                )
                for metric_name in metric_names
            }
        )
        rows.append(row)
    return rows


def _bootstrap_metric_confidence_intervals(
    frame: pd.DataFrame,
    *,
    candidate_col: str,
    baseline_col: str,
    action_threshold: float | None,
    fold_viability: dict[str, Any] | None = None,
    metric_names: tuple[str, ...] = EVENT_DELTA_METRICS,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_RANDOM_SEED,
) -> dict[str, list[float]]:
    if frame.empty:
        return {metric_name: [0.0, 0.0] for metric_name in metric_names}
    rng = np.random.default_rng(int(seed))
    fold_frames = [fold_frame.reset_index(drop=True) for _, fold_frame in frame.groupby("fold", dropna=False)]
    samples_by_metric: dict[str, list[float]] = {metric_name: [] for metric_name in metric_names}
    for _ in range(max(int(iterations), 1)):
        sampled_parts = []
        for fold_frame in fold_frames:
            choices = rng.integers(0, len(fold_frame), size=len(fold_frame))
            sampled_parts.append(fold_frame.iloc[choices].copy())
        sampled = pd.concat(sampled_parts, ignore_index=True)
        candidate_metrics = _event_path_metrics(
            sampled,
            score_col=candidate_col,
            action_threshold=action_threshold,
            fold_viability=fold_viability,
        )
        baseline_metrics = _event_path_metrics(
            sampled,
            score_col=baseline_col,
            action_threshold=action_threshold,
            fold_viability=fold_viability,
        )
        for metric_name in metric_names:
            samples_by_metric[metric_name].append(
                _metric_delta(
                    candidate_metrics.get(metric_name),
                    baseline_metrics.get(metric_name),
                    metric_name,
                )
            )
    return {
        metric_name: [
            round(float(np.quantile(samples_by_metric[metric_name], 0.025)), 6),
            round(float(np.quantile(samples_by_metric[metric_name], 0.975)), 6),
        ]
        for metric_name in metric_names
    }


def _event_path_delta_summary(
    frame: pd.DataFrame,
    *,
    candidate_col: str,
    baseline_map: dict[str, str],
    action_threshold: float | None,
    fold_viability: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    delta_summary: dict[str, Any] = {}
    ci_summary: dict[str, Any] = {}
    fold_summary: dict[str, Any] = {}
    candidate_metrics = _event_path_metrics(
        frame,
        score_col=candidate_col,
        action_threshold=action_threshold,
        fold_viability=fold_viability,
    )
    for baseline_name, baseline_col in baseline_map.items():
        baseline_metrics = _event_path_metrics(
            frame,
            score_col=baseline_col,
            action_threshold=action_threshold,
            fold_viability=fold_viability,
        )
        delta_summary[baseline_name] = _event_metric_deltas(
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
        )
        ci_summary[baseline_name] = _bootstrap_metric_confidence_intervals(
            frame,
            candidate_col=candidate_col,
            baseline_col=baseline_col,
            action_threshold=action_threshold,
            fold_viability=fold_viability,
        )
        fold_summary[baseline_name] = _fold_metric_deltas(
            frame,
            candidate_col=candidate_col,
            baseline_col=baseline_col,
            action_threshold=action_threshold,
            fold_viability=fold_viability,
        )
    return delta_summary, ci_summary, fold_summary


def _attach_persistence_baseline_quantiles(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "current_known_incidence" not in frame.columns:
        return frame
    result = frame.copy()
    scale = (
        pd.to_numeric(result.get("seasonal_mad"), errors="coerce")
        .fillna(1.0)
        .clip(lower=1.0)
        .to_numpy(dtype=float)
        if "seasonal_mad" in result.columns
        else np.full(len(result), 1.0, dtype=float)
    )
    persistence = persistence_quantiles(
        current_values=result["current_known_incidence"].to_numpy(dtype=float),
        residual_scale=scale,
    )
    for quantile, values in persistence.items():
        result[f"baseline_q_{quantile:g}"] = np.asarray(values, dtype=float)
    return result


def _forecast_core_delta_summary(
    *,
    candidate_metrics: dict[str, Any],
    persistence_metrics: dict[str, Any],
    climatology_metrics: dict[str, Any],
) -> dict[str, dict[str, float]]:
    summary = {
        "persistence": {
            "wis": _metric_delta(candidate_metrics.get("wis"), persistence_metrics.get("wis"), "wis"),
            "crps": _metric_delta(candidate_metrics.get("crps"), persistence_metrics.get("crps"), "crps"),
        },
        "climatology": {
            "wis": _metric_delta(candidate_metrics.get("wis"), climatology_metrics.get("wis"), "wis"),
            "crps": _metric_delta(candidate_metrics.get("crps"), climatology_metrics.get("crps"), "crps"),
        },
    }
    return summary
    


def baseline_metrics(
    trainer,
    frame: pd.DataFrame,
    *,
    action_threshold: float,
    fold_viability: dict[str, Any] | None = None,
) -> dict[str, dict[str, float]]:
    baselines: dict[str, dict[str, float]] = {}
    effective_threshold = None if "action_threshold" in frame.columns else action_threshold
    for name, column in {
        "persistence": "persistence_probability",
        "climatology": "climatology_probability",
        "amelag_only": "amelag_only_probability",
    }.items():
        baselines[name] = _event_path_metrics(
            frame,
            score_col=column,
            action_threshold=effective_threshold,
            fold_viability=fold_viability,
        )
    return baselines


def build_backtest_payload(
    trainer,
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
    details: dict[str, Any] = {}
    ranking = []
    event_fold_viability = _summarize_event_fold_viability(frame)
    fold_viability_map = {
        int(item["fold"]): item
        for item in (event_fold_viability.get("folds") or [])
    }
    for state, state_frame in frame.groupby("bundesland"):
        precision, recall = state_precision_recall(state_frame, action_threshold=action_threshold)
        activated = activation_mask(state_frame, action_threshold=action_threshold)
        state_metrics = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "pr_auc": round(
                average_precision_safe(state_frame["event_label"], state_frame["event_probability_calibrated"]),
                6,
            ),
            "brier_score": round(
                brier_score_safe(state_frame["event_label"], state_frame["event_probability_calibrated"]),
                6,
            ),
            "ece": round(
                compute_ece(state_frame["event_label"], state_frame["event_probability_calibrated"]),
                6,
            ),
            "activations": int(np.sum(activated)),
            "events": int(np.sum(state_frame["event_label"] == 1)),
            "precision_at_top3": precision_at_k(state_frame, k=3),
        }
        timeline = (
            state_frame.sort_values("as_of_date")
            .tail(20)
            .assign(
                activated=lambda df: (
                    df["event_probability_calibrated"] >= df["action_threshold"]
                    if "action_threshold" in df.columns
                    else df["event_probability_calibrated"] >= action_threshold
                )
            )
            .to_dict(orient="records")
        )
        details[state] = {
            "bundesland": state,
            "bundesland_name": BUNDESLAND_NAMES.get(state, state),
            "total_windows": int(len(state_frame)),
            "metrics": _json_safe(state_metrics),
            "timeline": _json_safe(timeline),
        }
        ranking.append(
            {
                "bundesland": state,
                "name": BUNDESLAND_NAMES.get(state, state),
                "precision": state_metrics["precision"],
                "recall": state_metrics["recall"],
                "pr_auc": state_metrics["pr_auc"],
                "events": state_metrics["events"],
            }
        )

    ranking.sort(key=lambda item: (item["precision"], item["pr_auc"]), reverse=True)
    horizon = int(frame["horizon_days"].iloc[0]) if "horizon_days" in frame.columns else TARGET_WINDOW_DAYS[1]
    effective_threshold = None if "action_threshold" in frame.columns else action_threshold
    fold_diagnostics = []
    for fold, fold_frame in frame.groupby("fold"):
        positive_mask = fold_frame["event_label"] == 1
        positive_count = int(np.sum(positive_mask))
        positive_regions = int(fold_frame.loc[positive_mask, "bundesland"].astype(str).nunique())
        viability_row = fold_viability_map.get(int(fold)) or {}
        fold_diagnostics.append(
            {
                "fold": int(fold),
                "rows": int(len(fold_frame)),
                "positive_count": positive_count,
                "prevalence": round(float(positive_count / max(len(fold_frame), 1)), 6),
                "positive_regions": positive_regions,
                "event_viable": bool(viability_row.get("event_viable")),
                "event_viability_reason": viability_row.get("event_viability_reason"),
                "degeneration_flag": bool(
                    fold_frame["event_label"].nunique() < 2 or positive_regions <= 1
                ),
                "low_information_flag": bool(0 < positive_count < 5),
                "mean_absolute_error": round(float(fold_frame["absolute_error"].mean() or 0.0), 6)
                if "absolute_error" in fold_frame.columns
                else None,
                "mean_residual": round(float(fold_frame["residual"].mean() or 0.0), 6)
                if "residual" in fold_frame.columns
                else None,
                "calibration_mode": str(fold_frame["calibration_mode"].iloc[0]) if "calibration_mode" in fold_frame.columns else None,
            }
        )
    event_benchmark_paths = {
        "event_model": _event_path_metrics(
            frame,
            score_col="event_probability_calibrated",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        ),
        "persistence": _event_path_metrics(
            frame,
            score_col="persistence_probability",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        ),
        "climatology": _event_path_metrics(
            frame,
            score_col="climatology_probability",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        ),
        "amelag_only": _event_path_metrics(
            frame,
            score_col="amelag_only_probability",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        ),
    }
    if "forecast_implied_event_probability" in frame.columns:
        event_benchmark_paths["forecast_implied"] = _event_path_metrics(
            frame,
            score_col="forecast_implied_event_probability",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        )
    if "forecast_implied_event_probability_calibrated" in frame.columns:
        event_benchmark_paths["forecast_implied_calibrated"] = _event_path_metrics(
            frame,
            score_col="forecast_implied_event_probability_calibrated",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        )
    if "shadow_event_probability_calibrated" in frame.columns:
        event_benchmark_paths["shadow_classifier"] = _event_path_metrics(
            frame,
            score_col="shadow_event_probability_calibrated",
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        )

    baseline_map = {
        "persistence": "persistence_probability",
        "climatology": "climatology_probability",
        "amelag_only": "amelag_only_probability",
    }
    event_model_deltas, event_model_ci, event_model_fold_deltas = _event_path_delta_summary(
        frame,
        candidate_col="event_probability_calibrated",
        baseline_map=baseline_map,
        action_threshold=effective_threshold,
        fold_viability=event_fold_viability,
    )
    delta_vs_persistence: dict[str, Any] = {
        "event_model": event_model_deltas["persistence"],
    }
    delta_vs_climatology: dict[str, Any] = {
        "event_model": event_model_deltas["climatology"],
    }
    delta_vs_amelag_only: dict[str, Any] = {
        "event_model": event_model_deltas["amelag_only"],
    }
    delta_ci_95: dict[str, Any] = {
        "event_model": event_model_ci,
    }
    fold_metric_deltas: dict[str, Any] = {
        "event_model": event_model_fold_deltas,
    }
    if "forecast_implied_event_probability" in frame.columns:
        forecast_implied_deltas, forecast_implied_ci, forecast_implied_fold_deltas = _event_path_delta_summary(
            frame,
            candidate_col="forecast_implied_event_probability",
            baseline_map=baseline_map,
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        )
        delta_vs_persistence["forecast_implied"] = forecast_implied_deltas["persistence"]
        delta_vs_climatology["forecast_implied"] = forecast_implied_deltas["climatology"]
        delta_vs_amelag_only["forecast_implied"] = forecast_implied_deltas["amelag_only"]
        delta_ci_95["forecast_implied"] = forecast_implied_ci
        fold_metric_deltas["forecast_implied"] = forecast_implied_fold_deltas
    if "forecast_implied_event_probability_calibrated" in frame.columns:
        forecast_implied_cal_deltas, forecast_implied_cal_ci, forecast_implied_cal_fold_deltas = _event_path_delta_summary(
            frame,
            candidate_col="forecast_implied_event_probability_calibrated",
            baseline_map=baseline_map,
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        )
        delta_vs_persistence["forecast_implied_calibrated"] = forecast_implied_cal_deltas["persistence"]
        delta_vs_climatology["forecast_implied_calibrated"] = forecast_implied_cal_deltas["climatology"]
        delta_vs_amelag_only["forecast_implied_calibrated"] = forecast_implied_cal_deltas["amelag_only"]
        delta_ci_95["forecast_implied_calibrated"] = forecast_implied_cal_ci
        fold_metric_deltas["forecast_implied_calibrated"] = forecast_implied_cal_fold_deltas
    if "shadow_event_probability_calibrated" in frame.columns:
        shadow_deltas, shadow_ci, shadow_fold_deltas = _event_path_delta_summary(
            frame,
            candidate_col="shadow_event_probability_calibrated",
            baseline_map=baseline_map,
            action_threshold=effective_threshold,
            fold_viability=event_fold_viability,
        )
        delta_vs_persistence["shadow_classifier"] = shadow_deltas["persistence"]
        delta_vs_climatology["shadow_classifier"] = shadow_deltas["climatology"]
        delta_vs_amelag_only["shadow_classifier"] = shadow_deltas["amelag_only"]
        delta_ci_95["shadow_classifier"] = shadow_ci
        fold_metric_deltas["shadow_classifier"] = shadow_fold_deltas
    return {
        "virus_typ": str(frame["virus_typ"].iloc[0]),
        "horizon_days": horizon,
        "event_definition_version": EVENT_DEFINITION_VERSION,
        "target_window_days": _target_window_for_horizon(horizon),
        "selected_tau": tau,
        "selected_kappa": kappa,
        "action_threshold": action_threshold,
        "aggregate_metrics": _json_safe(aggregate_metrics),
        "baselines": _json_safe(baselines),
        "quality_gate": _json_safe(quality_gate),
        "nested_selection_summary": _json_safe(fold_selection_summary),
        "total_regions": len(details),
        "backtested": len(details),
        "failed": max(0, len(ALL_BUNDESLAENDER) - len(details)),
        "ranking": _json_safe(ranking),
        "fold_diagnostics": _json_safe(fold_diagnostics),
        "event_evaluation_mode": EVENT_EVALUATION_MODE,
        "fold_viability": _json_safe(event_fold_viability),
        "non_viable_fold_monitoring": _json_safe(
            {
                "event_model": _non_viable_fold_monitoring(
                    frame,
                    score_col="event_probability_calibrated",
                    action_threshold=effective_threshold,
                    fold_viability=event_fold_viability,
                ),
                "persistence": _non_viable_fold_monitoring(
                    frame,
                    score_col="persistence_probability",
                    action_threshold=effective_threshold,
                    fold_viability=event_fold_viability,
                ),
                "climatology": _non_viable_fold_monitoring(
                    frame,
                    score_col="climatology_probability",
                    action_threshold=effective_threshold,
                    fold_viability=event_fold_viability,
                ),
                "amelag_only": _non_viable_fold_monitoring(
                    frame,
                    score_col="amelag_only_probability",
                    action_threshold=effective_threshold,
                    fold_viability=event_fold_viability,
                ),
            }
        ),
        "event_benchmark_paths": _json_safe(event_benchmark_paths),
        "delta_vs_persistence": _json_safe(delta_vs_persistence),
        "delta_vs_climatology": _json_safe(delta_vs_climatology),
        "delta_vs_amelag_only": _json_safe(delta_vs_amelag_only),
        "delta_ci_95": _json_safe(delta_ci_95),
        "fold_metric_deltas": _json_safe(fold_metric_deltas),
        "details": _json_safe(details),
        "generated_at": utc_now().isoformat(),
    }


def activation_mask(state_frame: pd.DataFrame, *, action_threshold: float) -> pd.Series:
    if "action_threshold" in state_frame.columns:
        return state_frame["event_probability_calibrated"] >= state_frame["action_threshold"]
    return state_frame["event_probability_calibrated"] >= action_threshold


def state_precision_recall(state_frame: pd.DataFrame, *, action_threshold: float) -> tuple[float, float]:
    activated = activation_mask(state_frame, action_threshold=action_threshold)
    positives = state_frame["event_label"] == 1
    tp = float(np.sum(activated & positives))
    fp = float(np.sum(activated & ~positives))
    fn = float(np.sum(~activated & positives))
    precision = tp / max(tp + fp, 1.0)
    recall = tp / max(tp + fn, 1.0)
    return precision, recall
