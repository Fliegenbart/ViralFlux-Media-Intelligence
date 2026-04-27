"""Combine h5 curve-rise and h7 regional signals without averaging horizons."""

from __future__ import annotations

from typing import Any

from app.services.ml.regional_panel_utils import ALL_BUNDESLAENDER, BUNDESLAND_NAMES


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _stage(value: dict[str, Any]) -> str:
    decision = value.get("decision") if isinstance(value, dict) else {}
    if isinstance(decision, dict):
        stage = str(decision.get("stage") or "").strip().lower()
        if stage:
            return stage
    return str(value.get("decision_label") or "").strip().lower()


def classify_horizon_alignment(
    h5_region: dict[str, Any] | None,
    h7_region: dict[str, Any] | None,
    *,
    min_h5_change_pct: float = 10.0,
) -> dict[str, Any]:
    """Return one conservative interpretation for h5+h7.

    h5 and h7 are different forecast questions. This function deliberately
    avoids averaging their probabilities. h5 is the short-term curve check;
    h7 is a directional confirmation and freshness gate.
    """

    h5_region = dict(h5_region or {})
    h7_region = dict(h7_region or {})
    h5_change = _safe_float(h5_region.get("change_pct"))
    h7_change = _safe_float(h7_region.get("change_pct"))
    h5_rise = bool(h5_region.get("increase_detected")) and h5_change >= float(min_h5_change_pct)
    h7_fresh = bool(h7_region.get("regional_data_fresh", True))
    h7_quality = dict(h7_region.get("quality_gate") or {})
    h7_quality_ok = bool(h7_quality.get("overall_passed"))
    h7_stage = _stage(h7_region)
    h7_support = h7_fresh and h7_quality_ok and h7_stage in {"prepare", "activate"}

    blockers = sorted(
        {
            *[str(item) for item in h5_region.get("blockers") or []],
            *[str(item) for item in h7_region.get("coverage_blockers") or []],
        }
    )
    if not h7_region:
        return {
            "alignment_status": "h7_missing",
            "h5_rise": h5_rise,
            "h7_support": False,
            "blockers": blockers or ["h7_missing"],
            "statistical_read": "H5 ist vorhanden, aber H7 fehlt fuer diese Region.",
            "budget_read": "Keine Budgetfreigabe; erst H7-Abdeckung herstellen.",
            "media_action": "do_not_shift",
            "budget_permission": "blocked",
            "risk_level": "high",
            "decision_weight": 0.0,
        }
    if not h7_fresh:
        return {
            "alignment_status": "coverage_blocked",
            "h5_rise": h5_rise,
            "h7_support": False,
            "blockers": blockers or ["regional_data_stale"],
            "statistical_read": "H7 ist vorhanden, aber regional zu alt fuer eine saubere Bestaetigung.",
            "budget_read": "Keine Budgetfreigabe; erst Datenfrische reparieren.",
            "media_action": "do_not_shift",
            "budget_permission": "blocked",
            "risk_level": "high",
            "decision_weight": 0.0,
        }
    if h5_rise and h7_support:
        return {
            "alignment_status": "confirmed_direction",
            "h5_rise": True,
            "h7_support": True,
            "blockers": blockers,
            "statistical_read": "H5 kurzfristig hoch, H7 frisch bestaetigt die Richtung.",
            "budget_read": "Kandidat, aber Budgetfreigabe bleibt an Business- und Spend-Gates gekoppelt.",
            "media_action": "controlled_shift_candidate",
            "budget_permission": "blocked_until_business_truth",
            "risk_level": "medium",
            "decision_weight": 0.85,
        }
    if h5_rise and not h7_support:
        return {
            "alignment_status": "short_term_only",
            "h5_rise": True,
            "h7_support": False,
            "blockers": blockers,
            "statistical_read": "H5 steigt kurzfristig, H7 bestaetigt noch nicht.",
            "budget_read": "Nur beobachten oder vorbereiten; keine automatische Budgetverschiebung.",
            "media_action": "prepare_creative_hold_budget",
            "budget_permission": "blocked_until_h7_confirmation",
            "risk_level": "medium_high",
            "decision_weight": 0.45,
        }
    if not h5_rise and h7_support:
        return {
            "alignment_status": "weekly_building",
            "h5_rise": False,
            "h7_support": True,
            "blockers": blockers,
            "statistical_read": "H7 zeigt Richtung, H5 zeigt noch keinen kurzfristigen Anstieg.",
            "budget_read": "Planungssignal, aber noch kein kurzfristiger Shift.",
            "media_action": "prepare_watchlist",
            "budget_permission": "blocked_until_h5_or_business_truth",
            "risk_level": "medium_high",
            "decision_weight": 0.55,
        }
    return {
        "alignment_status": "no_aligned_rise",
        "h5_rise": False,
        "h7_support": False,
        "blockers": blockers,
        "statistical_read": "H5 und H7 zeigen gemeinsam keinen belastbaren Anstieg.",
        "budget_read": "Watch.",
        "media_action": "watch",
        "budget_permission": "not_requested",
        "risk_level": "low",
        "decision_weight": 0.15,
    }


def build_horizon_alignment_snapshot(
    *,
    h5_snapshot: dict[str, Any],
    h7_forecasts: dict[str, dict[str, Any]],
    min_h5_change_pct: float = 10.0,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    h5_by_virus_region = {
        (virus, item.get("region")): item
        for virus, payload in (h5_snapshot.get("viruses") or {}).items()
        for item in payload.get("regions") or []
    }
    h7_by_virus_region = {
        (virus, item.get("bundesland")): item
        for virus, payload in h7_forecasts.items()
        for item in payload.get("predictions") or []
    }
    viruses = sorted({virus for virus, _region in h5_by_virus_region} | set(h7_forecasts))
    for virus in viruses:
        for region in ALL_BUNDESLAENDER:
            h5_item = h5_by_virus_region.get((virus, region))
            h7_item = h7_by_virus_region.get((virus, region))
            alignment = classify_horizon_alignment(
                h5_item,
                h7_item,
                min_h5_change_pct=min_h5_change_pct,
            )
            rows.append(
                {
                    "virus_typ": virus,
                    "region": region,
                    "region_name": BUNDESLAND_NAMES.get(region, region),
                    "h5": h5_item,
                    "h7": h7_item,
                    "alignment": alignment,
                }
            )

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str((row["alignment"] or {}).get("alignment_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "policy": {
            "h5_role": "short_term_curve_rise",
            "h7_role": "weekly_direction_confirmation",
            "combination_rule": "do_not_average_probabilities",
            "budget_rule": "budget_requires_h5_rise_h7_fresh_support_and_business_gate",
        },
        "summary": {
            "total_rows": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "rows": rows,
    }
