"""Human-readable evaluation for virus wave backtests.

v1.3 stores the measurements. v1.4 turns them into a compact decision report:
which pathogens are good candidates for later simulation, which need review,
and which should not influence Forecast Quality or Viral Pressure yet.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from app.models.database import VirusWaveBacktestResult, VirusWaveBacktestRun
from app.services.media.cockpit.virus_wave_backtest import (
    BACKTEST_VERSION,
    MIN_SEASON_SPAN_DAYS,
    MIN_SEASON_SOURCE_POINTS,
    MODEL_EVIDENCE_WEIGHTED,
    MODEL_SURVSTAT_ONLY,
)


REPORT_VERSION = "virus-wave-backtest-evaluation-v1.7"
DEFAULT_REPORT_PATH = Path("/app/data/processed/virus_wave_backtest_evaluation_report.md")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return number


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _run_scope_mode(row: VirusWaveBacktestRun) -> str | None:
    if isinstance(row.parameters_json, Mapping):
        scope_mode = row.parameters_json.get("scope_mode")
        if scope_mode:
            return str(scope_mode)
    if isinstance(row.summary_json, Mapping):
        scope_mode = row.summary_json.get("scope_mode")
        if scope_mode:
            return str(scope_mode)
    return None


def _latest_successful_runs(
    db: Session,
    *,
    mode: str,
    scope_mode: str | None = None,
) -> list[VirusWaveBacktestRun]:
    rows = (
        db.query(VirusWaveBacktestRun)
        .filter(
            VirusWaveBacktestRun.status == "success",
            VirusWaveBacktestRun.mode == mode,
        )
        .order_by(VirusWaveBacktestRun.finished_at.desc(), VirusWaveBacktestRun.id.desc())
        .all()
    )
    latest_by_scope: dict[tuple[str, str, str], VirusWaveBacktestRun] = {}
    for row in rows:
        if scope_mode and _run_scope_mode(row) != scope_mode:
            continue
        source_status = row.parameters_json.get("source_status") if isinstance(row.parameters_json, Mapping) else {}
        if (
            isinstance(source_status, Mapping)
            and source_status.get("season_windowed")
            and (
                _safe_float(source_status.get("survstat_points")) < MIN_SEASON_SOURCE_POINTS
                or _safe_float(source_status.get("amelag_points")) < MIN_SEASON_SOURCE_POINTS
                or _safe_float(source_status.get("season_window_span_days"), -1.0) < MIN_SEASON_SPAN_DAYS
            )
        ):
            continue
        pathogen = str((row.pathogens or ["unknown"])[0])
        region = str((row.regions or ["DE"])[0])
        season = str((row.seasons or ["unseasoned"])[0])
        key = (pathogen, region, season)
        if key not in latest_by_scope:
            latest_by_scope[key] = row
    return list(latest_by_scope.values())


def _results_by_model(db: Session, run_id: int) -> dict[str, VirusWaveBacktestResult]:
    rows = db.query(VirusWaveBacktestResult).filter(VirusWaveBacktestResult.run_id == run_id).all()
    return {row.model_name: row for row in rows}


def _metric(row: VirusWaveBacktestResult | None, name: str) -> float | None:
    if row is None:
        return None
    value = getattr(row, name)
    return None if value is None else float(value)


def _delta(
    evidence: VirusWaveBacktestResult | None,
    baseline: VirusWaveBacktestResult | None,
    name: str,
) -> float | None:
    left = _metric(evidence, name)
    right = _metric(baseline, name)
    if left is None or right is None:
        return None
    return left - right


def _recommendation(
    *,
    evidence: VirusWaveBacktestResult | None,
    baseline: VirusWaveBacktestResult | None,
    warnings: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if evidence is None:
        return "no_go", ["evidence_model_missing"]
    if evidence.status != "ok":
        return "no_go", [f"evidence_model_status_{evidence.status}"]
    if baseline is None or baseline.status != "ok":
        return "review", ["survstat_baseline_missing_or_unstable"]

    onset_gain = _safe_float(evidence.onset_detection_gain_days)
    peak_gain = _safe_float(evidence.peak_detection_gain_days)
    phase_delta = _safe_float(_delta(evidence, baseline, "phase_accuracy"))
    false_warning = _safe_float(evidence.false_early_warning_rate)
    missed_wave = _safe_float(evidence.missed_wave_rate)

    if false_warning > 0.20:
        reasons.append("false_early_warning_rate_too_high")
    if missed_wave > 0.20:
        reasons.append("missed_wave_rate_too_high")
    if phase_delta < -0.10:
        reasons.append("phase_accuracy_worse_than_survstat_only")
    if onset_gain < -14:
        reasons.append("onset_later_than_survstat_only")
    if reasons:
        return "no_go", reasons

    has_timing_gain = onset_gain >= 7 or peak_gain >= 7
    stable_enough = phase_delta >= -0.05 and false_warning <= 0.05 and missed_wave <= 0.05
    anchor_warning_present = any(
        warning in warnings
        for warning in (
            "rsv_variant_scope_requires_review",
            "subtype_specific_amelag_vs_combined_clinical_anchor",
        )
    )
    if has_timing_gain and stable_enough and not anchor_warning_present:
        return "go_for_simulation", ["timing_gain_without_material_quality_penalty"]

    review_reasons = []
    if not has_timing_gain:
        review_reasons.append("timing_gain_not_clear_enough")
    if not stable_enough:
        review_reasons.append("quality_tradeoff_requires_review")
    if "rsv_variant_scope_requires_review" in warnings:
        review_reasons.append("rsv_mapping_must_be_confirmed_before_promotion")
    if "subtype_specific_amelag_vs_combined_clinical_anchor" in warnings:
        review_reasons.append("clinical_anchor_must_be_confirmed_before_promotion")
    return "review", review_reasons or ["manual_review_recommended"]


def _pathogen_report(db: Session, run: VirusWaveBacktestRun) -> dict[str, Any]:
    by_model = _results_by_model(db, run.id)
    baseline = by_model.get(MODEL_SURVSTAT_ONLY)
    evidence = by_model.get(MODEL_EVIDENCE_WEIGHTED)
    representative = evidence or baseline
    pathogen = str((run.pathogens or [representative.pathogen if representative else "unknown"])[0])
    canonical_pathogen = str((representative.canonical_pathogen if representative else pathogen) or pathogen)
    pathogen_variant = representative.pathogen_variant if representative else None
    region = str((run.regions or [representative.region_code if representative else "DE"])[0])
    season = str((run.seasons or [representative.season if representative else ""])[0]) if (run.seasons or representative) else None

    warnings: list[str] = []
    method_flags = run.parameters_json.get("method_flags") if isinstance(run.parameters_json, Mapping) else {}
    if isinstance(method_flags, Mapping):
        warnings.extend(str(warning) for warning in method_flags.get("warnings") or [])
    if canonical_pathogen == "RSV" and pathogen_variant:
        warnings.append("rsv_variant_scope_requires_review")
    if run.parameters_json and not bool(run.parameters_json.get("backtest_safe", False)):
        warnings.append("backtest_mode_not_historical_cutoff_safe")
    if not (run.summary_json or {}).get("budget_impact", {}).get("can_change_budget") is False:
        warnings.append("budget_isolation_not_explicit_in_snapshot")

    recommendation, reasons = _recommendation(evidence=evidence, baseline=baseline, warnings=warnings)

    metrics: dict[str, dict[str, Any]] = {}
    for model_name, row in by_model.items():
        metrics[model_name] = {
            "status": row.status,
            "onset_detection_gain_days": _round(row.onset_detection_gain_days),
            "peak_detection_gain_days": _round(row.peak_detection_gain_days),
            "phase_accuracy": _round(row.phase_accuracy),
            "false_early_warning_rate": _round(row.false_early_warning_rate),
            "missed_wave_rate": _round(row.missed_wave_rate),
            "false_post_peak_rate": _round(row.false_post_peak_rate),
            "lead_lag_stability": _round(row.lead_lag_stability),
            "mean_alignment_score": _round(row.mean_alignment_score),
            "mean_divergence_score": _round(row.mean_divergence_score),
            "confidence_brier_score": _round(row.confidence_brier_score),
        }

    comparison = {
        "model_name": MODEL_EVIDENCE_WEIGHTED,
        "baseline_model": MODEL_SURVSTAT_ONLY,
        "onset_gain_days": _metric(evidence, "onset_detection_gain_days"),
        "peak_gain_days": _metric(evidence, "peak_detection_gain_days"),
        "phase_accuracy_delta": _delta(evidence, baseline, "phase_accuracy"),
        "false_early_warning_delta": _delta(evidence, baseline, "false_early_warning_rate"),
        "missed_wave_delta": _delta(evidence, baseline, "missed_wave_rate"),
    }

    return {
        "pathogen": pathogen,
        "canonical_pathogen": canonical_pathogen,
        "pathogen_variant": pathogen_variant,
        "region_code": region,
        "season": season,
        "run_id": run.id,
        "run_key": run.run_key,
        "recommendation": recommendation,
        "recommendation_reasons": reasons,
        "method_flags": dict(method_flags) if isinstance(method_flags, Mapping) else {},
        "warnings": list(dict.fromkeys(warnings)),
        "comparison": comparison,
        "metrics": metrics,
    }


def _summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    def _label(row: Mapping[str, Any]) -> str:
        season = row.get("season")
        return f"{row['pathogen']} {season}" if season else str(row["pathogen"])

    return {
        "scope_count": len(items),
        "go_count": sum(1 for row in items if row.get("recommendation") == "go_for_simulation"),
        "review_count": sum(1 for row in items if row.get("recommendation") == "review"),
        "no_go_count": sum(1 for row in items if row.get("recommendation") == "no_go"),
        "go_scopes": [_label(row) for row in items if row.get("recommendation") == "go_for_simulation"],
        "review_scopes": [_label(row) for row in items if row.get("recommendation") == "review"],
        "no_go_scopes": [_label(row) for row in items if row.get("recommendation") == "no_go"],
    }


def build_virus_wave_backtest_evaluation_report(
    db: Session,
    *,
    mode: str = "historical_cutoff",
    scope_mode: str | None = None,
) -> dict[str, Any]:
    """Build a research-only report from latest persisted v1.7 backtests."""

    runs = _latest_successful_runs(db, mode=mode, scope_mode=scope_mode)
    generated_at = datetime.utcnow().replace(tzinfo=None).isoformat()
    if not runs:
        return {
            "schema": "virus_wave_backtest_evaluation_v1",
            "report_version": REPORT_VERSION,
            "status": "no_data",
            "mode": mode,
            "scope_mode": scope_mode,
            "backtest_safe": mode == "historical_cutoff",
            "generated_at": generated_at,
            "summary": {
                "scope_count": 0,
                "go_count": 0,
                "review_count": 0,
                "no_go_count": 0,
                "go_scopes": [],
                "review_scopes": [],
                "no_go_scopes": [],
            },
            "pathogen_reports": [],
            "budget_impact": {
                "mode": "diagnostic_only",
                "can_change_budget": False,
                "reason": "evaluation_report_research_only",
            },
            "limitations": ["no_successful_backtest_runs_found"],
        }

    pathogen_reports = sorted(
        [_pathogen_report(db, run) for run in runs],
        key=lambda row: (str(row["canonical_pathogen"]), str(row["pathogen"]), str(row.get("season"))),
    )
    return {
        "schema": "virus_wave_backtest_evaluation_v1",
        "report_version": REPORT_VERSION,
        "backtest_version": BACKTEST_VERSION,
        "status": "success",
        "mode": mode,
        "scope_mode": scope_mode,
        "backtest_safe": mode == "historical_cutoff",
        "generated_at": generated_at,
        "summary": _summary(pathogen_reports),
        "pathogen_reports": pathogen_reports,
        "budget_impact": {
            "mode": "diagnostic_only",
            "can_change_budget": False,
            "reason": "evaluation_report_research_only",
        },
        "promotion_gate": {
            "can_promote_to_forecast_quality": False,
            "can_promote_to_viral_pressure": False,
            "reason": "requires_human_review_and_separate_feature_flag",
        },
        "limitations": [
            "historical_cutoff_backtest_is_required_for_product_decisions",
            "recommendations_are_research_only",
            "legacy_subtype_scopes_require_mapping_review_before_promotion",
        ],
    }


def render_virus_wave_backtest_markdown(report: Mapping[str, Any]) -> str:
    """Render the evaluation report as a small operator-readable Markdown file."""

    lines = [
        "# Virus Wave Backtest Evaluation v1.7",
        "",
        f"status: {report.get('status')}",
        f"mode: {report.get('mode')}",
        f"scope_mode: {report.get('scope_mode') or 'all'}",
        f"backtest_safe: {str(bool(report.get('backtest_safe'))).lower()}",
        "evidence_mode: diagnostic_only",
        "budget_can_change: false",
        "",
        "## Summary",
        "",
    ]
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines.extend(
        [
            f"- scopes: {summary.get('scope_count', 0)}",
            f"- go_for_simulation: {summary.get('go_count', 0)}",
            f"- review: {summary.get('review_count', 0)}",
            f"- no_go: {summary.get('no_go_count', 0)}",
            "",
            "## Pathogens",
            "",
            "| Pathogen | Recommendation | Onset Gain | Peak Gain | Phase Delta | Warnings |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in report.get("pathogen_reports") or []:
        comparison = row.get("comparison") if isinstance(row.get("comparison"), Mapping) else {}
        warnings = ", ".join(row.get("warnings") or [])
        lines.append(
            "| {pathogen} | {recommendation} | {onset} | {peak} | {phase} | {warnings} |".format(
                pathogen=row.get("pathogen"),
                recommendation=row.get("recommendation"),
                onset=comparison.get("onset_gain_days"),
                peak=comparison.get("peak_gain_days"),
                phase=_round(comparison.get("phase_accuracy_delta")),
                warnings=warnings or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This report is diagnostic_only. It may identify candidates for later simulation, but it does not change Forecast Quality, Viral Pressure, media budgets, decision gates, or global_status.",
            "",
        ]
    )
    return "\n".join(lines)


def write_virus_wave_backtest_evaluation_report(
    db: Session,
    *,
    mode: str = "historical_cutoff",
    scope_mode: str | None = None,
    output_path: str | Path = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    """Build and write the Markdown report to disk."""

    report = build_virus_wave_backtest_evaluation_report(db, mode=mode, scope_mode=scope_mode)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_virus_wave_backtest_markdown(report), encoding="utf-8")
    return {"status": report["status"], "path": str(target), "report": report}
