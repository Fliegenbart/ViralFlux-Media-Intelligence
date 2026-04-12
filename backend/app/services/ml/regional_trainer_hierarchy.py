from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper


def hierarchy_reconciled_benchmark_frame(
    trainer,
    *,
    oof_frame: pd.DataFrame,
    source_panel: pd.DataFrame,
    state_order_from_codes_fn,
) -> pd.DataFrame:
    required = {
        "as_of_date",
        "bundesland",
        "bundesland_name",
        "virus_typ",
        "horizon_days",
        "event_label",
        "event_probability_calibrated",
        "next_week_incidence",
        "expected_target_incidence",
        "prediction_interval_lower",
        "prediction_interval_upper",
    }
    if oof_frame.empty or not required.issubset(oof_frame.columns):
        return pd.DataFrame()

    working_panel = source_panel.copy()
    working_panel["as_of_date"] = pd.to_datetime(working_panel["as_of_date"]).dt.normalize()
    working_oof = oof_frame.copy()
    working_oof["as_of_date"] = pd.to_datetime(working_oof["as_of_date"]).dt.normalize()
    records: list[dict[str, Any]] = []
    historical_residual_rows: list[dict[str, float]] = []
    historical_cluster_rows: list[dict[str, float]] = []
    historical_national_rows: list[dict[str, float]] = []

    for as_of_date in sorted(working_oof["as_of_date"].dropna().unique()):
        date_value = pd.Timestamp(as_of_date).normalize()
        date_frame = working_oof.loc[working_oof["as_of_date"] == date_value].copy()
        target_regime = GeoHierarchyHelper.season_regime(date_value)
        state_order = state_order_from_codes_fn(date_frame["bundesland"].astype(str).tolist())
        if not state_order:
            continue
        date_frame = date_frame.drop_duplicates(subset=["bundesland"], keep="last").set_index("bundesland")
        available_states = [state for state in state_order if state in date_frame.index]
        if not available_states:
            continue
        target_horizon_days = (
            int(date_frame["horizon_days"].dropna().iloc[-1])
            if "horizon_days" in date_frame.columns and date_frame["horizon_days"].notna().any()
            else None
        )
        state_quantiles = {
            0.1: np.asarray(
                [float(date_frame.at[state, "prediction_interval_lower"]) for state in available_states],
                dtype=float,
            ),
            0.5: np.asarray(
                [float(date_frame.at[state, "expected_target_incidence"]) for state in available_states],
                dtype=float,
            ),
            0.9: np.asarray(
                [float(date_frame.at[state, "prediction_interval_upper"]) for state in available_states],
                dtype=float,
            ),
        }
        panel_until_date = working_panel.loc[working_panel["as_of_date"] <= date_value].copy()
        cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
            panel_until_date,
            state_col="bundesland",
            value_col="current_known_incidence",
            date_col="as_of_date",
        )
        cluster_order: list[str] = []
        seen_clusters: set[str] = set()
        for state in available_states:
            cluster_id = str(cluster_assignments.get(state) or "")
            if not cluster_id or cluster_id in seen_clusters:
                continue
            seen_clusters.add(cluster_id)
            cluster_order.append(cluster_id)
        state_weights: dict[str, float] = {}
        date_panel = panel_until_date.loc[panel_until_date["bundesland"].isin(available_states)].copy()
        if {"bundesland", "state_population_millions"}.issubset(date_panel.columns):
            latest_weights = (
                date_panel.sort_values("as_of_date")
                .groupby("bundesland", as_index=False)
                .tail(1)
                .set_index("bundesland")["state_population_millions"]
                .to_dict()
            )
            state_weights = {
                str(key): float(value) for key, value in latest_weights.items() if pd.notna(value)
            }
        residual_history = None
        if historical_residual_rows:
            residual_history = np.asarray(
                [
                    [float(row.get(state, 0.0)) for state in available_states]
                    for row in historical_residual_rows
                ],
                dtype=float,
            )
        derived_cluster_quantiles = {
            quantile: GeoHierarchyHelper._aggregate_states(
                np.asarray(values, dtype=float),
                state_order=available_states,
                cluster_assignments={
                    state: cluster_assignments[state]
                    for state in available_states
                    if state in cluster_assignments
                },
                cluster_order=cluster_order,
                state_weights=state_weights,
            )[0]
            for quantile, values in state_quantiles.items()
        }
        derived_national_quantiles = {
            quantile: GeoHierarchyHelper._aggregate_states(
                np.asarray(values, dtype=float),
                state_order=available_states,
                cluster_assignments={
                    state: cluster_assignments[state]
                    for state in available_states
                    if state in cluster_assignments
                },
                cluster_order=cluster_order,
                state_weights=state_weights,
            )[1]
            for quantile, values in state_quantiles.items()
        }
        model_cluster_quantiles = None
        if cluster_order and "cluster_id" in date_frame.columns and date_frame["cluster_id"].notna().any():
            model_cluster_quantiles = {
                0.1: np.asarray(
                    [
                        float(
                            date_frame.loc[
                                date_frame["cluster_id"] == cluster_id,
                                "cluster_prediction_interval_lower",
                            ].iloc[-1]
                        )
                        for cluster_id in cluster_order
                    ],
                    dtype=float,
                ),
                0.5: np.asarray(
                    [
                        float(
                            date_frame.loc[
                                date_frame["cluster_id"] == cluster_id,
                                "cluster_expected_target_incidence",
                            ].iloc[-1]
                        )
                        for cluster_id in cluster_order
                    ],
                    dtype=float,
                ),
                0.9: np.asarray(
                    [
                        float(
                            date_frame.loc[
                                date_frame["cluster_id"] == cluster_id,
                                "cluster_prediction_interval_upper",
                            ].iloc[-1]
                        )
                        for cluster_id in cluster_order
                    ],
                    dtype=float,
                ),
            }
        model_national_quantiles = None
        if (
            "national_expected_target_incidence" in date_frame.columns
            and date_frame["national_expected_target_incidence"].notna().any()
        ):
            model_national_quantiles = {
                0.1: np.asarray(
                    [float(date_frame["national_prediction_interval_lower"].dropna().iloc[-1])],
                    dtype=float,
                ),
                0.5: np.asarray(
                    [float(date_frame["national_expected_target_incidence"].dropna().iloc[-1])],
                    dtype=float,
                ),
                0.9: np.asarray(
                    [float(date_frame["national_prediction_interval_upper"].dropna().iloc[-1])],
                    dtype=float,
                ),
            }
        cluster_blend_choice = trainer._estimate_hierarchy_blend_choice(
            historical_cluster_rows,
            target_as_of_date=date_value,
            target_regime=target_regime,
            target_horizon_days=target_horizon_days,
        )
        national_blend_choice = trainer._estimate_hierarchy_blend_choice(
            historical_national_rows,
            target_as_of_date=date_value,
            target_regime=target_regime,
            target_horizon_days=target_horizon_days,
        )
        cluster_blend_weight = float(cluster_blend_choice.get("weight") or 0.0)
        national_blend_weight = float(national_blend_choice.get("weight") or 0.0)
        cluster_quantiles = trainer._blend_hierarchy_quantiles(
            model_quantiles=model_cluster_quantiles,
            baseline_quantiles=derived_cluster_quantiles,
            blend_weight=cluster_blend_weight,
        )
        national_quantiles = trainer._blend_hierarchy_quantiles(
            model_quantiles=model_national_quantiles,
            baseline_quantiles=derived_national_quantiles,
            blend_weight=national_blend_weight,
        )
        if cluster_blend_weight <= 0.0 and national_blend_weight <= 0.0:
            reconciled_quantiles = {
                float(quantile): np.asarray(values, dtype=float)
                for quantile, values in state_quantiles.items()
            }
            reconciled_meta = {
                "reconciliation_method": "state_sum_passthrough",
                "hierarchy_consistency_status": "coherent",
            }
        else:
            reconciled_quantiles, reconciled_meta = GeoHierarchyHelper.reconcile_quantiles(
                state_quantiles,
                cluster_assignments={
                    state: cluster_assignments[state]
                    for state in available_states
                    if state in cluster_assignments
                },
                state_order=available_states,
                cluster_quantiles=cluster_quantiles,
                national_quantiles=national_quantiles,
                residual_history=residual_history,
                state_weights=state_weights,
            )
        for idx, state in enumerate(available_states):
            row = date_frame.loc[state]
            expected_target = float(reconciled_quantiles[0.5][idx])
            lower = float(reconciled_quantiles[0.1][idx])
            upper = float(reconciled_quantiles[0.9][idx])
            y_true = float(row["next_week_incidence"])
            records.append(
                {
                    "fold": row.get("fold"),
                    "candidate": "regional_pooled_panel_mint",
                    "virus_typ": row["virus_typ"],
                    "bundesland": state,
                    "bundesland_name": row["bundesland_name"],
                    "as_of_date": date_value,
                    "target_date": row.get("target_date"),
                    "target_week_start": row.get("target_week_start"),
                    "horizon_days": int(row["horizon_days"]),
                    "event_label": int(row["event_label"]),
                    "event_probability": float(row["event_probability_calibrated"]),
                    "y_true": y_true,
                    "q_0.1": lower,
                    "q_0.5": expected_target,
                    "q_0.9": upper,
                    "current_known_incidence": float(row.get("current_known_incidence") or 0.0),
                    "seasonal_baseline": float(row.get("seasonal_baseline") or 0.0),
                    "seasonal_mad": float(row.get("seasonal_mad") or 1.0),
                    "expected_target_incidence": expected_target,
                    "prediction_interval_lower": lower,
                    "prediction_interval_upper": upper,
                    "residual": y_true - expected_target,
                    "absolute_error": abs(y_true - expected_target),
                    "season_regime": target_regime,
                    "reconciliation_method": reconciled_meta.get("reconciliation_method"),
                    "hierarchy_consistency_status": reconciled_meta.get(
                        "hierarchy_consistency_status"
                    ),
                    "cluster_blend_weight": cluster_blend_weight,
                    "national_blend_weight": national_blend_weight,
                    "cluster_blend_scope": cluster_blend_choice.get("scope"),
                    "national_blend_scope": national_blend_choice.get("scope"),
                }
            )
        residual_row: dict[str, float] = {}
        for idx, state in enumerate(available_states):
            y_true = float(date_frame.at[state, "next_week_incidence"])
            pred = float(reconciled_quantiles[0.5][idx])
            residual_row[state] = y_true - pred
        historical_residual_rows.append(residual_row)
        if cluster_order:
            cluster_truth = []
            for cluster_id in cluster_order:
                members = [
                    state
                    for state in available_states
                    if cluster_assignments.get(state) == cluster_id
                ]
                member_weights = np.asarray(
                    [float(state_weights.get(state, 1.0)) for state in members],
                    dtype=float,
                )
                member_truth = np.asarray(
                    [float(date_frame.at[state, "next_week_incidence"]) for state in members],
                    dtype=float,
                )
                cluster_truth.append(
                    float(np.average(member_truth, weights=member_weights))
                    if len(member_truth)
                    else 0.0
                )
            for idx, truth_value in enumerate(cluster_truth):
                historical_cluster_rows.append(
                    {
                        "fold": (
                            date_frame["fold"].dropna().iloc[-1]
                            if "fold" in date_frame.columns and date_frame["fold"].notna().any()
                            else None
                        ),
                        "as_of_date": date_value,
                        "horizon_days": target_horizon_days,
                        "regime": target_regime,
                        "model": (
                            float(model_cluster_quantiles[0.5][idx])
                            if model_cluster_quantiles is not None
                            else np.nan
                        ),
                        "baseline": float(derived_cluster_quantiles[0.5][idx]),
                        "truth": float(truth_value),
                        "model_q_0.1": (
                            float(model_cluster_quantiles[0.1][idx])
                            if model_cluster_quantiles is not None
                            else np.nan
                        ),
                        "model_q_0.5": (
                            float(model_cluster_quantiles[0.5][idx])
                            if model_cluster_quantiles is not None
                            else np.nan
                        ),
                        "model_q_0.9": (
                            float(model_cluster_quantiles[0.9][idx])
                            if model_cluster_quantiles is not None
                            else np.nan
                        ),
                        "baseline_q_0.1": float(derived_cluster_quantiles[0.1][idx]),
                        "baseline_q_0.5": float(derived_cluster_quantiles[0.5][idx]),
                        "baseline_q_0.9": float(derived_cluster_quantiles[0.9][idx]),
                    }
                )
        historical_national_rows.append(
            {
                "fold": (
                    date_frame["fold"].dropna().iloc[-1]
                    if "fold" in date_frame.columns and date_frame["fold"].notna().any()
                    else None
                ),
                "as_of_date": date_value,
                "horizon_days": target_horizon_days,
                "regime": target_regime,
                "model": (
                    float(model_national_quantiles[0.5][0])
                    if model_national_quantiles is not None
                    else np.nan
                ),
                "baseline": float(derived_national_quantiles[0.5][0]),
                "truth": float(
                    np.average(
                        np.asarray(
                            [
                                float(date_frame.at[state, "next_week_incidence"])
                                for state in available_states
                            ],
                            dtype=float,
                        ),
                        weights=np.asarray(
                            [float(state_weights.get(state, 1.0)) for state in available_states],
                            dtype=float,
                        ),
                    )
                ),
                "model_q_0.1": (
                    float(model_national_quantiles[0.1][0])
                    if model_national_quantiles is not None
                    else np.nan
                ),
                "model_q_0.5": (
                    float(model_national_quantiles[0.5][0])
                    if model_national_quantiles is not None
                    else np.nan
                ),
                "model_q_0.9": (
                    float(model_national_quantiles[0.9][0])
                    if model_national_quantiles is not None
                    else np.nan
                ),
                "baseline_q_0.1": float(derived_national_quantiles[0.1][0]),
                "baseline_q_0.5": float(derived_national_quantiles[0.5][0]),
                "baseline_q_0.9": float(derived_national_quantiles[0.9][0]),
            }
        )

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def prepare_hierarchy_history_frame(
    history_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not history_rows:
        return pd.DataFrame()
    history = pd.DataFrame(history_rows).replace([np.inf, -np.inf], np.nan).copy()
    required_baseline = {"baseline_q_0.1", "baseline_q_0.5", "baseline_q_0.9", "truth"}
    if history.empty or not required_baseline.issubset(history.columns):
        return pd.DataFrame()
    if "as_of_date" in history.columns:
        history["as_of_date"] = pd.to_datetime(history["as_of_date"], errors="coerce").dt.normalize()
    if "regime" not in history.columns and "as_of_date" in history.columns:
        history["regime"] = history["as_of_date"].apply(GeoHierarchyHelper.season_regime)
    history["horizon_days"] = pd.to_numeric(
        history.get("horizon_days"),
        errors="coerce",
    )
    return history.dropna(
        subset=["truth", "baseline_q_0.1", "baseline_q_0.5", "baseline_q_0.9"]
    ).copy()


def quantile_blend_metrics(
    history: pd.DataFrame,
    *,
    blend_weight: float,
) -> dict[str, float]:
    if history.empty:
        return {"wis": float("inf"), "crps": float("inf")}
    baseline_quantiles = {
        0.1: history["baseline_q_0.1"].to_numpy(dtype=float),
        0.5: history["baseline_q_0.5"].to_numpy(dtype=float),
        0.9: history["baseline_q_0.9"].to_numpy(dtype=float),
    }
    if blend_weight <= 0.0:
        blended_quantiles = baseline_quantiles
    else:
        blended_quantiles = {}
        for quantile in (0.1, 0.5, 0.9):
            baseline = history[f"baseline_q_{quantile}"].to_numpy(dtype=float)
            model_series = history.get(f"model_q_{quantile}")
            if model_series is None:
                model = baseline
            else:
                model = (
                    pd.to_numeric(model_series, errors="coerce")
                    .fillna(pd.Series(baseline, index=history.index))
                    .to_numpy(dtype=float)
                )
            blended_quantiles[quantile] = (blend_weight * model) + (
                (1.0 - blend_weight) * baseline
            )
    metrics = summarize_probabilistic_metrics(
        y_true=history["truth"].to_numpy(dtype=float),
        quantile_predictions=blended_quantiles,
    )
    return {
        "wis": float(metrics.get("wis") or float("inf")),
        "crps": float(metrics.get("crps") or float("inf")),
        "coverage_80": float(metrics.get("coverage_80") or 0.0),
    }


def blend_weight_improves(
    *,
    baseline_metrics: dict[str, float],
    candidate_metrics: dict[str, float],
    epsilon: float,
) -> bool:
    baseline_wis = float(baseline_metrics.get("wis") or float("inf"))
    baseline_crps = float(baseline_metrics.get("crps") or float("inf"))
    candidate_wis = float(candidate_metrics.get("wis") or float("inf"))
    candidate_crps = float(candidate_metrics.get("crps") or float("inf"))
    if candidate_wis < baseline_wis - epsilon and candidate_crps <= baseline_crps + epsilon:
        return True
    if abs(candidate_wis - baseline_wis) <= epsilon and candidate_crps < baseline_crps - epsilon:
        return True
    return False


def estimate_hierarchy_blend_choice(
    trainer,
    history_rows: list[dict[str, Any]],
    *,
    target_as_of_date: pd.Timestamp | None = None,
    target_regime: str | None = None,
    target_horizon_days: int | None = None,
    min_total_samples: int,
    min_regime_samples: int,
    weight_grid: tuple[float, ...],
    blend_epsilon: float,
) -> dict[str, Any]:
    history = trainer._prepare_hierarchy_history_frame(history_rows)
    if history.empty:
        return {
            "weight": 0.0,
            "scope": "insufficient_history",
            "samples": 0,
            "regime": target_regime,
            "horizon_days": target_horizon_days,
        }

    if target_as_of_date is not None and "as_of_date" in history.columns:
        history = history.loc[
            history["as_of_date"] < pd.Timestamp(target_as_of_date).normalize()
        ].copy()
    if history.empty:
        return {
            "weight": 0.0,
            "scope": "insufficient_history",
            "samples": 0,
            "regime": target_regime,
            "horizon_days": target_horizon_days,
        }

    if (
        target_horizon_days is not None
        and "horizon_days" in history.columns
        and history["horizon_days"].notna().any()
    ):
        horizon_history = history.loc[
            history["horizon_days"] == float(target_horizon_days)
        ].copy()
        if not horizon_history.empty:
            history = horizon_history

    selected = history
    scope = "all_history"
    minimum_required = int(min_total_samples)
    if target_regime:
        regime_history = history.loc[history.get("regime") == str(target_regime)].copy()
        if len(regime_history) >= int(min_regime_samples):
            selected = regime_history
            scope = "same_regime"
            minimum_required = int(min_regime_samples)
        else:
            scope = "horizon_fallback"

    if len(selected) < minimum_required:
        return {
            "weight": 0.0,
            "scope": "insufficient_history",
            "samples": int(len(selected)),
            "regime": target_regime,
            "horizon_days": target_horizon_days,
        }

    baseline_metrics = trainer._quantile_blend_metrics(selected, blend_weight=0.0)
    candidate_rows: list[dict[str, Any]] = []
    for weight in weight_grid:
        metrics = trainer._quantile_blend_metrics(selected, blend_weight=float(weight))
        candidate_rows.append(
            {
                "weight": round(float(weight), 6),
                "wis": round(float(metrics["wis"]), 6),
                "crps": round(float(metrics["crps"]), 6),
                "coverage_80": round(float(metrics.get("coverage_80") or 0.0), 6),
            }
        )
    candidate_rows.sort(
        key=lambda item: (
            float(item.get("wis") or float("inf")),
            float(item.get("crps") or float("inf")),
            abs(float(item.get("weight") or 0.0)),
        )
    )
    best = candidate_rows[0] if candidate_rows else {
        "weight": 0.0,
        "wis": baseline_metrics["wis"],
        "crps": baseline_metrics["crps"],
        "coverage_80": baseline_metrics.get("coverage_80", 0.0),
    }
    selected_row = (
        best
        if trainer._blend_weight_improves(
            baseline_metrics=baseline_metrics,
            candidate_metrics=best,
        )
        else {
            "weight": 0.0,
            "wis": round(float(baseline_metrics["wis"]), 6),
            "crps": round(float(baseline_metrics["crps"]), 6),
            "coverage_80": round(float(baseline_metrics.get("coverage_80") or 0.0), 6),
        }
    )
    return {
        "weight": round(float(selected_row["weight"]), 6),
        "scope": scope if float(selected_row["weight"]) > 0.0 else f"{scope}_baseline_only",
        "samples": int(len(selected)),
        "regime": target_regime,
        "horizon_days": target_horizon_days,
        "wis": round(float(selected_row["wis"]), 6),
        "crps": round(float(selected_row["crps"]), 6),
        "baseline_wis": round(float(baseline_metrics["wis"]), 6),
        "baseline_crps": round(float(baseline_metrics["crps"]), 6),
        "top_candidates": candidate_rows[:3],
    }


def build_hierarchy_blend_policy(
    trainer,
    history_rows: list[dict[str, Any]],
    *,
    horizon_days: int | None,
    min_total_samples: int,
    min_regime_samples: int,
    weight_grid: tuple[float, ...],
    blend_epsilon: float,
) -> dict[str, Any]:
    history = trainer._prepare_hierarchy_history_frame(history_rows)
    if history.empty:
        return {
            "version": "fold_probabilistic_wis_crps_v1",
            "horizon_days": horizon_days,
            "fallback": {
                "weight": 0.0,
                "scope": "insufficient_history",
                "samples": 0,
            },
            "by_regime": {},
        }

    history_rows = history.to_dict("records")
    fallback = trainer._estimate_hierarchy_blend_choice(
        history_rows,
        target_horizon_days=horizon_days,
        target_regime=None,
        min_total_samples=min_total_samples,
        min_regime_samples=min_regime_samples,
    )
    regimes = sorted(
        {
            str(value)
            for value in history.get("regime", pd.Series(dtype=str)).dropna().astype(str).tolist()
        }
    )
    by_regime = {
        regime: trainer._estimate_hierarchy_blend_choice(
            history_rows,
            target_horizon_days=horizon_days,
            target_regime=regime,
            min_total_samples=min_total_samples,
            min_regime_samples=min_regime_samples,
        )
        for regime in regimes
    }
    return {
        "version": "fold_probabilistic_wis_crps_v1",
        "horizon_days": horizon_days,
        "fallback": fallback,
        "by_regime": by_regime,
    }


def estimate_hierarchy_blend_weight(
    trainer,
    history_rows: list[dict[str, Any]],
    *,
    min_samples: int,
    min_regime_samples: int,
    weight_grid: tuple[float, ...],
    blend_epsilon: float,
) -> float:
    choice = trainer._estimate_hierarchy_blend_choice(
        history_rows,
        min_total_samples=min_samples,
        min_regime_samples=min_regime_samples,
    )
    return float(choice.get("weight") or 0.0)


def blend_hierarchy_quantiles(
    *,
    model_quantiles: dict[float, np.ndarray] | None,
    baseline_quantiles: dict[float, np.ndarray],
    blend_weight: float,
) -> dict[float, np.ndarray]:
    return GeoHierarchyHelper.blend_quantiles(
        model_quantiles=model_quantiles,
        baseline_quantiles=baseline_quantiles,
        blend_weight=blend_weight,
    )


def hierarchy_component_diagnostics(
    trainer,
    *,
    oof_frame: pd.DataFrame,
    min_total_samples: int,
    min_regime_samples: int,
    weight_grid: tuple[float, ...],
    blend_epsilon: float,
) -> dict[str, Any]:
    if oof_frame.empty:
        return {}

    cluster_rows: list[dict[str, float]] = []
    national_rows: list[dict[str, float]] = []
    working = oof_frame.copy()
    working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
    for as_of_date, date_frame in working.groupby("as_of_date", dropna=False):
        date_frame = date_frame.copy().drop_duplicates(subset=["bundesland"], keep="last")
        if date_frame.empty:
            continue
        if "state_population_millions" in date_frame.columns:
            weights = (
                pd.to_numeric(date_frame["state_population_millions"], errors="coerce")
                .fillna(1.0)
                .clip(lower=1e-6)
            )
        else:
            weights = pd.Series(1.0, index=date_frame.index, dtype=float)
        baseline_lower_series = (
            pd.to_numeric(date_frame["prediction_interval_lower"], errors="coerce")
            if "prediction_interval_lower" in date_frame.columns
            else pd.to_numeric(date_frame["expected_target_incidence"], errors="coerce")
        )
        baseline_upper_series = (
            pd.to_numeric(date_frame["prediction_interval_upper"], errors="coerce")
            if "prediction_interval_upper" in date_frame.columns
            else pd.to_numeric(date_frame["expected_target_incidence"], errors="coerce")
        )
        if "cluster_id" in date_frame.columns and date_frame["cluster_id"].notna().any():
            for _cluster_id, cluster_frame in date_frame.dropna(subset=["cluster_id"]).groupby(
                "cluster_id",
                dropna=False,
            ):
                cluster_weights = weights.loc[cluster_frame.index]
                cluster_baseline_lower = baseline_lower_series.loc[cluster_frame.index]
                cluster_baseline_upper = baseline_upper_series.loc[cluster_frame.index]
                cluster_rows.append(
                    {
                        "as_of_date": pd.Timestamp(as_of_date).normalize(),
                        "regime": GeoHierarchyHelper.season_regime(as_of_date),
                        "horizon_days": (
                            int(cluster_frame["horizon_days"].iloc[-1])
                            if "horizon_days" in cluster_frame.columns
                            else None
                        ),
                        "truth": float(
                            np.average(
                                cluster_frame["next_week_incidence"].astype(float),
                                weights=cluster_weights,
                            )
                        ),
                        "baseline": float(
                            np.average(
                                cluster_frame["expected_target_incidence"].astype(float),
                                weights=cluster_weights,
                            )
                        ),
                        "model": float(cluster_frame["cluster_expected_target_incidence"].iloc[-1]),
                        "baseline_q_0.1": float(
                            np.average(cluster_baseline_lower.astype(float), weights=cluster_weights)
                        ),
                        "baseline_q_0.5": float(
                            np.average(
                                cluster_frame["expected_target_incidence"].astype(float),
                                weights=cluster_weights,
                            )
                        ),
                        "baseline_q_0.9": float(
                            np.average(cluster_baseline_upper.astype(float), weights=cluster_weights)
                        ),
                        "model_q_0.1": float(
                            cluster_frame["cluster_prediction_interval_lower"].iloc[-1]
                            if "cluster_prediction_interval_lower" in cluster_frame.columns
                            else cluster_frame["cluster_expected_target_incidence"].iloc[-1]
                        ),
                        "model_q_0.5": float(cluster_frame["cluster_expected_target_incidence"].iloc[-1]),
                        "model_q_0.9": float(
                            cluster_frame["cluster_prediction_interval_upper"].iloc[-1]
                            if "cluster_prediction_interval_upper" in cluster_frame.columns
                            else cluster_frame["cluster_expected_target_incidence"].iloc[-1]
                        ),
                    }
                )
        if (
            "national_expected_target_incidence" in date_frame.columns
            and date_frame["national_expected_target_incidence"].notna().any()
        ):
            national_rows.append(
                {
                    "as_of_date": pd.Timestamp(as_of_date).normalize(),
                    "regime": GeoHierarchyHelper.season_regime(as_of_date),
                    "horizon_days": (
                        int(date_frame["horizon_days"].iloc[-1])
                        if "horizon_days" in date_frame.columns
                        else None
                    ),
                    "truth": float(
                        np.average(date_frame["next_week_incidence"].astype(float), weights=weights)
                    ),
                    "baseline": float(
                        np.average(
                            date_frame["expected_target_incidence"].astype(float),
                            weights=weights,
                        )
                    ),
                    "model": float(date_frame["national_expected_target_incidence"].iloc[-1]),
                    "baseline_q_0.1": float(
                        np.average(baseline_lower_series.astype(float), weights=weights)
                    ),
                    "baseline_q_0.5": float(
                        np.average(
                            date_frame["expected_target_incidence"].astype(float),
                            weights=weights,
                        )
                    ),
                    "baseline_q_0.9": float(
                        np.average(baseline_upper_series.astype(float), weights=weights)
                    ),
                    "model_q_0.1": float(
                        date_frame["national_prediction_interval_lower"].iloc[-1]
                        if "national_prediction_interval_lower" in date_frame.columns
                        else date_frame["national_expected_target_incidence"].iloc[-1]
                    ),
                    "model_q_0.5": float(date_frame["national_expected_target_incidence"].iloc[-1]),
                    "model_q_0.9": float(
                        date_frame["national_prediction_interval_upper"].iloc[-1]
                        if "national_prediction_interval_upper" in date_frame.columns
                        else date_frame["national_expected_target_incidence"].iloc[-1]
                    ),
                }
            )

    def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"samples": 0}
        frame = pd.DataFrame(rows).dropna(subset=["truth", "baseline"])
        if frame.empty:
            return {"samples": 0}
        frame["baseline_abs_error"] = (frame["baseline"] - frame["truth"]).abs()
        model_frame = frame.dropna(subset=["model"]).copy()
        model_mae = (
            float(model_frame["model"].sub(model_frame["truth"]).abs().mean())
            if not model_frame.empty
            else None
        )
        baseline_mae = float(frame["baseline_abs_error"].mean())
        baseline_metrics = trainer._quantile_blend_metrics(frame, blend_weight=0.0)
        model_metrics = trainer._quantile_blend_metrics(frame, blend_weight=1.0)
        horizon_values = pd.to_numeric(frame.get("horizon_days"), errors="coerce").dropna().astype(int)
        horizon_days = int(horizon_values.mode().iloc[0]) if not horizon_values.empty else None
        blend_policy = trainer._build_hierarchy_blend_policy(rows, horizon_days=horizon_days)
        recommended_weight = float(((blend_policy.get("fallback") or {}).get("weight")) or 0.0)
        return {
            "samples": int(len(frame)),
            "baseline_mae": round(float(baseline_mae), 6),
            "model_mae": round(float(model_mae), 6) if model_mae is not None else None,
            "baseline_wis": round(float(baseline_metrics.get("wis") or 0.0), 6),
            "model_wis": round(float(model_metrics.get("wis") or 0.0), 6),
            "baseline_crps": round(float(baseline_metrics.get("crps") or 0.0), 6),
            "model_crps": round(float(model_metrics.get("crps") or 0.0), 6),
            "mae_delta_model_minus_baseline": (
                round(float(model_mae - baseline_mae), 6)
                if model_mae is not None
                else None
            ),
            "recommended_blend_weight": recommended_weight,
            "blend_policy": blend_policy,
        }

    return {
        "cluster": _summarize(cluster_rows),
        "national": _summarize(national_rows),
    }


def predict_hierarchy_aggregate_quantiles(
    trainer,
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
    cluster_ids = pd.Series(index=frame.index, dtype=object)
    cluster_lower = pd.Series(np.nan, index=frame.index, dtype=float)
    cluster_median = pd.Series(np.nan, index=frame.index, dtype=float)
    cluster_upper = pd.Series(np.nan, index=frame.index, dtype=float)
    national_lower = pd.Series(np.nan, index=frame.index, dtype=float)
    national_median = pd.Series(np.nan, index=frame.index, dtype=float)
    national_upper = pd.Series(np.nan, index=frame.index, dtype=float)

    working_panel = source_panel.copy()
    working_panel["as_of_date"] = pd.to_datetime(working_panel["as_of_date"]).dt.normalize()
    frame_dates = frame.assign(as_of_date=pd.to_datetime(frame["as_of_date"]).dt.normalize())
    for as_of_date, idx in frame_dates.groupby("as_of_date").groups.items():
        date_slice = frame_dates.loc[idx].copy()
        panel_until_date = working_panel.loc[
            working_panel["as_of_date"] <= pd.Timestamp(as_of_date)
        ].copy()
        cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
            panel_until_date,
            state_col="bundesland",
            value_col="current_known_incidence",
            date_col="as_of_date",
        )
        cluster_frame = GeoHierarchyHelper.aggregate_feature_frame(
            date_slice,
            feature_columns=feature_columns,
            cluster_assignments=cluster_assignments,
            level="cluster",
        )
        national_frame = GeoHierarchyHelper.aggregate_feature_frame(
            date_slice,
            feature_columns=feature_columns,
            level="national",
        )
        cluster_baseline_map, national_baseline_values = trainer._hierarchy_state_baseline_features(
            date_slice=date_slice,
            cluster_assignments=cluster_assignments,
            state_feature_columns=state_feature_columns or feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
        )
        if not cluster_frame.empty:
            cluster_frame = trainer._apply_hierarchy_baseline_map(
                cluster_frame,
                baseline_map=cluster_baseline_map,
            )
        if not national_frame.empty and national_baseline_values:
            national_frame = national_frame.copy()
            for column, value in national_baseline_values.items():
                national_frame[column] = float(value)

        cluster_maps: dict[str, dict[str, float]] = {}
        cluster_model_bundle = (hierarchy_models or {}).get("cluster") or {}
        national_model_bundle = (hierarchy_models or {}).get("national") or {}
        if not cluster_frame.empty and cluster_model_bundle:
            cluster_X = cluster_frame[feature_columns].to_numpy(dtype=float)
            cluster_frame = cluster_frame.copy()
            cluster_target_mode = str((hierarchy_model_modes or {}).get("cluster") or "direct_log")
            if cluster_target_mode == "residual_log":
                cluster_frame["q_0.1"] = trainer._hierarchy_apply_residual_prediction(
                    baseline=cluster_frame["hierarchy_state_baseline_q10"].to_numpy(dtype=float),
                    residual_log=cluster_model_bundle["lower"].predict(cluster_X),
                )
                cluster_frame["q_0.5"] = trainer._hierarchy_apply_residual_prediction(
                    baseline=cluster_frame["hierarchy_state_baseline_q50"].to_numpy(dtype=float),
                    residual_log=cluster_model_bundle["median"].predict(cluster_X),
                )
                cluster_frame["q_0.9"] = trainer._hierarchy_apply_residual_prediction(
                    baseline=cluster_frame["hierarchy_state_baseline_q90"].to_numpy(dtype=float),
                    residual_log=cluster_model_bundle["upper"].predict(cluster_X),
                )
            else:
                cluster_frame["q_0.1"] = np.expm1(cluster_model_bundle["lower"].predict(cluster_X))
                cluster_frame["q_0.5"] = np.expm1(cluster_model_bundle["median"].predict(cluster_X))
                cluster_frame["q_0.9"] = np.expm1(cluster_model_bundle["upper"].predict(cluster_X))
            cluster_maps = {
                str(row["hierarchy_group"]): {
                    "q_0.1": float(row["q_0.1"]),
                    "q_0.5": float(row["q_0.5"]),
                    "q_0.9": float(row["q_0.9"]),
                }
                for _, row in cluster_frame.iterrows()
            }

        national_values = {"q_0.1": np.nan, "q_0.5": np.nan, "q_0.9": np.nan}
        if not national_frame.empty and national_model_bundle:
            national_X = national_frame[feature_columns].to_numpy(dtype=float)
            national_values = {
                "q_0.1": float(np.expm1(national_model_bundle["lower"].predict(national_X))[0]),
                "q_0.5": float(np.expm1(national_model_bundle["median"].predict(national_X))[0]),
                "q_0.9": float(np.expm1(national_model_bundle["upper"].predict(national_X))[0]),
            }

        for row_idx, row in date_slice.iterrows():
            state = str(row["bundesland"])
            cluster_id = cluster_assignments.get(state)
            cluster_ids.at[row_idx] = cluster_id
            cluster_values = cluster_maps.get(str(cluster_id), {})
            cluster_lower.at[row_idx] = float(cluster_values.get("q_0.1", np.nan))
            cluster_median.at[row_idx] = float(cluster_values.get("q_0.5", np.nan))
            cluster_upper.at[row_idx] = float(cluster_values.get("q_0.9", np.nan))
            national_lower.at[row_idx] = float(national_values["q_0.1"])
            national_median.at[row_idx] = float(national_values["q_0.5"])
            national_upper.at[row_idx] = float(national_values["q_0.9"])

    return {
        "cluster_ids": cluster_ids.tolist(),
        "cluster_lower": cluster_lower.tolist(),
        "cluster_median": cluster_median.tolist(),
        "cluster_upper": cluster_upper.tolist(),
        "national_lower": national_lower.tolist(),
        "national_median": national_median.tolist(),
        "national_upper": national_upper.tolist(),
    }


def hierarchy_apply_residual_prediction(
    *,
    baseline: np.ndarray,
    residual_log: np.ndarray,
) -> np.ndarray:
    baseline_arr = np.asarray(baseline, dtype=float)
    residual_arr = np.asarray(residual_log, dtype=float)
    return np.expm1(np.log1p(np.clip(baseline_arr, 0.0, None)) + residual_arr)


def hierarchy_state_baseline_features(
    *,
    date_slice: pd.DataFrame,
    cluster_assignments: dict[str, str],
    state_feature_columns: list[str],
    reg_lower: XGBRegressor,
    reg_median: XGBRegressor,
    reg_upper: XGBRegressor,
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    if date_slice.empty:
        return {}, {}
    state_order = [str(value) for value in date_slice["bundesland"].tolist()]
    state_weights = (
        {
            str(row["bundesland"]): float(row.get("state_population_millions") or 1.0)
            for _, row in date_slice.iterrows()
        }
        if "state_population_millions" in date_slice.columns
        else {}
    )
    X = date_slice[state_feature_columns].to_numpy(dtype=float)
    state_quantiles = {
        0.1: np.expm1(reg_lower.predict(X)),
        0.5: np.expm1(reg_median.predict(X)),
        0.9: np.expm1(reg_upper.predict(X)),
    }
    cluster_quantiles, national_quantiles, cluster_order = GeoHierarchyHelper.derived_aggregate_quantiles(
        state_quantiles,
        state_order=state_order,
        cluster_assignments=cluster_assignments,
        state_weights=state_weights,
    )
    cluster_map: dict[str, dict[str, float]] = {}
    for idx, cluster_id in enumerate(cluster_order):
        lower = float(cluster_quantiles.get(0.1, np.asarray([], dtype=float))[idx])
        median = float(cluster_quantiles.get(0.5, np.asarray([], dtype=float))[idx])
        upper = float(cluster_quantiles.get(0.9, np.asarray([], dtype=float))[idx])
        cluster_map[str(cluster_id)] = {
            "hierarchy_state_baseline_q10": lower,
            "hierarchy_state_baseline_q50": median,
            "hierarchy_state_baseline_q90": upper,
            "hierarchy_state_baseline_width_80": float(max(upper - lower, 0.0)),
        }
    national_values = (
        {
            "hierarchy_state_baseline_q10": float(np.asarray(national_quantiles.get(0.1), dtype=float)[0]),
            "hierarchy_state_baseline_q50": float(np.asarray(national_quantiles.get(0.5), dtype=float)[0]),
            "hierarchy_state_baseline_q90": float(np.asarray(national_quantiles.get(0.9), dtype=float)[0]),
        }
        if national_quantiles
        else {}
    )
    if national_values:
        national_values["hierarchy_state_baseline_width_80"] = float(
            max(
                float(national_values["hierarchy_state_baseline_q90"])
                - float(national_values["hierarchy_state_baseline_q10"]),
                0.0,
            )
        )
    return cluster_map, national_values


def apply_hierarchy_baseline_map(
    frame: pd.DataFrame,
    *,
    baseline_map: dict[str, dict[str, float]],
) -> pd.DataFrame:
    if frame.empty:
        return frame
    working = frame.copy()
    for column in GeoHierarchyHelper.HIERARCHY_STATE_BASELINE_FEATURE_COLUMNS:
        working[column] = [
            float((baseline_map.get(str(group)) or {}).get(column, 0.0))
            for group in working["hierarchy_group"].astype(str)
        ]
    return working


def build_hierarchy_training_frame(
    trainer,
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
    if panel.empty:
        return pd.DataFrame()

    working = panel.copy()
    working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
    aggregate_frames: list[pd.DataFrame] = []
    for as_of_date in sorted(working["as_of_date"].dropna().unique()):
        date_value = pd.Timestamp(as_of_date).normalize()
        date_slice = working.loc[working["as_of_date"] == date_value].copy()
        if date_slice.empty:
            continue
        panel_until_date = working.loc[working["as_of_date"] <= date_value].copy()
        cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
            panel_until_date,
            state_col="bundesland",
            value_col="current_known_incidence",
            date_col="as_of_date",
        )
        aggregate_frame = GeoHierarchyHelper.aggregate_feature_frame(
            date_slice,
            feature_columns=feature_columns,
            cluster_assignments=cluster_assignments,
            level=level,
        )
        if aggregate_frame.empty or "next_week_incidence" not in aggregate_frame.columns:
            continue
        cluster_baseline_map, national_baseline_values = trainer._hierarchy_state_baseline_features(
            date_slice=date_slice,
            cluster_assignments=cluster_assignments,
            state_feature_columns=state_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
        )
        if level == "cluster":
            aggregate_frame = trainer._apply_hierarchy_baseline_map(
                aggregate_frame,
                baseline_map=cluster_baseline_map,
            )
        elif level == "national" and national_baseline_values:
            aggregate_frame = aggregate_frame.copy()
            for column, value in national_baseline_values.items():
                aggregate_frame[column] = float(value)
        aggregate_frames.append(aggregate_frame)

    if not aggregate_frames:
        return pd.DataFrame()
    combined = pd.concat(aggregate_frames, ignore_index=True)
    combined["y_next_log"] = np.log1p(combined["next_week_incidence"].astype(float).clip(lower=0.0))
    if target_mode == "residual_log":
        combined["y_residual_log_lower"] = combined["y_next_log"] - np.log1p(
            combined["hierarchy_state_baseline_q10"].astype(float).clip(lower=0.0)
        )
        combined["y_residual_log_median"] = combined["y_next_log"] - np.log1p(
            combined["hierarchy_state_baseline_q50"].astype(float).clip(lower=0.0)
        )
        combined["y_residual_log_upper"] = combined["y_next_log"] - np.log1p(
            combined["hierarchy_state_baseline_q90"].astype(float).clip(lower=0.0)
        )
    return combined


def fit_hierarchy_models(
    trainer,
    *,
    panel: pd.DataFrame,
    feature_columns: list[str],
    state_feature_columns: list[str],
    reg_lower: XGBRegressor,
    reg_median: XGBRegressor,
    reg_upper: XGBRegressor,
    regressor_config: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, XGBRegressor] | None], dict[str, str]]:
    cluster_training = trainer._build_hierarchy_training_frame(
        panel=panel,
        feature_columns=feature_columns,
        state_feature_columns=state_feature_columns,
        reg_lower=reg_lower,
        reg_median=reg_median,
        reg_upper=reg_upper,
        level="cluster",
        target_mode="residual_log",
    )
    national_training = trainer._build_hierarchy_training_frame(
        panel=panel,
        feature_columns=feature_columns,
        state_feature_columns=state_feature_columns,
        reg_lower=reg_lower,
        reg_median=reg_median,
        reg_upper=reg_upper,
        level="national",
    )

    def _fit_bundle(frame: pd.DataFrame, *, target_mode: str) -> dict[str, XGBRegressor] | None:
        if frame.empty or len(frame) < 40:
            return None
        target_columns = {
            "lower": "y_next_log",
            "median": "y_next_log",
            "upper": "y_next_log",
        }
        if target_mode == "residual_log":
            target_columns = {
                "lower": "y_residual_log_lower",
                "median": "y_residual_log_median",
                "upper": "y_residual_log_upper",
            }
        return {
            "lower": trainer._fit_regressor_from_frame(
                frame,
                feature_columns,
                regressor_config["lower"],
                target_col=target_columns["lower"],
            ),
            "median": trainer._fit_regressor_from_frame(
                frame,
                feature_columns,
                regressor_config["median"],
                target_col=target_columns["median"],
            ),
            "upper": trainer._fit_regressor_from_frame(
                frame,
                feature_columns,
                regressor_config["upper"],
                target_col=target_columns["upper"],
            ),
        }

    return (
        {
            "cluster": _fit_bundle(cluster_training, target_mode="residual_log"),
            "national": _fit_bundle(national_training, target_mode="direct_log"),
        },
        {
            "cluster": "residual_log",
            "national": "direct_log",
        },
    )
