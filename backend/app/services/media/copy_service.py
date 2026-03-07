"""Customer-facing copy helpers for campaign and trigger language."""

from __future__ import annotations

import re

PUBLIC_SOURCE_LABELS: dict[str, str] = {
    "BFARM_API": "BfArM Engpassmonitor",
    "BFARM": "BfArM Engpassmonitor",
    "BFARM_CONQUESTING": "BfArM Engpassmonitor",
    "RKI_SURVSTAT": "RKI SurvStat",
    "RKI_ARE": "RKI ARE",
    "AKTIN_RKI": "AKTIN/RKI Notaufnahme",
    "RKI": "RKI",
    "WEATHER_API": "Wetterdaten",
    "OPENWEATHER_FORECAST": "Wetterdaten",
    "OPENWEATHER_TEMPERATURE": "Wetterdaten",
    "OPENWEATHER_UV": "Wetterdaten",
    "BRIGHTSKY_DWD": "DWD/BrightSky",
    "DWD_BRIGHTSKY": "DWD/BrightSky",
    "DWD": "DWD Wetterdaten",
    "DWD_POLLEN": "DWD Pollen",
    "GOOGLE_TRENDS": "Google Trends",
    "PEIX": "PeixEpiScore",
    "PEIXEPISCORE": "PeixEpiScore",
    "PLAYBOOKENGINE": "Playbook-System",
    "SIGNAL_FUSION": "Signal-Fusion",
    "INTERNAL_ERP": "internes ERP",
    "ERP_SALES_SYNC": "ERP-Sales-Sync",
    "BRAND_PRODUCTS": "Produktkatalog",
}

PUBLIC_EVENT_LABELS: dict[str, str] = {
    "COMPETITOR_SHORTAGE_GELO_PRO": "Wettbewerber-Engpass bei Erkältungsmitteln",
    "COMPETITOR_SHORTAGE_GELO_GMF": "Wettbewerber-Engpass bei Husten- und Bronchitisprodukten",
    "COMPETITOR_SHORTAGE_GELO_RVC": "Wettbewerber-Engpass bei Halsschmerzprodukten",
    "COMPETITOR_SHORTAGE_GELO_BRO": "Wettbewerber-Engpass bei Hustenstillern",
    "COMPETITOR_SHORTAGE_GELO_SIT": "Wettbewerber-Engpass bei Sinusitis-Produkten",
    "COMPETITOR_SHORTAGE_GELO_DUR": "Wettbewerber-Engpass bei Schnupfenprodukten",
    "COMPETITOR_SHORTAGE_GELO_VOX": "Wettbewerber-Engpass bei Heiserkeitsprodukten",
    "COMPETITOR_SHORTAGE_GELO_VIT": "Wettbewerber-Engpass bei Immunpräparaten",
    "COMPETITOR_SHORTAGE_GELO_MUC": "Wettbewerber-Engpass bei Schleimlösern",
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
    "BROAD_INFECTION_WAVE": "breiter Erkältungsdruck",
    "RESOURCE_SCARCITY": "angespannte Verfügbarkeit im Markt",
    "MYCOPLASMA_WOW_SPIKE": "auffälliger Mykoplasmen-Anstieg",
    "RSV_PNEUMO_SINUS_SIGNAL": "RSV- und Pneumokokken-Signal",
    "WETTER_BELASTUNG_PLUS_PSYCHO": "kombinierter Wetter- und Suchdruck",
    "ALLERGY_FALSE_POSITIVE_FILTER": "allergiegetriebene Entlastung statt Erkältungswelle",
}

PUBLIC_CONDITION_LABELS: dict[str, str] = {
    "bronchitis_husten": "Bronchitis und Husten",
    "sinusitis_nebenhoehlen": "Sinusitis und Nebenhöhlenbeschwerden",
    "halsschmerz_heiserkeit": "Halsschmerz und Heiserkeit",
    "rhinitis_trockene_nase": "trockene und gereizte Nase",
    "immun_support": "erhöhter Immunbedarf",
    "erkaltung_akut": "akute Erkältungssymptome",
}

RESPIRATORY_SUFFIX_LABELS: dict[str, str] = {
    "HALSSCHMERZ": "Halsschmerz- und Heiserkeitssignale",
    "HEISERKEIT": "Heiserkeitssignale",
    "BRONCHITIS": "Husten- und Bronchitissignale",
    "HUSTEN": "Hustensignale",
    "ERKAELTUNG": "Erkältungssignale",
    "SINUSITIS": "Nebenhöhlensignale",
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
    normalized = _normalize_token(raw)
    if normalized in PUBLIC_EVENT_LABELS:
        return PUBLIC_EVENT_LABELS[normalized]
    if normalized.startswith("RESPIRATORY_GROWTH_"):
        suffix = normalized.removeprefix("RESPIRATORY_GROWTH_")
        label = RESPIRATORY_SUFFIX_LABELS.get(suffix) or _humanize_token(suffix)
        if label:
            return f"zunehmende {label}"
    if not _looks_internal_key(raw):
        return _cleanup_copy(raw)
    return _humanize_token(raw)


def public_source_label(source: str | None) -> str:
    raw = str(source or "").strip()
    if not raw:
        return ""

    if "+" in raw:
        parts = [public_source_label(part) or part.strip() for part in raw.split("+")]
        return " + ".join(part for part in parts if part)

    normalized = _normalize_token(raw)
    if normalized in PUBLIC_SOURCE_LABELS:
        return PUBLIC_SOURCE_LABELS[normalized]
    return _cleanup_copy(raw)


def public_condition_label(condition: str | None) -> str:
    raw = str(condition or "").strip()
    if not raw:
        return ""
    normalized = _normalize_token(raw).lower()
    if normalized in PUBLIC_CONDITION_LABELS:
        return PUBLIC_CONDITION_LABELS[normalized]
    return _cleanup_copy(_replace_internal_tokens(raw))


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
        parts.append(f"Signalen aus {public_source_label(source_label)}")

    event_label = public_event_label(event)
    if event_label:
        parts.append(f"dem Muster {event_label}")

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


def build_region_outlook_text(
    *,
    virus_typ: str,
    trend: str,
    change_pct: float,
    vorhersage_delta_pct: float | None = None,
) -> str:
    virus_label = _cleanup_copy(str(virus_typ or "")) or "die Lage"
    pct_str = f"{change_pct:+.0f}%"

    if trend == "steigend":
        text = f"steigende {virus_label}-Aktivität ({pct_str} WoW)"
    elif trend == "fallend":
        text = f"aktuell rückläufige {virus_label}-Aktivität ({pct_str} WoW)"
    else:
        text = f"eine stabile {virus_label}-Lage ({pct_str} WoW)"

    if vorhersage_delta_pct is None or abs(vorhersage_delta_pct) <= 5:
        return text
    if trend == "fallend" and vorhersage_delta_pct > 0:
        return f"{text}, der Forecast zeigt jedoch wieder nach oben"
    if trend == "steigend" and vorhersage_delta_pct > 0:
        return f"{text} mit weiter positivem Forecast"
    if vorhersage_delta_pct < 0:
        return f"{text}, der Forecast deutet eher auf Entspannung"
    return text


def build_region_recommendation_text(
    *,
    region_name: str,
    outlook_text: str,
    product: str,
    reason: str,
) -> str:
    reason_text = _cleanup_copy(str(reason or "weil die Lage genauer beobachtet werden sollte"))
    if not reason_text.startswith("weil"):
        reason_text = f"weil {reason_text}"
    return (
        f"In {region_name} sehen wir für die nächsten 7 bis 14 Tage {outlook_text}. "
        f"Deshalb priorisieren wir zunächst {product}, {reason_text}."
    )


def build_decision_summary_text(
    *,
    basis_text: str,
    condition_text: str,
    primary_region: str,
    primary_product: str,
    action_required: str,
) -> str:
    public_condition = public_condition_label(condition_text) or condition_text or "eine relevante Lage"
    basis_sentence = f"Auslöser sind {basis_text}." if basis_text else ""

    if action_required == "review_mapping" or "Produktfreigabe" in str(primary_product):
        return (
            f"Die Signale sprechen in den nächsten 7 bis 14 Tagen für {public_condition} in {primary_region}. "
            f"{basis_sentence} Vor einer Freigabe muss das passende Produkt noch bestätigt werden."
        ).replace("  ", " ").strip()

    return (
        f"Die Signale sprechen in den nächsten 7 bis 14 Tagen für {public_condition} in {primary_region}. "
        f"{basis_sentence} Deshalb priorisieren wir {primary_product} als nächstes Paket für Review und Freigabe."
    ).replace("  ", " ").strip()


def _replace_internal_tokens(text: str) -> str:
    result = text
    for raw, label in PUBLIC_SOURCE_LABELS.items():
        result = result.replace(raw, label)
    for raw, label in PUBLIC_EVENT_LABELS.items():
        result = result.replace(raw, label)
    for raw, label in PLAYBOOK_TITLE_ALIASES.items():
        result = result.replace(raw, label)
    token_pattern = r"\b[A-Za-z0-9]+(?:[_/-][A-Za-z0-9()]+)+\b"
    for token in sorted(set(re.findall(token_pattern, result)), key=len, reverse=True):
        replacement = public_event_label(token)
        if replacement == _cleanup_copy(token):
            source_replacement = public_source_label(token)
            if source_replacement != _cleanup_copy(token):
                replacement = source_replacement
        result = result.replace(token, replacement)
    return result


def _cleanup_copy(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned.rstrip(".")


def _normalize_token(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).upper()
    return re.sub(r"_+", "_", normalized).strip("_")


def _looks_internal_key(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized) and bool(re.fullmatch(r"[A-Z0-9_-]+", normalized))


def _humanize_token(value: str) -> str:
    raw = value.replace("-", " ").replace("_", " ")
    parts = [part for part in raw.split() if part]
    if not parts:
        return ""
    return " ".join(part if part.isupper() and len(part) <= 4 else part.capitalize() for part in parts)
