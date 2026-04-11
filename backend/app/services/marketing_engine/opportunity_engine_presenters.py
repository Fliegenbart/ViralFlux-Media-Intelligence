"""Presentation and output-shaping helpers for the marketing opportunity engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.models.database import MarketingOpportunity
from app.services.media.copy_service import (
    build_decision_basis_text,
    build_decision_summary_text,
    public_condition_label,
    public_event_label,
    public_reason_text,
    public_source_label,
)
from app.services.media.semantic_contracts import (
    forecast_probability_contract,
    priority_score_contract,
    ranking_signal_contract,
    signal_confidence_contract,
)

from .opportunity_engine_constants import BUNDESLAND_NAMES, WORKFLOW_TO_LEGACY
from .opportunity_engine_helpers import (
    confidence_pct,
    fact_label,
    public_fact_value,
    secondary_products,
)

if TYPE_CHECKING:
    from .opportunity_engine import MarketingOpportunityEngine


def decision_facts(
    engine: "MarketingOpportunityEngine",
    *,
    trigger_snapshot: dict[str, Any],
    trigger_evidence: dict[str, Any],
    peix_context: dict[str, Any],
    confidence_pct_value: float | None,
    forecast_assessment: dict[str, Any] | None = None,
    opportunity_assessment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del engine
    facts: list[dict[str, Any]] = []
    ranking_signal_source = "RankingSignal"
    raw_source = (
        trigger_evidence.get("source")
        or trigger_snapshot.get("source")
        or "Signal-Fusion"
    )
    source = public_source_label(raw_source) or raw_source
    values = trigger_snapshot.get("values")
    if isinstance(values, dict):
        for key in sorted(values.keys()):
            value = values.get(key)
            if isinstance(value, (str, int, float, bool)):
                facts.append(
                    {
                        "key": str(key),
                        "label": fact_label(str(key)),
                        "value": public_fact_value(str(key), value),
                        "source": source,
                    }
                )

    event = trigger_evidence.get("event") or trigger_snapshot.get("event")
    if event:
        facts.append(
            {
                "key": "trigger_event",
                "label": "Signal",
                "value": public_event_label(str(event)),
                "source": source,
            }
        )

    lead_time = trigger_evidence.get("lead_time_days") or trigger_snapshot.get("lead_time_days")
    if lead_time is not None:
        facts.append(
            {
                "key": "lead_time_days",
                "label": "Modell Lead-Time (Tage)",
                "value": lead_time,
                "source": source,
            }
        )

    score = peix_context.get("score")
    if score is not None:
        facts.append(
            {
                "key": "signal_score",
                "label": "Signal-Score",
                "value": score,
                "source": ranking_signal_source,
            }
        )

    impact = peix_context.get("impact_probability")
    if impact is not None:
        facts.append(
            {
                "key": "impact_probability",
                "label": "Signal-Score (%)",
                "value": impact,
                "source": ranking_signal_source,
            }
        )

    if confidence_pct_value is not None:
        facts.append(
            {
                "key": "signal_confidence_pct",
                "label": "Signal-Konfidenz (%)",
                "value": confidence_pct_value,
                "source": source,
            }
        )

    event_forecast = (forecast_assessment or {}).get("event_forecast") or {}
    if event_forecast.get("event_probability") is not None:
        facts.append(
            {
                "key": "event_probability_pct",
                "label": "Event-Wahrscheinlichkeit",
                "value": round(float(event_forecast.get("event_probability") or 0.0) * 100.0, 1),
                "source": "ForecastDecisionService",
            }
        )
    quality = (forecast_assessment or {}).get("forecast_quality") or {}
    if quality.get("forecast_readiness"):
        facts.append(
            {
                "key": "forecast_readiness",
                "label": "Forecast-Readiness",
                "value": quality.get("forecast_readiness"),
                "source": "Backtest-Promotion-Gate",
            }
        )

    if opportunity_assessment and opportunity_assessment.get("truth_readiness"):
        facts.append(
            {
                "key": "truth_readiness",
                "label": "Truth-Readiness",
                "value": opportunity_assessment.get("truth_readiness"),
                "source": "Outcome-Coverage",
            }
        )
    if opportunity_assessment and opportunity_assessment.get("decision_priority_index") is not None:
        facts.append(
            {
                "key": "decision_priority_index",
                "label": "Decision-Priority-Index",
                "value": float(opportunity_assessment.get("decision_priority_index") or 0.0),
                "source": "Forecast-first Ranking",
            }
        )

    return facts


def build_decision_brief(
    engine: "MarketingOpportunityEngine",
    *,
    urgency_score: float | None,
    recommendation_reason: str | None,
    trigger_context: dict[str, Any],
    trigger_snapshot: dict[str, Any],
    trigger_evidence: dict[str, Any],
    peix_context: dict[str, Any],
    region_codes: list[str],
    condition_key: str | None,
    condition_label: str | None,
    recommended_product: str | None,
    mapping_status: str | None,
    mapping_reason: str | None,
    mapping_candidate_product: str | None,
    suggested_products: Any,
    budget_shift_pct: float | None,
    budget_shift_pct_fallback: float | None,
    forecast_assessment: dict[str, Any] | None = None,
    opportunity_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ranking_signal_source = "RankingSignal"
    primary_region_code = region_codes[0] if region_codes else "Gesamt"
    primary_region = (
        "Deutschland"
        if primary_region_code == "Gesamt"
        else engine._region_label(primary_region_code)
    )
    secondary_regions = [
        engine._region_label(code) if code in BUNDESLAND_NAMES else code
        for code in region_codes[1:]
    ]

    raw_confidence = trigger_evidence.get("confidence")
    if raw_confidence is None:
        raw_confidence = trigger_snapshot.get("confidence")
    confidence_pct_value = confidence_pct(raw_confidence, urgency_score)

    lead_time_days = trigger_evidence.get("lead_time_days") or trigger_snapshot.get("lead_time_days")

    mapping_status_value = str(mapping_status or "").strip().lower() or "needs_review"
    action_required = (
        "review_mapping"
        if mapping_status_value == "needs_review"
        else "ready_for_activation"
    )

    primary_product = str(recommended_product or "").strip() or "Produktfreigabe ausstehend"
    secondary_products_value = secondary_products(
        suggested_products=suggested_products,
        mapping_candidate_product=mapping_candidate_product,
        primary_product=primary_product,
    )

    condition_text = str(condition_label or condition_key or "relevante Lageklasse")
    rationale = (
        str(mapping_reason or "").strip()
        or public_reason_text(
            reason=recommendation_reason,
            event=trigger_evidence.get("event") or trigger_snapshot.get("event") or trigger_context.get("event"),
            details=trigger_evidence.get("details") or trigger_snapshot.get("details"),
        )
    )

    source_label = trigger_evidence.get("source") or trigger_snapshot.get("source")
    source = public_source_label(source_label or "Signal-Fusion") or (source_label or "Signal-Fusion")
    event_label = trigger_evidence.get("event") or trigger_snapshot.get("event")
    score = peix_context.get("score")
    basis_text = build_decision_basis_text(
        source_label=source_label,
        event=event_label,
        score=score,
    )

    budget_shift = budget_shift_pct if budget_shift_pct is not None else budget_shift_pct_fallback

    summary_sentence = build_decision_summary_text(
        basis_text=basis_text,
        condition_text=condition_text,
        primary_region=primary_region,
        primary_product=primary_product,
        action_required=action_required,
    )

    return {
        "summary_sentence": summary_sentence,
        "horizon": {
            "min_days": 7,
            "max_days": 14,
            "model_lead_time_days": lead_time_days,
        },
        "facts": decision_facts(
            engine,
            trigger_snapshot=trigger_snapshot,
            trigger_evidence=trigger_evidence,
            peix_context=peix_context,
            confidence_pct_value=confidence_pct_value,
            forecast_assessment=forecast_assessment,
            opportunity_assessment=opportunity_assessment,
        ),
        "expectation": {
            "condition_key": condition_key,
            "condition_label": public_condition_label(condition_label or condition_key),
            "region_codes": region_codes,
            "impact_probability": peix_context.get("impact_probability"),
            "signal_score": peix_context.get("signal_score") or peix_context.get("score"),
            "peix_score": peix_context.get("score"),
            "signal_confidence_pct": confidence_pct_value,
            "confidence_pct": confidence_pct_value,
            "event_probability_pct": (
                round(float((((forecast_assessment or {}).get("event_forecast") or {}).get("event_probability") or 0.0) * 100.0), 1)
                if ((forecast_assessment or {}).get("event_forecast") or {}).get("event_probability") is not None
                else None
            ),
            "forecast_readiness": (forecast_assessment or {}).get("forecast_quality", {}).get("forecast_readiness"),
            "truth_readiness": (opportunity_assessment or {}).get("truth_readiness"),
            "decision_priority_index": (opportunity_assessment or {}).get("decision_priority_index"),
            "rationale": rationale,
            "field_contracts": {
                "signal_score": ranking_signal_contract(source=ranking_signal_source),
                "impact_probability": ranking_signal_contract(
                    source=ranking_signal_source,
                    label="Legacy Signal-Score",
                ),
                "signal_confidence_pct": signal_confidence_contract(
                    source=source,
                    derived_from="trigger_evidence.confidence",
                ),
                "event_probability_pct": forecast_probability_contract(),
                "priority_score": priority_score_contract(source="MarketingOpportunityEngine"),
            },
        },
        "recommendation": {
            "primary_product": primary_product,
            "primary_region": primary_region,
            "secondary_regions": secondary_regions,
            "secondary_products": secondary_products_value,
            "budget_shift_pct": budget_shift,
            "mapping_status": mapping_status_value,
            "mapping_reason": mapping_reason,
            "action_required": action_required,
        },
    }


def model_to_dict(
    engine: "MarketingOpportunityEngine",
    model: MarketingOpportunity,
    normalize_status: bool = True,
) -> dict[str, Any]:
    status = engine._normalize_workflow_status(model.status) if normalize_status else model.status
    campaign_payload = model.campaign_payload or {}
    campaign_preview = engine._campaign_preview_from_payload(campaign_payload) if campaign_payload else None
    product_mapping = campaign_payload.get("product_mapping") or {}
    ranking_signal_context = (
        campaign_payload.get("ranking_signal_context")
        or campaign_payload.get("peix_context")
        or {}
    )
    peix_context = ranking_signal_context
    forecast_assessment = campaign_payload.get("forecast_assessment") or {}
    opportunity_assessment = campaign_payload.get("opportunity_assessment") or {}
    playbook = campaign_payload.get("playbook") or {}
    ai_meta = campaign_payload.get("ai_meta") or {}
    region_codes = engine._extract_region_codes_from_opportunity(
        {
            "region_target": model.region_target or {},
            "campaign_payload": campaign_payload,
        }
    )
    trigger_context = (
        model.trigger_details
        or {
            "source": model.trigger_source,
            "event": model.trigger_event,
            "detected_at": model.trigger_detected_at.isoformat() if model.trigger_detected_at else None,
        }
    )
    recommended_product = product_mapping.get("recommended_product") or model.product
    decision_brief = build_decision_brief(
        engine,
        urgency_score=model.urgency_score,
        recommendation_reason=model.recommendation_reason,
        trigger_context=trigger_context,
        trigger_snapshot=campaign_payload.get("trigger_snapshot") or {},
        trigger_evidence=campaign_payload.get("trigger_evidence") or {},
        peix_context=peix_context,
        region_codes=region_codes,
        condition_key=product_mapping.get("condition_key"),
        condition_label=product_mapping.get("condition_label"),
        recommended_product=recommended_product,
        mapping_status=product_mapping.get("mapping_status"),
        mapping_reason=product_mapping.get("mapping_reason"),
        mapping_candidate_product=product_mapping.get("candidate_product"),
        suggested_products=model.suggested_products,
        budget_shift_pct=model.budget_shift_pct,
        budget_shift_pct_fallback=(campaign_payload.get("budget_plan") or {}).get("budget_shift_pct"),
        forecast_assessment=forecast_assessment,
        opportunity_assessment=opportunity_assessment,
    )

    return {
        "id": model.opportunity_id,
        "type": model.opportunity_type,
        "status": status,
        "legacy_status": WORKFLOW_TO_LEGACY.get(status, model.status),
        "urgency_score": model.urgency_score,
        "priority_score": model.urgency_score,
        "region_target": model.region_target,
        "trigger_context": trigger_context,
        "target_audience": model.target_audience,
        "sales_pitch": model.sales_pitch,
        "suggested_products": model.suggested_products,
        "brand": model.brand,
        "product": model.product,
        "region": region_codes[0] if region_codes else "Gesamt",
        "region_codes": region_codes,
        "budget_shift_pct": model.budget_shift_pct,
        "channel_mix": model.channel_mix,
        "activation_start": model.activation_start.isoformat() if model.activation_start else None,
        "activation_end": model.activation_end.isoformat() if model.activation_end else None,
        "recommendation_reason": model.recommendation_reason,
        "campaign_payload": campaign_payload,
        "campaign_preview": campaign_preview,
        "recommended_product": recommended_product,
        "mapping_status": product_mapping.get("mapping_status"),
        "mapping_confidence": product_mapping.get("mapping_confidence"),
        "mapping_reason": product_mapping.get("mapping_reason"),
        "condition_key": product_mapping.get("condition_key"),
        "condition_label": product_mapping.get("condition_label"),
        "mapping_candidate_product": product_mapping.get("candidate_product"),
        "rule_source": product_mapping.get("rule_source"),
        "peix_context": peix_context,
        "ranking_signal_context": ranking_signal_context,
        "signal_score": peix_context.get("signal_score") or peix_context.get("score"),
        "forecast_assessment": forecast_assessment,
        "opportunity_assessment": opportunity_assessment,
        "exploratory_signals": campaign_payload.get("exploratory_signals") or [],
        "playbook_key": model.playbook_key or playbook.get("key"),
        "playbook_title": playbook.get("title"),
        "strategy_mode": model.strategy_mode or campaign_payload.get("strategy_mode"),
        "trigger_snapshot": campaign_payload.get("trigger_snapshot"),
        "guardrail_notes": (campaign_payload.get("guardrail_report") or {}).get("applied_fixes"),
        "ai_generation_status": ai_meta.get("status"),
        "trigger_evidence": campaign_payload.get("trigger_evidence"),
        "decision_brief": decision_brief,
        "detail_url": f"/kampagnen/{model.opportunity_id}",
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
        "expires_at": model.expires_at.isoformat() if model.expires_at else None,
        "exported_at": model.exported_at.isoformat() if model.exported_at else None,
        "is_supply_gap_active": bool(
            ((campaign_payload.get("supply_gap") or campaign_payload.get("conquesting") or {}).get("is_active", False))
        ),
        "supply_gap_match_examples": ", ".join(
            (
                (campaign_payload.get("supply_gap") or {}).get("matched_products")
                or (campaign_payload.get("conquesting") or {}).get("matched_drugs", [])
            )[:3]
        ),
        "recommended_priority_multiplier": float(
            (
                (campaign_payload.get("supply_gap") or {}).get("priority_multiplier")
                or (campaign_payload.get("conquesting") or {}).get("multiplier", 1.0)
            )
        ),
        "supply_gap_product": (
            (campaign_payload.get("supply_gap") or campaign_payload.get("conquesting") or {}).get("product", "")
        ),
    }
