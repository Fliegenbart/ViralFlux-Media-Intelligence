import os

from celery import Celery
from celery.schedules import crontab

# Hole die Redis-URL aus den Environment-Variablen (Fallback auf localhost fuer lokale Tests)
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
    ],  # Hintergrund-Jobs
)

# Celery CLI expects a top-level `app` attribute for `celery -A ...`
app = celery_app

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,  # wichtig fuer ML/LLM-Tasks
    timezone="Europe/Berlin",
    enable_utc=True,
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
    # Taeglich 06:30 — Marketing-Opportunities aus frischen Signalen generieren
    "daily-marketing-opportunities": {
        "task": "generate_marketing_opportunities_task",
        "schedule": crontab(hour=6, minute=30),
        "kwargs": {},
    },
    # Taeglich 07:00 — XGBoost Retraining mit neuen Daten
    "daily-xgboost-training": {
        "task": "train_xgboost_model_task",
        "schedule": crontab(hour=7, minute=0),
        "kwargs": {"virus_type": None},  # alle 4 Typen
    },
    # Montags 03:00 — RKI SurvStat Kreis-Daten (wochentlich, Rate-Limit-schonend)
    "weekly-survstat-kreis": {
        "task": "fetch_survstat_kreis_api",
        "schedule": crontab(hour=3, minute=0, day_of_week="monday"),
        "kwargs": {"years": None, "diseases": None},  # aktuelles + Vorjahr
    },
    # Taeglich 08:00 — Forecast-Accuracy Monitoring (nach Ingestion + Training)
    "daily-forecast-accuracy": {
        "task": "compute_forecast_accuracy_task",
        "schedule": crontab(hour=8, minute=0),
        "kwargs": {},
    },
    # Montags 08:30 — Woechentlicher Gelo Media Action Brief (nach allen Daten-Updates)
    "weekly-media-brief": {
        "task": "generate_weekly_brief_task",
        "schedule": crontab(hour=8, minute=30, day_of_week="monday"),
        "kwargs": {},
    },
}
