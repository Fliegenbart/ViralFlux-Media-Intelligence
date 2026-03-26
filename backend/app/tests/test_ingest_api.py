import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ingest import router
from app.core.security import create_access_token
from app.db.session import get_db


class IngestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()

        def override_get_db():
            try:
                yield None
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(router, prefix="/api/v1/ingest")
        self.app = app
        self.client = TestClient(app)
        self.admin_headers = self._auth_headers(role="admin")
        self.user_headers = self._auth_headers(role="user")

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def _auth_headers(self, role: str = "admin") -> dict[str, str]:
        token = create_access_token(
            data={"sub": f"{role}@example.com", "role": role},
            expires_delta=timedelta(minutes=15),
        )
        return {"Authorization": f"Bearer {token}"}

    def test_ingest_trigger_requires_authentication(self) -> None:
        response = self.client.post("/api/v1/ingest/run-all", json={})

        self.assertEqual(response.status_code, 401)

    def test_ingest_trigger_forbids_non_admin_users(self) -> None:
        response = self.client.post(
            "/api/v1/ingest/run-all",
            json={},
            headers=self.user_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Not enough privileges")

    def test_ingest_trigger_allows_admin_users(self) -> None:
        with patch("app.api.ingest._enqueue_full_ingestion", return_value="task-123"):
            response = self.client.post(
                "/api/v1/ingest/run-all",
                json={"region_code": "ALL"},
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["task_id"], "task-123")
        self.assertEqual(response.json()["status_url"], "/api/v1/ingest/status/task-123")


if __name__ == "__main__":
    unittest.main()
