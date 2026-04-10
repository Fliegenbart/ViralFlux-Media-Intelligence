from __future__ import annotations

from typing import Any

from sqlalchemy import func

from app.models.database import WastewaterAggregated
from app.services.media.v2 import lineage


def _decision_freshness_state(service, source_status: dict[str, Any]) -> str:
    items = source_status.get("items") or []
    live_core = {
        item.get("source_key")
        for item in items
        if item.get("is_live") and item.get("source_key") in lineage.CORE_SIGNAL_KEYS
    }
    if live_core == lineage.CORE_SIGNAL_KEYS:
        return "fresh"
    if live_core:
        return "degraded"
    return "stale"


def _build_why_now(
    service,
    *,
    top_card: dict[str, Any] | None,
    top_regions: list[dict[str, Any]],
    cockpit: dict[str, Any],
    decision_state: str,
    signal_summary: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if decision_state != "GO":
        reasons.append("Die epidemiologischen Signale sind relevant, aber die Freigabe bleibt vorerst im Beobachtungsmodus.")
    if top_regions:
        reasons.append(
            f"{top_regions[0].get('name')} fuehrt die regionalen Signale mit {round(float(top_regions[0].get('signal_score') or top_regions[0].get('peix_score') or top_regions[0].get('impact_probability') or 0))}/100 an."
        )
    if top_card:
        if decision_state == "GO" and top_card.get("decision_brief", {}).get("summary_sentence"):
            reasons.append(str(top_card["decision_brief"]["summary_sentence"]))
        else:
            title = top_card.get("display_title") or top_card.get("recommended_product") or "Der stärkste Kampagnenvorschlag"
            reasons.append(f"{title} ist der nächste priorisierte Vorschlag für Prüfung und Freigabe.")
    if signal_summary.get("decision_mode_reason"):
        reasons.append(str(signal_summary["decision_mode_reason"]))
    else:
        top_drivers = (cockpit.get("peix_epi_score") or {}).get("top_drivers") or []
        if top_drivers:
            driver_labels = ", ".join(driver.get("label") for driver in top_drivers[:2] if driver.get("label"))
            reasons.append(f"Treiber dieser Woche: {driver_labels}.")
    while len(reasons) < 3:
        reasons.append("AMELAG, SurvStat und Vorhersage werden gemeinsam für die Wochenentscheidung gewichtet.")
    return reasons[:3]


def _known_limits(
    service,
    cockpit: dict[str, Any],
    virus_typ: str,
    *,
    truth_coverage: dict[str, Any] | None = None,
    truth_validation_legacy: dict[str, Any] | None = None,
) -> list[str]:
    limits: list[str] = []
    truth = truth_coverage or service.get_truth_coverage()
    if truth.get("coverage_weeks", 0) < 26:
        limits.append("Kundennahe Daten decken noch keine 26 Wochen ab.")
    if truth.get("truth_freshness_state") == "stale":
        limits.append("Der letzte Import der Kundendaten liegt zu weit hinter der aktuellen epidemiologischen Woche.")
    if not truth.get("conversion_fields_present"):
        limits.append("In den Kundendaten fehlt noch mindestens eine belastbare Wirkungszahl wie Verkäufe, Bestellungen oder Umsatz.")
    if truth_validation_legacy and truth.get("coverage_weeks", 0) == 0:
        limits.append("Der sichtbare frühere Kundenlauf ist nur ein explorativer Hinweis und noch kein aktiver Bereich für Kundendaten.")
    if not (cockpit.get("backtest_summary", {}).get("latest_market") or {}).get("quality_gate", {}).get("overall_passed"):
        limits.append("Der Marktvergleich steht aktuell auf Beobachten.")
    series_points = (
        service.db.query(func.count(WastewaterAggregated.id))
        .filter(WastewaterAggregated.virus_typ == virus_typ)
        .scalar()
    ) or 0
    if series_points < 120:
        limits.append("Die virale Kernreihe ist noch relativ kurz für robuste Saisonabdeckung.")
    return limits
