import json
import tempfile
import unittest
from pathlib import Path

from app.services.media.cockpit.truth_scoreboard import build_truth_scoreboard


DEFAULT_REGION_CODES = [
    "BY",
    "HB",
    "HH",
    "BE",
    "BW",
    "NW",
    "HE",
    "NI",
    "SN",
    "ST",
    "SH",
    "RP",
    "SL",
    "TH",
]

DEFAULT_DELTA_CI_95 = {
    "event_model": {
        "persistence": {
            "pr_auc": [0.02, 0.25],
            "precision_at_top3": [0.04, 0.22],
        }
    }
}


def _timeline(
    *,
    weeks: int,
    hit_weeks: int,
    observed_weeks: int | None = None,
    decoy_rank: int = 0,
    persistence_hit_weeks: int | None = None,
    include_current_known_incidence: bool = True,
) -> list[dict]:
    observed = weeks if observed_weeks is None else observed_weeks
    persistence_hits = (
        max(0, hit_weeks - 3)
        if persistence_hit_weeks is None
        else persistence_hit_weeks
    )
    rows: list[dict] = []
    for idx in range(weeks):
        as_of = f"2026-01-{(idx % 28) + 1:02d}"
        event_label = 1 if idx < observed and decoy_rank == 0 else 0
        if decoy_rank == 0:
            probability = 0.9 if idx < hit_weeks else 0.05
            current_known_incidence = 100.0 if idx < persistence_hits else 0.1
        else:
            probability = 0.1 if idx < hit_weeks else 0.8 - decoy_rank * 0.05
            current_known_incidence = 1.0 - decoy_rank * 0.01
        row = {
            "as_of_date": as_of,
            "target_date": as_of,
            "event_label": event_label,
            "event_probability_calibrated": probability,
        }
        if include_current_known_incidence:
            row["current_known_incidence"] = current_known_incidence
        rows.append(row)
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
        ece: float | None = 0.02,
        quality_gate: dict | None = None,
        region_codes: list[str] | None = None,
        persistence_hit_weeks: int | None = None,
        include_current_known_incidence: bool = True,
        delta_ci_95: dict | None = None,
        include_delta_ci_95: bool = True,
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
            "quality_gate": quality_gate
            or {
                "forecast_readiness": "GO" if quality_passed else "WATCH",
                "overall_passed": quality_passed,
            },
            "details": {},
        }
        if include_delta_ci_95:
            artifact["delta_ci_95"] = delta_ci_95 or DEFAULT_DELTA_CI_95
        for rank, code in enumerate(region_codes or DEFAULT_REGION_CODES):
            artifact["details"][code] = {
                "bundesland_name": code,
                "timeline": _timeline(
                    weeks=weeks,
                    hit_weeks=hit_weeks,
                    observed_weeks=observed_weeks,
                    decoy_rank=rank,
                    persistence_hit_weeks=persistence_hit_weeks,
                    include_current_known_incidence=include_current_known_incidence,
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

    def test_combined_decision_does_not_treat_candidate_and_go_as_fully_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=5,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                include_delta_ci_95=False,
            )
            self._write_artifact(root, horizon_days=7, weeks=20, hit_weeks=18, observed_weeks=20)

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[5, 7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        combined = payload["combined_by_virus"]["Influenza A"]
        self.assertEqual(combined["h5"]["readiness"], "candidate")
        self.assertEqual(combined["h7"]["readiness"], "go")
        self.assertEqual(combined["decision_class"], "weekly_only_prepare")
        self.assertNotEqual(combined["decision_class"], "short_and_weekly_supported")
        self.assertNotEqual(combined["media_action"], "controlled_shift_candidate")

    def test_combined_decision_candidate_and_candidate_requires_manual_watch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=5,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                include_delta_ci_95=False,
            )
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                include_delta_ci_95=False,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[5, 7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        combined = payload["combined_by_virus"]["Influenza A"]
        self.assertEqual(combined["h5"]["readiness"], "candidate")
        self.assertEqual(combined["h7"]["readiness"], "candidate")
        self.assertEqual(combined["decision_class"], "forecast_watch_candidate")
        self.assertEqual(combined["media_action"], "watch_with_manual_review")
        self.assertEqual(combined["budget_permission"], "blocked")

    def test_combined_decision_only_go_and_go_allows_controlled_shift_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(root, horizon_days=5, weeks=20, hit_weeks=18, observed_weeks=20)
            self._write_artifact(root, horizon_days=7, weeks=20, hit_weeks=18, observed_weeks=20)

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[5, 7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        combined = payload["combined_by_virus"]["Influenza A"]
        self.assertEqual(combined["h5"]["readiness"], "go")
        self.assertEqual(combined["h7"]["readiness"], "go")
        self.assertEqual(combined["decision_class"], "short_and_weekly_supported")
        self.assertEqual(combined["media_action"], "controlled_shift_candidate")

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
        self.assertLess(card["score"], 50)

    def test_missing_ece_warns_and_does_not_receive_go_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                ece=None,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "candidate")
        self.assertIn("calibration_ece_missing", card["warnings"])
        self.assertLess(card["score"], 80)

    def test_go_score_requires_no_blockers_or_warnings_and_uses_defensive_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "go")
        self.assertEqual(card["blockers"], [])
        self.assertEqual(card["warnings"], [])
        self.assertGreaterEqual(card["score"], 80)
        self.assertEqual(
            card["score_interpretation"],
            "heuristic_readiness_score_not_statistical_confidence",
        )
        self.assertIn("Business-Truth-gated", card["plain_language"])
        self.assertNotIn("belastbar", card["plain_language"])

    def test_quality_gate_nested_checks_are_preserved_and_failed_gate_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                quality_gate={
                    "forecast_readiness": "WATCH",
                    "overall_passed": False,
                    "profile": "strict_v1",
                    "checks": {
                        "precision_at_top3_passed": False,
                        "pr_auc_passed": True,
                    },
                    "failed_checks": ["precision_at_top3_passed"],
                    "thresholds": {
                        "precision_at_top3": 0.7,
                    },
                },
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "blocked")
        self.assertIn("artifact_quality_gate_not_passed", card["blockers"])
        self.assertEqual(card["quality_gate"]["checks"]["precision_at_top3_passed"], False)
        self.assertEqual(card["quality_gate"]["failed_checks"], ["precision_at_top3_passed"])
        self.assertEqual(card["quality_gate"]["thresholds"]["precision_at_top3"], 0.7)

    def test_weeks_with_too_few_regions_do_not_count_as_evaluable_top3_panels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=20,
                observed_weeks=20,
                region_codes=["BY", "HB", "HH"],
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "blocked")
        self.assertIn("too_few_evaluable_weeks", card["blockers"])
        self.assertEqual(card["evaluable_weeks"], 0)
        self.assertGreater(card["coverage_rejected_weeks"], 0)

    def test_weeks_with_fourteen_regions_count_as_evaluable_top3_panels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                region_codes=DEFAULT_REGION_CODES,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertGreaterEqual(card["evaluable_weeks"], 12)
        self.assertNotIn("too_few_evaluable_weeks", card["blockers"])

    def test_high_hit_rate_blocked_when_not_better_than_persistence_hit_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                persistence_hit_weeks=18,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "blocked")
        self.assertAlmostEqual(card["hit_rate"], 0.9)
        self.assertEqual(card["baseline_hit_rates"]["persistence_hit_rate"], 0.9)
        self.assertEqual(card["lift_vs_baseline_hit_rate"]["persistence_pp"], 0.0)
        self.assertIn("hit_rate_not_better_than_persistence", card["blockers"])

    def test_missing_current_known_incidence_keeps_persistence_hit_rate_empty_and_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                include_current_known_incidence=False,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertIsNone(card["baseline_hit_rates"]["persistence_hit_rate"])
        self.assertIn("persistence_hit_rate_missing", card["warnings"])

    def test_random_expected_hit_rate_uses_panel_size_events_and_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                region_codes=DEFAULT_REGION_CODES,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertAlmostEqual(
            card["baseline_hit_rates"]["random_expected_hit_rate"],
            3 / 14,
            places=4,
        )

    def test_pr_auc_positive_point_estimate_blocks_when_ci_lower_bound_not_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                pr_auc=0.7,
                persistence_pr_auc=0.3,
                delta_ci_95={
                    "event_model": {
                        "persistence": {
                            "pr_auc": [0.0, 0.3],
                            "precision_at_top3": [0.04, 0.22],
                        }
                    }
                },
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "blocked")
        self.assertIn("pr_auc_lift_ci_not_positive", card["blockers"])
        self.assertEqual(card["lift_confidence"]["pr_auc_delta_ci_95"], [0.0, 0.3])

    def test_precision_positive_point_estimate_warns_when_ci_lower_bound_not_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                precision_at_top3=0.72,
                persistence_precision_at_top3=0.55,
                delta_ci_95={
                    "event_model": {
                        "persistence": {
                            "pr_auc": [0.02, 0.25],
                            "precision_at_top3": [0.0, 0.22],
                        }
                    }
                },
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "candidate")
        self.assertIn("precision_top3_lift_ci_not_positive", card["warnings"])
        self.assertNotIn("precision_top3_lift_ci_not_positive", card["blockers"])
        self.assertEqual(
            card["lift_confidence"]["precision_at_top3_delta_ci_95"], [0.0, 0.22]
        )

    def test_missing_lift_confidence_interval_warns_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=20,
                hit_weeks=18,
                observed_weeks=20,
                include_delta_ci_95=False,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "candidate")
        self.assertIsNone(card["lift_confidence"]["pr_auc_delta_ci_95"])
        self.assertIsNone(card["lift_confidence"]["precision_at_top3_delta_ci_95"])
        self.assertIn("lift_confidence_interval_missing", card["warnings"])
