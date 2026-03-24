from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from app.services.ml.benchmarking.metrics import summarize_frame_metrics


def build_leaderboard(
    frame: pd.DataFrame,
    *,
    candidate_col: str = "candidate",
    group_by: Sequence[str] = ("virus_typ", "horizon_days", "bundesland"),
    action_threshold: float | None = None,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []

    rows: list[dict[str, Any]] = []
    group_columns = [column for column in group_by if column in frame.columns]
    for keys, group in frame.groupby(group_columns + [candidate_col], dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {
            column: value
            for column, value in zip(group_columns + [candidate_col], keys, strict=False)
        }
        row.update(
            summarize_frame_metrics(
                group,
                action_threshold=action_threshold,
            )
        )
        row["samples"] = int(len(group))
        rows.append(row)

    rows.sort(
        key=lambda item: (
            float(item.get("relative_wis") or 9999.0),
            float(item.get("crps") or 9999.0),
            -float(item.get("coverage_95") or 0.0),
            float(item.get("brier_score") or 9999.0),
            -float(item.get("decision_utility") or float("-inf")),
        )
    )
    return rows
