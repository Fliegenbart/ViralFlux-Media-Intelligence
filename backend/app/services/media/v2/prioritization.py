from __future__ import annotations

from typing import Any


def _forecast_direction(service, region: dict[str, Any]) -> str:
    if region.get("tooltip", {}).get("forecast_trend"):
        return str(region["tooltip"]["forecast_trend"])
    change = float(region.get("change_pct") or 0.0)
    if change >= 10:
        return "aufwärts"
    if change <= -10:
        return "abwärts"
    return "seitwärts"


def _priority_explanation(
    service,
    *,
    region: dict[str, Any],
    suggestion: dict[str, Any],
    forecast_direction: str,
    severity_score: int,
    momentum_score: int,
    actionability_score: int,
    decision_mode: str,
) -> str:
    trend = str(region.get("trend") or "stabil")
    name = str(region.get("name") or "Die Region")
    if decision_mode == "supply_window":
        return (
            f"{name} bleibt im Fokus, weil Versorgungssignal und Kontext ein Aktivierungsfenster öffnen. "
            "Das ist keine reine Welleneskalation, sondern eine defensive Versorgungschance."
        )
    if momentum_score < 40 and severity_score >= 70:
        return (
            f"{name} beschleunigt aktuell nicht, bleibt aber wegen hohem Ausgangsniveau und hoher Umsetzbarkeit "
            "für Prüfung und Vorbereitung priorisiert."
        )
    if momentum_score >= 60 and forecast_direction == "aufwärts":
        return (
            f"{name} zeigt ein frühes Signal: steigende Dynamik, aufwärts gerichtete Vorhersage und hohe Umsetzbarkeit."
        )
    if trend == "fallend" and actionability_score >= 65:
        return (
            f"{name} fällt kurzfristig, bleibt aber für defensive Planung relevant: Niveau und Umsetzbarkeit sind noch hoch."
        )
    if suggestion.get("reason"):
        return str(suggestion["reason"])
    return f"{name} wird aus epidemiologischer Lage, Vorhersage und Umsetzungschance priorisiert."


def _severity_score(service, region: dict[str, Any]) -> int:
    impact = float(region.get("signal_score") or region.get("impact_probability") or region.get("peix_score") or 0.0)
    intensity = float(region.get("intensity") or 0.0) * 100.0
    return int(round(max(impact, intensity)))


def _momentum_score(
    service,
    *,
    region: dict[str, Any],
    forecast_direction: str,
) -> int:
    change = max(-40.0, min(40.0, float(region.get("change_pct") or 0.0)))
    score = 50.0 + (change * 0.7)
    trend = str(region.get("trend") or "").lower()
    if trend == "steigend":
        score += 6.0
    elif trend == "fallend":
        score -= 6.0

    if forecast_direction == "aufwärts":
        score += 18.0
    elif forecast_direction == "abwärts":
        score -= 18.0

    return int(round(max(0.0, min(100.0, score))))


def _actionability_score(
    service,
    *,
    region: dict[str, Any],
    suggestion: dict[str, Any],
    severity_score: int,
    momentum_score: int,
) -> int:
    recommendation_ref = region.get("recommendation_ref") or {}
    urgency_score = float(recommendation_ref.get("urgency_score") or 0.0)
    urgency_normalized = min(max(urgency_score / 2.0, 0.0), 100.0)
    package_bonus = 10.0 if recommendation_ref.get("card_id") or suggestion.get("budget_shift_pct") else 0.0
    actionability = (
        severity_score * 0.50
        + urgency_normalized * 0.25
        + max(momentum_score, 25) * 0.15
        + package_bonus
    )
    return int(round(max(0.0, min(100.0, actionability))))


def _region_decision_mode(service, peix_region: dict[str, Any]) -> dict[str, str]:
    contributions = peix_region.get("layer_contributions") or {}
    epidemic_total = float(contributions.get("Bio") or 0.0) + float(contributions.get("Forecast") or 0.0)
    supply_total = float(contributions.get("Shortage") or 0.0)
    context_total = sum(float(contributions.get(key) or 0.0) for key in ("Weather", "Search", "Baseline"))
    return service._decision_mode_from_contributions(
        epidemic_total=epidemic_total,
        supply_total=supply_total,
        context_total=context_total,
    )


def _region_source_trace(service, peix_region: dict[str, Any]) -> list[str]:
    trace = ["AMELAG", "SurvStat", "Vorhersage", "ARE"]
    contributions = peix_region.get("layer_contributions") or {}
    if float(contributions.get("Shortage") or 0.0) > 0:
        trace.append("BfArM")
    if float(contributions.get("Weather") or 0.0) > 0:
        trace.append("Wetter")
    return trace
