from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "very-strong-admin-password")


@contextmanager
def _temporary_module_overrides(overrides: dict[str, ModuleType]):
    original_modules = {
        name: sys.modules[name]
        for name in overrides
        if name in sys.modules
    }
    missing_modules = [name for name in overrides if name not in sys.modules]

    sys.modules.update(overrides)
    try:
        yield
    finally:
        for name, module in original_modules.items():
            sys.modules[name] = module
        for name in missing_modules:
            sys.modules.pop(name, None)


def _import_main_for_tests():
    sentinel = object()
    app_package = importlib.import_module("app")
    previous_main_module = sys.modules.get("app.main", sentinel)
    previous_main_attr = getattr(app_package, "main", sentinel)

    readiness_stub = ModuleType("app.services.ops.production_readiness_service")
    readiness_stub.ProductionReadinessService = type(
        "_StubProductionReadinessService",
        (),
        {},
    )
    xgboost_stub = ModuleType("xgboost")
    xgboost_stub.XGBClassifier = object
    xgboost_stub.XGBRegressor = object

    with _temporary_module_overrides(
        {
            "app.services.ops.production_readiness_service": readiness_stub,
            "xgboost": xgboost_stub,
        }
    ):
        sys.modules.pop("app.main", None)
        if previous_main_attr is not sentinel and hasattr(app_package, "main"):
            delattr(app_package, "main")

        imported_main = importlib.import_module("app.main")

    if previous_main_module is sentinel:
        sys.modules.pop("app.main", None)
    else:
        sys.modules["app.main"] = previous_main_module

    if previous_main_attr is sentinel:
        if hasattr(app_package, "main"):
            delattr(app_package, "main")
    else:
        setattr(app_package, "main", previous_main_attr)

    return imported_main


main = _import_main_for_tests()


@contextmanager
def _lock_result(acquired: bool):
    yield acquired


@contextmanager
def _db_context(db: object):
    yield db


class StartupSingletonTests(unittest.TestCase):
    def test_temporary_module_overrides_restore_only_stubbed_modules(self) -> None:
        original_module = ModuleType("tests.original_module")
        replacement_module = ModuleType("tests.original_module")
        stubbed_module = ModuleType("tests.stubbed_module")
        late_loaded_module = ModuleType("tests.late_loaded_module")
        sys.modules["tests.original_module"] = original_module
        sys.modules.pop("tests.stubbed_module", None)
        sys.modules.pop("tests.late_loaded_module", None)

        with _temporary_module_overrides(
            {
                "tests.original_module": replacement_module,
                "tests.stubbed_module": stubbed_module,
            }
        ):
            self.assertIs(sys.modules["tests.original_module"], replacement_module)
            self.assertIs(sys.modules["tests.stubbed_module"], stubbed_module)
            sys.modules["tests.late_loaded_module"] = late_loaded_module

        self.assertIs(sys.modules["tests.original_module"], original_module)
        self.assertNotIn("tests.stubbed_module", sys.modules)
        self.assertIs(sys.modules["tests.late_loaded_module"], late_loaded_module)

        sys.modules.pop("tests.original_module", None)
        sys.modules.pop("tests.late_loaded_module", None)

    def test_import_main_for_tests_does_not_leave_app_main_in_global_import_cache(self) -> None:
        app_package = importlib.import_module("app")
        previous_module = sys.modules.pop("app.main", None)
        previous_attr = getattr(app_package, "main", None)
        had_attr = hasattr(app_package, "main")
        if had_attr:
            delattr(app_package, "main")

        try:
            isolated_main = _import_main_for_tests()

            self.assertEqual(isolated_main.__name__, "app.main")
            self.assertNotIn("app.main", sys.modules)
            self.assertFalse(hasattr(app_package, "main"))
        finally:
            if previous_module is not None:
                sys.modules["app.main"] = previous_module
            if had_attr:
                setattr(app_package, "main", previous_attr)

    def test_startup_event_skips_bfarm_import_when_flag_is_disabled(self) -> None:
        readiness_snapshot = {
            "status": "healthy",
            "components": {},
            "blockers": [],
            "checked_at": "2026-03-26T10:00:00",
        }

        with (
            patch.object(main, "settings", SimpleNamespace(
                APP_NAME="ViralFlux Media Intelligence",
                APP_VERSION="1.0.0",
                ENVIRONMENT="development",
                EFFECTIVE_STARTUP_STRICT_READINESS=False,
                STARTUP_ENABLE_BFARM_IMPORT=False,
            )),
            patch.object(main, "check_db_connection") as check_db_connection_mock,
            patch.object(main, "init_db", return_value={"status": "ok", "warnings": [], "actions": []}),
            patch.object(main, "ProductionReadinessService") as readiness_service_cls,
            patch.object(main, "_record_startup_readiness_once", return_value={"status": "healthy"}),
            patch.object(main, "_run_startup_morning_catchup_once", return_value={"status": "skipped"}),
            patch.object(main, "_launch_bfarm_startup_import_thread") as launch_import_mock,
            patch.object(main, "log_event") as log_event_mock,
        ):
            check_db_connection_mock.return_value = True
            readiness_service_cls.return_value.build_snapshot.return_value = readiness_snapshot

            import asyncio

            asyncio.run(main.startup_event())

        launch_import_mock.assert_not_called()
        self.assertTrue(
            any(call.args[1] == "startup_bfarm_import_disabled" for call in log_event_mock.call_args_list)
        )

    def test_startup_event_launches_bfarm_import_when_flag_is_enabled(self) -> None:
        readiness_snapshot = {
            "status": "healthy",
            "components": {},
            "blockers": [],
            "checked_at": "2026-03-26T10:00:00",
        }

        with (
            patch.object(main, "settings", SimpleNamespace(
                APP_NAME="ViralFlux Media Intelligence",
                APP_VERSION="1.0.0",
                ENVIRONMENT="development",
                EFFECTIVE_STARTUP_STRICT_READINESS=False,
                STARTUP_ENABLE_BFARM_IMPORT=True,
            )),
            patch.object(main, "check_db_connection") as check_db_connection_mock,
            patch.object(main, "init_db", return_value={"status": "ok", "warnings": [], "actions": []}),
            patch.object(main, "ProductionReadinessService") as readiness_service_cls,
            patch.object(main, "_record_startup_readiness_once", return_value={"status": "healthy"}),
            patch.object(main, "_run_startup_morning_catchup_once", return_value={"status": "skipped"}),
            patch.object(main, "_launch_bfarm_startup_import_thread") as launch_import_mock,
        ):
            check_db_connection_mock.return_value = True
            readiness_service_cls.return_value.build_snapshot.return_value = readiness_snapshot

            import asyncio

            asyncio.run(main.startup_event())

        launch_import_mock.assert_called_once_with()

    def test_startup_event_runs_morning_catchup_when_forecast_monitoring_is_stale(self) -> None:
        readiness_snapshot = {
            "status": "degraded",
            "components": {
                "forecast_monitoring": {
                    "status": "warning",
                    "items": [
                        {
                            "virus_typ": "Influenza A",
                            "status": "warning",
                            "accuracy_freshness_status": "expired",
                        }
                    ],
                }
            },
            "blockers": [],
            "checked_at": "2026-03-26T10:00:00",
        }

        with (
            patch.object(main, "settings", SimpleNamespace(
                APP_NAME="ViralFlux Media Intelligence",
                APP_VERSION="1.0.0",
                ENVIRONMENT="development",
                EFFECTIVE_STARTUP_STRICT_READINESS=False,
                STARTUP_ENABLE_BFARM_IMPORT=False,
            )),
            patch.object(main, "check_db_connection") as check_db_connection_mock,
            patch.object(main, "init_db", return_value={"status": "ok", "warnings": [], "actions": []}),
            patch.object(main, "ProductionReadinessService") as readiness_service_cls,
            patch.object(main, "_record_startup_readiness_once", return_value={"status": "healthy"}),
            patch.object(main, "_run_startup_morning_catchup_once", create=True) as catchup_mock,
            patch.object(main, "_launch_bfarm_startup_import_thread") as launch_import_mock,
        ):
            check_db_connection_mock.return_value = True
            readiness_service_cls.return_value.build_snapshot.return_value = readiness_snapshot

            import asyncio

            asyncio.run(main.startup_event())

        catchup_mock.assert_called_once_with(readiness_snapshot)
        launch_import_mock.assert_not_called()

    def test_record_startup_readiness_skips_when_lock_is_busy(self) -> None:
        snapshot = {"status": "healthy", "components": {}, "blockers": [], "checked_at": "2026-03-26T10:00:00"}

        with (
            patch.object(main, "try_advisory_lock", return_value=_lock_result(False)),
            patch.object(main, "OperationalRunRecorder") as recorder_cls,
            patch.object(main, "log_event") as log_event_mock,
        ):
            run_metadata = main._record_startup_readiness_once(snapshot)

        self.assertEqual(run_metadata["status"], "skipped")
        self.assertEqual(run_metadata["action"], "STARTUP_READINESS")
        recorder_cls.assert_not_called()
        self.assertTrue(
            any(call.args[1] == "startup_singleton_section_skipped" for call in log_event_mock.call_args_list)
        )

    def test_record_startup_readiness_runs_once_when_lock_is_acquired(self) -> None:
        snapshot = {"status": "healthy", "components": {"database": {}}, "blockers": [], "checked_at": "2026-03-26T10:00:00"}
        db = object()
        recorder = MagicMock()
        recorder.record_event.return_value = {"run_id": "run-1", "status": "healthy", "action": "STARTUP_READINESS"}

        with (
            patch.object(main, "try_advisory_lock", return_value=_lock_result(True)),
            patch.object(main, "get_db_context", return_value=_db_context(db)),
            patch.object(main, "OperationalRunRecorder", return_value=recorder) as recorder_cls,
            patch.object(main, "log_event") as log_event_mock,
        ):
            run_metadata = main._record_startup_readiness_once(snapshot)

        self.assertEqual(run_metadata["run_id"], "run-1")
        recorder_cls.assert_called_once_with(db)
        recorder.record_event.assert_called_once()
        self.assertTrue(
            any(call.args[1] == "startup_singleton_section_completed" for call in log_event_mock.call_args_list)
        )

    def test_bfarm_startup_import_skips_when_lock_is_busy(self) -> None:
        with (
            patch.object(main, "try_advisory_lock", return_value=_lock_result(False)),
            patch.object(main, "log_event") as log_event_mock,
        ):
            main._run_bfarm_startup_import_once()

        self.assertTrue(
            any(
                call.args[1] == "startup_singleton_section_skipped"
                and call.kwargs.get("section") == "startup_bfarm_import"
                for call in log_event_mock.call_args_list
            )
        )

    def test_bfarm_startup_import_runs_when_lock_is_acquired(self) -> None:
        service = MagicMock()
        service.run_full_import.return_value = {"relevant_records": 12, "risk_score": 4}
        bfarm_module = SimpleNamespace(BfarmIngestionService=MagicMock(return_value=service))

        with (
            patch.object(main, "try_advisory_lock", return_value=_lock_result(True)),
            patch.dict("sys.modules", {"app.services.data_ingest.bfarm_service": bfarm_module}),
            patch.object(main, "log_event") as log_event_mock,
        ):
            main._run_bfarm_startup_import_once()

        bfarm_module.BfarmIngestionService.assert_called_once_with()
        service.run_full_import.assert_called_once_with()
        self.assertTrue(
            any(call.args[1] == "startup_bfarm_pull_completed" for call in log_event_mock.call_args_list)
        )

    def test_startup_morning_catchup_queues_chain_once_when_needed(self) -> None:
        readiness_snapshot = {
            "status": "degraded",
            "components": {
                "forecast_monitoring": {
                    "status": "warning",
                    "items": [
                        {
                            "virus_typ": "Influenza A",
                            "status": "warning",
                            "accuracy_freshness_status": "expired",
                        }
                    ],
                }
            },
        }
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        recorder = MagicMock()
        recorder.record_event.return_value = {
            "run_id": "catchup-1",
            "status": "success",
            "action": "STARTUP_MORNING_CATCHUP",
        }
        ingestion_task = MagicMock()
        ingestion_task.si.return_value = "full-ingestion"
        xgboost_task = MagicMock()
        xgboost_task.si.return_value = "xgboost-training"
        regional_training_task = MagicMock()
        regional_training_task.si.return_value = "regional-training"
        live_task = MagicMock()
        live_task.si.return_value = "live-refresh"
        backtest_task = MagicMock()
        backtest_task.si.return_value = "backtest-refresh"
        accuracy_task = MagicMock()
        accuracy_task.si.return_value = "accuracy-refresh"
        snapshot_task = MagicMock()
        snapshot_task.si.return_value = "snapshot-refresh"
        opportunities_task = MagicMock()
        opportunities_task.si.return_value = "marketing-opportunities"
        fake_ml_tasks_module = SimpleNamespace(
            train_xgboost_model_task=xgboost_task,
            train_regional_models_task=regional_training_task,
            refresh_live_forecasts_task=live_task,
            refresh_market_backtests_task=backtest_task,
            compute_forecast_accuracy_task=accuracy_task,
            refresh_regional_operational_snapshots_task=snapshot_task,
        )
        fake_ingest_tasks_module = SimpleNamespace(run_full_ingestion_pipeline=ingestion_task)
        fake_media_tasks_module = SimpleNamespace(generate_marketing_opportunities_task=opportunities_task)
        chain_runner = MagicMock()

        with (
            patch.object(main, "utc_now", return_value=datetime(2026, 4, 15, 8, 30, 0)),
            patch.object(main, "try_advisory_lock", return_value=_lock_result(True)),
            patch.object(main, "get_db_context", return_value=_db_context(db)),
            patch.object(main, "OperationalRunRecorder", return_value=recorder),
            patch.dict(
                "sys.modules",
                {
                    "app.services.data_ingest.tasks": fake_ingest_tasks_module,
                    "app.services.media.tasks": fake_media_tasks_module,
                    "app.services.ml.tasks": fake_ml_tasks_module,
                },
            ),
            patch.object(main, "chain", return_value=chain_runner, create=True) as chain_mock,
            patch.object(main, "log_event"),
        ):
            run_metadata = main._run_startup_morning_catchup_once(readiness_snapshot)

        chain_mock.assert_called_once_with(
            "full-ingestion",
            "xgboost-training",
            "regional-training",
            "live-refresh",
            "backtest-refresh",
            "accuracy-refresh",
            "snapshot-refresh",
            "marketing-opportunities",
        )
        chain_runner.apply_async.assert_called_once_with()
        self.assertEqual(run_metadata["run_id"], "catchup-1")

    def test_startup_morning_catchup_skips_when_it_already_ran_today(self) -> None:
        readiness_snapshot = {
            "status": "degraded",
            "components": {
                "forecast_monitoring": {
                    "status": "warning",
                    "items": [
                        {
                            "virus_typ": "Influenza A",
                            "status": "warning",
                            "accuracy_freshness_status": "expired",
                        }
                    ],
                }
            },
        }
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = object()

        with (
            patch.object(main, "utc_now", return_value=datetime(2026, 4, 15, 8, 30, 0)),
            patch.object(main, "try_advisory_lock", return_value=_lock_result(True)),
            patch.object(main, "get_db_context", return_value=_db_context(db)),
            patch.object(main, "chain", create=True) as chain_mock,
            patch.object(main, "OperationalRunRecorder") as recorder_cls,
            patch.object(main, "log_event"),
        ):
            run_metadata = main._run_startup_morning_catchup_once(readiness_snapshot)

        self.assertEqual(run_metadata["status"], "skipped")
        chain_mock.assert_not_called()
        recorder_cls.assert_not_called()

    def test_startup_morning_catchup_uses_detailed_snapshot_when_startup_snapshot_is_shallow(self) -> None:
        readiness_snapshot = {
            "status": "degraded",
            "components": {
                "forecast_monitoring": {
                    "status": "warning",
                    "items": [],
                }
            },
        }
        detailed_snapshot = {
            "status": "degraded",
            "components": {
                "forecast_monitoring": {
                    "status": "warning",
                    "items": [
                        {
                            "virus_typ": "Influenza A",
                            "status": "warning",
                            "accuracy_freshness_status": "expired",
                        }
                    ],
                }
            },
        }
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        recorder = MagicMock()
        recorder.record_event.return_value = {
            "run_id": "catchup-2",
            "status": "success",
            "action": "STARTUP_MORNING_CATCHUP",
        }
        ingestion_task = MagicMock()
        ingestion_task.si.return_value = "full-ingestion"
        xgboost_task = MagicMock()
        xgboost_task.si.return_value = "xgboost-training"
        regional_training_task = MagicMock()
        regional_training_task.si.return_value = "regional-training"
        live_task = MagicMock()
        live_task.si.return_value = "live-refresh"
        backtest_task = MagicMock()
        backtest_task.si.return_value = "backtest-refresh"
        accuracy_task = MagicMock()
        accuracy_task.si.return_value = "accuracy-refresh"
        snapshot_task = MagicMock()
        snapshot_task.si.return_value = "snapshot-refresh"
        opportunities_task = MagicMock()
        opportunities_task.si.return_value = "marketing-opportunities"
        fake_ml_tasks_module = SimpleNamespace(
            train_xgboost_model_task=xgboost_task,
            train_regional_models_task=regional_training_task,
            refresh_live_forecasts_task=live_task,
            refresh_market_backtests_task=backtest_task,
            compute_forecast_accuracy_task=accuracy_task,
            refresh_regional_operational_snapshots_task=snapshot_task,
        )
        fake_ingest_tasks_module = SimpleNamespace(run_full_ingestion_pipeline=ingestion_task)
        fake_media_tasks_module = SimpleNamespace(generate_marketing_opportunities_task=opportunities_task)
        chain_runner = MagicMock()

        with (
            patch.object(main, "utc_now", return_value=datetime(2026, 4, 15, 8, 30, 0)),
            patch.object(main, "try_advisory_lock", return_value=_lock_result(True)),
            patch.object(main, "get_db_context", return_value=_db_context(db)),
            patch.object(main, "OperationalRunRecorder", return_value=recorder),
            patch.object(main, "ProductionReadinessService") as readiness_service_cls,
            patch.dict(
                "sys.modules",
                {
                    "app.services.data_ingest.tasks": fake_ingest_tasks_module,
                    "app.services.media.tasks": fake_media_tasks_module,
                    "app.services.ml.tasks": fake_ml_tasks_module,
                },
            ),
            patch.object(main, "chain", return_value=chain_runner, create=True) as chain_mock,
            patch.object(main, "log_event"),
        ):
            readiness_service_cls.return_value.build_snapshot.return_value = detailed_snapshot
            run_metadata = main._run_startup_morning_catchup_once(readiness_snapshot)

        chain_mock.assert_called_once_with(
            "full-ingestion",
            "xgboost-training",
            "regional-training",
            "live-refresh",
            "backtest-refresh",
            "accuracy-refresh",
            "snapshot-refresh",
            "marketing-opportunities",
        )
        self.assertEqual(run_metadata["run_id"], "catchup-2")
