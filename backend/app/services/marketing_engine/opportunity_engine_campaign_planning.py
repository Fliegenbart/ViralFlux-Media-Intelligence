"""Campaign planning primitives for the marketing opportunity engine."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.time import utc_now


def build_channel_mix(channels: list[str], opportunity_type: str, urgency: float) -> dict[str, float]:
    """Create a simple channel mix based on type and urgency."""
    normalized = [c.strip().lower() for c in channels if c and c.strip()]
    if not normalized:
        normalized = ["programmatic", "social", "search", "ctv"]

    if len(normalized) == 1:
        return {normalized[0]: 100}

    base = {c: round(100 / len(normalized), 1) for c in normalized}

    if opportunity_type in {"RESOURCE_SCARCITY", "PREDICTIVE_SALES_SPIKE"} and "search" in base:
        base["search"] = min(55.0, base["search"] + 15.0)
    if urgency >= 75 and "programmatic" in base:
        base["programmatic"] = min(60.0, base["programmatic"] + 10.0)
    if opportunity_type in {"SEASONAL_DEFICIENCY", "WEATHER_FORECAST"} and "social" in base:
        base["social"] = min(50.0, base["social"] + 10.0)

    total = sum(base.values()) or 1.0
    normalized_mix = {k: round(v / total * 100.0, 1) for k, v in base.items()}
    diff = round(100.0 - sum(normalized_mix.values()), 1)
    first_key = next(iter(normalized_mix))
    normalized_mix[first_key] = round(normalized_mix[first_key] + diff, 1)
    return normalized_mix


def derive_campaign_name(brand: str, product: str, region: str, opportunity_type: str) -> str:
    type_label = opportunity_type.replace("_", " ").title()
    return f"{brand} | {product} | {region} | {type_label}"


def derive_activation_window(urgency: float) -> dict[str, Any]:
    start = utc_now()
    days = 14 if urgency >= 70 else 10 if urgency >= 50 else 7
    end = start + timedelta(days=days)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "flight_days": days,
    }


def build_channel_plan(
    channel_mix: dict[str, float],
    budget_shift_value: float,
    campaign_goal: str,
) -> list[dict[str, Any]]:
    role_map = {
        "programmatic": "reach",
        "social": "consideration",
        "search": "intent",
        "ctv": "awareness",
    }
    format_map = {
        "programmatic": ["Display", "Video"],
        "social": ["Feed", "Story", "Reel"],
        "search": ["Brand", "Symptom", "Wettbewerb"],
        "ctv": ["Pre-Roll", "Connected TV"],
    }
    kpi_map = {
        "programmatic": "Reach",
        "social": "CTR",
        "search": "Qualified Clicks",
        "ctv": "Completed Views",
    }

    plan: list[dict[str, Any]] = []
    for channel, share in channel_mix.items():
        plan.append(
            {
                "channel": channel,
                "role": role_map.get(channel, "reach"),
                "share_pct": round(float(share), 1),
                "budget_eur": round(budget_shift_value * (float(share) / 100.0), 2),
                "formats": format_map.get(channel, ["Standard"]),
                "message_angle": f"{campaign_goal}: regionaler Trigger + Verfügbarkeit",
                "kpi_primary": kpi_map.get(channel, "CTR"),
                "kpi_secondary": ["CPM", "Frequency"],
            }
        )

    plan.sort(key=lambda item: item["share_pct"], reverse=True)
    return plan


def build_measurement_plan(campaign_goal: str, channel_plan: list[dict[str, Any]]) -> dict[str, Any]:
    primary = "Reach in Trigger-Region" if "awareness" in campaign_goal.lower() else "Qualified Visits"
    if channel_plan:
        primary = channel_plan[0].get("kpi_primary") or primary

    return {
        "primary_kpi": primary,
        "secondary_kpis": ["CTR", "CPM", "Landing Conversion"],
        "reporting_cadence": "Daily",
        "success_criteria": "Steigende KPI in aktivierten Trigger-Regionen bei stabiler Effizienz",
    }


def derive_activation_window_from_days(days: int) -> dict[str, Any]:
    start = utc_now()
    duration = max(1, min(28, int(days or 10)))
    end = start + timedelta(days=duration)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "flight_days": duration,
    }
