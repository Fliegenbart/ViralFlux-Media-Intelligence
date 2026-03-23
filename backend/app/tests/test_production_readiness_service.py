from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import AuditLog, Base, WastewaterData
from app.services.ml.forecast_horizon_utils import (
    SUPPORTED_FORECAST_HORIZONS,
    supported_regional_horizons_for_virus,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore
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

    def _supported_scope_count(self) -> int:
        return sum(len(supported_regional_horizons_for_virus(virus_typ)) for virus_typ in SUPPORTED_VIRUS_TYPES)

    def _unsupported_scope_count(self) -> int:
        return (len(SUPPORTED_VIRUS_TYPES) * len(SUPPORTED_FORECAST_HORIZONS)) - self._supported_scope_count()

    def test_build_snapshot_reports_healthy_when_models_and_sources_are_fresh(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ in {"Influenza A", "Influenza B"}:
                coverage["ifsg_influenza_available"] = 0.96
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            else:
                coverage.update(
                    {
                        "sars_are_available": 0.91,
                        "sars_notaufnahme_available": 0.93,
                        "sars_trends_available": 0.30,
                    }
                )
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
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
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
        self.assertEqual(snapshot["components"]["core_regional_operational"]["status"], "ok")
        self.assertIn("core_regional_operational", snapshot["blocking_components"])
        self.assertIn("forecast_monitoring", snapshot["advisory_components"])
        regional = snapshot["components"]["regional_operational"]
        self.assertEqual(regional["status"], "warning")
        self.assertEqual(regional["summary"]["unsupported"], self._unsupported_scope_count())
        self.assertEqual(regional["summary"]["critical"], 0)
        self.assertEqual(snapshot["blockers"], [])

    def test_build_core_snapshot_reports_healthy_for_allowlisted_scope_even_if_global_snapshot_stays_degraded(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ in {"Influenza A", "Influenza B"}:
                coverage["ifsg_influenza_available"] = 0.96
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            else:
                coverage.update(
                    {
                        "sars_are_available": 0.91,
                        "sars_notaufnahme_available": 0.93,
                        "sars_trends_available": 0.30,
                    }
                )

            return {
                "metadata": {
                    "feature_columns": ["feature_a"],
                    "trained_at": (now - timedelta(days=2)).isoformat(),
                    "model_version": f"regional:{virus_typ}:h{horizon_days}",
                    "calibration_version": f"isotonic:{virus_typ}:h{horizon_days}",
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "dataset_manifest": {
                        "rows": 120,
                        "states": 16,
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
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
                "monitoring_status": "warning",
                "forecast_readiness": "WATCH",
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
            service.settings.CORE_PRODUCTION_SCOPES = "RSV A:h7"
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_snapshot()
            core_snapshot = service.build_core_snapshot()

        self.assertEqual(snapshot["status"], "healthy")
        self.assertEqual(core_snapshot["status"], "healthy")
        self.assertEqual(core_snapshot["scope_mode"], "core_production")
        self.assertEqual(core_snapshot["scope_allowlist"], [{"virus_typ": "RSV A", "horizon_days": 7}])
        core_component = core_snapshot["components"]["core_regional_operational"]
        self.assertEqual(core_component["status"], "ok")
        self.assertEqual(core_component["summary"]["ready"], 1)
        self.assertEqual(core_component["summary"]["warning"], 0)
        self.assertEqual(core_component["summary"]["critical"], 0)

    def test_build_core_snapshot_turns_unhealthy_when_allowlisted_scope_is_unsupported(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            del virus_typ, horizon_days
            return {}

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
            service.settings.CORE_PRODUCTION_SCOPES = "RSV A:h3"
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_core_snapshot()

        self.assertEqual(snapshot["status"], "unhealthy")
        core_component = snapshot["components"]["core_regional_operational"]
        self.assertEqual(core_component["status"], "critical")
        self.assertEqual(core_component["summary"]["critical"], 1)
        item = core_component["matrix"][0]
        self.assertEqual(item["virus_typ"], "RSV A")
        self.assertEqual(item["horizon_days"], 3)
        self.assertEqual(item["model_availability"], "unsupported")
        self.assertFalse(item["core_scope_passed"])
        self.assertIn("Core scope has no loadable regional model artifacts.", item["blockers"])

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
        self.assertEqual(regional["summary"]["missing_models"], self._supported_scope_count())
        self.assertEqual(regional["summary"]["unsupported"], self._unsupported_scope_count())
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

    def test_build_snapshot_surfaces_component_failures_without_raising(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ in {"Influenza A", "Influenza B"}:
                coverage["ifsg_influenza_available"] = 0.96
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            else:
                coverage.update(
                    {
                        "sars_are_available": 0.91,
                        "sars_notaufnahme_available": 0.93,
                        "sars_trends_available": 0.30,
                    }
                )
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
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
                    "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                },
                "point_in_time_snapshot": {
                    "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                },
            }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService._load_artifacts",
            new=fake_artifacts,
        ), patch.object(
            ProductionReadinessService,
            "_forecast_monitoring_component",
            side_effect=RuntimeError("monitoring exploded"),
        ):
            service = ProductionReadinessService(
                session_factory=self._session_factory,
                now_provider=lambda: now,
            )
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_snapshot()

        self.assertEqual(snapshot["status"], "degraded")
        self.assertEqual(snapshot["components"]["forecast_monitoring"]["status"], "critical")
        self.assertIn("monitoring exploded", snapshot["components"]["forecast_monitoring"]["message"])
        self.assertEqual(snapshot["components"]["regional_operational"]["status"], "warning")

    def test_build_snapshot_uses_operational_snapshot_for_forecast_recency(self) -> None:
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
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": {"ww": 0.92, "trends": 0.88},
                    "as_of_range": {"end": (now - timedelta(days=10)).date().isoformat()},
                },
                "point_in_time_snapshot": {
                    "as_of_range": {"end": (now - timedelta(days=10)).date().isoformat()},
                },
            }

        store = RegionalOperationalSnapshotStore(self.db)
        for virus_typ in SUPPORTED_VIRUS_TYPES:
            for horizon_days in SUPPORTED_FORECAST_HORIZONS:
                store.record_scope_snapshot(
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    forecast={
                        "as_of_date": (now - timedelta(days=1)).date().isoformat(),
                        "predictions": [{"bundesland": "BY"}],
                        "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    },
                    allocation={"recommendations": [{"bundesland": "BY"}]},
                    recommendations={"recommendations": [{"bundesland": "BY"}]},
                )

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

        regional = snapshot["components"]["regional_operational"]
        self.assertEqual(regional["status"], "warning")
        supported_item = next(item for item in regional["matrix"] if item["model_availability"] != "unsupported")
        self.assertEqual(supported_item["forecast_recency_basis"], "operational_snapshot")
        self.assertEqual(supported_item["forecast_recency_status"], "ok")
        self.assertEqual(regional["summary"]["unsupported"], self._unsupported_scope_count())

    def test_build_snapshot_treats_explicit_unsupported_scope_as_warning_not_missing(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            del virus_typ, horizon_days
            return {}

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
        ), patch.dict(
            "app.services.ml.forecast_horizon_utils.REGIONAL_UNSUPPORTED_HORIZON_REASONS",
            {"Influenza A": {3: "Pilot supports only h5/h7 for this virus."}},
            clear=False,
        ):
            service = ProductionReadinessService(
                session_factory=self._session_factory,
                now_provider=lambda: now,
            )
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_snapshot()

        regional = snapshot["components"]["regional_operational"]
        unsupported = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "Influenza A" and item["horizon_days"] == 3
        )
        unsupported_count = sum(1 for item in regional["matrix"] if item["model_availability"] == "unsupported")
        self.assertEqual(unsupported["model_availability"], "unsupported")
        self.assertEqual(unsupported["status"], "warning")
        self.assertEqual(regional["summary"]["unsupported"], unsupported_count)
        self.assertLess(regional["summary"]["missing_models"], len(SUPPORTED_VIRUS_TYPES) * len(SUPPORTED_FORECAST_HORIZONS))

    def test_build_snapshot_treats_sars_trends_coverage_as_advisory_not_hard_blocker(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ in {"Influenza A", "Influenza B"}:
                coverage["ifsg_influenza_available"] = 0.96
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            elif virus_typ == "SARS-CoV-2":
                coverage.update(
                    {
                        "sars_are_available": 0.88,
                        "sars_notaufnahme_available": 0.99,
                        "sars_trends_available": 0.06,
                    }
                )

            return {
                "metadata": {
                    "feature_columns": ["feature_a"],
                    "trained_at": (now - timedelta(days=2)).isoformat(),
                    "model_version": f"regional:{virus_typ}:h{horizon_days}",
                    "calibration_version": f"isotonic:{virus_typ}:h{horizon_days}",
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "dataset_manifest": {
                        "rows": 120,
                        "states": 16,
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
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

        regional = snapshot["components"]["regional_operational"]
        sars_item = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "SARS-CoV-2" and item["horizon_days"] == 7
        )
        self.assertEqual(sars_item["status"], "warning")
        self.assertEqual(sars_item["source_coverage_required_status"], "ok")
        self.assertEqual(sars_item["source_coverage_optional_status"], "critical")
        self.assertIn("sars_trends_available", sars_item["source_coverage_optional_keys"])
        self.assertTrue(sars_item["source_coverage_advisories"])
        self.assertNotIn("Source coverage is below the minimum operational threshold.", sars_item["blockers"])

    def test_build_snapshot_keeps_required_sars_coverage_as_hard_blocker(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ in {"Influenza A", "Influenza B"}:
                coverage["ifsg_influenza_available"] = 0.96
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            elif virus_typ == "SARS-CoV-2":
                coverage.update(
                    {
                        "sars_are_available": 0.05,
                        "sars_notaufnahme_available": 0.99,
                        "sars_trends_available": 0.9,
                    }
                )

            return {
                "metadata": {
                    "feature_columns": ["feature_a"],
                    "trained_at": (now - timedelta(days=2)).isoformat(),
                    "model_version": f"regional:{virus_typ}:h{horizon_days}",
                    "calibration_version": f"isotonic:{virus_typ}:h{horizon_days}",
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "dataset_manifest": {
                        "rows": 120,
                        "states": 16,
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
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

        regional = snapshot["components"]["regional_operational"]
        sars_item = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "SARS-CoV-2" and item["horizon_days"] == 7
        )
        self.assertEqual(sars_item["status"], "critical")
        self.assertEqual(sars_item["source_coverage_required_status"], "critical")
        self.assertIn("Source coverage is below the minimum operational threshold.", sars_item["blockers"])

    def test_build_snapshot_surfaces_pilot_contract_and_quality_gate_details(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            pilot_profile = virus_typ in {"Influenza A", "Influenza B", "RSV A"} and horizon_days == 7
            quality_gate = {
                "overall_passed": True,
                "forecast_readiness": "GO",
                "profile": "pilot_v1" if pilot_profile else "strict_v1",
                "failed_checks": [],
            }
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ in {"Influenza A", "Influenza B"}:
                coverage["ifsg_influenza_available"] = 0.96
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            else:
                coverage.update(
                    {
                        "sars_are_available": 0.91,
                        "sars_notaufnahme_available": 0.93,
                        "sars_trends_available": 0.30,
                    }
                )
            return {
                "metadata": {
                    "feature_columns": ["feature_a"],
                    "trained_at": (now - timedelta(days=2)).isoformat(),
                    "model_version": f"regional:{virus_typ}:h{horizon_days}",
                    "calibration_version": f"isotonic:{virus_typ}:h{horizon_days}",
                    "quality_gate": quality_gate,
                    "dataset_manifest": {
                        "rows": 120,
                        "states": 16,
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
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

        regional = snapshot["components"]["regional_operational"]
        influenza_h7 = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "Influenza A" and item["horizon_days"] == 7
        )
        influenza_h5 = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "Influenza A" and item["horizon_days"] == 5
        )
        self.assertTrue(influenza_h7["pilot_contract_supported"])
        self.assertEqual(influenza_h7["quality_gate_profile"], "pilot_v1")
        self.assertEqual(influenza_h7["quality_gate_failed_checks"], [])
        self.assertFalse(influenza_h5["pilot_contract_supported"])
        self.assertIn("day-one pilot", influenza_h5["pilot_contract_reason"])

    def test_build_snapshot_tracks_sars_h7_promotion_eligibility_without_auto_promotion(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_wastewater(available_time=now - timedelta(days=1))

        store = RegionalOperationalSnapshotStore(self.db)
        for forecast_date in ("2026-03-16", "2026-03-17"):
            store.record_scope_snapshot(
                virus_typ="SARS-CoV-2",
                horizon_days=7,
                forecast={
                    "as_of_date": forecast_date,
                    "quality_gate": {
                        "overall_passed": True,
                        "forecast_readiness": "GO",
                        "profile": "strict_v1",
                        "failed_checks": [],
                    },
                    "predictions": [{"bundesland": "BY"}],
                },
                allocation={"recommendations": [{"bundesland": "BY"}]},
                recommendations={"recommendations": [{"bundesland": "BY"}]},
                readiness={
                    "forecast_recency_status": "ok",
                    "source_coverage_required_status": "ok",
                },
            )

        def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
            coverage = {
                "grippeweb_are_available": 0.95,
                "grippeweb_ili_available": 0.94,
            }
            if virus_typ == "SARS-CoV-2":
                coverage.update(
                    {
                        "sars_are_available": 0.88,
                        "sars_notaufnahme_available": 0.99,
                        "sars_trends_available": 0.10,
                    }
                )
            elif virus_typ == "RSV A":
                coverage["ifsg_rsv_available"] = 0.95
            else:
                coverage["ifsg_influenza_available"] = 0.96

            return {
                "metadata": {
                    "feature_columns": ["feature_a"],
                    "trained_at": (now - timedelta(days=2)).isoformat(),
                    "model_version": f"regional:{virus_typ}:h{horizon_days}",
                    "calibration_version": f"isotonic:{virus_typ}:h{horizon_days}",
                    "quality_gate": {
                        "overall_passed": True,
                        "forecast_readiness": "GO",
                        "profile": "strict_v1",
                        "failed_checks": [],
                    },
                    "dataset_manifest": {
                        "rows": 120,
                        "states": 16,
                        "source_coverage": coverage,
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": (now - timedelta(days=1)).date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
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
            service.settings.REGIONAL_SARS_H7_PROMOTION_ENABLED = False
            service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
            snapshot = service.build_snapshot()

        regional = snapshot["components"]["regional_operational"]
        sars_item = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "SARS-CoV-2" and item["horizon_days"] == 7
        )
        self.assertFalse(sars_item["pilot_contract_supported"])
        self.assertIsNotNone(sars_item["sars_h7_promotion"])
        self.assertTrue(sars_item["sars_h7_promotion"]["eligible"])
        self.assertFalse(sars_item["sars_h7_promotion"]["promoted"])


if __name__ == "__main__":
    unittest.main()
