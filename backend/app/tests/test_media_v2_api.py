import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.media import router
from app.db.session import get_db
from app.models.database import Base, BrandProduct, WastewaterAggregated


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
        self._seed_products_and_truth_reference()

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

    def _seed_products_and_truth_reference(self) -> None:
        now = datetime.utcnow()
        self.db.add_all([
            BrandProduct(
                brand="gelo",
                product_name="GeloProsed",
                source_url="manual://seed",
                source_hash="seed-geloprosed",
                active=True,
                created_at=now,
                updated_at=now,
            ),
            BrandProduct(
                brand="gelo",
                product_name="GeloRevoice",
                source_url="manual://seed",
                source_hash="seed-gelorevoice",
                active=True,
                created_at=now,
                updated_at=now,
            ),
            WastewaterAggregated(
                datum=datetime(2026, 2, 16),
                available_time=datetime(2026, 2, 16),
                virus_typ="Influenza A",
                n_standorte=12,
                anteil_bev=0.6,
                viruslast=1.2,
                viruslast_normalisiert=58.0,
            ),
        ])
        self.db.commit()

    def test_outcome_import_validate_history_and_template_endpoints(self) -> None:
        validate_response = self.client.post(
            "/api/v1/media/outcomes/import",
            json={
                "brand": "gelo",
                "source_label": "manual",
                "validate_only": True,
                "file_name": "truth.csv",
                "csv_payload": (
                    "week_start,product,region_code,media_spend_eur,sales_units\n"
                    "2026-02-02,GeloProsed,SH,12000,140\n"
                    "2026-02-09,GeloRevoice,Hamburg,9000,90\n"
                ),
            },
        )

        self.assertEqual(validate_response.status_code, 200)
        validate_body = validate_response.json()
        self.assertTrue(validate_body["preview_only"])
        self.assertEqual(validate_body["batch_summary"]["status"], "validated")
        batch_id = validate_body["batch_id"]

        batch_detail_response = self.client.get(f"/api/v1/media/outcomes/import-batches/{batch_id}")
        self.assertEqual(batch_detail_response.status_code, 200)
        self.assertEqual(batch_detail_response.json()["batch"]["batch_id"], batch_id)

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

        coverage_response = self.client.get("/api/v1/media/outcomes/coverage?brand=gelo&virus_typ=Influenza%20A")
        self.assertEqual(coverage_response.status_code, 200)
        coverage_body = coverage_response.json()
        self.assertEqual(coverage_body["coverage_weeks"], 1)
        self.assertIn("Media Spend", coverage_body["required_fields_present"])
        self.assertEqual(coverage_body["truth_freshness_state"], "fresh")

        truth_response = self.client.get("/api/v1/media/evidence/truth?brand=gelo&virus_typ=Influenza%20A")
        self.assertEqual(truth_response.status_code, 200)
        truth_body = truth_response.json()
        self.assertIn("recent_batches", truth_body)
        self.assertIn("coverage", truth_body)

        list_response = self.client.get("/api/v1/media/outcomes/import-batches?brand=gelo")
        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(len(list_response.json()["batches"]), 2)

        template_response = self.client.get("/api/v1/media/outcomes/template")
        self.assertEqual(template_response.status_code, 200)
        self.assertIn("week_start,product,region_code,media_spend_eur", template_response.text)


if __name__ == "__main__":
    unittest.main()
