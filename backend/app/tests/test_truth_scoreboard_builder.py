import json
import tempfile
import unittest
import datetime as _datetime
import sys
import types
from pathlib import Path

import pandas as pd

from app.services.media.cockpit.backtest_builder import build_backtest_summary
from app.services.media.cockpit.truth_scoreboard import build_truth_scoreboard


NATIONAL_REGION_CODES = [
    "BW",
    "BY",
    "BE",
    "BB",
    "HB",
    "HH",
    "HE",
    "MV",
    "NI",
    "NW",
    "RP",
    "SL",
    "SN",
    "ST",
    "SH",
    "TH",
]

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


def _native_panel_evaluation(
    *,
    weeks: int,
    hit_weeks: int,
    region_codes: list[str] | None = None,
    missing_by_week: dict[int, list[str]] | None = None,
    include_events: bool = True,
) -> dict:
    universe = NATIONAL_REGION_CODES
    available_regions = region_codes or universe
    rows = []
    for idx in range(weeks):
        missing = set((missing_by_week or {}).get(idx, []))
        scored = [code for code in available_regions if code not in missing]
        observed = ["BY"] if include_events else []
        predicted = ["BY", "BW", "BE"] if idx < hit_weeks else ["NW", "HE", "NI"]
        predicted_top3 = [
            {"code": code, "probability": 0.9 - rank * 0.1}
            for rank, code in enumerate(predicted)
            if code in scored
        ]
        persistence_top3 = [
            {"code": code, "current_known_incidence": 100.0 - rank}
            for rank, code in enumerate(["NW", "HE", "NI"])
            if code in scored
        ]
        rows.append(
            {
                "virus": "Influenza A",
                "horizon_days": 7,
                "forecast_issue_date": f"2026-01-{idx + 1:02d}",
                "forecast_issue_week": f"2026-01-{idx + 1:02d}",
                "target_week_start": f"2026-01-{idx + 8:02d}",
                "region_universe": universe,
                "scored_regions": scored,
                "missing_regions": [code for code in universe if code not in set(scored)],
                "scored_region_count": len(scored),
                "expected_region_count": len(universe),
                "observed_event_regions": observed,
                "observed_event_count": len(observed),
                "predicted_top3": predicted_top3,
                "persistence_top3": persistence_top3,
                "model_was_hit": bool(set(predicted) & set(observed)),
                "persistence_was_hit": False,
                "random_expected_hit_probability": 3 / len(scored) if scored and observed else None,
                "is_evaluable_top3_panel": len(scored) >= 14 and bool(observed),
            }
        )
    return {
        "schema_version": "panel_evaluation_v1",
        "region_universe": universe,
        "expected_region_count": len(universe),
        "rows": rows,
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
        panel_evaluation: dict | None = None,
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
        if panel_evaluation is not None:
            artifact["panel_evaluation"] = panel_evaluation
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

    def test_native_panel_evaluation_rows_are_used_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=3,
                hit_weeks=3,
                observed_weeks=3,
                region_codes=["BY", "HB", "HH"],
                precision_at_top3=0.9,
                panel_evaluation=_native_panel_evaluation(weeks=20, hit_weeks=18),
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["evaluation_source"], "native_panel_evaluation")
        self.assertEqual(card["readiness"], "go")
        self.assertEqual(card["evaluable_weeks"], 20)
        self.assertAlmostEqual(card["hit_rate"], 0.9)

    def test_legacy_weekly_hits_fallback_still_works_without_native_panel(self) -> None:
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
        self.assertEqual(card["evaluation_source"], "legacy_reconstructed_weekly_hits")
        self.assertEqual(card["readiness"], "go")

    def test_native_sixteen_region_panels_produce_evaluable_weeks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=1,
                hit_weeks=1,
                panel_evaluation=_native_panel_evaluation(weeks=12, hit_weeks=12),
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["evaluable_weeks"], 12)
        self.assertNotIn("too_few_evaluable_weeks", card["blockers"])

    def test_native_panel_zero_evaluable_rows_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=1,
                hit_weeks=1,
                panel_evaluation=_native_panel_evaluation(
                    weeks=20,
                    hit_weeks=20,
                    region_codes=NATIONAL_REGION_CODES[:13],
                ),
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(card["readiness"], "blocked")
        self.assertEqual(card["evaluable_weeks"], 0)
        self.assertIn("no_evaluable_full_panel_truth_weeks", card["blockers"])

    def test_dynamic_region_sets_do_not_create_covered_universe_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            panel = _native_panel_evaluation(
                weeks=20,
                hit_weeks=20,
                missing_by_week={0: ["BW", "BY", "BE"], 1: ["NW", "HE", "NI"]},
            )
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=1,
                hit_weeks=1,
                panel_evaluation=panel,
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertNotIn(card["readiness"], {"covered_universe_go", "covered_universe_candidate"})
        self.assertNotIn("covered_regions_only", str(payload))

    def test_native_panel_missing_regions_are_preserved_in_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=1,
                hit_weeks=1,
                panel_evaluation=_native_panel_evaluation(
                    weeks=2,
                    hit_weeks=2,
                    missing_by_week={0: ["BW", "BE"]},
                ),
            )

            summary = build_backtest_summary(
                virus_typ="Influenza A",
                horizon_days=7,
                models_dir=root,
            )

        self.assertEqual(summary["evaluation_source"], "native_panel_evaluation")
        self.assertEqual(summary["weekly_hits"][0]["missing_regions"], ["BW", "BE"])

    def test_native_panel_precision_metric_consistency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=1,
                hit_weeks=1,
                precision_at_top3=0.9,
                panel_evaluation=_native_panel_evaluation(weeks=20, hit_weeks=18),
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertEqual(
            card["panel_metric_consistency"]["quality_gate_precision_at_top3"],
            card["panel_metric_consistency"]["scoreboard_precision_at_top3"],
        )
        self.assertNotIn("quality_gate_scoreboard_panel_metric_mismatch", card["warnings"])

    def test_native_panel_precision_metric_mismatch_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_artifact(
                root,
                horizon_days=7,
                weeks=1,
                hit_weeks=1,
                precision_at_top3=0.4,
                panel_evaluation=_native_panel_evaluation(weeks=20, hit_weeks=18),
            )

            payload = build_truth_scoreboard(
                virus_types=["Influenza A"],
                horizons=[7],
                models_dir=root,
                min_evaluable_weeks=12,
            )

        card = payload["scorecards"][0]
        self.assertIn("quality_gate_scoreboard_panel_metric_mismatch", card["warnings"])

    def test_backtest_payload_writes_native_panel_evaluation_schema(self) -> None:
        if not hasattr(_datetime, "UTC"):
            _datetime.UTC = _datetime.timezone.utc
        sys.modules.setdefault(
            "xgboost",
            types.SimpleNamespace(XGBClassifier=object, XGBRegressor=object),
        )
        from app.services.ml.regional_trainer_backtest import build_backtest_payload

        rows = []
        for week in range(2):
            for rank, code in enumerate(NATIONAL_REGION_CODES):
                rows.append(
                    {
                        "virus_typ": "Influenza A",
                        "horizon_days": 7,
                        "bundesland": code,
                        "as_of_date": pd.Timestamp(f"2026-01-{week + 1:02d}"),
                        "target_week_start": pd.Timestamp(f"2026-01-{week + 8:02d}"),
                        "event_label": 1 if code == "BY" else 0,
                        "event_probability_calibrated": 0.95 if code == "BY" else 0.5 - rank * 0.01,
                        "event_probability_raw": 0.95 if code == "BY" else 0.5 - rank * 0.01,
                        "persistence_probability": 0.1,
                        "climatology_probability": 0.1,
                        "amelag_only_probability": 0.1,
                        "current_known_incidence": float(rank),
                        "action_threshold": 0.5,
                        "fold": week,
                        "absolute_error": 0.0,
                        "residual": 0.0,
                        "calibration_mode": "test",
                    }
                )
        frame = pd.DataFrame(rows)

        payload = build_backtest_payload(
            None,
            frame=frame,
            aggregate_metrics={
                "precision_at_top3": 1.0,
                "pr_auc": 1.0,
                "brier_score": 0.01,
                "ece": 0.01,
            },
            baselines={"persistence": {"precision_at_top3": 0.1, "pr_auc": 0.1}},
            quality_gate={"overall_passed": True},
            tau=1.0,
            kappa=1.0,
            action_threshold=0.5,
            fold_selection_summary=[],
        )

        panel = payload["panel_evaluation"]
        self.assertEqual(panel["schema_version"], "panel_evaluation_v1")
        self.assertEqual(panel["expected_region_count"], 16)
        self.assertEqual(len(panel["rows"]), 2)
        self.assertEqual(panel["rows"][0]["scored_region_count"], 16)
        self.assertEqual(panel["rows"][0]["missing_regions"], [])
        self.assertTrue(panel["rows"][0]["is_evaluable_top3_panel"])

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
