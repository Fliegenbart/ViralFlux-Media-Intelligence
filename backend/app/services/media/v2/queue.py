from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.media.recommendation_contracts import dedupe_group_id


QUEUE_LIFECYCLE_PRIORITY = {
    "SYNC_READY": 5,
    "APPROVE": 4,
    "REVIEW": 3,
    "PREPARE": 2,
    "LIVE": 1,
    "EXPIRED": 0,
    "ARCHIVED": 0,
}

QUEUE_LANE_ORDER = ("APPROVE", "REVIEW", "SYNC_READY", "PREPARE", "LIVE")


def _campaign_state_counts(service, cards: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for card in cards:
        counts[str(card.get("lifecycle_state") or "PREPARE")] += 1
    return dict(sorted(counts.items()))


def _campaign_sort_key(service, item: dict[str, Any]) -> tuple[Any, ...]:
    lifecycle = str(item.get("lifecycle_state") or "").upper()
    blockers = item.get("publish_blockers") or []
    freshness = str(item.get("freshness_state") or "").lower()
    return (
        item.get("is_publishable", False),
        QUEUE_LIFECYCLE_PRIORITY.get(lifecycle, 0),
        freshness == "current",
        freshness == "scheduled",
        -len(blockers),
        float(item.get("priority_score") or item.get("urgency_score") or 0.0),
        float(item.get("signal_confidence_pct") or item.get("confidence") or 0.0),
        str(item.get("updated_at") or item.get("created_at") or ""),
    )


def _build_campaign_queue(
    service,
    cards: list[dict[str, Any]],
    *,
    visible_limit: int = 8,
) -> dict[str, Any]:
    active_cards = [card for card in cards if card.get("lifecycle_state") not in {"EXPIRED", "ARCHIVED"}]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    archived_cards: list[dict[str, Any]] = []

    for card in cards:
        if card.get("lifecycle_state") in {"EXPIRED", "ARCHIVED"}:
            archived_cards.append(card)
            continue
        grouped[dedupe_group_id(card)].append(card)

    primary_cards: list[dict[str, Any]] = []
    for group_cards in grouped.values():
        ranked = sorted(group_cards, key=service._campaign_sort_key, reverse=True)
        primary = dict(ranked[0])
        primary["is_primary_variant"] = True
        primary["variant_count"] = len(ranked)
        primary["variants"] = [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "lifecycle_state": item.get("lifecycle_state"),
                "display_title": item.get("display_title"),
            }
            for item in ranked[1:]
        ]
        primary_cards.append(primary)

    primary_cards.sort(key=service._campaign_sort_key, reverse=True)
    visible_cards = service._select_visible_queue_cards(primary_cards, limit=visible_limit)

    return {
        "active_cards": active_cards,
        "primary_cards": primary_cards,
        "visible_cards": visible_cards,
        "archived_cards": archived_cards,
        "summary": {
            "visible_cards": len(visible_cards),
            "hidden_backlog_cards": max(len(primary_cards) - len(visible_cards), 0),
        },
    }


def _select_visible_queue_cards(
    service,
    cards: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if len(cards) <= limit:
        return cards

    by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        by_lane[str(card.get("lifecycle_state") or "PREPARE").upper()].append(card)

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for lane in QUEUE_LANE_ORDER:
        lane_cards = by_lane.get(lane) or []
        if not lane_cards:
            continue
        card = lane_cards[0]
        card_id = str(card.get("id") or "")
        if card_id and card_id not in seen_ids:
            selected.append(card)
            seen_ids.add(card_id)
        if len(selected) >= limit:
            return selected[:limit]

    for lane in QUEUE_LANE_ORDER:
        for card in by_lane.get(lane, [])[1:]:
            card_id = str(card.get("id") or "")
            if card_id and card_id in seen_ids:
                continue
            selected.append(card)
            if card_id:
                seen_ids.add(card_id)
            if len(selected) >= limit:
                return selected[:limit]

    return selected[:limit]


def _decision_focus_card(service, cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred = [
        card for card in cards
        if str(card.get("lifecycle_state") or "").upper() in {"SYNC_READY", "APPROVE", "REVIEW"}
    ]
    if preferred:
        return preferred[0]
    return cards[0] if cards else None


def _decision_top_products(
    service,
    cards: list[dict[str, Any]],
    top_card: dict[str, Any] | None,
) -> list[str]:
    products: list[str] = []
    for card in cards:
        product = str(card.get("recommended_product") or card.get("product") or "").strip()
        if product and product not in products:
            products.append(product)
        if len(products) >= 3:
            break
    if not products and top_card:
        product = str(top_card.get("recommended_product") or top_card.get("product") or "").strip()
        if product:
            products.append(product)
    return products


def _recommended_action(
    service,
    *,
    decision_state: str,
    top_card: dict[str, Any] | None,
    top_regions: list[dict[str, Any]],
    decision_mode: str,
) -> str:
    primary_region = (
        top_card.get("decision_brief", {}).get("recommendation", {}).get("primary_region")
        if top_card else None
    ) or (top_regions[0].get("name") if top_regions else None)
    product = (
        top_card.get("recommended_product")
        or top_card.get("product")
        if top_card else None
    )
    top_summary = top_card.get("decision_brief", {}).get("summary_sentence") if top_card else None

    if decision_state == "GO" and top_summary:
        return str(top_summary)
    if decision_state == "GO":
        if primary_region and product:
            return f"Diese Woche freigeben: {product} in {primary_region} priorisieren."
        return "Diese Woche freigeben: die stärksten regionalen Vorschläge in die Aktivierung ziehen."

    if decision_mode == "supply_window":
        if primary_region and product:
            return f"Diese Woche vorbereiten: {product} in {primary_region} als Versorgungschance absichern, aber noch keinen nationalen Shift freigeben."
        return "Diese Woche vorbereiten: Versorgungssignale beobachten und nur prüfbare Vorschläge weiterziehen."
    if decision_mode == "mixed":
        if primary_region and product:
            return f"Diese Woche vorbereiten: {product} in {primary_region} priorisieren, weil Epi-Signal und Kontext gemeinsam tragen, aber noch keinen nationalen Shift freigeben."
        return "Diese Woche vorbereiten: Epi-Signal und Kontext beobachten und keine harte Aktivierung freigeben."
    if primary_region and product:
        return f"Diese Woche vorbereiten: {product} in {primary_region} priorisieren, aber noch keinen nationalen Shift freigeben."
    if primary_region:
        return f"Diese Woche vorbereiten: {primary_region} priorisieren und nur prüfbare Vorschläge weiterziehen."
    return "Diese Woche vorbereiten: Signal beobachten, Regionen priorisieren und keine harte Aktivierung freigeben."
