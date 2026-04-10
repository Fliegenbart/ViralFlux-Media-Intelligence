from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper


def build_hierarchy_metadata(
    trainer,
    *,
    panel: pd.DataFrame,
    oof_frame: pd.DataFrame,
) -> dict[str, Any]:
    state_order = trainer._state_order_from_panel(panel)
    if not state_order:
        return {
            "enabled": False,
            "reconciliation_method": "not_available",
            "hierarchy_consistency_status": "empty",
            "max_coherence_gap": 0.0,
            "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            "cluster_assignments": {},
            "cluster_order": [],
            "state_order": [],
            "state_residual_history": [],
        }

    cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
        panel,
        state_col="bundesland",
        value_col="current_known_incidence",
        date_col="as_of_date",
    )
    state_weight_map: dict[str, float] = {}
    if {"bundesland", "state_population_millions"}.issubset(panel.columns):
        weights = (
            panel.dropna(subset=["bundesland"])
            .groupby("bundesland")["state_population_millions"]
            .median()
            .to_dict()
        )
        state_weight_map = {str(key): float(value) for key, value in weights.items() if pd.notna(value)}

    residual_history: list[list[float]] = []
    if not oof_frame.empty and {"as_of_date", "bundesland", "residual"}.issubset(oof_frame.columns):
        residual_matrix = (
            oof_frame.assign(as_of_date=pd.to_datetime(oof_frame["as_of_date"]).dt.normalize())
            .pivot_table(
                index="as_of_date",
                columns="bundesland",
                values="residual",
                aggfunc="mean",
            )
            .reindex(columns=state_order)
            .fillna(0.0)
            .tail(180)
        )
        residual_history = residual_matrix.to_numpy(dtype=float).tolist()

    reconciliation_summary: dict[str, Any] = {
        "reconciliation_method": "not_available",
        "hierarchy_consistency_status": "not_checked",
        "max_coherence_gap": 0.0,
        "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
        "cluster_order": sorted({value for value in cluster_assignments.values()}),
    }
    if not oof_frame.empty and {
        "bundesland",
        "prediction_interval_lower",
        "expected_target_incidence",
        "prediction_interval_upper",
    }.issubset(oof_frame.columns):
        latest_state_rows = (
            oof_frame.assign(as_of_date=pd.to_datetime(oof_frame["as_of_date"]).dt.normalize())
            .sort_values("as_of_date")
            .groupby("bundesland", as_index=False)
            .tail(1)
        )
        latest_by_state = latest_state_rows.set_index("bundesland")
        available_states = [state for state in state_order if state in latest_by_state.index]
        if available_states:
            state_quantiles = {
                0.1: np.asarray(
                    [float(latest_by_state.at[state, "prediction_interval_lower"]) for state in available_states],
                    dtype=float,
                ),
                0.5: np.asarray(
                    [float(latest_by_state.at[state, "expected_target_incidence"]) for state in available_states],
                    dtype=float,
                ),
                0.9: np.asarray(
                    [float(latest_by_state.at[state, "prediction_interval_upper"]) for state in available_states],
                    dtype=float,
                ),
            }
            _, reconciliation_summary = GeoHierarchyHelper.reconcile_quantiles(
                state_quantiles,
                cluster_assignments={
                    state: cluster_assignments[state]
                    for state in available_states
                    if state in cluster_assignments
                },
                state_order=available_states,
                residual_history=np.asarray(residual_history, dtype=float) if residual_history else None,
                state_weights={state: state_weight_map.get(state, 1.0) for state in available_states},
            )

    return {
        "enabled": True,
        "aggregate_input_strategy": "weighted_feature_pool_same_model",
        "model_sources": {
            "state": "regional_pooled_panel",
            "cluster": "regional_cluster_aggregate",
            "national": "regional_national_aggregate",
        },
        "reconciliation_method": reconciliation_summary["reconciliation_method"],
        "hierarchy_consistency_status": reconciliation_summary["hierarchy_consistency_status"],
        "max_coherence_gap": reconciliation_summary["max_coherence_gap"],
        "hierarchy_driver_attribution": {
            "state": float(reconciliation_summary.get("state", 1.0)),
            "cluster": float(reconciliation_summary.get("cluster", 0.0)),
            "national": float(reconciliation_summary.get("national", 0.0)),
        },
        "cluster_assignments": cluster_assignments,
        "cluster_order": reconciliation_summary.get("cluster_order")
        or sorted({value for value in cluster_assignments.values()}),
        "state_order": state_order,
        "state_weights": state_weight_map,
        "state_residual_history": residual_history,
    }


def fit_final_models(
    trainer,
    *,
    panel: pd.DataFrame,
    feature_columns: list[str],
    hierarchy_feature_columns: list[str],
    oof_frame: pd.DataFrame,
    action_threshold: float,
    regressor_config: dict[str, dict[str, Any]],
    supported_quantiles,
    quantile_regressor_config_fn,
    learned_event_model_cls,
    calibration_holdout_fraction: float,
) -> dict[str, Any]:
    calibration_frame = oof_frame.copy()
    if "as_of_date" not in calibration_frame.columns:
        calibration_frame["as_of_date"] = pd.date_range(
            start="2000-01-01",
            periods=len(calibration_frame),
            freq="D",
        )

    classifier = trainer._fit_classifier_from_frame(panel, feature_columns)
    calibration, calibration_mode = trainer._select_guarded_calibration(
        calibration_frame=calibration_frame[
            ["as_of_date", "event_label", "event_probability_raw"]
        ].copy(),
        raw_probability_col="event_probability_raw",
        action_threshold=action_threshold,
    )
    reg_median = trainer._fit_regressor_from_frame(
        panel,
        feature_columns,
        regressor_config["median"],
    )
    reg_lower = trainer._fit_regressor_from_frame(
        panel,
        feature_columns,
        regressor_config["lower"],
    )
    reg_upper = trainer._fit_regressor_from_frame(
        panel,
        feature_columns,
        regressor_config["upper"],
    )
    hierarchy_models, hierarchy_model_modes = trainer._fit_hierarchy_models(
        panel=panel,
        feature_columns=hierarchy_feature_columns,
        state_feature_columns=feature_columns,
        reg_lower=reg_lower,
        reg_median=reg_median,
        reg_upper=reg_upper,
    )
    quantile_regressors: dict[float, XGBRegressor] = {
        0.1: reg_lower,
        0.5: reg_median,
        0.9: reg_upper,
    }
    for quantile in supported_quantiles:
        if quantile in quantile_regressors:
            continue
        quantile_regressors[float(quantile)] = trainer._fit_regressor_from_frame(
            panel,
            feature_columns,
            quantile_regressor_config_fn(float(quantile)),
        )
    learned_event_model = None
    if "event_label" in panel.columns and panel["event_label"].nunique() >= 2:
        calibration_rows = max(int(len(panel) * calibration_holdout_fraction), 20)
        calibration_rows = min(calibration_rows, max(len(panel) - 20, 0))
        calibration_frame_full = (
            panel.tail(calibration_rows).copy() if calibration_rows > 0 else pd.DataFrame()
        )
        train_frame_full = panel.iloc[:-calibration_rows].copy() if calibration_rows > 0 else panel.copy()
        if train_frame_full["event_label"].nunique() >= 2:
            calibration_dates = (
                calibration_frame_full["as_of_date"].to_numpy()
                if not calibration_frame_full.empty and "as_of_date" in calibration_frame_full.columns
                else None
            )
            learned_event_model = learned_event_model_cls.fit(
                X_train=train_frame_full[feature_columns].to_numpy(),
                y_train=train_frame_full["event_label"].to_numpy(),
                X_calibration=(
                    calibration_frame_full[feature_columns].to_numpy()
                    if not calibration_frame_full.empty
                    and calibration_frame_full["event_label"].nunique() >= 2
                    else None
                ),
                y_calibration=(
                    calibration_frame_full["event_label"].to_numpy()
                    if not calibration_frame_full.empty
                    and calibration_frame_full["event_label"].nunique() >= 2
                    else None
                ),
                calibration_dates=calibration_dates,
            )
    return {
        "classifier": classifier,
        "calibration": calibration,
        "calibration_mode": calibration_mode,
        "regressor_median": reg_median,
        "regressor_lower": reg_lower,
        "regressor_upper": reg_upper,
        "quantile_regressors": quantile_regressors,
        "learned_event_model": learned_event_model,
        "hierarchy_models": hierarchy_models,
        "hierarchy_model_modes": hierarchy_model_modes,
    }


def persist_artifacts(
    *,
    model_dir: Path,
    final_artifacts: dict[str, Any],
    metadata: dict[str, Any],
    backtest_payload: dict[str, Any],
    dataset_manifest: dict[str, Any],
    point_in_time_manifest: dict[str, Any],
    json_safe_fn,
    quantile_key_fn,
    event_definition_version,
    target_window_days,
) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)

    final_artifacts["classifier"].save_model(str(model_dir / "classifier.json"))
    final_artifacts["regressor_median"].save_model(str(model_dir / "regressor_median.json"))
    final_artifacts["regressor_lower"].save_model(str(model_dir / "regressor_lower.json"))
    final_artifacts["regressor_upper"].save_model(str(model_dir / "regressor_upper.json"))
    hierarchy_models = final_artifacts.get("hierarchy_models") or {}
    cluster_models = hierarchy_models.get("cluster") or {}
    national_models = hierarchy_models.get("national") or {}
    if cluster_models:
        cluster_models["median"].save_model(str(model_dir / "cluster_regressor_median.json"))
        cluster_models["lower"].save_model(str(model_dir / "cluster_regressor_lower.json"))
        cluster_models["upper"].save_model(str(model_dir / "cluster_regressor_upper.json"))
    if national_models:
        national_models["median"].save_model(str(model_dir / "national_regressor_median.json"))
        national_models["lower"].save_model(str(model_dir / "national_regressor_lower.json"))
        national_models["upper"].save_model(str(model_dir / "national_regressor_upper.json"))
    for quantile, model in sorted((final_artifacts.get("quantile_regressors") or {}).items()):
        model.save_model(str(model_dir / f"{quantile_key_fn(float(quantile))}.json"))

    with open(model_dir / "calibration.pkl", "wb") as handle:
        pickle.dump(final_artifacts["calibration"], handle)

    with open(model_dir / "metadata.json", "w") as handle:
        json.dump(json_safe_fn(metadata), handle, indent=2)

    with open(model_dir / "backtest.json", "w") as handle:
        json.dump(json_safe_fn(backtest_payload), handle, indent=2)

    with open(model_dir / "threshold_manifest.json", "w") as handle:
        json.dump(
            json_safe_fn(
                {
                    "selected_tau": metadata["selected_tau"],
                    "selected_kappa": metadata["selected_kappa"],
                    "action_threshold": metadata["action_threshold"],
                    "min_event_absolute_incidence": metadata["min_event_absolute_incidence"],
                    "event_definition_version": event_definition_version,
                    "event_definition_config": metadata.get("event_definition_config") or {},
                    "signal_bundle_version": metadata.get("signal_bundle_version"),
                    "rollout_mode": metadata.get("rollout_mode"),
                    "activation_policy": metadata.get("activation_policy"),
                    "horizon_days": metadata.get("horizon_days"),
                    "target_window_days": metadata.get("target_window_days") or list(target_window_days),
                }
            ),
            handle,
            indent=2,
        )

    with open(model_dir / "dataset_manifest.json", "w") as handle:
        json.dump(json_safe_fn(dataset_manifest), handle, indent=2)
    with open(model_dir / "point_in_time_snapshot.json", "w") as handle:
        json.dump(json_safe_fn(point_in_time_manifest), handle, indent=2)
