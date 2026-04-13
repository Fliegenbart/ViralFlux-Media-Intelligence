from __future__ import annotations

from typing import Any


SOURCE_LABELS = {
    "wastewater": "Abwasser",
    "are konsultation": "ARE-Konsultation",
    "survstat": "SurvStat",
    "notaufnahme": "Notaufnahme",
    "weather": "Wetter",
    "pollen": "Pollen",
    "google trends": "Google Trends",
    "bfarm shortage": "BfArM-Engpässe",
    "marketing": "Kundendaten",
    "backtest": "Rückblicktest",
}

TILE_LABELS = {
    "SURVSTAT Respiratory": "SurvStat Atemwege",
    "Top Chancenregion": "Früheste Signalregion",
    "Signalscore Deutschland": "Signalwert Deutschland",
    "BfArM Engpass-Signal": "BfArM-Engpasssignal",
    "Google Trends Infekt": "Google Trends Atemwege",
    "ARE Konsultationsinzidenz": "ARE-Konsultationsinzidenz",
}


def safe(text: Any) -> str:
    """Sanitize text for Latin-1 encoding (core PDF fonts)."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u2022": "*",
        "\u00a0": " ",
        "\u2197": "^",
        "\u2198": "v",
        "\u2192": "->",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def source_display_label(source: str | None) -> str:
    raw = str(source or "").strip()
    if not raw:
        return "-"
    normalized = raw.lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    if normalized in SOURCE_LABELS:
        return SOURCE_LABELS[normalized]
    return raw.replace("_", " ").title()


def dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for card in cards:
        product = str(card.get("recommended_product", card.get("product", "")) or "").strip().lower()
        reason = str(card.get("reason", card.get("recommendation_reason", "")) or "").strip().lower()
        signature = (product, reason)
        if signature in seen:
            continue
        seen.add(signature)
        unique_cards.append(card)

    return unique_cards


def tile_display_title(title: str | None) -> str:
    raw = str(title or "").strip()
    if not raw:
        return "-"
    if raw in TILE_LABELS:
        return TILE_LABELS[raw]
    return raw.replace("Signalscore", "Signalwert")


def normalize_tile_line(text: str) -> str:
    normalized = str(text or "")
    for source, replacement in TILE_LABELS.items():
        normalized = normalized.replace(source, replacement)
    return normalized.replace("Signalscore", "Signalwert")


def normalize_signal_score(value: Any) -> float:
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def primary_signal_score(item: dict[str, Any] | None) -> float:
    payload = item or {}
    for key in ("signal_score", "ranking_signal_score", "peix_score", "score_0_100", "impact_probability"):
        if key in payload and payload.get(key) is not None:
            return round(normalize_signal_score(payload.get(key)), 1)
    return 0.0


def format_signal_score(value: Any, digits: int = 0) -> str:
    score = normalize_signal_score(value)
    return f"{score:.{digits}f}/100"


def action_card_title(card: dict[str, Any]) -> str:
    title = str(
        card.get("display_title")
        or card.get("recommended_product")
        or card.get("product")
        or "Kampagnenvorschlag"
    ).strip()
    reason = str(card.get("reason") or card.get("recommendation_reason") or "").strip()
    if reason and reason.lower() not in title.lower():
        return f"{title}: {reason}"
    return title
