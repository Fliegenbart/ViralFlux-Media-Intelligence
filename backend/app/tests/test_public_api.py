import os
import unittest

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.api.public_api import obfuscate_result


class PublicApiSemanticsTests(unittest.TestCase):
    def test_obfuscate_result_returns_signal_contract_without_trend_or_confidence(self) -> None:
        payload = obfuscate_result(
            {
                "decision_priority_index": 72.4,
                "reliability_label": "Hoch",
                "component_scores": {
                    "wastewater": 0.91,
                    "search_trends": 0.42,
                    "environment": 0.23,
                },
            }
        ).model_dump()

        self.assertEqual(payload["prediction"]["signal_index"], 72)
        self.assertEqual(payload["prediction"]["signal_level"], "HIGH")
        self.assertNotIn("confidence_level", payload["prediction"])
        self.assertNotIn("primary_driver", payload["explanation"])
        self.assertIn("signal_factors", payload["explanation"])
        self.assertNotIn("contributing_factors", payload["explanation"])
        self.assertEqual(payload["explanation"]["signal_factors"][0]["factor"], "Wastewater Load")
        self.assertEqual(payload["explanation"]["signal_factors"][0]["signal_intensity"], "CRITICAL")
        self.assertNotIn("trend", payload["explanation"]["signal_factors"][0])
        self.assertNotIn("copyright", payload["meta"])


if __name__ == "__main__":
    unittest.main()
