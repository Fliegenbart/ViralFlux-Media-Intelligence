from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from app.services.ml.benchmarking.artifacts import write_benchmark_artifacts
from app.services.ml.benchmarking.contracts import BenchmarkArtifactSummary, BENCHMARK_BASELINE_NAME
from app.services.ml.benchmarking.leaderboard import build_leaderboard
from app.services.ml.benchmarking.metrics import summarize_frame_metrics


@dataclass(frozen=True)
class BenchmarkCandidateSpec:
    name: str
    fit_predict: Callable[[pd.Timestamp, pd.DataFrame], pd.DataFrame]


class LockedVintageBacktestRunner:
    """Small locked rolling-origin runner for benchmark experiments."""

    def __init__(
        self,
        *,
        history_frame: pd.DataFrame,
        issue_dates: list[pd.Timestamp],
        output_dir=None,
    ) -> None:
        self.history_frame = history_frame.copy()
        self.issue_dates = [pd.Timestamp(value).normalize() for value in issue_dates]
        self.output_dir = output_dir

    def run(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        candidates: list[BenchmarkCandidateSpec],
        baseline_name: str = BENCHMARK_BASELINE_NAME,
        action_threshold: float | None = None,
    ) -> dict[str, Any]:
        frames: list[pd.DataFrame] = []
        for issue_date in self.issue_dates:
            vintage = self.history_frame.loc[
                pd.to_datetime(self.history_frame["as_of_date"]).dt.normalize() <= issue_date
            ].copy()
            if vintage.empty:
                continue
            for candidate in candidates:
                prediction_frame = candidate.fit_predict(issue_date, vintage)
                if prediction_frame.empty:
                    continue
                prediction_frame = prediction_frame.copy()
                prediction_frame["candidate"] = candidate.name
                frames.append(prediction_frame)

        if not frames:
            return {
                "virus_typ": virus_typ,
                "horizon_days": horizon_days,
                "leaderboard": [],
                "metrics": {},
            }

        combined = pd.concat(frames, ignore_index=True)
        leaderboard = build_leaderboard(
            combined,
            action_threshold=action_threshold,
        )
        champion_name = leaderboard[0]["candidate"] if leaderboard else None
        champion_frame = combined.loc[combined["candidate"] == champion_name].copy() if champion_name else combined
        summary = BenchmarkArtifactSummary(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            issue_dates=[value.isoformat() for value in self.issue_dates],
            primary_metric="relative_wis",
            champion_name=champion_name,
            metrics=summarize_frame_metrics(
                champion_frame,
                action_threshold=action_threshold,
            ),
            leaderboard=leaderboard,
        )
        result = summary.to_dict()
        if self.output_dir is not None:
            result["artifacts"] = write_benchmark_artifacts(
                output_dir=self.output_dir,
                summary=summary,
                diagnostics=combined.to_dict(orient="records"),
            )
        return result
