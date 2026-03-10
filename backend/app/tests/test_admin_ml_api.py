import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.admin_ml import router
from app.api.deps import get_current_admin
from app.core.rate_limit import limiter
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES


class AdminMLApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.dependency_overrides[get_current_admin] = lambda: {"role": "admin"}
        app.include_router(router, prefix="/api/v1/admin/ml")
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_empty_request_normalizes_to_all_supported_viruses(self) -> None:
        with patch(
            "app.services.ml.tasks.train_xgboost_model_task.delay",
            return_value=SimpleNamespace(id="task-all"),
        ) as delay_mock:
            response = self.client.post("/api/v1/admin/ml/train-xgboost", json={})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["virus_types"], list(SUPPORTED_VIRUS_TYPES))
        self.assertEqual(response.json()["selection_mode"], "all")
        self.assertIsNone(response.json()["virus_typ"])
        delay_mock.assert_called_once_with(
            virus_types=list(SUPPORTED_VIRUS_TYPES),
            include_internal_history=True,
            research_mode=False,
        )

    def test_single_virus_request_uses_canonical_name(self) -> None:
        with patch(
            "app.services.ml.tasks.train_xgboost_model_task.delay",
            return_value=SimpleNamespace(id="task-single"),
        ) as delay_mock:
            response = self.client.post(
                "/api/v1/admin/ml/train-xgboost",
                json={
                    "virus_typ": "influenza a",
                    "include_internal_history": False,
                    "research_mode": True,
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["virus_typ"], "Influenza A")
        self.assertEqual(response.json()["virus_types"], ["Influenza A"])
        self.assertEqual(response.json()["selection_mode"], "single")
        delay_mock.assert_called_once_with(
            virus_types=["Influenza A"],
            include_internal_history=False,
            research_mode=True,
        )

    def test_subset_request_is_normalized_and_ordered(self) -> None:
        with patch(
            "app.services.ml.tasks.train_xgboost_model_task.delay",
            return_value=SimpleNamespace(id="task-subset"),
        ) as delay_mock:
            response = self.client.post(
                "/api/v1/admin/ml/train-xgboost",
                json={"virus_types": ["RSV A", "Influenza A"]},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["virus_types"], ["Influenza A", "RSV A"])
        self.assertEqual(response.json()["selection_mode"], "subset")
        delay_mock.assert_called_once_with(
            virus_types=["Influenza A", "RSV A"],
            include_internal_history=True,
            research_mode=False,
        )

    def test_invalid_selection_payloads_return_422(self) -> None:
        invalid_payloads = [
            {"virus_typ": "Influenza A", "virus_types": ["Influenza B"]},
            {"virus_types": []},
            {"virus_typ": "Norovirus"},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/v1/admin/ml/train-xgboost",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
