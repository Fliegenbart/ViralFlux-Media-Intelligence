import logging
import os
import time

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, task_success, task_prerun, task_postrun

from app.core.config import get_settings
from app.core.logging_config import setup_logging, log_event
from app.core.observability import (
    capture_exception,
    init_sentry,
    post_slack_alert,
    slack_task_allowlist,
)

settings = get_settings()
setup_logging(
    level=settings.LOG_LEVEL,
    json_format=settings.LOG_FORMAT == "json",
    service_name="viralflux-celery",
    environment=settings.ENVIRONMENT,
    app_version=settings.APP_VERSION,
)
logger = logging.getLogger(__name__)

# Fire-and-forget observability init. init_sentry is a no-op when
# SENTRY_DSN is unset, so local/dev runs stay quiet.
init_sentry(service_name="viralflux-celery")

# Hole die Redis-URL aus den Environment-Variablen (Fallback auf localhost für lokale Tests)
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", BROKER_URL)

celery_app = Celery(
    "viralflux_worker",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "app.services.data_ingest.tasks",
        "app.services.media.tasks",
        "app.services.ml.tasks",
        "app.services.research.tri_layer.tasks",
    ],  # Hintergrund-Jobs
)

# Celery CLI expects a top-level `app` attribute for `celery -A ...`
app = celery_app

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,  # wichtig für ML/LLM-Tasks
    timezone="Europe/Berlin",
    enable_utc=True,
    # Reliability: ack after task completes, reject on worker crash
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Time limits: prevent runaway tasks
    task_soft_time_limit=600,   # 10 min soft limit (SoftTimeLimitExceeded)
    task_time_limit=900,        # 15 min hard kill
    # Memory leak prevention
    worker_max_tasks_per_child=50,
    # Keep failed task results for inspection
    task_store_errors_even_if_ignored=True,
)


# ── Task Lifecycle Signals (Metrics + Error Logging) ────────────
_task_start_times: dict[str, float] = {}


@task_prerun.connect
def _on_task_prerun(task_id, task, *args, **kwargs):
    _task_start_times[task_id] = time.perf_counter()
    log_event(
        logger,
        "celery_task_started",
        task_name=task.name if task else "unknown",
        task_id=task_id,
    )


@task_postrun.connect
def _on_task_postrun(task_id, task, *args, **kwargs):
    start = _task_start_times.pop(task_id, None)
    if start is not None:
        duration = time.perf_counter() - start
        try:
            from app.core.metrics import celery_tasks_total, celery_task_duration_seconds
            celery_tasks_total.labels(task.name, "success").inc()
            celery_task_duration_seconds.labels(task.name).observe(duration)
        except Exception:
            pass
        log_event(
            logger,
            "celery_task_completed",
            task_name=task.name if task else "unknown",
            task_id=task_id,
            duration_ms=round(duration * 1000.0, 2),
        )


@task_failure.connect
def _on_task_failure(task_id, exception, traceback, sender, *args, **kwargs):
    _task_start_times.pop(task_id, None)
    task_name = sender.name if sender else "unknown"
    log_event(
        logger,
        "celery_task_failed",
        level=logging.ERROR,
        task_name=task_name,
        task_id=task_id,
        error_type=type(exception).__name__ if exception else "unknown",
        error_message=str(exception) if exception else "",
    )
    try:
        from app.core.metrics import celery_tasks_total
        celery_tasks_total.labels(task_name, "failure").inc()
    except Exception:
        pass

    # Sentry + Slack alert — both are quiet no-ops when the integrations are
    # not configured, so these calls stay safe for local runs.
    if exception is not None:
        capture_exception(exception)

    allowlist = slack_task_allowlist()
    if allowlist and task_name not in allowlist:
        return
    try:
        post_slack_alert(
            title=f":rotating_light: Celery-Task fehlgeschlagen · {task_name}",
            text=(
                f"*{type(exception).__name__ if exception else 'Unknown'}*: "
                f"{str(exception) if exception else '—'}"
            ),
            level="error",
            fields={
                "task_id": task_id or "—",
                "env": settings.ENVIRONMENT,
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("Slack alert post raised — swallowed to avoid masking failure")


@task_success.connect
def _on_task_success(result, sender, **kwargs):
    log_event(
        logger,
        "celery_task_success_signal",
        task_name=sender.name if sender else "unknown",
    )

# ── Celery Beat Schedule ──────────────────────────────────────────────────────
# Automatische Daten-Refreshes um Opportunities frisch zu halten.
celery_app.conf.beat_schedule = {
    # Taeglich 06:00 — Komplette Ingestion-Pipeline (RKI, AMELAG, GrippeWeb, Wetter, BfArM)
    "daily-full-ingestion": {
        "task": "run_full_ingestion_pipeline",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {},
    },
    # Monatlich am 1. um 07:00 — XGBoost Retraining mit neuen Daten
    "monthly-xgboost-training": {
        "task": "train_xgboost_model_task",
        "schedule": crontab(hour=7, minute=0, day_of_month="1"),
        "kwargs": {"virus_typ": None},  # alle 4 Typen
    },
    # Monatlich am 1. um 07:10 — Regionale Modelle nach frischer Ingestion neu trainieren
    "monthly-regional-model-training": {
        "task": "train_regional_models_task",
        "schedule": crontab(hour=7, minute=10, day_of_month="1"),
        "kwargs": {"virus_typ": None},
    },
    # Taeglich 07:30 — Frische Live-Forecasts in ml_forecasts persistieren
    "daily-live-forecast-refresh": {
        "task": "refresh_live_forecasts_task",
        "schedule": crontab(hour=7, minute=30),
        "kwargs": {},
    },
    # Taeglich 07:40 — Markt-Backtests nach frischem Training neu berechnen
    "daily-market-backtest-refresh": {
        "task": "refresh_market_backtests_task",
        "schedule": crontab(hour=7, minute=40),
        "kwargs": {},
    },
    # Taeglich 07:50 — Forecast-Accuracy Monitoring nach Daten- und Forecast-Refresh
    "daily-forecast-accuracy": {
        "task": "compute_forecast_accuracy_task",
        "schedule": crontab(hour=7, minute=50),
        "kwargs": {},
    },
    # Taeglich 08:00 — Regionale operative Snapshots fuer Readiness aktualisieren
    "daily-regional-operational-snapshot-refresh": {
        "task": "refresh_regional_operational_snapshots_task",
        "schedule": crontab(hour=8, minute=0),
        "kwargs": {},
    },
    # Montags 03:00 — RKI SurvStat Kreis-Daten (wochentlich, Rate-Limit-schonend)
    "weekly-survstat-kreis": {
        "task": "fetch_survstat_kreis_api",
        "schedule": crontab(hour=3, minute=0, day_of_week="monday"),
        "kwargs": {"years": None, "diseases": None},  # aktuelles + Vorjahr
    },
    # Taeglich 08:10 — Marketing-Opportunities aus frischen Forecasts und Gates generieren
    "daily-marketing-opportunities": {
        "task": "generate_marketing_opportunities_task",
        "schedule": crontab(hour=8, minute=10),
        "kwargs": {},
    },
    # Montags 08:30 — Woechentlicher Gelo Media Action Brief (nach allen Daten-Updates)
    "weekly-media-brief": {
        "task": "generate_weekly_brief_task",
        "schedule": crontab(hour=8, minute=30, day_of_week="monday"),
        "kwargs": {},
    },
}
