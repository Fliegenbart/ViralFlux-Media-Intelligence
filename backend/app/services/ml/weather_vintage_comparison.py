"""Small end-to-end weather vintage comparison runner and report helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.models.database import WeatherData
from app.services.ml.regional_panel_utils import time_based_panel_splits
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.regional_trainer import RegionalModelTrainer
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
)

DEFAULT_WEATHER_VINTAGE_COMPARISON_VIRUS_TYPES = (
    "Influenza A",
    "SARS-CoV-2",
    "RSV A",
)
DEFAULT_WEATHER_VINTAGE_COMPARISON_HORIZONS = (3, 7)
DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_VIRUS_TYPES = (
    "Influenza A",
    "SARS-CoV-2",
)
DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_HORIZONS = (7,)
DEFAULT_WEATHER_VINTAGE_REVIEW_RUN_PURPOSES = ("scheduled_shadow",)
SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES = (
    "smoke",
    "manual_eval",
    "scheduled_shadow",
)
WEATHER_VINTAGE_MIN_TRAIN_COVERAGE = 0.5
WEATHER_VINTAGE_MIN_TEST_COVERAGE = 0.8
WEATHER_VINTAGE_TIME_BLOCK_DAYS = 90
WEATHER_VINTAGE_MIN_COMPARABLE_RUNS = 6
WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS = 36
WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE = 14
WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK = 3
WEATHER_VINTAGE_GATE_ORDER = {
    "NO_GO": 0,
    "WATCH": 1,
    "GO": 2,
}
WEATHER_VINTAGE_HEALTH_STATUS_ORDER = {
    "ok": 0,
    "warning": 1,
    "critical": 2,
}


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def normalize_weather_vintage_matrix(
    *,
    virus_types: list[str] | tuple[str, ...] | None,
    horizon_days_list: list[int] | tuple[int, ...] | None,
) -> tuple[list[str], list[int]]:
    selected_viruses = list(virus_types or DEFAULT_WEATHER_VINTAGE_COMPARISON_VIRUS_TYPES)
    selected_horizons = list(horizon_days_list or DEFAULT_WEATHER_VINTAGE_COMPARISON_HORIZONS)
    normalized_viruses = [
        virus_typ for virus_typ in selected_viruses if virus_typ in SUPPORTED_VIRUS_TYPES
    ]
    normalized_horizons = [
        int(horizon) for horizon in selected_horizons if int(horizon) in SUPPORTED_FORECAST_HORIZONS
    ]
    if not normalized_viruses:
        raise ValueError("No supported virus types selected for weather vintage comparison.")
    if not normalized_horizons:
        raise ValueError("No supported horizons selected for weather vintage comparison.")
    return normalized_viruses, normalized_horizons


def classify_weather_vintage_result(scope_payload: dict[str, Any]) -> str:
    if str(scope_payload.get("status") or "").lower() != "success":
        return str(scope_payload.get("status") or "unknown").lower() or "unknown"
    comparison = scope_payload.get("weather_vintage_comparison") or {}
    if str(comparison.get("comparison_status") or "").lower() != "ok":
        return str(comparison.get("comparison_status") or "degraded").lower()

    run_identity = (
        comparison.get("weather_vintage_run_identity_coverage", {})
        .get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, {})
    )
    if not bool(run_identity.get("run_identity_present")):
        return "insufficient_identity"

    deltas = comparison.get("legacy_vs_vintage_metric_delta") or {}
    wis_delta = float(deltas.get("relative_wis", deltas.get("wis", 0.0)) or 0.0)
    crps_delta = float(deltas.get("crps", 0.0) or 0.0)
    if wis_delta <= -0.005 and crps_delta <= -0.001:
        return "better"
    if wis_delta >= 0.005 and crps_delta >= 0.001:
        return "worse"
    if abs(wis_delta) < 0.005 and abs(crps_delta) < 0.001:
        return "neutral"
    return "mixed"


def scope_report_from_training_result(
    *,
    virus_typ: str,
    horizon_days: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    comparison = result.get("weather_vintage_comparison") or {}
    modes = comparison.get("modes") or {}
    legacy_mode = modes.get(WEATHER_FORECAST_VINTAGE_DISABLED) or {}
    vintage_mode = modes.get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1) or {}
    report = {
        "virus_typ": virus_typ,
        "horizon_days": int(horizon_days),
        "status": result.get("status"),
        "weather_forecast_vintage_mode": result.get("weather_forecast_vintage_mode"),
        "exogenous_feature_semantics_version": (
            legacy_mode.get("exogenous_feature_semantics_version")
            or vintage_mode.get("exogenous_feature_semantics_version")
            or result.get("exogenous_feature_semantics_version")
        ),
        "comparison_status": comparison.get("comparison_status"),
        "weather_vintage_comparison": comparison,
        "legacy_vs_vintage_metric_delta": comparison.get("legacy_vs_vintage_metric_delta") or {},
        "quality_gate_change": comparison.get("quality_gate_change") or {},
        "threshold_change": comparison.get("threshold_change"),
        "calibration_change": comparison.get("calibration_change") or {},
        "weather_vintage_run_identity_coverage": comparison.get("weather_vintage_run_identity_coverage") or {},
        "modes": {
            WEATHER_FORECAST_VINTAGE_DISABLED: legacy_mode,
            WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1: vintage_mode,
        },
    }
    report["verdict"] = classify_weather_vintage_result(report)
    return _json_safe(report)


def build_weather_vintage_report_summary(
    scope_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    verdict_counts: dict[str, int] = {}
    coverage_status_counts: dict[str, int] = {}
    for item in scope_reports:
        verdict = str(item.get("verdict") or "unknown")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        coverage_status = str(
            ((item.get("weather_vintage_backtest_coverage") or {}).get("coverage_status") or "unknown")
        )
        coverage_status_counts[coverage_status] = coverage_status_counts.get(coverage_status, 0) + 1
    return {
        "total_scopes": int(len(scope_reports)),
        "verdict_counts": verdict_counts,
        "coverage_status_counts": coverage_status_counts,
        "better_scopes": [
            f"{item['virus_typ']} h{item['horizon_days']}"
            for item in scope_reports
            if item.get("verdict") == "better"
        ],
        "worse_scopes": [
            f"{item['virus_typ']} h{item['horizon_days']}"
            for item in scope_reports
            if item.get("verdict") == "worse"
        ],
        "neutral_scopes": [
            f"{item['virus_typ']} h{item['horizon_days']}"
            for item in scope_reports
            if item.get("verdict") == "neutral"
        ],
        "coverage_insufficient_scopes": [
            f"{item['virus_typ']} h{item['horizon_days']}"
            for item in scope_reports
            if ((item.get("weather_vintage_backtest_coverage") or {}).get("insufficient_for_comparison"))
        ],
    }


def _gate_rank(value: Any) -> int:
    return WEATHER_VINTAGE_GATE_ORDER.get(str(value or "").upper(), -1)


def determine_weather_vintage_comparison_eligibility(
    scope_payload: dict[str, Any],
) -> str:
    if str(scope_payload.get("status") or "").lower() != "success":
        return "failed"
    if str(scope_payload.get("comparison_status") or "").lower() != "ok":
        return "failed"

    run_identity = (
        scope_payload.get("weather_vintage_run_identity_coverage", {})
        .get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, {})
    )
    backtest_coverage = scope_payload.get("weather_vintage_backtest_coverage") or {}
    if (not bool(run_identity.get("run_identity_present"))) or bool(
        backtest_coverage.get("insufficient_for_comparison")
    ):
        return "insufficient_identity"
    return "comparable"


def _extract_mode_snapshot(
    scope_payload: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    snapshot = ((scope_payload.get("modes") or {}).get(mode) or {}).copy()
    snapshot.setdefault("weather_forecast_vintage_mode", mode)
    return _json_safe(
        {
            "weather_forecast_vintage_mode": snapshot.get("weather_forecast_vintage_mode"),
            "aggregate_metrics": snapshot.get("aggregate_metrics") or {},
            "benchmark_metrics": snapshot.get("benchmark_metrics") or {},
            "quality_gate": snapshot.get("quality_gate") or {},
            "selected_tau": snapshot.get("selected_tau"),
            "selected_kappa": snapshot.get("selected_kappa"),
            "action_threshold": snapshot.get("action_threshold"),
            "calibration_mode": snapshot.get("calibration_mode"),
            "weather_forecast_run_identity_present": snapshot.get(
                "weather_forecast_run_identity_present"
            ),
        }
    )


def build_weather_vintage_shadow_summary(
    *,
    report: dict[str, Any],
    generated_at: str,
    run_id: str,
    run_purpose: str,
) -> dict[str, Any]:
    scopes: list[dict[str, Any]] = []
    for item in report.get("scopes") or []:
        scopes.append(
            _json_safe(
                {
                    "run_id": run_id,
                    "generated_at": generated_at,
                    "virus_typ": item.get("virus_typ"),
                    "horizon_days": item.get("horizon_days"),
                    "weather_forecast_vintage_mode": item.get("weather_forecast_vintage_mode"),
                    "comparison_verdict": item.get("verdict"),
                    "comparison_eligibility": determine_weather_vintage_comparison_eligibility(item),
                    "comparison_status": item.get("comparison_status"),
                    "weather_vintage_run_identity_coverage": item.get(
                        "weather_vintage_run_identity_coverage"
                    )
                    or {},
                    "weather_vintage_backtest_coverage": item.get(
                        "weather_vintage_backtest_coverage"
                    )
                    or {},
                    "legacy_vs_vintage_metric_delta": item.get("legacy_vs_vintage_metric_delta")
                    or {},
                    "quality_gate_change": item.get("quality_gate_change") or {},
                    "threshold_change": item.get("threshold_change"),
                    "calibration_change": item.get("calibration_change") or {},
                    "primary_mode_snapshot": _extract_mode_snapshot(
                        item,
                        WEATHER_FORECAST_VINTAGE_DISABLED,
                    ),
                    "shadow_mode_snapshot": _extract_mode_snapshot(
                        item,
                        WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
                    ),
                    "modes": item.get("modes") or {},
                }
            )
        )

    comparable_runs = sum(1 for item in scopes if item["comparison_eligibility"] == "comparable")
    insufficient_runs = sum(
        1 for item in scopes if item["comparison_eligibility"] == "insufficient_identity"
    )
    failed_runs = sum(1 for item in scopes if item["comparison_eligibility"] == "failed")
    return _json_safe(
        {
            "run_id": run_id,
            "run_purpose": run_purpose,
            "generated_at": generated_at,
            "status": report.get("status"),
            "comparison_type": "weather_vintage_prospective_shadow",
            "matrix": report.get("matrix") or {},
            "scopes": scopes,
            "summary": {
                "archived_scopes": int(len(scopes)),
                "comparable_scopes": int(comparable_runs),
                "insufficient_identity_scopes": int(insufficient_runs),
                "failed_scopes": int(failed_runs),
            },
        }
    )


def render_weather_vintage_shadow_run_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Weather Vintage Prospective Shadow Run",
        "",
        "Dieser Lauf archiviert den end-to-end Vergleich zwischen `legacy_issue_time_only` und `run_timestamp_v1`.",
        "",
        "## Run",
        "",
        f"- run_id: `{summary.get('run_id')}`",
        f"- run_purpose: `{summary.get('run_purpose')}`",
        f"- generated_at: `{summary.get('generated_at')}`",
        f"- archived_scopes: `{(summary.get('summary') or {}).get('archived_scopes')}`",
        f"- comparable_scopes: `{(summary.get('summary') or {}).get('comparable_scopes')}`",
        f"- insufficient_identity_scopes: `{(summary.get('summary') or {}).get('insufficient_identity_scopes')}`",
        "",
        "## Scope Snapshot",
        "",
    ]
    for item in summary.get("scopes") or []:
        delta = item.get("legacy_vs_vintage_metric_delta") or {}
        coverage = item.get("weather_vintage_backtest_coverage") or {}
        lines.extend(
            [
                f"### {item.get('virus_typ')} / h{item.get('horizon_days')}",
                "",
                f"- comparison_eligibility: `{item.get('comparison_eligibility')}`",
                f"- comparison_verdict: `{item.get('comparison_verdict')}`",
                f"- coverage_test: `{coverage.get('coverage_test')}`",
                f"- delta_relative_wis: `{delta.get('relative_wis', delta.get('wis'))}`",
                f"- delta_crps: `{delta.get('crps')}`",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def write_weather_vintage_shadow_archive(
    *,
    archive_dir: Path,
    report: dict[str, Any],
    generated_at: str,
    run_id: str,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    archive_dir.mkdir(parents=True, exist_ok=False)
    report_json_path = archive_dir / "report.json"
    report_md_path = archive_dir / "report.md"
    summary_json_path = archive_dir / "summary.json"
    run_manifest_path = archive_dir / "run_manifest.json"

    report_json_path.write_text(json.dumps(_json_safe(report), indent=2), encoding="utf-8")
    report_md_path.write_text(render_weather_vintage_markdown(report), encoding="utf-8")

    summary = build_weather_vintage_shadow_summary(
        report=report,
        generated_at=generated_at,
        run_id=run_id,
        run_purpose=str(manifest.get("run_purpose") or "manual_eval"),
    )
    summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest_payload = {
        **manifest,
        "generated_at": generated_at,
        "run_id": run_id,
        "summary_path": str(summary_json_path),
        "report_path": str(report_json_path),
        "report_md_path": str(report_md_path),
        "run_manifest_path": str(run_manifest_path),
        "files_written": [
            str(summary_json_path),
            str(report_json_path),
            str(report_md_path),
            str(run_manifest_path),
        ],
    }
    run_manifest_path.write_text(
        json.dumps(_json_safe(manifest_payload), indent=2),
        encoding="utf-8",
    )
    return {
        "summary_json": summary_json_path,
        "report_json": report_json_path,
        "report_md": report_md_path,
        "run_manifest": run_manifest_path,
    }


def load_weather_vintage_shadow_summaries(
    output_root: Path,
    *,
    included_run_purposes: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    runs_dir = output_root / "runs"
    if not runs_dir.exists():
        return []
    allowed_purposes = (
        {str(value) for value in included_run_purposes}
        if included_run_purposes is not None
        else None
    )
    summaries: list[dict[str, Any]] = []
    for summary_path in sorted(runs_dir.glob("*/summary.json")):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if allowed_purposes is not None and str(payload.get("run_purpose") or "") not in allowed_purposes:
            continue
        summaries.append(payload)
    return summaries


def determine_weather_vintage_review_status(scope_aggregate: dict[str, Any]) -> str:
    if int(scope_aggregate.get("comparable_runs") or 0) < WEATHER_VINTAGE_MIN_COMPARABLE_RUNS:
        return "still_collecting_evidence"
    if int(scope_aggregate.get("gate_worsening_runs") or 0) > 0:
        return "keep_legacy_default"
    if float(scope_aggregate.get("average_coverage_test") or 0.0) < WEATHER_VINTAGE_MIN_TEST_COVERAGE:
        return "still_collecting_evidence"
    if float(scope_aggregate.get("median_coverage_test") or 0.0) < WEATHER_VINTAGE_MIN_TEST_COVERAGE:
        return "still_collecting_evidence"
    if (
        float(scope_aggregate.get("median_relative_wis_delta") or 0.0) <= -0.01
        and float(scope_aggregate.get("median_crps_delta") or 0.0) <= -0.005
    ):
        return "candidate_for_manual_rollout_review"
    return "review_ready"


def _scope_review_recommendation(scope_aggregate: dict[str, Any]) -> str:
    review_status = determine_weather_vintage_review_status(scope_aggregate)
    if review_status == "candidate_for_manual_rollout_review":
        return "candidate_for_manual_rollout_review"
    if review_status == "review_ready":
        return "expand_shadow_only"
    if review_status == "still_collecting_evidence":
        return "keep_legacy_default"
    if int(scope_aggregate.get("comparable_runs") or 0) < WEATHER_VINTAGE_MIN_COMPARABLE_RUNS:
        return "keep_legacy_default"
    if int(scope_aggregate.get("gate_worsening_runs") or 0) > 0:
        return "keep_legacy_default"
    if float(scope_aggregate.get("average_coverage_test") or 0.0) < WEATHER_VINTAGE_MIN_TEST_COVERAGE:
        return "keep_legacy_default"
    if (
        float(scope_aggregate.get("median_relative_wis_delta") or 0.0) <= -0.01
        and float(scope_aggregate.get("median_crps_delta") or 0.0) <= -0.005
    ):
        return "candidate_for_selected_training_paths"
    return "expand_shadow_only"


def build_weather_vintage_shadow_aggregate(
    run_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for run_summary in run_summaries:
        for item in run_summary.get("scopes") or []:
            key = (str(item.get("virus_typ") or ""), int(item.get("horizon_days") or 0))
            grouped.setdefault(key, []).append(item)

    scope_aggregates: list[dict[str, Any]] = []
    for (virus_typ, horizon_days), rows in sorted(grouped.items()):
        comparable_rows = [
            row for row in rows if row.get("comparison_eligibility") == "comparable"
        ]
        relative_wis_deltas = [
            float((row.get("legacy_vs_vintage_metric_delta") or {}).get("relative_wis") or 0.0)
            for row in comparable_rows
        ]
        crps_deltas = [
            float((row.get("legacy_vs_vintage_metric_delta") or {}).get("crps") or 0.0)
            for row in comparable_rows
        ]
        coverage_test_values = [
            float((row.get("weather_vintage_backtest_coverage") or {}).get("coverage_test") or 0.0)
            for row in comparable_rows
        ]
        gate_worsening_runs = 0
        for row in comparable_rows:
            gate_change = row.get("quality_gate_change") or {}
            if _gate_rank(gate_change.get("vintage_forecast_readiness")) < _gate_rank(
                gate_change.get("legacy_forecast_readiness")
            ):
                gate_worsening_runs += 1
        coverage_series = [
            {
                "generated_at": row.get("generated_at"),
                "coverage_test": (row.get("weather_vintage_backtest_coverage") or {}).get("coverage_test"),
                "coverage_overall": (row.get("weather_vintage_backtest_coverage") or {}).get("coverage_overall"),
                "comparison_eligibility": row.get("comparison_eligibility"),
            }
            for row in sorted(rows, key=lambda item: str(item.get("generated_at") or ""))
        ]
        gate_change_series = [
            {
                "generated_at": row.get("generated_at"),
                "legacy_forecast_readiness": (row.get("quality_gate_change") or {}).get(
                    "legacy_forecast_readiness"
                ),
                "vintage_forecast_readiness": (row.get("quality_gate_change") or {}).get(
                    "vintage_forecast_readiness"
                ),
                "comparison_eligibility": row.get("comparison_eligibility"),
            }
            for row in sorted(rows, key=lambda item: str(item.get("generated_at") or ""))
        ]
        scope_aggregate = {
            "virus_typ": virus_typ,
            "horizon_days": int(horizon_days),
            "archived_runs": int(len(rows)),
            "comparable_runs": int(len(comparable_rows)),
            "insufficient_identity_runs": int(
                sum(1 for row in rows if row.get("comparison_eligibility") == "insufficient_identity")
            ),
            "failed_runs": int(sum(1 for row in rows if row.get("comparison_eligibility") == "failed")),
            "average_relative_wis_delta": round(float(pd.Series(relative_wis_deltas).mean()), 4)
            if relative_wis_deltas
            else None,
            "median_relative_wis_delta": round(float(pd.Series(relative_wis_deltas).median()), 4)
            if relative_wis_deltas
            else None,
            "average_crps_delta": round(float(pd.Series(crps_deltas).mean()), 4)
            if crps_deltas
            else None,
            "median_crps_delta": round(float(pd.Series(crps_deltas).median()), 4)
            if crps_deltas
            else None,
            "average_coverage_test": round(float(pd.Series(coverage_test_values).mean()), 4)
            if coverage_test_values
            else 0.0,
            "median_coverage_test": round(float(pd.Series(coverage_test_values).median()), 4)
            if coverage_test_values
            else 0.0,
            "gate_worsening_runs": int(gate_worsening_runs),
            "coverage_trend": coverage_series,
            "gate_change_trend": gate_change_series,
        }
        scope_aggregate["review_status"] = determine_weather_vintage_review_status(scope_aggregate)
        scope_aggregate["overall_recommendation"] = _scope_review_recommendation(scope_aggregate)
        scope_aggregates.append(_json_safe(scope_aggregate))

    review_status_counts: dict[str, int] = {}
    for item in scope_aggregates:
        review_status = str(item.get("review_status") or "unknown")
        review_status_counts[review_status] = review_status_counts.get(review_status, 0) + 1

    return _json_safe(
        {
            "comparison_type": "weather_vintage_prospective_shadow_aggregate",
            "archived_runs": int(len(run_summaries)),
            "included_run_purposes": sorted(
                {str(item.get("run_purpose") or "unknown") for item in run_summaries}
            ),
            "scopes": scope_aggregates,
            "summary": {
                "total_scopes": int(len(scope_aggregates)),
                "comparable_scope_runs": int(
                    sum(int(item.get("comparable_runs") or 0) for item in scope_aggregates)
                ),
                "insufficient_identity_scope_runs": int(
                    sum(int(item.get("insufficient_identity_runs") or 0) for item in scope_aggregates)
                ),
                "review_status_counts": review_status_counts,
                "review_ready_scopes": [
                    f"{item['virus_typ']} h{item['horizon_days']}"
                    for item in scope_aggregates
                    if item.get("review_status") == "review_ready"
                ],
                "still_collecting_scopes": [
                    f"{item['virus_typ']} h{item['horizon_days']}"
                    for item in scope_aggregates
                    if item.get("review_status") == "still_collecting_evidence"
                ],
                "candidate_scopes": [
                    f"{item['virus_typ']} h{item['horizon_days']}"
                    for item in scope_aggregates
                    if item.get("review_status") == "candidate_for_manual_rollout_review"
                ],
                "shadow_only_scopes": [
                    f"{item['virus_typ']} h{item['horizon_days']}"
                    for item in scope_aggregates
                    if item.get("overall_recommendation") == "expand_shadow_only"
                ],
                "legacy_default_scopes": [
                    f"{item['virus_typ']} h{item['horizon_days']}"
                    for item in scope_aggregates
                    if item.get("overall_recommendation") == "keep_legacy_default"
                ],
            },
        }
    )


def render_weather_vintage_shadow_aggregate_markdown(aggregate: dict[str, Any]) -> str:
    lines = [
        "# Weather Vintage Prospective Shadow Aggregate",
        "",
        "Dieser Report fasst mehrere prospektive Shadow-Laeufe zusammen. `insufficient_identity`-Laeufe werden nicht als vergleichbar gezaehlt.",
        "",
        "## Summary",
        "",
        f"- archived_runs: `{aggregate.get('archived_runs')}`",
        f"- total_scopes: `{(aggregate.get('summary') or {}).get('total_scopes')}`",
        f"- comparable_scope_runs: `{(aggregate.get('summary') or {}).get('comparable_scope_runs')}`",
        f"- insufficient_identity_scope_runs: `{(aggregate.get('summary') or {}).get('insufficient_identity_scope_runs')}`",
        "",
        "## Scope Review",
        "",
    ]
    for item in aggregate.get("scopes") or []:
        lines.extend(
            [
                f"### {item.get('virus_typ')} / h{item.get('horizon_days')}",
                "",
                f"- archived_runs: `{item.get('archived_runs')}`",
                f"- comparable_runs: `{item.get('comparable_runs')}`",
                f"- gate_worsening_runs: `{item.get('gate_worsening_runs')}`",
                f"- average_relative_wis_delta: `{item.get('average_relative_wis_delta')}`",
                f"- median_relative_wis_delta: `{item.get('median_relative_wis_delta')}`",
                f"- average_crps_delta: `{item.get('average_crps_delta')}`",
                f"- median_crps_delta: `{item.get('median_crps_delta')}`",
                f"- average_coverage_test: `{item.get('average_coverage_test')}`",
                f"- review_status: `{item.get('review_status')}`",
                f"- overall_recommendation: `{item.get('overall_recommendation')}`",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _parse_generated_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return pd.Timestamp(value).to_pydatetime()
    except Exception:
        return None


def _weather_health_status_exit_code(status: str) -> int:
    if status == "critical":
        return 2
    if status == "warning":
        return 1
    return 0


def _combine_weather_health_status(current: str, new: str) -> str:
    if WEATHER_VINTAGE_HEALTH_STATUS_ORDER.get(new, 0) > WEATHER_VINTAGE_HEALTH_STATUS_ORDER.get(
        current, 0
    ):
        return new
    return current


def build_weather_vintage_shadow_health_report(
    run_summaries: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_run_age_hours: int = WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS,
    max_days_without_comparable: int = WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE,
    max_insufficient_identity_streak: int = WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK,
) -> dict[str, Any]:
    now_dt = now or datetime.utcnow()
    status = "ok"
    findings: list[dict[str, Any]] = []
    sorted_runs = sorted(
        run_summaries,
        key=lambda item: _parse_generated_at(item.get("generated_at")) or datetime.min,
    )
    latest_run = sorted_runs[-1] if sorted_runs else None

    def _add_finding(severity: str, code: str, message: str, **details: Any) -> None:
        nonlocal status
        status = _combine_weather_health_status(status, severity)
        findings.append(
            _json_safe(
                {
                    "severity": severity,
                    "code": code,
                    "message": message,
                    **details,
                }
            )
        )

    if latest_run is None:
        _add_finding(
            "critical",
            "no_scheduled_shadow_runs",
            "Es gibt noch keine archivierten scheduled_shadow-Laeufe fuer den Weather-Vintage-Shadow-Betrieb.",
        )
    else:
        latest_generated_at = _parse_generated_at(latest_run.get("generated_at"))
        if latest_generated_at is not None:
            age_hours = round(
                max((now_dt - latest_generated_at).total_seconds(), 0.0) / 3600.0,
                2,
            )
            if age_hours > float(max_run_age_hours * 2):
                _add_finding(
                    "critical",
                    "latest_run_stale",
                    "Der letzte scheduled_shadow-Lauf ist deutlich aelter als erlaubt.",
                    run_id=latest_run.get("run_id"),
                    generated_at=latest_run.get("generated_at"),
                    age_hours=age_hours,
                    threshold_hours=max_run_age_hours,
                )
            elif age_hours > float(max_run_age_hours):
                _add_finding(
                    "warning",
                    "latest_run_stale",
                    "Der letzte scheduled_shadow-Lauf ist aelter als der erlaubte Schwellwert.",
                    run_id=latest_run.get("run_id"),
                    generated_at=latest_run.get("generated_at"),
                    age_hours=age_hours,
                    threshold_hours=max_run_age_hours,
                )
        latest_summary = latest_run.get("summary") or {}
        latest_failed_scopes = int(latest_summary.get("failed_scopes") or 0)
        latest_archived_scopes = int(latest_summary.get("archived_scopes") or 0)
        if latest_archived_scopes > 0 and latest_failed_scopes >= latest_archived_scopes:
            _add_finding(
                "critical",
                "latest_run_failed",
                "Der letzte scheduled_shadow-Lauf hat fuer alle Scopes unbrauchbare Ergebnisse geliefert.",
                run_id=latest_run.get("run_id"),
                failed_scopes=latest_failed_scopes,
                archived_scopes=latest_archived_scopes,
            )
        elif latest_failed_scopes > 0:
            _add_finding(
                "warning",
                "latest_run_partial_failure",
                "Der letzte scheduled_shadow-Lauf hat fuer mindestens einen Scope einen Fehler geliefert.",
                run_id=latest_run.get("run_id"),
                failed_scopes=latest_failed_scopes,
                archived_scopes=latest_archived_scopes,
            )

    grouped_scopes: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for run_summary in sorted_runs:
        generated_at = run_summary.get("generated_at")
        for scope in run_summary.get("scopes") or []:
            key = (str(scope.get("virus_typ") or ""), int(scope.get("horizon_days") or 0))
            grouped_scopes.setdefault(key, []).append(
                {
                    **scope,
                    "generated_at": generated_at,
                    "run_id": run_summary.get("run_id"),
                }
            )

    scope_health: list[dict[str, Any]] = []
    for (virus_typ, horizon_days), rows in sorted(grouped_scopes.items()):
        rows = sorted(rows, key=lambda item: _parse_generated_at(item.get("generated_at")) or datetime.min)
        first_seen = _parse_generated_at(rows[0].get("generated_at"))
        last_comparable = None
        insufficient_streak = 0
        for row in reversed(rows):
            eligibility = str(row.get("comparison_eligibility") or "")
            if eligibility == "insufficient_identity":
                insufficient_streak += 1
            else:
                break
        for row in reversed(rows):
            if str(row.get("comparison_eligibility") or "") == "comparable":
                last_comparable = _parse_generated_at(row.get("generated_at"))
                break

        scope_status = "ok"
        scope_findings: list[dict[str, Any]] = []
        if insufficient_streak >= int(max_insufficient_identity_streak * 2):
            scope_status = _combine_weather_health_status(scope_status, "critical")
            scope_findings.append(
                {
                    "severity": "critical",
                    "code": "insufficient_identity_streak",
                    "streak": insufficient_streak,
                    "threshold": max_insufficient_identity_streak,
                }
            )
        elif insufficient_streak >= int(max_insufficient_identity_streak):
            scope_status = _combine_weather_health_status(scope_status, "warning")
            scope_findings.append(
                {
                    "severity": "warning",
                    "code": "insufficient_identity_streak",
                    "streak": insufficient_streak,
                    "threshold": max_insufficient_identity_streak,
                }
            )

        if last_comparable is None:
            days_without_comparable = (
                round(max((now_dt - first_seen).total_seconds(), 0.0) / 86400.0, 2)
                if first_seen is not None
                else None
            )
            if (
                days_without_comparable is not None
                and days_without_comparable > float(max_days_without_comparable)
            ):
                scope_status = _combine_weather_health_status(scope_status, "critical")
                scope_findings.append(
                    {
                        "severity": "critical",
                        "code": "no_comparable_runs",
                        "days_without_comparable": days_without_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )
            elif rows:
                scope_status = _combine_weather_health_status(scope_status, "warning")
                scope_findings.append(
                    {
                        "severity": "warning",
                        "code": "still_waiting_for_comparable_run",
                        "days_without_comparable": days_without_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )
        else:
            days_since_comparable = round(
                max((now_dt - last_comparable).total_seconds(), 0.0) / 86400.0,
                2,
            )
            if days_since_comparable > float(max_days_without_comparable * 2):
                scope_status = _combine_weather_health_status(scope_status, "critical")
                scope_findings.append(
                    {
                        "severity": "critical",
                        "code": "comparable_run_too_old",
                        "days_since_comparable": days_since_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )
            elif days_since_comparable > float(max_days_without_comparable):
                scope_status = _combine_weather_health_status(scope_status, "warning")
                scope_findings.append(
                    {
                        "severity": "warning",
                        "code": "comparable_run_old",
                        "days_since_comparable": days_since_comparable,
                        "threshold_days": max_days_without_comparable,
                    }
                )

        status = _combine_weather_health_status(status, scope_status)
        scope_health.append(
            _json_safe(
                {
                    "virus_typ": virus_typ,
                    "horizon_days": horizon_days,
                    "status": scope_status,
                    "archived_runs": len(rows),
                    "comparable_runs": sum(
                        1 for row in rows if row.get("comparison_eligibility") == "comparable"
                    ),
                    "insufficient_identity_streak": insufficient_streak,
                    "last_comparable_generated_at": (
                        last_comparable.isoformat() if last_comparable is not None else None
                    ),
                    "findings": scope_findings,
                }
            )
        )

    summary = {
        "total_runs": int(len(sorted_runs)),
        "monitored_scopes": int(len(scope_health)),
        "comparable_scopes": int(sum(1 for item in scope_health if int(item.get("comparable_runs") or 0) > 0)),
        "warning_scopes": int(sum(1 for item in scope_health if item.get("status") == "warning")),
        "critical_scopes": int(sum(1 for item in scope_health if item.get("status") == "critical")),
    }
    return _json_safe(
        {
            "comparison_type": "weather_vintage_prospective_shadow_health",
            "generated_at": now_dt.isoformat(),
            "status": status,
            "exit_code": _weather_health_status_exit_code(status),
            "thresholds": {
                "max_run_age_hours": int(max_run_age_hours),
                "max_days_without_comparable": int(max_days_without_comparable),
                "max_insufficient_identity_streak": int(max_insufficient_identity_streak),
            },
            "included_run_purposes": sorted(
                {str(item.get("run_purpose") or "unknown") for item in sorted_runs}
            ),
            "latest_run": (
                {
                    "run_id": latest_run.get("run_id"),
                    "generated_at": latest_run.get("generated_at"),
                    "run_purpose": latest_run.get("run_purpose"),
                    "summary": latest_run.get("summary") or {},
                }
                if latest_run is not None
                else None
            ),
            "findings": findings,
            "scopes": scope_health,
            "summary": summary,
        }
    )


def render_weather_vintage_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Weather Vintage Comparison",
        "",
        "This report compares `legacy_issue_time_only` against `run_timestamp_v1` end-to-end on the regional training/backtest path.",
        "",
        "## Summary",
        "",
        f"- Total scopes: {int((report.get('summary') or {}).get('total_scopes') or 0)}",
    ]
    verdict_counts = (report.get("summary") or {}).get("verdict_counts") or {}
    for key in sorted(verdict_counts):
        lines.append(f"- {key}: {int(verdict_counts[key])}")
    coverage_status_counts = (report.get("summary") or {}).get("coverage_status_counts") or {}
    for key in sorted(coverage_status_counts):
        lines.append(f"- coverage_{key}: {int(coverage_status_counts[key])}")
    lines.extend(["", "## Scope Results", ""])
    for item in report.get("scopes") or []:
        delta = item.get("legacy_vs_vintage_metric_delta") or {}
        coverage = (
            item.get("weather_vintage_run_identity_coverage", {})
            .get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, {})
        )
        backtest_coverage = item.get("weather_vintage_backtest_coverage") or {}
        lines.extend(
            [
                f"### {item['virus_typ']} / h{item['horizon_days']}",
                "",
                f"- Status: `{item.get('status')}`",
                f"- Verdict: `{item.get('verdict')}`",
                f"- Comparison status: `{item.get('comparison_status')}`",
                f"- Vintage run identity present: `{bool(coverage.get('run_identity_present'))}`",
                f"- Coverage status: `{backtest_coverage.get('coverage_status')}`",
                f"- Coverage overall: `{backtest_coverage.get('coverage_overall')}`",
                f"- Coverage train: `{backtest_coverage.get('coverage_train')}`",
                f"- Coverage test: `{backtest_coverage.get('coverage_test')}`",
                f"- First available run-identity date: `{backtest_coverage.get('first_available_run_identity_date')}`",
                f"- Last available run-identity date: `{backtest_coverage.get('last_available_run_identity_date')}`",
                f"- First covered as_of_date: `{backtest_coverage.get('first_covered_as_of_date')}`",
                f"- Last covered as_of_date: `{backtest_coverage.get('last_covered_as_of_date')}`",
                f"- Delta relative_wis: `{delta.get('relative_wis', delta.get('wis'))}`",
                f"- Delta crps: `{delta.get('crps')}`",
                f"- Quality gate change: `{(item.get('quality_gate_change') or {}).get('legacy_forecast_readiness')}` -> `{(item.get('quality_gate_change') or {}).get('vintage_forecast_readiness')}`",
                f"- Threshold change: `{item.get('threshold_change')}`",
                f"- Calibration change: `{(item.get('calibration_change') or {}).get('legacy')}` -> `{(item.get('calibration_change') or {}).get('vintage')}`",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


class WeatherVintageComparisonRunner:
    """Run the small weather vintage benchmark matrix against the regional trainer."""

    def __init__(
        self,
        db,
        *,
        trainer_factory: Callable[[Any], RegionalModelTrainer] | None = None,
        coverage_analyzer: Callable[[RegionalModelTrainer, str, int, int], dict[str, Any]] | None = None,
    ) -> None:
        self.db = db
        self.trainer_factory = trainer_factory or (lambda database: RegionalModelTrainer(database))
        self.coverage_analyzer = coverage_analyzer or self._analyze_scope_coverage

    def _load_weather_identity_frame(
        self,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            self.db.query(
                WeatherData.datum,
                WeatherData.available_time,
                WeatherData.forecast_run_timestamp,
                WeatherData.forecast_run_id,
                WeatherData.forecast_run_identity_source,
                WeatherData.forecast_run_identity_quality,
                WeatherData.data_type,
            )
            .filter(
                WeatherData.data_type == "DAILY_FORECAST",
                WeatherData.datum >= start_date.to_pydatetime(),
                WeatherData.datum <= end_date.to_pydatetime(),
            )
            .all()
        )
        if not rows:
            return pd.DataFrame(
                columns=[
                    "datum",
                    "available_time",
                    "forecast_run_timestamp",
                    "forecast_run_id",
                    "forecast_run_identity_source",
                    "forecast_run_identity_quality",
                    "data_type",
                ]
            )
        return pd.DataFrame(
            [
                {
                    "datum": row.datum,
                    "available_time": row.available_time,
                    "forecast_run_timestamp": row.forecast_run_timestamp,
                    "forecast_run_id": row.forecast_run_id,
                    "forecast_run_identity_source": row.forecast_run_identity_source,
                    "forecast_run_identity_quality": row.forecast_run_identity_quality,
                    "data_type": row.data_type,
                }
                for row in rows
            ]
        )

    @staticmethod
    def summarize_backtest_weather_identity_coverage(
        *,
        panel: pd.DataFrame,
        weather_frame: pd.DataFrame,
        horizon_days: int,
    ) -> dict[str, Any]:
        if panel.empty:
            return {
                "coverage_status": "no_panel",
                "insufficient_for_comparison": True,
                "coverage_overall": 0.0,
                "coverage_train": 0.0,
                "coverage_test": 0.0,
                "coverage_by_fold": [],
                "coverage_by_time_block": [],
                "first_available_run_identity_date": None,
                "last_available_run_identity_date": None,
                "first_covered_as_of_date": None,
                "last_covered_as_of_date": None,
                "unique_as_of_dates": 0,
                "rows_in_panel": 0,
            }

        working = panel.copy()
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        if "target_date" in working.columns:
            working["target_date"] = pd.to_datetime(working["target_date"]).dt.normalize()
        else:
            working["target_date"] = working["as_of_date"] + pd.to_timedelta(int(horizon_days), unit="D")

        by_as_of = (
            working.loc[:, ["as_of_date", "target_date"]]
            .drop_duplicates()
            .sort_values(["as_of_date", "target_date"])
            .groupby("as_of_date", as_index=False)
            .first()
        )

        weather = weather_frame.copy()
        if weather.empty:
            weather = pd.DataFrame(
                columns=[
                    "datum",
                    "available_time",
                    "forecast_run_timestamp",
                    "forecast_run_id",
                    "forecast_run_identity_source",
                    "forecast_run_identity_quality",
                    "data_type",
                ]
            )
        else:
            weather["datum"] = pd.to_datetime(weather["datum"]).dt.normalize()
            weather["available_time"] = pd.to_datetime(weather["available_time"])
            weather["forecast_run_timestamp"] = pd.to_datetime(weather["forecast_run_timestamp"])
            weather = weather.loc[
                weather["forecast_run_timestamp"].notna()
                & weather["available_time"].notna()
                & (weather["data_type"] == "DAILY_FORECAST")
            ].copy()

        availability_records: list[dict[str, Any]] = []
        for row in by_as_of.itertuples(index=False):
            as_of_date = pd.Timestamp(row.as_of_date).normalize()
            target_date = pd.Timestamp(row.target_date).normalize()
            covered = False
            if not weather.empty:
                covered = bool(
                    not weather.loc[
                        (weather["datum"] == target_date)
                        & (weather["available_time"] <= as_of_date)
                        & (weather["forecast_run_timestamp"] <= as_of_date)
                    ].empty
                )
            availability_records.append(
                {
                    "as_of_date": as_of_date,
                    "target_date": target_date,
                    "covered": covered,
                }
            )

        availability = pd.DataFrame(availability_records)
        if availability.empty:
            availability = pd.DataFrame(columns=["as_of_date", "target_date", "covered"])

        unique_dates = [pd.Timestamp(value).normalize() for value in availability["as_of_date"].tolist()]
        coverage_overall = round(float(availability["covered"].mean() or 0.0), 4) if not availability.empty else 0.0

        train_total_dates = 0
        train_covered_dates = 0
        test_total_dates = 0
        test_covered_dates = 0
        coverage_by_fold: list[dict[str, Any]] = []
        for fold_index, (train_dates, test_dates) in enumerate(
            time_based_panel_splits(
                unique_dates,
                n_splits=5,
                min_train_periods=90,
                min_test_periods=21,
            ),
            start=1,
        ):
            train_mask = availability["as_of_date"].isin(train_dates)
            test_mask = availability["as_of_date"].isin(test_dates)
            train_fraction = round(float(availability.loc[train_mask, "covered"].mean() or 0.0), 4)
            test_fraction = round(float(availability.loc[test_mask, "covered"].mean() or 0.0), 4)
            train_rows = int(train_mask.sum())
            test_rows = int(test_mask.sum())
            train_total_dates += train_rows
            test_total_dates += test_rows
            train_covered_dates += int(availability.loc[train_mask, "covered"].sum()) if train_rows else 0
            test_covered_dates += int(availability.loc[test_mask, "covered"].sum()) if test_rows else 0
            coverage_by_fold.append(
                {
                    "fold": int(fold_index),
                    "train_start": str(min(train_dates)) if train_dates else None,
                    "train_end": str(max(train_dates)) if train_dates else None,
                    "test_start": str(min(test_dates)) if test_dates else None,
                    "test_end": str(max(test_dates)) if test_dates else None,
                    "coverage_train": train_fraction,
                    "coverage_test": test_fraction,
                    "train_dates": train_rows,
                    "test_dates": test_rows,
                }
            )

        coverage_train = round(float(train_covered_dates / train_total_dates), 4) if train_total_dates else 0.0
        coverage_test = round(float(test_covered_dates / test_total_dates), 4) if test_total_dates else 0.0

        block_start = pd.Timestamp(min(unique_dates)).normalize() if unique_dates else None
        block_end = pd.Timestamp(max(unique_dates)).normalize() if unique_dates else None
        coverage_by_time_block: list[dict[str, Any]] = []
        if block_start is not None and block_end is not None:
            current_start = block_start
            while current_start <= block_end:
                current_end = min(
                    current_start + pd.Timedelta(days=WEATHER_VINTAGE_TIME_BLOCK_DAYS - 1),
                    block_end,
                )
                block_mask = (
                    (availability["as_of_date"] >= current_start)
                    & (availability["as_of_date"] <= current_end)
                )
                block_rows = int(block_mask.sum())
                coverage_by_time_block.append(
                    {
                        "start": str(current_start),
                        "end": str(current_end),
                        "coverage": round(
                            float(availability.loc[block_mask, "covered"].mean() or 0.0),
                            4,
                        )
                        if block_rows
                        else 0.0,
                        "as_of_dates": block_rows,
                    }
                )
                current_start = current_end + pd.Timedelta(days=1)

        covered_dates = availability.loc[availability["covered"], "as_of_date"].sort_values()
        if coverage_test >= WEATHER_VINTAGE_MIN_TEST_COVERAGE and coverage_train >= WEATHER_VINTAGE_MIN_TRAIN_COVERAGE:
            coverage_status = "sufficient"
        elif coverage_overall <= 0.0:
            coverage_status = "none"
        else:
            coverage_status = "insufficient"

        return _json_safe(
            {
                "coverage_status": coverage_status,
                "insufficient_for_comparison": coverage_status != "sufficient",
                "coverage_overall": coverage_overall,
                "coverage_train": coverage_train,
                "coverage_test": coverage_test,
                "coverage_by_fold": coverage_by_fold,
                "coverage_by_time_block": coverage_by_time_block,
                "first_available_run_identity_date": (
                    str(weather["datum"].min()) if not weather.empty else None
                ),
                "last_available_run_identity_date": (
                    str(weather["datum"].max()) if not weather.empty else None
                ),
                "first_covered_as_of_date": str(covered_dates.min()) if not covered_dates.empty else None,
                "last_covered_as_of_date": str(covered_dates.max()) if not covered_dates.empty else None,
                "unique_as_of_dates": int(len(unique_dates)),
                "rows_in_panel": int(len(panel)),
                "weather_rows_with_run_identity": int(len(weather)),
            }
        )

    def _analyze_scope_coverage(
        self,
        trainer: RegionalModelTrainer,
        virus_typ: str,
        horizon_days: int,
        lookback_days: int,
    ) -> dict[str, Any]:
        panel = trainer._build_training_panel(
            virus_typ=virus_typ,
            lookback_days=int(lookback_days),
            horizon_days=int(horizon_days),
            weather_forecast_vintage_mode=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
        )
        panel = trainer._prepare_horizon_panel(panel, horizon_days=int(horizon_days))
        if panel.empty:
            return self.summarize_backtest_weather_identity_coverage(
                panel=panel,
                weather_frame=pd.DataFrame(),
                horizon_days=int(horizon_days),
            )

        weather_frame = self._load_weather_identity_frame(
            start_date=pd.Timestamp(panel["as_of_date"].min()).normalize() + pd.Timedelta(days=1),
            end_date=pd.Timestamp(panel["target_date"].max()).normalize(),
        )
        return self.summarize_backtest_weather_identity_coverage(
            panel=panel,
            weather_frame=weather_frame,
            horizon_days=int(horizon_days),
        )

    def run(
        self,
        *,
        virus_types: list[str] | tuple[str, ...] | None = None,
        horizon_days_list: list[int] | tuple[int, ...] | None = None,
        lookback_days: int = 900,
        output_json: Path | None = None,
        output_markdown: Path | None = None,
    ) -> dict[str, Any]:
        selected_viruses, selected_horizons = normalize_weather_vintage_matrix(
            virus_types=virus_types,
            horizon_days_list=horizon_days_list,
        )
        trainer = self.trainer_factory(self.db)
        scope_reports: list[dict[str, Any]] = []

        for virus_typ in selected_viruses:
            for horizon_days in selected_horizons:
                result = trainer.train_all_regions(
                    virus_typ=virus_typ,
                    lookback_days=int(lookback_days),
                    persist=False,
                    horizon_days=int(horizon_days),
                    weather_vintage_comparison=True,
                )
                scope_report = scope_report_from_training_result(
                    virus_typ=virus_typ,
                    horizon_days=int(horizon_days),
                    result=result or {},
                )
                scope_report["weather_vintage_backtest_coverage"] = self.coverage_analyzer(
                    trainer,
                    virus_typ,
                    int(horizon_days),
                    int(lookback_days),
                )
                scope_reports.append(_json_safe(scope_report))

        report = {
            "status": "ok",
            "comparison_type": "weather_vintage_end_to_end_training_backtest",
            "matrix": {
                "virus_types": selected_viruses,
                "horizon_days_list": selected_horizons,
                "lookback_days": int(lookback_days),
                "active_training_mode_default": WEATHER_FORECAST_VINTAGE_DISABLED,
                "shadow_mode": WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            },
            "scopes": scope_reports,
            "summary": build_weather_vintage_report_summary(scope_reports),
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(_json_safe(report), indent=2), encoding="utf-8")
        if output_markdown is not None:
            output_markdown.parent.mkdir(parents=True, exist_ok=True)
            output_markdown.write_text(render_weather_vintage_markdown(report), encoding="utf-8")
        return _json_safe(report)
