"""Campaign write/export helpers for the marketing opportunity engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.time import utc_now
from app.models.database import AuditLog, MarketingOpportunity

from .opportunity_engine_constants import ALLOWED_TRANSITIONS, WORKFLOW_STATUSES, WORKFLOW_TO_LEGACY

if TYPE_CHECKING:
    from .opportunity_engine import MarketingOpportunityEngine


def update_campaign(
    engine: "MarketingOpportunityEngine",
    opportunity_id: str,
    *,
    activation_window: dict | None = None,
    budget: dict | None = None,
    channel_plan: list[dict] | None = None,
    kpi_targets: dict | None = None,
) -> dict:
    row = (
        engine.db.query(MarketingOpportunity)
        .filter(MarketingOpportunity.opportunity_id == opportunity_id)
        .first()
    )
    if not row:
        return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

    payload = (row.campaign_payload or {}).copy()
    payload.setdefault("meta", {
        "version": "1.0",
        "generated_at": utc_now().isoformat() + "Z",
        "generator": "ViralFlux-Media-v3",
    })

    if activation_window:
        start = engine._parse_iso_datetime(activation_window.get("start"))
        end = engine._parse_iso_datetime(activation_window.get("end"))
        if not start or not end:
            return {"error": "activation_window.start und activation_window.end sind erforderlich"}
        if start > end:
            return {"error": "activation_window.start darf nicht nach activation_window.end liegen"}

        payload["activation_window"] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "flight_days": max(1, (end - start).days + 1),
        }
        row.activation_start = start
        row.activation_end = end

    if budget:
        weekly = float(budget.get("weekly_budget_eur", 0.0))
        shift_pct = float(budget.get("budget_shift_pct", 0.0))
        if weekly < 0:
            return {"error": "Budgets dürfen nicht negativ sein"}
        if shift_pct > 100 or shift_pct < -100:
            return {"error": "budget_shift_pct muss zwischen -100 und 100 liegen"}

        shift_value = round(weekly * (abs(shift_pct) / 100.0), 2)
        window = payload.get("activation_window") or {}
        flight_days = int(window.get("flight_days") or 7)
        total_flight_budget = round((weekly / 7.0) * flight_days, 2)

        payload["budget_plan"] = {
            "weekly_budget_eur": weekly,
            "budget_shift_pct": shift_pct,
            "budget_shift_value_eur": shift_value,
            "total_flight_budget_eur": total_flight_budget,
            "currency": "EUR",
        }
        row.budget_shift_pct = shift_pct

    if channel_plan is not None:
        if not channel_plan:
            return {"error": "channel_plan darf nicht leer sein"}

        total_share = round(sum(float(item.get("share_pct", 0.0)) for item in channel_plan), 1)
        if abs(total_share - 100.0) > 0.2:
            return {"error": "Channel-Shares müssen in Summe 100 ergeben"}

        budget_plan = payload.get("budget_plan") or {}
        shift_value = abs(float(budget_plan.get("budget_shift_value_eur", 0.0)))

        normalized = []
        mix = {}
        for item in channel_plan:
            channel = str(item.get("channel", "")).strip().lower()
            share = round(float(item.get("share_pct", 0.0)), 1)
            mix[channel] = share
            normalized.append(
                {
                    "channel": channel,
                    "role": item.get("role") or "reach",
                    "share_pct": share,
                    "budget_eur": round(shift_value * (share / 100.0), 2),
                    "formats": item.get("formats") or [],
                    "message_angle": item.get("message_angle") or "Verfügbarkeit + früher Bedarf",
                    "kpi_primary": item.get("kpi_primary") or "CTR",
                    "kpi_secondary": item.get("kpi_secondary") or ["CPM"],
                }
            )

        payload["channel_plan"] = normalized
        row.channel_mix = mix

    if kpi_targets:
        measurement = payload.get("measurement_plan") or {}
        measurement["primary_kpi"] = kpi_targets.get("primary_kpi") or measurement.get("primary_kpi")
        measurement["secondary_kpis"] = kpi_targets.get("secondary_kpis") or measurement.get("secondary_kpis") or []
        measurement["success_criteria"] = kpi_targets.get("success_criteria") or measurement.get("success_criteria")
        payload["measurement_plan"] = measurement

    row.campaign_payload = payload
    row.updated_at = utc_now()
    engine.db.commit()
    return engine._model_to_dict(row, normalize_status=True)


def update_status(
    engine: "MarketingOpportunityEngine",
    opportunity_id: str,
    new_status: str,
    *,
    dismiss_reason: str | None = None,
    dismiss_comment: str | None = None,
) -> dict:
    """Status einer Opportunity aktualisieren (Workflow + Legacy kompatibel)."""
    target = engine._normalize_workflow_status(new_status)
    if target not in WORKFLOW_STATUSES:
        return {"error": f"Ungültiger Status: {new_status}. Erlaubt: {sorted(WORKFLOW_STATUSES)}"}

    opp = (
        engine.db.query(MarketingOpportunity)
        .filter(MarketingOpportunity.opportunity_id == opportunity_id)
        .first()
    )
    if not opp:
        return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

    current = engine._normalize_workflow_status(opp.status)
    if current != target and target not in ALLOWED_TRANSITIONS.get(current, set()):
        return {"error": f"Ungültiger Transition: {current} -> {target}"}

    old_status = current
    opp.status = target
    opp.updated_at = utc_now()

    payload = (opp.campaign_payload or {}).copy()
    campaign = (payload.get("campaign") or {}).copy()
    campaign["status"] = target
    payload["campaign"] = campaign

    if target == "DISMISSED" and (dismiss_reason or dismiss_comment):
        payload["dismiss_info"] = {
            "reason": dismiss_reason or "",
            "comment": (dismiss_comment or "").strip()[:500],
            "dismissed_at": utc_now().isoformat() + "Z",
        }

    opp.campaign_payload = payload

    engine.db.add(AuditLog(
        user="system",
        action="STATUS_CHANGE",
        entity_type="MarketingOpportunity",
        entity_id=opp.id,
        old_value=old_status,
        new_value=target,
        reason=opportunity_id,
    ))

    engine.db.commit()
    return {
        "opportunity_id": opportunity_id,
        "old_status": old_status,
        "new_status": target,
        "legacy_status": WORKFLOW_TO_LEGACY.get(target, target),
    }


def export_crm_json(
    engine: "MarketingOpportunityEngine",
    opportunity_ids: list[str] | None = None,
    *,
    system_version: str,
) -> dict[str, Any]:
    """CRM-Export: Markiert Opportunities als exportiert."""
    query = engine.db.query(MarketingOpportunity)

    if opportunity_ids:
        query = query.filter(MarketingOpportunity.opportunity_id.in_(opportunity_ids))
    else:
        query = query.filter(
            MarketingOpportunity.status.in_(["NEW", "URGENT", "DRAFT", "READY"])
        )

    results = query.order_by(MarketingOpportunity.urgency_score.desc()).all()

    now = utc_now()
    for opp in results:
        opp.exported_at = now

    engine.db.commit()

    opportunities = [engine._model_to_dict(row, normalize_status=True) for row in results]
    return {
        "meta": {
            "generated_at": now.isoformat() + "Z",
            "system_version": system_version,
            "total_opportunities": len(opportunities),
            "exported_at": now.isoformat() + "Z",
        },
        "opportunities": opportunities,
    }
