from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.database import MarketingOpportunity
from app.services.media.cockpit.constants import BUNDESLAND_NAMES, REGION_NAME_TO_CODE
from app.services.media.recommendation_contracts import to_card_response
from app.services.media.semantic_contracts import (
    normalize_confidence_pct,
    signal_confidence_contract,
)

LEGACY_TO_WORKFLOW = {
    "NEW": "DRAFT",
    "URGENT": "DRAFT",
    "SENT": "APPROVED",
    "CONVERTED": "ACTIVATED",
}


def build_recommendation_section(db: Session) -> dict[str, Any]:
    rows = db.query(MarketingOpportunity).order_by(
        MarketingOpportunity.urgency_score.desc(),
        MarketingOpportunity.created_at.desc(),
    ).limit(20).all()

    cards: list[dict[str, Any]] = []
    for row in rows:
        region_codes = extract_region_codes_from_row(row)
        primary_region = region_codes[0] if region_codes else "Gesamt"
        channel_mix = row.channel_mix or {"programmatic": 35, "social": 30, "search": 20, "ctv": 15}
        campaign_payload = row.campaign_payload or {}
        campaign = campaign_payload.get("campaign") or {}
        budget = campaign_payload.get("budget_plan") or {}
        measurement = campaign_payload.get("measurement_plan") or {}
        activation = campaign_payload.get("activation_window") or {}
        product_mapping = campaign_payload.get("product_mapping") or {}
        peix_context = campaign_payload.get("peix_context") or {}
        playbook = campaign_payload.get("playbook") or {}
        ai_meta = campaign_payload.get("ai_meta") or {}
        status = LEGACY_TO_WORKFLOW.get(str(row.status or "").upper(), row.status or "DRAFT")
        recommended_product = product_mapping.get("recommended_product") or row.product or "Atemwegslinie"
        decision_expectation = (campaign_payload.get("decision_brief") or {}).get("expectation") or {}
        signal_confidence_pct = (
            normalize_confidence_pct(decision_expectation.get("signal_confidence_pct"))
            or normalize_confidence_pct(decision_expectation.get("confidence_pct"))
            or normalize_confidence_pct(
                ((campaign_payload.get("forecast_assessment") or {}).get("event_forecast") or {}).get("confidence")
            )
        )
        signal_score = (
            _coerce_float((peix_context or {}).get("signal_score"))
            or _coerce_float((peix_context or {}).get("score"))
            or _coerce_float((peix_context or {}).get("impact_probability"))
        )
        opp_payload = {
            "id": row.opportunity_id,
            "status": status,
            "type": row.opportunity_type,
            "urgency_score": row.urgency_score,
            "priority_score": row.urgency_score,
            "brand": row.brand or "PEIX Partner",
            "product": recommended_product,
            "recommended_product": recommended_product,
            "region": primary_region,
            "region_codes": region_codes,
            "budget_shift_pct": row.budget_shift_pct if row.budget_shift_pct is not None else 15.0,
            "channel_mix": channel_mix,
            "activation_window": {
                "start": (
                    row.activation_start.isoformat() if row.activation_start
                    else activation.get("start")
                ),
                "end": (
                    row.activation_end.isoformat() if row.activation_end
                    else activation.get("end")
                ),
            },
            "recommendation_reason": row.recommendation_reason or (row.trigger_event or "Epidemiologisches Trigger-Signal"),
            "confidence": (
                round(float(signal_confidence_pct) / 100.0, 2)
                if signal_confidence_pct is not None
                else None
            ),
            "signal_score": signal_score,
            "signal_confidence_pct": signal_confidence_pct,
            "mapping_status": product_mapping.get("mapping_status"),
            "mapping_confidence": product_mapping.get("mapping_confidence"),
            "mapping_reason": product_mapping.get("mapping_reason"),
            "condition_key": product_mapping.get("condition_key"),
            "condition_label": product_mapping.get("condition_label"),
            "mapping_candidate_product": product_mapping.get("candidate_product"),
            "playbook_key": row.playbook_key or playbook.get("key"),
            "playbook_title": playbook.get("title"),
            "strategy_mode": row.strategy_mode or campaign_payload.get("strategy_mode"),
            "trigger_snapshot": campaign_payload.get("trigger_snapshot"),
            "guardrail_notes": (campaign_payload.get("guardrail_report") or {}).get("applied_fixes") or [],
            "ai_generation_status": ai_meta.get("status"),
            "campaign_name": campaign.get("campaign_name"),
            "primary_kpi": measurement.get("primary_kpi"),
            "peix_context": peix_context,
            "campaign_payload": campaign_payload,
            "campaign_preview": {
                "campaign_name": campaign.get("campaign_name"),
                "activation_window": {
                    "start": activation.get("start"),
                    "end": activation.get("end"),
                },
                "budget": {
                    "weekly_budget_eur": budget.get("weekly_budget_eur"),
                    "shift_pct": budget.get("budget_shift_pct"),
                    "shift_value_eur": budget.get("budget_shift_value_eur"),
                    "total_flight_budget_eur": budget.get("total_flight_budget_eur"),
                },
                "primary_kpi": measurement.get("primary_kpi"),
                "recommended_product": recommended_product,
                "mapping_status": product_mapping.get("mapping_status"),
            },
            "detail_url": f"/kampagnen/{row.opportunity_id}",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        card = to_card_response(opp_payload, include_preview=True)
        card.setdefault("field_contracts", {})
        card["field_contracts"]["signal_confidence_pct"] = signal_confidence_contract(
            source=str(
                (campaign_payload.get("trigger_snapshot") or {}).get("source")
                or "Signal-Fusion"
            ),
            derived_from="trigger_evidence.confidence",
        )
        cards.append(card)

    return {
        "total": len(cards),
        "cards": cards,
    }


def build_region_recommendation_refs(db: Session) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    rows = db.query(MarketingOpportunity).order_by(
        MarketingOpportunity.urgency_score.desc(),
        MarketingOpportunity.created_at.desc(),
    ).limit(250).all()

    for row in rows:
        status = LEGACY_TO_WORKFLOW.get(str(row.status or "").upper(), str(row.status or "DRAFT").upper())
        if status in {"DISMISSED", "EXPIRED"}:
            continue

        region_codes = extract_region_codes_from_row(row)
        if not region_codes:
            region_codes = sorted(BUNDESLAND_NAMES.keys())

        payload = {
            "card_id": row.opportunity_id,
            "detail_url": f"/kampagnen/{row.opportunity_id}",
            "status": status,
            "urgency_score": row.urgency_score,
            "priority_score": row.urgency_score,
            "brand": row.brand,
            "product": row.product,
        }

        for code in region_codes:
            if code not in refs:
                refs[code] = payload

    return refs


def extract_region_codes_from_row(row: MarketingOpportunity) -> list[str]:
    region_target = row.region_target or {}
    campaign_payload = row.campaign_payload or {}
    targeting = campaign_payload.get("targeting") or {}

    tokens: list[str] = []
    states = region_target.get("states")
    if isinstance(states, list):
        tokens.extend(str(item) for item in states)

    scope = targeting.get("region_scope")
    if isinstance(scope, list):
        tokens.extend(str(item) for item in scope)
    elif isinstance(scope, str):
        tokens.append(scope)

    normalized: set[str] = set()
    for token in tokens:
        lower = token.strip().lower()
        if lower in {"gesamt", "all", "de", "national", "deutschland"}:
            return []

        code = token.strip().upper()
        if code in BUNDESLAND_NAMES:
            normalized.add(code)
            continue

        mapped = REGION_NAME_TO_CODE.get(lower)
        if mapped:
            normalized.add(mapped)

    return sorted(normalized)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
