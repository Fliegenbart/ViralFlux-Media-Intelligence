"""Rationale builders for campaign recommendations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.services.media.campaign_recommendation_contracts import (
    CampaignClusterSelection,
    CampaignRecommendationRationale,
)


def build_rationale(
    *,
    reason_detail_builder: Callable[..., dict[str, Any]],
    stage: str,
    allocation_item: Mapping[str, Any],
    product_cluster: CampaignClusterSelection,
    keyword_cluster: CampaignClusterSelection,
    evidence_class: str,
    guardrail_status: str,
    budget_share: float,
    budget_amount: float,
) -> CampaignRecommendationRationale:
    region_name = str(
        allocation_item.get("bundesland_name")
        or allocation_item.get("region_name")
        or allocation_item.get("bundesland")
        or ""
    )
    confidence = float(allocation_item.get("confidence") or 0.0)
    stage_key = str(stage or "").strip().lower()
    if stage_key == "prepare" and budget_amount <= 0.0:
        why = [
            f"{region_name} is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
            f"Allocation confidence {confidence:.2f} is good enough for preparation work, not for live spend release.",
        ]
        why_details = [
            reason_detail_builder(
                "campaign_prepare_early_warning",
                why[0],
                region_name=region_name,
                stage=stage,
                budget_amount=round(budget_amount, 2),
            ),
            reason_detail_builder(
                "campaign_prepare_no_live_spend",
                why[1],
                confidence=round(confidence, 4),
                priority_rank=int(allocation_item.get("priority_rank") or 0),
            ),
        ]
    else:
        why = [
            f"{region_name} stays on {stage} with budget share {budget_share:.2%}.",
            f"Allocation confidence {confidence:.2f} and priority rank {int(allocation_item.get('priority_rank') or 0)} keep the region in the current wave plan.",
        ]
        why_details = [
            reason_detail_builder(
                "campaign_stage_budget_share",
                why[0],
                region_name=region_name,
                stage=stage,
                budget_share=round(budget_share, 6),
            ),
            reason_detail_builder(
                "campaign_wave_plan_support",
                why[1],
                confidence=round(confidence, 4),
                priority_rank=int(allocation_item.get("priority_rank") or 0),
            ),
        ]
    product_fit = [
        f"{product_cluster.label} scores {float(product_cluster.fit_score):.2f} for the available product set {product_cluster.products or allocation_item.get('products') or []}.",
    ]
    product_fit_details = [
        reason_detail_builder(
            "campaign_product_cluster_fit",
            product_fit[0],
            cluster_label=product_cluster.label,
            fit_score=round(float(product_cluster.fit_score), 4),
            products=product_cluster.products or allocation_item.get("products") or [],
        ),
    ]
    region_multiplier = float(product_cluster.metadata.get("region_fit_multiplier") or 1.0)
    if region_multiplier > 1.0:
        message = f"Region/product fit boosts this cluster by {region_multiplier:.2f}."
        product_fit.append(message)
        product_fit_details.append(
            reason_detail_builder(
                "campaign_region_product_fit_boost",
                message,
                region_fit_multiplier=round(region_multiplier, 4),
            )
        )
    keyword_fit = [
        f"{keyword_cluster.label} translates the product cluster into concrete search intent with fit {float(keyword_cluster.fit_score):.2f}.",
    ]
    keyword_fit_details = [
        reason_detail_builder(
            "campaign_keyword_cluster_fit",
            keyword_fit[0],
            cluster_label=keyword_cluster.label,
            fit_score=round(float(keyword_cluster.fit_score), 4),
        ),
    ]
    if stage_key == "prepare" and budget_amount <= 0.0:
        budget_notes = [
            "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
        ]
    else:
        budget_notes = [
            f"Suggested campaign budget is {budget_amount:.2f} EUR.",
        ]
    budget_note_details = [
        reason_detail_builder(
            "campaign_budget_amount",
            budget_notes[0],
            budget_amount=round(budget_amount, 2),
        ),
    ]
    if budget_share > 0.0:
        message = f"Budget share contribution is {budget_share:.2%}."
        budget_notes.append(message)
        budget_note_details.append(
            reason_detail_builder(
                "campaign_budget_share",
                message,
                budget_share=round(budget_share, 6),
            )
        )

    evidence_notes = [
        f"Evidence class is {evidence_class}.",
    ]
    evidence_note_details = [
        reason_detail_builder(
            "campaign_evidence_class",
            evidence_notes[0],
            evidence_class=evidence_class,
        ),
    ]
    signal_outcome_agreement = allocation_item.get("signal_outcome_agreement") or {}
    if signal_outcome_agreement.get("status"):
        message = f"Signal/outcome agreement is {signal_outcome_agreement.get('status')}."
        evidence_notes.append(message)
        evidence_note_details.append(
            reason_detail_builder(
                "campaign_signal_outcome_agreement",
                message,
                status=str(signal_outcome_agreement.get("status")),
            )
        )

    guardrails: list[str] = []
    guardrail_details: list[dict[str, Any]] = []
    if guardrail_status == "ready":
        message = "Spend guardrails are currently satisfied."
        guardrails.append(message)
        guardrail_details.append(reason_detail_builder("campaign_guardrail_ready", message))
    elif guardrail_status == "bundle_with_neighbor_region":
        message = "Budget is below the standalone threshold and should be bundled with a neighboring region or shared flight."
        guardrails.append(message)
        guardrail_details.append(
            reason_detail_builder("campaign_guardrail_bundle_neighbor", message)
        )
    elif guardrail_status == "low_confidence_review":
        message = "Confidence is below the stage-specific guardrail, so the recommendation needs manual review."
        guardrails.append(message)
        guardrail_details.append(
            reason_detail_builder(
                "campaign_guardrail_low_confidence_review",
                message,
                confidence=round(confidence, 4),
            )
        )
    elif guardrail_status == "blocked":
        message = "Operational or commercial spend gate is still blocking execution."
        guardrails.append(message)
        guardrail_details.append(
            reason_detail_builder("campaign_guardrail_blocked", message)
        )
    else:
        message = "Recommendation stays preparation-only for now."
        guardrails.append(message)
        guardrail_details.append(
            reason_detail_builder("campaign_guardrail_discussion_only", message)
        )

    return CampaignRecommendationRationale(
        why=why,
        why_details=why_details,
        product_fit=product_fit,
        product_fit_details=product_fit_details,
        keyword_fit=keyword_fit,
        keyword_fit_details=keyword_fit_details,
        budget_notes=budget_notes,
        budget_note_details=budget_note_details,
        evidence_notes=evidence_notes,
        evidence_note_details=evidence_note_details,
        guardrails=guardrails,
        guardrail_details=guardrail_details,
    )
