import unittest

from app.services.media.cockpit.media_spending_truth import build_media_spending_truth


def _prediction(**overrides) -> dict:
    payload = {
        "bundesland": "NW",
        "bundesland_name": "Nordrhein-Westfalen",
        "virus_typ": "Influenza A",
        "horizon_days": 7,
        "event_probability": 0.78,
        "change_pct": 24.0,
        "current_known_incidence": 18.0,
        "expected_next_week_incidence": 23.0,
        "state_population_millions": 18.0,
        "regional_data_fresh": True,
        "coverage_blockers": [],
        "decision": {
            "stage": "activate",
            "forecast_confidence": 0.74,
            "source_freshness_score": 0.90,
            "usable_source_share": 0.90,
            "source_coverage_score": 0.90,
            "source_revision_risk": 0.10,
            "reason_trace": {"why": ["high surge probability"]},
        },
        "viral_pressure_features": {
            "budget_opportunity_score": 0.76,
            "wastewater_case_divergence": 0.30,
            "spatial_import_pressure": 0.40,
            "recent_saturation_score": 0.20,
            "saturation_factor": 0.80,
        },
    }
    payload.update(overrides)
    return payload


def _scoreboard(readiness: str = "go", blockers: list[str] | None = None, evaluable_weeks: int = 16) -> dict:
    return {
        "combined_by_virus": {
            "Influenza A": {
                "h7": {
                    "readiness": readiness,
                    "blockers": blockers or [],
                    "warnings": [],
                    "evaluable_weeks": evaluable_weeks,
                    "headline": {"ece": 0.03, "brier_score": 0.12},
                    "lift_vs_baseline_hit_rate": {"persistence_pp": 0.10},
                    "lift_vs_persistence": {"pr_auc_multiplier": 1.20, "precision_pp": 0.08},
                    "quality_gate": {"overall_passed": readiness == "go"},
                }
            }
        }
    }


class MediaSpendingTruthTests(unittest.TestCase):
    def test_hard_forecast_blockers_force_zero_delta(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction()],
            truth_scoreboard=_scoreboard("blocked", ["artifact_quality_gate_not_passed"]),
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.12},
        )

        region = payload["regions"][0]
        self.assertEqual(payload["global_status"], "blocked")
        self.assertEqual(region["media_spending_truth"], "blocked")
        self.assertEqual(region["recommended_delta_pct"], 0.0)
        self.assertIn("artifact_quality_gate_not_passed", region["limiting_factors"])

    def test_model_worse_than_persistence_cannot_increase_budget(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction()],
            truth_scoreboard=_scoreboard("blocked", ["hit_rate_not_better_than_persistence"], evaluable_weeks=16),
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.12},
        )

        region = payload["regions"][0]
        self.assertIn(region["media_spending_truth"], {"blocked", "watch_only"})
        self.assertNotEqual(region["recommended_action"], "increase")
        self.assertEqual(region["recommended_delta_pct"], 0.0)
        self.assertIn("model_not_better_than_persistence", region["reason_codes"])

    def test_promising_but_insufficient_evidence_is_planner_assist_only(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction()],
            truth_scoreboard=_scoreboard("candidate", ["too_few_evaluable_weeks"], evaluable_weeks=10),
            decision_backtest={"decision_backtest_passed": False, "regret_reduction_vs_static": 0.0},
        )

        region = payload["regions"][0]
        self.assertEqual(payload["global_status"], "planner_assist")
        self.assertEqual(region["media_spending_truth"], "preposition_approved")
        self.assertTrue(region["manual_approval_required"])
        self.assertLessEqual(region["max_delta_pct"], 5.0)
        self.assertIn("manual_approval_required", region["reason_codes"])


    def test_blocked_payload_exposes_gate_reason_matrix(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction(regional_data_fresh=False, coverage_blockers=["regional_data_stale"])],
            truth_scoreboard=_scoreboard("blocked", ["artifact_quality_gate_not_passed"], evaluable_weeks=16),
            decision_backtest={
                "decision_backtest_passed": False,
                "regret_reduction_vs_static": -0.02,
                "min_regret_reduction": 0.05,
            },
        )

        self.assertEqual(payload["global_status"], "blocked")
        self.assertIn("forecast_quality_gate_failed", payload["blocked_because"])
        self.assertIn("data_quality_insufficient_for_budget_shift", payload["blocked_because"])
        self.assertIn("decision_backtest_not_passed", payload["blocked_because"])
        self.assertEqual(payload["blockedBecause"], payload["blocked_because"])

        by_gate = {item["gate"]: item for item in payload["gate_evaluations"]}
        self.assertEqual(by_gate["forecast_quality"]["status"], "failed")
        self.assertEqual(by_gate["live_data_quality"]["status"], "failed")
        self.assertEqual(by_gate["decision_backtest"]["status"], "failed")
        self.assertIn("threshold", by_gate["decision_backtest"])
        self.assertIn("observed", by_gate["decision_backtest"])
        self.assertEqual(payload["gateEvaluations"], payload["gate_evaluations"])

    def test_golden_gate_matrix_blocks_good_forecast_when_decision_backtest_fails(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction()],
            truth_scoreboard=_scoreboard("go", [], evaluable_weeks=18),
            decision_backtest={"decision_backtest_passed": False, "regret_reduction_vs_static": -0.02},
        )

        region = payload["regions"][0]
        self.assertEqual(payload["global_status"], "blocked")
        self.assertIn("decision_backtest_not_passed", payload["blocked_because"])
        self.assertEqual(region["recommended_delta_pct"], 0.0)
        self.assertNotEqual(region["recommended_action"], "increase")

    def test_golden_gate_matrix_blocks_bad_live_data_even_when_backtest_passes(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction(regional_data_fresh=False, coverage_blockers=["regional_data_stale"])],
            truth_scoreboard=_scoreboard("go", [], evaluable_weeks=18),
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.12},
        )

        region = payload["regions"][0]
        self.assertEqual(payload["global_status"], "blocked")
        self.assertIn("data_quality_insufficient_for_budget_shift", payload["blocked_because"])
        self.assertEqual(region["media_spending_truth"], "blocked")
        self.assertEqual(region["recommended_delta_pct"], 0.0)


    def test_release_cascade_approved_exposes_shadow_and_approved_deltas(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[
                _prediction(),
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    event_probability=0.20,
                    change_pct=-8.0,
                    state_population_millions=13.0,
                    decision={"stage": "watch", "forecast_confidence": 0.70},
                    viral_pressure_features={"budget_opportunity_score": 0.18, "recent_saturation_score": 0.20},
                ),
            ],
            truth_scoreboard=_scoreboard("go", [], evaluable_weeks=18),
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.14},
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        nw = next(item for item in payload["regions"] if item["region_code"] == "NW")
        self.assertEqual(payload["release_mode"], "approved")
        self.assertEqual(payload["releaseMode"], "approved")
        self.assertEqual(payload["globalDecision"], "approved")
        self.assertEqual(payload["maxApprovedDeltaPct"], 15.0)
        self.assertGreater(nw["shadow_delta_pct"], 0.0)
        self.assertEqual(nw["approved_delta_pct"], nw["shadow_delta_pct"])
        self.assertEqual(nw["recommended_delta_pct"], nw["approved_delta_pct"])
        self.assertAlmostEqual(sum(item["approved_delta_pct"] for item in payload["regions"]), 0.0, places=6)
        self.assertTrue(all("severity" in item for item in payload["gateTrace"]))

    def test_release_cascade_limited_when_backtest_is_positive_but_uncertain(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[
                _prediction(),
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    event_probability=0.20,
                    change_pct=-8.0,
                    state_population_millions=13.0,
                    decision={"stage": "watch", "forecast_confidence": 0.70},
                    viral_pressure_features={"budget_opportunity_score": 0.18, "recent_saturation_score": 0.20},
                ),
            ],
            truth_scoreboard=_scoreboard("go", [], evaluable_weeks=18),
            decision_backtest={
                "decision_backtest_passed": False,
                "regret_reduction_vs_static": 0.01,
                "min_regret_reduction": 0.03,
                "evaluable_panel_weeks": 18,
                "verdict": "better_but_uncertain",
            },
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        nw = next(item for item in payload["regions"] if item["region_code"] == "NW")
        self.assertEqual(payload["release_mode"], "limited")
        self.assertEqual(payload["globalDecision"], "limited")
        self.assertEqual(payload["maxApprovedDeltaPct"], 5.0)
        self.assertGreater(nw["shadow_delta_pct"], nw["approved_delta_pct"])
        self.assertGreater(nw["approved_delta_pct"], 0.0)
        self.assertLessEqual(abs(nw["approved_delta_pct"]), 5.0)
        self.assertEqual(nw["executionStatus"], "limited")

    def test_release_cascade_shadow_only_when_evidence_is_insufficient(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[
                _prediction(),
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    event_probability=0.20,
                    change_pct=-8.0,
                    state_population_millions=13.0,
                    decision={"stage": "watch", "forecast_confidence": 0.70},
                    viral_pressure_features={"budget_opportunity_score": 0.18, "recent_saturation_score": 0.20},
                ),
            ],
            truth_scoreboard=_scoreboard("candidate", ["too_few_evaluable_weeks"], evaluable_weeks=10),
            decision_backtest={
                "decision_backtest_passed": False,
                "regret_reduction_vs_static": 0.0,
                "evaluable_panel_weeks": 6,
                "verdict": "not_enough_data",
            },
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        nw = next(item for item in payload["regions"] if item["region_code"] == "NW")
        self.assertEqual(payload["release_mode"], "shadow_only")
        self.assertEqual(payload["globalDecision"], "shadow_only")
        self.assertEqual(payload["maxApprovedDeltaPct"], 0.0)
        self.assertGreater(nw["shadow_delta_pct"], 0.0)
        self.assertEqual(nw["approved_delta_pct"], 0.0)
        self.assertEqual(nw["recommended_delta_pct"], 0.0)
        by_gate = {item["gate"]: item for item in payload["gateTrace"]}
        self.assertIn("insufficient_evidence", {by_gate["forecast_quality"]["status"], by_gate["decision_backtest"]["status"]})

    def test_regional_data_problem_blocks_only_that_region_when_enough_regions_remain(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[
                _prediction(),
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    event_probability=0.20,
                    change_pct=-8.0,
                    state_population_millions=13.0,
                    decision={"stage": "watch", "forecast_confidence": 0.70},
                    viral_pressure_features={"budget_opportunity_score": 0.18, "recent_saturation_score": 0.20},
                ),
                _prediction(
                    bundesland="SN",
                    bundesland_name="Sachsen",
                    event_probability=0.80,
                    change_pct=30.0,
                    regional_data_fresh=False,
                    coverage_blockers=["regional_data_stale"],
                    viral_pressure_features={"budget_opportunity_score": 0.90, "recent_saturation_score": 0.20},
                ),
            ],
            truth_scoreboard=_scoreboard("go", [], evaluable_weeks=18),
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.14},
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0, "SN": 10000.0},
        )

        sn = next(item for item in payload["regions"] if item["region_code"] == "SN")
        self.assertEqual(payload["release_mode"], "approved")
        self.assertEqual(sn["executionStatus"], "blocked")
        self.assertEqual(sn["approved_delta_pct"], 0.0)
        by_gate = {item["gate"]: item for item in payload["gateTrace"]}
        self.assertEqual(by_gate["live_data_quality"]["status"], "warning")


    def test_forecast_quality_gate_exposes_component_diagnostics_and_engine_version(self) -> None:
        scoreboard = _scoreboard("blocked", ["ece_fail"], evaluable_weeks=18)
        card = scoreboard["combined_by_virus"]["Influenza A"]["h7"]
        card["quality_gate"] = {
            "overall_passed": False,
            "components": {
                "valid_region_share": {"observed": 0.94, "threshold": 0.75, "direction": "higher_is_better"},
                "directional_accuracy": {"observed": 0.71, "threshold": 0.60, "direction": "higher_is_better"},
                "rank_quality": {"observed": 0.48, "threshold": 0.50, "direction": "higher_is_better"},
                "persistence_uplift": {"observed": 0.04, "threshold": 0.00, "direction": "higher_is_better"},
                "calibration_error": {"observed": 0.23, "threshold": 0.15, "direction": "lower_is_better"},
            },
        }

        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction(), _prediction(bundesland="BY", bundesland_name="Bayern", event_probability=0.20, change_pct=-8.0, viral_pressure_features={"budget_opportunity_score": 0.18})],
            truth_scoreboard=scoreboard,
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.14},
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        by_gate = {item["gate"]: item for item in payload["gateTrace"]}
        forecast_gate = by_gate["forecast_quality"]
        self.assertEqual(payload["engine_version"], "media_spending_truth_v1_2")
        self.assertIn("components", forecast_gate)
        self.assertEqual(forecast_gate["components"]["calibration_error"]["status"], "failed")
        self.assertEqual(forecast_gate["components"]["calibration_error"]["direction"], "lower_is_better")
        self.assertEqual(forecast_gate["components"]["valid_region_share"]["status"], "passed")

    def test_calibration_only_forecast_warning_allows_limited_release_when_decision_backtest_passes(self) -> None:
        scoreboard = _scoreboard("blocked", ["ece_fail"], evaluable_weeks=18)
        card = scoreboard["combined_by_virus"]["Influenza A"]["h7"]
        card["quality_gate"] = {
            "overall_passed": False,
            "components": {
                "valid_region_share": {"observed": 1.0, "threshold": 0.75, "direction": "higher_is_better"},
                "forecast_freshness": {"observed": 1.0, "threshold": 0.80, "direction": "higher_is_better"},
                "directional_accuracy": {"observed": 0.74, "threshold": 0.55, "direction": "higher_is_better"},
                "rank_quality": {"observed": 0.62, "threshold": 0.50, "direction": "higher_is_better"},
                "persistence_uplift": {"observed": 0.05, "threshold": 0.00, "direction": "higher_is_better"},
                "calibration_error": {"observed": 0.23, "threshold": 0.15, "direction": "lower_is_better"},
            },
        }

        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[
                _prediction(),
                _prediction(bundesland="BY", bundesland_name="Bayern", event_probability=0.20, change_pct=-8.0, viral_pressure_features={"budget_opportunity_score": 0.18}),
            ],
            truth_scoreboard=scoreboard,
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.14},
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        nw = next(item for item in payload["regions"] if item["region_code"] == "NW")
        by_gate = {item["gate"]: item for item in payload["gateTrace"]}
        self.assertEqual(by_gate["forecast_quality"]["status"], "warning")
        self.assertEqual(by_gate["forecast_quality"]["severity"], "limited")
        self.assertEqual(payload["release_mode"], "limited")
        self.assertGreater(nw["shadow_delta_pct"], nw["approved_delta_pct"])
        self.assertGreater(nw["approved_delta_pct"], 0.0)
        self.assertLessEqual(abs(nw["approved_delta_pct"]), 5.0)

    def test_directional_or_persistence_forecast_component_failure_remains_blocked(self) -> None:
        scoreboard = _scoreboard("blocked", [], evaluable_weeks=18)
        card = scoreboard["combined_by_virus"]["Influenza A"]["h7"]
        card["quality_gate"] = {
            "overall_passed": False,
            "components": {
                "valid_region_share": {"observed": 1.0, "threshold": 0.75, "direction": "higher_is_better"},
                "forecast_freshness": {"observed": 1.0, "threshold": 0.80, "direction": "higher_is_better"},
                "directional_accuracy": {"observed": 0.40, "threshold": 0.55, "direction": "higher_is_better"},
                "rank_quality": {"observed": 0.62, "threshold": 0.50, "direction": "higher_is_better"},
                "persistence_uplift": {"observed": 0.03, "threshold": 0.00, "direction": "higher_is_better"},
                "calibration_error": {"observed": 0.08, "threshold": 0.15, "direction": "lower_is_better"},
            },
        }

        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[_prediction(), _prediction(bundesland="BY", bundesland_name="Bayern", event_probability=0.20, change_pct=-8.0, viral_pressure_features={"budget_opportunity_score": 0.18})],
            truth_scoreboard=scoreboard,
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.14},
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        by_gate = {item["gate"]: item for item in payload["gateTrace"]}
        self.assertEqual(payload["release_mode"], "blocked")
        self.assertEqual(by_gate["forecast_quality"]["status"], "failed")
        self.assertEqual(by_gate["forecast_quality"]["severity"], "hard")
        self.assertEqual(by_gate["forecast_quality"]["components"]["directional_accuracy"]["status"], "failed")

    def test_passed_gates_allow_increase_approved_with_reason_codes(self) -> None:
        payload = build_media_spending_truth(
            virus_typ="Influenza A",
            horizon_days=7,
            predictions=[
                _prediction(),
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    event_probability=0.20,
                    change_pct=-8.0,
                    state_population_millions=13.0,
                    decision={
                        "stage": "watch",
                        "forecast_confidence": 0.70,
                        "source_freshness_score": 0.90,
                        "usable_source_share": 0.90,
                        "source_coverage_score": 0.90,
                        "source_revision_risk": 0.10,
                    },
                    viral_pressure_features={
                        "budget_opportunity_score": 0.18,
                        "wastewater_case_divergence": -0.10,
                        "spatial_import_pressure": 0.10,
                        "recent_saturation_score": 0.20,
                        "saturation_factor": 0.80,
                    },
                ),
            ],
            truth_scoreboard=_scoreboard("go", [], evaluable_weeks=18),
            decision_backtest={"decision_backtest_passed": True, "regret_reduction_vs_static": 0.14},
            base_budget_by_region={"NW": 10000.0, "BY": 10000.0},
        )

        region = next(item for item in payload["regions"] if item["region_code"] == "NW")
        self.assertEqual(payload["schema_version"], "media_spending_truth_v1")
        self.assertEqual(payload["global_status"], "spendable")
        self.assertEqual(region["media_spending_truth"], "increase_approved")
        self.assertEqual(region["recommended_action"], "increase")
        self.assertGreater(region["recommended_delta_pct"], 0.0)
        self.assertLessEqual(region["recommended_delta_pct"], 15.0)
        self.assertIn("high_surge_probability", region["reason_codes"])


if __name__ == "__main__":
    unittest.main()
