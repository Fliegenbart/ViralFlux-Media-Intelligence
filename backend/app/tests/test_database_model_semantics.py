import unittest
from datetime import datetime

from app.models.database import OutbreakScore
from app.schemas.outbreak_score import OutbreakScoreResponse


class DatabaseModelSemanticsTests(unittest.TestCase):
    def test_outbreak_score_model_uses_decision_priority_index_on_python_side(self) -> None:
        row = OutbreakScore(
            decision_priority_index=72.5,
            signal_level="HIGH",
            signal_source="forecast_decision_service",
            reliability_label="Hoch",
            reliability_score=0.81,
        )

        self.assertEqual(row.decision_priority_index, 72.5)
        self.assertEqual(row.signal_level, "HIGH")
        self.assertEqual(row.signal_source, "forecast_decision_service")
        self.assertEqual(row.reliability_label, "Hoch")
        self.assertEqual(row.reliability_score, 0.81)
        self.assertFalse(hasattr(row, "decision_signal_index"))
        self.assertFalse(hasattr(row, "final_risk_score"))
        self.assertFalse(hasattr(row, "risk_level"))
        self.assertFalse(hasattr(row, "leading_indicator"))
        self.assertFalse(hasattr(row, "confidence_level"))
        self.assertFalse(hasattr(row, "confidence_numeric"))

    def test_outbreak_score_response_serializes_new_field_name(self) -> None:
        row = OutbreakScore(
            id=1,
            datum=datetime(2026, 4, 11, 12, 0, 0),
            virus_typ="Influenza A",
            decision_priority_index=72.5,
            signal_level="HIGH",
            signal_source="forecast_decision_service",
            reliability_label="Hoch",
            reliability_score=0.81,
        )
        row.created_at = datetime(2026, 4, 11, 12, 5, 0)

        payload = OutbreakScoreResponse.model_validate(row).model_dump()

        self.assertEqual(payload["decision_priority_index"], 72.5)
        self.assertNotIn("decision_signal_index", payload)


if __name__ == "__main__":
    unittest.main()
