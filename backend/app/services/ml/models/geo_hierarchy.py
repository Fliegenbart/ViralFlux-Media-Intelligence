from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

from app.services.ml.benchmarking.metrics import monotone_quantiles
from app.services.ml.regional_panel_utils import REGIONAL_NEIGHBORS


class GeoHierarchyHelper:
    """Dynamic clustering and MinT-like coherent reconciliation helpers."""

    HIERARCHY_DERIVED_FEATURE_COLUMNS = [
        "hierarchy_member_count",
        "hierarchy_total_weight",
        "hierarchy_incidence_std",
        "hierarchy_incidence_mad",
        "hierarchy_incidence_range",
        "hierarchy_incidence_max",
        "hierarchy_incidence_min",
        "hierarchy_hot_state_population_share",
        "hierarchy_hot_state_excess",
        "hierarchy_vs_national_current_gap",
        "hierarchy_vs_national_current_ratio",
        "hierarchy_vs_national_baseline_gap",
        "hierarchy_vs_national_baseline_ratio",
        "hierarchy_vs_rest_current_gap",
        "hierarchy_vs_rest_current_ratio",
        "hierarchy_vs_rest_baseline_gap",
        "hierarchy_vs_rest_baseline_ratio",
        "hierarchy_current_rank_pct",
        "hierarchy_gap_to_hottest_cluster",
        "hierarchy_gap_to_coolest_cluster",
        "hierarchy_neighbor_cluster_count",
        "hierarchy_neighbor_current_gap",
        "hierarchy_neighbor_current_ratio",
        "hierarchy_neighbor_baseline_gap",
        "hierarchy_neighbor_baseline_ratio",
    ]
    HIERARCHY_STATE_BASELINE_FEATURE_COLUMNS = [
        "hierarchy_state_baseline_q10",
        "hierarchy_state_baseline_q50",
        "hierarchy_state_baseline_q90",
        "hierarchy_state_baseline_width_80",
    ]

    @staticmethod
    def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
        numeric = pd.to_numeric(values, errors="coerce")
        valid = numeric.notna() & weights.notna()
        if not valid.any():
            return 0.0
        return float(np.average(numeric.loc[valid], weights=weights.loc[valid]))

    @staticmethod
    def _weighted_std(values: pd.Series, weights: pd.Series) -> float:
        numeric = pd.to_numeric(values, errors="coerce")
        valid = numeric.notna() & weights.notna()
        if not valid.any():
            return 0.0
        numeric_values = numeric.loc[valid].astype(float)
        weight_values = weights.loc[valid].astype(float)
        mean_value = float(np.average(numeric_values, weights=weight_values))
        variance = float(np.average((numeric_values - mean_value) ** 2, weights=weight_values))
        return float(np.sqrt(max(variance, 0.0)))

    @classmethod
    def hierarchy_feature_columns(cls, feature_columns: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                [str(column) for column in feature_columns]
                + list(cls.HIERARCHY_DERIVED_FEATURE_COLUMNS)
                + list(cls.HIERARCHY_STATE_BASELINE_FEATURE_COLUMNS)
            )
        )

    @staticmethod
    def _safe_ratio(numerator: float | None, denominator: float | None, default: float = 1.0) -> float:
        if numerator is None or denominator is None:
            return float(default)
        denominator_value = float(denominator)
        if not np.isfinite(denominator_value) or abs(denominator_value) < 1e-6:
            return float(default)
        return float(float(numerator) / denominator_value)

    @classmethod
    def _attach_context_features(
        cls,
        aggregated: pd.DataFrame,
        *,
        level: str,
        group_cols: list[str],
    ) -> pd.DataFrame:
        if aggregated.empty:
            return aggregated

        working = aggregated.copy()
        ratio_columns = {
            "hierarchy_vs_national_current_ratio",
            "hierarchy_vs_national_baseline_ratio",
            "hierarchy_vs_rest_current_ratio",
            "hierarchy_vs_rest_baseline_ratio",
        }
        for column in cls.HIERARCHY_DERIVED_FEATURE_COLUMNS:
            if column not in working.columns:
                working[column] = 1.0 if column in ratio_columns else 0.0

        if level != "cluster":
            return working

        context_cols = [column for column in group_cols if column != "hierarchy_group"]
        if not context_cols:
            grouped_iterable = [(None, working.index)]
        else:
            grouped_iterable = working.groupby(context_cols, dropna=False).groups.items()

        for _context_key, indices in grouped_iterable:
            context_frame = working.loc[indices].copy()
            if context_frame.empty:
                continue

            current_series = (
                context_frame["current_known_incidence"]
                if "current_known_incidence" in context_frame.columns
                else pd.Series(np.nan, index=context_frame.index, dtype=float)
            )
            baseline_series = (
                context_frame["seasonal_baseline"]
                if "seasonal_baseline" in context_frame.columns
                else pd.Series(np.nan, index=context_frame.index, dtype=float)
            )
            current_values = pd.to_numeric(current_series, errors="coerce")
            baseline_values = pd.to_numeric(baseline_series, errors="coerce")
            weights = pd.to_numeric(context_frame.get("hierarchy_total_weight"), errors="coerce").fillna(0.0)

            national_current = (
                float(np.average(current_values, weights=weights))
                if current_values.notna().any() and float(weights.sum()) > 0
                else None
            )
            national_baseline = (
                float(np.average(baseline_values, weights=weights))
                if baseline_values.notna().any() and float(weights.sum()) > 0
                else None
            )
            hottest_cluster = float(current_values.max()) if current_values.notna().any() else None
            coolest_cluster = float(current_values.min()) if current_values.notna().any() else None
            rank_pct = (
                current_values.rank(method="average", pct=True)
                if current_values.notna().any()
                else pd.Series(0.0, index=context_frame.index, dtype=float)
            )

            current_weighted_sum = (current_values.fillna(0.0) * weights).astype(float)
            baseline_weighted_sum = (baseline_values.fillna(0.0) * weights).astype(float)
            total_weight = float(weights.sum())
            total_current_sum = float(current_weighted_sum.sum())
            total_baseline_sum = float(baseline_weighted_sum.sum())
            state_to_cluster: dict[str, str] = {}
            cluster_to_states: dict[str, list[str]] = {}
            for row_idx in context_frame.index:
                cluster_id = str(context_frame.at[row_idx, "hierarchy_group"])
                member_states = [
                    str(value)
                    for value in (context_frame.at[row_idx, "state_members"] or [])
                    if str(value)
                ]
                cluster_to_states[cluster_id] = member_states
                for state in member_states:
                    state_to_cluster[state] = cluster_id

            for row_idx in context_frame.index:
                row_current = float(current_values.loc[row_idx]) if pd.notna(current_values.loc[row_idx]) else None
                row_baseline = float(baseline_values.loc[row_idx]) if pd.notna(baseline_values.loc[row_idx]) else None
                row_weight = float(weights.loc[row_idx])
                rest_weight = total_weight - row_weight
                rest_current = (
                    float((total_current_sum - float(current_weighted_sum.loc[row_idx])) / rest_weight)
                    if rest_weight > 1e-6
                    else national_current
                )
                rest_baseline = (
                    float((total_baseline_sum - float(baseline_weighted_sum.loc[row_idx])) / rest_weight)
                    if rest_weight > 1e-6
                    else national_baseline
                )
                working.at[row_idx, "hierarchy_vs_national_current_gap"] = (
                    float(row_current - national_current)
                    if row_current is not None and national_current is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_vs_national_current_ratio"] = cls._safe_ratio(
                    row_current,
                    national_current,
                )
                working.at[row_idx, "hierarchy_vs_national_baseline_gap"] = (
                    float(row_baseline - national_baseline)
                    if row_baseline is not None and national_baseline is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_vs_national_baseline_ratio"] = cls._safe_ratio(
                    row_baseline,
                    national_baseline,
                )
                working.at[row_idx, "hierarchy_vs_rest_current_gap"] = (
                    float(row_current - rest_current)
                    if row_current is not None and rest_current is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_vs_rest_current_ratio"] = cls._safe_ratio(
                    row_current,
                    rest_current,
                )
                working.at[row_idx, "hierarchy_vs_rest_baseline_gap"] = (
                    float(row_baseline - rest_baseline)
                    if row_baseline is not None and rest_baseline is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_vs_rest_baseline_ratio"] = cls._safe_ratio(
                    row_baseline,
                    rest_baseline,
                )
                working.at[row_idx, "hierarchy_current_rank_pct"] = float(rank_pct.loc[row_idx])
                working.at[row_idx, "hierarchy_gap_to_hottest_cluster"] = (
                    float((row_current or 0.0) - hottest_cluster)
                    if row_current is not None and hottest_cluster is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_gap_to_coolest_cluster"] = (
                    float((row_current or 0.0) - coolest_cluster)
                    if row_current is not None and coolest_cluster is not None
                    else 0.0
                )
                current_cluster_id = str(context_frame.at[row_idx, "hierarchy_group"])
                member_states = cluster_to_states.get(current_cluster_id, [])
                neighbor_cluster_ids: set[str] = set()
                for state in member_states:
                    for neighbor_state in REGIONAL_NEIGHBORS.get(state, []):
                        neighbor_cluster = state_to_cluster.get(str(neighbor_state))
                        if neighbor_cluster and neighbor_cluster != current_cluster_id:
                            neighbor_cluster_ids.add(neighbor_cluster)
                working.at[row_idx, "hierarchy_neighbor_cluster_count"] = float(len(neighbor_cluster_ids))
                if neighbor_cluster_ids:
                    neighbor_frame = context_frame.loc[
                        context_frame["hierarchy_group"].astype(str).isin(sorted(neighbor_cluster_ids))
                    ].copy()
                    neighbor_weights = pd.to_numeric(neighbor_frame["hierarchy_total_weight"], errors="coerce").fillna(0.0)
                    neighbor_current_values = pd.to_numeric(
                        neighbor_frame["current_known_incidence"]
                        if "current_known_incidence" in neighbor_frame.columns
                        else pd.Series(np.nan, index=neighbor_frame.index, dtype=float),
                        errors="coerce",
                    )
                    neighbor_baseline_values = pd.to_numeric(
                        neighbor_frame["seasonal_baseline"]
                        if "seasonal_baseline" in neighbor_frame.columns
                        else pd.Series(np.nan, index=neighbor_frame.index, dtype=float),
                        errors="coerce",
                    )
                    neighbor_current = (
                        float(np.average(neighbor_current_values, weights=neighbor_weights))
                        if neighbor_current_values.notna().any() and float(neighbor_weights.sum()) > 0
                        else None
                    )
                    neighbor_baseline = (
                        float(np.average(neighbor_baseline_values, weights=neighbor_weights))
                        if neighbor_baseline_values.notna().any() and float(neighbor_weights.sum()) > 0
                        else None
                    )
                else:
                    neighbor_current = None
                    neighbor_baseline = None
                working.at[row_idx, "hierarchy_neighbor_current_gap"] = (
                    float(row_current - neighbor_current)
                    if row_current is not None and neighbor_current is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_neighbor_current_ratio"] = cls._safe_ratio(
                    row_current,
                    neighbor_current,
                )
                working.at[row_idx, "hierarchy_neighbor_baseline_gap"] = (
                    float(row_baseline - neighbor_baseline)
                    if row_baseline is not None and neighbor_baseline is not None
                    else 0.0
                )
                working.at[row_idx, "hierarchy_neighbor_baseline_ratio"] = cls._safe_ratio(
                    row_baseline,
                    neighbor_baseline,
                )

        return working

    @staticmethod
    def build_dynamic_clusters(
        panel: pd.DataFrame,
        *,
        state_col: str = "bundesland",
        value_col: str = "current_known_incidence",
        date_col: str = "as_of_date",
        trailing_days: int = 56,
        n_clusters: int = 3,
    ) -> dict[str, str]:
        if panel.empty or state_col not in panel.columns:
            return {}

        working = panel.copy()
        working[date_col] = pd.to_datetime(working[date_col]).dt.normalize()
        cutoff = working[date_col].max() - pd.Timedelta(days=trailing_days)
        recent = working.loc[working[date_col] >= cutoff].copy()
        if recent.empty or recent[state_col].nunique() < max(2, n_clusters):
            return {}

        pivot = recent.pivot_table(
            index=state_col,
            columns=date_col,
            values=value_col,
            aggfunc="mean",
        ).ffill(axis=1).fillna(0.0)
        if len(pivot) < n_clusters:
            return {}

        standardized = pivot.subtract(pivot.mean(axis=1), axis=0)
        std = standardized.std(axis=1).replace(0.0, 1.0)
        standardized = standardized.divide(std, axis=0).fillna(0.0)
        cluster_count = min(n_clusters, len(standardized))
        model = AgglomerativeClustering(n_clusters=cluster_count, linkage="ward")
        labels = model.fit_predict(standardized.to_numpy())
        return {
            str(state): f"cluster_{int(label)}"
            for state, label in zip(standardized.index.tolist(), labels, strict=False)
        }

    @classmethod
    def aggregate_feature_frame(
        cls,
        panel: pd.DataFrame,
        *,
        feature_columns: list[str],
        cluster_assignments: dict[str, str] | None = None,
        level: str = "cluster",
        state_col: str = "bundesland",
        weight_col: str = "state_population_millions",
    ) -> pd.DataFrame:
        if panel.empty:
            return pd.DataFrame()

        working = panel.copy()
        if level == "cluster":
            assignments = {str(key): str(value) for key, value in (cluster_assignments or {}).items()}
            working["hierarchy_group"] = [
                assignments.get(str(value))
                for value in working.get(state_col, pd.Series(dtype=str)).astype(str)
            ]
            working = working.loc[working["hierarchy_group"].notna()].copy()
        elif level == "national":
            working["hierarchy_group"] = "national"
        else:
            raise ValueError(f"Unsupported hierarchy level: {level}")

        if working.empty:
            return pd.DataFrame()

        weight_values = working.get(weight_col)
        if weight_values is None:
            weight_values = pd.Series(1.0, index=working.index, dtype=float)
        weights = pd.to_numeric(weight_values, errors="coerce").fillna(1.0)
        working["_hierarchy_weight"] = weights.clip(lower=1e-6)

        group_cols = ["hierarchy_group"]
        for optional in ["as_of_date", "target_date", "target_week_start", "virus_typ", "horizon_days"]:
            if optional in working.columns:
                group_cols.insert(0, optional)

        passthrough_numeric = [
            column
            for column in [
                "current_known_incidence",
                "next_week_incidence",
                "target_incidence",
                "seasonal_baseline",
                "seasonal_mad",
                "pollen_context_score",
            ]
            if column in working.columns
        ]
        aggregated_rows: list[dict[str, Any]] = []
        for group_key, group in working.groupby(group_cols, dropna=False):
            if not isinstance(group_key, tuple):
                group_key = (group_key,)
            row = {column: value for column, value in zip(group_cols, group_key, strict=False)}
            row["hierarchy_level"] = level
            row["member_count"] = int(len(group))
            row["state_members"] = sorted(group.get(state_col, pd.Series(dtype=str)).astype(str).tolist())
            group_weights = group["_hierarchy_weight"]

            for column in feature_columns:
                if column in group.columns:
                    row[column] = cls._weighted_mean(group[column], group_weights)

            for column in passthrough_numeric:
                row[column] = cls._weighted_mean(group[column], group_weights)

            row["hierarchy_member_count"] = float(len(group))
            row["hierarchy_total_weight"] = float(group_weights.sum())
            incidence_values = pd.to_numeric(group.get("current_known_incidence"), errors="coerce")
            valid_incidence = incidence_values.notna() & group_weights.notna()
            if valid_incidence.any():
                incidence = incidence_values.loc[valid_incidence].astype(float)
                incidence_weights = group_weights.loc[valid_incidence].astype(float)
                weighted_mean = float(np.average(incidence, weights=incidence_weights))
                hot_state_idx = incidence.idxmax()
                total_weight = float(incidence_weights.sum())
                row["hierarchy_incidence_std"] = cls._weighted_std(incidence, incidence_weights)
                row["hierarchy_incidence_mad"] = float(
                    np.average(np.abs(incidence - weighted_mean), weights=incidence_weights)
                )
                row["hierarchy_incidence_range"] = float(incidence.max() - incidence.min())
                row["hierarchy_incidence_max"] = float(incidence.max())
                row["hierarchy_incidence_min"] = float(incidence.min())
                row["hierarchy_hot_state_population_share"] = float(
                    incidence_weights.loc[hot_state_idx] / total_weight
                ) if total_weight > 0 else 0.0
                row["hierarchy_hot_state_excess"] = float(incidence.max() - weighted_mean)
            else:
                for column in cls.HIERARCHY_DERIVED_FEATURE_COLUMNS:
                    row[column] = 0.0

            aggregated_rows.append(row)

        aggregated = pd.DataFrame(aggregated_rows)
        return cls._attach_context_features(
            aggregated,
            level=level,
            group_cols=group_cols,
        )

    @staticmethod
    def _pairwise_values(matrix: pd.DataFrame) -> np.ndarray:
        if matrix.empty or len(matrix) < 2:
            return np.asarray([], dtype=float)
        corr = matrix.T.corr().to_numpy(dtype=float)
        upper = corr[np.triu_indices_from(corr, k=1)]
        return upper[np.isfinite(upper)]

    @staticmethod
    def _align_cluster_labels(
        current_assignments: dict[str, str],
        previous_assignments: dict[str, str],
    ) -> dict[str, str]:
        if not current_assignments or not previous_assignments:
            return {str(state): str(cluster) for state, cluster in current_assignments.items()}

        current_members: dict[str, set[str]] = {}
        previous_members: dict[str, set[str]] = {}
        for state, cluster_id in current_assignments.items():
            current_members.setdefault(str(cluster_id), set()).add(str(state))
        for state, cluster_id in previous_assignments.items():
            previous_members.setdefault(str(cluster_id), set()).add(str(state))

        cluster_scores: list[tuple[int, str, str]] = []
        for current_cluster, current_states in current_members.items():
            for previous_cluster, previous_states in previous_members.items():
                overlap = len(current_states & previous_states)
                if overlap > 0:
                    cluster_scores.append((overlap, current_cluster, previous_cluster))

        remap: dict[str, str] = {}
        used_current: set[str] = set()
        used_previous: set[str] = set()
        for _overlap, current_cluster, previous_cluster in sorted(cluster_scores, reverse=True):
            if current_cluster in used_current or previous_cluster in used_previous:
                continue
            remap[current_cluster] = previous_cluster
            used_current.add(current_cluster)
            used_previous.add(previous_cluster)

        next_cluster_idx = 0
        taken_labels = set(previous_members)
        for current_cluster in sorted(current_members):
            if current_cluster in remap:
                continue
            while f"cluster_{next_cluster_idx}" in taken_labels:
                next_cluster_idx += 1
            new_label = f"cluster_{next_cluster_idx}"
            remap[current_cluster] = new_label
            taken_labels.add(new_label)

        return {
            str(state): str(remap.get(cluster_id, cluster_id))
            for state, cluster_id in current_assignments.items()
        }

    @classmethod
    def cluster_homogeneity_diagnostics(
        cls,
        panel: pd.DataFrame,
        *,
        state_col: str = "bundesland",
        value_col: str = "current_known_incidence",
        date_col: str = "as_of_date",
        weight_col: str = "state_population_millions",
        trailing_days: int = 56,
        n_clusters: int = 3,
    ) -> dict[str, Any]:
        if panel.empty or state_col not in panel.columns or value_col not in panel.columns or date_col not in panel.columns:
            return {
                "status": "insufficient_data",
                "evaluation_dates": 0,
                "latest_clusters": {},
            }

        working = panel.copy()
        working[date_col] = pd.to_datetime(working[date_col]).dt.normalize()
        working = working.dropna(subset=[state_col, date_col]).copy()
        if working.empty:
            return {
                "status": "insufficient_data",
                "evaluation_dates": 0,
                "latest_clusters": {},
            }

        unique_dates = sorted(working[date_col].dropna().unique())
        within_values: list[float] = []
        within_date_means: list[float] = []
        between_values: list[float] = []
        cluster_counts: list[int] = []
        member_counts: list[int] = []
        previous_assignments: dict[str, str] = {}
        state_transition_counts: dict[str, int] = {}
        state_reassignment_counts: dict[str, int] = {}
        latest_snapshot: dict[str, Any] = {}
        evaluation_dates = 0

        for current_date in unique_dates:
            date_value = pd.Timestamp(current_date).normalize()
            panel_until_date = working.loc[working[date_col] <= date_value].copy()
            cluster_assignments = cls.build_dynamic_clusters(
                panel_until_date,
                state_col=state_col,
                value_col=value_col,
                date_col=date_col,
                trailing_days=trailing_days,
                n_clusters=n_clusters,
            )
            if not cluster_assignments:
                continue

            recent_cutoff = date_value - pd.Timedelta(days=trailing_days)
            recent = panel_until_date.loc[panel_until_date[date_col] >= recent_cutoff].copy()
            pivot = recent.pivot_table(
                index=state_col,
                columns=date_col,
                values=value_col,
                aggfunc="mean",
            ).ffill(axis=1).fillna(0.0)
            pivot.index = pivot.index.astype(str)
            state_order = [state for state in pivot.index.tolist() if state in cluster_assignments]
            if len(state_order) < 2:
                continue

            evaluation_dates += 1
            current_assignments_raw = {state: str(cluster_assignments[state]) for state in state_order if state in cluster_assignments}
            current_assignments = cls._align_cluster_labels(current_assignments_raw, previous_assignments)
            cluster_ids = sorted({str(value) for value in current_assignments.values()})
            cluster_counts.append(len(cluster_ids))
            if previous_assignments:
                for state, cluster_id in current_assignments.items():
                    if state not in previous_assignments:
                        continue
                    state_transition_counts[state] = int(state_transition_counts.get(state, 0)) + 1
                    if previous_assignments[state] != cluster_id:
                        state_reassignment_counts[state] = int(state_reassignment_counts.get(state, 0)) + 1
            previous_assignments = current_assignments

            full_corr = pivot.loc[state_order].T.corr()
            full_corr.index = full_corr.index.astype(str)
            full_corr.columns = full_corr.columns.astype(str)
            local_within_values: list[float] = []
            local_between_values: list[float] = []
            latest_rows = (
                panel_until_date.sort_values(date_col)
                .groupby(state_col, as_index=False)
                .tail(1)
                .set_index(state_col)
            )
            weight_series = pd.to_numeric(latest_rows.get(weight_col), errors="coerce") if weight_col in latest_rows.columns else None
            current_values = pd.to_numeric(latest_rows.get(value_col), errors="coerce")
            snapshot: dict[str, Any] = {}

            for cluster_id in cluster_ids:
                members = [state for state in state_order if current_assignments.get(state) == cluster_id]
                if not members:
                    continue
                member_counts.append(len(members))
                member_corr_values = cls._pairwise_values(pivot.loc[members])
                hot_state = None
                incidence_range = 0.0
                if current_values is not None:
                    member_current = current_values.reindex(members).dropna()
                    if not member_current.empty:
                        hot_state = str(member_current.idxmax())
                        incidence_range = float(member_current.max() - member_current.min())
                total_weight = None
                hot_state_weight_share = None
                if weight_series is not None:
                    member_weights = weight_series.reindex(members).dropna()
                    if not member_weights.empty:
                        total_weight = float(member_weights.sum())
                        if hot_state is not None and hot_state in member_weights.index and total_weight > 0:
                            hot_state_weight_share = float(member_weights.loc[hot_state] / total_weight)
                snapshot[str(cluster_id)] = {
                    "states": sorted(members),
                    "member_count": int(len(members)),
                    "within_cluster_corr_mean": (
                        round(float(np.mean(member_corr_values)), 6)
                        if member_corr_values.size
                        else None
                    ),
                    "current_incidence_range": round(float(incidence_range), 6),
                    "hot_state": hot_state,
                    "hot_state_population_share": (
                        round(float(hot_state_weight_share), 6)
                        if hot_state_weight_share is not None
                        else None
                    ),
                }

            for left_idx, left_state in enumerate(state_order):
                for right_state in state_order[left_idx + 1 :]:
                    corr_value = full_corr.at[left_state, right_state]
                    if not np.isfinite(corr_value):
                        continue
                    if current_assignments.get(left_state) == current_assignments.get(right_state):
                        local_within_values.append(float(corr_value))
                    else:
                        local_between_values.append(float(corr_value))

            if local_within_values:
                within_values.extend(local_within_values)
                within_date_means.append(float(np.mean(local_within_values)))
            if local_between_values:
                between_values.extend(local_between_values)
            latest_snapshot = snapshot

        if evaluation_dates == 0:
            return {
                "status": "insufficient_data",
                "evaluation_dates": 0,
                "latest_clusters": {},
            }

        total_transitions = int(sum(state_transition_counts.values()))
        total_reassignments = int(sum(state_reassignment_counts.values()))
        state_rates = [
            float(state_reassignment_counts.get(state, 0) / transitions)
            for state, transitions in state_transition_counts.items()
            if transitions > 0
        ]
        within_mean = float(np.mean(within_values)) if within_values else None
        between_mean = float(np.mean(between_values)) if between_values else None
        separation_gap = (
            float(within_mean - between_mean)
            if within_mean is not None and between_mean is not None
            else None
        )
        reassignment_rate = (
            float(total_reassignments / total_transitions)
            if total_transitions > 0
            else None
        )
        if within_mean is None:
            rating = "insufficient"
        elif (within_mean >= 0.65) and ((separation_gap or 0.0) >= 0.15) and ((reassignment_rate or 0.0) <= 0.15):
            rating = "good"
        elif (within_mean >= 0.4) and ((separation_gap or 0.0) >= 0.05) and ((reassignment_rate or 0.0) <= 0.3):
            rating = "mixed"
        else:
            rating = "weak"

        return {
            "status": "ok",
            "trailing_days": int(trailing_days),
            "evaluation_dates": int(evaluation_dates),
            "cluster_count_mean": round(float(np.mean(cluster_counts)), 6) if cluster_counts else None,
            "member_count_mean": round(float(np.mean(member_counts)), 6) if member_counts else None,
            "within_cluster_corr_mean": round(float(within_mean), 6) if within_mean is not None else None,
            "within_cluster_corr_median": round(float(np.median(within_values)), 6) if within_values else None,
            "within_cluster_corr_min": round(float(np.min(within_values)), 6) if within_values else None,
            "between_cluster_corr_mean": round(float(between_mean), 6) if between_mean is not None else None,
            "separation_gap": round(float(separation_gap), 6) if separation_gap is not None else None,
            "state_reassignment_rate": round(float(reassignment_rate), 6) if reassignment_rate is not None else None,
            "stable_states_share": (
                round(float(np.mean([rate <= 0.1 for rate in state_rates])), 6)
                if state_rates
                else None
            ),
            "homogeneity_rating": rating,
            "latest_clusters": latest_snapshot,
        }

    @staticmethod
    def blend_quantiles(
        *,
        model_quantiles: dict[float, np.ndarray] | None,
        baseline_quantiles: dict[float, np.ndarray],
        blend_weight: float,
    ) -> dict[float, np.ndarray]:
        if not baseline_quantiles:
            return {}
        if not model_quantiles or blend_weight <= 0.0:
            return {
                float(quantile): np.asarray(values, dtype=float)
                for quantile, values in baseline_quantiles.items()
            }
        blended: dict[float, np.ndarray] = {}
        for quantile, baseline_values in baseline_quantiles.items():
            baseline_arr = np.asarray(baseline_values, dtype=float)
            model_arr = np.asarray(model_quantiles.get(float(quantile), baseline_arr), dtype=float)
            if model_arr.shape != baseline_arr.shape:
                blended[float(quantile)] = baseline_arr
                continue
            blended[float(quantile)] = (blend_weight * model_arr) + ((1.0 - blend_weight) * baseline_arr)
        return blended

    @staticmethod
    def _resolve_state_order(
        *,
        state_quantiles: dict[float, np.ndarray],
        state_order: list[str] | None,
        cluster_assignments: dict[str, str] | None,
    ) -> list[str]:
        if state_order:
            return [str(value) for value in state_order]
        if cluster_assignments:
            return [str(value) for value in cluster_assignments]
        if not state_quantiles:
            return []
        n_states = len(np.asarray(next(iter(state_quantiles.values())), dtype=float))
        return [f"state_{idx}" for idx in range(n_states)]

    @staticmethod
    def _cluster_order(
        state_order: list[str],
        cluster_assignments: dict[str, str] | None,
    ) -> list[str]:
        if not cluster_assignments:
            return []
        seen: set[str] = set()
        ordered: list[str] = []
        for state in state_order:
            cluster = str(cluster_assignments.get(state) or f"cluster_{state}")
            if cluster in seen:
                continue
            seen.add(cluster)
            ordered.append(cluster)
        return ordered

    @staticmethod
    def _resolve_state_weights(
        *,
        state_order: list[str],
        state_weights: dict[str, float] | list[float] | np.ndarray | None,
    ) -> np.ndarray | None:
        if state_weights is None:
            return None
        if isinstance(state_weights, dict):
            values = np.asarray([float(state_weights.get(state, 1.0) or 1.0) for state in state_order], dtype=float)
        else:
            values = np.asarray(state_weights, dtype=float)
            if values.shape[0] != len(state_order):
                return None
        values = np.where(np.isfinite(values), values, 1.0)
        values = np.clip(values, 1e-6, None)
        return values

    @staticmethod
    def _aggregate_states(
        state_values: np.ndarray,
        *,
        state_order: list[str],
        cluster_assignments: dict[str, str] | None,
        cluster_order: list[str],
        state_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        weights = GeoHierarchyHelper._resolve_state_weights(
            state_order=state_order,
            state_weights=state_weights,
        )
        if not cluster_order:
            if weights is None:
                national = np.asarray([float(np.sum(state_values))], dtype=float)
            else:
                national = np.asarray([float(np.average(state_values, weights=weights))], dtype=float)
            return np.asarray([], dtype=float), national

        cluster_values = []
        for cluster in cluster_order:
            members = [
                idx
                for idx, state in enumerate(state_order)
                if str(cluster_assignments.get(state) or f"cluster_{state}") == cluster
            ]
            if not members:
                cluster_values.append(0.0)
                continue
            if weights is None:
                cluster_values.append(float(np.sum(state_values[members])))
            else:
                member_weights = weights[members]
                cluster_values.append(float(np.average(state_values[members], weights=member_weights)))
        if weights is None:
            national = np.asarray([float(np.sum(state_values))], dtype=float)
        else:
            national = np.asarray([float(np.average(state_values, weights=weights))], dtype=float)
        return np.asarray(cluster_values, dtype=float), national

    @classmethod
    def derived_aggregate_quantiles(
        cls,
        state_quantiles: dict[float, np.ndarray],
        *,
        state_order: list[str],
        cluster_assignments: dict[str, str] | None,
        state_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> tuple[dict[float, np.ndarray], dict[float, np.ndarray], list[str]]:
        cluster_assignments = {str(key): str(value) for key, value in (cluster_assignments or {}).items()}
        cluster_order = cls._cluster_order(state_order, cluster_assignments)
        cluster_quantiles: dict[float, np.ndarray] = {}
        national_quantiles: dict[float, np.ndarray] = {}
        for quantile, values in state_quantiles.items():
            cluster_values, national_values = cls._aggregate_states(
                np.asarray(values, dtype=float),
                state_order=state_order,
                cluster_assignments=cluster_assignments,
                cluster_order=cluster_order,
                state_weights=state_weights,
            )
            cluster_quantiles[float(quantile)] = cluster_values
            national_quantiles[float(quantile)] = national_values
        return cluster_quantiles, national_quantiles, cluster_order

    @classmethod
    def _summing_matrix(
        cls,
        *,
        state_order: list[str],
        cluster_assignments: dict[str, str] | None,
        cluster_order: list[str],
        state_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> np.ndarray:
        n_states = len(state_order)
        identity = np.eye(n_states, dtype=float)
        rows = [identity]
        weights = cls._resolve_state_weights(
            state_order=state_order,
            state_weights=state_weights,
        )

        if cluster_order:
            cluster_rows = np.zeros((len(cluster_order), n_states), dtype=float)
            for cluster_idx, cluster in enumerate(cluster_order):
                member_indices = [
                    state_idx
                    for state_idx, state in enumerate(state_order)
                    if str(cluster_assignments.get(state) or f"cluster_{state}") == cluster
                ]
                member_weight_sum = float(np.sum(weights[member_indices])) if weights is not None and member_indices else 0.0
                for state_idx, state in enumerate(state_order):
                    if str(cluster_assignments.get(state) or f"cluster_{state}") == cluster:
                        if weights is None or member_weight_sum <= 0.0:
                            cluster_rows[cluster_idx, state_idx] = 1.0
                        else:
                            cluster_rows[cluster_idx, state_idx] = float(weights[state_idx] / member_weight_sum)
            rows.append(cluster_rows)

        if weights is None:
            rows.append(np.ones((1, n_states), dtype=float))
        else:
            rows.append(np.asarray([weights / float(np.sum(weights))], dtype=float))
        return np.vstack(rows)

    @staticmethod
    def _prepare_weight_matrix(
        *,
        base_all_levels: np.ndarray,
        residual_history: np.ndarray | pd.DataFrame | None,
        state_order: list[str],
        cluster_assignments: dict[str, str] | None,
        cluster_order: list[str],
        state_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> np.ndarray:
        size = int(len(base_all_levels))
        if residual_history is None:
            scale = np.maximum(np.abs(base_all_levels), 1.0)
            return np.diag(scale)

        residuals = np.asarray(residual_history, dtype=float)
        if residuals.ndim != 2 or residuals.shape[0] < 2:
            scale = np.maximum(np.abs(base_all_levels), 1.0)
            return np.diag(scale)
        if residuals.shape[1] == len(state_order):
            expanded_rows = []
            for row in residuals:
                cluster_values, national_value = GeoHierarchyHelper._aggregate_states(
                    np.asarray(row, dtype=float),
                    state_order=state_order,
                    cluster_assignments=cluster_assignments,
                    cluster_order=cluster_order,
                    state_weights=state_weights,
                )
                expanded_rows.append(np.concatenate([np.asarray(row, dtype=float), cluster_values, national_value]))
            residuals = np.asarray(expanded_rows, dtype=float)
        if residuals.shape[1] != size:
            scale = np.maximum(np.abs(base_all_levels), 1.0)
            return np.diag(scale)

        covariance = np.cov(residuals, rowvar=False)
        if covariance.ndim == 0:
            covariance = np.asarray([[float(covariance)]], dtype=float)
        covariance = np.asarray(covariance, dtype=float)
        if covariance.shape != (size, size):
            scale = np.maximum(np.abs(base_all_levels), 1.0)
            return np.diag(scale)
        ridge = np.eye(size, dtype=float) * 1e-6
        return covariance + ridge

    @classmethod
    def reconcile_hierarchy(
        cls,
        state_quantiles: dict[float, np.ndarray],
        *,
        cluster_assignments: dict[str, str] | None = None,
        state_order: list[str] | None = None,
        cluster_quantiles: dict[float, np.ndarray] | None = None,
        national_quantiles: dict[float, np.ndarray | float] | None = None,
        residual_history: np.ndarray | pd.DataFrame | None = None,
        state_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> dict[str, Any]:
        if not state_quantiles:
            return {
                "state_quantiles": {},
                "cluster_quantiles": {},
                "national_quantiles": {},
                "state_order": [],
                "cluster_order": [],
                "reconciliation_method": "no_op",
                "hierarchy_consistency_status": "empty",
                "max_coherence_gap": 0.0,
                "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            }

        cluster_assignments = {str(key): str(value) for key, value in (cluster_assignments or {}).items()}
        state_order_resolved = cls._resolve_state_order(
            state_quantiles=state_quantiles,
            state_order=state_order,
            cluster_assignments=cluster_assignments,
        )
        cluster_order = cls._cluster_order(state_order_resolved, cluster_assignments)
        summing_matrix = cls._summing_matrix(
            state_order=state_order_resolved,
            cluster_assignments=cluster_assignments,
            cluster_order=cluster_order,
            state_weights=state_weights,
        )

        state_base_ordered = {
            float(quantile): np.asarray(values, dtype=float)
            for quantile, values in state_quantiles.items()
        }
        ordered_quantiles = sorted(state_base_ordered)
        reconciled_state_raw: dict[float, np.ndarray] = {}
        adjustment_totals = {"state": 0.0, "cluster": 0.0, "national": 0.0}

        for quantile in ordered_quantiles:
            state_base = np.asarray(state_base_ordered[quantile], dtype=float)
            derived_cluster_base, derived_national_base = cls._aggregate_states(
                state_base,
                state_order=state_order_resolved,
                cluster_assignments=cluster_assignments,
                cluster_order=cluster_order,
                state_weights=state_weights,
            )
            cluster_base = (
                np.asarray(cluster_quantiles[quantile], dtype=float)
                if cluster_quantiles is not None and quantile in cluster_quantiles
                else derived_cluster_base
            )
            national_base = (
                np.asarray(np.atleast_1d(national_quantiles[quantile]), dtype=float)
                if national_quantiles is not None and quantile in national_quantiles
                else derived_national_base
            )

            base_all_levels = np.concatenate([state_base, cluster_base, national_base])
            weight_matrix = cls._prepare_weight_matrix(
                base_all_levels=base_all_levels,
                residual_history=residual_history,
                state_order=state_order_resolved,
                cluster_assignments=cluster_assignments,
                cluster_order=cluster_order,
                state_weights=state_weights,
            )
            weight_inverse = np.linalg.pinv(weight_matrix)
            projection = summing_matrix @ np.linalg.pinv(
                summing_matrix.T @ weight_inverse @ summing_matrix
            ) @ summing_matrix.T @ weight_inverse
            reconciled_all = np.maximum(projection @ base_all_levels, 0.0)
            reconciled_state = reconciled_all[: len(state_order_resolved)]
            reconciled_state_raw[quantile] = reconciled_state

            reconciled_cluster, reconciled_national = cls._aggregate_states(
                reconciled_state,
                state_order=state_order_resolved,
                cluster_assignments=cluster_assignments,
                cluster_order=cluster_order,
                state_weights=state_weights,
            )
            adjustment_totals["state"] += float(np.sum(np.abs(reconciled_state - state_base)))
            adjustment_totals["cluster"] += float(np.sum(np.abs(reconciled_cluster - cluster_base)))
            adjustment_totals["national"] += float(np.sum(np.abs(reconciled_national - national_base)))

        reconciled_state_quantiles = monotone_quantiles(reconciled_state_raw)
        reconciled_cluster_quantiles: dict[float, np.ndarray] = {}
        reconciled_national_quantiles: dict[float, np.ndarray] = {}
        max_gap = 0.0
        for quantile in ordered_quantiles:
            cluster_values, national_values = cls._aggregate_states(
                reconciled_state_quantiles[quantile],
                state_order=state_order_resolved,
                cluster_assignments=cluster_assignments,
                cluster_order=cluster_order,
                state_weights=state_weights,
            )
            reconciled_cluster_quantiles[quantile] = cluster_values
            reconciled_national_quantiles[quantile] = national_values
            recomputed_cluster, recomputed_national = cls._aggregate_states(
                reconciled_state_quantiles[quantile],
                state_order=state_order_resolved,
                cluster_assignments=cluster_assignments,
                cluster_order=cluster_order,
                state_weights=state_weights,
            )
            max_gap = max(
                max_gap,
                0.0 if len(cluster_values) == 0 else float(np.max(np.abs(cluster_values - recomputed_cluster))),
                float(np.max(np.abs(national_values - recomputed_national))),
            )

        total_adjustment = sum(adjustment_totals.values())
        if total_adjustment <= 1e-9:
            attribution = {"state": 1.0, "cluster": 0.0, "national": 0.0}
        else:
            attribution = {
                key: round(value / total_adjustment, 6)
                for key, value in adjustment_totals.items()
            }

        return {
            "state_quantiles": reconciled_state_quantiles,
            "cluster_quantiles": reconciled_cluster_quantiles,
            "national_quantiles": reconciled_national_quantiles,
            "state_order": state_order_resolved,
            "cluster_order": cluster_order,
            "reconciliation_method": "mint_projection_residual_covariance" if residual_history is not None else "mint_projection_diagonal",
            "hierarchy_consistency_status": "coherent" if max_gap <= 1e-6 else "approximate",
            "max_coherence_gap": round(float(max_gap), 10),
            "hierarchy_driver_attribution": attribution,
        }

    @classmethod
    def reconcile_quantiles(
        cls,
        state_quantiles: dict[float, np.ndarray],
        *,
        cluster_assignments: dict[str, str] | None = None,
        state_order: list[str] | None = None,
        cluster_quantiles: dict[float, np.ndarray] | None = None,
        national_quantiles: dict[float, np.ndarray | float] | None = None,
        residual_history: np.ndarray | pd.DataFrame | None = None,
        state_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> tuple[dict[float, np.ndarray], dict[str, Any]]:
        reconciled = cls.reconcile_hierarchy(
            state_quantiles,
            cluster_assignments=cluster_assignments,
            state_order=state_order,
            cluster_quantiles=cluster_quantiles,
            national_quantiles=national_quantiles,
            residual_history=residual_history,
            state_weights=state_weights,
        )
        attribution = dict(reconciled["hierarchy_driver_attribution"])
        attribution.update(
            {
                "reconciliation_method": reconciled["reconciliation_method"],
                "hierarchy_consistency_status": reconciled["hierarchy_consistency_status"],
                "max_coherence_gap": reconciled["max_coherence_gap"],
                "cluster_order": reconciled["cluster_order"],
                "state_order": reconciled["state_order"],
                "cluster_quantiles": reconciled["cluster_quantiles"],
                "national_quantiles": reconciled["national_quantiles"],
            }
        )
        return reconciled["state_quantiles"], attribution
