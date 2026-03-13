"""Audit trail helper for tracking user actions."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    *,
    user: str,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an audit log entry to the database.

    Usage:
        from app.core.audit import log_audit
        log_audit(db, user=current_user["sub"], action="approve",
                  entity_type="recommendation", entity_id=rec_id)
    """
    try:
        from app.models.database import AuditLog

        entry = AuditLog(
            user=user,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            ip_address=ip_address,
        )
        db.add(entry)
        db.flush()
    except Exception as exc:
        logger.warning("Audit log write failed (non-blocking): %s", exc)
