import unittest
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dashboard import router as dashboard_router
from app.api.inventory import router as inventory_router
from app.api.recommendations import router as recommendations_router
from app.api.data_import import router as data_import_router
from app.api.outbreak_score import router as outbreak_score_router
from app.api.map_data import router as map_data_router
from app.api.ordering import router as ordering_router
from app.core.security import create_access_token
from app.db.session import get_db


class _DummyDb:
    def query(self, *_args, **_kwargs):
        return self

    def filter_by(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

    def first(self):
        return None

    @property
    def c(self):
        return self


class LegacyRouteAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()

        def override_get_db():
            try:
                yield _DummyDb()
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(dashboard_router, prefix="/api/v1/dashboard")
        app.include_router(inventory_router, prefix="/api/v1/inventory")
        app.include_router(recommendations_router, prefix="/api/v1/recommendations")
        app.include_router(data_import_router, prefix="/api/v1/data-import")
        app.include_router(outbreak_score_router, prefix="/api/v1/outbreak-score")
        app.include_router(map_data_router, prefix="/api/v1/map")
        app.include_router(ordering_router, prefix="/api/v1/ordering")
        self.app = app
        self.client = TestClient(app)
        self.admin_headers = self._auth_headers("admin")
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

    def test_dashboard_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/dashboard/overview")
        self.assertEqual(response.status_code, 401)

    def test_inventory_read_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/inventory/")
        self.assertEqual(response.status_code, 401)

    def test_inventory_update_requires_admin_role(self) -> None:
        response = self.client.post(
            "/api/v1/inventory/update",
            json={"test_typ": "PCR", "aktueller_bestand": 10},
            headers=self.user_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_recommendations_latest_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/recommendations/latest")
        self.assertEqual(response.status_code, 401)

    def test_recommendations_generate_requires_admin_role(self) -> None:
        response = self.client.post("/api/v1/recommendations/generate", headers=self.user_headers)
        self.assertEqual(response.status_code, 403)

    def test_data_import_history_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/data-import/history")
        self.assertEqual(response.status_code, 401)

    def test_data_import_preview_rejects_invalid_upload_type_for_admin(self) -> None:
        response = self.client.post(
            "/api/v1/data-import/preview?upload_type=lab_results",
            headers=self.admin_headers,
            files={"file": ("payload.bin", BytesIO(b"binary\x00payload"), "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Nur CSV oder Excel (.xlsx) Dateien erlaubt")

    def test_map_data_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/map/regional/Influenza%20A")
        self.assertEqual(response.status_code, 401)

    def test_ordering_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/ordering/stockout-analysis")
        self.assertEqual(response.status_code, 401)

    def test_outbreak_peix_score_stays_public_for_landing_without_internal_model_details(self) -> None:
        payload = {
            "national_score": 0.42,
            "national_band": "elevated",
            "national_impact_probability": 58.0,
            "score_semantics": "ranking_signal",
            "impact_probability_semantics": "ranking_signal",
            "impact_probability_deprecated": True,
            "virus_scores": {"Influenza A": {"epi_score": 0.5}},
            "context_signals": {"forecast": {"weight": 0.2}},
            "weights_source": "translated_lab_policy",
            "top_drivers": ["forecast"],
            "generated_at": "2026-04-08T10:00:00Z",
            "regions": {
                "BE": {
                    "region_code": "BE",
                    "region_name": "Berlin",
                    "score_0_100": 77.0,
                    "risk_band": "high",
                    "impact_probability": 84.0,
                    "score_semantics": "ranking_signal",
                    "impact_probability_semantics": "ranking_signal",
                    "impact_probability_deprecated": True,
                    "top_drivers": ["forecast"],
                    "layer_contributions": {"Forecast": 55.0},
                }
            },
        }
        with patch("app.api.outbreak_score.RankingSignalService.build", return_value=payload):
            response = self.client.get("/api/v1/outbreak-score/peix-score")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "national_score": 0.42,
                "national_band": "elevated",
                "national_impact_probability": 58.0,
                "score_semantics": "ranking_signal",
                "impact_probability_semantics": "ranking_signal",
                "impact_probability_deprecated": True,
                "generated_at": "2026-04-08T10:00:00Z",
                "regions": {
                    "BE": {
                        "region_code": "BE",
                        "region_name": "Berlin",
                        "score_0_100": 77.0,
                        "risk_band": "high",
                        "impact_probability": 84.0,
                        "score_semantics": "ranking_signal",
                        "impact_probability_semantics": "ranking_signal",
                        "impact_probability_deprecated": True,
                    }
                },
            },
        )

    def test_outbreak_peix_score_full_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/outbreak-score/peix-score/full")
        self.assertEqual(response.status_code, 401)

    def test_outbreak_history_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/outbreak-score/history")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
