"""Truth and business gate helper functions for regional forecast service."""

from __future__ import annotations

from typing import Any


def truth_readiness(
    service,
    *,
    brand: str,
    forecast_decision_service_cls,
) -> dict[str, Any]:
    if service.db is None:
        return {
            "coverage_weeks": 0,
            "truth_readiness": "noch_nicht_angeschlossen",
            "truth_ready": False,
            "expected_units_lift_enabled": False,
            "expected_revenue_lift_enabled": False,
        }
    return forecast_decision_service_cls(service.db).get_truth_readiness(brand=brand)


def business_gate(
    service,
    *,
    quality_gate: dict[str, Any],
    truth_readiness: dict[str, Any] | None = None,
    brand: str = "gelo",
    business_validation_service_cls,
) -> dict[str, Any]:
    forecast_ready = bool((quality_gate or {}).get("overall_passed"))
    if service.db is None:
        truth = truth_readiness or service._truth_readiness(brand=brand)
        return {
            "truth_readiness": str(truth.get("truth_readiness") or "noch_nicht_angeschlossen"),
            "truth_ready": bool(truth.get("truth_ready")),
            "coverage_weeks": int(truth.get("coverage_weeks") or 0),
            "expected_units_lift_enabled": False,
            "expected_revenue_lift_enabled": False,
            "action_class": "watch_only" if not forecast_ready else "market_watch",
            "validation_status": "pending_truth_connection" if int(truth.get("coverage_weeks") or 0) <= 0 else "building_truth_layer",
            "decision_scope": "decision_support_only",
            "validated_for_budget_activation": False,
            "evidence_tier": "no_truth" if int(truth.get("coverage_weeks") or 0) <= 0 else "observational",
        }

    validation = business_validation_service_cls(service.db).evaluate(
        brand=brand,
        truth_coverage=truth_readiness,
    )
    validation["quality_gate_passed"] = forecast_ready
    return validation


def truth_layer_assessment_for_products(
    service,
    *,
    region_code: str,
    products: list[str],
    target_week_start: Any,
    signal_context: dict[str, Any],
    operational_action: str,
    operational_gate_open: bool,
    brand: str = "gelo",
) -> dict[str, Any]:
    normalized_products = [
        str(product).strip()
        for product in products
        if str(product or "").strip()
    ] or [""]
    window_start, window_end = service._truth_assessment_window(target_week_start)
    assessments: list[dict[str, Any]] = []
    for product in normalized_products:
        assessment = service._truth_layer_assessment_for_product(
            brand=brand,
            region_code=region_code,
            product=product or None,
            window_start=window_start,
            window_end=window_end,
            signal_context=signal_context,
        )
        spend_gate_status, budget_release_recommendation = service._commercial_truth_gate(
            truth_assessment=assessment,
            operational_action=operational_action,
            operational_gate_open=operational_gate_open,
        )
        assessments.append(
            {
                "product": product or None,
                "scope": assessment.get("scope") or {},
                "outcome_readiness": assessment.get("outcome_readiness") or {},
                "evidence_status": assessment.get("evidence_status"),
                "evidence_confidence": assessment.get("evidence_confidence"),
                "signal_outcome_agreement": assessment.get("signal_outcome_agreement") or {},
                "holdout_eligibility": assessment.get("holdout_eligibility") or {},
                "commercial_gate": assessment.get("commercial_gate") or {},
                "metadata": assessment.get("metadata") or {},
                "spend_gate_status": spend_gate_status,
                "budget_release_recommendation": budget_release_recommendation,
            }
        )

    primary = assessments[0]
    return {
        "truth_layer_enabled": bool(service.db is not None),
        "truth_scope": {
            "brand": str(brand or "gelo").strip().lower(),
            "region_code": str(region_code or "").strip().upper() or None,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "lookback_weeks": 26,
            "products": [item["product"] for item in assessments],
            "primary_product": primary["product"],
        },
        "outcome_readiness": primary["outcome_readiness"],
        "evidence_status": primary["evidence_status"],
        "evidence_confidence": primary["evidence_confidence"],
        "signal_outcome_agreement": primary["signal_outcome_agreement"],
        "spend_gate_status": primary["spend_gate_status"],
        "budget_release_recommendation": primary["budget_release_recommendation"],
        "commercial_gate": primary["commercial_gate"],
        "truth_assessments": assessments,
    }


def truth_layer_assessment_for_product(
    service,
    *,
    brand: str,
    region_code: str,
    product: str | None,
    window_start,
    window_end,
    signal_context: dict[str, Any],
    truth_layer_service_cls,
    logger,
) -> dict[str, Any]:
    if service.db is None:
        return service._fallback_truth_assessment(
            brand=brand,
            region_code=region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
            signal_context=signal_context,
            source_mode="unavailable",
            message="Truth-Layer ist optional; in dieser Laufzeit ist keine Outcome-Datenbank verbunden.",
        )
    try:
        return truth_layer_service_cls(service.db).assess(
            brand=brand,
            region_code=region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
            signal_context=signal_context,
        )
    except Exception:
        logger.exception(
            "Truth layer assessment failed for brand=%s region=%s product=%s",
            brand,
            region_code,
            product,
        )
        return service._fallback_truth_assessment(
            brand=brand,
            region_code=region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
            signal_context=signal_context,
            source_mode="error",
            message="Truth-Layer konnte für diese Scope-Abfrage nicht ausgewertet werden.",
        )


def truth_assessment_window(
    target_week_start: Any,
    *,
    truth_lookback_weeks: int,
    pd_module,
):
    target_start = pd_module.Timestamp(target_week_start).normalize()
    return (
        (target_start - pd_module.Timedelta(weeks=truth_lookback_weeks)).to_pydatetime(),
        (target_start + pd_module.Timedelta(days=6)).to_pydatetime(),
    )


def truth_signal_context(
    *,
    prediction: dict[str, Any],
    confidence: float | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    decision = dict(prediction.get("decision") or {})
    decision_stage = str(
        stage
        or decision.get("stage")
        or prediction.get("decision_label")
        or ""
    ).strip().lower()
    event_probability = float(
        prediction.get("event_probability")
        or prediction.get("event_probability_calibrated")
        or 0.0
    )
    forecast_confidence = (
        confidence
        if confidence is not None
        else decision.get("signal_support_score") or decision.get("forecast_confidence")
    )
    signal_present = decision_stage in {"activate", "prepare"} or event_probability >= 0.5
    context = {
        "signal_present": signal_present,
        "decision_stage": decision_stage or None,
        "event_probability": event_probability,
    }
    if forecast_confidence is not None:
        context["confidence"] = float(forecast_confidence)
        context["signal_support_score"] = float(forecast_confidence)
        context["forecast_confidence"] = float(forecast_confidence)
    return context


def fallback_truth_assessment(
    *,
    brand: str,
    region_code: str,
    product: str | None,
    window_start,
    window_end,
    signal_context: dict[str, Any],
    source_mode: str,
    message: str,
) -> dict[str, Any]:
    signal_present = bool(signal_context.get("signal_present"))
    signal_confidence = signal_context.get("confidence") or signal_context.get("forecast_confidence")
    try:
        normalized_confidence = float(signal_confidence or signal_context.get("event_probability") or 0.0)
    except (TypeError, ValueError):
        normalized_confidence = 0.0
    return {
        "scope": {
            "brand": str(brand or "gelo").strip().lower(),
            "region_code": str(region_code or "").strip().upper() or None,
            "product": str(product).strip() if product else None,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
        "outcome_readiness": {
            "status": "missing",
            "score": 0.0,
            "coverage_weeks": 0,
            "metrics_present": [],
            "regions_present": 0,
            "products_present": 0,
            "spend_windows": 0,
            "response_windows": 0,
            "notes": [message],
        },
        "signal_outcome_agreement": {
            "status": "no_outcome_support" if signal_present else "no_signal",
            "signal_present": signal_present,
            "historical_response_observed": False,
            "score": round(0.2 * normalized_confidence, 4) if signal_present else None,
            "signal_confidence": round(normalized_confidence, 4) if signal_present else None,
            "outcome_support_score": 0.0,
            "outcome_confidence": 0.0,
            "notes": [message],
        },
        "holdout_eligibility": {
            "eligible": False,
            "ready": False,
            "holdout_groups": [],
            "reason": "No scoped outcome data is available for holdout validation.",
        },
        "evidence_status": "no_truth",
        "evidence_confidence": 0.0,
        "commercial_gate": {
            "budget_decision_allowed": False,
            "decision_scope": "decision_support_only",
            "message": message,
        },
        "metadata": {
            "source_mode": source_mode,
            "observations": 0,
            "metrics_present": [],
            "optional_layer": True,
        },
    }


def commercial_truth_gate(
    *,
    truth_assessment: dict[str, Any],
    operational_action: str,
    operational_gate_open: bool,
) -> tuple[str, str]:
    action = str(operational_action or "watch").strip().lower()
    evidence_status = str(truth_assessment.get("evidence_status") or "no_truth").strip().lower()
    budget_allowed = bool((truth_assessment.get("commercial_gate") or {}).get("budget_decision_allowed"))

    if action == "prioritize":
        return "prioritize_only", "hold"
    if action not in {"activate", "prepare"}:
        return "not_applicable", "hold"
    if not operational_gate_open:
        return "blocked_operational_gate", "hold"
    if budget_allowed or evidence_status == "commercially_validated":
        return "released", "release"
    if evidence_status in {"holdout_ready", "truth_backed"}:
        return "guarded_release", "limited_release"
    return "manual_review_required", "manual_review"


def truth_layer_rollup(
    service,
    items: list[dict[str, Any]],
    *,
    truth_lookback_weeks: int,
) -> dict[str, Any]:
    evidence_status_counts: dict[str, int] = {}
    spend_gate_status_counts: dict[str, int] = {}
    budget_release_counts: dict[str, int] = {}
    for item in items:
        evidence_status = str(item.get("evidence_status") or "").strip()
        spend_gate_status = str(item.get("spend_gate_status") or "").strip()
        budget_release = str(item.get("budget_release_recommendation") or "").strip()
        if evidence_status:
            evidence_status_counts[evidence_status] = evidence_status_counts.get(evidence_status, 0) + 1
        if spend_gate_status:
            spend_gate_status_counts[spend_gate_status] = spend_gate_status_counts.get(spend_gate_status, 0) + 1
        if budget_release:
            budget_release_counts[budget_release] = budget_release_counts.get(budget_release, 0) + 1
    return {
        "enabled": bool(service.db is not None),
        "lookback_weeks": truth_lookback_weeks,
        "scopes_evaluated": len(items),
        "evidence_status_counts": evidence_status_counts,
        "spend_gate_status_counts": spend_gate_status_counts,
        "budget_release_recommendation_counts": budget_release_counts,
    }
