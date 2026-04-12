from __future__ import annotations

from typing import Any

from app.services.media.recommendation_contracts import to_card_response
from app.services.media.semantic_contracts import (
    outcome_confidence_contract,
    outcome_signal_contract,
    truth_readiness_contract,
)


def _campaign_cards(service, *, brand: str, limit: int = 120) -> list[dict[str, Any]]:
    opportunities = service.engine.get_opportunities(
        brand_filter=brand,
        limit=limit,
        normalize_status=True,
    )
    truth_coverage = service.get_truth_coverage(brand=brand)
    truth_gate = service.truth_gate_service.evaluate(truth_coverage)
    learning_bundle = service.outcome_signal_service.build_learning_bundle(
        brand=brand,
        truth_coverage=truth_coverage,
        truth_gate=truth_gate,
    )
    cards = [
        service._attach_outcome_learning_to_card(
            card=to_card_response(opp, include_preview=True),
            learning_bundle=learning_bundle,
            truth_gate=truth_gate,
        )
        for opp in opportunities
    ]
    cards.sort(
        key=service._campaign_sort_key,
        reverse=True,
    )
    return cards


def _attach_outcome_learning_to_card(
    service,
    *,
    card: dict[str, Any],
    learning_bundle: dict[str, Any],
    truth_gate: dict[str, Any],
) -> dict[str, Any]:
    learning_signal = service.outcome_signal_service.signal_for_card(
        card=card,
        bundle=learning_bundle,
    )
    learned_priority = service._learned_priority_score(
        base_priority=float(card.get("priority_score") or card.get("urgency_score") or 0.0),
        outcome_signal_score=learning_signal.get("outcome_signal_score"),
        truth_gate=truth_gate,
    )
    updated_contracts = dict(card.get("field_contracts") or {})
    updated_contracts.update({
        "outcome_signal_score": outcome_signal_contract(),
        "outcome_confidence_pct": outcome_confidence_contract(),
        "truth_readiness": truth_readiness_contract(),
    })
    return card | {
        "priority_score": learned_priority,
        "learning_state": learning_signal.get("learning_state"),
        "outcome_signal_score": learning_signal.get("outcome_signal_score"),
        "outcome_confidence_pct": learning_signal.get("outcome_confidence_pct"),
        "outcome_learning_scope": learning_signal.get("outcome_learning_scope"),
        "outcome_learning_explanation": learning_signal.get("outcome_learning_explanation"),
        "observed_response": learning_signal.get("observed_response"),
        "learned_lifts": learning_signal.get("learned_lifts"),
        "field_contracts": updated_contracts,
    }


def _learned_priority_score(
    service,
    *,
    base_priority: float,
    outcome_signal_score: Any,
    truth_gate: dict[str, Any],
) -> float:
    learning_state = str(truth_gate.get("learning_state") or "missing").lower()
    if learning_state in {"missing", "explorative", "stale"}:
        learning_weight = 0.0 if learning_state == "missing" else 0.12
    elif learning_state == "im_aufbau":
        learning_weight = 0.20
    else:
        learning_weight = 0.30

    try:
        outcome_score = float(outcome_signal_score)
    except (TypeError, ValueError):
        outcome_score = 0.0
    blended = base_priority * (1.0 - learning_weight) + outcome_score * learning_weight
    return round(max(0.0, min(100.0, blended)), 1)
