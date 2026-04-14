from app.core.time import utc_now
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.media import router
from app.core.security import create_access_token
from app.db.schema_contracts import MLForecastSchemaMismatchError
from app.db.session import get_db
from app.models.database import Base, BrandProduct, MediaOutcomeImportBatch, MediaOutcomeRecord, OutcomeObservation, WastewaterAggregated


class MediaV2ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_m2m_secret = os.environ.get("M2M_SECRET_KEY")
        os.environ["M2M_SECRET_KEY"] = "test-m2m-secret"
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
        self.admin_headers = self._auth_headers(role="admin")
        self.user_headers = self._auth_headers(role="user")

    def tearDown(self) -> None:
        if self.previous_m2m_secret is None:
            os.environ.pop("M2M_SECRET_KEY", None)
        else:
            os.environ["M2M_SECRET_KEY"] = self.previous_m2m_secret
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _seed_products_and_truth_reference(self) -> None:
        now = utc_now()
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

    def _auth_headers(self, role: str = "admin") -> dict[str, str]:
        token = create_access_token(
            data={"sub": f"{role}@example.com", "role": role},
            expires_delta=timedelta(minutes=15),
        )
        return {"Authorization": f"Bearer {token}"}

    def test_media_read_endpoint_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/media/cockpit?virus_typ=Influenza%20A")

        self.assertEqual(response.status_code, 401)

    def test_media_admin_action_forbids_non_admin_users(self) -> None:
        response = self.client.post(
            "/api/v1/media/outcomes/import",
            json={
                "brand": "gelo",
                "source_label": "manual",
                "validate_only": True,
                "records": [],
            },
            headers=self.user_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Not enough privileges")

    def test_outcome_import_requires_explicit_brand(self) -> None:
        response = self.client.post(
            "/api/v1/media/outcomes/import",
            json={
                "source_label": "manual",
                "validate_only": True,
                "records": [],
            },
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 422)

    def test_decision_endpoint_defaults_brand_query_when_missing(self) -> None:
        with patch(
            "app.services.media.v2_service.MediaV2Service.get_decision_payload",
            return_value={"brand": "gelo", "generated_at": "2026-04-12T10:00:00Z"},
        ) as decision_mock:
            response = self.client.get(
                "/api/v1/media/decision?virus_typ=Influenza%20A",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 200)
        decision_mock.assert_called_once_with(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
            brand="gelo",
        )

    def test_campaigns_endpoint_defaults_brand_query_when_missing(self) -> None:
        with patch(
            "app.services.media.v2_service.MediaV2Service.get_campaigns_payload",
            return_value={"cards": [], "generated_at": "2026-04-12T10:00:00Z"},
        ) as campaigns_mock:
            response = self.client.get(
                "/api/v1/media/campaigns?limit=120",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 200)
        campaigns_mock.assert_called_once_with(brand="gelo", limit=120)

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
            headers=self.admin_headers,
        )

        self.assertEqual(validate_response.status_code, 200)
        validate_body = validate_response.json()
        self.assertTrue(validate_body["preview_only"])
        self.assertEqual(validate_body["batch_summary"]["status"], "validated")
        batch_id = validate_body["batch_id"]

        batch_detail_response = self.client.get(
            f"/api/v1/media/outcomes/import-batches/{batch_id}",
            headers=self.admin_headers,
        )
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
            headers=self.admin_headers,
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json()["imported"], 1)

        coverage_response = self.client.get(
            "/api/v1/media/outcomes/coverage?brand=gelo&virus_typ=Influenza%20A",
            headers=self.admin_headers,
        )
        self.assertEqual(coverage_response.status_code, 200)
        coverage_body = coverage_response.json()
        self.assertEqual(coverage_body["coverage_weeks"], 1)
        self.assertIn("Mediabudget", coverage_body["required_fields_present"])
        self.assertEqual(coverage_body["truth_freshness_state"], "fresh")

        truth_response = self.client.get(
            "/api/v1/media/evidence/truth?brand=gelo&virus_typ=Influenza%20A",
            headers=self.admin_headers,
        )
        self.assertEqual(truth_response.status_code, 200)
        truth_body = truth_response.json()
        self.assertIn("recent_batches", truth_body)
        self.assertIn("coverage", truth_body)

        list_response = self.client.get(
            "/api/v1/media/outcomes/import-batches?brand=gelo",
            headers=self.admin_headers,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(len(list_response.json()["batches"]), 2)

        template_response = self.client.get(
            "/api/v1/media/outcomes/template",
            headers=self.admin_headers,
        )
        self.assertEqual(template_response.status_code, 200)
        self.assertIn("week_start,product,region_code,media_spend_eur", template_response.text)

    def test_recommendation_list_exposes_outcome_learning_fields(self) -> None:
        now = datetime(2026, 3, 10)
        for index in range(30):
            self.db.add(
                MediaOutcomeRecord(
                    week_start=now - timedelta(days=7 * index),
                    brand="gelo",
                    product="GeloProsed",
                    region_code="SH",
                    media_spend_eur=10000 + index * 100,
                    sales_units=120 + index * 2,
                    qualified_visits=240 + index,
                    search_lift_index=18 + (index % 4),
                    source_label="manual",
                )
            )
        self.db.commit()

        opportunity = {
            "id": "opp-1",
            "status": "READY",
            "type": "activation",
            "urgency_score": 61.0,
            "brand": "gelo",
            "product": "GeloProsed",
            "recommended_product": "GeloProsed",
            "region_codes": ["SH"],
            "budget_shift_pct": 16.0,
            "channel_mix": {"programmatic": 35, "social": 30, "search": 20, "ctv": 15},
            "campaign_payload": {
                "message_framework": {"hero_message": "Norddeutschland priorisieren."},
                "channel_plan": [{"channel": "search", "share_pct": 40.0}],
                "guardrail_report": {"passed": True},
            },
            "campaign_preview": {
                "budget": {"weekly_budget_eur": 120000.0},
                "activation_window": {
                    "start": "2026-03-09T00:00:00",
                    "end": "2026-03-22T00:00:00",
                },
            },
            "condition_key": "erkaltung_akut",
        }

        with patch("app.api.media.MarketingOpportunityEngine.get_opportunities", return_value=[opportunity]):
            response = self.client.get(
                "/api/v1/media/recommendations/list?brand=gelo",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        card = body["cards"][0]
        self.assertIn("outcome_signal_score", card)
        self.assertIn("outcome_confidence_pct", card)
        self.assertEqual(card["learning_state"], "im_aufbau")

    def test_pilot_reporting_endpoint_returns_report_payload(self) -> None:
        expected_payload = {
            "brand": "gelo",
            "summary": {"total_recommendations": 2},
            "pilot_kpi_summary": {
                "hit_rate": {"value": 0.5, "assessed": 2},
            },
            "recommendation_history": [{"opportunity_id": "pilot-opp-sh"}],
            "activation_history": [],
            "region_evidence_view": [],
            "before_after_comparison": [],
            "methodology": {"version": "pilot_reporting_v1"},
        }

        with patch(
            "app.services.media.pilot_reporting_service.PilotReportingService.build_pilot_report",
            return_value=expected_payload,
        ) as mocked_build:
            response = self.client.get(
                "/api/v1/media/pilot-reporting?brand=gelo&lookback_weeks=12&region_code=SH&product=GeloProsed",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["total_recommendations"], 2)
        mocked_build.assert_called_once()

    def test_pilot_reporting_endpoint_maps_invalid_window_to_422(self) -> None:
        with patch(
            "app.services.media.pilot_reporting_service.PilotReportingService.build_pilot_report",
            side_effect=ValueError("window_end must be on or after window_start"),
        ):
            response = self.client.get(
                "/api/v1/media/pilot-reporting?brand=gelo&window_start=2026-03-31T00:00:00&window_end=2026-03-01T00:00:00",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "window_end must be on or after window_start")

    def test_pilot_readout_endpoint_returns_customer_contract(self) -> None:
        expected_payload = {
            "brand": "gelo",
            "run_context": {
                "forecast_readiness": "GO",
                "commercial_validation_status": "WATCH",
                "pilot_mode": "forecast_first",
                "budget_mode": "scenario_split",
                "scope_readiness": "WATCH",
                "scope_readiness_by_section": {
                    "forecast": "GO",
                    "allocation": "WATCH",
                    "recommendation": "WATCH",
                    "evidence": "WATCH",
                },
            },
            "executive_summary": {
                "what_should_we_do_now": "Hold spend release until the business gate closes.",
            },
            "operational_recommendations": {
                "regions": [{"region_code": "BE", "priority_score": 0.88}],
            },
            "pilot_evidence": {
                "legacy_context": {
                    "status": "frozen",
                    "sunset_date": "2026-04-30",
                },
            },
            "empty_state": {"code": "watch_only"},
        }

        with patch(
            "app.services.media.pilot_readout_service.PilotReadoutService.build_readout",
            return_value=expected_payload,
        ) as mocked_build:
            response = self.client.get(
                "/api/v1/media/pilot-readout?brand=gelo&virus_typ=RSV%20A&horizon_days=7&weekly_budget_eur=120000",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["executive_summary"]["what_should_we_do_now"], expected_payload["executive_summary"]["what_should_we_do_now"])
        self.assertEqual(body["pilot_evidence"]["legacy_context"]["sunset_date"], "2026-04-30")
        self.assertEqual(body["run_context"]["pilot_mode"], "forecast_first")
        self.assertEqual(body["run_context"]["budget_mode"], "scenario_split")
        self.assertNotIn("impact_probability", str(body))
        mocked_build.assert_called_once()

    def test_outcomes_ingest_requires_valid_api_key(self) -> None:
        response = self.client.post(
            "/api/v1/media/outcomes/ingest",
            json={
                "brand": "gelo",
                "source_system": "crm",
                "external_batch_id": "batch-1",
                "observations": [],
            },
            headers={"X-API-Key": "wrong-key"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid API key")

    def test_outcomes_ingest_keeps_m2m_flow_without_bearer_token(self) -> None:
        response = self.client.post(
            "/api/v1/media/outcomes/ingest",
            json={
                "brand": "gelo",
                "source_system": "crm",
                "external_batch_id": "batch-m2m-only",
                "observations": [],
            },
            headers={"X-API-Key": "test-m2m-secret"},
        )

        self.assertEqual(response.status_code, 200)

    def test_outcomes_ingest_requires_api_key_header(self) -> None:
        response = self.client.post(
            "/api/v1/media/outcomes/ingest",
            json={
                "brand": "gelo",
                "source_system": "crm",
                "external_batch_id": "batch-missing-key",
                "observations": [],
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Missing API key")

    def test_outcomes_ingest_is_idempotent_and_persists_auditable_batch(self) -> None:
        payload = {
            "brand": "gelo",
            "source_system": "crm",
            "external_batch_id": "batch-42",
            "observations": [
                {
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "window_start": "2026-02-02T00:00:00",
                    "window_end": "2026-02-08T00:00:00",
                    "metric_name": "media_spend",
                    "metric_value": 12000,
                    "metric_unit": "eur",
                    "channel": "search",
                    "campaign_id": "wave-1",
                    "holdout_group": "test",
                    "metadata": {"incremental_lift_pct": 12.5},
                },
                {
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "window_start": "2026-02-02T00:00:00",
                    "window_end": "2026-02-08T00:00:00",
                    "metric_name": "sales",
                    "metric_value": 140,
                    "metric_unit": "units",
                    "campaign_id": "wave-1",
                    "holdout_group": "test",
                },
            ],
        }

        first = self.client.post(
            "/api/v1/media/outcomes/ingest",
            json=payload,
            headers={"X-API-Key": "test-m2m-secret"},
        )
        second = self.client.post(
            "/api/v1/media/outcomes/ingest",
            json=payload,
            headers={"X-API-Key": "test-m2m-secret"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_body = first.json()
        second_body = second.json()
        self.assertFalse(first_body["idempotent_replay"])
        self.assertTrue(second_body["idempotent_replay"])
        self.assertEqual(first_body["batch_id"], second_body["batch_id"])
        self.assertEqual(first_body["batch_summary"]["ingestion_mode"], "api_ingest")
        self.assertEqual(first_body["batch_summary"]["source_system"], "crm")
        self.assertEqual(first_body["batch_summary"]["external_batch_id"], "batch-42")

        batches = self.db.query(MediaOutcomeImportBatch).all()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].external_batch_id, "batch-42")
        self.assertEqual(
            self.db.query(OutcomeObservation).count(),
            2,
        )

    def test_outcomes_ingest_records_issues_for_invalid_metrics(self) -> None:
        response = self.client.post(
            "/api/v1/media/outcomes/ingest",
            json={
                "brand": "gelo",
                "source_system": "crm",
                "external_batch_id": "batch-invalid",
                "observations": [
                    {
                        "product": "GeloProsed",
                        "region_code": "SH",
                        "window_start": "2026-02-02T00:00:00",
                        "window_end": "2026-02-08T00:00:00",
                        "metric_name": "unsupported_metric",
                        "metric_value": 12000,
                    }
                ],
            },
            headers={"X-API-Key": "test-m2m-secret"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["imported"], 0)
        self.assertEqual(body["batch_summary"]["status"], "failed")
        self.assertEqual(body["issues"][0]["issue_code"], "unsupported_metric_name")

    def test_cockpit_endpoint_maps_mlforecast_schema_mismatch_to_503(self) -> None:
        with patch(
            "app.services.media.cockpit_service.MediaCockpitService.get_cockpit_payload",
            side_effect=MLForecastSchemaMismatchError("MLForecast schema mismatch detected."),
        ):
            response = self.client.get(
                "/api/v1/media/cockpit?virus_typ=Influenza%20A",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "MLForecast schema mismatch detected.")

    def test_decision_endpoint_maps_mlforecast_schema_mismatch_to_503(self) -> None:
        with patch(
            "app.services.media.v2_service.MediaV2Service.get_decision_payload",
            side_effect=MLForecastSchemaMismatchError("MLForecast schema mismatch detected."),
        ):
            response = self.client.get(
                "/api/v1/media/decision?brand=gelo&virus_typ=Influenza%20A",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "MLForecast schema mismatch detected.")

    def test_regions_endpoint_maps_mlforecast_schema_mismatch_to_503(self) -> None:
        with patch(
            "app.services.media.v2_service.MediaV2Service.get_regions_payload",
            side_effect=MLForecastSchemaMismatchError("MLForecast schema mismatch detected."),
        ):
            response = self.client.get(
                "/api/v1/media/regions?brand=gelo&virus_typ=Influenza%20A",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "MLForecast schema mismatch detected.")

    def test_evidence_endpoint_maps_mlforecast_schema_mismatch_to_503(self) -> None:
        with patch(
            "app.services.media.v2_service.MediaV2Service.get_evidence_payload",
            side_effect=MLForecastSchemaMismatchError("MLForecast schema mismatch detected."),
        ):
            response = self.client.get(
                "/api/v1/media/evidence?brand=gelo&virus_typ=Influenza%20A",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "MLForecast schema mismatch detected.")

    def test_pilot_readout_endpoint_maps_mlforecast_schema_mismatch_to_503(self) -> None:
        with patch(
            "app.services.media.pilot_readout_service.PilotReadoutService.build_readout",
            side_effect=MLForecastSchemaMismatchError("MLForecast schema mismatch detected."),
        ):
            response = self.client.get(
                "/api/v1/media/pilot-readout?brand=gelo&virus_typ=RSV%20A&horizon_days=7&weekly_budget_eur=120000",
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "MLForecast schema mismatch detected.")


if __name__ == "__main__":
    unittest.main()
