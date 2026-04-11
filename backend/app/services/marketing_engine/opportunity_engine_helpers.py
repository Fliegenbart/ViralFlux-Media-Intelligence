"""Pure helper functions extracted from the marketing opportunity engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.media.copy_service import (
    public_event_label,
    public_reason_text,
    public_source_label,
)
from app.services.media.semantic_contracts import normalize_confidence_pct

from .opportunity_engine_constants import (
    BUNDESLAND_NAMES,
    LEGACY_TO_WORKFLOW,
    REGION_NAME_TO_CODE,
    WORKFLOW_STATUSES,
)


def normalize_region_token(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    upper = raw.upper()
    if upper in BUNDESLAND_NAMES:
        return upper

    lower = raw.lower()
    if lower in {"gesamt", "all", "de", "national", "deutschland"}:
        return "Gesamt"

    return REGION_NAME_TO_CODE.get(lower)


def canonical_brand(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if "gelo" in raw:
        return "gelo"
    return raw


def region_label(region_code: str) -> str:
    if region_code in BUNDESLAND_NAMES:
        return BUNDESLAND_NAMES[region_code]
    return region_code


def extract_region_codes_from_opportunity(opportunity: dict[str, Any]) -> list[str]:
    region_target = opportunity.get("region_target") or {}
    campaign_payload = opportunity.get("campaign_payload") or {}
    targeting = campaign_payload.get("targeting") or {}

    tokens: list[str] = []
    states = region_target.get("states")
    if isinstance(states, list):
        tokens.extend(str(item) for item in states if item)

    scope = targeting.get("region_scope")
    if isinstance(scope, list):
        tokens.extend(str(item) for item in scope if item)
    elif isinstance(scope, str) and scope.strip():
        tokens.append(scope)

    region_codes: set[str] = set()
    for token in tokens:
        normalized = normalize_region_token(token)
        if normalized == "Gesamt":
            return []
        if normalized:
            region_codes.add(normalized)
    return sorted(region_codes)


def derive_ranking_signal_context(
    ranking_signal_regions: dict[str, Any],
    selected_region: str,
    opportunity: dict[str, Any],
    *,
    ranking_signal_national: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trigger = opportunity.get("trigger_context") or {}

    if selected_region == "Gesamt":
        nat = ranking_signal_national or {}
        score = nat.get("national_score")
        if score is None:
            return {}
        return {
            "region_code": "Gesamt",
            "score": score,
            "signal_score": score,
            "ranking_signal_score": score,
            "band": nat.get("national_band"),
            "signal_band": nat.get("national_band"),
            "impact_probability": nat.get("national_impact_probability"),
            "drivers": nat.get("top_drivers") or [],
            "signal_drivers": nat.get("top_drivers") or [],
            "trigger_event": trigger.get("event"),
        }

    ranking_signal_entry = ranking_signal_regions.get(selected_region) or {}
    return {
        "region_code": selected_region,
        "score": ranking_signal_entry.get("score_0_100"),
        "signal_score": ranking_signal_entry.get("score_0_100"),
        "ranking_signal_score": ranking_signal_entry.get("score_0_100"),
        "band": ranking_signal_entry.get("risk_band"),
        "signal_band": ranking_signal_entry.get("risk_band"),
        "impact_probability": ranking_signal_entry.get("impact_probability"),
        "drivers": ranking_signal_entry.get("top_drivers") or [],
        "signal_drivers": ranking_signal_entry.get("top_drivers") or [],
        "trigger_event": trigger.get("event"),
    }


def derive_peix_context(
    peix_regions: dict[str, Any],
    selected_region: str,
    opportunity: dict[str, Any],
    *,
    peix_national: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return derive_ranking_signal_context(
        peix_regions,
        selected_region,
        opportunity,
        ranking_signal_national=peix_national,
    )


def fact_label(key: str) -> str:
    overrides = {
        "latest_incidence": "aktuelle Inzidenz",
        "previous_incidence": "Vorwochen-Inzidenz",
        "wow_pct": "Wochenwachstum",
        "p75": "oberes Vergleichsniveau",
        "bfarm_risk_score": "BfArM-Risikoscore",
        "respiratory_shortage_count": "Engpässe Atemwege",
        "pediatric_alert": "Kinderarznei-Hinweis",
        "are_growth_pct": "ARE-Wachstum",
        "weather_burden": "Wetterdruck",
        "psycho_level": "Suchdruck",
        "psycho_delta": "Suchtrend",
        "pollen_score": "Pollenlage",
        "allergy_search_level": "Allergie-Suche",
        "allergy_search_delta": "Allergie-Trend",
        "peix_score": "Ranking-Signal",
        "ranking_signal_score": "Ranking-Signal",
        "event_probability_pct": "Event-Wahrscheinlichkeit",
        "decision_priority_index": "Decision-Priority-Index",
        "forecast_readiness": "Forecast-Readiness",
        "truth_readiness": "Truth-Readiness",
        "avg_recent_incidence": "aktuelle Durchschnitts-Inzidenz",
        "growth_pct": "Wachstum",
        "total_infection_load": "gesamte Infektionslast",
        "median_load": "Median im Vergleich",
        "relative_to_median": "Abstand zum Median",
    }
    normalized = str(key or "").strip().lower()
    if normalized in overrides:
        return overrides[normalized]

    raw = str(key or "").strip().replace("_", " ")
    if not raw:
        return "Fakt"
    words = [word.capitalize() for word in raw.split() if word]
    return " ".join(words) or "Fakt"


def confidence_pct(raw_confidence: Any, urgency_score: float | None) -> float | None:
    del urgency_score
    return normalize_confidence_pct(raw_confidence)


def public_fact_value(key: str, value: Any) -> Any:
    normalized_key = str(key or "").strip().lower()

    if isinstance(value, bool):
        return "Ja" if value else "Nein"

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        if "source" in normalized_key:
            return public_source_label(stripped) or stripped
        if "event" in normalized_key:
            return public_event_label(stripped) or stripped
        return public_reason_text(reason=stripped)

    if isinstance(value, (int, float)):
        number = float(value)
        if any(token in normalized_key for token in ("pct", "probability", "delta", "growth", "share", "wow")):
            return f"{number:.1f}%"
        if any(token in normalized_key for token in ("score", "confidence", "strength")):
            return round(number, 1)
        if number.is_integer():
            return int(number)
        return round(number, 2)

    return value


def secondary_products(
    suggested_products: Any,
    mapping_candidate_product: str | None,
    primary_product: str | None,
) -> list[str]:
    primary = str(primary_product or "").strip().lower()
    out: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        raw = str(value or "").strip()
        if not raw:
            return
        norm = raw.lower()
        if primary and norm == primary:
            return
        if norm in seen:
            return
        seen.add(norm)
        out.append(raw)

    if isinstance(suggested_products, list):
        for item in suggested_products:
            if isinstance(item, str):
                add(item)
                continue
            if isinstance(item, dict):
                add(item.get("product_name") or item.get("product") or item.get("name"))
    add(mapping_candidate_product)
    return out


def clean_for_output(opp: dict[str, Any]) -> dict[str, Any]:
    """Entfernt interne _-Felder und promotiert Supply-Gap Felder für den API-Output."""
    clean = {k: v for k, v in opp.items() if not k.startswith("_")}

    clean["is_supply_gap_active"] = bool(opp.get("_supply_gap_applied", False))
    if clean["is_supply_gap_active"]:
        matched_products = opp.get("_supply_gap_matched_products", [])
        clean["supply_gap_match_examples"] = (
            ", ".join(matched_products[:3]) if matched_products else ""
        )
        clean["recommended_priority_multiplier"] = float(
            opp.get("_supply_gap_priority_multiplier", 1.0)
        )
        clean["supply_gap_product"] = opp.get("_supply_gap_product", "")
    else:
        clean["supply_gap_match_examples"] = ""
        clean["recommended_priority_multiplier"] = 1.0
        clean["supply_gap_product"] = ""

    return clean


def normalize_workflow_status(status: str | None) -> str:
    if not status:
        return "DRAFT"
    normalized = str(status).upper()
    if normalized in WORKFLOW_STATUSES:
        return normalized
    return LEGACY_TO_WORKFLOW.get(normalized, normalized)


def status_filter_values(status_filter: str) -> set[str]:
    normalized = normalize_workflow_status(status_filter)
    values = {normalized, status_filter.upper()}
    if normalized == "DRAFT":
        values.update({"NEW", "URGENT"})
    if normalized == "APPROVED":
        values.add("SENT")
    if normalized == "ACTIVATED":
        values.add("CONVERTED")
    return values


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
