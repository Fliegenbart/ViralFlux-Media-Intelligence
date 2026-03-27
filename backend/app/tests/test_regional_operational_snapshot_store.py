from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import AuditLog, Base
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore


class RegionalOperationalSnapshotStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_record_scope_snapshot_persists_operational_metadata(self) -> None:
        store = RegionalOperationalSnapshotStore(self.db)

        payload = store.record_scope_snapshot(
            virus_typ="Influenza A",
            horizon_days=5,
            forecast={
                "as_of_date": "2026-03-17",
                "generated_at": "2026-03-17T08:00:00",
                "model_version": "regional_pooled_panel:h5:2026-03-17T08:00:00",
                "metric_semantics_version": "regional_probabilistic_metrics_v1",
                "registry_status": "champion",
                "promotion_evidence": {"promotion_allowed": True, "promotion_blockers": []},
                "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                "predictions": [{"bundesland": "BY"}],
            },
            allocation={"generated_at": "2026-03-17T08:01:00", "recommendations": [{"bundesland": "BY"}]},
            recommendations={"generated_at": "2026-03-17T08:02:00", "recommendations": [{"bundesland": "BY"}]},
            readiness={
                "forecast_recency_status": "ok",
                "source_coverage_required_status": "ok",
                "source_freshness_status": "ok",
                "live_source_coverage_status": "ok",
                "live_source_freshness_status": "ok",
                "artifact_source_coverage": {"grippeweb_are_available": 0.95},
                "training_source_coverage": {"grippeweb_are_available": 0.95},
                "live_source_coverage": {"grippeweb_are": {"coverage_ratio": 1.0, "status": "ok"}},
                "live_source_freshness": {"grippeweb_are": {"age_days": 1, "status": "ok"}},
                "source_criticality": {"grippeweb_are": "critical"},
                "pilot_contract_supported": True,
                "pilot_contract_reason": None,
            },
        )

        row = self.db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.action, RegionalOperationalSnapshotStore.ACTION)
        self.assertEqual(row.entity_type, RegionalOperationalSnapshotStore.ENTITY_TYPE)
        self.assertEqual(payload["status"], "success")
        latest = store.latest_scope_snapshot(virus_typ="Influenza A", horizon_days=5)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["forecast_as_of_date"], "2026-03-17")
        self.assertEqual(latest["forecast_regions"], 1)
        self.assertEqual(latest["allocation_regions"], 1)
        self.assertEqual(latest["recommendation_count"], 1)
        self.assertEqual(latest["forecast_recency_status"], "ok")
        self.assertTrue(latest["pilot_contract_supported"])
        self.assertEqual(latest["metric_semantics_version"], "regional_probabilistic_metrics_v1")
        self.assertEqual(latest["registry_status"], "champion")
        self.assertTrue(latest["promotion_evidence"]["promotion_allowed"])
        self.assertEqual(latest["live_source_coverage_status"], "ok")
        self.assertEqual(latest["source_criticality"]["grippeweb_are"], "critical")
        self.assertEqual(latest["source_coverage_scope"], "artifact")

    def test_latest_scope_snapshots_prefers_newest_scope_run(self) -> None:
        store = RegionalOperationalSnapshotStore(self.db)
        store.record_scope_snapshot(
            virus_typ="Influenza A",
            horizon_days=7,
            forecast={"as_of_date": "2026-03-10", "predictions": []},
            allocation={"recommendations": []},
            recommendations={"recommendations": []},
        )
        store.record_scope_snapshot(
            virus_typ="Influenza A",
            horizon_days=7,
            forecast={"as_of_date": "2026-03-17", "predictions": [{"bundesland": "BY"}]},
            allocation={"recommendations": [{"bundesland": "BY"}]},
            recommendations={"recommendations": [{"bundesland": "BY"}]},
        )

        latest = store.latest_scope_snapshot(virus_typ="Influenza A", horizon_days=7)

        self.assertIsNotNone(latest)
        self.assertEqual(latest["forecast_as_of_date"], "2026-03-17")
        self.assertEqual(latest["forecast_regions"], 1)

    def test_recent_scope_snapshots_returns_newest_history_first(self) -> None:
        store = RegionalOperationalSnapshotStore(self.db)
        store.record_scope_snapshot(
            virus_typ="SARS-CoV-2",
            horizon_days=7,
            forecast={
                "as_of_date": "2026-03-10",
                "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                "predictions": [{"bundesland": "BY"}],
            },
            allocation={"recommendations": [{"bundesland": "BY"}]},
            recommendations={"recommendations": [{"bundesland": "BY"}]},
            readiness={
                "forecast_recency_status": "ok",
                "source_coverage_required_status": "ok",
            },
        )
        store.record_scope_snapshot(
            virus_typ="SARS-CoV-2",
            horizon_days=7,
            forecast={
                "as_of_date": "2026-03-17",
                "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                "predictions": [{"bundesland": "BY"}],
            },
            allocation={"recommendations": [{"bundesland": "BY"}]},
            recommendations={"recommendations": [{"bundesland": "BY"}]},
            readiness={
                "forecast_recency_status": "ok",
                "source_coverage_required_status": "ok",
            },
        )

        history = store.recent_scope_snapshots(virus_typ="SARS-CoV-2", horizon_days=7, limit=2)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["forecast_as_of_date"], "2026-03-17")
        self.assertEqual(history[1]["forecast_as_of_date"], "2026-03-10")

    def test_latest_scope_snapshot_backfills_live_fields_for_legacy_metadata(self) -> None:
        recorder = RegionalOperationalSnapshotStore(self.db).recorder
        recorder.record_event(
            action=RegionalOperationalSnapshotStore.ACTION,
            status="success",
            summary="Legacy snapshot payload",
            entity_type=RegionalOperationalSnapshotStore.ENTITY_TYPE,
            metadata={
                "virus_typ": "RSV A",
                "horizon_days": 7,
                "forecast_as_of_date": "2026-03-17",
                "source_coverage": {"grippeweb_are_available": 0.95},
                "source_coverage_required_status": "ok",
                "source_freshness_status": "warning",
            },
        )

        latest = RegionalOperationalSnapshotStore(self.db).latest_scope_snapshot(
            virus_typ="RSV A",
            horizon_days=7,
        )

        self.assertIsNotNone(latest)
        self.assertEqual(latest["source_coverage_scope"], "artifact")
        self.assertEqual(latest["artifact_source_coverage"]["grippeweb_are_available"], 0.95)
        self.assertEqual(latest["training_source_coverage"]["grippeweb_are_available"], 0.95)
        self.assertEqual(latest["live_source_coverage_status"], "ok")
        self.assertEqual(latest["live_source_freshness_status"], "warning")

    def test_legacy_source_coverage_alone_does_not_backfill_live_status(self) -> None:
        recorder = RegionalOperationalSnapshotStore(self.db).recorder
        recorder.record_event(
            action=RegionalOperationalSnapshotStore.ACTION,
            status="success",
            summary="Legacy artifact-only snapshot payload",
            entity_type=RegionalOperationalSnapshotStore.ENTITY_TYPE,
            metadata={
                "virus_typ": "Influenza A",
                "horizon_days": 5,
                "forecast_as_of_date": "2026-03-17",
                "source_coverage": {"wastewater_available": 0.91},
            },
        )

        latest = RegionalOperationalSnapshotStore(self.db).latest_scope_snapshot(
            virus_typ="Influenza A",
            horizon_days=5,
        )

        self.assertIsNotNone(latest)
        self.assertEqual(latest["source_coverage_scope"], "artifact")
        self.assertEqual(latest["artifact_source_coverage"]["wastewater_available"], 0.91)
        self.assertNotIn("live_source_coverage_status", latest)
        self.assertNotIn("live_source_freshness_status", latest)


if __name__ == "__main__":
    unittest.main()
