"""Aggregate phase-lead virus snapshots into one regional product index."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from app.services.ml.regional_panel_utils import BUNDESLAND_NAMES

PHASE_LEAD_AGGREGATE_VERSION = "plgrf_aggregate_v0"
PHASE_LEAD_AGGREGATE_VIRUSES = ("Influenza A", "Influenza B", "RSV A", "SARS-CoV-2")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _json_float(value: float) -> float:
    return float(round(value, 6)) if math.isfinite(value) else 0.0


def _model_score(snapshot: Mapping[str, Any]) -> float:
    summary = snapshot.get("summary") or {}
    fit_mode = summary.get("fit_mode")
    if fit_mode == "map_optimization" and bool(summary.get("converged")):
        return 1.0
    if fit_mode == "map_optimization":
        return 0.7
    return 0.4


def _warning_factor(snapshot: Mapping[str, Any]) -> float:
    warning_count = _safe_int((snapshot.get("summary") or {}).get("warning_count"))
    return max(0.4, 1.0 - 0.15 * warning_count)


def _active_source_count(snapshot: Mapping[str, Any]) -> int:
    sources = snapshot.get("sources") or {}
    return sum(1 for status in sources.values() if _safe_int((status or {}).get("rows")) > 0)


def _latest_source_date(snapshot: Mapping[str, Any]) -> date | None:
    latest: date | None = None
    for status in (snapshot.get("sources") or {}).values():
        event_date = _parse_iso_date((status or {}).get("latest_event_date"))
        if event_date and (latest is None or event_date > latest):
            latest = event_date
    return latest


def _freshness_score(snapshot: Mapping[str, Any]) -> float:
    as_of = _parse_iso_date(snapshot.get("as_of"))
    latest = _latest_source_date(snapshot)
    if not as_of or not latest:
        return 0.25
    age_days = max(0, (as_of - latest).days)
    if age_days <= 10:
        return 1.0
    if age_days <= 21:
        return 0.75
    if age_days <= 35:
        return 0.5
    return 0.25


def _quality_components(snapshot: Mapping[str, Any], max_sqrt_observations: float) -> dict[str, float]:
    summary = snapshot.get("summary") or {}
    observation_count = max(0, _safe_int(summary.get("observation_count")))
    observation_score = (
        math.sqrt(observation_count) / max_sqrt_observations
        if max_sqrt_observations > 0.0
        else 0.0
    )
    coverage_score = min(1.0, _active_source_count(snapshot) / 4.0)
    freshness_score = _freshness_score(snapshot)
    model_score = _model_score(snapshot)
    warning_factor = _warning_factor(snapshot)
    quality = (
        0.35 * observation_score
        + 0.25 * coverage_score
        + 0.25 * freshness_score
        + 0.15 * model_score
    ) * warning_factor
    return {
        "quality": quality,
        "observation_score": observation_score,
        "coverage_score": coverage_score,
        "freshness_score": freshness_score,
        "model_score": model_score,
        "warning_factor": warning_factor,
    }


def _region_signal(region: Mapping[str, Any], max_gegb: float) -> float:
    burden_norm = _safe_float(region.get("gegb")) / max_gegb if max_gegb > 0.0 else 0.0
    burden_norm = min(1.0, max(0.0, burden_norm))
    return 100.0 * (
        0.45 * min(1.0, max(0.0, _safe_float(region.get("p_up_h7"))))
        + 0.35 * min(1.0, max(0.0, _safe_float(region.get("p_surge_h7"))))
        + 0.20 * burden_norm
    )


def _combined_hash(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(str(value).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def build_phase_lead_aggregate_snapshot(
    snapshots_by_virus: Mapping[str, Mapping[str, Any]],
    *,
    warnings: Iterable[str] = (),
    fallback_viruses: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a frontend-compatible Gesamt snapshot from per-virus snapshots."""

    snapshots = {
        virus: snapshot
        for virus, snapshot in snapshots_by_virus.items()
        if snapshot and snapshot.get("regions")
    }
    if not snapshots:
        raise ValueError("No phase-lead snapshots are available for aggregate scoring")

    max_sqrt_observations = max(
        math.sqrt(max(0, _safe_int((snapshot.get("summary") or {}).get("observation_count"))))
        for snapshot in snapshots.values()
    )
    components_by_virus = {
        virus: _quality_components(snapshot, max_sqrt_observations)
        for virus, snapshot in snapshots.items()
    }
    quality_total = sum(item["quality"] for item in components_by_virus.values())
    if quality_total <= 0.0:
        weights = {virus: 1.0 / len(snapshots) for virus in snapshots}
    else:
        weights = {
            virus: components["quality"] / quality_total
            for virus, components in components_by_virus.items()
        }

    region_accumulator: dict[str, dict[str, Any]] = {}
    drivers_by_region: dict[str, list[dict[str, Any]]] = {}

    for virus, snapshot in snapshots.items():
        weight = weights[virus]
        regions = snapshot.get("regions") or []
        max_gegb = max((_safe_float(region.get("gegb")) for region in regions), default=0.0)
        for region in regions:
            region_code = str(region.get("region_code") or "")
            if not region_code:
                continue
            signal = _region_signal(region, max_gegb)
            contribution = weight * signal
            target = region_accumulator.setdefault(
                region_code,
                {
                    "region_code": region_code,
                    "region": region.get("region") or BUNDESLAND_NAMES.get(region_code, region_code),
                    "current_level": 0.0,
                    "current_growth": 0.0,
                    "p_up_h7": 0.0,
                    "p_surge_h7": 0.0,
                    "p_front": 0.0,
                    "eeb": 0.0,
                    "gegb": 0.0,
                    "source_rows": 0,
                },
            )
            target["current_level"] += weight * _safe_float(region.get("current_level"))
            target["current_growth"] += weight * _safe_float(region.get("current_growth"))
            target["p_up_h7"] += weight * _safe_float(region.get("p_up_h7"))
            target["p_surge_h7"] += weight * _safe_float(region.get("p_surge_h7"))
            target["p_front"] += weight * _safe_float(region.get("p_front"))
            target["eeb"] += weight * _safe_float(region.get("eeb"))
            target["gegb"] += contribution
            target["source_rows"] += _safe_int(region.get("source_rows"))
            drivers_by_region.setdefault(region_code, []).append(
                {
                    "virus_typ": virus,
                    "weight": _json_float(weight),
                    "signal": _json_float(signal),
                    "contribution": _json_float(contribution),
                }
            )

    for drivers in drivers_by_region.values():
        drivers.sort(key=lambda item: item["contribution"], reverse=True)

    regions_payload = [
        {
            **region,
            "current_level": _json_float(region["current_level"]),
            "current_growth": _json_float(region["current_growth"]),
            "p_up_h7": _json_float(region["p_up_h7"]),
            "p_surge_h7": _json_float(region["p_surge_h7"]),
            "p_front": _json_float(region["p_front"]),
            "eeb": _json_float(region["eeb"]),
            "gegb": _json_float(region["gegb"]),
        }
        for region in region_accumulator.values()
    ]
    regions_payload.sort(key=lambda item: item["gegb"], reverse=True)

    combined_sources: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots.values():
        for source, status in (snapshot.get("sources") or {}).items():
            target = combined_sources.setdefault(
                source,
                {"rows": 0, "latest_event_date": None, "units": set()},
            )
            target["rows"] += _safe_int((status or {}).get("rows"))
            latest = (status or {}).get("latest_event_date")
            if latest and (target["latest_event_date"] is None or latest > target["latest_event_date"]):
                target["latest_event_date"] = latest
            target["units"].update((status or {}).get("units") or [])

    sources_payload = {
        source: {
            "rows": status["rows"],
            "latest_event_date": status["latest_event_date"],
            "units": sorted(status["units"]),
        }
        for source, status in sorted(combined_sources.items())
    }

    child_warnings = []
    for virus, snapshot in snapshots.items():
        child_warnings.extend(f"{virus}: {warning}" for warning in snapshot.get("warnings") or [])
    warning_payload = list(warnings) + child_warnings

    summaries = [snapshot.get("summary") or {} for snapshot in snapshots.values()]
    window_starts = [str(summary.get("window_start")) for summary in summaries if summary.get("window_start")]
    window_ends = [str(summary.get("window_end")) for summary in summaries if summary.get("window_end")]
    as_of_dates = [str(snapshot.get("as_of")) for snapshot in snapshots.values() if snapshot.get("as_of")]
    all_map = all(summary.get("fit_mode") == "map_optimization" for summary in summaries)
    all_converged = all(bool(summary.get("converged")) for summary in summaries)

    virus_weights = []
    for virus, components in components_by_virus.items():
        virus_weights.append(
            {
                "virus_typ": virus,
                "weight": _json_float(weights[virus]),
                "quality": _json_float(components["quality"]),
                "observation_score": _json_float(components["observation_score"]),
                "coverage_score": _json_float(components["coverage_score"]),
                "freshness_score": _json_float(components["freshness_score"]),
                "model_score": _json_float(components["model_score"]),
                "warning_factor": _json_float(components["warning_factor"]),
            }
        )
    virus_weights.sort(key=lambda item: item["weight"], reverse=True)

    return {
        "module": "phase_lead_graph_renewal_filter",
        "version": PHASE_LEAD_AGGREGATE_VERSION,
        "mode": "research",
        "as_of": max(as_of_dates) if as_of_dates else date.today().isoformat(),
        "virus_typ": "Gesamt",
        "horizons": next(iter(snapshots.values())).get("horizons") or [3, 5, 7, 10, 14],
        "summary": {
            "data_source": "live_database",
            "fit_mode": "map_optimization" if all_map else "fast_initialization",
            "observation_count": sum(_safe_int(summary.get("observation_count")) for summary in summaries),
            "window_start": min(window_starts) if window_starts else "",
            "window_end": max(window_ends) if window_ends else "",
            "converged": all_converged,
            "objective_value": regions_payload[0]["gegb"] if regions_payload else 0.0,
            "data_vintage_hash": _combined_hash(
                summary.get("data_vintage_hash", "") for summary in summaries
            ),
            "config_hash": _combined_hash(summary.get("config_hash", "") for summary in summaries),
            "top_region": regions_payload[0]["region_code"] if regions_payload else None,
            "warning_count": len(warning_payload),
        },
        "sources": sources_payload,
        "regions": regions_payload,
        "rankings": {
            "Gesamt": [
                {"region_id": region["region_code"], "gegb": region["gegb"]}
                for region in regions_payload
            ]
        },
        "warnings": warning_payload,
        "aggregate": {
            "kind": "respiratory_pressure",
            "weighting": "data_quality",
            "available_viruses": list(snapshots.keys()),
            "fallback_viruses": list(fallback_viruses),
            "virus_weights": virus_weights,
            "drivers_by_region": drivers_by_region,
        },
    }
