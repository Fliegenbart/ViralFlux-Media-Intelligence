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


if __name__ == "__main__":
    unittest.main()
