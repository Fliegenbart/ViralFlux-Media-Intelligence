from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime
from typing import Any

from app.services.media.copy_service import (
    public_campaign_name,
    public_display_title,
    public_event_label,
    public_playbook_title,
    public_reason_text,
    public_source_label,
)
from app.services.media.semantic_contracts import (
    forecast_probability_contract,
    normalize_confidence_pct,
    priority_score_contract,
    ranking_signal_contract,
    signal_confidence_contract,
)

BUNDESLAND_NAMES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
REGION_NAME_TO_CODE = {name.lower(): code for code, name in BUNDESLAND_NAMES.items()}

CONDITION_LABELS: dict[str, str] = {
    "erkaltung_akut": "Akute Erkältung",
    "bronchitis_husten": "Bronchitis & Husten",
    "halsschmerz": "Halsschmerzen",
    "husten_reizhusten": "Reizhusten",
    "sinusitis": "Sinusitis",
    "schnupfen": "Schnupfen",
    "heiserkeit": "Heiserkeit",
    "immun_support": "Immununterstützung",
    "schleimloeser": "Schleimlösung",
}

STATUS_LABELS: dict[str, str] = {
    "NEW": "Neu",
    "URGENT": "Dringend",
    "DRAFT": "Vorbereitung",
    "READY": "In Prüfung",
    "APPROVED": "Freigegeben",
    "ACTIVATED": "Live",
    "DISMISSED": "Archiviert",
    "EXPIRED": "Abgelaufen",
}

PLACEHOLDER_PRODUCTS = {
    "",
    "atemwegslinie",
    "produktfreigabe ausstehend",
    "alle gelo-produkte",
}
PLACEHOLDER_TITLE_MARKERS = {
    "produktfreigabe ausstehend",
}
MAPPING_BLOCK_STATES = {
    "needs_review",
    "pending",
    "unmapped",
    "rejected",
}


def normalize_region_code(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "DE"

    upper = raw.upper()
    if upper in BUNDESLAND_NAMES:
        return upper

    mapped = REGION_NAME_TO_CODE.get(raw.lower())
    if mapped:
        return mapped

    return upper


def extract_region_codes_from_card_payload(
    opp: dict[str, Any],
    campaign_pack: dict[str, Any],
) -> list[str]:
    existing = opp.get("region_codes")
    if isinstance(existing, list) and existing:
        normalized = [normalize_region_code(str(item)) for item in existing if item]
        return sorted({code for code in normalized if code in BUNDESLAND_NAMES})

    region = opp.get("region")
    if isinstance(region, str) and region.strip():
        code = normalize_region_code(region)
        if code in BUNDESLAND_NAMES:
            return [code]
        if region.strip().lower() in {"gesamt", "de", "all", "national"}:
            return sorted(BUNDESLAND_NAMES.keys())

    targeting = campaign_pack.get("targeting") or {}
    scope = targeting.get("region_scope")
    tokens: list[str] = []
    if isinstance(scope, list):
        tokens.extend(str(item) for item in scope if item)
    elif isinstance(scope, str) and scope.strip():
        tokens.append(scope)

    if not tokens:
        return []

    result = set()
    for token in tokens:
        lower = token.strip().lower()
        if lower in {"gesamt", "de", "all", "national", "deutschland"}:
            return sorted(BUNDESLAND_NAMES.keys())
        code = normalize_region_code(token)
        if code in BUNDESLAND_NAMES:
            result.add(code)

    return sorted(result)


def extract_region_codes_from_card(card: dict[str, Any]) -> set[str]:
    codes = card.get("region_codes")
    if isinstance(codes, list) and codes:
        normalized = {normalize_region_code(str(code)) for code in codes if code}
        normalized = {code for code in normalized if code in BUNDESLAND_NAMES}
        if normalized:
            return normalized

    region = str(card.get("region") or "").strip().lower()
    if region in {"gesamt", "de", "all", "national", "deutschland"}:
        return set(BUNDESLAND_NAMES.keys())

    if region:
        code = normalize_region_code(region)
        if code in BUNDESLAND_NAMES:
            return {code}

    return set()


def _build_display_title(opp: dict[str, Any], product: str | None) -> str:
    event = (opp.get("trigger_context") or {}).get("event", "")
    prod = product or opp.get("product") or "Atemwegslinie"
    condition = CONDITION_LABELS.get(opp.get("condition_key", ""), "")
    return public_display_title(
        playbook_key=opp.get("playbook_key"),
        playbook_title=opp.get("playbook_title"),
        campaign_name=(
            (opp.get("campaign_preview") or {}).get("campaign_name")
            or ((opp.get("campaign_payload") or {}).get("campaign") or {}).get("campaign_name")
        ),
        product=prod,
        trigger_event=event,
        condition_label=condition,
    )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _activation_window(card: dict[str, Any], campaign_pack: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    activation_window = card.get("activation_window") or {}
    payload_activation = campaign_pack.get("activation_window") or {}
    start = (
        activation_window.get("start")
        or card.get("activation_start")
        or payload_activation.get("start")
    )
    end = (
        activation_window.get("end")
        or card.get("activation_end")
        or payload_activation.get("end")
    )
    return _parse_iso_datetime(start), _parse_iso_datetime(end)


def _dedupe_messages(messages: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for message in messages:
        if message not in seen:
            deduped.append(message)
            seen.add(message)
    return deduped


def _has_placeholder_title(card: dict[str, Any]) -> bool:
    preview = card.get("campaign_preview") or {}
    title_candidates = [
        str(card.get("display_title") or "").strip(),
        str(card.get("campaign_name") or "").strip(),
        str(preview.get("campaign_name") or "").strip(),
    ]
    lowered = " ".join(part for part in title_candidates if part).lower()
    return any(marker in lowered for marker in PLACEHOLDER_TITLE_MARKERS)


def _derive_content_blockers(card: dict[str, Any], now: datetime | None = None) -> list[str]:
    effective_now = now or utc_now()
    campaign_pack = card.get("campaign_payload") or {}
    budget = (card.get("campaign_preview") or {}).get("budget") or campaign_pack.get("budget_plan") or {}
    message_framework = campaign_pack.get("message_framework") or {}
    guardrails = campaign_pack.get("guardrail_report") or {}
    channel_plan = campaign_pack.get("channel_plan") or []
    channel_mix = card.get("channel_mix") or {}

    blockers: list[str] = []
    recommended_product = str(card.get("recommended_product") or card.get("product") or "").strip()
    if recommended_product.lower() in PLACEHOLDER_PRODUCTS:
        blockers.append("Produktfreigabe ist noch nicht abgeschlossen.")
    elif _has_placeholder_title(card):
        blockers.append("Produktfreigabe ist noch nicht abgeschlossen.")

    mapping_status = str(card.get("mapping_status") or "").strip().lower()
    if mapping_status in MAPPING_BLOCK_STATES:
        blockers.append("Produkt-Mapping braucht noch eine Pruefung.")

    start_at, end_at = _activation_window(card, campaign_pack)
    if start_at is None or end_at is None:
        blockers.append("Flight-Fenster ist unvollständig.")
    elif end_at < effective_now:
        blockers.append("Flight-Fenster ist bereits abgelaufen.")

    weekly_budget = budget.get("weekly_budget_eur")
    total_budget = budget.get("total_flight_budget_eur")
    if not any(
        isinstance(value, (int, float)) and float(value) > 0
        for value in (weekly_budget, total_budget)
    ):
        blockers.append("Budget ist noch nicht valide hinterlegt.")

    if not channel_plan and not channel_mix:
        blockers.append("Channel-Plan fehlt.")

    if not str(message_framework.get("hero_message") or "").strip():
        blockers.append("Leitbotschaft fehlt.")

    if guardrails.get("passed") is False:
        blockers.append("Die Pruefkriterien sind noch nicht erfuellt.")

    return _dedupe_messages(blockers)


def _humanize_trigger_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = dict(payload or {})
    if cleaned.get("event"):
        cleaned["event"] = public_event_label(cleaned.get("event"))
    if cleaned.get("trigger_event"):
        cleaned["trigger_event"] = public_event_label(cleaned.get("trigger_event"))
    if cleaned.get("source"):
        cleaned["source"] = public_source_label(cleaned.get("source")) or cleaned.get("source")
    if cleaned.get("details"):
        cleaned["details"] = public_reason_text(details=cleaned.get("details"))
    return cleaned


def _humanize_peix_context(peix_context: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = dict(peix_context or {})
    if cleaned.get("trigger_event"):
        cleaned["trigger_event"] = public_event_label(cleaned.get("trigger_event"))
    return cleaned


def _humanize_campaign_name(name: Any, product: str | None = None) -> str | None:
    raw = str(name or "").strip()
    if not raw:
        return None
    return public_campaign_name(raw, product=product) or raw


def _humanize_playbook(playbook: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = dict(playbook or {})
    if cleaned.get("title") or cleaned.get("key"):
        cleaned["title"] = public_playbook_title(
            playbook_key=cleaned.get("key"),
            title=cleaned.get("title"),
        ) or cleaned.get("title")
    return cleaned


def derive_publish_blockers(card: dict[str, Any], now: datetime | None = None) -> list[str]:
    blockers = _derive_content_blockers(card, now=now)
    freshness_state = derive_freshness_state(card, now=now)
    status = str(card.get("status") or "").strip().upper()

    if freshness_state != "expired":
        if status in {"DRAFT", "NEW", "URGENT"}:
            blockers.append("Paket ist noch nicht in Prüfung.")
        elif status == "READY":
            blockers.append("Freigabe steht noch aus.")

    return _dedupe_messages(blockers)


def derive_freshness_state(card: dict[str, Any], now: datetime | None = None) -> str:
    effective_now = now or utc_now()
    campaign_pack = card.get("campaign_payload") or {}
    start_at, end_at = _activation_window(card, campaign_pack)

    if end_at and end_at < effective_now:
        return "expired"
    if start_at and start_at > effective_now:
        return "scheduled"
    if start_at and (end_at is None or end_at >= effective_now):
        return "current"
    if start_at is None and end_at is None:
        return "missing_window"
    return "stale"


def derive_evidence_strength(card: dict[str, Any]) -> str:
    confidence = float(card.get("confidence") or 0.0)
    if confidence <= 1:
        confidence *= 100.0
    forecast_assessment = (card.get("campaign_payload") or {}).get("forecast_assessment") or {}
    event_forecast = forecast_assessment.get("event_forecast") or {}
    quality = forecast_assessment.get("forecast_quality") or {}
    event_strength = float(event_forecast.get("event_probability") or 0.0) * 100.0
    peix_score = float(
        event_strength
        or (card.get("peix_context") or {}).get("score")
        or (card.get("peix_context") or {}).get("impact_probability")
        or 0.0
    )
    signal_count = len((card.get("decision_brief") or {}).get("facts") or [])
    if confidence >= 78 and peix_score >= 60 and signal_count >= 2 and quality.get("forecast_readiness") != "WATCH":
        return "hoch"
    if confidence >= 60 or peix_score >= 50:
        return "mittel"
    return "niedrig"


def derive_lifecycle_state(card: dict[str, Any], now: datetime | None = None) -> str:
    status = str(card.get("status") or "").upper()
    freshness_state = derive_freshness_state(card, now=now)
    blockers = _derive_content_blockers(card, now=now)

    if freshness_state == "expired" or status == "EXPIRED":
        return "EXPIRED"
    if status == "DISMISSED":
        return "ARCHIVED"
    if status == "ACTIVATED":
        return "LIVE"
    if status == "APPROVED":
        return "SYNC_READY" if not blockers else "REVIEW"
    if status == "READY":
        return "APPROVE" if not blockers else "REVIEW"
    if status in {"DRAFT", "NEW", "URGENT"}:
        return "REVIEW" if not blockers else "PREPARE"
    if blockers:
        return "PREPARE"
    return "REVIEW"


def dedupe_group_id(card: dict[str, Any]) -> str:
    region_codes = sorted(str(code) for code in (card.get("region_codes") or []) if code)
    activation_window = card.get("activation_window") or {}
    start = str(activation_window.get("start") or "")[:10]
    end = str(activation_window.get("end") or "")[:10]
    condition = str(card.get("condition_key") or "unknown").strip().lower()
    product = str(card.get("recommended_product") or card.get("product") or "unknown").strip().lower()
    if not product:
        product = "unknown"
    region_part = ",".join(region_codes) or "national"
    return f"{condition}|{product}|{region_part}|{start}|{end}"


def enrich_card_v2(card: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    effective_now = now or utc_now()
    enriched = dict(card)
    blockers = derive_publish_blockers(enriched, now=effective_now)
    lifecycle_state = derive_lifecycle_state(enriched, now=effective_now)
    freshness_state = derive_freshness_state(enriched, now=effective_now)
    evidence_strength = derive_evidence_strength(enriched)
    enriched["publish_blockers"] = blockers
    enriched["is_publishable"] = not blockers and lifecycle_state in {"SYNC_READY", "LIVE"}
    enriched["lifecycle_state"] = lifecycle_state
    enriched["freshness_state"] = freshness_state
    enriched["evidence_strength"] = evidence_strength
    enriched["dedupe_group_id"] = dedupe_group_id(enriched)
    enriched.setdefault("is_primary_variant", True)
    enriched["decision_link"] = f"/entscheidung?focus={enriched.get('id')}"
    return enriched


def to_card_response(opp: dict[str, Any], include_preview: bool = True) -> dict[str, Any]:
    preview = opp.get("campaign_preview") or {}
    campaign_pack = opp.get("campaign_payload") or {}
    measurement = campaign_pack.get("measurement_plan") or {}
    product_mapping = campaign_pack.get("product_mapping") or {}
    peix_context = campaign_pack.get("peix_context") or {}
    playbook = campaign_pack.get("playbook") or {}
    ai_meta = campaign_pack.get("ai_meta") or {}
    region_codes = extract_region_codes_from_card_payload(opp, campaign_pack)
    trigger_snapshot = _humanize_trigger_payload(opp.get("trigger_snapshot") or campaign_pack.get("trigger_snapshot"))
    trigger_context = _humanize_trigger_payload(opp.get("trigger_context") or {})
    cleaned_peix_context = _humanize_peix_context(opp.get("peix_context") or peix_context)
    cleaned_campaign_pack = dict(campaign_pack)
    cleaned_playbook = _humanize_playbook(playbook)
    preview_campaign_name = _humanize_campaign_name(
        preview.get("campaign_name"),
        product=opp.get("recommended_product") or product_mapping.get("recommended_product") or opp.get("product"),
    )
    payload_campaign_name = _humanize_campaign_name(
        ((campaign_pack.get("campaign") or {}).get("campaign_name")),
        product=opp.get("recommended_product") or product_mapping.get("recommended_product") or opp.get("product"),
    )
    ai_plan = dict(campaign_pack.get("ai_plan") or {})
    if ai_plan.get("campaign_name"):
        ai_plan["campaign_name"] = _humanize_campaign_name(
            ai_plan.get("campaign_name"),
            product=opp.get("recommended_product") or product_mapping.get("recommended_product") or opp.get("product"),
        )
    cleaned_campaign_pack["trigger_snapshot"] = _humanize_trigger_payload(campaign_pack.get("trigger_snapshot"))
    cleaned_campaign_pack["trigger_evidence"] = _humanize_trigger_payload(campaign_pack.get("trigger_evidence"))
    cleaned_campaign_pack["peix_context"] = _humanize_peix_context(peix_context)
    cleaned_campaign_pack["playbook"] = cleaned_playbook
    cleaned_campaign_pack["signal_contracts"] = campaign_pack.get("signal_contracts") or {}
    if campaign_pack.get("campaign"):
        cleaned_campaign_pack["campaign"] = dict(campaign_pack.get("campaign") or {})
        if payload_campaign_name:
            cleaned_campaign_pack["campaign"]["campaign_name"] = payload_campaign_name
    if ai_plan:
        cleaned_campaign_pack["ai_plan"] = ai_plan
    recommended_product = (
        opp.get("recommended_product")
        or product_mapping.get("recommended_product")
        or opp.get("product")
    )

    condition_key = opp.get("condition_key") or product_mapping.get("condition_key", "")
    signal_confidence_pct = (
        normalize_confidence_pct(((opp.get("decision_brief") or {}).get("expectation") or {}).get("signal_confidence_pct"))
        or normalize_confidence_pct(((opp.get("decision_brief") or {}).get("expectation") or {}).get("confidence_pct"))
        or normalize_confidence_pct(
            ((campaign_pack.get("forecast_assessment") or {}).get("event_forecast") or {}).get("confidence")
        )
    )
    signal_score = (
        opp.get("signal_score")
        or cleaned_peix_context.get("signal_score")
        or cleaned_peix_context.get("score")
        or cleaned_peix_context.get("impact_probability")
    )
    priority_score = opp.get("priority_score") or opp.get("urgency_score")
    field_contracts = {
        "signal_score": ranking_signal_contract(source="PeixEpiScore"),
        "impact_probability": ranking_signal_contract(
            source="PeixEpiScore",
            label="Legacy Signal-Score",
        ),
        "priority_score": priority_score_contract(source="MarketingOpportunityEngine"),
        "signal_confidence_pct": signal_confidence_contract(
            source=str((opp.get("trigger_context") or {}).get("source") or (opp.get("trigger_snapshot") or {}).get("source") or "Signal-Fusion"),
            derived_from="trigger_evidence.confidence",
        ),
        "event_probability": forecast_probability_contract(),
    }
    if campaign_pack.get("signal_contracts"):
        field_contracts.update(campaign_pack.get("signal_contracts") or {})
    public_playbook = public_playbook_title(
        playbook_key=opp.get("playbook_key") or playbook.get("key"),
        title=opp.get("playbook_title") or playbook.get("title"),
    )
    public_title = public_display_title(
        playbook_key=opp.get("playbook_key") or playbook.get("key"),
        playbook_title=opp.get("playbook_title") or playbook.get("title"),
        campaign_name=preview_campaign_name or payload_campaign_name,
        product=recommended_product,
        trigger_event=trigger_context.get("event"),
        condition_label=(
            opp.get("condition_label")
            or product_mapping.get("condition_label")
            or CONDITION_LABELS.get(condition_key)
        ),
    )

    card = {
        "id": opp.get("id"),
        "status": opp.get("status"),
        "status_label": STATUS_LABELS.get(opp.get("status", ""), opp.get("status")),
        "type": opp.get("type"),
        "urgency_score": opp.get("urgency_score"),
        "brand": opp.get("brand") or "PEIX Partner",
        "product": recommended_product or "Atemwegslinie",
        "recommended_product": recommended_product,
        "region": opp.get("region") or (
            BUNDESLAND_NAMES.get(region_codes[0], region_codes[0]) if region_codes else "National"
        ),
        "region_codes": region_codes,
        "region_codes_display": [BUNDESLAND_NAMES.get(c, c) for c in region_codes],
        "budget_shift_pct": opp.get("budget_shift_pct") or (preview.get("budget") or {}).get("shift_pct") or 15.0,
        "channel_mix": opp.get("channel_mix") or {"programmatic": 35, "social": 30, "search": 20, "ctv": 15},
        "activation_window": {
            "start": opp.get("activation_start") or (preview.get("activation_window") or {}).get("start"),
            "end": opp.get("activation_end") or (preview.get("activation_window") or {}).get("end"),
        },
        "reason": public_reason_text(
            reason=opp.get("recommendation_reason"),
            event=trigger_context.get("event"),
            details=trigger_context.get("details"),
        ),
        "confidence": (
            round(float(opp.get("confidence")), 2)
            if opp.get("confidence") is not None
            else (
                round(float(signal_confidence_pct or 0.0) / 100.0, 2)
                if signal_confidence_pct is not None
                else None
            )
        ),
        "detail_url": opp.get("detail_url") or f"/kampagnen/{opp.get('id')}",
        "created_at": opp.get("created_at"),
        "updated_at": opp.get("updated_at"),
        "expires_at": opp.get("expires_at"),
        "campaign_name": preview_campaign_name or payload_campaign_name,
        "primary_kpi": preview.get("primary_kpi") or measurement.get("primary_kpi"),
        "mapping_status": opp.get("mapping_status") or product_mapping.get("mapping_status"),
        "mapping_confidence": opp.get("mapping_confidence") or product_mapping.get("mapping_confidence"),
        "mapping_reason": opp.get("mapping_reason") or product_mapping.get("mapping_reason"),
        "condition_key": condition_key,
        "condition_label": (
            opp.get("condition_label")
            or product_mapping.get("condition_label")
            or CONDITION_LABELS.get(condition_key)
        ),
        "mapping_candidate_product": opp.get("mapping_candidate_product") or product_mapping.get("candidate_product"),
        "mapping_rule_source": opp.get("rule_source") or product_mapping.get("rule_source"),
        "peix_context": cleaned_peix_context,
        "signal_score": signal_score,
        "priority_score": priority_score,
        "signal_confidence_pct": signal_confidence_pct,
        "field_contracts": field_contracts,
        "playbook_key": opp.get("playbook_key") or cleaned_playbook.get("key"),
        "playbook_title": public_playbook or opp.get("playbook_title") or cleaned_playbook.get("title"),
        "trigger_context": trigger_context,
        "trigger_snapshot": trigger_snapshot,
        "guardrail_notes": opp.get("guardrail_notes") or (campaign_pack.get("guardrail_report") or {}).get("applied_fixes") or [],
        "ai_generation_status": opp.get("ai_generation_status") or ai_meta.get("status"),
        "strategy_mode": opp.get("strategy_mode") or campaign_pack.get("strategy_mode"),
        "decision_brief": opp.get("decision_brief"),
        "display_title": public_title or _build_display_title(opp, recommended_product),
        "campaign_payload": cleaned_campaign_pack,
        "forecast_assessment": campaign_pack.get("forecast_assessment") or {},
        "opportunity_assessment": campaign_pack.get("opportunity_assessment") or {},
        "exploratory_signals": campaign_pack.get("exploratory_signals") or [],
    }

    if include_preview:
        card["campaign_preview"] = {
            "campaign_name": card.get("campaign_name"),
            "activation_window": preview.get("activation_window") or card.get("activation_window"),
            "budget": preview.get("budget") or {},
            "primary_kpi": card.get("primary_kpi"),
            "recommended_product": recommended_product,
            "mapping_status": card.get("mapping_status"),
            "peix_context": card.get("peix_context"),
            "forecast_assessment": card.get("forecast_assessment"),
            "opportunity_assessment": card.get("opportunity_assessment"),
            "playbook_key": card.get("playbook_key"),
            "playbook_title": card.get("playbook_title"),
            "ai_generation_status": card.get("ai_generation_status"),
        }

    return enrich_card_v2(card)
