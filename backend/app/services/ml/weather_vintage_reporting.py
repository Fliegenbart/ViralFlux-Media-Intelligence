"""Reporting and shadow archive helpers for weather vintage comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def scope_report_from_training_result(
    *,
    virus_typ: str,
    horizon_days: int,
    result: dict[str, Any],
    weather_forecast_vintage_disabled: str,
    weather_forecast_vintage_run_timestamp_v1: str,
    json_safe_fn: Any,
    classify_weather_vintage_result_fn: Any,
) -> dict[str, Any]:
    comparison = result.get("weather_vintage_comparison") or {}
    modes = comparison.get("modes") or {}
    legacy_mode = modes.get(weather_forecast_vintage_disabled) or {}
    vintage_mode = modes.get(weather_forecast_vintage_run_timestamp_v1) or {}
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
            weather_forecast_vintage_disabled: legacy_mode,
            weather_forecast_vintage_run_timestamp_v1: vintage_mode,
        },
    }
    report["verdict"] = classify_weather_vintage_result_fn(report)
    return json_safe_fn(report)


def build_weather_vintage_report_summary(scope_reports: list[dict[str, Any]]) -> dict[str, Any]:
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


def build_weather_vintage_shadow_summary(
    *,
    report: dict[str, Any],
    generated_at: str,
    run_id: str,
    run_purpose: str,
    json_safe_fn: Any,
    determine_weather_vintage_comparison_eligibility_fn: Any,
    extract_mode_snapshot_fn: Any,
    weather_forecast_vintage_disabled: str,
    weather_forecast_vintage_run_timestamp_v1: str,
) -> dict[str, Any]:
    scopes: list[dict[str, Any]] = []
    for item in report.get("scopes") or []:
        scopes.append(
            json_safe_fn(
                {
                    "run_id": run_id,
                    "generated_at": generated_at,
                    "virus_typ": item.get("virus_typ"),
                    "horizon_days": item.get("horizon_days"),
                    "weather_forecast_vintage_mode": item.get("weather_forecast_vintage_mode"),
                    "comparison_verdict": item.get("verdict"),
                    "comparison_eligibility": determine_weather_vintage_comparison_eligibility_fn(item),
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
                    "primary_mode_snapshot": extract_mode_snapshot_fn(
                        item,
                        weather_forecast_vintage_disabled,
                    ),
                    "shadow_mode_snapshot": extract_mode_snapshot_fn(
                        item,
                        weather_forecast_vintage_run_timestamp_v1,
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
    return json_safe_fn(
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
    json_module: Any,
    json_safe_fn: Any,
    render_weather_vintage_markdown_fn: Any,
    build_weather_vintage_shadow_summary_fn: Any,
) -> dict[str, Path]:
    archive_dir.mkdir(parents=True, exist_ok=False)
    report_json_path = archive_dir / "report.json"
    report_md_path = archive_dir / "report.md"
    summary_json_path = archive_dir / "summary.json"
    run_manifest_path = archive_dir / "run_manifest.json"

    report_json_path.write_text(json_module.dumps(json_safe_fn(report), indent=2), encoding="utf-8")
    report_md_path.write_text(render_weather_vintage_markdown_fn(report), encoding="utf-8")

    summary = build_weather_vintage_shadow_summary_fn(
        report=report,
        generated_at=generated_at,
        run_id=run_id,
        run_purpose=str(manifest.get("run_purpose") or "manual_eval"),
    )
    summary_json_path.write_text(json_module.dumps(summary, indent=2), encoding="utf-8")
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
        json_module.dumps(json_safe_fn(manifest_payload), indent=2),
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


def determine_weather_vintage_review_status(scope_aggregate: dict[str, Any], *, min_comparable_runs: int, min_test_coverage: float) -> str:
    if int(scope_aggregate.get("comparable_runs") or 0) < min_comparable_runs:
        return "still_collecting_evidence"
    if int(scope_aggregate.get("gate_worsening_runs") or 0) > 0:
        return "keep_legacy_default"
    if float(scope_aggregate.get("average_coverage_test") or 0.0) < min_test_coverage:
        return "still_collecting_evidence"
    if float(scope_aggregate.get("median_coverage_test") or 0.0) < min_test_coverage:
        return "still_collecting_evidence"
    if (
        float(scope_aggregate.get("median_relative_wis_delta") or 0.0) <= -0.01
        and float(scope_aggregate.get("median_crps_delta") or 0.0) <= -0.005
    ):
        return "candidate_for_manual_rollout_review"
    return "review_ready"


def scope_review_recommendation(scope_aggregate: dict[str, Any], *, determine_weather_vintage_review_status_fn: Any, min_comparable_runs: int, min_test_coverage: float) -> str:
    review_status = determine_weather_vintage_review_status_fn(scope_aggregate)
    if review_status == "candidate_for_manual_rollout_review":
        return "candidate_for_manual_rollout_review"
    if review_status == "review_ready":
        return "expand_shadow_only"
    if review_status == "still_collecting_evidence":
        return "keep_legacy_default"
    if int(scope_aggregate.get("comparable_runs") or 0) < min_comparable_runs:
        return "keep_legacy_default"
    if int(scope_aggregate.get("gate_worsening_runs") or 0) > 0:
        return "keep_legacy_default"
    if float(scope_aggregate.get("average_coverage_test") or 0.0) < min_test_coverage:
        return "keep_legacy_default"
    if (
        float(scope_aggregate.get("median_relative_wis_delta") or 0.0) <= -0.01
        and float(scope_aggregate.get("median_crps_delta") or 0.0) <= -0.005
    ):
        return "candidate_for_selected_training_paths"
    return "expand_shadow_only"


def build_weather_vintage_shadow_aggregate(
    run_summaries: list[dict[str, Any]],
    *,
    gate_rank_fn: Any,
    json_safe_fn: Any,
    determine_weather_vintage_review_status_fn: Any,
    scope_review_recommendation_fn: Any,
    pd_module: Any,
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
            if gate_rank_fn(gate_change.get("vintage_forecast_readiness")) < gate_rank_fn(
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
            "average_relative_wis_delta": round(float(pd_module.Series(relative_wis_deltas).mean()), 4)
            if relative_wis_deltas
            else None,
            "median_relative_wis_delta": round(float(pd_module.Series(relative_wis_deltas).median()), 4)
            if relative_wis_deltas
            else None,
            "average_crps_delta": round(float(pd_module.Series(crps_deltas).mean()), 4)
            if crps_deltas
            else None,
            "median_crps_delta": round(float(pd_module.Series(crps_deltas).median()), 4)
            if crps_deltas
            else None,
            "average_coverage_test": round(float(pd_module.Series(coverage_test_values).mean()), 4)
            if coverage_test_values
            else 0.0,
            "median_coverage_test": round(float(pd_module.Series(coverage_test_values).median()), 4)
            if coverage_test_values
            else 0.0,
            "gate_worsening_runs": int(gate_worsening_runs),
            "coverage_trend": coverage_series,
            "gate_change_trend": gate_change_series,
        }
        scope_aggregate["review_status"] = determine_weather_vintage_review_status_fn(scope_aggregate)
        scope_aggregate["overall_recommendation"] = scope_review_recommendation_fn(scope_aggregate)
        scope_aggregates.append(json_safe_fn(scope_aggregate))

    review_status_counts: dict[str, int] = {}
    for item in scope_aggregates:
        review_status = str(item.get("review_status") or "unknown")
        review_status_counts[review_status] = review_status_counts.get(review_status, 0) + 1

    return json_safe_fn(
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
        "Dieser Report fasst mehrere prospektive Shadow-Läufe zusammen. `insufficient_identity`-Läufe werden nicht als vergleichbar gezaehlt.",
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
