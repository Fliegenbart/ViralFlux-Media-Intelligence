from __future__ import annotations

import os
from datetime import datetime
from math import comb
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
MIN_EVALUABLE_PANEL_WEEKS = 12


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
            "max_depth": 4,
            "learning_rate": 0.05,
            "min_child_weight": 2,
            "objective": "reg:quantileerror",
            "quantile_alpha": 0.1,
            "random_state": 42,
            "verbosity": 0,
            "n_jobs": 1,
        })
        # Q90 reparameterised 2026-04-20 — see REGIONAL_REGRESSOR_CONFIG
        # upper notes for the rationale (plateau-breaker via max_depth 5 +
        # min_child_weight + mild L1).
        reg_upper = trainer._fit_regressor_from_frame(train_df, feature_columns, {
            "n_estimators": 130,
            "max_depth": 5,
            "learning_rate": 0.05,
            "min_child_weight": 2,
            "reg_alpha": 0.1,
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
    panel_evaluation = _build_panel_evaluation(oof_frame)
    aggregate = trainer._aggregate_metrics(
        frame=oof_frame,
        action_threshold=action_threshold,
    )
    baselines = trainer._baseline_metrics(
        frame=oof_frame,
        action_threshold=action_threshold,
    )
    panel_model_precision = _panel_precision_at_top3(panel_evaluation)
    if panel_model_precision is not None:
        aggregate["precision_at_top3"] = panel_model_precision
    panel_persistence_precision = _panel_precision_at_top3(
        panel_evaluation,
        hit_key="persistence_was_hit",
    )
    if panel_persistence_precision is not None:
        baselines.setdefault("persistence", {})["precision_at_top3"] = panel_persistence_precision
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
    quality_gate = _quality_gate_with_panel_evaluation_check(
        quality_gate,
        panel_evaluation,
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
        panel_evaluation=panel_evaluation,
    )
    backtest_payload["backtest_policy"] = _build_backtest_policy(
        prepared_frame=working,
        oof_frame=oof_frame,
        panel_evaluation=panel_evaluation,
        feature_columns=feature_columns,
        event_feature_columns=effective_event_feature_columns,
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


def _date_key(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return str(value)[:10]


def _random_expected_hit_probability(
    *,
    scored_region_count: int,
    observed_event_count: int,
    k: int = 3,
) -> float | None:
    if scored_region_count <= 0 or observed_event_count <= 0:
        return None
    top_k = min(int(k), int(scored_region_count))
    non_event_count = max(int(scored_region_count) - int(observed_event_count), 0)
    no_hit_combinations = comb(non_event_count, top_k) if non_event_count >= top_k else 0
    return 1.0 - (no_hit_combinations / comb(int(scored_region_count), top_k))


def _build_panel_evaluation(
    frame: pd.DataFrame,
    *,
    min_regions_for_top3: int = 14,
    region_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Build common weekly panel rows before per-region timeline truncation."""
    universe = list(region_universe or ALL_BUNDESLAENDER)
    universe_set = set(universe)
    rows: list[dict[str, Any]] = []
    diagnostics = {
        "issue_calendar_type": "weekly_shared_issue_calendar",
        "feature_asof_policy": "latest_available_at_or_before_cutoff",
        "target_join_policy": "weekly_target_week_start",
        "forecast_target_semantics": "day_horizon_to_weekly_target",
        "target_week_start_formula": "week_start(forecast_issue_cutoff_date + horizon_days)",
    }
    if frame.empty or "bundesland" not in frame.columns or "as_of_date" not in frame.columns:
        return {
            "schema_version": "panel_evaluation_v1",
            **diagnostics,
            "region_universe": universe,
            "expected_region_count": len(universe),
            "rows": rows,
        }

    working = frame.copy()
    if "forecast_issue_cutoff_date" in working.columns:
        working["_forecast_issue_cutoff_date"] = working["forecast_issue_cutoff_date"].map(_date_key)
    elif "forecast_issue_date" in working.columns:
        working["_forecast_issue_cutoff_date"] = working["forecast_issue_date"].map(_date_key)
    else:
        working["_forecast_issue_cutoff_date"] = working["as_of_date"].map(_date_key)

    if "forecast_issue_week_start" in working.columns:
        working["_forecast_issue_week_start"] = working["forecast_issue_week_start"].map(_date_key)
    else:
        working["_forecast_issue_week_start"] = working["_forecast_issue_cutoff_date"].map(
            lambda value: _date_key(
                pd.Timestamp(value) - pd.Timedelta(days=int(pd.Timestamp(value).weekday()))
            )
            if value
            else None
        )

    if "target_week_start" in working.columns:
        working["_target_week_start"] = working["target_week_start"].map(_date_key)
    else:
        working["_target_week_start"] = working["_forecast_issue_cutoff_date"]

    working["_virus"] = (
        working["virus_typ"].astype(str)
        if "virus_typ" in working.columns
        else pd.Series([None] * len(working), index=working.index)
    )
    working["_horizon_days"] = (
        working["horizon_days"].map(lambda value: int(value) if not pd.isna(value) else None)
        if "horizon_days" in working.columns
        else pd.Series([None] * len(working), index=working.index)
    )

    for (
        virus,
        horizon_days,
        issue_week_start,
        issue_cutoff_date,
        target_week_start,
    ), panel in working.groupby(
        [
            "_virus",
            "_horizon_days",
            "_forecast_issue_week_start",
            "_forecast_issue_cutoff_date",
            "_target_week_start",
        ],
        dropna=False,
    ):
        if not issue_cutoff_date:
            continue
        panel = panel.copy()
        panel["bundesland"] = panel["bundesland"].astype(str)
        scored_panel = panel.loc[panel["bundesland"].isin(universe_set)].copy()
        present_regions = set(scored_panel["bundesland"].dropna().astype(str).unique().tolist())

        score_col = (
            "event_probability_calibrated"
            if "event_probability_calibrated" in scored_panel.columns
            else "event_probability_raw"
        )
        has_score = (
            scored_panel[score_col].notna()
            if score_col in scored_panel.columns
            else pd.Series(False, index=scored_panel.index)
        )
        has_truth = (
            scored_panel["event_label"].notna()
            if "event_label" in scored_panel.columns
            else pd.Series(False, index=scored_panel.index)
        )
        scored_for_rank = scored_panel.loc[has_score & has_truth].copy()
        scored_regions = sorted(
            scored_for_rank["bundesland"].dropna().astype(str).unique().tolist()
        )
        scored_region_set = set(scored_regions)
        missing_regions = [code for code in universe if code not in scored_region_set]
        missing_region_reasons = {}
        for code in missing_regions:
            if code not in present_regions:
                missing_region_reasons[code] = "missing_panel_row"
                continue
            region_rows = scored_panel.loc[scored_panel["bundesland"] == code]
            if score_col not in region_rows.columns or region_rows[score_col].isna().all():
                missing_region_reasons[code] = "missing_model_score"
            elif "event_label" not in region_rows.columns or region_rows["event_label"].isna().all():
                missing_region_reasons[code] = "missing_truth_label"
            else:
                missing_region_reasons[code] = "not_scored"

        predicted_top3: list[dict[str, Any]] = []
        if not scored_for_rank.empty and score_col in scored_for_rank.columns:
            top_model = scored_for_rank.sort_values(score_col, ascending=False).head(3)
            predicted_top3 = [
                {
                    "code": str(row["bundesland"]),
                    "probability": float(row[score_col]),
                }
                for _, row in top_model.iterrows()
            ]

        observed_event_regions: list[str] = []
        if "event_label" in scored_for_rank.columns:
            observed_event_regions = sorted(
                scored_for_rank.loc[
                    scored_for_rank["event_label"].astype(int) == 1,
                    "bundesland",
                ]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        persistence_top3: list[dict[str, Any]] = []
        persistence_was_hit: bool | None = None
        if "current_known_incidence" in scored_for_rank.columns:
            persistence_scored = scored_for_rank.loc[
                scored_for_rank["current_known_incidence"].notna()
            ].copy()
            if len(persistence_scored) == len(scored_regions):
                top_persistence = persistence_scored.sort_values(
                    "current_known_incidence",
                    ascending=False,
                ).head(3)
                persistence_top3 = [
                    {
                        "code": str(row["bundesland"]),
                        "current_known_incidence": float(row["current_known_incidence"]),
                    }
                    for _, row in top_persistence.iterrows()
                ]
                persistence_codes = {item["code"] for item in persistence_top3}
                persistence_was_hit = bool(persistence_codes & set(observed_event_regions))

        predicted_codes = {item["code"] for item in predicted_top3}
        observed_codes = set(observed_event_regions)
        scored_region_count = len(scored_regions)
        observed_event_count = len(observed_event_regions)
        rows.append(
            {
                "virus": str(virus) if virus is not None and not pd.isna(virus) else None,
                "horizon_days": int(horizon_days)
                if horizon_days is not None and not pd.isna(horizon_days)
                else None,
                "forecast_issue_date": str(issue_cutoff_date)[:10],
                "forecast_issue_week": str(issue_week_start or issue_cutoff_date)[:10],
                "forecast_issue_week_start": str(issue_week_start or issue_cutoff_date)[:10],
                "forecast_issue_cutoff_date": str(issue_cutoff_date)[:10],
                "target_week_start": str(target_week_start or issue_cutoff_date)[:10],
                "region_universe": universe,
                "scored_regions": scored_regions,
                "missing_regions": missing_regions,
                "missing_region_reasons": missing_region_reasons,
                "scored_region_count": scored_region_count,
                "expected_region_count": len(universe),
                "observed_event_regions": observed_event_regions,
                "observed_event_count": observed_event_count,
                "predicted_top3": predicted_top3,
                "persistence_top3": persistence_top3,
                "model_was_hit": bool(predicted_codes & observed_codes),
                "persistence_was_hit": persistence_was_hit,
                "random_expected_hit_probability": _random_expected_hit_probability(
                    scored_region_count=scored_region_count,
                    observed_event_count=observed_event_count,
                    k=3,
                ),
                "is_evaluable_top3_panel": bool(
                    scored_region_count >= int(min_regions_for_top3)
                    and observed_event_count > 0
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            row.get("forecast_issue_week_start") or "",
            row.get("forecast_issue_cutoff_date") or "",
            row.get("target_week_start") or "",
        )
    )
    return {
        "schema_version": "panel_evaluation_v1",
        **diagnostics,
        "region_universe": universe,
        "expected_region_count": len(universe),
        "rows": _json_safe(rows),
    }


def _panel_precision_at_top3(
    panel_evaluation: dict[str, Any],
    *,
    hit_key: str = "model_was_hit",
) -> float | None:
    rows = [
        row for row in panel_evaluation.get("rows") or []
        if row.get("is_evaluable_top3_panel")
    ]
    if not rows:
        return None
    evaluable = [row for row in rows if row.get(hit_key) is not None]
    if not evaluable:
        return None
    return round(
        sum(1 for row in evaluable if bool(row.get(hit_key))) / len(evaluable),
        6,
    )


def _source_start_by_age_columns(prepared_frame: pd.DataFrame) -> dict[str, str | None]:
    if prepared_frame.empty or "as_of_date" not in prepared_frame.columns:
        return {}
    as_of_dates = pd.to_datetime(prepared_frame["as_of_date"], errors="coerce").dt.normalize()
    source_age_columns = {
        "wastewater": ("ww_feature_age_days",),
        "wastewater_cross_virus_context": (
            "ww_context_feature_age_days",
            "wastewater_context_feature_age_days",
        ),
        "survstat_truth": ("survstat_feature_age_days", "truth_feature_age_days"),
        "grippeweb": ("grippeweb_feature_age_days",),
        "ifsg_influenza": ("ifsg_influenza_feature_age_days",),
        "ifsg_rsv": ("ifsg_rsv_feature_age_days",),
        "are": ("are_feature_age_days",),
    }
    starts: dict[str, str | None] = {}
    for source, columns in source_age_columns.items():
        candidates = []
        for column in columns:
            if column not in prepared_frame.columns:
                continue
            ages = pd.to_numeric(prepared_frame[column], errors="coerce")
            visible = as_of_dates - pd.to_timedelta(ages, unit="D")
            visible = visible.loc[visible.notna()]
            if not visible.empty:
                candidates.append(visible.min())
        starts[source] = min(candidates).date().isoformat() if candidates else None
    return starts


def _target_leakage_guards(
    *,
    feature_columns: list[str],
    event_feature_columns: list[str],
) -> dict[str, Any]:
    feature_set = {str(column) for column in feature_columns}
    event_feature_set = {str(column) for column in event_feature_columns}
    all_feature_set = feature_set | event_feature_set
    forbidden_target_columns = {
        "event_label",
        "next_week_incidence",
        "target_incidence",
        "target_date",
        "target_week_start",
        "y_next_log",
    }
    leaked_columns = sorted(all_feature_set & forbidden_target_columns)
    guards = {
        "event_label_not_in_feature_columns": "event_label" not in all_feature_set,
        "next_week_incidence_not_in_feature_columns": "next_week_incidence" not in all_feature_set,
        "target_week_survstat_not_used_as_feature": not bool(
            all_feature_set
            & {
                "event_label",
                "next_week_incidence",
                "target_incidence",
                "target_date",
                "target_week_start",
                "y_next_log",
            }
        ),
        "current_known_incidence_policy": "allowed_only_as_asof_safe_event_anchor",
        "current_known_incidence_in_regression_features": "current_known_incidence" in feature_set,
        "current_known_incidence_in_event_features": "current_known_incidence" in event_feature_set,
        "current_known_incidence_available_asof_policy": (
            "visible SurvStat rows must have available_date at or before forecast_issue_cutoff_date"
        ),
        "leaked_target_columns": leaked_columns,
    }
    guards["passed"] = bool(
        guards["event_label_not_in_feature_columns"]
        and guards["next_week_incidence_not_in_feature_columns"]
        and guards["target_week_survstat_not_used_as_feature"]
    )
    return guards


def _historical_evidence_level(*, actual_test_weeks: int, evaluable_panel_weeks: int) -> str:
    if evaluable_panel_weeks < MIN_EVALUABLE_PANEL_WEEKS or actual_test_weeks < 26:
        return "limited"
    if actual_test_weeks < 52:
        return "moderate"
    return "strong"


def _build_backtest_policy(
    *,
    prepared_frame: pd.DataFrame,
    oof_frame: pd.DataFrame,
    panel_evaluation: dict[str, Any],
    feature_columns: list[str],
    event_feature_columns: list[str],
) -> dict[str, Any]:
    prepared_issue_weeks = (
        int(pd.to_datetime(prepared_frame["as_of_date"], errors="coerce").dt.normalize().nunique())
        if "as_of_date" in prepared_frame.columns
        else 0
    )
    actual_test_weeks = (
        int(pd.to_datetime(oof_frame["as_of_date"], errors="coerce").dt.normalize().nunique())
        if "as_of_date" in oof_frame.columns
        else 0
    )
    rows = [row for row in panel_evaluation.get("rows") or [] if isinstance(row, dict)]
    evaluable_panel_weeks = sum(1 for row in rows if row.get("is_evaluable_top3_panel"))
    max_possible_test_weeks = max(0, int(prepared_issue_weeks) - int(_BACKTEST_MIN_TRAIN_PERIODS))
    return {
        "issue_calendar_type": panel_evaluation.get("issue_calendar_type") or "weekly_shared_issue_calendar",
        "prepared_issue_weeks": prepared_issue_weeks,
        "min_train_weeks": int(_BACKTEST_MIN_TRAIN_PERIODS),
        "min_test_weeks": int(_BACKTEST_MIN_TEST_PERIODS),
        "requested_splits": int(_BACKTEST_N_SPLITS),
        "max_possible_test_weeks": max_possible_test_weeks,
        "actual_test_weeks": actual_test_weeks,
        "panel_evaluation_rows": len(rows),
        "evaluable_panel_weeks": int(evaluable_panel_weeks),
        "min_evaluable_panel_weeks": int(MIN_EVALUABLE_PANEL_WEEKS),
        "data_start_by_source": _source_start_by_age_columns(prepared_frame),
        "historical_evidence_level": _historical_evidence_level(
            actual_test_weeks=actual_test_weeks,
            evaluable_panel_weeks=int(evaluable_panel_weeks),
        ),
        "limitation": (
            "short_history_limits_backtest_evidence"
            if max_possible_test_weeks < 52
            else None
        ),
        "target_leakage_guards": _target_leakage_guards(
            feature_columns=feature_columns,
            event_feature_columns=event_feature_columns,
        ),
    }


def _quality_gate_with_panel_evaluation_check(
    quality_gate: dict[str, Any],
    panel_evaluation: dict[str, Any],
    *,
    min_evaluable_panel_weeks: int = MIN_EVALUABLE_PANEL_WEEKS,
) -> dict[str, Any]:
    rows = [
        row for row in panel_evaluation.get("rows") or []
        if isinstance(row, dict)
    ]
    evaluable = [
        row for row in rows
        if row.get("is_evaluable_top3_panel")
    ]
    checks = dict(quality_gate.get("checks") or {})
    checks["min_evaluable_panel_weeks_passed"] = (
        len(evaluable) >= int(min_evaluable_panel_weeks)
    )
    thresholds = dict(quality_gate.get("thresholds") or {})
    thresholds["min_evaluable_panel_weeks"] = int(min_evaluable_panel_weeks)
    failed_checks = [key for key, passed in checks.items() if not bool(passed)]
    overall_passed = all(bool(passed) for passed in checks.values())
    return {
        **quality_gate,
        "overall_passed": bool(overall_passed),
        "forecast_readiness": "GO" if overall_passed else "WATCH",
        "checks": checks,
        "failed_checks": failed_checks,
        "thresholds": thresholds,
        "panel_evaluation_summary": {
            "evaluable_panel_weeks": len(evaluable),
            "panel_rows": len(rows),
            "min_evaluable_panel_weeks": int(min_evaluable_panel_weeks),
        },
    }


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
    panel_evaluation: dict[str, Any] | None = None,
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
    panel_evaluation = panel_evaluation or _build_panel_evaluation(frame)
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
        "panel_evaluation": panel_evaluation,
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
