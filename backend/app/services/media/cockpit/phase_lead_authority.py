"""Shared Phase-Lead authority helpers for cockpit surfaces.

Phase-Lead uses the cached manual MAP artifacts and the aggregate respiratory
pressure score. It is allowed to decide regional priority. It is not allowed to
grant media-budget permission without the GELO outcome layer.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Mapping

from app.services.media.cockpit.constants import BUNDESLAND_NAMES
from app.services.research.phase_lead.aggregate import (
    PHASE_LEAD_AGGREGATE_VIRUSES,
    build_phase_lead_aggregate_snapshot,
)
from app.services.research.phase_lead.artifacts import load_cached_phase_lead_map_snapshot

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def load_phase_lead_authority_snapshot(
    *,
    issue_date: date | datetime | str | None = None,
    window_days: int = 70,
    n_samples: int = 80,
) -> dict[str, Any] | None:
    """Load the cached Phase-Lead aggregate without triggering heavy compute."""

    snapshots: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for virus_typ in PHASE_LEAD_AGGREGATE_VIRUSES:
        cached = load_cached_phase_lead_map_snapshot(
            virus_typ=virus_typ,
            issue_date=issue_date,
            window_days=window_days,
            region_codes=None,
            n_samples=n_samples,
        )
        if cached is not None:
            snapshots[virus_typ] = cached
        else:
            warnings.append(f"{virus_typ}: no cached Phase-Lead MAP artifact available.")

    if not snapshots:
        return None

    try:
        return build_phase_lead_aggregate_snapshot(
            snapshots,
            warnings=warnings,
            fallback_viruses=[],
        )
    except Exception:  # noqa: BLE001
        logger.exception("phase-lead authority aggregate build failed")
        return None


def phase_lead_regions_by_code(snapshot: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not snapshot:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for region in snapshot.get("regions") or []:
        code = str((region or {}).get("region_code") or "").upper()
        if code:
            out[code] = dict(region)
    return out


def phase_lead_rank_by_code(snapshot: Mapping[str, Any] | None) -> dict[str, int]:
    if not snapshot:
        return {}
    return {
        str((region or {}).get("region_code") or "").upper(): index + 1
        for index, region in enumerate(snapshot.get("regions") or [])
        if str((region or {}).get("region_code") or "").strip()
    }


def phase_lead_driver_labels(snapshot: Mapping[str, Any] | None, region_code: str, *, limit: int = 2) -> list[str]:
    if not snapshot:
        return []
    drivers = (
        ((snapshot.get("aggregate") or {}).get("drivers_by_region") or {})
        .get(str(region_code or "").upper())
        or []
    )
    labels: list[str] = []
    for driver in drivers[:limit]:
        label = str((driver or {}).get("virus_typ") or "").strip()
        if label:
            labels.append(label)
    return labels


def phase_lead_decision_label(region: Mapping[str, Any] | None) -> str:
    if not region:
        return "Watch"
    p_up = _safe_float(region.get("p_up_h7"))
    p_surge = _safe_float(region.get("p_surge_h7"))
    if p_surge >= 0.35 or p_up >= 0.75:
        return "Prepare"
    return "Watch"


def apply_phase_lead_to_cockpit_regions(
    regions: list[dict[str, Any]],
    phase_lead_snapshot: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Overlay Phase-Lead regional truth onto existing cockpit region rows."""

    by_code = phase_lead_regions_by_code(phase_lead_snapshot)
    ranks = phase_lead_rank_by_code(phase_lead_snapshot)
    if not by_code:
        return regions

    seen_codes: set[str] = set()
    out: list[dict[str, Any]] = []
    for region in regions:
        code = str(region.get("code") or "").upper()
        seen_codes.add(code)
        phase_region = by_code.get(code)
        if not phase_region:
            out.append(region)
            continue

        drivers = phase_lead_driver_labels(phase_lead_snapshot, code)
        old_delta = region.get("delta7d")
        merged = dict(region)
        if isinstance(old_delta, (int, float)):
            merged["legacyForecastDelta7d"] = old_delta
        merged.update(
            {
                "name": phase_region.get("region") or region.get("name") or BUNDESLAND_NAMES.get(code, code),
                "delta7d": _safe_float(phase_region.get("current_growth")),
                "pRising": _safe_float(phase_region.get("p_up_h7")),
                "decisionLabel": phase_lead_decision_label(phase_region),
                "phaseLeadRank": ranks.get(code),
                "phaseLeadScore": round(_safe_float(phase_region.get("gegb")), 4),
                "phaseLeadPUpH7": round(_safe_float(phase_region.get("p_up_h7")), 4),
                "phaseLeadPSurgeH7": round(_safe_float(phase_region.get("p_surge_h7")), 4),
                "phaseLeadGrowth": round(_safe_float(phase_region.get("current_growth")), 4),
                "phaseLeadDrivers": drivers,
                "phaseLeadSource": "plgrf_aggregate_v0",
                "drivers": [
                    f"Phase-Lead Gesamt: {' + '.join(drivers) if drivers else 'Atemwegsdruck'}",
                    *(region.get("drivers") or [])[:2],
                ],
            }
        )
        out.append(merged)

    for code, phase_region in by_code.items():
        if code in seen_codes:
            continue
        drivers = phase_lead_driver_labels(phase_lead_snapshot, code)
        out.append(
            {
                "code": code,
                "name": phase_region.get("region") or BUNDESLAND_NAMES.get(code, code),
                "delta7d": _safe_float(phase_region.get("current_growth")),
                "pRising": _safe_float(phase_region.get("p_up_h7")),
                "forecast": None,
                "drivers": [f"Phase-Lead Gesamt: {' + '.join(drivers) if drivers else 'Atemwegsdruck'}"],
                "currentSpendEur": None,
                "recommendedShiftEur": None,
                "decisionLabel": phase_lead_decision_label(phase_region),
                "phaseLeadRank": ranks.get(code),
                "phaseLeadScore": round(_safe_float(phase_region.get("gegb")), 4),
                "phaseLeadPUpH7": round(_safe_float(phase_region.get("p_up_h7")), 4),
                "phaseLeadPSurgeH7": round(_safe_float(phase_region.get("p_surge_h7")), 4),
                "phaseLeadGrowth": round(_safe_float(phase_region.get("current_growth")), 4),
                "phaseLeadDrivers": drivers,
                "phaseLeadSource": "plgrf_aggregate_v0",
            }
        )

    return sorted(
        out,
        key=lambda region: (
            region.get("phaseLeadRank") is None,
            region.get("phaseLeadRank") or 999,
            str(region.get("code") or ""),
        ),
    )


def build_phase_lead_primary_recommendation(
    phase_lead_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    regions = list((phase_lead_snapshot or {}).get("regions") or [])
    if not regions:
        return None

    top = dict(regions[0])
    bottom = dict(regions[-1]) if len(regions) > 1 else top
    top_code = str(top.get("region_code") or "").upper()
    bottom_code = str(bottom.get("region_code") or "").upper()
    top_name = str(top.get("region") or BUNDESLAND_NAMES.get(top_code, top_code))
    bottom_name = str(bottom.get("region") or BUNDESLAND_NAMES.get(bottom_code, bottom_code))
    drivers = phase_lead_driver_labels(phase_lead_snapshot, top_code)
    score = _safe_float(top.get("gegb"))
    p_up = _safe_float(top.get("p_up_h7"))
    p_surge = _safe_float(top.get("p_surge_h7"))
    growth = _safe_float(top.get("current_growth"))
    driver_text = " + ".join(drivers) if drivers else "mehrere Atemwegsviren"

    return {
        "id": f"phase_lead_aggregate_{top_code}",
        "fromCode": bottom_code if bottom_code != top_code else None,
        "toCode": top_code,
        "fromName": bottom_name if bottom_code != top_code else None,
        "toName": top_name,
        "amountEur": None,
        "signalScore": round(max(0.05, min(0.95, score / 100.0)), 3),
        "confidence": round(max(0.05, min(0.95, score / 100.0)), 3),
        "expectedReachUplift": None,
        "why": (
            f"Phase-Lead Gesamtwert priorisiert {top_name}: Score {score:.1f}, "
            f"p(up) 7 Tage {p_up:.0%}, Surge {p_surge:.0%}, Wachstum {growth:+.2f}. "
            f"Haupttreiber: {driver_text}. Budget bleibt ohne GELO-Salesdaten gesperrt."
        ),
        "primary": True,
        "signalMode": True,
        "phaseLeadMode": True,
        "phaseLeadSource": "plgrf_aggregate_v0",
    }


def build_phase_lead_authority_payload(
    phase_lead_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    regions = list((phase_lead_snapshot or {}).get("regions") or [])
    if not regions:
        return None
    top = dict(regions[0])
    top_code = str(top.get("region_code") or "").upper()
    return {
        "source": "phase_lead_aggregate",
        "version": phase_lead_snapshot.get("version"),
        "asOf": phase_lead_snapshot.get("as_of"),
        "topRegionCode": top_code,
        "topRegionName": top.get("region") or BUNDESLAND_NAMES.get(top_code, top_code),
        "topScore": round(_safe_float(top.get("gegb")), 4),
        "topDrivers": phase_lead_driver_labels(phase_lead_snapshot, top_code),
        "availableViruses": (phase_lead_snapshot.get("aggregate") or {}).get("available_viruses") or [],
        "fallbackViruses": (phase_lead_snapshot.get("aggregate") or {}).get("fallback_viruses") or [],
        "budgetCanChange": False,
        "note": "Regional priority is aligned to Phase-Lead aggregate; budget remains gated by GELO Sales validation.",
    }
