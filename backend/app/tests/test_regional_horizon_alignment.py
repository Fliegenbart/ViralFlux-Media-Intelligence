import unittest

from app.services.ml.regional_horizon_alignment import classify_horizon_alignment


class RegionalHorizonAlignmentTests(unittest.TestCase):
    def test_confirmed_requires_h5_rise_and_fresh_h7_support(self) -> None:
        h5 = {
            "increase_detected": True,
            "change_pct": 24.0,
            "budget_release_status": "candidate_only",
            "blockers": ["business_validation_missing"],
        }
        h7 = {
            "decision": {"stage": "activate"},
            "decision_label": "Activate",
            "regional_data_fresh": True,
            "coverage_blockers": [],
            "change_pct": 18.0,
            "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
        }

        result = classify_horizon_alignment(h5, h7)

        self.assertEqual(result["alignment_status"], "confirmed_direction")
        self.assertEqual(result["statistical_read"], "H5 kurzfristig hoch, H7 frisch bestaetigt die Richtung.")
        self.assertEqual(result["budget_read"], "Kandidat, aber Budgetfreigabe bleibt an Business- und Spend-Gates gekoppelt.")
        self.assertTrue(result["h5_rise"])
        self.assertTrue(result["h7_support"])
        self.assertEqual(result["media_action"], "controlled_shift_candidate")
        self.assertEqual(result["budget_permission"], "blocked_until_business_truth")
        self.assertEqual(result["risk_level"], "medium")

    def test_stale_h7_blocks_alignment_even_when_h5_rises(self) -> None:
        h5 = {
            "increase_detected": True,
            "change_pct": 31.0,
            "budget_release_status": "candidate_only",
            "blockers": [],
        }
        h7 = {
            "decision": {"stage": "activate"},
            "decision_label": "Activate",
            "regional_data_fresh": False,
            "coverage_blockers": ["regional_data_stale"],
            "change_pct": 42.0,
            "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
        }

        result = classify_horizon_alignment(h5, h7)

        self.assertEqual(result["alignment_status"], "coverage_blocked")
        self.assertEqual(result["budget_read"], "Keine Budgetfreigabe; erst Datenfrische reparieren.")
        self.assertTrue(result["h5_rise"])
        self.assertFalse(result["h7_support"])
        self.assertEqual(result["media_action"], "do_not_shift")
        self.assertEqual(result["budget_permission"], "blocked")
        self.assertEqual(result["risk_level"], "high")

    def test_weekly_building_is_prepare_not_budget_shift(self) -> None:
        h5 = {
            "increase_detected": False,
            "change_pct": 3.0,
            "blockers": [],
        }
        h7 = {
            "decision": {"stage": "prepare"},
            "regional_data_fresh": True,
            "quality_gate": {"overall_passed": True},
            "change_pct": 16.0,
        }

        result = classify_horizon_alignment(h5, h7)

        self.assertEqual(result["alignment_status"], "weekly_building")
        self.assertEqual(result["media_action"], "prepare_watchlist")
        self.assertEqual(result["budget_permission"], "blocked_until_h5_or_business_truth")
        self.assertEqual(result["risk_level"], "medium_high")

    def test_h7_without_regional_data_fresh_blocks_alignment(self) -> None:
        h5 = {
            "increase_detected": True,
            "change_pct": 24.0,
            "blockers": [],
        }
        h7 = {
            "decision": {"stage": "activate"},
            "quality_gate": {"overall_passed": True},
            "change_pct": 18.0,
        }

        result = classify_horizon_alignment(h5, h7)

        self.assertEqual(result["alignment_status"], "coverage_blocked")
        self.assertFalse(result["h7_support"])
        self.assertIn("regional_data_fresh_missing", result["blockers"])
        self.assertEqual(result["media_action"], "do_not_shift")
        self.assertEqual(result["budget_permission"], "blocked")

    def test_h7_quality_gate_failure_is_reported_as_blocker(self) -> None:
        h5 = {
            "increase_detected": True,
            "change_pct": 24.0,
            "blockers": [],
        }
        h7 = {
            "decision": {"stage": "activate"},
            "regional_data_fresh": True,
            "quality_gate": {"overall_passed": False},
            "change_pct": 18.0,
        }

        result = classify_horizon_alignment(h5, h7)

        self.assertFalse(result["h7_support"])
        self.assertIn("h7_quality_gate_not_passed", result["blockers"])

    def test_missing_h5_is_reported_when_h7_is_present(self) -> None:
        h7 = {
            "decision": {"stage": "activate"},
            "regional_data_fresh": True,
            "quality_gate": {"overall_passed": True},
            "change_pct": 18.0,
        }

        result = classify_horizon_alignment(None, h7)

        self.assertFalse(result["h5_rise"])
        self.assertTrue(result["h7_support"])
        self.assertIn("h5_missing", result["blockers"])


if __name__ == "__main__":
    unittest.main()
