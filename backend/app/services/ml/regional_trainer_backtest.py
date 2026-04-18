from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.baselines import persistence_quantiles, seasonal_quantiles
from app.core.time import utc_now
from app.services.ml.benchmarking.leaderboard import build_leaderboard
from app.services.ml.benchmarking.metrics import brier_decomposition, summarize_probabilistic_metrics
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
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

# Walk-forward split configuration is env-tunable so we can run a
# dense weekly backtest over the full SURVSTAT history without
# changing the defaults used by scheduled retrains. Defaults match
# the pre-2026-04-18 behaviour (5 folds, 21-day test window).
#
# For the pitch-story full-historical run we typically set:
#   REGIONAL_BACKTEST_N_SPLITS=500         (effectively unbounded,
#                                          the generator caps at the
#                                          number of available windows)
#   REGIONAL_BACKTEST_MIN_TRAIN_PERIODS=104 (2 years warm-up)
#   REGIONAL_BACKTEST_MIN_TEST_PERIODS=7   (weekly walk-forward step)
_BACKTEST_N_SPLITS = int(os.getenv("REGIONAL_BACKTEST_N_SPLITS", "5"))
_BACKTEST_MIN_TRAIN_PERIODS = int(os.getenv("REGIONAL_BACKTEST_MIN_TRAIN_PERIODS", "90"))
_BACKTEST_MIN_TEST_PERIODS = int(os.getenv("REGIONAL_BACKTEST_MIN_TEST_PERIODS", "21"))

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
BOOTSTRAP_ITERATIONS = 2000


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
        n_splits=_BACKTEST_N_SPLITS,
        min_train_periods=_BACKTEST_MIN_TRAIN_PERIODS,
        min_test_periods=_BACKTEST_MIN_TEST_PERIODS,
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
        if train_df["event_label"].nunique() < 2:
            continue

        calib_split = trainer._calibration_split_dates(train_dates)
        if not calib_split:
            continue
        model_train_dates, cal_dates = calib_split
        model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
        cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
        if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
            continue

        classifier = trainer._fit_classifier_from_frame(
            model_train_df,
            effective_event_feature_columns,
            sample_weight=trainer._event_sample_weights(model_train_df, virus_typ=virus_typ),
        )
        calibration, calibration_mode = trainer._select_guarded_calibration(
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
        raw_prob = classifier.predict_proba(test_df[effective_event_feature_columns].to_numpy())[:, 1]
        calibrated_prob = trainer._apply_calibration(calibration, raw_prob)

        ww_prob = trainer._amelag_only_probabilities(
            train_df=train_df,
            test_df=test_df,
            feature_columns=ww_only_columns,
        )

        reg_median = trainer._fit_regressor_from_frame(
            train_df,
            feature_columns,
            trainer.REGIONAL_REGRESSOR_CONFIG["median"] if hasattr(trainer, "REGIONAL_REGRESSOR_CONFIG") else {
                "n_estimators": 140,
                "max_depth": 4,
                "learning_rate": 0.05,
                "objective": "reg:quantileerror",
                "quantile_alpha": 0.5,
                "random_state": 42,
                "verbosity": 0,
                "n_jobs": 1,
            },
        )
        reg_lower = trainer._fit_regressor_from_frame(train_df, feature_columns, {
            "n_estimators": 100,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "reg:quantileerror",
            "quantile_alpha": 0.1,
            "random_state": 42,
            "verbosity": 0,
            "n_jobs": 1,
        })
        reg_upper = trainer._fit_regressor_from_frame(train_df, feature_columns, {
            "n_estimators": 100,
            "max_depth": 3,
            "learning_rate": 0.05,
            "objective": "reg:quantileerror",
            "quantile_alpha": 0.9,
            "random_state": 42,
            "verbosity": 0,
            "n_jobs": 1,
        })
        hierarchy_models, hierarchy_model_modes = trainer._fit_hierarchy_models(
            panel=train_df,
            feature_columns=hierarchy_feature_columns,
            state_feature_columns=feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
        )

        pred_log = reg_median.predict(test_df[feature_columns].to_numpy())
        pred_lo = reg_lower.predict(test_df[feature_columns].to_numpy())
        pred_hi = reg_upper.predict(test_df[feature_columns].to_numpy())
        pred_next = np.expm1(pred_log)
        pred_next_lo = np.expm1(pred_lo)
        pred_next_hi = np.expm1(pred_hi)
        forecast_implied_prob = trainer._forecast_implied_event_probability(
            quantile_predictions={
                0.1: pred_next_lo,
                0.5: pred_next,
                0.9: pred_next_hi,
            },
            current_known=test_df["current_known_incidence"].to_numpy(),
            baseline=test_df["seasonal_baseline"].to_numpy(),
            mad=test_df["seasonal_mad"].to_numpy(),
            tau=fold_tau,
            kappa=fold_kappa,
            min_absolute_incidence=config.min_absolute_incidence,
        )
        hierarchy_inputs = trainer._predict_hierarchy_aggregate_quantiles(
            frame=test_df,
            source_panel=working,
            feature_columns=hierarchy_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
            hierarchy_models=hierarchy_models,
            state_feature_columns=feature_columns,
            hierarchy_model_modes=hierarchy_model_modes,
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
            }
        )
        fold_frames.append(
            pd.DataFrame(
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
                    "event_probability_calibrated": calibrated_prob,
                    "event_probability_raw": raw_prob,
                    "forecast_implied_event_probability": forecast_implied_prob,
                    "amelag_only_probability": ww_prob,
                    "persistence_probability": persistence_prob,
                    "climatology_probability": climatology_prob,
                    "current_known_incidence": test_df["current_known_incidence"].values.astype(float),
                    "seasonal_baseline": test_df["seasonal_baseline"].values.astype(float),
                    "seasonal_mad": test_df["seasonal_mad"].values.astype(float),
                    "next_week_incidence": test_df["next_week_incidence"].values.astype(float),
                    "expected_next_week_incidence": pred_next,
                    "expected_target_incidence": pred_next,
                    "prediction_interval_lower": pred_next_lo,
                    "prediction_interval_upper": pred_next_hi,
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
                    "residual": test_df["next_week_incidence"].values.astype(float) - pred_next,
                    "absolute_error": np.abs(test_df["next_week_incidence"].values.astype(float) - pred_next),
                    "selected_tau": fold_tau,
                    "selected_kappa": fold_kappa,
                    "action_threshold": fold_threshold,
                    "calibration_mode": calibration_mode,
                }
            )
        )

    if not fold_frames:
        raise ValueError("Regional backtest produced no valid folds.")

    oof_frame = pd.concat(fold_frames, ignore_index=True)
    aggregate = trainer._aggregate_metrics(
        frame=oof_frame,
        action_threshold=action_threshold,
    )
    baselines = trainer._baseline_metrics(
        frame=oof_frame,
        action_threshold=action_threshold,
    )
    benchmark_frame = oof_frame.copy()
    benchmark_frame["candidate"] = "regional_pooled_panel"
    benchmark_frame["y_true"] = benchmark_frame["next_week_incidence"].astype(float)
    benchmark_frame["q_0.1"] = benchmark_frame["prediction_interval_lower"].astype(float)
    benchmark_frame["q_0.5"] = benchmark_frame["expected_target_incidence"].astype(float)
    benchmark_frame["q_0.9"] = benchmark_frame["prediction_interval_upper"].astype(float)
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
        quantile_predictions={
            0.1: benchmark_frame["q_0.1"].to_numpy(dtype=float),
            0.5: benchmark_frame["q_0.5"].to_numpy(dtype=float),
            0.9: benchmark_frame["q_0.9"].to_numpy(dtype=float),
        },
        baseline_quantiles=persistence_baseline_quantile_predictions,
        event_labels=benchmark_frame["event_label"].to_numpy(dtype=int),
        event_probabilities=benchmark_frame["event_probability"].to_numpy(dtype=float),
        action_threshold=action_threshold,
    )
    persistence_forecast_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=persistence_baseline_quantile_predictions,
    )
    climatology_forecast_metrics = summarize_probabilistic_metrics(
        y_true=benchmark_frame["y_true"].to_numpy(dtype=float),
        quantile_predictions=climatology_baseline_quantile_predictions,
    )
    benchmark_leaderboard = build_leaderboard(
        combined_benchmark_frame,
        group_by=("virus_typ", "horizon_days", "bundesland"),
        action_threshold=action_threshold,
    )
    candidate_summaries = []
    for candidate_name, candidate_frame in combined_benchmark_frame.groupby("candidate", dropna=False):
        candidate_metrics = summarize_probabilistic_metrics(
            y_true=candidate_frame["y_true"].to_numpy(dtype=float),
            quantile_predictions={
                0.1: candidate_frame["q_0.1"].to_numpy(dtype=float),
                0.5: candidate_frame["q_0.5"].to_numpy(dtype=float),
                0.9: candidate_frame["q_0.9"].to_numpy(dtype=float),
            },
            baseline_quantiles={
                0.1: candidate_frame["baseline_q_0.1"].to_numpy(dtype=float),
                0.5: candidate_frame["baseline_q_0.5"].to_numpy(dtype=float),
                0.9: candidate_frame["baseline_q_0.9"].to_numpy(dtype=float),
            } if {"baseline_q_0.1", "baseline_q_0.5", "baseline_q_0.9"}.issubset(candidate_frame.columns) else None,
            event_labels=candidate_frame["event_label"].to_numpy(dtype=int),
            event_probabilities=candidate_frame["event_probability"].to_numpy(dtype=float),
            action_threshold=action_threshold,
        )
        candidate_summaries.append(
            {
                "candidate": str(candidate_name),
                "metrics": candidate_metrics,
                "samples": int(len(candidate_frame)),
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
            },
            "forecast_core_deltas": _forecast_core_delta_summary(
                candidate_metrics=benchmark_metrics,
                persistence_metrics=persistence_forecast_metrics,
                climatology_metrics=climatology_forecast_metrics,
            ),
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


def aggregate_metrics(frame: pd.DataFrame, *, action_threshold: float) -> dict[str, float]:
    effective_threshold = None if "action_threshold" in frame.columns else action_threshold
    metrics = _event_probability_metrics(
        frame,
        score_col="event_probability_calibrated",
        action_threshold=effective_threshold,
    )
    metrics.update(
        {
            "precision_at_top5": precision_at_k(frame, k=5),
            "median_lead_days": median_lead_days(frame, threshold=effective_threshold),
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
    metric_names: tuple[str, ...] = EVENT_DELTA_METRICS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fold, fold_frame in frame.groupby("fold", dropna=False):
        candidate_metrics = _event_probability_metrics(
            fold_frame,
            score_col=candidate_col,
            action_threshold=action_threshold,
        )
        baseline_metrics = _event_probability_metrics(
            fold_frame,
            score_col=baseline_col,
            action_threshold=action_threshold,
        )
        row = {"fold": int(fold)}
        row.update(
            {
                metric_name: _metric_delta(
                    candidate_metrics.get(metric_name),
                    baseline_metrics.get(metric_name),
                    metric_name,
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
        candidate_metrics = _event_probability_metrics(
            sampled,
            score_col=candidate_col,
            action_threshold=action_threshold,
        )
        baseline_metrics = _event_probability_metrics(
            sampled,
            score_col=baseline_col,
            action_threshold=action_threshold,
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
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    delta_summary: dict[str, Any] = {}
    ci_summary: dict[str, Any] = {}
    fold_summary: dict[str, Any] = {}
    candidate_metrics = _event_probability_metrics(
        frame,
        score_col=candidate_col,
        action_threshold=action_threshold,
    )
    for baseline_name, baseline_col in baseline_map.items():
        baseline_metrics = _event_probability_metrics(
            frame,
            score_col=baseline_col,
            action_threshold=action_threshold,
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
        )
        fold_summary[baseline_name] = _fold_metric_deltas(
            frame,
            candidate_col=candidate_col,
            baseline_col=baseline_col,
            action_threshold=action_threshold,
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
    


def baseline_metrics(trainer, frame: pd.DataFrame, *, action_threshold: float) -> dict[str, dict[str, float]]:
    baselines: dict[str, dict[str, float]] = {}
    effective_threshold = None if "action_threshold" in frame.columns else action_threshold
    for name, column in {
        "persistence": "persistence_probability",
        "climatology": "climatology_probability",
        "amelag_only": "amelag_only_probability",
    }.items():
        baselines[name] = _event_probability_metrics(
            frame,
            score_col=column,
            action_threshold=effective_threshold,
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
        fold_diagnostics.append(
            {
                "fold": int(fold),
                "rows": int(len(fold_frame)),
                "positive_count": positive_count,
                "prevalence": round(float(positive_count / max(len(fold_frame), 1)), 6),
                "positive_regions": positive_regions,
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
        "event_model": _event_probability_metrics(
            frame,
            score_col="event_probability_calibrated",
            action_threshold=effective_threshold,
        ),
        "persistence": _event_probability_metrics(
            frame,
            score_col="persistence_probability",
            action_threshold=effective_threshold,
        ),
        "climatology": _event_probability_metrics(
            frame,
            score_col="climatology_probability",
            action_threshold=effective_threshold,
        ),
        "amelag_only": _event_probability_metrics(
            frame,
            score_col="amelag_only_probability",
            action_threshold=effective_threshold,
        ),
    }
    if "forecast_implied_event_probability" in frame.columns:
        event_benchmark_paths["forecast_implied"] = _event_probability_metrics(
            frame,
            score_col="forecast_implied_event_probability",
            action_threshold=effective_threshold,
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
        )
        delta_vs_persistence["forecast_implied"] = forecast_implied_deltas["persistence"]
        delta_vs_climatology["forecast_implied"] = forecast_implied_deltas["climatology"]
        delta_vs_amelag_only["forecast_implied"] = forecast_implied_deltas["amelag_only"]
        delta_ci_95["forecast_implied"] = forecast_implied_ci
        fold_metric_deltas["forecast_implied"] = forecast_implied_fold_deltas
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
