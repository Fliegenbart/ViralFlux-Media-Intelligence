import unittest

from app.models.database import OutbreakScore


class DatabaseModelSemanticsTests(unittest.TestCase):
    def test_outbreak_score_model_uses_signal_semantics_on_python_side(self) -> None:
        row = OutbreakScore(
            decision_signal_index=72.5,
            signal_level="HIGH",
            signal_source="forecast_decision_service",
            reliability_label="Hoch",
            reliability_score=0.81,
        )

        self.assertEqual(row.decision_signal_index, 72.5)
        self.assertEqual(row.signal_level, "HIGH")
        self.assertEqual(row.signal_source, "forecast_decision_service")
        self.assertEqual(row.reliability_label, "Hoch")
        self.assertEqual(row.reliability_score, 0.81)
        self.assertFalse(hasattr(row, "final_risk_score"))
        self.assertFalse(hasattr(row, "risk_level"))
        self.assertFalse(hasattr(row, "leading_indicator"))
        self.assertFalse(hasattr(row, "confidence_level"))
        self.assertFalse(hasattr(row, "confidence_numeric"))


if __name__ == "__main__":
    unittest.main()
