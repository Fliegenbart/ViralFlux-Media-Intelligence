import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.media import router
from app.db.session import get_db
from app.models.database import Base


class MediaV2ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

        app = FastAPI()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(router, prefix="/api/v1/media")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_outcome_import_and_coverage_endpoints(self) -> None:
        import_response = self.client.post(
            "/api/v1/media/outcomes/import",
            json={
                "brand": "gelo",
                "source_label": "manual",
                "records": [
                    {
                        "week_start": "2026-02-02T00:00:00",
                        "product": "GeloProsed",
                        "region_code": "SH",
                        "media_spend_eur": 12000,
                        "sales_units": 140,
                    }
                ],
            },
        )

        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json()["imported"], 1)

        coverage_response = self.client.get("/api/v1/media/outcomes/coverage?brand=gelo")

        self.assertEqual(coverage_response.status_code, 200)
        body = coverage_response.json()
        self.assertEqual(body["coverage_weeks"], 1)
        self.assertEqual(body["trust_readiness"], "erste_signale")


if __name__ == "__main__":
    unittest.main()
