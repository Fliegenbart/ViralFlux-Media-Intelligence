"""Outcome and KPI helpers for pilot reporting."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from app.services.marketing_engine.opportunity_engine_constants import BUNDESLAND_NAMES

_PRIMARY_METRIC_ORDER = (
    "revenue",
    "orders",
    "sales",
    "search_demand",
    "qualified_visits",
    "campaign_response",
    "clicks",
    "impressions",
)


def build_scope_comparison(
    reporting_service,
    *,
    brand: str,
    card: dict[str, Any],
    scope: dict[str, str],
    activation_window: dict[str, str | None],
    signal_context: dict[str, Any],
    lead_time_days: int | None,
    current_status: str,
) -> dict[str, Any]:
    after_start = _parse_datetime(activation_window.get("start"))
    after_end = _parse_datetime(activation_window.get("end"))
    before_window: dict[str, str | None] = {"start": None, "end": None}
    before_summary = reporting_service._empty_metric_summary()
    after_summary = reporting_service._empty_metric_summary()

    if after_start and after_end and after_end >= after_start:
        duration_days = max((after_end.date() - after_start.date()).days + 1, 1)
        before_end_dt = after_start - timedelta(days=1)
        before_start_dt = before_end_dt - timedelta(days=duration_days - 1)
        before_window = {
            "start": before_start_dt.isoformat(),
            "end": before_end_dt.isoformat(),
        }
        before_summary = reporting_service._metric_summary(
            brand=brand,
            product=str(card.get("recommended_product") or card.get("product") or "").strip(),
            region_code=scope["region_code"],
            window_start=before_start_dt,
            window_end=before_end_dt,
        )
        after_summary = reporting_service._metric_summary(
            brand=brand,
            product=str(card.get("recommended_product") or card.get("product") or "").strip(),
            region_code=scope["region_code"],
            window_start=after_start,
            window_end=after_end,
        )

    primary_metric = reporting_service._primary_metric(before_summary["metrics"], after_summary["metrics"])
    before_value = float(before_summary["metrics"].get(primary_metric) or 0.0) if primary_metric else None
    after_value = float(after_summary["metrics"].get(primary_metric) or 0.0) if primary_metric else None
    delta_absolute = None
    delta_pct = None
    if primary_metric is not None and before_value is not None and after_value is not None:
        delta_absolute = after_value - before_value
        if before_value > 0:
            delta_pct = ((after_value - before_value) / before_value) * 100.0
        elif after_value > 0:
            delta_pct = 100.0
        else:
            delta_pct = 0.0

    truth_assessment = reporting_service.truth_layer_service.assess(
        brand=brand,
        region_code=None if scope["region_code"] == "DE" else scope["region_code"],
        product=str(card.get("recommended_product") or card.get("product") or "").strip(),
        window_start=after_start,
        window_end=after_end,
        signal_context=signal_context,
    )
    agreement = truth_assessment.get("signal_outcome_agreement") or {}
    evidence_status = str(truth_assessment.get("evidence_status") or "no_truth")
    outcome_support_status = reporting_service._outcome_support_status(
        delta_pct=delta_pct,
        agreement_status=str(agreement.get("status") or ""),
        evidence_status=evidence_status,
        primary_metric=primary_metric,
    )

    return {
        "comparison_id": f"{card.get('id')}:{scope['region_code']}",
        "opportunity_id": card.get("id"),
        "region_code": scope["region_code"],
        "region_name": scope["region_name"],
        "product": card.get("recommended_product") or card.get("product"),
        "current_status": current_status,
        "is_activated": current_status in {"APPROVED", "ACTIVATED", "EXPIRED"},
        "priority_score": _round_or_none(card.get("priority_score"), 2),
        "lead_time_days": lead_time_days,
        "before_window": before_window,
        "after_window": activation_window,
        "before": before_summary,
        "after": after_summary,
        "primary_metric": primary_metric,
        "before_value": _round_or_none(before_value, 2),
        "after_value": _round_or_none(after_value, 2),
        "delta_absolute": _round_or_none(delta_absolute, 2),
        "delta_pct": _round_or_none(delta_pct, 2),
        "outcome_support_status": outcome_support_status,
        "truth_assessment": {
            "evidence_status": evidence_status,
            "evidence_confidence": truth_assessment.get("evidence_confidence"),
            "outcome_readiness": truth_assessment.get("outcome_readiness") or {},
            "signal_outcome_agreement": agreement,
            "commercial_gate": truth_assessment.get("commercial_gate") or {},
        },
    }


def metric_summary(
    reporting_service,
    *,
    brand: str,
    product: str,
    region_code: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    observations, source_mode = reporting_service.truth_layer_service._load_scope_observations(
        brand=brand,
        region_code=None if region_code == "DE" else region_code,
        product=product,
        window_start=window_start,
        window_end=window_end,
    )
    observations = [
        observation
        for observation in observations
        if reporting_service._observation_within_window(
            observation=observation,
            window_start=window_start,
            window_end=window_end,
        )
    ]
    if not observations:
        source_mode = "empty"
    metrics: Counter[str] = Counter()
    weeks: set[str] = set()
    for observation in observations:
        metrics[str(observation.get("metric_name") or "")] += float(observation.get("metric_value") or 0.0)
        if observation.get("window_start"):
            weeks.add(observation["window_start"].date().isoformat())
    return {
        "source_mode": source_mode,
        "observation_count": len(observations),
        "coverage_weeks": len(weeks),
        "metrics": {
            key: round(float(value), 2)
            for key, value in sorted(metrics.items())
        },
    }


def observation_within_window(
    *,
    observation: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
) -> bool:
    observation_start = _parse_datetime(observation.get("window_start"))
    observation_end = _parse_datetime(observation.get("window_end"))
    if observation_start is None:
        return False
    if observation_end is None:
        observation_end = observation_start
    return observation_start >= window_start and observation_end <= window_end


def empty_metric_summary() -> dict[str, Any]:
    return {
        "source_mode": "empty",
        "observation_count": 0,
        "coverage_weeks": 0,
        "metrics": {},
    }


def primary_metric(before_metrics: dict[str, Any], after_metrics: dict[str, Any]) -> str | None:
    combined = {**before_metrics, **after_metrics}
    for metric_name in _PRIMARY_METRIC_ORDER:
        if float(combined.get(metric_name) or 0.0) > 0.0:
            return metric_name
    return None


def outcome_support_status(
    *,
    delta_pct: float | None,
    agreement_status: str,
    evidence_status: str,
    primary_metric: str | None,
) -> str:
    normalized_agreement = str(agreement_status or "").strip().lower()
    if primary_metric is None and evidence_status == "no_truth":
        return "insufficient_evidence"
    if primary_metric is None:
        return "mixed"
    if delta_pct is None:
        return "insufficient_evidence"
    if delta_pct > 0 and normalized_agreement in {"moderate", "strong"}:
        return "supportive"
    if delta_pct > 0:
        return "mixed"
    return "not_supportive"


def region_bucket() -> dict[str, Any]:
    return {
        "region_name": None,
        "recommendations": 0,
        "activations": 0,
        "priority_scores": [],
        "lead_times": [],
        "products": Counter(),
        "supportive": 0,
        "assessed": 0,
        "agreements": 0,
        "agreement_assessed": 0,
        "delta_pcts": [],
        "evidence_status_counts": Counter(),
    }


def accumulate_region_bucket(
    bucket: dict[str, Any],
    *,
    card: dict[str, Any],
    comparison: dict[str, Any],
    scope: dict[str, str],
) -> None:
    bucket["region_name"] = scope["region_name"]
    bucket["recommendations"] += 1
    if comparison["is_activated"]:
        bucket["activations"] += 1
    priority_score = comparison.get("priority_score")
    if priority_score is not None:
        bucket["priority_scores"].append(float(priority_score))
    if comparison.get("lead_time_days") is not None:
        bucket["lead_times"].append(int(comparison["lead_time_days"]))
    product = str(card.get("recommended_product") or card.get("product") or "").strip()
    if product:
        bucket["products"][product] += 1
    evidence_status = str((comparison.get("truth_assessment") or {}).get("evidence_status") or "")
    if evidence_status:
        bucket["evidence_status_counts"][evidence_status] += 1
    agreement_status = str((((comparison.get("truth_assessment") or {}).get("signal_outcome_agreement") or {}).get("status")) or "")
    if agreement_status:
        bucket["agreement_assessed"] += 1
        if agreement_status in {"moderate", "strong"}:
            bucket["agreements"] += 1
    if comparison["outcome_support_status"] != "insufficient_evidence":
        bucket["assessed"] += 1
        if comparison["outcome_support_status"] == "supportive":
            bucket["supportive"] += 1
    if comparison.get("delta_pct") is not None:
        bucket["delta_pcts"].append(float(comparison["delta_pct"]))


def region_evidence_view(buckets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for region_code, bucket in buckets.items():
        avg_priority = (
            round(sum(bucket["priority_scores"]) / len(bucket["priority_scores"]), 2)
            if bucket["priority_scores"] else None
        )
        avg_lead = (
            round(sum(bucket["lead_times"]) / len(bucket["lead_times"]), 1)
            if bucket["lead_times"] else None
        )
        avg_delta = (
            round(sum(bucket["delta_pcts"]) / len(bucket["delta_pcts"]), 2)
            if bucket["delta_pcts"] else None
        )
        hit_rate = (
            round(bucket["supportive"] / bucket["assessed"], 4)
            if bucket["assessed"] else None
        )
        agreement_rate = (
            round(bucket["agreements"] / bucket["agreement_assessed"], 4)
            if bucket["agreement_assessed"] else None
        )
        dominant_evidence_status = None
        if bucket["evidence_status_counts"]:
            dominant_evidence_status = bucket["evidence_status_counts"].most_common(1)[0][0]
        items.append(
            {
                "region_code": region_code,
                "region_name": bucket["region_name"] or BUNDESLAND_NAMES.get(region_code, region_code),
                "recommendations": bucket["recommendations"],
                "activations": bucket["activations"],
                "avg_priority_score": avg_priority,
                "avg_lead_time_days": avg_lead,
                "avg_after_delta_pct": avg_delta,
                "hit_rate": hit_rate,
                "agreement_with_outcome_signals": agreement_rate,
                "dominant_evidence_status": dominant_evidence_status,
                "top_products": [name for name, _count in bucket["products"].most_common(3)],
                "evidence_status_counts": dict(bucket["evidence_status_counts"]),
            }
        )
    items.sort(
        key=lambda item: (
            float(item.get("hit_rate") or 0.0),
            float(item.get("avg_priority_score") or 0.0),
            item.get("recommendations") or 0,
        ),
        reverse=True,
    )
    return items


def pilot_kpi_summary(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    activated = [item for item in comparisons if item["is_activated"]]
    assessed_activated = [item for item in activated if item["outcome_support_status"] != "insufficient_evidence"]
    supportive_activated = [item for item in assessed_activated if item["outcome_support_status"] == "supportive"]
    lead_times = [item["lead_time_days"] for item in activated if item.get("lead_time_days") is not None]

    assessed_with_priority = [
        item for item in comparisons
        if item["outcome_support_status"] != "insufficient_evidence" and item.get("priority_score") is not None
    ]
    threshold_priority = (
        median([float(item["priority_score"]) for item in assessed_with_priority])
        if assessed_with_priority else None
    )
    high_priority_items = [
        item for item in assessed_with_priority
        if threshold_priority is not None and float(item["priority_score"]) >= float(threshold_priority)
    ]
    correct_high_priority = [
        item for item in high_priority_items
        if item["outcome_support_status"] in {"supportive", "mixed"}
    ]

    agreement_assessed = [
        item for item in comparisons
        if str((((item.get("truth_assessment") or {}).get("signal_outcome_agreement") or {}).get("status")) or "")
        not in {"", "no_signal"}
    ]
    agreement_positive = [
        item for item in agreement_assessed
        if str((((item.get("truth_assessment") or {}).get("signal_outcome_agreement") or {}).get("status")) or "") in {"moderate", "strong"}
    ]

    return {
        "hit_rate": {
            "value": _round_or_none(len(supportive_activated) / len(assessed_activated), 4) if assessed_activated else None,
            "supportive": len(supportive_activated),
            "assessed": len(assessed_activated),
            "definition": "Share of activated scopes with positive primary KPI delta and at least moderate outcome agreement.",
        },
        "early_warning_lead_time_days": {
            "average": _round_or_none(sum(lead_times) / len(lead_times), 2) if lead_times else None,
            "median": _round_or_none(float(median(lead_times)), 2) if lead_times else None,
            "assessed": len(lead_times),
            "definition": "Days between recommendation creation and activation window start.",
        },
        "share_of_correct_regional_prioritizations": {
            "value": _round_or_none(len(correct_high_priority) / len(high_priority_items), 4) if high_priority_items else None,
            "supportive_or_directional": len(correct_high_priority),
            "assessed_high_priority": len(high_priority_items),
            "priority_threshold": _round_or_none(float(threshold_priority), 2) if threshold_priority is not None else None,
            "definition": "Share of above-median priority scopes with supportive or directional positive after-window evidence.",
        },
        "agreement_with_outcome_signals": {
            "value": _round_or_none(len(agreement_positive) / len(agreement_assessed), 4) if agreement_assessed else None,
            "agreeing_scopes": len(agreement_positive),
            "assessed": len(agreement_assessed),
            "definition": "Share of assessed scopes with moderate or strong signal/outcome agreement.",
        },
    }


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)
