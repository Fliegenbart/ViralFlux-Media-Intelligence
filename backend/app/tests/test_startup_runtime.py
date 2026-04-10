from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import app.startup_runtime as startup_runtime


def test_safe_record_startup_readiness_once_degrades_when_persist_fails(
    monkeypatch,
) -> None:
    logged_events: list[tuple[str, dict]] = []

    def fake_log_event(_logger, event: str, **kwargs):
        logged_events.append((event, kwargs))

    def broken_record_once(_snapshot):
        raise RuntimeError("audit table unavailable")

    monkeypatch.setattr(
        startup_runtime,
        "utc_now",
        lambda: datetime(2026, 4, 10, 12, 0, 0),
    )

    result = startup_runtime.safe_record_startup_readiness_once(
        readiness_snapshot={"status": "healthy"},
        record_once=broken_record_once,
        settings_obj=SimpleNamespace(
            ENVIRONMENT="production",
            APP_VERSION="1.0.0",
        ),
        logger_obj=object(),
        log_event_fn=fake_log_event,
    )

    assert result["action"] == "STARTUP_READINESS"
    assert result["status"] == "warning"
    assert result["summary"] == (
        "Startup readiness snapshot was computed, but persistence failed."
    )
    assert result["metadata"]["persisted"] is False
    assert result["metadata"]["singleton"] is True
    assert result["metadata"]["error_message"] == "audit table unavailable"
    assert result["timestamp"] == "2026-04-10T12:00:00"
    assert logged_events == [
        (
            "startup_readiness_record_degraded",
            {
                "level": startup_runtime.logging.WARNING,
                "error_message": "audit table unavailable",
            },
        )
    ]


def test_launch_bfarm_startup_import_thread_preserves_expected_thread_contract() -> None:
    captured: dict[str, object] = {}

    class FakeThread:
        def __init__(self, *, target, daemon, name):
            captured["target"] = target
            captured["daemon"] = daemon
            captured["name"] = name
            captured["started"] = False

        def start(self) -> None:
            captured["started"] = True

    def fake_target() -> None:
        return None

    thread = startup_runtime.launch_bfarm_startup_import_thread(
        target=fake_target,
        thread_factory=FakeThread,
    )

    assert isinstance(thread, FakeThread)
    assert captured == {
        "target": fake_target,
        "daemon": True,
        "name": "startup-bfarm-import",
        "started": True,
    }
