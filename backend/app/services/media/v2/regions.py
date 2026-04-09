from __future__ import annotations

from typing import Any

from app.services.media.semantic_contracts import priority_score_contract, ranking_signal_contract

from .shared import JsonDict, generated_at


def build_regions_payload(
    service: Any,
    *,
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
) -> JsonDict:
    cockpit = service.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
    peix = cockpit.get("peix_epi_score") or {}
    map_section = cockpit.get("map") or {}
    suggestions = {
        item.get("region"): item
        for item in map_section.get("activation_suggestions", [])
        if item.get("region")
    }

    enriched_regions: dict[str, dict[str, Any]] = {}
    for code, region in (map_section.get("regions") or {}).items():
        peix_region = (peix.get("regions") or {}).get(code, {})
        suggestion = suggestions.get(code) or {}
        forecast_direction = service._forecast_direction(region)
        severity_score = service._severity_score(region)
        momentum_score = service._momentum_score(region=region, forecast_direction=forecast_direction)
        decision_mode = service._region_decision_mode(peix_region)
        actionability_score = service._actionability_score(
            region=region,
            suggestion=suggestion,
            severity_score=severity_score,
            momentum_score=momentum_score,
        )
        enriched_regions[code] = {
            **region,
            "signal_score": region.get("signal_score") or region.get("peix_score") or peix_region.get("score_0_100") or region.get("impact_probability"),
            "peix_score": region.get("peix_score") or peix_region.get("score_0_100"),
            "severity_score": severity_score,
            "momentum_score": momentum_score,
            "actionability_score": actionability_score,
            "forecast_direction": forecast_direction,
            "signal_drivers": peix_region.get("top_drivers") or [],
            "layer_contributions": peix_region.get("layer_contributions") or {},
            "budget_logic": suggestion.get("reason") or region.get("tooltip", {}).get("recommendation_text"),
            "decision_mode": decision_mode["key"],
            "decision_mode_label": decision_mode["label"],
            "decision_mode_reason": decision_mode["reason"],
            "priority_explanation": service._priority_explanation(
                region=region,
                suggestion=suggestion,
                forecast_direction=forecast_direction,
                severity_score=severity_score,
                momentum_score=momentum_score,
                actionability_score=actionability_score,
                decision_mode=decision_mode["key"],
            ),
            "source_trace": service._region_source_trace(peix_region),
            "field_contracts": {
                "signal_score": ranking_signal_contract(source="PeixEpiScore"),
                "priority_score": priority_score_contract(source="MediaV2Service"),
            },
        }

    sorted_regions = sorted(
        [{"code": code, **region} for code, region in enriched_regions.items()],
        key=lambda item: (
            float(item.get("actionability_score") or 0.0),
            float(item.get("severity_score") or 0.0),
            float(item.get("momentum_score") or 0.0),
            float(item.get("signal_score") or item.get("peix_score") or item.get("impact_probability") or 0.0),
        ),
        reverse=True,
    )
    for index, item in enumerate(sorted_regions, start=1):
        enriched_regions[item["code"]]["priority_rank"] = index
        item["priority_rank"] = index

    decision_payload = service.get_decision_payload(
        virus_typ=virus_typ,
        target_source=target_source,
        brand=brand,
    )
    return {
        "virus_typ": virus_typ,
        "target_source": target_source,
        "generated_at": generated_at(),
        "map": {
            **map_section,
            "regions": enriched_regions,
            "top_regions": sorted_regions[:5],
        },
        "top_regions": sorted_regions[:5],
        "decision_state": decision_payload.get("weekly_decision", {}).get("decision_state"),
    }
