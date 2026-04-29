"""Budget-neutral allocator for MediaSpendingTruth v1.

Deltas are expressed as percentage points of the total weekly budget. That makes
budget conservation explicit even when regional base budgets differ.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class BudgetAllocatorConfig:
    max_weekly_shift_pct: float = 15.0
    uncertainty_shift_cap_pct: float = 5.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _cap_for_row(row: dict[str, Any], config: BudgetAllocatorConfig) -> float:
    cap = min(
        abs(_safe_float(row.get("max_delta_pct"), config.max_weekly_shift_pct)),
        abs(config.max_weekly_shift_pct),
    )
    if row.get("uncertainty_capped"):
        cap = min(cap, abs(config.uncertainty_shift_cap_pct))
    return max(0.0, cap)


def _clip(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def _rebalance_to_zero(deltas: list[float], caps: list[float]) -> list[float]:
    adjusted = list(deltas)
    for _ in range(20):
        drift = sum(adjusted)
        if abs(drift) <= 1e-9:
            break
        if drift > 0:
            room = [max(value + cap, 0.0) for value, cap in zip(adjusted, caps)]
            total_room = sum(room)
            if total_room <= 1e-12:
                break
            for idx, available in enumerate(room):
                if available <= 0:
                    continue
                adjusted[idx] = max(-caps[idx], adjusted[idx] - drift * (available / total_room))
        else:
            needed = -drift
            room = [max(cap - value, 0.0) for value, cap in zip(adjusted, caps)]
            total_room = sum(room)
            if total_room <= 1e-12:
                break
            for idx, available in enumerate(room):
                if available <= 0:
                    continue
                adjusted[idx] = min(caps[idx], adjusted[idx] + needed * (available / total_room))
    return adjusted


def allocate_budget_deltas(
    regions: Iterable[dict[str, Any]],
    *,
    config: BudgetAllocatorConfig | None = None,
) -> dict[str, Any]:
    """Allocate capped, budget-neutral deltas from opportunity scores."""

    cfg = config or BudgetAllocatorConfig()
    rows = [dict(region) for region in regions]
    if not rows:
        return {"policy": cfg.__dict__, "total_before_budget_eur": 0.0, "total_after_budget_eur": 0.0, "regions": []}

    total_budget = sum(max(_safe_float(row.get("base_budget_eur")), 0.0) for row in rows)
    if total_budget <= 0:
        total_budget = float(len(rows))
        for row in rows:
            row.setdefault("base_budget_eur", 1.0)

    scores = [_safe_float(row.get("budget_opportunity_score")) for row in rows]
    caps = [_cap_for_row(row, cfg) for row in rows]
    mean_score = sum(scores) / len(scores)
    centered = [score - mean_score for score in scores]
    max_abs = max((abs(value) for value in centered), default=0.0)

    if max_abs <= 1e-12 or max(caps, default=0.0) <= 0.0:
        raw_deltas = [0.0 for _ in rows]
    else:
        raw_deltas = [
            _clip((value / max_abs) * cfg.max_weekly_shift_pct, cap)
            for value, cap in zip(centered, caps)
        ]
        raw_deltas = _rebalance_to_zero(raw_deltas, caps)

    rounded_deltas = [round(value, 6) for value in raw_deltas]
    drift = round(-sum(rounded_deltas), 6)
    if abs(drift) > 0.0:
        for idx in reversed(range(len(rounded_deltas))):
            if abs(rounded_deltas[idx] + drift) <= caps[idx] + 1e-9:
                rounded_deltas[idx] = round(rounded_deltas[idx] + drift, 6)
                break

    output_rows: list[dict[str, Any]] = []
    total_after = 0.0
    for row, delta_pct in zip(rows, rounded_deltas):
        before = max(_safe_float(row.get("base_budget_eur")), 0.0)
        shift_eur = total_budget * delta_pct / 100.0
        after = before + shift_eur
        enriched = dict(row)
        enriched["before_budget_eur"] = round(before, 2)
        enriched["allocated_shift_eur"] = round(shift_eur, 2)
        enriched["after_budget_eur"] = round(after, 2)
        enriched["recommended_delta_pct"] = delta_pct
        output_rows.append(enriched)
        total_after += enriched["after_budget_eur"]

    rounding_drift_eur = round(total_budget - total_after, 2)
    if output_rows and abs(rounding_drift_eur) >= 0.01:
        output_rows[-1]["after_budget_eur"] = round(output_rows[-1]["after_budget_eur"] + rounding_drift_eur, 2)
        output_rows[-1]["allocated_shift_eur"] = round(
            output_rows[-1]["after_budget_eur"] - output_rows[-1]["before_budget_eur"], 2
        )

    return {
        "policy": {
            "max_weekly_shift_pct": float(cfg.max_weekly_shift_pct),
            "uncertainty_shift_cap_pct": float(cfg.uncertainty_shift_cap_pct),
            "delta_basis": "percentage_points_of_total_budget",
        },
        "total_before_budget_eur": round(total_budget, 2),
        "total_after_budget_eur": round(sum(row["after_budget_eur"] for row in output_rows), 2),
        "regions": output_rows,
    }
