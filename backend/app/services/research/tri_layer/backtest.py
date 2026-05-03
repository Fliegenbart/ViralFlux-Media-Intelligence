"""Research-only TLEF-BICG backtest runner.

This module is deliberately isolated from production readiness, media
allocation and budget services. It evaluates historical cutoffs and writes a
JSON report for research review only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from app.services.media.cockpit.constants import BUNDESLAND_NAMES
from app.services.research.tri_layer.clinical_evidence import build_clinical_evidence_by_region
from app.services.research.tri_layer.observation_panel import build_tri_layer_observation_panel
from app.services.research.tri_layer.schema import (
    BudgetIsolationEvidence,
    SourceEvidence,
    TriLayerRegionEvidence,
)
from app.services.research.tri_layer.service import build_region_snapshot
from app.services.research.tri_layer.source_evidence_builder import build_source_evidence_from_panel


def _resolve_default_backtest_dir(*, base_dir: Path | None = None) -> Path:
    configured = os.getenv("TRI_LAYER_BACKTEST_DIR")
    if configured:
        return Path(configured).expanduser()
    return (base_dir or Path.cwd()) / "data" / "processed" / "tri_layer_backtests"


DEFAULT_BACKTEST_DIR = _resolve_default_backtest_dir()

BUDGET_STATE_RANK = {
    "blocked": 0,
    "calibration_window": 1,
    "shadow_only": 2,
    "limited": 3,
    "approved": 4,
}

MODEL_NAMES = [
    "persistence",
    "clinical_only",
    "wastewater_only",
    "wastewater_plus_clinical",
    "forecast_proxy_only",
    "tri_layer_epi_no_sales",
    "full_epi_no_sales",
]
CLINICAL_PANEL_SOURCES = {"survstat", "notaufnahme", "are", "grippeweb"}
MAX_STATE_WITHOUT_SALES = "shadow_only"
EARLY_WARNING_PROBABILITY_THRESHOLD = 0.35


@dataclass(frozen=True)
class TriLayerBacktestConfig:
    virus_typ: str = "Influenza A"
    brand: str = "gelo"
    horizon_days: int = 7
    start_date: str = "2024-10-01"
    end_date: str = "2026-04-30"
    mode: str = "historical_cutoff"
    include_sales: bool = False
    run_challenger_models: bool = False
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


def _clamp01(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


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
        "forecast_proxy": None,
        "sales": None,
    }
    for row in rows:
        source = str(row.get("source") or "").strip().lower()
        if source in {"survstat", "notaufnahme", "are", "grippeweb"}:
            source = "clinical"
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
            "available_at": None,
            "available_date": None,
            "signal_date": None,
            "signal": None,
            "status": "not_connected",
        }
    available = _iso(row.get("available_date") or row.get("available_at") or row.get("signal_date"))
    return {
        "source": source,
        "available_at": available,
        "available_date": available,
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
        available_date = _as_date(row.get("available_date") or row.get("available_at") or signal_date)
        outcome_date = max(signal_date, available_date)
        if cutoff.toordinal() < outcome_date.toordinal() <= end_ordinal:
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

    early_rows = [row for row in cutoff_results if (row.get("early_warning_score") or 0) >= EARLY_WARNING_PROBABILITY_THRESHOLD * 100.0]
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
        "phase_macro_f1": _phase_macro_f1(cutoff_results, model_name="tri_layer_epi_no_sales"),
        "precision_at_top3": _precision_at_top_k(cutoff_results, model_name="tri_layer_epi_no_sales", k=3),
        "recall_at_top3": _recall_at_top_k(cutoff_results, model_name="tri_layer_epi_no_sales", k=3),
        "pr_auc": _average_precision(
            [
                (
                    _safe_float((row.get("model_predictions") or {}).get("tri_layer_epi_no_sales", {}).get("onset_probability")),
                    bool(row.get("observed_onset")),
                )
                for row in cutoff_results
            ]
        ),
        "brier_score": _brier_score(
            [
                (
                    _safe_float((row.get("model_predictions") or {}).get("tri_layer_epi_no_sales", {}).get("onset_probability")),
                    bool(row.get("observed_onset")),
                )
                for row in cutoff_results
            ]
        ),
        "ece": _expected_calibration_error(
            [
                (
                    _safe_float((row.get("model_predictions") or {}).get("tri_layer_epi_no_sales", {}).get("onset_probability")),
                    bool(row.get("observed_onset")),
                )
                for row in cutoff_results
            ]
        ),
        "lead_lag_accuracy": None,
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


def _empty_model_metrics() -> dict[str, Any]:
    return {
        "n": 0,
        "positives": 0,
        "onset_detection_rate": None,
        "onset_detection_gain": None,
        "peak_lead_time": None,
        "false_early_warning_rate": None,
        "phase_accuracy": None,
        "phase_macro_f1": None,
        "precision_at_top3": None,
        "recall_at_top3": None,
        "pr_auc": None,
        "brier_score": None,
        "ece": None,
        "calibration_error": None,
        "lead_lag_accuracy": None,
    }


def _score_label_pairs(cutoff_results: list[dict[str, Any]], *, model_name: str) -> list[tuple[float | None, bool]]:
    return [
        (
            _safe_float((row.get("model_predictions") or {}).get(model_name, {}).get("onset_probability")),
            bool(row.get("observed_onset")),
        )
        for row in cutoff_results
    ]


def _brier_score(pairs: list[tuple[float | None, bool]]) -> float | None:
    usable = [(score, label) for score, label in pairs if score is not None]
    if not usable:
        return None
    return round(sum((float(score) - (1.0 if label else 0.0)) ** 2 for score, label in usable) / len(usable), 6)


def _calibration_error(pairs: list[tuple[float | None, bool]]) -> float | None:
    usable = [(score, label) for score, label in pairs if score is not None]
    if not usable:
        return None
    return round(sum(abs(float(score) - (1.0 if label else 0.0)) for score, label in usable) / len(usable), 6)


def _expected_calibration_error(pairs: list[tuple[float | None, bool]], *, bins: int = 5) -> float | None:
    usable = [(float(score), bool(label)) for score, label in pairs if score is not None]
    if not usable:
        return None
    total = len(usable)
    ece = 0.0
    for index in range(int(bins)):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            (score, label)
            for score, label in usable
            if (lower <= score < upper) or (index == bins - 1 and score == 1.0)
        ]
        if not bucket:
            continue
        confidence = sum(score for score, _ in bucket) / len(bucket)
        accuracy = sum(1.0 if label else 0.0 for _, label in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(confidence - accuracy)
    return round(ece, 6)


def _average_precision(pairs: list[tuple[float | None, bool]]) -> float | None:
    usable = [(float(score), bool(label)) for score, label in pairs if score is not None]
    positives = sum(1 for _, label in usable if label)
    negatives = sum(1 for _, label in usable if not label)
    if positives == 0 or negatives == 0:
        return None
    ranked = sorted(usable, key=lambda item: item[0], reverse=True)
    hits = 0
    precision_sum = 0.0
    for rank, (_, label) in enumerate(ranked, start=1):
        if not label:
            continue
        hits += 1
        precision_sum += hits / rank
    return round(precision_sum / positives, 6)


def _phase_macro_f1(cutoff_results: list[dict[str, Any]], *, model_name: str) -> float | None:
    rows = [
        (
            str((row.get("model_predictions") or {}).get(model_name, {}).get("predicted_phase") or "unknown"),
            str(row.get("observed_phase") or "unknown"),
        )
        for row in cutoff_results
        if str(row.get("observed_phase") or "unknown") != "unknown"
    ]
    labels = sorted({observed for _, observed in rows if observed != "unknown"})
    if len(rows) < 2 or len(labels) < 2:
        return None
    scores: list[float] = []
    for label in labels:
        tp = sum(1 for predicted, observed in rows if predicted == label and observed == label)
        fp = sum(1 for predicted, observed in rows if predicted == label and observed != label)
        fn = sum(1 for predicted, observed in rows if predicted != label and observed == label)
        if tp == 0 and fp == 0 and fn == 0:
            continue
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        scores.append(0.0 if precision + recall <= 0 else 2 * precision * recall / (precision + recall))
    return round(sum(scores) / len(scores), 6) if scores else None


def _phase_accuracy_for_model(cutoff_results: list[dict[str, Any]], *, model_name: str) -> float | None:
    rows = [
        row for row in cutoff_results
        if str(row.get("observed_phase") or "unknown") != "unknown"
        and (row.get("model_predictions") or {}).get(model_name, {}).get("predicted_phase") is not None
    ]
    if not rows:
        return None
    hits = sum(
        1
        for row in rows
        if str((row.get("model_predictions") or {}).get(model_name, {}).get("predicted_phase")) == str(row.get("observed_phase"))
    )
    return round(hits / len(rows), 6)


def _top_k_rows(rows: list[dict[str, Any]], *, model_name: str, k: int) -> list[dict[str, Any]]:
    scored = [
        row for row in rows
        if _safe_float((row.get("model_predictions") or {}).get(model_name, {}).get("onset_probability")) is not None
    ]
    return sorted(
        scored,
        key=lambda row: float((row.get("model_predictions") or {}).get(model_name, {}).get("onset_probability") or 0.0),
        reverse=True,
    )[:k]


def _precision_at_top_k(cutoff_results: list[dict[str, Any]], *, model_name: str, k: int) -> float | None:
    values: list[float] = []
    for cutoff in sorted({row["cutoff_date"] for row in cutoff_results}):
        rows = [row for row in cutoff_results if row["cutoff_date"] == cutoff]
        top = _top_k_rows(rows, model_name=model_name, k=k)
        if not top:
            continue
        values.append(sum(1 for row in top if row.get("observed_onset")) / len(top))
    return round(sum(values) / len(values), 6) if values else None


def _recall_at_top_k(cutoff_results: list[dict[str, Any]], *, model_name: str, k: int) -> float | None:
    values: list[float] = []
    for cutoff in sorted({row["cutoff_date"] for row in cutoff_results}):
        rows = [row for row in cutoff_results if row["cutoff_date"] == cutoff]
        positives = [row for row in rows if row.get("observed_onset")]
        if not positives:
            continue
        top = _top_k_rows(rows, model_name=model_name, k=k)
        values.append(sum(1 for row in top if row.get("observed_onset")) / len(positives))
    return round(sum(values) / len(values), 6) if values else None


def _model_metrics(cutoff_results: list[dict[str, Any]], *, model_name: str) -> dict[str, Any]:
    pairs = _score_label_pairs(cutoff_results, model_name=model_name)
    usable = [(score, label) for score, label in pairs if score is not None]
    if not usable:
        return _empty_model_metrics()
    positives = sum(1 for _, label in usable if label)
    predicted_positive = [(score, label) for score, label in usable if float(score) >= EARLY_WARNING_PROBABILITY_THRESHOLD]
    true_positive = [(score, label) for score, label in predicted_positive if label]
    false_positive = [(score, label) for score, label in predicted_positive if not label]
    lead_times: list[int] = []
    for row in cutoff_results:
        score = _safe_float((row.get("model_predictions") or {}).get(model_name, {}).get("onset_probability"))
        if score is None or score < 0.5 or not row.get("observed_peak_date"):
            continue
        lead_times.append(_as_date(row["observed_peak_date"]).toordinal() - _as_date(row["cutoff_date"]).toordinal())
    return {
        "n": len(usable),
        "positives": positives,
        "onset_detection_rate": round(len(true_positive) / positives, 6) if positives else None,
        "onset_detection_gain": None,
        "peak_lead_time": round(sum(lead_times) / len(lead_times), 6) if lead_times else None,
        "false_early_warning_rate": round(len(false_positive) / len(predicted_positive), 6) if predicted_positive else None,
        "phase_accuracy": _phase_accuracy_for_model(cutoff_results, model_name=model_name),
        "phase_macro_f1": _phase_macro_f1(cutoff_results, model_name=model_name),
        "precision_at_top3": _precision_at_top_k(cutoff_results, model_name=model_name, k=3),
        "recall_at_top3": _recall_at_top_k(cutoff_results, model_name=model_name, k=3),
        "pr_auc": _average_precision(pairs),
        "brier_score": _brier_score(pairs),
        "ece": _expected_calibration_error(pairs),
        "calibration_error": _calibration_error(pairs),
        "lead_lag_accuracy": None,
    }


def _source_availability_from_rows(rows: list[Mapping[str, Any]], *, include_sales: bool) -> dict[str, Any]:
    counts = {
        "wastewater": 0,
        "survstat": 0,
        "notaufnahme": 0,
        "are": 0,
        "grippeweb": 0,
        "forecast_proxy": 0,
        "sales": 0,
    }
    for row in rows:
        source = str(row.get("source") or "").strip().lower()
        if source == "clinical":
            source = "survstat"
        if source in counts:
            counts[source] += 1
    out: dict[str, Any] = {}
    for source, count in counts.items():
        if source == "sales":
            out[source] = {
                "status": "connected" if include_sales and count > 0 else "not_connected",
                "rows": count,
            }
        else:
            out[source] = {
                "status": "connected" if count > 0 else "not_connected",
                "rows": count,
            }
    return out


def _source_availability_from_panel(panel: pd.DataFrame | None, *, include_sales: bool, sales_rows: int = 0) -> dict[str, Any]:
    if panel is None or panel.empty:
        return _source_availability_from_rows([], include_sales=include_sales) | {
            "sales": {"status": "connected" if include_sales and sales_rows > 0 else "not_connected", "rows": sales_rows}
        }
    rows = [{"source": str(source)} for source in panel["source"].dropna().tolist()]
    availability = _source_availability_from_rows(rows, include_sales=include_sales)
    availability["sales"] = {
        "status": "connected" if include_sales and sales_rows > 0 else "not_connected",
        "rows": int(sales_rows),
    }
    return availability


def _incremental_value(models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def delta(metric: str, left: str, right: str, *, lower_is_better: bool = False) -> float | None:
        left_value = _safe_float(models.get(left, {}).get(metric))
        right_value = _safe_float(models.get(right, {}).get(metric))
        if left_value is None or right_value is None:
            return None
        value = left_value - right_value
        if lower_is_better:
            value = right_value - left_value
        return round(value, 6)

    return {
        "wastewater_vs_clinical_only": {
            "onset_detection_rate_delta": delta("onset_detection_rate", "wastewater_plus_clinical", "clinical_only"),
            "false_early_warning_rate_delta": delta("false_early_warning_rate", "wastewater_plus_clinical", "clinical_only"),
            "brier_score_delta": delta("brier_score", "wastewater_plus_clinical", "clinical_only", lower_is_better=True),
        },
        "tri_layer_vs_persistence": {
            "onset_detection_rate_delta": delta("onset_detection_rate", "tri_layer_epi_no_sales", "persistence"),
            "brier_score_delta": delta("brier_score", "tri_layer_epi_no_sales", "persistence", lower_is_better=True),
        },
        "forecast_proxy_vs_raw_tri_layer": {
            "onset_detection_rate_delta": delta("onset_detection_rate", "forecast_proxy_only", "tri_layer_epi_no_sales"),
            "brier_score_delta": delta("brier_score", "forecast_proxy_only", "tri_layer_epi_no_sales", lower_is_better=True),
            "status": (
                "not_evaluated"
                if models.get("forecast_proxy_only", {}).get("n", 0) == 0
                else "evaluated"
            ),
        },
    }


def _claim_readiness(models: dict[str, dict[str, Any]], incremental: dict[str, Any], *, sales_connected: bool) -> dict[str, str]:
    wastewater_rate = _safe_float(models.get("wastewater_plus_clinical", {}).get("onset_detection_rate"))
    clinical_rate = _safe_float(models.get("clinical_only", {}).get("onset_detection_rate")) or 0.0
    wastewater_false_rate = _safe_float(models.get("wastewater_plus_clinical", {}).get("false_early_warning_rate"))
    clinical_false_rate = _safe_float(models.get("clinical_only", {}).get("false_early_warning_rate"))
    tri_layer_gain = _safe_float(incremental["tri_layer_vs_persistence"].get("onset_detection_rate_delta"))
    tri_layer_brier_gain = _safe_float(incremental["tri_layer_vs_persistence"].get("brier_score_delta"))
    earlier = (
        "pass"
        if wastewater_rate is not None
        and wastewater_rate > clinical_rate
        and (clinical_false_rate is None or wastewater_false_rate is None or wastewater_false_rate <= clinical_false_rate + 0.05)
        else "fail"
    )
    better = "pass" if (tri_layer_gain is not None and tri_layer_gain > 0.0) or (tri_layer_brier_gain is not None and tri_layer_brier_gain > 0.0) else "fail"
    return {
        "earlier_than_clinical": earlier,
        "better_than_persistence": better,
        "commercially_validated": "pass" if sales_connected else "fail",
        "budget_ready": "pass" if sales_connected else "fail",
    }


def _claims_from_readiness(readiness: dict[str, str]) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    forbidden: list[str] = []
    if readiness.get("earlier_than_clinical") == "pass":
        allowed.append("Earlier epidemiological warning in this backtest window.")
    else:
        forbidden.append("Abwasser improves forecast.")
    if readiness.get("commercially_validated") != "pass":
        forbidden.append("Commercial lift validated.")
    if readiness.get("budget_ready") != "pass":
        forbidden.extend(["Budget optimization validated.", "ROI improvement proven."])
    return allowed, forbidden


def _scientific_models(cutoff_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    models = {name: _model_metrics(cutoff_results, model_name=name) for name in MODEL_NAMES}
    persistence_rate = _safe_float(models["persistence"].get("onset_detection_rate"))
    for name, metrics in models.items():
        rate = _safe_float(metrics.get("onset_detection_rate"))
        metrics["onset_detection_gain"] = (
            round(rate - persistence_rate, 6)
            if rate is not None and persistence_rate is not None
            else None
        )
    return models


def _model_prediction(snapshot, *, source_connected: bool) -> dict[str, Any]:
    probability = None
    if source_connected and snapshot.early_warning_score is not None:
        probability = _clamp01(float(snapshot.early_warning_score) / 100.0)
    return {
        "onset_probability": probability,
        "predicted_phase": snapshot.wave_phase if source_connected else "unknown",
        "budget_permission_state": snapshot.budget_permission_state,
    }


def _build_snapshot_for_sources(
    *,
    region: str,
    region_code: str,
    wastewater: SourceEvidence | None = None,
    clinical: SourceEvidence | None = None,
    sales: SourceEvidence | None = None,
    observation_panel: Any | None = None,
    virus_typ: str | None = None,
    cutoff: date | datetime | None = None,
):
    return build_region_snapshot(
        TriLayerRegionEvidence(
            region=region,
            region_code=region_code,
            wastewater=wastewater or SourceEvidence(),
            clinical=clinical or SourceEvidence(),
            sales=sales or SourceEvidence(status="not_connected"),
            budget_isolation=BudgetIsolationEvidence(status="pass"),
        ),
        observation_panel=observation_panel,
        virus_typ=virus_typ,
        cutoff=cutoff,
    )


def _model_predictions_for_evidence(
    *,
    region: str,
    region_code: str,
    wastewater: SourceEvidence,
    clinical: SourceEvidence,
    forecast_proxy: SourceEvidence,
    sales: SourceEvidence,
    persistence_probability: float | None,
    persistence_phase: str,
    observation_panel: Any | None = None,
    virus_typ: str | None = None,
    cutoff: date | datetime | None = None,
) -> dict[str, dict[str, Any]]:
    snapshots = {
        "clinical_only": _build_snapshot_for_sources(
            region=region,
            region_code=region_code,
            clinical=clinical,
            observation_panel=observation_panel,
            virus_typ=virus_typ,
            cutoff=cutoff,
        ),
        "wastewater_only": _build_snapshot_for_sources(
            region=region,
            region_code=region_code,
            wastewater=wastewater,
            observation_panel=observation_panel,
            virus_typ=virus_typ,
            cutoff=cutoff,
        ),
        "wastewater_plus_clinical": _build_snapshot_for_sources(
            region=region,
            region_code=region_code,
            wastewater=wastewater,
            clinical=clinical,
            observation_panel=observation_panel,
            virus_typ=virus_typ,
            cutoff=cutoff,
        ),
        "forecast_proxy_only": _build_snapshot_for_sources(
            region=region,
            region_code=region_code,
            clinical=forecast_proxy,
            observation_panel=observation_panel,
            virus_typ=virus_typ,
            cutoff=cutoff,
        ),
        "tri_layer_epi_no_sales": _build_snapshot_for_sources(
            region=region,
            region_code=region_code,
            wastewater=wastewater,
            clinical=clinical,
            sales=sales,
            observation_panel=observation_panel,
            virus_typ=virus_typ,
            cutoff=cutoff,
        ),
    }
    predictions = {
        "persistence": {
            "onset_probability": persistence_probability,
            "predicted_phase": persistence_phase,
            "budget_permission_state": "blocked",
        },
        "clinical_only": _model_prediction(snapshots["clinical_only"], source_connected=clinical.status != "not_connected"),
        "wastewater_only": _model_prediction(snapshots["wastewater_only"], source_connected=wastewater.status != "not_connected"),
        "wastewater_plus_clinical": _model_prediction(
            snapshots["wastewater_plus_clinical"],
            source_connected=wastewater.status != "not_connected" or clinical.status != "not_connected",
        ),
        "forecast_proxy_only": _model_prediction(snapshots["forecast_proxy_only"], source_connected=forecast_proxy.status != "not_connected"),
        "tri_layer_epi_no_sales": _model_prediction(
            snapshots["tri_layer_epi_no_sales"],
            source_connected=wastewater.status != "not_connected" or clinical.status != "not_connected",
        ),
    }
    predictions["full_epi_no_sales"] = dict(predictions["tri_layer_epi_no_sales"])
    return predictions


def _finalize_report(
    *,
    run_id: str,
    config: TriLayerBacktestConfig,
    start: date,
    end: date,
    cutoff_results: list[dict[str, Any]],
    source_availability: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    models = _scientific_models(cutoff_results)
    incremental = _incremental_value(models)
    if config.run_challenger_models:
        from app.services.research.tri_layer.challenger_models import fit_tri_layer_challenger_models

        challenger_models = fit_tri_layer_challenger_models(cutoff_results)
    else:
        challenger_models = {
            "status": "disabled",
            "reason": "run_challenger_models=false",
            "runtime": {"engine": "xgboost", "device": "cpu", "gpu_opt_in": False},
            "models": {},
        }
    sales_connected = str((source_availability.get("sales") or {}).get("status")) == "connected"
    readiness = _claim_readiness(models, incremental, sales_connected=sales_connected)
    allowed_claims, forbidden_claims = _claims_from_readiness(readiness)

    max_state = "blocked"
    for row in cutoff_results:
        state = row["budget_permission_state"]
        if BUDGET_STATE_RANK[state] > BUDGET_STATE_RANK[max_state]:
            max_state = state
    if not sales_connected and BUDGET_STATE_RANK[max_state] > BUDGET_STATE_RANK[MAX_STATE_WITHOUT_SALES]:
        max_state = MAX_STATE_WITHOUT_SALES

    unique_cutoffs = sorted({row["cutoff_date"] for row in cutoff_results})
    unique_regions = sorted({row["region_code"] for row in cutoff_results})
    report = {
        "status": "complete",
        "run_id": run_id,
        "module": "tri_layer_evidence_fusion",
        "version": "tlef_bicg_v0_backtest",
        "research_only": True,
        "point_in_time_semantics": "historical_cutoff_available_at_lte_cutoff",
        "no_future_leakage": True,
        "virus_typ": config.virus_typ,
        "brand": config.brand,
        "horizon_days": int(config.horizon_days),
        "date_range": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "cutoffs": len(unique_cutoffs),
        "regions": len(unique_regions),
        "mode": config.mode,
        "include_sales": bool(config.include_sales),
        "run_challenger_models": bool(config.run_challenger_models),
        "source_availability": source_availability,
        "models": models,
        "challenger_models": challenger_models,
        "source_ablation": models,
        "incremental_value": incremental,
        "claim_readiness": readiness,
        "allowed_claims": allowed_claims,
        "forbidden_claims": forbidden_claims,
        "max_budget_permission_state": max_state,
        "metrics": {
            **_compute_metrics(cutoff_results, include_sales=config.include_sales),
            **models["tri_layer_epi_no_sales"],
            "number_of_cutoffs": len(unique_cutoffs),
            "number_of_regions": len(unique_regions),
        },
        "baselines": _baseline_summary(cutoff_results),
        "cutoff_results": cutoff_results,
        "model_notes": [
            "Research-only. Does not change media budget.",
            "Budget can change remains false unless future explicit sales and isolation validation is added.",
        ],
        "warnings": warnings or [],
    }
    if not sales_connected:
        report["metrics"]["sales_lift_predictiveness"] = None
        report["metrics"]["budget_regret_reduction"] = None
    config.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = config.output_dir / f"{run_id}.json"
    report["artifact_path"] = str(output_path)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


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
    previous_outcome_by_region: dict[str, dict[str, Any]] = {}
    for cutoff in cutoffs:
        for region_code, region_name in regions:
            latest = _latest_by_source(
                rows,
                cutoff=cutoff,
                region_code=region_code,
                include_sales=config.include_sales,
            )
            sales = _source_from_row("sales", latest["sales"]) if config.include_sales else SourceEvidence(status="not_connected")
            wastewater = _source_from_row("wastewater", latest["wastewater"])
            clinical = _source_from_row("clinical", latest["clinical"])
            forecast_proxy = _source_from_row("forecast_proxy", latest["forecast_proxy"])
            snapshot = build_region_snapshot(
                TriLayerRegionEvidence(
                    region=region_name or region_code,
                    region_code=region_code,
                    wastewater=wastewater,
                    clinical=clinical,
                    sales=sales,
                    budget_isolation=BudgetIsolationEvidence(status="pass"),
                )
            )
            observed = _observed_for_cutoff(
                rows,
                cutoff=cutoff,
                region_code=region_code,
                horizon_days=config.horizon_days,
            )
            previous = previous_outcome_by_region.get(region_code)
            persistence_probability = None
            persistence_phase = "unknown"
            if previous is not None:
                persistence_probability = 1.0 if previous.get("observed_onset") else 0.0
                persistence_phase = str(previous.get("observed_phase") or "unknown")
            model_predictions = _model_predictions_for_evidence(
                region=region_name or region_code,
                region_code=region_code,
                wastewater=wastewater,
                clinical=clinical,
                forecast_proxy=forecast_proxy,
                sales=sales,
                persistence_probability=persistence_probability,
                persistence_phase=persistence_phase,
                virus_typ=config.virus_typ,
                cutoff=cutoff,
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
                    "predicted_onset_probability": model_predictions["tri_layer_epi_no_sales"]["onset_probability"],
                    "predicted_phase": model_predictions["tri_layer_epi_no_sales"]["predicted_phase"],
                    "model_predictions": model_predictions,
                    "source_inputs": [
                        _source_input_trace("wastewater", latest["wastewater"]),
                        _source_input_trace("clinical", latest["clinical"]),
                        _source_input_trace("forecast_proxy", latest["forecast_proxy"]),
                        _source_input_trace("sales", latest["sales"] if config.include_sales else None),
                    ],
                    "realized_onset": observed["observed_onset"],
                    "realized_phase": observed["observed_phase"],
                    "realized_peak_date": observed["observed_peak_date"],
                    **observed,
                }
            )
            previous_outcome_by_region[region_code] = observed

    warnings: list[str] = []
    if config.include_sales and not any(str(row.get("source") or "").lower() == "sales" for row in rows):
        warnings.append("include_sales=true requested, but no point-in-time sales panel is connected.")

    return _finalize_report(
        run_id=run_id,
        config=config,
        start=start,
        end=end,
        cutoff_results=cutoff_results,
        source_availability=_source_availability_from_rows(rows, include_sales=config.include_sales),
        warnings=warnings,
    )


def _rolling_weekly_cutoffs(start: date, end: date) -> list[date]:
    if end < start:
        return []
    cutoffs: list[date] = []
    current = start
    while current <= end:
        cutoffs.append(current)
        current += timedelta(days=7)
    return cutoffs or [start]


def _clinical_region_codes(panel: pd.DataFrame | None) -> list[str]:
    if panel is None or panel.empty:
        return []
    clinical = panel.loc[
        panel["source"].isin(CLINICAL_PANEL_SOURCES)
        & (panel["region_code"].astype(str).str.upper() != "DE")
    ]
    return sorted(str(value).upper() for value in clinical["region_code"].dropna().unique())


def _observed_from_panel(
    panel: pd.DataFrame | None,
    *,
    cutoff: date,
    region_code: str,
    horizon_days: int,
) -> dict[str, Any]:
    if panel is None or panel.empty:
        return {"observed_onset": False, "observed_phase": "unknown", "observed_peak_date": None}
    cutoff_ts = pd.Timestamp(cutoff)
    end_ts = cutoff_ts + pd.Timedelta(days=int(horizon_days))
    frame = panel.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    frame = frame.loc[
        frame["source"].isin(CLINICAL_PANEL_SOURCES)
        & (frame["region_code"].astype(str).str.upper() == str(region_code).upper())
        & (frame["signal_date"] > cutoff_ts)
        & (frame["signal_date"] <= end_ts)
    ].copy()
    if frame.empty:
        return {"observed_onset": False, "observed_phase": "unknown", "observed_peak_date": None}

    intensity = pd.to_numeric(frame.get("intensity"), errors="coerce")
    normalized = pd.to_numeric(frame.get("value_normalized"), errors="coerce")
    growth = pd.to_numeric(frame.get("growth_7d"), errors="coerce")
    max_intensity = float(intensity.max()) if intensity.notna().any() else None
    max_normalized = float(normalized.max()) if normalized.notna().any() else None
    max_growth = float(growth.max()) if growth.notna().any() else None
    observed_onset = bool(
        (max_intensity is not None and max_intensity >= 0.60)
        or (max_normalized is not None and max_normalized >= 0.25)
        or (max_growth is not None and max_growth >= 0.20)
    )
    if max_intensity is not None and max_intensity >= 0.78:
        phase = "peak"
    elif max_growth is not None and max_growth >= 0.30:
        phase = "acceleration"
    elif observed_onset:
        phase = "early_growth"
    else:
        phase = "baseline"
    peak_row = frame.assign(__intensity=intensity.fillna(0.0)).sort_values("__intensity").tail(1)
    peak_date = None
    if not peak_row.empty:
        peak_date = pd.Timestamp(peak_row.iloc[0]["signal_date"]).date().isoformat()
    return {"observed_onset": observed_onset, "observed_phase": phase, "observed_peak_date": peak_date}


def _panel_source_trace(panel: pd.DataFrame | None, *, source: str, region_code: str) -> dict[str, Any]:
    if panel is None or panel.empty:
        return _source_input_trace(source, None)
    sources = {"survstat", "notaufnahme", "are", "grippeweb"} if source == "clinical" else {source}
    frame = panel.loc[panel["source"].isin(sources)].copy()
    region = str(region_code or "").upper()
    exact = frame.loc[frame["region_code"].astype(str).str.upper() == region].copy()
    if not exact.empty:
        frame = exact
    else:
        frame = frame.loc[frame["region_code"].astype(str).str.upper() == "DE"].copy()
    if frame.empty:
        return _source_input_trace(source, None)
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce")
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    row = frame.sort_values(["available_at", "signal_date"]).iloc[-1]
    return {
        "source": source,
        "available_at": pd.Timestamp(row["available_at"]).date().isoformat() if pd.notna(row["available_at"]) else None,
        "available_date": pd.Timestamp(row["available_at"]).date().isoformat() if pd.notna(row["available_at"]) else None,
        "signal_date": pd.Timestamp(row["signal_date"]).date().isoformat() if pd.notna(row["signal_date"]) else None,
        "signal": _safe_float(row.get("intensity")),
        "status": "connected",
    }


def run_tri_layer_backtest_from_db(
    db: Session,
    config: TriLayerBacktestConfig,
) -> dict[str, Any]:
    """Run the real point-in-time historical-cutoff Tri-Layer backtest."""
    if config.mode != "historical_cutoff":
        raise ValueError("Tri-Layer backtest currently supports mode='historical_cutoff' only.")

    start = _as_date(config.start_date)
    end = _as_date(config.end_date)
    run_id = config.run_id or f"tlef-{uuid4().hex}"
    cutoffs = _rolling_weekly_cutoffs(start, end)
    label_cutoff = datetime.combine(end + timedelta(days=int(config.horizon_days) + 35), datetime.min.time())
    source_start = datetime.combine(start - timedelta(days=365), datetime.min.time())
    label_end = datetime.combine(end + timedelta(days=int(config.horizon_days)), datetime.min.time())

    try:
        label_panel = build_tri_layer_observation_panel(
            db,
            virus_typ=config.virus_typ,
            cutoff=label_cutoff,
            start_date=source_start,
            end_date=label_end,
            region_codes=None,
        )
    except Exception:
        label_panel = pd.DataFrame()

    regions = _clinical_region_codes(label_panel)
    cutoff_results: list[dict[str, Any]] = []
    previous_outcome_by_region: dict[str, dict[str, Any]] = {}
    for cutoff_date in cutoffs:
        cutoff_dt = datetime.combine(cutoff_date, datetime.min.time())
        try:
            panel = build_tri_layer_observation_panel(
                db,
                virus_typ=config.virus_typ,
                cutoff=cutoff_dt,
                start_date=source_start,
                end_date=cutoff_dt,
                region_codes=None,
            )
        except Exception:
            panel = pd.DataFrame()
        cutoff_regions = sorted(set(regions) | set(_clinical_region_codes(panel)))
        if not cutoff_regions:
            continue
        try:
            clinical_by_region = build_clinical_evidence_by_region(
                db,
                virus_typ=config.virus_typ,
                cutoff=cutoff_dt,
                region_codes=cutoff_regions,
            )
        except Exception:
            clinical_by_region = {}

        for region_code in cutoff_regions:
            region_name = BUNDESLAND_NAMES.get(region_code, region_code)
            wastewater = build_source_evidence_from_panel(
                panel,
                source="wastewater",
                region_code=region_code,
                virus_typ=config.virus_typ,
                cutoff=cutoff_dt,
                allow_national_fallback=True,
            ) if panel is not None and not panel.empty else SourceEvidence()
            clinical = clinical_by_region.get(region_code, SourceEvidence())
            sales = SourceEvidence(status="not_connected")
            previous = previous_outcome_by_region.get(region_code)
            persistence_probability = 1.0 if previous and previous.get("observed_onset") else (0.0 if previous else None)
            persistence_phase = str((previous or {}).get("observed_phase") or "unknown")
            model_predictions = _model_predictions_for_evidence(
                region=region_name,
                region_code=region_code,
                wastewater=wastewater,
                clinical=clinical,
                forecast_proxy=SourceEvidence(),
                sales=sales,
                persistence_probability=persistence_probability,
                persistence_phase=persistence_phase,
                observation_panel=panel,
                virus_typ=config.virus_typ,
                cutoff=cutoff_dt,
            )
            snapshot = _build_snapshot_for_sources(
                region=region_name,
                region_code=region_code,
                wastewater=wastewater,
                clinical=clinical,
                sales=sales,
                observation_panel=panel,
                virus_typ=config.virus_typ,
                cutoff=cutoff_dt,
            )
            observed = _observed_from_panel(
                label_panel,
                cutoff=cutoff_date,
                region_code=region_code,
                horizon_days=config.horizon_days,
            )
            state = snapshot.budget_permission_state
            if BUDGET_STATE_RANK[state] > BUDGET_STATE_RANK[MAX_STATE_WITHOUT_SALES]:
                state = MAX_STATE_WITHOUT_SALES
            cutoff_results.append(
                {
                    "cutoff_date": cutoff_date.isoformat(),
                    "region": region_name,
                    "region_code": region_code,
                    "early_warning_score": snapshot.early_warning_score,
                    "commercial_relevance_score": None,
                    "budget_permission_state": state,
                    "budget_state_without_isolation": _permission_without_budget_isolation(state),
                    "budget_can_change": False,
                    "wave_phase": snapshot.wave_phase,
                    "gates": snapshot.gates.model_dump(),
                    "predicted_onset_probability": model_predictions["tri_layer_epi_no_sales"]["onset_probability"],
                    "predicted_phase": model_predictions["tri_layer_epi_no_sales"]["predicted_phase"],
                    "model_predictions": model_predictions,
                    "source_inputs": [
                        _panel_source_trace(panel, source="wastewater", region_code=region_code),
                        _panel_source_trace(panel, source="clinical", region_code=region_code),
                        _source_input_trace("forecast_proxy", None),
                        _source_input_trace("sales", None),
                    ],
                    "realized_onset": observed["observed_onset"],
                    "realized_phase": observed["observed_phase"],
                    "realized_peak_date": observed["observed_peak_date"],
                    **observed,
                }
            )
            previous_outcome_by_region[region_code] = observed

    # Media outcome tables are not a point-in-time GELO sell-out sales panel.
    # Keep Sales explicitly disconnected until that real panel exists.
    sales_rows = 0
    warnings: list[str] = []
    if config.include_sales and sales_rows <= 0:
        warnings.append("include_sales=true requested, but no point-in-time sales panel is connected.")
    source_availability = _source_availability_from_panel(
        label_panel,
        include_sales=config.include_sales,
        sales_rows=sales_rows,
    )
    return _finalize_report(
        run_id=run_id,
        config=config,
        start=start,
        end=end,
        cutoff_results=cutoff_results,
        source_availability=source_availability,
        warnings=warnings,
    )


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
