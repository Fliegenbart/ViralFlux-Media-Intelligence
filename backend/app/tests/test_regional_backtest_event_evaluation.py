import unittest

import pandas as pd

from app.services.ml.regional_panel_utils import (
    activation_false_positive_rate,
    average_precision_safe,
    quality_gate_from_metrics,
)
from app.services.ml.regional_trainer_backtest import (
    _summarize_event_fold_viability,
    aggregate_metrics,
)


def _build_fold_rows(
    *,
    fold: int,
    as_of_start: str,
    viable: bool,
    include_false_alerts: bool = False,
) -> list[dict[str, object]]:
    as_of_date = pd.Timestamp(as_of_start)
    rows: list[dict[str, object]] = []
    if viable:
        positive_regions = ["BY", "BE", "BY", "BE", "BW"]
        positive_scores = [0.98, 0.96, 0.95, 0.93, 0.92]
        negative_regions = ["BY", "BE", "BW", "HE", "HH"]
        negative_scores = [0.35, 0.25, 0.15, 0.05, 0.01]
        for idx, (region, score) in enumerate(zip(positive_regions, positive_scores)):
            rows.append(
                {
                    "fold": fold,
                    "as_of_date": as_of_date + pd.Timedelta(days=idx),
                    "target_week_start": as_of_date + pd.Timedelta(days=idx + 7),
                    "bundesland": region,
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "event_label": 1,
                    "event_probability_calibrated": score,
                }
            )
        for idx, (region, score) in enumerate(zip(negative_regions, negative_scores), start=len(rows)):
            rows.append(
                {
                    "fold": fold,
                    "as_of_date": as_of_date + pd.Timedelta(days=idx),
                    "target_week_start": as_of_date + pd.Timedelta(days=idx + 7),
                    "bundesland": region,
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "event_label": 0,
                    "event_probability_calibrated": score,
                }
            )
        return rows

    negative_regions = ["BY", "BE", "BW", "HE", "HH"]
    negative_scores = [0.97, 0.94, 0.91, 0.88, 0.86] if include_false_alerts else [0.07, 0.05, 0.03, 0.02, 0.01]
    for idx, (region, score) in enumerate(zip(negative_regions, negative_scores)):
        rows.append(
            {
                "fold": fold,
                "as_of_date": as_of_date + pd.Timedelta(days=idx),
                "target_week_start": as_of_date + pd.Timedelta(days=idx + 7),
                "bundesland": region,
                "virus_typ": "Influenza A",
                "horizon_days": 7,
                "event_label": 0,
                "event_probability_calibrated": score,
            }
        )
    return rows


class RegionalBacktestEventEvaluationTests(unittest.TestCase):
    def test_fold_viability_allows_single_non_viable_fold(self) -> None:
        frame = pd.DataFrame(
            _build_fold_rows(fold=0, as_of_start="2025-01-01", viable=True)
            + _build_fold_rows(fold=1, as_of_start="2025-02-01", viable=True)
            + _build_fold_rows(fold=2, as_of_start="2025-03-01", viable=False)
            + _build_fold_rows(fold=3, as_of_start="2025-04-01", viable=True)
            + _build_fold_rows(fold=4, as_of_start="2025-05-01", viable=True)
        )

        summary = _summarize_event_fold_viability(frame)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["viable_fold_count"], 4)
        self.assertEqual(summary["non_viable_fold_count"], 1)
        self.assertEqual(summary["minimum_viable_folds"], 4)
        self.assertEqual(summary["folds"][2]["event_viability_reason"], "no_positive_events")

    def test_aggregate_metrics_use_viable_folds_for_discrimination_only(self) -> None:
        frame = pd.DataFrame(
            _build_fold_rows(fold=0, as_of_start="2025-01-01", viable=True)
            + _build_fold_rows(
                fold=1,
                as_of_start="2025-02-01",
                viable=False,
                include_false_alerts=True,
            )
        )
        viable_frame = frame.loc[frame["fold"] == 0].copy()

        metrics = aggregate_metrics(frame, action_threshold=0.85)

        self.assertEqual(metrics["event_viable_fold_count"], 1)
        self.assertEqual(metrics["event_non_viable_fold_count"], 1)
        self.assertTrue(metrics["event_discrimination_available"])
        self.assertEqual(
            metrics["pr_auc"],
            round(
                average_precision_safe(
                    viable_frame["event_label"],
                    viable_frame["event_probability_calibrated"],
                ),
                6,
            ),
        )
        self.assertEqual(
            metrics["activation_false_positive_rate"],
            activation_false_positive_rate(
                frame,
                threshold=0.85,
                score_col="event_probability_calibrated",
            ),
        )

    def test_quality_gate_skips_discrimination_checks_when_unavailable(self) -> None:
        result = quality_gate_from_metrics(
            metrics={
                "precision_at_top3": 0.0,
                "activation_false_positive_rate": 0.01,
                "pr_auc": 0.0,
                "brier_score": 0.09,
                "ece": 0.03,
                "event_discrimination_available": False,
            },
            baseline_metrics={
                "persistence": {"pr_auc": 0.52},
                "climatology": {"pr_auc": 0.50, "brier_score": 0.10},
                "amelag_only": {"pr_auc": 0.48},
            },
            virus_typ="Influenza A",
            horizon_days=7,
        )

        self.assertTrue(result["overall_passed"])
        self.assertEqual(
            result["skipped_checks"],
            ["precision_at_top3_passed", "pr_auc_passed"],
        )
        self.assertTrue(result["checks"]["precision_at_top3_passed"])
        self.assertTrue(result["checks"]["pr_auc_passed"])
