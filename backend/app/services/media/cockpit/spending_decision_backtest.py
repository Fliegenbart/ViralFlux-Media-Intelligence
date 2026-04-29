"""Decision-oriented backtest for MediaSpendingTruth v1."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _normalise(scores: Iterable[float]) -> list[float]:
    values = [max(_safe_float(score), 0.0) for score in scores]
    total = sum(values)
    if total <= 0.0:
        if not values:
            return []
        return [1.0 / len(values) for _ in values]
    return [value / total for value in values]


def _capture(weights: list[float], future_activity: list[float]) -> float:
    total_future = sum(future_activity)
    if total_future <= 0.0:
        return 0.0
    return sum(weight * future for weight, future in zip(weights, future_activity)) / total_future


def _timeline_rows_by_issue(artifact: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    details = artifact.get("details") or {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for region_code, region_payload in details.items():
        timeline = []
        if isinstance(region_payload, dict):
            timeline = list(region_payload.get("timeline") or [])
        for row in timeline:
            if not isinstance(row, dict):
                continue
            issue = str(row.get("as_of_date") or row.get("forecast_week_start") or row.get("issue_date") or "")
            if not issue:
                continue
            enriched = dict(row)
            enriched["region_code"] = str(region_code)
            grouped.setdefault(issue, []).append(enriched)
    return grouped


def _issue_metrics(rows: list[dict[str, Any]], *, top_k: int) -> dict[str, dict[str, float]]:
    current = [_safe_float(row.get("current_known_incidence")) for row in rows]
    expected = [_safe_float(row.get("expected_target_incidence") or row.get("expected_next_week_incidence")) for row in rows]
    future = [
        max(_safe_float(row.get("next_week_incidence") or row.get("observed_target_incidence") or row.get("target_incidence")) - cur, 0.0)
        for row, cur in zip(rows, current)
    ]
    populations = [_safe_float(row.get("state_population_millions"), 1.0) for row in rows]
    expected_growth = [max(exp - cur, 0.0) for exp, cur in zip(expected, current)]
    probabilities = [
        _safe_float(row.get("event_probability_calibrated") or row.get("event_probability"))
        for row in rows
    ]
    model_scores = [prob * (growth + 1e-6) for prob, growth in zip(probabilities, expected_growth)]

    strategy_scores = {
        "model_based_media_spending_truth": model_scores,
        "static_allocation": [1.0 for _ in rows],
        "population_weighted_allocation": populations,
        "highest_current_incidence_allocation": current,
        "highest_recent_growth_allocation": expected_growth,
        "persistence_allocation": current,
    }
    oracle_weights = _normalise(future)
    oracle_capture = _capture(oracle_weights, future)
    metrics: dict[str, dict[str, float]] = {}
    event_regions = {idx for idx, value in enumerate(future) if value > 0.0}
    for name, scores in strategy_scores.items():
        weights = _normalise(scores)
        capture = _capture(weights, future)
        regret = max(oracle_capture - capture, 0.0)
        ranked = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)[: max(1, min(top_k, len(scores)))]
        hit_rate = sum(1 for idx in ranked if idx in event_regions) / len(ranked) if ranked else 0.0
        metrics[name] = {
            "budget_weighted_event_capture": capture,
            "allocation_regret_vs_oracle": regret,
            "top_k_hit_rate_among_increased_regions": hit_rate,
        }
    metrics["oracle_allocation"] = {
        "budget_weighted_event_capture": oracle_capture,
        "allocation_regret_vs_oracle": 0.0,
        "top_k_hit_rate_among_increased_regions": 1.0 if event_regions else 0.0,
    }
    return metrics


def evaluate_spending_decision_backtest(
    artifact: dict[str, Any] | None,
    *,
    min_regret_reduction: float = 0.03,
    min_evaluable_weeks: int = 2,
    top_k: int = 3,
) -> dict[str, Any]:
    """Evaluate whether model-based allocation beats simple budget baselines."""

    grouped = _timeline_rows_by_issue(artifact or {})
    issue_metrics: list[dict[str, dict[str, float]]] = []
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        future_total = sum(
            max(
                _safe_float(row.get("next_week_incidence") or row.get("observed_target_incidence") or row.get("target_incidence"))
                - _safe_float(row.get("current_known_incidence")),
                0.0,
            )
            for row in rows
        )
        if future_total <= 0.0:
            continue
        issue_metrics.append(_issue_metrics(rows, top_k=top_k))

    if not issue_metrics:
        return {
            "decision_backtest_passed": False,
            "evaluable_panel_weeks": 0,
            "budget_weighted_event_capture": 0.0,
            "allocation_regret_vs_oracle": None,
            "regret_reduction_vs_static": 0.0,
            "regret_reduction_vs_current_incidence": 0.0,
            "regret_reduction_vs_baselines": {},
            "best_baseline_name": None,
            "model_rank_among_strategies": None,
            "safe_max_shift_pct_recommendation": 0.0,
            "baselines": {},
        }

    names = sorted(issue_metrics[0].keys())
    averaged: dict[str, dict[str, float]] = {}
    for name in names:
        averaged[name] = {
            key: round(sum(issue[name][key] for issue in issue_metrics) / len(issue_metrics), 6)
            for key in issue_metrics[0][name]
        }

    model = averaged["model_based_media_spending_truth"]
    baselines = {
        name: metrics
        for name, metrics in averaged.items()
        if name not in {"model_based_media_spending_truth", "oracle_allocation"}
    }
    static_regret = baselines.get("static_allocation", {}).get("allocation_regret_vs_oracle", 0.0)
    current_regret = baselines.get("highest_current_incidence_allocation", {}).get("allocation_regret_vs_oracle", 0.0)
    regret_reduction_vs_baselines = {
        name: round(metrics["allocation_regret_vs_oracle"] - model["allocation_regret_vs_oracle"], 6)
        for name, metrics in baselines.items()
    }
    best_baseline_name = min(
        baselines,
        key=lambda name: baselines[name]["allocation_regret_vs_oracle"],
    ) if baselines else None

    rank_entries = [("model_based_media_spending_truth", model)] + sorted(baselines.items())
    rank_entries.sort(key=lambda item: (item[1]["allocation_regret_vs_oracle"], 0 if item[0] == "model_based_media_spending_truth" else 1))
    model_rank = next(idx for idx, item in enumerate(rank_entries, start=1) if item[0] == "model_based_media_spending_truth")
    regret_reduction_vs_static = round(static_regret - model["allocation_regret_vs_oracle"], 6)
    regret_reduction_vs_current = round(current_regret - model["allocation_regret_vs_oracle"], 6)
    decision_backtest_passed = (
        len(issue_metrics) >= int(min_evaluable_weeks)
        and regret_reduction_vs_static >= float(min_regret_reduction)
        and model_rank == 1
    )

    return {
        "decision_backtest_passed": bool(decision_backtest_passed),
        "evaluable_panel_weeks": len(issue_metrics),
        "budget_weighted_event_capture": model["budget_weighted_event_capture"],
        "top_k_hit_rate_among_increased_regions": model["top_k_hit_rate_among_increased_regions"],
        "allocation_regret_vs_oracle": model["allocation_regret_vs_oracle"],
        "regret_reduction_vs_static": regret_reduction_vs_static,
        "regret_reduction_vs_current_incidence": regret_reduction_vs_current,
        "regret_reduction_vs_baselines": regret_reduction_vs_baselines,
        "best_baseline_name": best_baseline_name,
        "model_rank_among_strategies": model_rank,
        "safe_max_shift_pct_recommendation": 15.0 if decision_backtest_passed else 5.0 if regret_reduction_vs_static > 0 else 0.0,
        "baselines": baselines,
    }


def _virus_slug(virus_typ: str) -> str:
    return str(virus_typ or "").lower().replace(" ", "_").replace("-", "_")


def _candidate_artifact_paths(virus_typ: str, horizon_days: int) -> list[Path]:
    slug = _virus_slug(virus_typ)
    return [
        Path("/app/app/ml_models") / "regional_panel" / slug / f"horizon_{horizon_days}" / "backtest.json",
        Path("/app/app/ml_models") / "regional_panel" / slug / f"h{horizon_days}" / "backtest.json",
        Path.cwd() / "app/ml_models" / "regional_panel" / slug / f"horizon_{horizon_days}" / "backtest.json",
        Path.cwd() / "backend/app/ml_models" / "regional_panel" / slug / f"horizon_{horizon_days}" / "backtest.json",
    ]


def evaluate_spending_decision_backtest_for_scope(
    *,
    virus_typ: str,
    horizon_days: int,
    min_regret_reduction: float = 0.03,
) -> dict[str, Any]:
    for path in _candidate_artifact_paths(virus_typ, horizon_days):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                artifact = json.load(handle)
            payload = evaluate_spending_decision_backtest(
                artifact,
                min_regret_reduction=min_regret_reduction,
            )
            payload["artifact_path"] = str(path)
            return payload
        except Exception as exc:  # noqa: BLE001
            return {
                "decision_backtest_passed": False,
                "error": str(exc),
                "artifact_path": str(path),
                "regret_reduction_vs_static": 0.0,
                "baselines": {},
            }
    return {
        "decision_backtest_passed": False,
        "error": "decision_backtest_artifact_missing",
        "artifact_path": None,
        "regret_reduction_vs_static": 0.0,
        "baselines": {},
    }
