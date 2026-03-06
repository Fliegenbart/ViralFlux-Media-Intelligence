"""Customer-facing copy helpers for campaign and trigger language."""

from __future__ import annotations

import re


PUBLIC_EVENT_LABELS: dict[str, str] = {
    "COMPETITOR_SHORTAGE_GELO-PRO": "Wettbewerber-Engpass bei Erkältungsmitteln",
    "COMPETITOR_SHORTAGE_GELO-GMF": "Wettbewerber-Engpass bei Husten- und Bronchitisprodukten",
    "COMPETITOR_SHORTAGE_GELO-RVC": "Wettbewerber-Engpass bei Halsschmerzprodukten",
    "COMPETITOR_SHORTAGE_GELO-BRO": "Wettbewerber-Engpass bei Hustenstillern",
    "COMPETITOR_SHORTAGE_GELO-SIT": "Wettbewerber-Engpass bei Sinusitis-Produkten",
    "COMPETITOR_SHORTAGE_GELO-DUR": "Wettbewerber-Engpass bei Schnupfenprodukten",
    "COMPETITOR_SHORTAGE_GELO-VOX": "Wettbewerber-Engpass bei Heiserkeitsprodukten",
    "COMPETITOR_SHORTAGE_GELO-VIT": "Wettbewerber-Engpass bei Immunpräparaten",
    "COMPETITOR_SHORTAGE_GELO-MUC": "Wettbewerber-Engpass bei Schleimlösern",
    "CRITICAL_SHORTAGE_ANTIBIOTICS": "kritische Antibiotika-Engpässe",
    "CRITICAL_SHORTAGE_RESPIRATORY": "kritische Engpässe bei Atemwegsmedikamenten",
    "CRITICAL_SHORTAGE_FEVER": "kritische Engpässe bei Fieber- und Schmerzmitteln",
    "ORDER_VELOCITY_SURGE": "spürbar steigende Nachfrage",
    "LOW_UV_EXTENDED": "anhaltend niedrige UV-Belastung",
    "WINTER_COLD_STREAK": "winterliche Kältephase",
    "LOW_SUNSHINE_FORECAST": "wenig Sonnenschein in der Vorhersage",
    "NASSKALT_FORECAST": "nasskalte Wetterlage",
    "EXTREME_COLD_FORECAST": "extreme Kältephase",
    "SUPPLY_SHOCK_WINDOW": "Verfügbarkeitsfenster im Wettbewerb",
}

PUBLIC_PLAYBOOK_TITLES: dict[str, str] = {
    "MYCOPLASMA_JAEGER": "Hartnäckigen Husten abfangen",
    "SUPPLY_SHOCK_ATTACK": "Verfügbarkeitsfenster nutzen",
    "WETTER_REFLEX": "Vor Wetterumschwung aktivieren",
    "ALLERGIE_BREMSE": "Budget defensiv absichern",
    "HALSSCHMERZ_HUNTER": "Hals und Stimme absichern",
    "ERKAELTUNGSWELLE": "Erkältungswelle begleiten",
    "SINUS_DEFENDER": "Nebenhöhlen gezielt begleiten",
}

PLAYBOOK_TITLE_ALIASES: dict[str, str] = {
    "Mycoplasma-Jäger": PUBLIC_PLAYBOOK_TITLES["MYCOPLASMA_JAEGER"],
    "Supply-Shock Attack": PUBLIC_PLAYBOOK_TITLES["SUPPLY_SHOCK_ATTACK"],
    "Wetter-Reflex": PUBLIC_PLAYBOOK_TITLES["WETTER_REFLEX"],
    "Allergie-Bremse": PUBLIC_PLAYBOOK_TITLES["ALLERGIE_BREMSE"],
    "Halsschmerz-Hunter": PUBLIC_PLAYBOOK_TITLES["HALSSCHMERZ_HUNTER"],
    "Erkältungswelle": PUBLIC_PLAYBOOK_TITLES["ERKAELTUNGSWELLE"],
    "Sinus-Defender": PUBLIC_PLAYBOOK_TITLES["SINUS_DEFENDER"],
}


def public_event_label(event: str | None) -> str:
    raw = str(event or "").strip()
    if not raw:
        return ""
    if raw in PUBLIC_EVENT_LABELS:
        return PUBLIC_EVENT_LABELS[raw]
    return _humanize_token(raw)


def public_playbook_title(playbook_key: str | None = None, title: str | None = None) -> str:
    key = str(playbook_key or "").strip().upper()
    raw_title = str(title or "").strip()

    if key and key in PUBLIC_PLAYBOOK_TITLES:
        return PUBLIC_PLAYBOOK_TITLES[key]
    if raw_title and raw_title in PLAYBOOK_TITLE_ALIASES:
        return PLAYBOOK_TITLE_ALIASES[raw_title]
    if raw_title:
        return _cleanup_copy(raw_title)
    return ""


def public_display_title(
    *,
    playbook_key: str | None = None,
    playbook_title: str | None = None,
    campaign_name: str | None = None,
    product: str | None = None,
    trigger_event: str | None = None,
    condition_label: str | None = None,
) -> str:
    public_playbook = public_playbook_title(playbook_key=playbook_key, title=playbook_title)
    if public_playbook:
        return public_playbook

    public_campaign = public_campaign_name(campaign_name=campaign_name, product=product)
    if public_campaign:
        return public_campaign

    event_label = public_event_label(trigger_event)
    if event_label:
        prefix = str(product or "").strip()
        return f"{prefix}: {event_label}" if prefix else event_label

    condition = str(condition_label or "").strip()
    prefix = str(product or "").strip()
    if condition:
        return f"{prefix}: {condition}" if prefix else condition

    return str(product or "Kampagnenpaket").strip() or "Kampagnenpaket"


def public_campaign_name(campaign_name: str | None, product: str | None = None) -> str:
    raw = str(campaign_name or "").strip()
    if not raw:
        return ""

    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if len(parts) >= 4:
        display_product = parts[1]
        display_theme = public_playbook_title(title=parts[-1]) or public_event_label(parts[-1]) or _cleanup_copy(parts[-1])
        return f"{display_product}: {display_theme}"

    if _looks_internal_key(raw):
        return public_event_label(raw)

    if len(parts) >= 2:
        return _cleanup_copy(parts[-1])

    prefix = str(product or "").strip()
    cleaned = _cleanup_copy(raw)
    if prefix and cleaned.lower() != prefix.lower():
        return f"{prefix}: {cleaned}"
    return cleaned


def public_reason_text(
    *,
    reason: str | None = None,
    event: str | None = None,
    details: str | None = None,
) -> str:
    raw_reason = str(reason or "").strip()
    raw_event = str(event or "").strip()
    raw_details = str(details or "").strip()

    if raw_reason:
        if raw_reason.startswith("OPP-"):
            raw_reason = ""
        elif _looks_internal_key(raw_reason):
            return public_event_label(raw_reason)
        else:
            return _replace_internal_tokens(_cleanup_copy(raw_reason))

    if raw_event:
        return public_event_label(raw_event)

    if raw_details:
        return _replace_internal_tokens(_cleanup_copy(raw_details))

    return "Epidemiologisches Signal"


def build_decision_basis_text(
    *,
    source_label: str | None = None,
    event: str | None = None,
    score: float | int | str | None = None,
) -> str:
    parts: list[str] = []

    if source_label:
        parts.append(str(source_label).strip())

    event_label = public_event_label(event)
    if event_label:
        parts.append(f"dem Signal {event_label}")

    if score is not None and str(score).strip() != "":
        try:
            parts.append(f"einem PeixEpiScore von {float(score):.1f}")
        except (TypeError, ValueError):
            parts.append(f"einem PeixEpiScore von {score}")

    if not parts:
        return "aktuellen epidemiologischen Signalen"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} und {parts[1]}"
    return f"{', '.join(parts[:-1])} und {parts[-1]}"


def _replace_internal_tokens(text: str) -> str:
    result = text
    for raw, label in PUBLIC_EVENT_LABELS.items():
        result = result.replace(raw, label)
    for raw, label in PLAYBOOK_TITLE_ALIASES.items():
        result = result.replace(raw, label)
    return result


def _cleanup_copy(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned.rstrip(".")


def _looks_internal_key(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized) and bool(re.fullmatch(r"[A-Z0-9_-]+", normalized))


def _humanize_token(value: str) -> str:
    raw = value.replace("-", " ").replace("_", " ")
    parts = [part for part in raw.split() if part]
    if not parts:
        return ""
    return " ".join(part if part.isupper() and len(part) <= 4 else part.capitalize() for part in parts)
