from __future__ import annotations

from typing import Any

from app.services.media.semantic_contracts import (
    business_gate_contract,
    evidence_tier_contract,
    forecast_probability_contract,
    outcome_confidence_contract,
    outcome_signal_contract,
    priority_score_contract,
    ranking_signal_contract,
    signal_confidence_contract,
    truth_readiness_contract,
)
from app.services.ml.forecast_decision_service import ForecastDecisionService

from .shared import JsonDict, generated_at


def build_decision_payload(
    service: Any,
    *,
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
) -> JsonDict:
    cockpit = service.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
    forecast_bundle = ForecastDecisionService(service.db).build_forecast_bundle(
        virus_typ=virus_typ,
        target_source=target_source,
    )
    forecast_quality = forecast_bundle.get("forecast_quality") or {}
    event_forecast = forecast_bundle.get("event_forecast") or {}
    truth_coverage = service.get_truth_coverage(brand=brand, virus_typ=virus_typ)
    truth_gate = service.truth_gate_service.evaluate(truth_coverage)
    outcome_learning = service.outcome_signal_service.build_learning_bundle(
        brand=brand,
        truth_coverage=truth_coverage,
        truth_gate=truth_gate,
    )["summary"]
    business_validation = service.business_validation_service.evaluate(
        brand=brand,
        virus_typ=virus_typ,
        truth_coverage=truth_coverage,
        truth_gate=truth_gate,
        outcome_learning_summary=outcome_learning,
    )
    model_lineage = service.get_model_lineage(virus_typ=virus_typ)
    queue = service._build_campaign_queue(service._campaign_cards(brand=brand, limit=80), visible_limit=8)
    campaign_cards = queue["visible_cards"]
    primary_cards = queue["primary_cards"]
    top_card = service._decision_focus_card(primary_cards)
    top_regions = cockpit.get("map", {}).get("top_regions", [])[:3]
    market = cockpit.get("backtest_summary", {}).get("latest_market") or {}
    signal_summary = service.get_signal_stack(virus_typ=virus_typ).get("summary") or {}
    top_card_contracts = ((top_card or {}).get("field_contracts") or {}) if top_card else {}

    freshness_state = service._decision_freshness_state(cockpit.get("source_status", {}))
    has_truth = truth_gate["passed"]
    has_business_validation = bool(business_validation.get("validated_for_budget_activation"))
    market_passed = bool((market.get("quality_gate") or {}).get("overall_passed"))
    forecast_passed = str(forecast_quality.get("forecast_readiness") or "WATCH") == "GO"
    publishable_cards = [card for card in primary_cards if card.get("is_publishable")]
    has_publishable = len(publishable_cards) > 0
    drift_state = str(model_lineage.get("drift_state") or "unknown")
    decision_state = "GO" if all([
        freshness_state == "fresh",
        market_passed,
        forecast_passed,
        has_truth,
        has_business_validation,
        has_publishable,
        drift_state != "warning",
    ]) else "WATCH"

    risk_flags: list[str] = []
    if freshness_state != "fresh":
        risk_flags.append("Kernquellen sind nicht vollständig frisch.")
    if not market_passed:
        risk_flags.append("Der Marktvergleich liegt aktuell nicht im Zielkorridor.")
    if not forecast_passed:
        risk_flags.append("Die Vorhersage ist aktuell noch nicht freigegeben.")
    if not has_truth:
        risk_flags.append(str(truth_gate["message"]))
    if not has_business_validation:
        risk_flags.append(
            str(
                business_validation.get("message")
                or "Die Freigabe auf Basis von Kundendaten ist noch nicht validiert."
            )
        )
    if drift_state == "warning":
        risk_flags.append("Modell-Drift ist im Monitoring auffällig.")
    if not has_publishable:
        risk_flags.append("Es gibt aktuell keinen freigabefähigen Kampagnenvorschlag.")
    if truth_gate.get("guidance") and truth_gate.get("learning_state") != "belastbar":
        risk_flags.append(str(truth_gate["guidance"]))
    if business_validation.get("guidance") and business_validation.get("decision_scope") != "validated_budget_activation":
        risk_flags.append(str(business_validation["guidance"]))

    why_now = service._build_why_now(
        top_card=top_card,
        top_regions=top_regions,
        cockpit=cockpit,
        decision_state=decision_state,
        signal_summary=signal_summary,
    )
    if truth_gate.get("message") and truth_gate["message"] not in why_now:
        why_now = [str(truth_gate["message"]), *why_now][:3]
    recommended_action = service._recommended_action(
        decision_state=decision_state,
        top_card=top_card,
        top_regions=top_regions,
        decision_mode=str(signal_summary.get("decision_mode") or "epidemic_wave"),
    )
    top_products = service._decision_top_products(primary_cards, top_card)

    return {
        "virus_typ": virus_typ,
        "target_source": target_source,
        "generated_at": generated_at(),
        "weekly_decision": {
            "decision_state": decision_state,
            "action_stage": "activate" if decision_state == "GO" else "prepare",
            "decision_window": {
                "start": cockpit.get("map", {}).get("date"),
                "horizon_days": top_card.get("decision_brief", {}).get("horizon", {}).get("max_days") if top_card else None,
            },
            "recommended_action": recommended_action,
            "top_regions": [
                {
                    "code": item.get("code"),
                    "name": item.get("name"),
                    "signal_score": item.get("signal_score") or item.get("peix_score") or item.get("impact_probability"),
                    "trend": item.get("trend"),
                }
                for item in top_regions
            ],
            "top_products": top_products,
            "budget_shift": (
                top_card.get("budget_shift_pct")
                if decision_state == "GO" and top_card and top_card.get("is_publishable")
                else None
            ),
            "why_now": why_now,
            "risk_flags": risk_flags,
            "freshness_state": freshness_state,
            "proxy_state": "passed" if market_passed else "watch",
            "forecast_state": "passed" if forecast_passed else "watch",
            "forecast_quality": forecast_quality,
            "event_forecast": event_forecast,
            "truth_state": truth_coverage.get("trust_readiness"),
            "truth_freshness_state": truth_coverage.get("truth_freshness_state"),
            "truth_last_imported_at": truth_coverage.get("last_imported_at"),
            "truth_latest_batch_id": truth_coverage.get("latest_batch_id"),
            "truth_risk_flag": None if has_truth else truth_gate["message"],
            "truth_gate": truth_gate,
            "business_gate": business_validation,
            "business_readiness": business_validation.get("validation_status"),
            "business_evidence_tier": business_validation.get("evidence_tier"),
            "learning_state": outcome_learning.get("learning_state"),
            "outcome_learning_summary": outcome_learning,
            "decision_mode": signal_summary.get("decision_mode"),
            "decision_mode_label": signal_summary.get("decision_mode_label"),
            "decision_mode_reason": signal_summary.get("decision_mode_reason"),
            "signal_stack_summary": signal_summary,
            "operator_context": business_validation.get("operator_context"),
            "field_contracts": {
                "event_probability": forecast_probability_contract(),
                "signal_score": ranking_signal_contract(source="PeixEpiScore"),
                "priority_score": top_card_contracts.get("priority_score")
                or priority_score_contract(source="MarketingOpportunityEngine"),
                "signal_confidence_pct": top_card_contracts.get("signal_confidence_pct")
                or signal_confidence_contract(
                    source="MarketingOpportunityEngine",
                    derived_from="trigger_evidence.confidence",
                ),
                "truth_readiness": truth_readiness_contract(),
                "business_gate": business_gate_contract(),
                "evidence_tier": evidence_tier_contract(),
                "outcome_signal_score": outcome_signal_contract(),
                "outcome_confidence_pct": outcome_confidence_contract(),
            },
        },
        "top_recommendations": campaign_cards[:3],
        "campaign_summary": queue["summary"],
        "wave_run_id": (cockpit.get("backtest_summary", {}).get("latest_market") or {}).get("run_id"),
        "backtest_summary": cockpit.get("backtest_summary"),
        "model_lineage": model_lineage,
        "truth_coverage": truth_coverage,
        "business_validation": business_validation,
        "operator_context": business_validation.get("operator_context"),
    }
