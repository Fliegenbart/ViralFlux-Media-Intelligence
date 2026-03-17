from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import AuditLog, Base, WastewaterData
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.production_readiness_service import ProductionReadinessService
from app.services.ops.run_metadata_service import OperationalRunRecorder


class ProductionReadinessServiceTests(unittest.TestCase):
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

    @contextmanager
    def _session_factory(self):
        try:
            yield self.db
        finally:
            pass

    def _seed_wastewater(self, *, available_time: datetime) -> None:
        for virus_typ in SUPPORTED_VIRUS_TYPES:
            self.db.add(
                WastewaterData(
                    standort=f"site-{virus_typ}",
                    bundesland="BY",
                    datum=available_time,
                    available_time=available_time,
                    virus_typ=virus_typ,
                    viruslast=1.0,
                )
            )
        self.db.commit()

    def test_build_snapshot_reports_healthy_when_models_and_sources_are_fresh(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            del virus_typ
            return {
                "metadata": {
                    "feature_columns": ["feature_a"],
                    "trained_at": (now - timedelta(days=2)).isoformat(),
                    "model_version": f"regional:{horizon_days}",
                    "calibration_version": f"isotonic:{horizon_days}",
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "dataset_manifest": {
                        "rows": 120,
                        "states": 16,
                        "source_coverage": {"ww": 0.92, "trends": 0.88},
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": {"ww": 0.92, "trends": 0.88},
                    "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                },
                "point_in_time_snapshot": {
                    "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                },
            }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService._load_artifacts",
            new=fake_artifacts,
        ), patch(
            "app.services.ml.forecast_decision_service.ForecastDecisionService.build_monitoring_snapshot",
            return_value={
                "monitoring_status": "healthy",
                "forecast_readiness": "GO",
                "freshness_status": "fresh",
                "accuracy_freshness_status": "fresh",
                "backtest_freshness_status": "fresh",
                "model_version": "national:v1",
            },
        ):
            service = ProductionReadinessService(
                session_factory=self._session_factory,
                now_provider=lambda: now,
            )
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_snapshot()

        self.assertEqual(snapshot["status"], "healthy")
        self.assertEqual(snapshot["components"]["database"]["status"], "ok")
        regional = snapshot["components"]["regional_operational"]
        self.assertEqual(
            regional["summary"]["ready"],
            len(SUPPORTED_VIRUS_TYPES) * len(SUPPORTED_FORECAST_HORIZONS),
        )
        self.assertEqual(regional["summary"]["critical"], 0)
        self.assertEqual(snapshot["blockers"], [])

    def test_build_snapshot_flags_missing_models_and_stale_sources(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=30))

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService._load_artifacts",
            return_value={},
        ), patch(
            "app.services.ml.forecast_decision_service.ForecastDecisionService.build_monitoring_snapshot",
            return_value={
                "monitoring_status": "healthy",
                "forecast_readiness": "GO",
                "freshness_status": "fresh",
                "accuracy_freshness_status": "fresh",
                "backtest_freshness_status": "fresh",
                "model_version": "national:v1",
            },
        ):
            service = ProductionReadinessService(
                session_factory=self._session_factory,
                now_provider=lambda: now,
            )
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_snapshot()

        self.assertEqual(snapshot["status"], "unhealthy")
        regional = snapshot["components"]["regional_operational"]
        self.assertEqual(
            regional["summary"]["missing_models"],
            len(SUPPORTED_VIRUS_TYPES) * len(SUPPORTED_FORECAST_HORIZONS),
        )
        self.assertGreater(regional["summary"]["stale_sources"], 0)
        self.assertTrue(snapshot["blockers"])

    def test_operational_run_recorder_persists_audit_log_metadata(self) -> None:
        recorder = OperationalRunRecorder(self.db)
        payload = recorder.record_event(
            action="OPS_SMOKE_TEST",
            status="success",
            summary="Smoke test completed.",
            metadata={"ready": True},
            commit=True,
        )

        row = self.db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.action, "OPS_SMOKE_TEST")
        self.assertEqual(row.entity_type, "OperationalRun")
        self.assertEqual((row.new_value or {}).get("run_id"), payload["run_id"])
        self.assertTrue((row.new_value or {}).get("metadata", {}).get("ready"))


if __name__ == "__main__":
    unittest.main()
