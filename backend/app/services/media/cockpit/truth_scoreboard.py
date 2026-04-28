"""Investor-grade truth scoreboard for regional h5/h7 forecast artifacts.

This module does not invent media uplift. It reads the persisted regional
walk-forward backtests and answers a narrower question: did the forecast rank
the later truth better than simple persistence, and is there enough evaluated
history to trust the horizon as an operational signal?
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.services.media.cockpit.backtest_builder import build_backtest_summary


DEFAULT_VIRUSES = ("Influenza A", "Influenza B", "RSV A")
DEFAULT_HORIZONS = (5, 7)
MIN_EVALUABLE_WEEKS = 12
MIN_HIT_RATE = 0.60
MIN_PR_AUC_LIFT = 1.05
MAX_ECE = 0.05


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _score_from_metrics(
    *,
    hit_rate: float | None,
    pr_auc_multiplier: float | None,
    precision_pp: float | None,
    ece: float | None,
    quality_gate_passed: bool,
) -> float:
    hit_component = 0.0 if hit_rate is None else min(max(hit_rate, 0.0), 1.0) * 35.0
    lift_component = (
        0.0
        if pr_auc_multiplier is None
        else min(max((pr_auc_multiplier - 1.0) / 2.0, 0.0), 1.0) * 25.0
    )
    precision_component = (
        0.0
        if precision_pp is None
        else min(max((precision_pp + 0.05) / 0.25, 0.0), 1.0) * 20.0
    )
    calibration_component = (
        10.0
        if ece is None
        else max(0.0, min(1.0, (MAX_ECE * 2.0 - ece) / (MAX_ECE * 2.0))) * 10.0
    )
    quality_component = 10.0 if quality_gate_passed else 4.0
    return round(
        hit_component
        + lift_component
        + precision_component
        + calibration_component
        + quality_component,
        1,
    )


def _plain_read(readiness: str, *, horizon_days: int) -> str:
    if readiness == "go":
        return f"H{horizon_days} ist als Forecast-Signal belastbar."
    if readiness == "candidate":
        return f"H{horizon_days} ist nutzbar, aber nur mit sichtbaren Warnhinweisen."
    if readiness == "blocked":
        return f"H{horizon_days} ist fuer harte Media-Entscheidungen noch blockiert."
    return f"H{horizon_days} konnte nicht bewertet werden."


def build_horizon_truth_card(
    *,
    virus_typ: str,
    horizon_days: int,
    models_dir: Path | None = None,
    weeks_to_surface: int = 400,
    min_evaluable_weeks: int = MIN_EVALUABLE_WEEKS,
    min_hit_rate: float = MIN_HIT_RATE,
    min_pr_auc_lift: float = MIN_PR_AUC_LIFT,
    max_ece: float = MAX_ECE,
    min_regions_for_top3: int = 14,
) -> dict[str, Any]:
    payload = build_backtest_summary(
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        models_dir=models_dir,
        weeks_to_surface=weeks_to_surface,
        min_regions_for_top3=min_regions_for_top3,
    )
    if not payload.get("available"):
        return {
            "virus_typ": virus_typ,
            "horizon_days": int(horizon_days),
            "available": False,
            "readiness": "blocked",
            "score": 0.0,
            "blockers": ["artifact_missing"],
            "warnings": [],
            "reason": payload.get("reason"),
            "plain_language": f"Kein bewertbares H{horizon_days}-Backtest-Artefakt gefunden.",
        }

    weekly = payload.get("weekly_hits") or []
    evaluable = [row for row in weekly if row.get("is_evaluable_top3_panel")]
    coverage_rejected = [
        row
        for row in weekly
        if row.get("observed_top") and not row.get("is_evaluable_top3_panel")
    ]
    hits = [row for row in evaluable if row.get("was_hit")]
    misses = [row for row in evaluable if not row.get("was_hit")]
    non_event_or_unscored = max(0, len(weekly) - len(evaluable) - len(coverage_rejected))
    hit_rate = (len(hits) / len(evaluable)) if evaluable else None

    headline = payload.get("headline") or {}
    baselines = payload.get("baselines") or {}
    precision = _safe_float(headline.get("precision_at_top3"))
    baseline_precision = _safe_float(baselines.get("persistence_precision_at_top3"))
    pr_auc = _safe_float(headline.get("pr_auc"))
    baseline_pr_auc = _safe_float(baselines.get("persistence_pr_auc"))
    ece = _safe_float(headline.get("ece"))
    brier = _safe_float(headline.get("brier_score"))
    pr_auc_multiplier = _ratio(pr_auc, baseline_pr_auc)
    precision_pp = None
    if precision is not None and baseline_precision is not None:
        precision_pp = precision - baseline_precision

    quality_gate = payload.get("quality_gate") or {}
    quality_gate_passed = bool(quality_gate.get("overall_passed"))

    blockers: list[str] = []
    warnings: list[str] = []
    if len(evaluable) < int(min_evaluable_weeks):
        blockers.append("too_few_evaluable_weeks")
    if hit_rate is None:
        blockers.append("no_evaluable_full_panel_truth_weeks")
    elif hit_rate < float(min_hit_rate):
        blockers.append("hit_rate_below_gate")
    if coverage_rejected:
        warnings.append("some_truth_weeks_rejected_for_insufficient_panel_coverage")
    if pr_auc_multiplier is None:
        warnings.append("persistence_pr_auc_missing")
    elif pr_auc_multiplier < float(min_pr_auc_lift):
        blockers.append("does_not_beat_persistence_pr_auc")
    if precision_pp is None:
        warnings.append("persistence_precision_missing")
    elif precision_pp < 0:
        blockers.append("precision_below_persistence")
    if ece is not None and ece > float(max_ece):
        warnings.append("calibration_ece_above_gate")
    if not quality_gate_passed:
        blockers.append("artifact_quality_gate_not_passed")

    if blockers:
        readiness = "blocked"
    elif warnings:
        readiness = "candidate"
    else:
        readiness = "go"

    score = _score_from_metrics(
        hit_rate=hit_rate,
        pr_auc_multiplier=pr_auc_multiplier,
        precision_pp=precision_pp,
        ece=ece,
        quality_gate_passed=quality_gate_passed,
    )
    if blockers:
        score = min(score, 69.0)
    elif warnings:
        score = min(score, 84.0)
    else:
        score = max(score, 70.0)

    return {
        "virus_typ": virus_typ,
        "horizon_days": int(horizon_days),
        "available": True,
        "readiness": readiness,
        "score": score,
        "window": payload.get("window") or {},
        "coverage_policy": payload.get("coverage_policy") or {},
        "evaluable_weeks": len(evaluable),
        "hit_weeks": len(hits),
        "miss_weeks": len(misses),
        "coverage_rejected_weeks": len(coverage_rejected),
        "pending_truth_weeks": non_event_or_unscored,
        "non_event_or_unscored_weeks": non_event_or_unscored,
        "hit_rate": _round(hit_rate),
        "headline": {
            "precision_at_top3": _round(precision),
            "pr_auc": _round(pr_auc),
            "brier_score": _round(brier),
            "ece": _round(ece),
            "median_lead_days": headline.get("median_lead_days"),
        },
        "baseline": {
            "persistence_precision_at_top3": _round(baseline_precision),
            "persistence_pr_auc": _round(baseline_pr_auc),
        },
        "lift_vs_persistence": {
            "pr_auc_multiplier": _round(pr_auc_multiplier),
            "precision_pp": _round(precision_pp),
        },
        "quality_gate": quality_gate,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "plain_language": _plain_read(readiness, horizon_days=horizon_days),
    }


def _combined_decision(h5: dict[str, Any] | None, h7: dict[str, Any] | None) -> dict[str, Any]:
    h5_ready = (h5 or {}).get("readiness")
    h7_ready = (h7 or {}).get("readiness")
    h5_ok = h5_ready in {"go", "candidate"}
    h7_ok = h7_ready in {"go", "candidate"}

    if h5_ok and h7_ok:
        return {
            "decision_class": "short_and_weekly_supported",
            "media_action": "controlled_shift_candidate",
            "budget_permission": "blocked_until_business_truth",
            "plain_language": "H5 und H7 liefern beide nutzbare Evidenz; Budget bleibt trotzdem vom Business-Truth-Gate abhaengig.",
        }
    if h7_ok and not h5_ok:
        return {
            "decision_class": "weekly_only_prepare",
            "media_action": "prepare_watchlist",
            "budget_permission": "blocked_until_h5_or_business_truth",
            "plain_language": "H7 sieht ein Wochen-Signal, H5 ist noch nicht hart genug; vorbereiten, nicht schieben.",
        }
    if h5_ok and not h7_ok:
        return {
            "decision_class": "short_term_only_unconfirmed",
            "media_action": "prepare_creative_hold_budget",
            "budget_permission": "blocked_until_h7_confirmation",
            "plain_language": "H5 sieht kurzfristig etwas, H7 bestaetigt nicht; kein automatischer Shift.",
        }
    return {
        "decision_class": "insufficient_forecast_evidence",
        "media_action": "watch",
        "budget_permission": "not_requested",
        "plain_language": "Kein belastbarer gemeinsamer H5/H7-Nachweis.",
    }


def build_truth_scoreboard(
    *,
    virus_types: Iterable[str] = DEFAULT_VIRUSES,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    models_dir: Path | None = None,
    weeks_to_surface: int = 400,
    min_evaluable_weeks: int = MIN_EVALUABLE_WEEKS,
    min_regions_for_top3: int = 14,
) -> dict[str, Any]:
    scorecards: list[dict[str, Any]] = []
    for virus_typ in virus_types:
        for horizon_days in horizons:
            scorecards.append(
                build_horizon_truth_card(
                    virus_typ=str(virus_typ),
                    horizon_days=int(horizon_days),
                    models_dir=models_dir,
                    weeks_to_surface=weeks_to_surface,
                    min_evaluable_weeks=min_evaluable_weeks,
                    min_regions_for_top3=min_regions_for_top3,
                )
            )

    combined: dict[str, dict[str, Any]] = {}
    viruses = sorted({str(card.get("virus_typ")) for card in scorecards})
    for virus in viruses:
        by_horizon = {
            int(card["horizon_days"]): card
            for card in scorecards
            if card.get("virus_typ") == virus and card.get("horizon_days") is not None
        }
        decision = _combined_decision(by_horizon.get(5), by_horizon.get(7))
        combined[virus] = {
            "virus_typ": virus,
            "h5": by_horizon.get(5),
            "h7": by_horizon.get(7),
            **decision,
        }

    readiness_counts: dict[str, int] = {}
    for card in scorecards:
        readiness = str(card.get("readiness") or "unknown")
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1
    if readiness_counts.get("blocked"):
        overall = "mixed_blocked"
    elif readiness_counts.get("candidate"):
        overall = "mixed_candidate"
    elif readiness_counts.get("go"):
        overall = "go"
    else:
        overall = "unknown"

    return {
        "scoreboard_type": "walk_forward_artifact_truth_scoreboard",
        "policy": {
            "truth_source": "regional_walk_forward_backtest_artifacts",
            "h5_role": "short_term_curve_rise",
            "h7_role": "weekly_direction_confirmation",
            "combination_rule": "do_not_average_horizons",
            "budget_rule": "never_auto_release_without_business_truth",
        },
        "gates": {
            "min_evaluable_weeks": int(min_evaluable_weeks),
            "min_regions_for_top3": int(min_regions_for_top3),
            "min_hit_rate": MIN_HIT_RATE,
            "min_pr_auc_lift": MIN_PR_AUC_LIFT,
            "max_ece": MAX_ECE,
        },
        "summary": {
            "total_scorecards": len(scorecards),
            "readiness_counts": dict(sorted(readiness_counts.items())),
            "overall_readiness": overall,
        },
        "combined_by_virus": combined,
        "scorecards": scorecards,
    }
