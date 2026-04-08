"""ROI retrospective helpers for the marketing opportunity engine."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import func

from app.models.database import BacktestRun, MarketingOpportunity, SurvstatWeeklyData

if TYPE_CHECKING:
    from .opportunity_engine import MarketingOpportunityEngine


def get_roi_retrospective(engine: "MarketingOpportunityEngine") -> dict[str, Any]:
    """Estimate the value of past opportunities against observed respiratory demand."""
    all_opps = engine.db.query(MarketingOpportunity).all()
    if not all_opps:
        return {"available": False, "reason": "Keine Opportunities vorhanden"}

    acted_on = [o for o in all_opps if o.status in ("SENT", "APPROVED", "CONVERTED", "ACTIVATED")]
    missed = [o for o in all_opps if o.status in ("EXPIRED", "DISMISSED")]
    pending = [o for o in all_opps if o.status in ("NEW", "URGENT", "DRAFT", "READY")]

    avg_urgency_acted = (
        sum(o.urgency_score for o in acted_on) / len(acted_on)
        if acted_on else 0
    )
    avg_urgency_missed = (
        sum(o.urgency_score for o in missed) / len(missed)
        if missed else 0
    )

    latest_backtest = engine._latest_market_backtest()

    model_accuracy: dict[str, Any] = {}
    if latest_backtest and latest_backtest.metrics:
        metrics = latest_backtest.metrics
        quality_gate = metrics.get("quality_gate") or {}
        timing_metrics = metrics.get("timing_metrics") or {}
        overall_gate = bool(quality_gate.get("overall_passed"))
        lead_gate = bool(quality_gate.get("lead_passed", overall_gate))
        model_accuracy = {
            "r2_score": round(metrics.get("r2_score", 0), 3),
            "correlation": round(metrics.get("correlation", 0), 3),
            "mae": round(metrics.get("mae", 0), 1),
            "readiness_status": "GO" if (overall_gate and lead_gate) else "WATCH",
            "lead_passed": lead_gate,
            "best_lag_days": int(timing_metrics.get("best_lag_days", 0) or 0),
        }
        if latest_backtest.improvement_vs_baselines:
            persistence_val, seasonal_val = engine._extract_improvement_vs_baselines(
                latest_backtest.improvement_vs_baselines
            )
            model_accuracy["improvement_vs_persistence"] = round(float(persistence_val or 0.0), 1)
            model_accuracy["improvement_vs_seasonal"] = round(float(seasonal_val or 0.0), 1)

    signal_accuracy_samples: list[dict[str, Any]] = []
    for opp in all_opps[:30]:
        created = opp.created_at
        if not created:
            continue

        week_at_creation = (
            engine.db.query(SurvstatWeeklyData.incidence)
            .filter(
                SurvstatWeeklyData.bundesland == "Bundesweit",
                SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                SurvstatWeeklyData.week_start <= created,
            )
            .order_by(SurvstatWeeklyData.week_start.desc())
            .first()
        )

        peak_after = (
            engine.db.query(func.max(SurvstatWeeklyData.incidence))
            .filter(
                SurvstatWeeklyData.bundesland == "Bundesweit",
                SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                SurvstatWeeklyData.week_start > created,
                SurvstatWeeklyData.week_start <= created + timedelta(weeks=4),
            )
            .scalar()
        )

        if week_at_creation and week_at_creation[0] and peak_after:
            base = week_at_creation[0]
            if base > 0:
                demand_increase = round(((peak_after - base) / base) * 100, 1)
                signal_accuracy_samples.append(
                    {
                        "urgency": opp.urgency_score,
                        "demand_increase_pct": demand_increase,
                        "type": opp.opportunity_type,
                    }
                )

    converted_count = len([o for o in all_opps if o.status in ("CONVERTED", "ACTIVATED")])
    acted_count = len(acted_on)
    conversion_rate = round((converted_count / acted_count * 100) if acted_count else 0, 1)

    avg_demand_increase = (
        round(sum(s["demand_increase_pct"] for s in signal_accuracy_samples) / len(signal_accuracy_samples), 1)
        if signal_accuracy_samples else 0
    )

    high_urgency_hits = [
        s for s in signal_accuracy_samples
        if s["urgency"] >= 70 and s["demand_increase_pct"] > 0
    ]
    signal_hit_rate = (
        round(len(high_urgency_hits) / len([s for s in signal_accuracy_samples if s["urgency"] >= 70]) * 100, 1)
        if any(s["urgency"] >= 70 for s in signal_accuracy_samples) else 0
    )

    missed_high_urgency = [o for o in missed if o.urgency_score >= 70]

    return {
        "available": True,
        "summary": {
            "total_opportunities": len(all_opps),
            "acted_on": acted_count,
            "missed": len(missed),
            "pending": len(pending),
            "conversion_rate": conversion_rate,
        },
        "urgency_comparison": {
            "avg_urgency_acted": round(avg_urgency_acted, 1),
            "avg_urgency_missed": round(avg_urgency_missed, 1),
        },
        "signal_quality": {
            "avg_demand_increase_pct": avg_demand_increase,
            "signal_hit_rate_pct": signal_hit_rate,
            "samples_analyzed": len(signal_accuracy_samples),
        },
        "model_accuracy": model_accuracy,
        "missed_opportunity_value": {
            "high_urgency_missed": len(missed_high_urgency),
            "estimated_campaigns_lost": len(missed_high_urgency),
            "avg_potential_demand_lift_pct": avg_demand_increase,
        },
        "by_type": {},
    }
