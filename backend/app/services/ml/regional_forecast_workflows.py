"""Workflow helpers for regional forecast media and campaign flows."""

from __future__ import annotations

from typing import Any


def generate_media_allocation(
    service,
    *,
    virus_typ: str = "Influenza A",
    weekly_budget_eur: float = 50000,
    horizon_days: int = 7,
    rollout_mode_for_virus_fn,
    activation_policy_for_virus_fn,
    portfolio_products,
    media_channels,
    utc_now_fn,
) -> dict[str, Any]:
    forecast = service.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)
    predictions = forecast.get("predictions") or []
    quality_gate = forecast.get("quality_gate") or {"overall_passed": False}
    business_gate = forecast.get("business_gate") or service._business_gate(quality_gate=quality_gate)
    threshold = float(forecast.get("action_threshold") or 0.6)
    rollout_mode = str(forecast.get("rollout_mode") or rollout_mode_for_virus_fn(virus_typ))
    activation_policy = str(
        forecast.get("activation_policy") or activation_policy_for_virus_fn(virus_typ)
    )

    if not predictions:
        return service._empty_media_allocation_response(
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
            status=str(forecast.get("status") or "no_data"),
            message=str(
                forecast.get("message")
                or "Keine regionalen Forecast-/Decision-Daten verfügbar."
            ),
            quality_gate=quality_gate,
            business_gate=business_gate,
            rollout_mode=rollout_mode,
            activation_policy=activation_policy,
        )

    spend_enabled, spend_blockers = service._media_spend_gate(
        quality_gate=quality_gate,
        business_gate=business_gate,
        activation_policy=activation_policy,
    )
    allocation = service.media_allocation_engine.allocate(
        virus_typ=virus_typ,
        predictions=predictions,
        total_budget_eur=weekly_budget_eur,
        spend_enabled=spend_enabled,
        spend_blockers=spend_blockers,
        default_products=portfolio_products.get(virus_typ, ["GeloMyrtol forte"]),
    )
    allocation_by_region = {
        item["bundesland"]: item
        for item in allocation.get("recommendations") or []
    }

    recommendations = []
    for item in predictions:
        allocation_item = allocation_by_region.get(item["bundesland"], {})
        recommended_level = str(
            allocation_item.get("recommended_activation_level")
            or item.get("decision_label")
            or "Watch"
        )
        action = service._media_action(
            recommended_level=recommended_level,
            spend_enabled=spend_enabled,
        )
        intensity = service._media_intensity(action)
        budget_share = round(float(allocation_item.get("suggested_budget_share") or 0.0), 6)
        budget_eur = round(float(allocation_item.get("suggested_budget_eur") or 0.0), 2)
        suggested_budget_amount = round(
            float(allocation_item.get("suggested_budget_amount") or budget_eur),
            2,
        )
        allocation_reason_trace = (
            allocation_item.get("allocation_reason_trace")
            or allocation_item.get("reason_trace")
            or item.get("reason_trace")
        )
        products = service._products_from_allocation(
            allocation_item=allocation_item,
            virus_typ=virus_typ,
        )
        truth_overlay = service._truth_layer_assessment_for_products(
            region_code=item["bundesland"],
            products=products,
            target_week_start=item["target_week_start"],
            signal_context=service._truth_signal_context(
                prediction=item,
                confidence=allocation_item.get("allocation_support_score") or allocation_item.get("confidence"),
                stage=recommended_level,
            ),
            operational_action=action,
            operational_gate_open=spend_enabled,
        )

        recommendations.append(
            {
                "bundesland": item["bundesland"],
                "bundesland_name": item["bundesland_name"],
                "rank": item["rank"],
                "decision_rank": item.get("decision_rank"),
                "priority_rank": allocation_item.get("priority_rank"),
                "action": action,
                "intensity": intensity,
                "recommended_activation_level": recommended_level,
                "spend_readiness": allocation_item.get("spend_readiness"),
                "event_probability": (
                    item.get("event_probability")
                    or item.get("event_probability_calibrated")
                ),
                "decision_label": item.get("decision_label"),
                "decision_priority_index": item.get("decision_priority_index") or item.get("priority_score"),
                "allocation_score": allocation_item.get("allocation_score"),
                "allocation_support_score": (
                    allocation_item.get("allocation_support_score")
                    or allocation_item.get("confidence")
                ),
                "reason_trace": allocation_reason_trace,
                "allocation_reason_trace": allocation_reason_trace,
                "uncertainty_summary": item.get("uncertainty_summary"),
                "decision": item.get("decision"),
                "change_pct": item["change_pct"],
                "trend": item["trend"],
                "budget_share": budget_share,
                "suggested_budget_share": budget_share,
                "budget_eur": budget_eur,
                "suggested_budget_eur": budget_eur,
                "suggested_budget_amount": suggested_budget_amount,
                "channels": media_channels[intensity],
                "products": products,
                "product_clusters": allocation_item.get("product_clusters") or [],
                "keyword_clusters": allocation_item.get("keyword_clusters") or [],
                "timeline": service._media_timeline(
                    action=action,
                    spend_enabled=spend_enabled,
                    activation_policy=activation_policy,
                    business_gate=business_gate,
                    quality_gate=quality_gate,
                ),
                "current_load": item["current_known_incidence"],
                "predicted_load": item["expected_next_week_incidence"],
                "quality_gate": quality_gate,
                "business_gate": business_gate,
                "evidence_tier": business_gate.get("evidence_tier"),
                "rollout_mode": rollout_mode,
                "activation_policy": activation_policy,
                "activation_threshold": threshold,
                "allocation_policy_version": allocation.get("allocation_policy_version"),
                "as_of_date": item["as_of_date"],
                "target_week_start": item["target_week_start"],
                "truth_layer_enabled": truth_overlay["truth_layer_enabled"],
                "truth_scope": truth_overlay["truth_scope"],
                "outcome_readiness": truth_overlay["outcome_readiness"],
                "evidence_status": truth_overlay["evidence_status"],
                "evidence_confidence": truth_overlay["evidence_confidence"],
                "signal_outcome_agreement": truth_overlay["signal_outcome_agreement"],
                "spend_gate_status": truth_overlay["spend_gate_status"],
                "budget_release_recommendation": truth_overlay["budget_release_recommendation"],
                "commercial_gate": truth_overlay["commercial_gate"],
                "truth_assessments": truth_overlay["truth_assessments"],
            }
        )

    recommendations.sort(
        key=lambda item: (
            float(item.get("priority_rank") or 0),
            -float(item.get("suggested_budget_share") or 0.0),
        ),
    )
    recommendations = list(recommendations)

    summary = {
        "activate_regions": sum(1 for item in recommendations if item["action"] == "activate"),
        "prepare_regions": sum(1 for item in recommendations if item["action"] == "prepare"),
        "watch_regions": sum(1 for item in recommendations if item["action"] == "watch"),
        "total_budget_allocated": round(sum(item["budget_eur"] for item in recommendations), 2),
        "budget_share_total": round(sum(item["suggested_budget_share"] for item in recommendations), 6),
        "weekly_budget": round(float(weekly_budget_eur), 2),
        "quality_gate": quality_gate,
        "business_gate": business_gate,
        "evidence_tier": business_gate.get("evidence_tier"),
        "rollout_mode": rollout_mode,
        "activation_policy": activation_policy,
        "allocation_policy_version": allocation.get("allocation_policy_version"),
        "spend_enabled": spend_enabled,
        "spend_blockers": spend_blockers,
    }
    truth_layer = service._truth_layer_rollup(recommendations)

    return {
        "virus_typ": virus_typ,
        "headline": service._media_headline(
            virus_typ=virus_typ,
            recommendations=recommendations,
            spend_enabled=spend_enabled,
        ),
        "summary": summary,
        "allocation_config": allocation.get("config") or {},
        "horizon_days": horizon_days,
        "truth_layer": truth_layer,
        "generated_at": utc_now_fn().isoformat(),
        "recommendations": recommendations,
    }


def generate_media_activation(
    service,
    *,
    virus_typ: str = "Influenza A",
    weekly_budget_eur: float = 50000,
    horizon_days: int = 7,
) -> dict[str, Any]:
    return service.generate_media_allocation(
        virus_typ=virus_typ,
        weekly_budget_eur=weekly_budget_eur,
        horizon_days=horizon_days,
    )


def generate_campaign_recommendations(
    service,
    *,
    virus_typ: str = "Influenza A",
    weekly_budget_eur: float = 50000,
    horizon_days: int = 7,
    top_n: int | None = None,
) -> dict[str, Any]:
    allocation_payload = service.generate_media_allocation(
        virus_typ=virus_typ,
        weekly_budget_eur=weekly_budget_eur,
        horizon_days=horizon_days,
    )
    recommendation_payload = service.campaign_recommendation_service.recommend_from_allocation(
        allocation_payload=allocation_payload,
        top_n=top_n,
    )
    recommendation_payload.setdefault("horizon_days", horizon_days)
    recommendation_payload.setdefault(
        "target_window_days",
        allocation_payload.get("target_window_days") or service._target_window_for_horizon(horizon_days),
    )
    return recommendation_payload
