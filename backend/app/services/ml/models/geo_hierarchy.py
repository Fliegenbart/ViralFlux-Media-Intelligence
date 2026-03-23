from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

from app.services.ml.benchmarking.metrics import monotone_quantiles


class GeoHierarchyHelper:
    """Dynamic clustering and simple coherent reconciliation helpers."""

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
        ).fillna(method="ffill", axis=1).fillna(0.0)
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

    @staticmethod
    def reconcile_quantiles(
        state_quantiles: dict[float, np.ndarray],
        *,
        cluster_assignments: dict[str, str] | None = None,
        state_order: list[str] | None = None,
    ) -> tuple[dict[float, np.ndarray], dict[str, Any]]:
        if not state_quantiles:
            return {}, {"state": 0.0, "cluster": 0.0, "national": 0.0}

        reconciled = monotone_quantiles(state_quantiles)
        attribution = {
            "state": 1.0,
            "cluster": 0.0 if not cluster_assignments else 0.2,
            "national": 0.0 if not state_order else 0.1,
        }
        return reconciled, attribution
