import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.marketing import router as marketing_router
from app.core.security import create_access_token
from app.db.session import get_db


class _DummyDb:
    pass


class MarketingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()

        def override_get_db():
            try:
                yield _DummyDb()
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(marketing_router, prefix="/api/v1/marketing")
        self.app = app
        self.client = TestClient(app)
        self.user_headers = self._auth_headers("user")

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def _auth_headers(self, role: str) -> dict[str, str]:
        token = create_access_token(
            data={"sub": f"{role}@example.com", "role": role},
            expires_delta=timedelta(minutes=15),
        )
        return {"Authorization": f"Bearer {token}"}

    def test_export_crm_requires_authentication(self) -> None:
        response = self.client.post("/api/v1/marketing/export/crm")
        self.assertEqual(response.status_code, 401)

    def test_export_crm_rejects_get_requests(self) -> None:
        response = self.client.get("/api/v1/marketing/export/crm", headers=self.user_headers)
        self.assertEqual(response.status_code, 405)

    def test_export_crm_uses_post_and_marks_requested_ids(self) -> None:
        payload = {"meta": {"total_opportunities": 2}, "opportunities": []}
        with patch(
            "app.services.marketing_engine.opportunity_engine.MarketingOpportunityEngine"
        ) as engine_cls:
            engine_cls.return_value.export_crm_json.return_value = payload
            response = self.client.post(
                "/api/v1/marketing/export/crm?ids=opp-1,opp-2",
                headers=self.user_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        engine_cls.return_value.export_crm_json.assert_called_once_with(
            opportunity_ids=["opp-1", "opp-2"]
        )


if __name__ == "__main__":
    unittest.main()
