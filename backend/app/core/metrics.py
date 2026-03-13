"""Prometheus metrics for ViralFlux backend."""

from prometheus_client import Counter, Histogram, Info

# App info
app_info = Info("viralflux", "ViralFlux Media Intelligence")

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Celery task metrics
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total Celery tasks by name and status",
    ["task_name", "status"],
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration in seconds",
    ["task_name"],
)

# Data ingestion metrics
ingestion_records_total = Counter(
    "ingestion_records_total",
    "Total records ingested by source",
    ["source"],
)

ingestion_errors_total = Counter(
    "ingestion_errors_total",
    "Total ingestion errors by source",
    ["source"],
)
