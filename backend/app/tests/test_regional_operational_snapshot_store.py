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
                "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                "predictions": [{"bundesland": "BY"}],
            },
            allocation={"generated_at": "2026-03-17T08:01:00", "recommendations": [{"bundesland": "BY"}]},
            recommendations={"generated_at": "2026-03-17T08:02:00", "recommendations": [{"bundesland": "BY"}]},
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


if __name__ == "__main__":
    unittest.main()
