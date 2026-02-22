import os

from celery import Celery

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
