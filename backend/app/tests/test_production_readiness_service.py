from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import (
    AREKonsultation,
    AuditLog,
    Base,
    GoogleTrendsData,
    GrippeWebData,
    InfluenzaData,
    NotaufnahmeSyndromData,
    RSVData,
    WastewaterData,
)
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
        self._seed_live_sources(available_time=available_time)

    def _seed_live_sources(
        self,
        *,
        available_time: datetime,
        source_times: dict[str, datetime] | None = None,
        skip_sources: set[str] | None = None,
    ) -> None:
        source_times = source_times or {}
        skip_sources = set(skip_sources or set())

        def source_time(source_id: str) -> datetime:
            return source_times.get(source_id, available_time)

        for virus_typ in SUPPORTED_VIRUS_TYPES:
            wastewater_time = source_time("wastewater")
            self.db.add(
                WastewaterData(
                    standort=f"site-{virus_typ}",
                    bundesland="BY",
                    datum=wastewater_time,
                    available_time=wastewater_time,
                    virus_typ=virus_typ,
                    viruslast=1.0,
                )
            )
        if "grippeweb_are" not in skip_sources:
            grippeweb_are_time = source_time("grippeweb_are")
            for offset in (21, 14, 7, 0):
                datum = grippeweb_are_time - timedelta(days=offset)
                self.db.add(
                    GrippeWebData(
                        datum=datum,
                        kalenderwoche=datum.isocalendar()[1],
                        erkrankung_typ="ARE",
                        altersgruppe="Gesamt",
                        bundesland="BY",
                        inzidenz=12.0,
                        anzahl_meldungen=100,
                        created_at=datum,
                    )
                )
        if "grippeweb_ili" not in skip_sources:
            grippeweb_ili_time = source_time("grippeweb_ili")
            for offset in (21, 14, 7, 0):
                datum = grippeweb_ili_time - timedelta(days=offset)
                self.db.add(
                    GrippeWebData(
                        datum=datum,
                        kalenderwoche=datum.isocalendar()[1],
                        erkrankung_typ="ILI",
                        altersgruppe="Gesamt",
                        bundesland="BY",
                        inzidenz=8.0,
                        anzahl_meldungen=80,
                        created_at=datum,
                    )
                )
        if "ifsg_influenza" not in skip_sources:
            influenza_time = source_time("ifsg_influenza")
            for offset in (21, 14, 7, 0):
                datum = influenza_time - timedelta(days=offset)
                self.db.add(
                    InfluenzaData(
                        datum=datum,
                        available_time=datum,
                        meldewoche=f"{datum.isocalendar().year}-W{datum.isocalendar().week:02d}",
                        region="BY",
                        altersgruppe="Gesamt",
                        fallzahl=10,
                        inzidenz=15.0,
                    )
                )
        if "ifsg_rsv" not in skip_sources:
            rsv_time = source_time("ifsg_rsv")
            for offset in (21, 14, 7, 0):
                datum = rsv_time - timedelta(days=offset)
                self.db.add(
                    RSVData(
                        datum=datum,
                        available_time=datum,
                        meldewoche=f"{datum.isocalendar().year}-W{datum.isocalendar().week:02d}",
                        region="BY",
                        altersgruppe="Gesamt",
                        fallzahl=8,
                        inzidenz=12.0,
                    )
                )
        if "sars_are" not in skip_sources:
            are_time = source_time("sars_are")
            for offset in (21, 14, 7, 0):
                datum = are_time - timedelta(days=offset)
                self.db.add(
                    AREKonsultation(
                        datum=datum,
                        available_time=datum,
                        kalenderwoche=datum.isocalendar()[1],
                        saison=f"{datum.year}/{datum.year + 1}",
                        altersgruppe="00+",
                        bundesland="BY",
                        konsultationsinzidenz=18,
                    )
                )
        if "sars_notaufnahme" not in skip_sources:
            notaufnahme_time = source_time("sars_notaufnahme")
            for offset in range(6, -1, -1):
                datum = notaufnahme_time - timedelta(days=offset)
                self.db.add(
                    NotaufnahmeSyndromData(
                        datum=datum,
                        ed_type="all",
                        age_group="00+",
                        syndrome="COVID",
                        relative_cases=0.12,
                        relative_cases_7day_ma=0.11,
                        expected_value=0.09,
                        expected_lowerbound=0.07,
                        expected_upperbound=0.13,
                        ed_count=20,
                        created_at=datum,
                    )
                )
        if "sars_trends" not in skip_sources:
            trends_time = source_time("sars_trends")
            for offset in range(6, -1, -1):
                datum = trends_time - timedelta(days=offset)
                self.db.add(
                    GoogleTrendsData(
                        datum=datum,
                        available_time=datum,
                        keyword="corona test",
                        region="DE",
                        interest_score=35,
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
        influenza_item = next(
            item
            for item in regional["matrix"]
            if item["virus_typ"] == "Influenza A" and item["horizon_days"] == 7
        )
        self.assertEqual(influenza_item["source_coverage_scope"], "artifact")
        self.assertEqual(influenza_item["source_coverage"], influenza_item["artifact_source_coverage"])
        self.assertEqual(influenza_item["artifact_source_coverage"], influenza_item["training_source_coverage"])
        self.assertIn("live_source_coverage", influenza_item)
        self.assertIn("live_source_freshness", influenza_item)
        self.assertIn("source_criticality", influenza_item)
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

    def test_build_core_snapshot_treats_source_warning_as_advisory_when_forecast_recency_is_ok(self) -> None:
        now = datetime(2026, 3, 23, 10, 0, 0)
        latest_available = now - timedelta(days=10)
        self._seed_wastewater(available_time=latest_available)

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
                        "as_of_range": {"end": latest_available.date().isoformat()},
                    },
                    "point_in_time_snapshot": {
                        "as_of_range": {"end": latest_available.date().isoformat()},
                    },
                },
                "dataset_manifest": {
                    "rows": 120,
                    "states": 16,
                    "source_coverage": coverage,
                    "as_of_range": {"end": latest_available.date().isoformat()},
                },
                "point_in_time_snapshot": {
                    "as_of_range": {"end": latest_available.date().isoformat()},
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
                "accuracy_freshness_status": "stale",
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
        core_item = core_snapshot["components"]["core_regional_operational"]["matrix"][0]
        self.assertEqual(core_item["status"], "ok")
        self.assertEqual(core_item["source_freshness_status"], "warning")
        self.assertEqual(core_item["forecast_recency_status"], "ok")
        self.assertEqual(core_item["blockers"], [])
        self.assertTrue(core_item["core_scope_advisories"])

    def test_build_snapshot_warns_when_live_critical_source_is_stale(self) -> None:
        now = datetime(2026, 3, 23, 10, 0, 0)
        self._seed_live_sources(
            available_time=now - timedelta(days=1),
            source_times={"ifsg_rsv": now - timedelta(days=10)},
        )

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

        rsv_item = next(
            item
            for item in snapshot["components"]["regional_operational"]["matrix"]
            if item["virus_typ"] == "RSV A" and item["horizon_days"] == 7
        )
        self.assertEqual(rsv_item["status"], "warning")
        self.assertEqual(rsv_item["source_freshness_status"], "warning")
        self.assertEqual(rsv_item["live_source_freshness"]["ifsg_rsv"]["status"], "warning")
        self.assertEqual(rsv_item["source_coverage_required_status"], "ok")

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

    def test_build_snapshot_keeps_artifact_coverage_separate_from_live_source_status(self) -> None:
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
        self.assertEqual(sars_item["source_coverage_required_status"], "ok")
        self.assertEqual(sars_item["source_coverage_optional_status"], "ok")
        self.assertEqual(sars_item["artifact_source_coverage_status"], "warning")
        self.assertEqual(sars_item["artifact_source_coverage"]["sars_trends_available"], 0.06)
        self.assertEqual(sars_item["live_source_coverage"]["sars_trends"]["status"], "ok")
        self.assertNotIn("Critical live source coverage is missing or too low: sars_trends.", sars_item["blockers"])

    def test_build_snapshot_keeps_required_live_sars_coverage_as_hard_blocker(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_live_sources(
            available_time=now - timedelta(days=1),
            skip_sources={"sars_are"},
        )

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
        self.assertIn("Critical live source coverage is missing or too low: sars_are.", sars_item["blockers"])

    def test_build_snapshot_treats_missing_live_advisory_source_as_warning_not_blocker(self) -> None:
        now = datetime(2026, 3, 17, 10, 0, 0)
        self._seed_live_sources(
            available_time=now - timedelta(days=1),
            skip_sources={"sars_trends"},
        )

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
                        "sars_trends_available": 0.90,
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

        sars_item = next(
            item
            for item in snapshot["components"]["regional_operational"]["matrix"]
            if item["virus_typ"] == "SARS-CoV-2" and item["horizon_days"] == 7
        )
        self.assertEqual(sars_item["source_coverage_required_status"], "ok")
        self.assertEqual(sars_item["source_coverage_optional_status"], "warning")
        self.assertEqual(sars_item["live_source_coverage"]["sars_trends"]["status"], "critical")
        self.assertNotIn("Critical live source coverage is missing or too low: sars_trends.", sars_item["blockers"])
        self.assertTrue(sars_item["live_source_advisories"])

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
        self.assertIn("h7-first product focus", influenza_h5["pilot_contract_reason"])

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
                    "model_version": "regional_pooled_panel:h7:2026-03-17T08:00:00",
                    "metric_semantics_version": "regional_probabilistic_metrics_v1",
                    "registry_status": "champion",
                    "promotion_evidence": {
                        "promotion_allowed": True,
                        "promotion_blockers": [],
                    },
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
                    "metric_semantics_version": "regional_probabilistic_metrics_v1",
                    "promotion_evidence": {
                        "promotion_allowed": True,
                        "promotion_blockers": [],
                    },
                    "registry_status": "champion",
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
