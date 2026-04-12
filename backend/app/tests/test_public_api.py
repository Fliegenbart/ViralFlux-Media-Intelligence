import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.api import public_api as public_api_module
from app.api.public_api import obfuscate_result
from app.core.rate_limit import limiter
from app.db.session import get_db


class PublicApiSemanticsTests(unittest.TestCase):
    def test_obfuscate_result_returns_signal_contract_without_trend_or_confidence(self) -> None:
        payload = obfuscate_result(
            {
                "signal_index": 54.2,
                "decision_priority_index": 72.4,
                "reliability_label": "Hoch",
                "component_scores": {
                    "wastewater": 0.91,
                    "drug_shortage": 0.92,
                    "search_trends": 0.42,
                    "environment": 0.23,
                    "order_velocity": 0.99,
                },
            }
        ).model_dump()

        self.assertEqual(payload["prediction"]["signal_index"], 54)
        self.assertEqual(payload["prediction"]["signal_level"], "ELEVATED")
        self.assertNotIn("confidence_level", payload["prediction"])
        self.assertNotIn("primary_driver", payload["explanation"])
        self.assertIn("signal_factors", payload["explanation"])
        self.assertNotIn("contributing_factors", payload["explanation"])
        self.assertEqual(payload["explanation"]["signal_factors"][0]["factor"], "Wastewater Load")
        self.assertEqual(payload["explanation"]["signal_factors"][0]["signal_intensity"], "CRITICAL")
        self.assertEqual(
            [factor["factor"] for factor in payload["explanation"]["signal_factors"]],
            ["Wastewater Load", "Search Behavior", "Weather Conditions"],
        )
        self.assertNotIn("trend", payload["explanation"]["signal_factors"][0])
        self.assertNotIn("copyright", payload["meta"])


class PublicApiRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        limiter.reset()
        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        def override_get_db():
            try:
                yield None
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(public_api_module.router, prefix="/api/v1/public")
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()
        limiter.reset()

    def test_public_risk_rejects_unknown_virus(self) -> None:
        response = self.client.get(
            "/api/v1/public/risk",
            params={"virus": "not-a-virus"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Unsupported virus"})

    def test_public_risk_rejects_invalid_plz(self) -> None:
        response = self.client.get(
            "/api/v1/public/risk",
            params={"virus": "Influenza A", "plz": "abc"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Invalid PLZ"})

    def test_public_risk_uses_explicit_valid_virus_without_fallback(self) -> None:
        with patch(
            "app.services.ml.forecast_decision_service.ForecastDecisionService.build_legacy_outbreak_score",
            return_value={
                "decision_priority_index": 71.8,
                "component_scores": {"wastewater": 0.81},
            },
        ) as build_score:
            response = self.client.get(
                "/api/v1/public/risk",
                params={"virus": "RSV A", "plz": "10115"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["prediction"]["signal_index"], 72)
        build_score.assert_called_once_with(virus_typ="RSV A")


if __name__ == "__main__":
    unittest.main()
