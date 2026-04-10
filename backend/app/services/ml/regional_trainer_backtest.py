from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.time import utc_now
from app.services.ml.benchmarking.leaderboard import build_leaderboard
from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
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
            feature_columns=feature_columns,
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

        classifier = trainer._fit_classifier_from_frame(model_train_df, feature_columns)
        calibration, calibration_mode = trainer._select_guarded_calibration(
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
            action_threshold=fold_threshold,
        )
        raw_prob = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
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
                    "amelag_only_probability": ww_prob,
                    "persistence_probability": persistence_prob,
                    "climatology_probability": climatology_prob,
                    "current_known_incidence": test_df["current_known_incidence"].values.astype(float),
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
    hierarchy_benchmark_frame = trainer._hierarchy_reconciled_benchmark_frame(
        oof_frame=oof_frame,
        source_panel=working,
    )
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
        event_labels=benchmark_frame["event_label"].to_numpy(dtype=int),
        event_probabilities=benchmark_frame["event_probability"].to_numpy(dtype=float),
        action_threshold=action_threshold,
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
    return {
        "precision_at_top3": precision_at_k(frame, k=3),
        "precision_at_top5": precision_at_k(frame, k=5),
        "pr_auc": round(
            average_precision_safe(frame["event_label"], frame["event_probability_calibrated"]),
            6,
        ),
        "brier_score": round(
            brier_score_safe(frame["event_label"], frame["event_probability_calibrated"]),
            6,
        ),
        "ece": round(
            compute_ece(frame["event_label"], frame["event_probability_calibrated"]),
            6,
        ),
        "median_lead_days": median_lead_days(frame, threshold=effective_threshold),
        "activation_false_positive_rate": activation_false_positive_rate(
            frame,
            threshold=effective_threshold,
        ),
        "action_threshold": round(float(action_threshold), 4),
    }


def baseline_metrics(trainer, frame: pd.DataFrame, *, action_threshold: float) -> dict[str, dict[str, float]]:
    baselines: dict[str, dict[str, float]] = {}
    effective_threshold = None if "action_threshold" in frame.columns else action_threshold
    for name, column in {
        "persistence": "persistence_probability",
        "climatology": "climatology_probability",
        "amelag_only": "amelag_only_probability",
    }.items():
        baseline_frame = frame.copy()
        baseline_frame["baseline_probability"] = baseline_frame[column]
        baselines[name] = {
            "pr_auc": round(average_precision_safe(frame["event_label"], frame[column]), 6),
            "brier_score": round(brier_score_safe(frame["event_label"], frame[column]), 6),
            "ece": round(compute_ece(frame["event_label"], frame[column]), 6),
            "precision_at_top3": precision_at_k(
                baseline_frame,
                k=3,
                score_col="baseline_probability",
            ),
            "activation_false_positive_rate": activation_false_positive_rate(
                baseline_frame,
                threshold=effective_threshold,
                score_col="baseline_probability",
            ),
        }
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
    fold_diagnostics = []
    for fold, fold_frame in frame.groupby("fold"):
        fold_diagnostics.append(
            {
                "fold": int(fold),
                "rows": int(len(fold_frame)),
                "mean_absolute_error": round(float(fold_frame["absolute_error"].mean() or 0.0), 6)
                if "absolute_error" in fold_frame.columns
                else None,
                "mean_residual": round(float(fold_frame["residual"].mean() or 0.0), 6)
                if "residual" in fold_frame.columns
                else None,
                "calibration_mode": str(fold_frame["calibration_mode"].iloc[0]) if "calibration_mode" in fold_frame.columns else None,
            }
        )
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
