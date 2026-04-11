"""Media decision helper functions for regional forecast service."""

from __future__ import annotations

from typing import Any


def decision_stage_sort_value(stage: str | None) -> int:
    return {
        "activate": 3,
        "prepare": 2,
        "watch": 1,
    }.get(str(stage or "watch").strip().lower(), 0)


def decision_priority_sort_key(item: dict[str, Any]) -> tuple[float, float, float, float]:
    decision = item.get("decision") or {}
    return (
        float(decision_stage_sort_value(decision.get("stage"))),
        float(item.get("priority_score") or 0.0),
        float(item.get("event_probability_calibrated") or 0.0),
        float(item.get("change_pct") or 0.0),
    )


def decision_summary(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    if not predictions:
        return {
            "watch_regions": 0,
            "prepare_regions": 0,
            "activate_regions": 0,
            "avg_priority_score": 0.0,
            "top_region": None,
            "top_region_decision": None,
        }

    ranked_decisions = sorted(
        predictions,
        key=decision_priority_sort_key,
        reverse=True,
    )
    top_region = ranked_decisions[0]
    return {
        "watch_regions": sum(1 for item in predictions if str(item.get("decision_label") or "").lower() == "watch"),
        "prepare_regions": sum(1 for item in predictions if str(item.get("decision_label") or "").lower() == "prepare"),
        "activate_regions": sum(1 for item in predictions if str(item.get("decision_label") or "").lower() == "activate"),
        "avg_priority_score": round(
            sum(float(item.get("priority_score") or 0.0) for item in predictions) / len(predictions),
            4,
        ),
        "top_region": top_region.get("bundesland"),
        "top_region_decision": top_region.get("decision_label"),
    }


def media_spend_gate(
    *,
    quality_gate: dict[str, Any],
    business_gate: dict[str, Any],
    activation_policy: str,
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if activation_policy == "watch_only":
        blockers.append("Activation policy 'watch_only' keeps the region in preparation-only mode.")
    if not business_gate.get("validated_for_budget_activation"):
        blockers.append("Business-Gate noch nicht validiert.")
    if not quality_gate.get("overall_passed"):
        blockers.append("Quality Gate blockiert Aktivierung.")
    return len(blockers) == 0, blockers


def media_action(
    *,
    recommended_level: str,
    spend_enabled: bool,
) -> str:
    stage = str(recommended_level or "Watch").strip().lower()
    if not spend_enabled:
        return "prepare" if stage in {"activate", "prepare"} else "watch"
    if stage in {"activate", "prepare"}:
        return stage
    return "watch"


def media_intensity(action: str) -> str:
    return {
        "activate": "high",
        "prepare": "medium",
    }.get(str(action or "watch").strip().lower(), "low")


def products_from_allocation(
    *,
    allocation_item: dict[str, Any],
    virus_typ: str,
    portfolio_products: dict[str, list[str]],
) -> list[str]:
    product_clusters = allocation_item.get("product_clusters") or []
    if product_clusters:
        cluster = product_clusters[0] or {}
        products = [str(item) for item in cluster.get("products") or [] if str(item).strip()]
        if products:
            return products
    return portfolio_products.get(virus_typ, ["GeloMyrtol forte"])


def media_timeline(
    *,
    action: str,
    spend_enabled: bool,
    activation_policy: str,
    business_gate: dict[str, Any],
    quality_gate: dict[str, Any],
    target_window_days: list[int],
) -> str:
    if not spend_enabled:
        if action == "prepare":
            if activation_policy == "watch_only":
                return "Nur vorbereiten — Shadow-Policy blockiert Aktivierung"
            if not business_gate.get("validated_for_budget_activation"):
                return "Nur vorbereiten — Business-Gate noch nicht validiert"
            if not quality_gate.get("overall_passed"):
                return "Nur vorbereiten — Quality Gate blockiert Aktivierung"
            return "Nur vorbereiten — Spend aktuell blockiert"
        return (
            "Nur beobachten — Shadow-Policy blockiert Aktivierung"
            if activation_policy == "watch_only"
            else "Nur beobachten — Business-Gate noch nicht validiert"
            if not business_gate.get("validated_for_budget_activation")
            else "Nur beobachten — Quality Gate blockiert Aktivierung"
            if not quality_gate.get("overall_passed")
            else "Nur beobachten — Spend aktuell blockiert"
        )
    if action == "activate":
        return f"Sofort aktivieren — Wellenfenster in {target_window_days[0]}-{target_window_days[1]} Tagen"
    if action == "prepare":
        return "In 1-2 Tagen vorbereiten — Signal für regionale Aktivierung vorhanden"
    return "Beobachten — unterhalb des operationalen Spend-Niveaus"


def media_headline(
    *,
    virus_typ: str,
    recommendations: list[dict[str, Any]],
    spend_enabled: bool,
) -> str:
    prioritized = [
        item["bundesland"]
        for item in recommendations
        if item["action"] in {"activate", "prepare"} and float(item.get("suggested_budget_share") or 0.0) > 0.0
    ]
    if prioritized and spend_enabled:
        return f"{virus_typ}: Budget auf {', '.join(prioritized[:3])} fokussieren"
    return f"{virus_typ}: aktuell kein validierter Aktivierungs-Case"


def metric_delta(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, float]:
    delta: dict[str, float] = {}
    for metric in (
        "precision_at_top3",
        "precision_at_top5",
        "pr_auc",
        "brier_score",
        "ece",
        "activation_false_positive_rate",
    ):
        if metric in candidate and metric in reference:
            delta[metric] = round(float(candidate[metric]) - float(reference[metric]), 6)
    return delta


def benchmark_score(item: dict[str, Any]) -> float:
    metrics = item.get("aggregate_metrics") or {}
    quality_gate = item.get("quality_gate") or {}
    precision = float(metrics.get("precision_at_top3") or 0.0)
    pr_auc = float(metrics.get("pr_auc") or 0.0)
    ece = float(metrics.get("ece") or 1.0)
    fp_rate = float(metrics.get("activation_false_positive_rate") or 1.0)
    score = (
        precision * 0.4
        + pr_auc * 0.35
        + max(0.0, 1.0 - min(ece, 1.0)) * 0.15
        + max(0.0, 1.0 - min(fp_rate, 1.0)) * 0.10
    )
    if quality_gate.get("overall_passed"):
        score += 0.1
    return round(score * 100.0, 2)


def portfolio_priority_score(
    *,
    prediction: dict[str, Any],
    benchmark_item: dict[str, Any],
) -> float:
    probability = float(prediction.get("event_probability_calibrated") or 0.0)
    change_pct = float(prediction.get("change_pct") or 0.0)
    benchmark_score_value = float(benchmark_item.get("benchmark_score") or 0.0) / 100.0
    quality_gate = prediction.get("quality_gate") or {}
    activation_policy = str(prediction.get("activation_policy") or "quality_gate")
    business_gate = prediction.get("business_gate") or benchmark_item.get("business_gate") or {}
    if activation_policy == "watch_only":
        readiness_multiplier = 0.78
    elif not business_gate.get("validated_for_budget_activation"):
        readiness_multiplier = 0.84 if quality_gate.get("overall_passed") else 0.68
    else:
        readiness_multiplier = 1.0 if quality_gate.get("overall_passed") else 0.72
    momentum_multiplier = 1.0 + min(max(change_pct, 0.0), 80.0) / 200.0
    return round(probability * max(benchmark_score_value, 0.05) * readiness_multiplier * momentum_multiplier * 100.0, 2)


def portfolio_action(
    *,
    prediction: dict[str, Any],
    benchmark_item: dict[str, Any],
) -> tuple[str, str]:
    probability = float(prediction.get("event_probability_calibrated") or 0.0)
    change_pct = float(prediction.get("change_pct") or 0.0)
    threshold = float(prediction.get("action_threshold") or 0.6)
    quality_gate = prediction.get("quality_gate") or {}
    activation_policy = str(prediction.get("activation_policy") or "quality_gate")
    business_gate = prediction.get("business_gate") or benchmark_item.get("business_gate") or {}

    if activation_policy == "watch_only":
        if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
            return "prioritize", "medium"
        return "watch", "low"

    if not business_gate.get("validated_for_budget_activation"):
        if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
            return "prioritize", "medium"
        return "watch", "low"
    if quality_gate.get("overall_passed") and probability >= threshold and change_pct >= 20:
        return "activate", "high"
    if quality_gate.get("overall_passed") and probability >= threshold:
        return "prepare", "medium"
    if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
        return "prioritize", "medium"
    return "watch", "low"


def region_rollup(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in opportunities:
        grouped.setdefault(item["bundesland"], []).append(item)

    rollup: list[dict[str, Any]] = []
    for bundesland, items in grouped.items():
        ranked_items = sorted(
            items,
            key=lambda item: float(item.get("portfolio_priority_score") or 0.0),
            reverse=True,
        )
        leader = ranked_items[0]
        rollup.append(
            {
                "bundesland": bundesland,
                "bundesland_name": leader["bundesland_name"],
                "leading_virus": leader["virus_typ"],
                "leading_probability": leader["event_probability_calibrated"],
                "leading_priority_score": leader["portfolio_priority_score"],
                "top_signals": [
                    {
                        "virus_typ": item["virus_typ"],
                        "portfolio_action": item["portfolio_action"],
                        "portfolio_priority_score": item["portfolio_priority_score"],
                        "event_probability_calibrated": item["event_probability_calibrated"],
                    }
                    for item in ranked_items[:3]
                ],
            }
        )

    rollup.sort(
        key=lambda item: float(item.get("leading_priority_score") or 0.0),
        reverse=True,
    )
    return rollup
