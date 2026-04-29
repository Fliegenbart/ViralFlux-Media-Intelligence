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
