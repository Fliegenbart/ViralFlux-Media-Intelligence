from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import BacktestRun


def build_backtest_summary(
    db: Session,
    *,
    virus_typ: str,
    target_source: str,
) -> dict:
    latest_market_query = db.query(BacktestRun).filter(
        BacktestRun.mode == "MARKET_CHECK",
        BacktestRun.virus_typ == virus_typ,
    )
    if target_source:
        latest_market_query = latest_market_query.filter(
            func.upper(BacktestRun.target_source) == str(target_source).strip().upper()
        )
    latest_market = latest_market_query.order_by(BacktestRun.created_at.desc()).first()

    latest_customer = db.query(BacktestRun).filter(
        BacktestRun.mode == "CUSTOMER_CHECK",
        BacktestRun.virus_typ == virus_typ,
    ).order_by(BacktestRun.created_at.desc()).first()

    def _pack(row: BacktestRun | None) -> dict | None:
        if not row:
            return None
        metrics = row.metrics or {}
        return {
            "run_id": row.run_id,
            "mode": row.mode,
            "target_source": row.target_source,
            "target_label": row.target_label,
            "metrics": metrics,
            "decision_metrics": metrics.get("decision_metrics"),
            "interval_coverage": metrics.get("interval_coverage"),
            "event_calibration": metrics.get("event_calibration"),
            "quality_gate": metrics.get("quality_gate"),
            "timing_metrics": metrics.get("timing_metrics"),
            "lead_lag": row.lead_lag or {},
            "proof_text": row.proof_text,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    recent_runs = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(8).all()

    return {
        "target_source": target_source,
        "latest_market": _pack(latest_market),
        "latest_customer": _pack(latest_customer),
        "recent_runs": [
            {
                "run_id": row.run_id,
                "mode": row.mode,
                "target_source": row.target_source,
                "virus_typ": row.virus_typ,
                "metrics": row.metrics or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent_runs
        ],
    }
