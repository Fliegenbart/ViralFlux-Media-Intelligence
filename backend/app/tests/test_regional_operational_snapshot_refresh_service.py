from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import AuditLog, Base
from app.services.ops.regional_operational_snapshot_refresh import (
    RegionalOperationalSnapshotRefreshService,
)


class RegionalOperationalSnapshotRefreshServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        testing_session_local = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = testing_session_local()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_refresh_supported_scopes_persists_snapshot_audit_entry(self) -> None:
        observed_at = datetime(2026, 4, 8, 7, 20, 0)

        forecast_payload = {
            "status": "ok",
            "as_of_date": "2026-04-06T00:00:00",
            "generated_at": observed_at.isoformat(),
            "supported_horizon_days": [3, 5, 7],
            "supported_horizon_days_for_virus": [3, 5, 7],
            "predictions": [{"bundesland": "BY"}],
            "top_5": [{"bundesland": "BY"}],
            "top_decisions": [],
            "decision_summary": {"activate": 1},
            "total_regions": 1,
            "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
            "business_gate": {"evidence_tier": "strong"},
            "rollout_mode": "regional",
            "activation_policy": "decision-first",
            "source_coverage": {"ifsg_influenza_available": 1.0},
            "source_coverage_scope": "artifact",
        }
        allocation_payload = {
            "status": "ok",
            "generated_at": observed_at.isoformat(),
            "target_window_days": [7, 7],
            "recommendations": [{"bundesland": "BY", "suggested_budget_amount": 5000.0}],
            "summary": {"activate_regions": 1},
        }
        recommendation_payload = {
            "status": "ok",
            "generated_at": observed_at.isoformat(),
            "recommendations": [{"region": "BY", "activation_level": "Prepare"}],
            "summary": {"ready_recommendations": 1},
        }
        readiness_payload = {
            "status": "ok",
            "forecast_recency_status": "ok",
            "source_coverage_required_status": "ok",
            "source_freshness_status": "ok",
            "live_source_coverage_status": "ok",
            "live_source_freshness_status": "ok",
            "artifact_source_coverage": {"ifsg_influenza_available": 1.0},
            "training_source_coverage": {"ifsg_influenza_available": 1.0},
            "live_source_coverage": {"ifsg_influenza_available": 1.0},
            "live_source_freshness": {"ifsg_influenza_available": {"status": "ok"}},
            "source_criticality": {"ifsg_influenza_available": "critical"},
            "pilot_contract_supported": True,
            "pilot_contract_reason": None,
        }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService.predict_all_regions",
            return_value=forecast_payload,
        ), patch(
            "app.services.ml.regional_forecast.RegionalForecastService.generate_media_allocation",
            return_value=allocation_payload,
        ), patch(
            "app.services.media.campaign_recommendation_service.CampaignRecommendationService.recommend_from_allocation",
            return_value=recommendation_payload,
        ), patch(
            "app.services.ops.production_readiness_service.ProductionReadinessService._latest_source_state",
            return_value={"latest_available_as_of": observed_at, "status": "ok"},
        ), patch(
            "app.services.ops.production_readiness_service.ProductionReadinessService._regional_matrix_item",
            return_value=readiness_payload,
        ):
            service = RegionalOperationalSnapshotRefreshService(
                self.db,
                now_provider=lambda: observed_at,
            )
            result = service.refresh_supported_scopes(
                virus_types=["Influenza A"],
                horizon_days_list=[7],
            )

        self.assertEqual(result["records_written"], 1)
        row = self.db.query(AuditLog).filter(AuditLog.action == "REGIONAL_OPERATIONAL_SNAPSHOT").one()
        self.assertEqual(row.entity_type, "RegionalOperationalSnapshot")
        metadata = dict((row.new_value or {}).get("metadata") or {})
        self.assertEqual(metadata["virus_typ"], "Influenza A")
        self.assertEqual(metadata["horizon_days"], 7)
        self.assertEqual(metadata["forecast_as_of_date"], "2026-04-06T00:00:00")
        self.assertEqual(metadata["status"], "ok")
