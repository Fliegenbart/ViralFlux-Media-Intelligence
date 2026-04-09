from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch


os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "very-strong-admin-password")

from app import main


@contextmanager
def _lock_result(acquired: bool):
    yield acquired


@contextmanager
def _db_context(db: object):
    yield db


class StartupSingletonTests(unittest.TestCase):
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

    def test_startup_does_not_launch_bfarm_thread_when_flag_is_disabled(self) -> None:
        with (
            patch.object(
                main,
                "settings",
                SimpleNamespace(
                    APP_NAME=main.settings.APP_NAME,
                    APP_VERSION=main.settings.APP_VERSION,
                    ENVIRONMENT=main.settings.ENVIRONMENT,
                    EFFECTIVE_STARTUP_STRICT_READINESS=main.settings.EFFECTIVE_STARTUP_STRICT_READINESS,
                    STARTUP_BFARM_IMPORT_ENABLED=False,
                ),
            ),
            patch.object(main, "_launch_bfarm_startup_import_thread") as launch_mock,
            patch.object(main, "check_db_connection", AsyncMock(return_value=True)),
            patch.object(main, "init_db", MagicMock(return_value={"status": "ok"})),
            patch.object(
                main.ProductionReadinessService,
                "build_snapshot",
                lambda self, deep_checks=False: {"status": "healthy", "blockers": []},
            ),
            patch.object(main, "_record_startup_readiness_once", lambda *_args, **_kwargs: {"run_id": "test"}),
        ):
            asyncio.run(main.startup_event())

        launch_mock.assert_not_called()
