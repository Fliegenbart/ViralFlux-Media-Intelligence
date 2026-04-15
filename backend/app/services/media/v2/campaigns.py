from __future__ import annotations

from typing import Any

from .context import build_truth_learning_context
from .shared import JsonDict, generated_at


def build_campaigns_payload(
    service: Any,
    *,
    brand: str,
    limit: int = 120,
) -> JsonDict:
    cards = service._campaign_cards(brand=brand, limit=limit)
    queue = service._build_campaign_queue(cards, visible_limit=min(limit, 8))
    primary_cards = queue["primary_cards"]
    archived_cards = queue["archived_cards"]
    visible_cards = queue["visible_cards"]
    truth_context = build_truth_learning_context(service, brand=brand)
    outcome_learning = truth_context["learning_bundle"]["summary"]

    return {
        "generated_at": generated_at(),
        "cards": visible_cards,
        "archived_cards": archived_cards[:20],
        "summary": queue["summary"] | {
            "total_cards": len(cards),
            "active_cards": len(queue["active_cards"]),
            "deduped_cards": len(primary_cards),
            "publishable_cards": len([card for card in primary_cards if card.get("is_publishable")]),
            "expired_cards": len([card for card in cards if card.get("lifecycle_state") == "EXPIRED"]),
            "states": service._campaign_state_counts(primary_cards),
            "learning_state": outcome_learning.get("learning_state"),
            "outcome_signal_score": outcome_learning.get("outcome_signal_score"),
            "outcome_confidence_pct": outcome_learning.get("outcome_confidence_pct"),
        },
    }
