"""Persistence helpers for BacktestService history data."""

from __future__ import annotations

from typing import Optional

from app.core.time import utc_now
from app.models.database import BacktestPoint, BacktestRun


def persist_backtest_result(
    service,
    *,
    mode: str,
    virus_typ: str,
    target_source: str,
    target_key: str,
    target_label: str,
    result: dict,
    parameters: Optional[dict] = None,
    pd_module,
    uuid4_fn,
    logger_obj,
) -> Optional[str]:
    """Persistiert einen Backtest-Lauf inklusive Chart-Punkten."""
    try:
        run_id = f"bt_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4_fn().hex[:8]}"
        chart_data = result.get("chart_data", []) or []
        metrics_payload = dict(result.get("metrics", {}) or {})
        if result.get("decision_metrics") is not None:
            metrics_payload["decision_metrics"] = result.get("decision_metrics")
        if result.get("interval_coverage") is not None:
            metrics_payload["interval_coverage"] = result.get("interval_coverage")
        if result.get("event_calibration") is not None:
            metrics_payload["event_calibration"] = result.get("event_calibration")
        if result.get("quality_gate") is not None:
            metrics_payload["quality_gate"] = result.get("quality_gate")
        if result.get("timing_metrics") is not None:
            metrics_payload["timing_metrics"] = result.get("timing_metrics")

        run = BacktestRun(
            run_id=run_id,
            mode=mode,
            status="success",
            virus_typ=virus_typ,
            target_source=target_source,
            target_key=target_key,
            target_label=target_label,
            strict_vintage_mode=bool(
                result.get("walk_forward", {}).get(
                    "strict_vintage_mode",
                    service.strict_vintage_mode,
                )
            ),
            horizon_days=int(result.get("walk_forward", {}).get("horizon_days", 14)),
            min_train_points=int(result.get("walk_forward", {}).get("min_train_points", 20)),
            parameters=parameters or {},
            metrics=metrics_payload,
            baseline_metrics=result.get("baseline_metrics", {}),
            improvement_vs_baselines=result.get("improvement_vs_baselines", {}),
            optimized_weights=result.get("optimized_weights", {}),
            proof_text=result.get("proof_text"),
            llm_insight=result.get("llm_insight"),
            lead_lag=result.get("lead_lag"),
            chart_points=len(chart_data),
        )
        service.db.add(run)
        service.db.flush()

        points: list[BacktestPoint] = []
        for row in chart_data:
            date_raw = row.get("date")
            date_parsed = pd_module.to_datetime(date_raw, errors="coerce")
            if pd_module.isna(date_parsed):
                continue

            points.append(
                BacktestPoint(
                    run_id=run_id,
                    date=date_parsed.to_pydatetime(),
                    region=row.get("region"),
                    real_qty=float(row.get("real_qty")) if row.get("real_qty") is not None else None,
                    predicted_qty=float(row.get("predicted_qty")) if row.get("predicted_qty") is not None else None,
                    baseline_persistence=(
                        float(row.get("baseline_persistence"))
                        if row.get("baseline_persistence") is not None
                        else None
                    ),
                    baseline_seasonal=(
                        float(row.get("baseline_seasonal"))
                        if row.get("baseline_seasonal") is not None
                        else None
                    ),
                    bio=float(row.get("bio")) if row.get("bio") is not None else None,
                    psycho=float(row.get("psycho")) if row.get("psycho") is not None else None,
                    context=float(row.get("context")) if row.get("context") is not None else None,
                    extra={
                        "feature_date": row.get("feature_date"),
                        "source_mode": mode,
                    },
                )
            )

        if points:
            service.db.bulk_save_objects(points)

        service.db.commit()
        return run_id
    except Exception as exc:
        service.db.rollback()
        logger_obj.warning(f"Backtest-Persistenz fehlgeschlagen: {exc}")
        return None


def list_backtest_runs(service, *, mode: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Liefert persistierte Backtest-Läufe für die UI-Historie."""
    query = service.db.query(BacktestRun).order_by(BacktestRun.created_at.desc())
    if mode:
        query = query.filter(BacktestRun.mode == mode)

    rows = query.limit(max(1, min(limit, 200))).all()
    return [
        {
            "run_id": row.run_id,
            "mode": row.mode,
            "status": row.status,
            "virus_typ": row.virus_typ,
            "target_source": row.target_source,
            "target_key": row.target_key,
            "target_label": row.target_label,
            "strict_vintage_mode": row.strict_vintage_mode,
            "horizon_days": row.horizon_days,
            "metrics": row.metrics or {},
            "lead_lag": row.lead_lag or {},
            "chart_points": row.chart_points,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def get_backtest_run(service, run_id: str) -> dict | None:
    """Liefert einen persistierten Backtest-Lauf inklusive Chart-Punkten."""
    row = service.db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
    if not row:
        return None

    metrics = row.metrics or {}
    points = (
        service.db.query(BacktestPoint)
        .filter(BacktestPoint.run_id == run_id)
        .order_by(BacktestPoint.date.asc(), BacktestPoint.id.asc())
        .all()
    )

    chart_data = [
        {
            "date": point.date.date().isoformat() if point.date else None,
            "region": point.region,
            "real_qty": point.real_qty,
            "predicted_qty": point.predicted_qty,
            "baseline_persistence": point.baseline_persistence,
            "baseline_seasonal": point.baseline_seasonal,
            "bio": point.bio,
            "psycho": point.psycho,
            "context": point.context,
        }
        for point in points
        if point.date is not None
    ]

    return {
        "run_id": row.run_id,
        "mode": row.mode,
        "status": row.status,
        "virus_typ": row.virus_typ,
        "target_source": row.target_source,
        "target_key": row.target_key,
        "target_label": row.target_label,
        "metrics": metrics,
        "decision_metrics": metrics.get("decision_metrics"),
        "quality_gate": metrics.get("quality_gate"),
        "timing_metrics": metrics.get("timing_metrics"),
        "lead_lag": row.lead_lag or {},
        "proof_text": row.proof_text,
        "llm_insight": row.llm_insight,
        "chart_data": chart_data,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "walk_forward": {
            "horizon_days": row.horizon_days,
            "min_train_points": row.min_train_points,
            "strict_vintage_mode": row.strict_vintage_mode,
        },
    }
