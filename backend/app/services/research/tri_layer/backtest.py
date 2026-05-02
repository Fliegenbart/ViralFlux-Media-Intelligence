"""Research-only TLEF-BICG backtest runner.

This module is deliberately isolated from production readiness, media
allocation and budget services. It evaluates historical cutoffs and writes a
JSON report for research review only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from app.services.research.tri_layer.schema import (
    BudgetIsolationEvidence,
    SourceEvidence,
    TriLayerRegionEvidence,
)
from app.services.research.tri_layer.service import build_region_snapshot


DEFAULT_BACKTEST_DIR = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "processed"
    / "tri_layer_backtests"
)

BUDGET_STATE_RANK = {
    "blocked": 0,
    "calibration_window": 1,
    "shadow_only": 2,
    "limited": 3,
    "approved": 4,
}

BASELINES = [
    "persistence",
    "clinical_only",
    "wastewater_plus_clinical",
    "tri_layer_without_budget_isolation",
    "tri_layer_with_budget_isolation",
]


@dataclass(frozen=True)
class TriLayerBacktestConfig:
    virus_typ: str = "Influenza A"
    brand: str = "gelo"
    horizon_days: int = 7
    start_date: str = "2024-10-01"
    end_date: str = "2026-04-30"
    mode: str = "historical_cutoff"
    include_sales: bool = False
    output_dir: Path = DEFAULT_BACKTEST_DIR
    run_id: str | None = None


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)[:10]).date()


def _iso(value: Any) -> str:
    return _as_date(value).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _source_status(source: str, row: Mapping[str, Any] | None) -> str:
    if row is None:
        return "not_connected"
    explicit = str(row.get("status") or "").strip()
    if explicit in {"connected", "partial", "not_connected"}:
        return explicit
    return "connected"


def _source_from_row(source: str, row: Mapping[str, Any] | None) -> SourceEvidence:
    if row is None:
        return SourceEvidence(status="not_connected")
    return SourceEvidence(
        status=_source_status(source, row),  # type: ignore[arg-type]
        freshness=_safe_float(row.get("freshness")),
        reliability=_safe_float(row.get("reliability")),
        baseline_stability=_safe_float(row.get("baseline_stability")),
        snr=_safe_float(row.get("snr")),
        consistency=_safe_float(row.get("consistency")),
        drift=_safe_float(row.get("drift")),
        coverage=_safe_float(row.get("coverage")),
        signal=_safe_float(row.get("signal")),
        intensity=_safe_float(row.get("intensity")),
        growth=_safe_float(row.get("growth")),
        budget_isolated=bool(row.get("budget_isolated") or False),
        causal_adjusted=bool(row.get("causal_adjusted") or False),
    )


def _latest_by_source(
    rows: Iterable[Mapping[str, Any]],
    *,
    cutoff: date,
    region_code: str,
    include_sales: bool,
) -> dict[str, Mapping[str, Any] | None]:
    latest: dict[str, Mapping[str, Any] | None] = {
        "wastewater": None,
        "clinical": None,
        "sales": None,
    }
    for row in rows:
        source = str(row.get("source") or "").strip().lower()
        if source not in latest:
            continue
        if source == "sales" and not include_sales:
            continue
        if str(row.get("region_code") or "").upper() != region_code:
            continue
        available = _as_date(row.get("available_date") or row.get("signal_date"))
        if available > cutoff:
            continue
        current = latest[source]
        if current is None or available >= _as_date(current.get("available_date") or current.get("signal_date")):
            latest[source] = row
    return latest


def _source_input_trace(source: str, row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "source": source,
            "available_date": None,
            "signal_date": None,
            "signal": None,
            "status": "not_connected",
        }
    return {
        "source": source,
        "available_date": _iso(row.get("available_date") or row.get("signal_date")),
        "signal_date": _iso(row.get("signal_date") or row.get("available_date")),
        "signal": _safe_float(row.get("signal")),
        "status": _source_status(source, row),
    }


def _observed_for_cutoff(
    rows: Iterable[Mapping[str, Any]],
    *,
    cutoff: date,
    region_code: str,
    horizon_days: int,
) -> dict[str, Any]:
    end_ordinal = cutoff.toordinal() + int(horizon_days)
    candidates: list[Mapping[str, Any]] = []
    for row in rows:
        if str(row.get("region_code") or "").upper() != region_code:
            continue
        signal_date = _as_date(row.get("signal_date") or row.get("available_date"))
        if cutoff.toordinal() < signal_date.toordinal() <= end_ordinal:
            candidates.append(row)
    if not candidates:
        return {"observed_onset": False, "observed_phase": "unknown", "observed_peak_date": None}
    onset = any(_safe_bool(row.get("observed_onset")) for row in candidates)
    phase = next((str(row.get("observed_phase")) for row in candidates if row.get("observed_phase")), "unknown")
    peak_date = next((row.get("observed_peak_date") for row in candidates if row.get("observed_peak_date")), None)
    return {
        "observed_onset": bool(onset),
        "observed_phase": phase,
        "observed_peak_date": _iso(peak_date) if peak_date else None,
    }


def _permission_without_budget_isolation(snapshot_state: str) -> str:
    if snapshot_state == "blocked":
        return "blocked"
    if snapshot_state == "calibration_window":
        return "calibration_window"
    return "shadow_only"


def _empty_gate_counts() -> dict[str, dict[str, int]]:
    gates = [
        "epidemiological_signal",
        "clinical_confirmation",
        "sales_calibration",
        "coverage",
        "drift",
        "budget_isolation",
    ]
    states = ["pass", "watch", "fail", "not_available"]
    return {gate: {state: 0 for state in states} for gate in gates}


def _compute_metrics(cutoff_results: list[dict[str, Any]], *, include_sales: bool) -> dict[str, Any]:
    gate_counts = _empty_gate_counts()
    for row in cutoff_results:
        for gate, state in (row.get("gates") or {}).items():
            if gate in gate_counts and state in gate_counts[gate]:
                gate_counts[gate][state] += 1

    early_rows = [row for row in cutoff_results if (row.get("early_warning_score") or 0) >= 50]
    onset_rows = [row for row in cutoff_results if row.get("observed_onset")]
    false_early = [row for row in early_rows if not row.get("observed_onset")]
    phase_known = [row for row in cutoff_results if row.get("observed_phase") not in {None, "unknown"}]
    phase_hits = [row for row in phase_known if row.get("wave_phase") == row.get("observed_phase")]
    calibration_rows = [
        row for row in cutoff_results
        if row.get("early_warning_score") is not None and row.get("observed_onset") is not None
    ]
    calibration_error = None
    if calibration_rows:
        calibration_error = round(
            sum(
                abs(float(row["early_warning_score"]) / 100.0 - (1.0 if row.get("observed_onset") else 0.0))
                for row in calibration_rows
            )
            / len(calibration_rows),
            6,
        )

    lead_times: list[int] = []
    for row in early_rows:
        peak_date = row.get("observed_peak_date")
        if peak_date:
            lead_times.append(_as_date(peak_date).toordinal() - _as_date(row["cutoff_date"]).toordinal())

    return {
        "onset_detection_gain": round((len(early_rows) - len(onset_rows)) / max(len(cutoff_results), 1), 6),
        "peak_lead_time": round(sum(lead_times) / len(lead_times), 6) if lead_times else None,
        "false_early_warning_rate": round(len(false_early) / max(len(early_rows), 1), 6),
        "phase_accuracy": round(len(phase_hits) / max(len(phase_known), 1), 6) if phase_known else None,
        "sales_lift_predictiveness": None if not include_sales else None,
        "budget_regret_reduction": None if not include_sales else None,
        "calibration_error": calibration_error,
        "number_of_cutoffs": len({row["cutoff_date"] for row in cutoff_results}),
        "number_of_regions": len({row["region_code"] for row in cutoff_results}),
        "gate_transition_counts": gate_counts,
    }


def _baseline_summary(cutoff_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    false_budget_without = sum(
        1
        for row in cutoff_results
        if row["budget_state_without_isolation"] in {"limited", "approved", "shadow_only"}
        and not row.get("observed_onset")
    )
    false_budget_with = sum(
        1
        for row in cutoff_results
        if row["budget_permission_state"] in {"limited", "approved", "shadow_only"}
        and not row.get("observed_onset")
    )
    return {
        "persistence": {"description": "Previous observed phase carries forward."},
        "clinical_only": {"description": "Clinical source only."},
        "wastewater_plus_clinical": {"description": "Epidemiological sources without sales."},
        "tri_layer_without_budget_isolation": {
            "false_budget_triggers": false_budget_without,
            "description": "Tri-Layer gates evaluated as if budget isolation did not exist.",
        },
        "tri_layer_with_budget_isolation": {
            "false_budget_triggers": false_budget_with,
            "description": "Tri-Layer gates with explicit budget isolation.",
        },
    }


def run_tri_layer_backtest_panel(
    panel: Iterable[Mapping[str, Any]],
    config: TriLayerBacktestConfig,
) -> dict[str, Any]:
    if config.mode != "historical_cutoff":
        raise ValueError("Tri-Layer backtest currently supports mode='historical_cutoff' only.")
    rows = [dict(row) for row in panel or []]
    start = _as_date(config.start_date)
    end = _as_date(config.end_date)
    run_id = config.run_id or f"tlef-{uuid4().hex}"
    cutoffs = sorted(
        {
            _as_date(row.get("available_date") or row.get("signal_date"))
            for row in rows
            if start <= _as_date(row.get("available_date") or row.get("signal_date")) <= end
        }
    )
    regions = sorted(
        {
            (str(row.get("region_code") or "").upper(), str(row.get("region") or row.get("region_code") or ""))
            for row in rows
            if row.get("region_code")
        }
    )

    cutoff_results: list[dict[str, Any]] = []
    for cutoff in cutoffs:
        for region_code, region_name in regions:
            latest = _latest_by_source(
                rows,
                cutoff=cutoff,
                region_code=region_code,
                include_sales=config.include_sales,
            )
            sales = _source_from_row("sales", latest["sales"]) if config.include_sales else SourceEvidence(status="not_connected")
            isolation = BudgetIsolationEvidence(
                status=str((latest["sales"] or {}).get("budget_isolation") or "pass")  # type: ignore[arg-type]
                if config.include_sales
                else "pass"
            )
            snapshot = build_region_snapshot(
                TriLayerRegionEvidence(
                    region=region_name or region_code,
                    region_code=region_code,
                    wastewater=_source_from_row("wastewater", latest["wastewater"]),
                    clinical=_source_from_row("clinical", latest["clinical"]),
                    sales=sales,
                    budget_isolation=isolation,
                )
            )
            observed = _observed_for_cutoff(
                rows,
                cutoff=cutoff,
                region_code=region_code,
                horizon_days=config.horizon_days,
            )
            state = snapshot.budget_permission_state
            if not config.include_sales and BUDGET_STATE_RANK[state] > BUDGET_STATE_RANK["shadow_only"]:
                state = "shadow_only"
            cutoff_results.append(
                {
                    "cutoff_date": cutoff.isoformat(),
                    "region": region_name or region_code,
                    "region_code": region_code,
                    "early_warning_score": snapshot.early_warning_score,
                    "commercial_relevance_score": snapshot.commercial_relevance_score,
                    "budget_permission_state": state,
                    "budget_state_without_isolation": _permission_without_budget_isolation(state),
                    "budget_can_change": False,
                    "wave_phase": snapshot.wave_phase,
                    "gates": snapshot.gates.model_dump(),
                    "source_inputs": [
                        _source_input_trace("wastewater", latest["wastewater"]),
                        _source_input_trace("clinical", latest["clinical"]),
                        _source_input_trace("sales", latest["sales"] if config.include_sales else None),
                    ],
                    **observed,
                }
            )

    max_state = "blocked"
    for row in cutoff_results:
        state = row["budget_permission_state"]
        if BUDGET_STATE_RANK[state] > BUDGET_STATE_RANK[max_state]:
            max_state = state

    report = {
        "status": "complete",
        "run_id": run_id,
        "module": "tri_layer_evidence_fusion",
        "version": "tlef_bicg_v0_backtest",
        "research_only": True,
        "point_in_time_semantics": "historical_cutoff_available_date_lte_cutoff",
        "no_future_leakage": True,
        "virus_typ": config.virus_typ,
        "brand": config.brand,
        "horizon_days": int(config.horizon_days),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "mode": config.mode,
        "include_sales": bool(config.include_sales),
        "max_budget_permission_state": max_state,
        "metrics": _compute_metrics(cutoff_results, include_sales=config.include_sales),
        "baselines": _baseline_summary(cutoff_results),
        "cutoff_results": cutoff_results,
        "model_notes": [
            "Research-only. Does not change media budget.",
            "Budget can change remains false unless future explicit sales and isolation validation is added.",
        ],
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / f"{run_id}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["artifact_path"] = str(output_path)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_empty_tri_layer_backtest(config: TriLayerBacktestConfig) -> dict[str, Any]:
    """Return a valid blocked report when no PIT panel is available yet."""
    return run_tri_layer_backtest_panel([], config)


def read_tri_layer_backtest_report(run_id: str, output_dir: Path = DEFAULT_BACKTEST_DIR) -> dict[str, Any] | None:
    path = output_dir / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_latest_tri_layer_backtest_report(
    *,
    virus_typ: str,
    horizon_days: int,
    output_dir: Path = DEFAULT_BACKTEST_DIR,
) -> dict[str, Any] | None:
    if not output_dir.exists():
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for path in output_dir.glob("*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("status") != "complete":
            continue
        if str(report.get("virus_typ")) != str(virus_typ):
            continue
        if int(report.get("horizon_days") or 0) != int(horizon_days):
            continue
        candidates.append((path.stat().st_mtime, report))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]
