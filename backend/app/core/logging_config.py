"""Structured JSON logging configuration for ViralFlux."""

import logging
import sys
import uuid
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

# Correlation ID for request tracing across async tasks
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationFilter(logging.Filter):
    """Inject correlation_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get("")  # type: ignore[attr-defined]
        return True


def generate_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure root logger with JSON or text output."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s %(correlation_id)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s (%(correlation_id)s) %(message)s"
        )

    handler.setFormatter(formatter)
    handler.addFilter(CorrelationFilter())
    root.addHandler(handler)

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
