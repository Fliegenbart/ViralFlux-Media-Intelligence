import json
import tempfile
import unittest
from pathlib import Path

from app.services.media.cockpit.truth_scoreboard import build_truth_scoreboard


def _timeline(
    *,
    weeks: int,
    hit_weeks: int,
    observed_weeks: int | None = None,
    decoy_rank: int = 0,
) -> list[dict]:
    observed = weeks if observed_weeks is None else observed_weeks
    rows: list[dict] = []
    for idx in range(weeks):
        as_of = f"2026-01-{(idx % 28) + 1:02d}"
        event_label = 1 if idx < observed and decoy_rank == 0 else 0
        if decoy_rank == 0:
            probability = 0.9 if idx < hit_weeks else 0.05
        else:
            probability = 0.1 if idx < hit_weeks else 0.8 - decoy_rank * 0.05
        rows.append(
            {
                "as_of_date": as_of,
                "target_date": as_of,
                "event_label": event_label,
                "event_probability_calibrated": probability,
            }
        )
    return rows


class TruthScoreboardBuilderTests(unittest.TestCase):
    def _write_artifact(
        self,
        root: Path,
        *,
        virus_dir: str = "influenza_a",
        horizon_days: int,
        weeks: int,
        hit_weeks: int,
        observed_weeks: int | None = None,
        quality_passed: bool = True,
        pr_auc: float = 0.7,
        persistence_pr_auc: float = 0.3,
        precision_at_top3: float = 0.72,
        persistence_precision_at_top3: float = 0.55,
        ece: float = 0.02,
    ) -> None:
        path = root / virus_dir / f"horizon_{horizon_days}"
        path.mkdir(parents=True)
        artifact = {
            "aggregate_metrics": {
                "precision_at_top3": precision_at_top3,
                "pr_auc": pr_auc,
                "brier_score": 0.06,
                "ece": ece,
                "activation_false_positive_rate": 0.03,
                "median_lead_days": 5,
            },
            "baselines": {
                "persistence": {
                    "precision_at_top3": persistence_precision_at_top3,
                    "pr_auc": persistence_pr_auc,
                }
            },
            "quality_gate": {
                "forecast_readiness": "GO" if quality_passed else "WATCH",
                "overall_passed": quality_passed,
            },
            "details": {},
        }
        for rank, code in enumerate(["BY", "HB", "HH", "BE"]):
            artifact["details"][code] = {
                "bundesland_name": code,
                "timeline": _timeline(
                    weeks=weeks,
                    hit_weeks=hit_weeks,
                    observed_weeks=observed_weeks,
                    decoy_rank=rank,
                ),
            }
        (path / "backtest.json").write_text(json.dumps(artifact), encoding="utf-8")

    def test_scoreboard_marks_h7_go_and_h5_blocked_when_h5_has_too_few_evaluable_weeks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(root, horizon_days=5, weeks=10, hit_weeks=8, observed_weeks=10)
            self._write_artifact(root, horizon_days=7, weeks=20, hit_weeks=18, observed_weeks=20)

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[5, 7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        cards = {(c["virus_typ"], c["horizon_days"]): c for c in payload["scorecards"]}
        self.assertEqual(cards[("Influenza A", 5)]["readiness"], "blocked")
        self.assertIn("too_few_evaluable_weeks", cards[("Influenza A", 5)]["blockers"])
        self.assertEqual(cards[("Influenza A", 7)]["readiness"], "go")
        self.assertAlmostEqual(cards[("Influenza A", 7)]["hit_rate"], 0.9)

        combined = payload["combined_by_virus"]["Influenza A"]
        self.assertEqual(combined["decision_class"], "weekly_only_prepare")
        self.assertEqual(combined["budget_permission"], "blocked_until_h5_or_business_truth")
        self.assertEqual(payload["policy"]["budget_rule"], "never_auto_release_without_business_truth")

    def test_scoreboard_blocks_when_model_does_not_beat_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                pr_auc=0.30,
                persistence_pr_auc=0.35,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "blocked")
        self.assertIn("does_not_beat_persistence_pr_auc", card["blockers"])
        self.assertLess(card["score"], 70)
