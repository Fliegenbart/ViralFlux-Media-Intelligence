import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_admin, get_current_user
from app.api.media_contracts import OutcomeImportRequest
from app.api.media_routes_outcomes import router as outcomes_router
from app.api.media_routes_weekly_brief import router as weekly_brief_router
from app.db.session import get_db
from app.models.database import Base
from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.outcome_signal_service import OutcomeSignalService
from app.services.media.v2_service import MediaV2Service
from app.services.media.weekly_brief_service import WeeklyBriefService


class MediaBrandContractTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()

        def override_get_db():
            try:
                yield None
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: {"role": "user"}
        app.dependency_overrides[get_current_admin] = lambda: {"role": "admin"}
        app.include_router(outcomes_router, prefix="/api/v1/media")
        app.include_router(weekly_brief_router, prefix="/api/v1/media")
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_outcome_import_request_requires_explicit_brand(self) -> None:
        with self.assertRaises(ValidationError):
            OutcomeImportRequest(
                source_label="manual",
                validate_only=True,
                records=[],
            )

    def test_decision_endpoint_requires_explicit_brand_query(self) -> None:
        response = self.client.get("/api/v1/media/decision?virus_typ=Influenza%20A")

        self.assertEqual(response.status_code, 422)

    def test_outcomes_coverage_requires_explicit_brand_query(self) -> None:
        response = self.client.get("/api/v1/media/outcomes/coverage?virus_typ=Influenza%20A")

        self.assertEqual(response.status_code, 422)

    def test_weekly_brief_generate_requires_explicit_brand_query(self) -> None:
        response = self.client.post("/api/v1/media/weekly-brief/generate?virus_typ=Influenza%20A")

        self.assertEqual(response.status_code, 422)

    def test_decision_endpoint_accepts_explicit_brand_query(self) -> None:
        with patch("app.api.media_routes_weekly_brief.MediaV2Service") as service_cls:
            service_cls.return_value.get_decision_payload.return_value = {
                "brand": "acme",
                "decision": "watch",
            }
            response = self.client.get(
                "/api/v1/media/decision?brand=acme&virus_typ=Influenza%20A"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"brand": "acme", "decision": "watch"})
        service_cls.return_value.get_decision_payload.assert_called_once_with(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
            brand="acme",
        )

    def test_weekly_brief_generate_accepts_explicit_brand_query(self) -> None:
        with patch.object(
            WeeklyBriefService,
            "generate",
            return_value={
                "calendar_week": "2026-W15",
                "pages": 3,
                "summary": {"brand": "acme"},
            },
        ) as mocked_generate:
            response = self.client.post(
                "/api/v1/media/weekly-brief/generate?brand=acme&virus_typ=Influenza%20A"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["calendar_week"], "2026-W15")
        mocked_generate.assert_called_once_with(brand="acme", virus_typ="Influenza A")


class MediaBrandScopedServiceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MediaV2Service(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_brand_scoped_service_methods_require_explicit_brand(self) -> None:
        brand_scoped_calls = [
            ("get_decision_payload", {"virus_typ": "Influenza A"}),
            ("get_regions_payload", {"virus_typ": "Influenza A"}),
            ("get_campaigns_payload", {"limit": 10}),
            ("get_evidence_payload", {"virus_typ": "Influenza A"}),
            ("get_truth_coverage", {"virus_typ": "Influenza A"}),
            ("get_truth_evidence", {"virus_typ": "Influenza A"}),
            ("list_outcome_import_batches", {"limit": 10}),
            ("_campaign_cards", {"limit": 10}),
        ]

        for method_name, kwargs in brand_scoped_calls:
            with self.subTest(method=method_name):
                method = getattr(self.service, method_name)
                with self.assertRaises(TypeError):
                    method(**kwargs)

        with self.assertRaises(TypeError):
            self.service.import_outcomes(
                source_label="manual_csv",
                records=[],
            )


class MediaInternalBrandContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.outcome_signal_service = OutcomeSignalService(self.db)
        self.business_validation_service = BusinessValidationService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_internal_brand_services_require_explicit_brand(self) -> None:
        with self.assertRaises(TypeError):
            self.outcome_signal_service.build_learning_bundle()

        with self.assertRaises(TypeError):
            self.business_validation_service.evaluate()

    def test_internal_brand_services_reject_blank_brand(self) -> None:
        with self.assertRaises(ValueError):
            self.outcome_signal_service.build_learning_bundle(brand="   ")

        with self.assertRaises(ValueError):
            self.business_validation_service.evaluate(brand="   ")


if __name__ == "__main__":
    unittest.main()
