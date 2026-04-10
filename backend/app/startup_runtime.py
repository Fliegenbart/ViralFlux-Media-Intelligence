from __future__ import annotations

from app.core.time import utc_now

import logging
import threading
from typing import Any, Callable


def safe_record_startup_readiness_once(
    *,
    readiness_snapshot: dict[str, Any],
    record_once: Callable[[dict[str, Any]], dict[str, Any]],
    settings_obj: Any,
    logger_obj: Any,
    log_event_fn: Callable[..., Any],
) -> dict[str, Any]:
    try:
        return record_once(readiness_snapshot)
    except Exception as exc:
        log_event_fn(
            logger_obj,
            "startup_readiness_record_degraded",
            level=logging.WARNING,
            error_message=str(exc),
        )
        return {
            "run_id": None,
            "action": "STARTUP_READINESS",
            "status": "warning",
            "summary": "Startup readiness snapshot was computed, but persistence failed.",
            "timestamp": utc_now().isoformat(),
            "environment": getattr(settings_obj, "ENVIRONMENT", None),
            "app_version": getattr(settings_obj, "APP_VERSION", None),
            "metadata": {
                "persisted": False,
                "singleton": True,
                "error_message": str(exc),
            },
        }


def launch_bfarm_startup_import_thread(
    *,
    target: Callable[[], None],
    thread_factory: Callable[..., Any] = threading.Thread,
):
    thread = thread_factory(
        target=target,
        daemon=True,
        name="startup-bfarm-import",
    )
    thread.start()
    return thread
