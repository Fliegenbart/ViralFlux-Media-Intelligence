"""Minimal observability hooks for Sentry + Slack alerts.

Both integrations are opt-in via environment variables and become no-ops
when the corresponding setting is empty. This keeps local development,
test runs, and CI clean of network calls while letting production wire
them in via .env.

Design goals:
  * Idempotent — callers can invoke ``init_sentry()`` multiple times
    without side effects beyond the first successful init.
  * Quiet failures — alerting itself must never raise into the caller.
    A blown Slack webhook cannot be allowed to mask a Celery task
    failure; log the hook error and move on.
  * Dependency-light — Slack uses urllib from stdlib. Sentry is the only
    new runtime dep (``sentry-sdk``, see requirements.txt).

The Celery and FastAPI entrypoints call ``init_sentry`` once; Celery's
``task_failure`` signal handler calls ``post_slack_alert`` once per
failing task.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_sentry_initialized = False
_sentry_lock = threading.Lock()


def init_sentry(*, service_name: str) -> bool:
    """Initialise Sentry once per process.

    Returns ``True`` when Sentry is active after the call, ``False`` when
    it is disabled or not installed. Safe to call from multiple entrypoints
    (FastAPI startup + Celery worker boot).
    """
    global _sentry_initialized
    with _sentry_lock:
        if _sentry_initialized:
            return True
        settings = get_settings()
        dsn = (settings.SENTRY_DSN or "").strip()
        if not dsn:
            return False
        try:
            import sentry_sdk
        except ImportError:
            logger.warning("sentry_sdk not installed — SENTRY_DSN set but package missing")
            return False
        try:
            sentry_sdk.init(
                dsn=dsn,
                environment=settings.ENVIRONMENT,
                release=settings.APP_VERSION,
                traces_sample_rate=float(settings.SENTRY_TRACES_SAMPLE_RATE or 0.0),
                send_default_pii=False,
            )
            sentry_sdk.set_tag("service", service_name)
            _sentry_initialized = True
            logger.info("Sentry initialised for service=%s env=%s", service_name, settings.ENVIRONMENT)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Sentry initialisation failed — continuing without it")
            return False


def capture_exception(exc: BaseException) -> None:
    """Forward an exception to Sentry when initialised; silent otherwise."""
    if not _sentry_initialized:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        logger.exception("Sentry capture_exception failed — swallowed to avoid masking caller")


def post_slack_alert(
    *,
    title: str,
    text: str,
    level: str = "warning",
    fields: dict[str, Any] | None = None,
) -> bool:
    """Fire a Slack-incoming-webhook message. Returns True on HTTP 2xx.

    Never raises — webhook failures are logged and swallowed so upstream
    task_failure handlers cannot be tripped up by an alerting outage.
    """
    settings = get_settings()
    webhook = (settings.SLACK_ALERT_WEBHOOK_URL or "").strip()
    if not webhook:
        return False

    colour = {
        "info": "#36a64f",
        "warning": "#f2c744",
        "error": "#d13838",
    }.get(level.lower(), "#808080")

    attachment: dict[str, Any] = {
        "color": colour,
        "title": title,
        "text": text,
        "mrkdwn_in": ["text"],
    }
    if fields:
        attachment["fields"] = [
            {"title": str(k), "value": str(v), "short": len(str(v)) <= 40}
            for k, v in fields.items()
        ]

    payload = {
        "attachments": [attachment],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                logger.warning("Slack webhook returned %s", resp.status)
            return ok
    except urllib.error.URLError:
        logger.exception("Slack webhook network error — alert dropped")
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Slack webhook unexpected error — alert dropped")
        return False


def slack_task_allowlist() -> set[str]:
    """Parse the comma-separated allowlist of task names for Slack alerts.

    An empty allowlist means "alert on every failing task"; callers should
    treat the empty set as a wildcard.
    """
    raw = (get_settings().SLACK_ALERT_TASK_ALLOWLIST or "").strip()
    if not raw:
        return set()
    return {segment.strip() for segment in raw.split(",") if segment.strip()}
