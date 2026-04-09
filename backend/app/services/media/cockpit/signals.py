from __future__ import annotations

from typing import Any

from app.services.media.semantic_contracts import ranking_signal_contract


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def primary_signal_score(item: dict[str, Any] | None) -> float:
    payload = item or {}
    for key in ("signal_score", "peix_score", "score_0_100", "impact_probability"):
        score = coerce_float(payload.get(key))
        if score is not None:
            return round(score, 1)
    return 0.0


def build_ranking_signal_fields(
    *,
    signal_score: Any,
    source: str,
    legacy_alias: Any = None,
    label: str = "Signal-Score",
) -> dict[str, Any]:
    normalized_signal = coerce_float(signal_score)
    normalized_alias = coerce_float(legacy_alias)
    if normalized_signal is None:
        normalized_signal = normalized_alias
    if normalized_alias is None:
        normalized_alias = normalized_signal

    payload: dict[str, Any] = {
        "score_semantics": "ranking_signal",
        "impact_probability_semantics": "ranking_signal",
        "impact_probability_deprecated": True,
        "field_contracts": {
            "signal_score": ranking_signal_contract(source=source, label=label),
            "impact_probability": ranking_signal_contract(
                source=source,
                label="Legacy Signal-Score",
            ),
        },
    }
    if normalized_signal is not None:
        payload["signal_score"] = round(normalized_signal, 1)
    if normalized_alias is not None:
        payload["impact_probability"] = round(normalized_alias, 1)
    return payload


def normalize_recommendation_ref(
    recommendation_ref: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not recommendation_ref:
        return None
    return {
        "card_id": recommendation_ref.get("card_id"),
        "detail_url": recommendation_ref.get("detail_url"),
        "status": recommendation_ref.get("status"),
        "urgency_score": recommendation_ref.get("urgency_score"),
        "brand": recommendation_ref.get("brand"),
        "product": recommendation_ref.get("product"),
        "priority_score": recommendation_ref.get("priority_score"),
    }


def build_signal_snapshot_section(
    *,
    virus_typ: str,
    peix_score: dict[str, Any],
    map_section: dict[str, Any],
) -> dict[str, Any]:
    national = {
        "virus_typ": virus_typ,
        "band": peix_score.get("national_band"),
        "top_drivers": peix_score.get("top_drivers") or [],
    }
    national.update(build_ranking_signal_fields(
        signal_score=peix_score.get("national_score"),
        legacy_alias=peix_score.get("national_impact_probability"),
        source="PeixEpiScore",
    ))

    top_region = (map_section.get("top_regions") or [None])[0]
    top_region_snapshot = None
    if top_region:
        top_region_snapshot = {
            "code": top_region.get("code"),
            "name": top_region.get("name"),
            "trend": top_region.get("trend"),
        }
        top_region_snapshot.update(build_ranking_signal_fields(
            signal_score=top_region.get("signal_score") or top_region.get("peix_score"),
            legacy_alias=top_region.get("impact_probability"),
            source="PeixEpiScore",
        ))

    return {
        "national": national,
        "top_region": top_region_snapshot,
    }


def build_campaign_refs_section(
    region_recommendations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    refs = []
    for region_code, recommendation_ref in region_recommendations.items():
        normalized = normalize_recommendation_ref(recommendation_ref)
        if not normalized:
            continue
        refs.append({"region_code": region_code, **normalized})
    refs.sort(
        key=lambda item: float(item.get("priority_score") or item.get("urgency_score") or 0.0),
        reverse=True,
    )
    return {
        "regions_with_recommendations": len(refs),
        "items": refs[:12],
    }
