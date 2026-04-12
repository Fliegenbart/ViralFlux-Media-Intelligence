"""Read/query helpers for the marketing opportunity engine."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func

from app.core.time import utc_now
from app.models.database import MarketingOpportunity

if TYPE_CHECKING:
    from .opportunity_engine import MarketingOpportunityEngine


def get_opportunities(
    engine: "MarketingOpportunityEngine",
    *,
    type_filter: str | None = None,
    status_filter: str | None = None,
    brand_filter: str | None = None,
    min_urgency: float | None = None,
    limit: int = 50,
    skip: int = 0,
    normalize_status: bool = True,
) -> list[dict]:
    """Gespeicherte Opportunities mit Filtern abrufen."""
    query = engine.db.query(MarketingOpportunity).order_by(
        MarketingOpportunity.urgency_score.desc(),
        MarketingOpportunity.created_at.desc(),
    )

    if type_filter:
        query = query.filter(MarketingOpportunity.opportunity_type == type_filter)
    if status_filter:
        query = query.filter(MarketingOpportunity.status.in_(engine._status_filter_values(status_filter)))
    if brand_filter:
        canonical_brand = engine._canonical_brand(brand_filter)
        query = query.filter(func.lower(MarketingOpportunity.brand) == canonical_brand)
    if min_urgency is not None:
        query = query.filter(MarketingOpportunity.urgency_score >= min_urgency)

    results = query.offset(skip).limit(limit).all()
    return [engine._model_to_dict(row, normalize_status=normalize_status) for row in results]


def count_opportunities(
    engine: "MarketingOpportunityEngine",
    *,
    type_filter: str | None = None,
    status_filter: str | None = None,
    brand_filter: str | None = None,
    min_urgency: float | None = None,
) -> int:
    """Gesamtanzahl der Opportunities mit denselben Filtern."""
    query = engine.db.query(func.count(MarketingOpportunity.id))

    if type_filter:
        query = query.filter(MarketingOpportunity.opportunity_type == type_filter)
    if status_filter:
        query = query.filter(MarketingOpportunity.status.in_(engine._status_filter_values(status_filter)))
    if brand_filter:
        canonical_brand = engine._canonical_brand(brand_filter)
        query = query.filter(func.lower(MarketingOpportunity.brand) == canonical_brand)
    if min_urgency is not None:
        query = query.filter(MarketingOpportunity.urgency_score >= min_urgency)

    return query.scalar() or 0


def get_recommendation_by_id(
    engine: "MarketingOpportunityEngine",
    opportunity_id: str,
) -> dict | None:
    row = (
        engine.db.query(MarketingOpportunity)
        .filter(MarketingOpportunity.opportunity_id == opportunity_id)
        .first()
    )
    if not row:
        return None
    return engine._model_to_dict(row, normalize_status=True)


def get_stats(engine: "MarketingOpportunityEngine") -> dict:
    """Aggregierte Statistiken."""
    total = engine.db.query(MarketingOpportunity).count()

    by_type = dict(
        engine.db.query(
            MarketingOpportunity.opportunity_type,
            func.count(MarketingOpportunity.id),
        )
        .group_by(MarketingOpportunity.opportunity_type)
        .all()
    )

    raw_by_status = dict(
        engine.db.query(
            MarketingOpportunity.status,
            func.count(MarketingOpportunity.id),
        )
        .group_by(MarketingOpportunity.status)
        .all()
    )

    by_status: dict[str, int] = {}
    for status, count in raw_by_status.items():
        normalized = engine._normalize_workflow_status(status)
        by_status[normalized] = by_status.get(normalized, 0) + count

    avg_urgency = engine.db.query(func.avg(MarketingOpportunity.urgency_score)).scalar()

    recent = (
        engine.db.query(MarketingOpportunity)
        .filter(MarketingOpportunity.created_at >= utc_now() - timedelta(days=7))
        .count()
    )

    daily_counts: list[int] = []
    now = utc_now()
    for days_ago in range(6, -1, -1):
        day_start = (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = (
            engine.db.query(MarketingOpportunity)
            .filter(
                MarketingOpportunity.created_at >= day_start,
                MarketingOpportunity.created_at < day_end,
            )
            .count()
        )
        daily_counts.append(count)

    return {
        "total": total,
        "recent_7d": recent,
        "daily_counts_7d": daily_counts,
        "by_type": by_type,
        "by_status": by_status,
        "avg_urgency": round(avg_urgency, 1) if avg_urgency else 0,
    }
