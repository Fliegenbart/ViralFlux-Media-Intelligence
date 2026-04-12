import unittest
from datetime import datetime

from app.services.ml.regional_forecast_truth import fallback_truth_assessment


class RegionalForecastTruthTests(unittest.TestCase):
    def test_fallback_truth_assessment_rejects_blank_brand(self) -> None:
        with self.assertRaises(ValueError):
            fallback_truth_assessment(
                brand="   ",
                region_code="SH",
                product="GeloProsed",
                window_start=datetime(2026, 1, 1),
                window_end=datetime(2026, 1, 8),
                signal_context={"signal_present": True, "confidence": 0.7},
                source_mode="forecast_only",
                message="missing truth",
            )


if __name__ == "__main__":
    unittest.main()
