from __future__ import annotations

from typing import Any


def build_region_rows(
    service,
    *,
    forecast: dict[str, Any],
    allocation: dict[str, Any],
    recommendations: dict[str, Any],
) -> list[dict[str, Any]]:
    forecast_rows = list(forecast.get("predictions") or [])
    allocation_rows = {
        str(item.get("bundesland") or item.get("region") or "").strip().upper(): item
        for item in (allocation.get("recommendations") or [])
    }
    recommendation_rows = {
        str(item.get("region") or "").strip().upper(): item
        for item in (recommendations.get("recommendations") or [])
    }
    rows: list[dict[str, Any]] = []
    for prediction in forecast_rows:
        region_code = str(prediction.get("bundesland") or "").strip().upper()
        allocation_item = allocation_rows.get(region_code) or {}
        recommendation_item = recommendation_rows.get(region_code) or {}
        decision_stage = (
            recommendation_item.get("activation_level")
            or allocation_item.get("recommended_activation_level")
            or prediction.get("decision_label")
            or "Beobachten"
        )
        decision_payload = allocation_item.get("decision") or prediction.get("decision") or {}
        reason_trace = service._unique_non_empty(
            [
                *service._reason_trace_lines(prediction.get("reason_trace")),
                *service._reason_trace_lines(allocation_item.get("reason_trace")),
                *service._reason_trace_lines(
                    recommendation_item.get("recommendation_rationale"),
                ),
                str(decision_payload.get("explanation_summary") or "").strip(),
                str(allocation_item.get("uncertainty_summary") or "").strip(),
            ]
        )
        reason_trace_details = service._unique_reason_details(
            [
                *service._reason_trace_detail_items(prediction.get("reason_trace")),
                *service._reason_trace_detail_items(allocation_item.get("reason_trace")),
                *service._reason_trace_detail_items(
                    recommendation_item.get("recommendation_rationale"),
                ),
                decision_payload.get("explanation_summary_detail"),
            ]
        )
        rows.append(
            {
                "region_code": region_code,
                "region_name": prediction.get("bundesland_name") or recommendation_item.get("region_name"),
                "decision_stage": decision_stage,
                "forecast_scope_readiness": service._forecast_scope_readiness(
                    {
                        "predictions": [prediction],
                        "quality_gate": forecast.get("quality_gate"),
                        "status": forecast.get("status"),
                    }
                ),
                "priority_rank": recommendation_item.get("priority_rank")
                or allocation_item.get("priority_rank")
                or prediction.get("decision_rank"),
                "priority_score": prediction.get("priority_score"),
                "event_probability": prediction.get("event_probability_calibrated"),
                "allocation_score": allocation_item.get("allocation_score"),
                "confidence": recommendation_item.get("confidence") or allocation_item.get("confidence"),
                "budget_share": allocation_item.get("suggested_budget_share"),
                "budget_amount_eur": allocation_item.get("suggested_budget_amount")
                or allocation_item.get("budget_eur"),
                "recommended_product": (
                    (recommendation_item.get("recommended_product_cluster") or {}).get("label")
                    or ((allocation_item.get("products") or [None])[0])
                ),
                "recommended_keywords": (
                    (recommendation_item.get("recommended_keyword_cluster") or {}).get("label")
                ),
                "campaign_recommendation": (
                    recommendation_item.get("timeline")
                    or recommendation_item.get("region_name")
                ),
                "channels": recommendation_item.get("channels") or allocation_item.get("channels") or [],
                "uncertainty_summary": allocation_item.get("uncertainty_summary")
                or prediction.get("uncertainty_summary"),
                "uncertainty_summary_detail": decision_payload.get("uncertainty_summary_detail"),
                "reason_trace": reason_trace[:4],
                "reason_trace_details": reason_trace_details[:6],
                "quality_gate": allocation_item.get("quality_gate") or forecast.get("quality_gate"),
                "business_gate": allocation_item.get("business_gate") or forecast.get("business_gate"),
                "spend_gate_status": allocation_item.get("spend_gate_status"),
                "budget_release_recommendation": allocation_item.get("budget_release_recommendation"),
            }
        )
    rows.sort(
        key=lambda item: (
            int(item.get("priority_rank") or 10_000),
            -float(item.get("priority_score") or 0.0),
            -float(item.get("event_probability") or 0.0),
        )
    )
    return rows


def build_executive_summary(
    service,
    *,
    virus_typ: str,
    horizon_days: int,
    weekly_budget_eur: float,
    forecast: dict[str, Any],
    allocation: dict[str, Any],
    recommendations: dict[str, Any],
    region_rows: list[dict[str, Any]],
    forecast_readiness: str,
    commercial_validation_status: str,
    budget_mode: str,
    validation_disclaimer: str,
    overall_scope_readiness: str,
    gate_snapshot: dict[str, Any],
) -> dict[str, Any]:
    lead_region = region_rows[0] if region_rows else {}
    lead_stage = str(lead_region.get("decision_stage") or "Beobachten")
    reason_trace = list(lead_region.get("reason_trace") or [])[:3]
    reason_trace_details = list(lead_region.get("reason_trace_details") or [])[:3]
    blocked_reasons = list(allocation.get("summary", {}).get("spend_blockers") or [])
    if gate_snapshot["missing_requirements"]:
        blocked_reasons = service._unique_non_empty(
            blocked_reasons + gate_snapshot["missing_requirements"]
        )
    if overall_scope_readiness == "GO" and gate_snapshot.get("budget_release_status") == "GO":
        recommendation_text = (
            f"Fokussiere {lead_region.get('region_name')} jetzt und gib das Wochenbudget in der empfohlenen Verteilung frei."
        )
    elif overall_scope_readiness == "GO":
        recommendation_text = (
            f"Fokussiere {lead_region.get('region_name')} jetzt und nutze die Verteilung unten als forecast-basierten Szenario-Split, solange die kommerzielle Validierung noch aussteht."
        )
    elif lead_region:
        recommendation_text = (
            f"Behalte {lead_region.get('region_name')} ganz oben auf dem Plan, aber gib Budget erst frei, wenn die offenen Gate-Anforderungen geschlossen sind."
        )
    else:
        recommendation_text = "Für diesen Scope liegt aktuell noch keine belastbare Kundenempfehlung vor."
    return {
        "what_should_we_do_now": recommendation_text,
        "decision_stage": lead_stage,
        "forecast_readiness": forecast_readiness,
        "commercial_validation_status": commercial_validation_status,
        "pilot_mode": "forecast_first",
        "budget_mode": budget_mode,
        "validation_disclaimer": validation_disclaimer,
        "scope_readiness": overall_scope_readiness,
        "headline": recommendations.get("headline")
        or allocation.get("headline")
        or f"{virus_typ} / h{horizon_days}",
        "top_regions": region_rows[:3],
        "budget_recommendation": {
            "weekly_budget_eur": round(float(weekly_budget_eur), 2),
            "recommended_active_budget_eur": allocation.get("summary", {}).get("total_budget_allocated"),
            "scenario_budget_eur": allocation.get("summary", {}).get("total_budget_allocated"),
            "spend_enabled": bool(allocation.get("summary", {}).get("spend_enabled")),
            "budget_mode": budget_mode,
            "blocked_reasons": blocked_reasons,
        },
        "confidence_summary": {
            "lead_region_confidence": lead_region.get("confidence"),
            "lead_region_event_probability": lead_region.get("event_probability"),
            "evaluation_retained": (gate_snapshot.get("latest_evaluation") or {}).get("retained"),
            "evaluation_gate_outcome": (gate_snapshot.get("latest_evaluation") or {}).get("gate_outcome"),
        },
        "uncertainty_summary": lead_region.get("uncertainty_summary"),
        "uncertainty_summary_detail": lead_region.get("uncertainty_summary_detail"),
        "reason_trace": reason_trace,
        "reason_trace_details": reason_trace_details,
    }
