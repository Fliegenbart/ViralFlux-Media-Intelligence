"""Operational run metadata and audit trail helpers."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import AuditLog


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except Exception:
            pass
    return str(value)


class OperationalRunRecorder:
    """Persist operational run metadata into the existing audit trail."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def record_event(
        self,
        *,
        action: str,
        status: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        reason: str | None = None,
        user: str = "system",
        entity_type: str = "OperationalRun",
        commit: bool = False,
    ) -> dict[str, Any]:
        run_metadata = {
            "run_id": uuid4().hex,
            "action": str(action or "").strip().upper(),
            "status": str(status or "").strip().lower(),
            "summary": str(summary or "").strip(),
            "timestamp": utc_now().isoformat(),
            "environment": self.settings.ENVIRONMENT,
            "app_version": self.settings.APP_VERSION,
            "metadata": _json_safe(dict(metadata or {})),
        }
        self.db.add(
            AuditLog(
                timestamp=utc_now(),
                user=user,
                action=run_metadata["action"],
                entity_type=entity_type,
                entity_id=None,
                old_value=None,
                new_value=run_metadata,
                reason=reason or run_metadata["summary"] or run_metadata["action"],
            )
        )
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return run_metadata
