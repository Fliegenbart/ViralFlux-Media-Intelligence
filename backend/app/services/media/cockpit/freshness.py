from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.database import (
    AREKonsultation,
    BacktestRun,
    GoogleTrendsData,
    MarketingOpportunity,
    NotaufnahmeSyndromData,
    PollenData,
    SurvstatWeeklyData,
    WastewaterAggregated,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals

SOURCE_SLA_DAYS = {
    "wastewater": 10,
    "are_konsultation": 14,
    "notaufnahme": 3,
    "survstat": 14,
    "weather": 2,
    "pollen": 2,
    "google_trends": 4,
    "bfarm_shortage": 7,
}

SOURCE_LABELS = {
    "wastewater": "AMELAG Abwasser",
    "are_konsultation": "RKI ARE",
    "notaufnahme": "RKI/AKTIN Notaufnahme",
    "survstat": "RKI SURVSTAT",
    "weather": "DWD/BrightSky Wetter",
    "pollen": "DWD Pollen",
    "google_trends": "Google Trends",
    "bfarm_shortage": "BfArM Engpässe",
}


def build_source_freshness_summary(source_status: dict[str, Any]) -> dict[str, Any]:
    items = source_status.get("items") or []
    core_source_keys = ("wastewater", "survstat", "are_konsultation", "notaufnahme")
    core_sources = [item for item in items if item.get("source_key") in core_source_keys]
    degraded_sources = [
        item for item in items
        if item.get("freshness_state") in {"stale", "no_data"}
    ]
    return {
        "live_ratio": source_status.get("live_ratio"),
        "live_count": source_status.get("live_count"),
        "total": source_status.get("total"),
        "core_sources": core_sources,
        "degraded_sources": degraded_sources,
    }


def build_data_freshness(
    db: Session,
    *,
    normalize_freshness_timestamp: Callable[..., str | None],
) -> dict[str, Any]:
    now = utc_now()

    def _max_date_for(model_cls: Any, *col_names: str) -> str | None:
        for col_name in col_names:
            col = getattr(model_cls, col_name, None)
            if col is None:
                continue
            value = db.query(func.max(col)).scalar()
            if value:
                return normalize_freshness_timestamp(value, now=now)
        return None

    bfarm_freshness = None
    signals = get_cached_signals() or {}
    analysis_date = signals.get("analysis_date")
    if analysis_date:
        try:
            bfarm_freshness = normalize_freshness_timestamp(
                datetime.fromisoformat(str(analysis_date)),
                now=now,
            )
        except ValueError:
            bfarm_freshness = None

    return {
        "wastewater": _max_date_for(WastewaterAggregated, "available_time", "datum", "created_at"),
        "are_konsultation": _max_date_for(AREKonsultation, "available_time", "datum", "created_at"),
        "survstat": _max_date_for(SurvstatWeeklyData, "available_time", "week_start", "created_at"),
        "notaufnahme": _max_date_for(NotaufnahmeSyndromData, "datum", "created_at"),
        "weather": _max_date_for(WeatherData, "available_time", "datum", "created_at"),
        "pollen": _max_date_for(PollenData, "available_time", "datum", "created_at"),
        "google_trends": _max_date_for(GoogleTrendsData, "available_time", "datum", "created_at"),
        "bfarm_shortage": bfarm_freshness,
        "marketing": _max_date_for(MarketingOpportunity, "updated_at", "created_at"),
        "backtest": _max_date_for(BacktestRun, "created_at"),
    }


def build_source_status(data_freshness: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()

    items = []
    live_count = 0
    for source_key, sla_days in SOURCE_SLA_DAYS.items():
        raw_ts = data_freshness.get(source_key)
        parsed = None
        if raw_ts:
            try:
                parsed = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.replace(tzinfo=None)
            except ValueError:
                parsed = None

        age_days = None
        if parsed is not None:
            age_days = max(0.0, (now - parsed).total_seconds() / 86400.0)

        is_live = bool(parsed is not None and age_days is not None and age_days <= float(sla_days))
        freshness_state = "live" if is_live else ("stale" if parsed else "no_data")
        status_color = "green" if freshness_state == "live" else "amber"
        feed_reachable = parsed is not None
        if is_live:
            live_count += 1

        items.append({
            "source_key": source_key,
            "label": SOURCE_LABELS.get(source_key, source_key),
            "last_updated": parsed.isoformat() if parsed else None,
            "age_days": round(age_days, 2) if age_days is not None else None,
            "sla_days": sla_days,
            "feed_reachable": feed_reachable,
            "feed_status_color": "green" if feed_reachable else "amber",
            "freshness_state": freshness_state,
            "is_live": is_live,
            "status_color": status_color,
        })

    items.sort(key=lambda row: (not row["is_live"], row["source_key"]))

    return {
        "items": items,
        "live_count": live_count,
        "total": len(items),
        "live_ratio": round((live_count / len(items)) * 100.0, 1) if items else 0.0,
    }
