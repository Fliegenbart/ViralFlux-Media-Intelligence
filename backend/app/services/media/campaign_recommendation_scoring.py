"""Selection and scoring helpers for campaign recommendations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.media.campaign_recommendation_contracts import (
    CampaignClusterSelection,
    CampaignRecommendationConfig,
    ProductClusterConfig,
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def available_products(allocation_item: Mapping[str, Any]) -> list[str]:
    products = [str(item) for item in (allocation_item.get("products") or []) if str(item).strip()]
    if products:
        return products
    clusters = allocation_item.get("product_clusters") or []
    collected: list[str] = []
    for cluster in clusters:
        for product in cluster.get("products") or []:
            value = str(product).strip()
            if value and value not in collected:
                collected.append(value)
    return collected


def select_product_cluster(
    config: CampaignRecommendationConfig,
    *,
    virus_typ: str,
    stage: str,
    region: str,
    confidence: float,
    available_products: Sequence[str],
    allocation_item: Mapping[str, Any],
) -> CampaignClusterSelection:
    hinted_clusters = {
        str(item.get("cluster_key") or ""): float(item.get("fit_score") or 0.0)
        for item in (allocation_item.get("product_clusters") or [])
    }
    candidates: list[CampaignClusterSelection] = []
    available_set = {str(product).strip() for product in available_products if str(product).strip()}
    for cluster in config.product_clusters:
        if cluster.supported_viruses and virus_typ not in set(cluster.supported_viruses):
            continue
        overlap = product_overlap(cluster=cluster, available_products=available_set)
        if overlap <= 0.0:
            continue
        allocation_hint = _clamp(hinted_clusters.get(cluster.cluster_key, 0.0))
        stage_fit = _clamp(float(cluster.activation_fit.get(stage, 0.70)))
        fit_multiplier = region_fit_multiplier(config, region=region, cluster_key=cluster.cluster_key)
        raw_fit = (
            0.35 * float(cluster.base_fit)
            + 0.25 * overlap
            + 0.20 * stage_fit
            + 0.10 * confidence
            + 0.10 * allocation_hint
        ) * fit_multiplier
        candidates.append(
            CampaignClusterSelection(
                cluster_key=cluster.cluster_key,
                label=cluster.label,
                fit_score=round(_clamp(raw_fit, 0.0, 1.25), 4),
                products=[product for product in cluster.products if product in available_set],
                metadata={
                    "source": "campaign_recommendation_v1",
                    "base_fit": round(float(cluster.base_fit), 4),
                    "product_overlap": round(overlap, 4),
                    "stage_fit": round(stage_fit, 4),
                    "allocation_hint": round(allocation_hint, 4),
                    "region_fit_multiplier": round(fit_multiplier, 4),
                    **dict(cluster.metadata or {}),
                },
            )
        )
    if candidates:
        candidates.sort(key=lambda item: (float(item.fit_score), len(item.products)), reverse=True)
        return candidates[0]

    return CampaignClusterSelection(
        cluster_key="unmapped_product_cluster",
        label="Fallback Product Cluster",
        fit_score=round(_clamp(0.40 + (confidence * 0.20)), 4),
        products=list(available_products),
        metadata={"source": "campaign_recommendation_fallback"},
    )


def select_keyword_cluster(
    config: CampaignRecommendationConfig,
    *,
    virus_typ: str,
    stage: str,
    region: str,
    confidence: float,
    product_cluster: CampaignClusterSelection,
) -> CampaignClusterSelection:
    candidates: list[CampaignClusterSelection] = []
    for cluster in config.keyword_clusters:
        if cluster.product_cluster_key != product_cluster.cluster_key:
            continue
        if cluster.supported_viruses and virus_typ not in set(cluster.supported_viruses):
            continue
        stage_fit = _clamp(float(cluster.activation_fit.get(stage, 0.70)))
        fit_multiplier = region_fit_multiplier(config, region=region, cluster_key=cluster.product_cluster_key)
        raw_fit = (
            0.50 * float(product_cluster.fit_score)
            + 0.25 * float(cluster.base_fit)
            + 0.15 * stage_fit
            + 0.10 * confidence
        ) * fit_multiplier
        candidates.append(
            CampaignClusterSelection(
                cluster_key=cluster.cluster_key,
                label=cluster.label,
                fit_score=round(_clamp(raw_fit, 0.0, 1.25), 4),
                keywords=list(cluster.keywords),
                metadata={
                    "source": "campaign_recommendation_v1",
                    "product_cluster_key": cluster.product_cluster_key,
                    "base_fit": round(float(cluster.base_fit), 4),
                    "stage_fit": round(stage_fit, 4),
                    "region_fit_multiplier": round(fit_multiplier, 4),
                    **dict(cluster.metadata or {}),
                },
            )
        )
    if candidates:
        candidates.sort(key=lambda item: (float(item.fit_score), len(item.keywords)), reverse=True)
        return candidates[0]

    return CampaignClusterSelection(
        cluster_key="fallback_keyword_cluster",
        label="Fallback Search Demand Cluster",
        fit_score=round(_clamp(0.35 + (0.25 * confidence)), 4),
        keywords=["atemwege beruhigen", "husten symptomhilfe", "erkaltung beschwerden"],
        metadata={"source": "campaign_recommendation_fallback"},
    )


def product_overlap(
    *,
    cluster: ProductClusterConfig,
    available_products: set[str],
) -> float:
    if not cluster.products:
        return 0.0
    overlap = len(set(cluster.products) & set(available_products))
    return _clamp(overlap / max(len(set(cluster.products)), 1))


def region_fit_multiplier(
    config: CampaignRecommendationConfig,
    *,
    region: str,
    cluster_key: str,
) -> float:
    region_fits = config.region_product_fit or {}
    return max(float((region_fits.get(region) or {}).get(cluster_key) or 1.0), 0.0)


def guardrail_status(
    config: CampaignRecommendationConfig,
    *,
    stage: str,
    budget_share: float,
    budget_amount: float,
    confidence: float,
    spend_gate_status: str,
) -> str:
    guardrails = config.spend_guardrails
    normalized_spend_status = str(spend_gate_status or "").strip()
    if stage == "watch" or budget_amount <= 0.0:
        return "observe_only"
    if normalized_spend_status in set(guardrails.blocked_spend_statuses):
        return "blocked"
    confidence_floor = (
        float(guardrails.min_confidence_for_activate)
        if stage == "activate"
        else float(guardrails.min_confidence_for_prepare)
    )
    if confidence < confidence_floor:
        return "low_confidence_review"
    if (
        budget_amount < float(guardrails.min_budget_amount_eur)
        or budget_share < float(guardrails.min_budget_share)
    ):
        return "bundle_with_neighbor_region"
    return "ready"


def evidence_class(allocation_item: Mapping[str, Any]) -> str:
    evidence_status = str(allocation_item.get("evidence_status") or "").strip()
    if evidence_status:
        return evidence_status
    if allocation_item.get("truth_layer_enabled"):
        return "truth_layer_pending"
    return "epidemiological_only"


def sort_key(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
    stage = str(item.get("activation_level") or "Watch").strip().lower()
    stage_order = {"activate": 3, "prepare": 2, "watch": 1}.get(stage, 0)
    guardrail_order = {
        "ready": 3,
        "bundle_with_neighbor_region": 2,
        "low_confidence_review": 1.5,
        "observe_only": 1,
        "blocked": 0,
    }.get(str(item.get("spend_guardrail_status") or ""), 0)
    return (
        float(stage_order),
        float(guardrail_order),
        float(item.get("suggested_budget_share") or 0.0),
        float(item.get("confidence") or 0.0),
    )


def headline(
    *,
    virus_typ: str,
    recommendations: Sequence[Mapping[str, Any]],
) -> str:
    if not recommendations:
        return f"{virus_typ}: keine Campaign Recommendations verfügbar"
    lead = recommendations[0]
    region = str(lead.get("region") or lead.get("bundesland") or "")
    cluster = ((lead.get("recommended_product_cluster") or {}).get("label")) or "Campaign Cluster"
    return f"{virus_typ}: {region} jetzt mit {cluster} diskutieren"
