#!/usr/bin/env python3
"""Run the RSV A / h7 live evaluation path against the real ViralFlux database."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

LIVE_EVAL_VIRUS = "RSV A"
LIVE_EVAL_HORIZON = 7
LIVE_EVAL_PRESET = "rsv_ranking"
DEFAULT_OUTPUT_ROOT = BACKEND_ROOT / "app" / "ml_models" / "regional_panel_h7_live_evaluation"
ARCHIVE_PREFIX = "rsv_a_h7_rsv_ranking"
REQUIRED_METRICS = (
    "precision_at_top3",
    "activation_false_positive_rate",
    "ece",
    "brier_score",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Persistent artifact root that will contain timestamped RSV h7 evaluation archives.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional archive folder name. A UTC timestamp with a short suffix is used by default.",
    )
    return parser.parse_args()


def _make_run_id(value: str | None = None) -> str:
    if value:
        safe_value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
        safe_value = safe_value.strip("._-")
        if safe_value:
            return safe_value
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{uuid4().hex[:8]}"


def _git_commit_sha(repo_root: Path) -> str | None:
    candidates = (repo_root, repo_root.parent, repo_root / "app")
    for candidate in candidates:
        try:
            result = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            continue
        sha = result.stdout.strip()
        if sha:
            return sha
    return None


def _format_number(value: Any, digits: int = 6) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _gate_outcome_detail(row: dict[str, Any]) -> str:
    raw_outcome = str(row.get("gate_outcome") or "").strip() or "-"
    if raw_outcome not in {"GO", "WATCH"}:
        return raw_outcome

    gate_summary = row.get("gate_summary") or {}
    if raw_outcome == "GO":
        return "GO"

    failed_checks = [
        str(item).strip()
        for item in (gate_summary.get("failed_checks") or [])
        if str(item).strip()
    ]
    if not failed_checks:
        return "WATCH"
    return f"WATCH ({', '.join(failed_checks)})"


def _comparison_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in summary.get("comparison_table") or []:
        row = dict(raw_row or {})
        metrics = dict(row.get("metrics") or {})
        precision_at_top3 = metrics.get("precision_at_top3", row.get("precision_at_top3"))
        activation_false_positive_rate = metrics.get(
            "activation_false_positive_rate",
            row.get("activation_false_positive_rate"),
        )
        ece = metrics.get("ece", row.get("ece"))
        brier_score = metrics.get("brier_score", row.get("brier_score"))
        comparison_row = {
            "role": str(row.get("source") or "experiment"),
            "name": row.get("name"),
            "calibration_version": row.get("calibration_version"),
            "precision_at_top3": precision_at_top3,
            "activation_false_positive_rate": activation_false_positive_rate,
            "ece": ece,
            "brier": brier_score,
            "brier_score": brier_score,
            "calibration_mode": row.get("calibration_mode") or row.get("selected_calibration_mode"),
            "gate_outcome": _gate_outcome_detail(row),
            "gate_outcome_raw": row.get("gate_outcome"),
            "retained": row.get("retained"),
            "retention_reason": row.get("retention_reason"),
            "delta_vs_baseline": row.get("delta_vs_baseline") or {},
            "status": row.get("status"),
            "artifact_dir": row.get("artifact_dir"),
            "feature_selection": row.get("feature_selection"),
            "recency_weight_half_life_days": row.get("recency_weight_half_life_days"),
            "signal_agreement_weight": row.get("signal_agreement_weight"),
            "pr_auc": metrics.get("pr_auc", row.get("pr_auc")),
        }
        rows.append(comparison_row)
    return rows


def _selected_experiment_row(
    rows: list[dict[str, Any]],
    *,
    preferred_names: tuple[str | None, ...] = (),
) -> dict[str, Any] | None:
    experiments = [row for row in rows if row.get("role") != "baseline"]
    if not experiments:
        return None
    for preferred_name in preferred_names:
        if not preferred_name:
            continue
        match = next((row for row in experiments if row.get("name") == preferred_name), None)
        if match is not None:
            return match
    retained = [row for row in experiments if row.get("retained")]
    if retained:
        return retained[0]
    return experiments[0]


def _verify_required_files(archive_dir: Path, required_names: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for name in required_names:
        if not (archive_dir / name).exists():
            missing.append(name)
    return missing


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "role",
        "variant",
        "precision_at_top3",
        "activation_false_positive_rate",
        "ece",
        "brier",
        "calibration_mode",
        "gate_outcome",
        "retained",
        "delta_precision_at_top3",
        "delta_activation_false_positive_rate",
        "delta_ece",
        "delta_brier",
    ]
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines = [header_line, separator_line]
    for row in rows:
        delta = dict(row.get("delta_vs_baseline") or {})
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("role") or "-"),
                    str(row.get("name") or "-"),
                    _format_number(row.get("precision_at_top3")),
                    _format_number(row.get("activation_false_positive_rate")),
                    _format_number(row.get("ece")),
                    _format_number(row.get("brier")),
                    str(row.get("calibration_mode") or "-"),
                    str(row.get("gate_outcome") or "-"),
                    str(bool(row.get("retained"))),
                    _format_number(delta.get("precision_at_top3")),
                    _format_number(delta.get("activation_false_positive_rate")),
                    _format_number(delta.get("ece")),
                    _format_number(delta.get("brier_score")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _build_report(
    *,
    summary: dict[str, Any],
    run_id: str,
    archive_dir: Path,
    summary_path: Path,
    report_path: Path,
    manifest_path: Path,
    artifacts_dir: Path,
    audit_payload: dict[str, Any] | None,
    audit_error: str | None,
) -> dict[str, Any]:
    virus_summary = (summary.get("viruses") or {}).get(LIVE_EVAL_VIRUS) or {}
    comparison_rows = _comparison_rows(virus_summary)
    baseline = next((row for row in comparison_rows if row.get("role") == "baseline"), None)
    experiments = [row for row in comparison_rows if row.get("role") != "baseline"]
    best_experiment_name = virus_summary.get("best_experiment")
    best_retained_experiment_name = virus_summary.get("best_retained_experiment")
    selected_experiment = _selected_experiment_row(
        comparison_rows,
        preferred_names=(best_retained_experiment_name, best_experiment_name),
    )

    report = {
        "status": summary.get("status"),
        "summary_status": summary.get("status"),
        "run_id": run_id,
        "generated_at": summary.get("generated_at"),
        "preset": LIVE_EVAL_PRESET,
        "virus_typ": LIVE_EVAL_VIRUS,
        "horizon_days": LIVE_EVAL_HORIZON,
        "archive_dir": str(archive_dir),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
        "manifest_path": str(manifest_path),
        "artifacts_dir": str(artifacts_dir),
        "baseline_models_dir": summary.get("baseline_models_dir"),
        "experiment_models_dir": summary.get("experiment_models_dir"),
        "selected_experiment": selected_experiment,
        "selected_experiment_name": selected_experiment.get("name") if selected_experiment else None,
        "selected_experiment_artifact_path": (
            selected_experiment.get("artifact_dir") if selected_experiment else None
        ),
        "selected_experiment_calibration_version": (
            selected_experiment.get("calibration_version") if selected_experiment else None
        ),
        "selected_experiment_calibration_mode": (
            selected_experiment.get("calibration_mode") if selected_experiment else None
        ),
        "selected_experiment_gate_outcome": (
            selected_experiment.get("gate_outcome") if selected_experiment else None
        ),
        "selected_experiment_retained": (
            selected_experiment.get("retained") if selected_experiment else None
        ),
        "best_experiment": virus_summary.get("best_experiment"),
        "best_retained_experiment": virus_summary.get("best_retained_experiment"),
        "best_experiment_name": best_experiment_name,
        "best_retained_experiment_name": best_retained_experiment_name,
        "baseline_artifact_path": baseline.get("artifact_dir") if baseline else None,
        "baseline_artifact_version": baseline.get("calibration_version") if baseline else None,
        "baseline_calibration_mode": baseline.get("calibration_mode") if baseline else None,
        "baseline_gate_outcome": baseline.get("gate_outcome") if baseline else None,
        "baseline_retained": baseline.get("retained") if baseline else None,
        "experiment_artifact_path": (
            selected_experiment.get("artifact_dir") if selected_experiment else None
        ),
        "experiment_artifact_version": (
            selected_experiment.get("calibration_version") if selected_experiment else None
        ),
        "calibration_mode": selected_experiment.get("calibration_mode") if selected_experiment else None,
        "gate_outcome": selected_experiment.get("gate_outcome") if selected_experiment else None,
        "retained": selected_experiment.get("retained") if selected_experiment else None,
        "baseline": baseline,
        "experiments": experiments,
        "comparison_table": comparison_rows,
        "audit_payload": audit_payload,
        "audit_error": audit_error,
    }

    report_md = [
        "# RSV A / h7 Live Evaluation",
        "",
        f"- run_id: `{run_id}`",
        f"- generated_at: `{summary.get('generated_at')}`",
        f"- summary_status: `{summary.get('status')}`",
        f"- preset: `{LIVE_EVAL_PRESET}`",
        f"- track: `{LIVE_EVAL_PRESET}`",
        f"- virus_typ: `{LIVE_EVAL_VIRUS}`",
        f"- virus: `{LIVE_EVAL_VIRUS}`",
        f"- horizon_days: `{LIVE_EVAL_HORIZON}`",
        f"- horizon: `{LIVE_EVAL_HORIZON}`",
        f"- archive_dir: `{archive_dir}`",
        f"- summary_json: `{summary_path}`",
        f"- report_json: `{report_path}`",
        f"- artifacts_dir: `{artifacts_dir}`",
        f"- best_experiment: `{virus_summary.get('best_experiment')}`",
        f"- best_retained_experiment: `{virus_summary.get('best_retained_experiment')}`",
        f"- best_experiment_name: `{best_experiment_name}`",
        f"- best_retained_experiment_name: `{best_retained_experiment_name}`",
        f"- selected_experiment: `{selected_experiment.get('name') if selected_experiment else None}`",
        "",
        "## Baseline Vs Experiment",
        "",
        _markdown_table(comparison_rows),
        "",
        "## Quick Decision Template",
        "",
        "- decision: `GO` / `WATCH` / `NO_GO`",
        "- retained_experiment: `yes` / `no`",
        "- winning_variant: `<name or none>`",
        "- reason: `<short note on precision, false positives, and calibration>`",
        "- next_step: `<promote, hold, or rerun>`",
        "",
        "Decision heuristic:",
        "",
        "- `GO` only when the chosen experiment is retained and the gate outcome is `GO`.",
        "- `WATCH` when the experiment improves honestly but the gate still says `WATCH`.",
        "- `NO_GO` when `precision_at_top3` does not improve or calibration / false positives regress.",
        "",
    ]
    if audit_error:
        report_md.extend(
            [
                "## Audit Trail",
                "",
                f"- audit_status: `failed`",
                f"- audit_error: `{audit_error}`",
                "",
            ]
        )
    elif audit_payload is not None:
        report_md.extend(
            [
                "## Audit Trail",
                "",
                f"- audit_status: `recorded`",
                f"- audit_run_id: `{audit_payload.get('run_id')}`",
                f"- audit_action: `{audit_payload.get('action')}`",
                f"- audit_status_label: `{audit_payload.get('status')}`",
                "",
            ]
        )

    report["report_md"] = "\n".join(report_md).rstrip() + "\n"
    return report


def _required_fields_present(report: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if report.get("status") != "success":
        issues.append(f"summary_status={report.get('status')}")
    baseline = report.get("baseline") or {}
    if str(baseline.get("status") or "") != "available":
        issues.append(f"baseline_status={baseline.get('status')}")
    for key in (
        "baseline_artifact_path",
        "baseline_artifact_version",
        "experiment_artifact_path",
        "experiment_artifact_version",
        "calibration_mode",
        "gate_outcome",
        "retained",
    ):
        if report.get(key) is None:
            issues.append(f"{key}_missing")
    rows = list(report.get("comparison_table") or [])
    if len(rows) < 2:
        issues.append("comparison_rows_missing")
    for row in rows:
        for key in REQUIRED_METRICS + ("calibration_mode", "gate_outcome", "retained"):
            if row.get(key) is None:
                issues.append(f"{row.get('name') or 'row'}:{key}_missing")
    return (len(issues) == 0), issues


def main() -> int:
    args = _parse_args()
    started_at = datetime.utcnow().isoformat()
    run_id = _make_run_id(args.run_id)
    archive_dir = args.output_root / ARCHIVE_PREFIX / run_id
    archive_dir.mkdir(parents=True, exist_ok=False)

    summary_path = archive_dir / "summary.json"
    report_path = archive_dir / "report.json"
    manifest_path = archive_dir / "run_manifest.json"
    error_path = archive_dir / "error.json"
    error_md_path = archive_dir / "error.md"
    required_files = ("summary.json", "report.json", "report.md", "run_manifest.json")
    artifacts_dir = archive_dir / "artifacts"
    git_sha = _git_commit_sha(BACKEND_ROOT)

    manifest = {
        "run_id": run_id,
        "status": "starting",
        "started_at": started_at,
        "generated_at": started_at,
        "finished_at": None,
        "preset": LIVE_EVAL_PRESET,
        "track": LIVE_EVAL_PRESET,
        "virus_typ": LIVE_EVAL_VIRUS,
        "virus": LIVE_EVAL_VIRUS,
        "horizon_days": LIVE_EVAL_HORIZON,
        "horizon": LIVE_EVAL_HORIZON,
        "output_root": str(args.output_root),
        "archive_dir": str(archive_dir),
        "artifact_path": str(artifacts_dir),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
        "report_md_path": str(archive_dir / "report.md"),
        "run_manifest_path": str(manifest_path),
        "artifacts_dir": str(artifacts_dir),
        "baseline_models_dir": str(BACKEND_ROOT / "app" / "ml_models" / "regional_panel"),
        "experiment_models_dir": str(artifacts_dir),
        "git_commit_sha": git_sha,
        "files_required": list(required_files),
        "files_written": [],
        "verification_passed": False,
        "verification_issues": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

    try:
        from app.db.session import get_db_context
        from app.services.ml.h7_pilot_training import (
            H7PilotExperimentRunner,
            default_h7_rsv_ranking_specs_by_virus,
        )
        from app.services.ops.run_metadata_service import OperationalRunRecorder

        spec_map = default_h7_rsv_ranking_specs_by_virus([LIVE_EVAL_VIRUS])

        audit_payload: dict[str, Any] | None = None
        audit_error: str | None = None
        with get_db_context() as db:
            runner = H7PilotExperimentRunner(
                db,
                experiment_models_dir=artifacts_dir,
            )
            summary = runner.run(
                virus_types=[LIVE_EVAL_VIRUS],
                specs_by_virus=spec_map,
                summary_output=summary_path,
            )
            try:
                audit_payload = OperationalRunRecorder(db).record_event(
                    action="RSV_H7_LIVE_EVALUATION",
                    status=str(summary.get("status") or "unknown"),
                    summary="RSV A / h7 live evaluation archive generated.",
                    metadata={
                        "preset": LIVE_EVAL_PRESET,
                        "virus_typ": LIVE_EVAL_VIRUS,
                        "horizon_days": LIVE_EVAL_HORIZON,
                        "run_id": run_id,
                        "summary_path": str(summary_path),
                        "report_path": str(report_path),
                        "archive_dir": str(archive_dir),
                        "experiment_models_dir": str(artifacts_dir),
                        "baseline_models_dir": manifest["baseline_models_dir"],
                    },
                )
            except Exception as exc:  # best-effort audit trail
                audit_error = str(exc)

        report = _build_report(
            summary=summary,
            run_id=run_id,
            archive_dir=archive_dir,
            summary_path=summary_path,
            report_path=report_path,
            manifest_path=manifest_path,
            artifacts_dir=artifacts_dir,
            audit_payload=audit_payload,
            audit_error=audit_error,
        )
        report_ok, issues = _required_fields_present(report)
        report["validation"] = {
            "passed": report_ok,
            "issues": issues,
        }
        report["status"] = "success" if report_ok else "partial_error"
        validation_lines = [
            "",
            "## Validation",
            "",
            f"- passed: `{str(report_ok).lower()}`",
            f"- issues: `{', '.join(issues) if issues else 'none'}`",
            "",
        ]
        report["report_md"] = report["report_md"].rstrip() + "\n" + "\n".join(validation_lines)
        report_path.write_text(json.dumps(report, indent=2, default=str))
        report_md_path = archive_dir / "report.md"
        report_md_path.write_text(report["report_md"])
        selection_row = report.get("selected_experiment") or {}
        final_status = "success" if report_ok else "partial_error"
        manifest.update(
            {
                "selected_experiment_name": selection_row.get("name"),
                "selected_experiment_artifact_path": selection_row.get("artifact_dir"),
                "selected_experiment_calibration_version": selection_row.get("calibration_version"),
                "selected_experiment_calibration_mode": selection_row.get("calibration_mode"),
                "selected_experiment_gate_outcome": selection_row.get("gate_outcome"),
                "selected_experiment_retained": selection_row.get("retained"),
                "best_experiment_name": report.get("best_experiment_name"),
                "best_retained_experiment_name": report.get("best_retained_experiment_name"),
                "baseline_artifact_path": (report.get("baseline") or {}).get("artifact_dir"),
                "baseline_artifact_version": (report.get("baseline") or {}).get("calibration_version"),
                "baseline_calibration_mode": (report.get("baseline") or {}).get("calibration_mode"),
                "baseline_gate_outcome": (report.get("baseline") or {}).get("gate_outcome"),
                "baseline_retained": (report.get("baseline") or {}).get("retained"),
                "experiment_artifact_path": selection_row.get("artifact_dir"),
                "experiment_artifact_version": selection_row.get("calibration_version"),
                "calibration_mode": selection_row.get("calibration_mode"),
                "gate_outcome": selection_row.get("gate_outcome"),
                "retained": selection_row.get("retained"),
                "finished_at": datetime.utcnow().isoformat(),
                "status": final_status,
            }
        )
        files_written = [summary_path, report_path, report_md_path, manifest_path]
        missing_files = _verify_required_files(archive_dir, required_files)
        manifest.update(
            {
                "files_written": [str(path) for path in files_written],
                "verification_passed": not missing_files,
                "verification_issues": missing_files,
            }
        )
        if missing_files:
            manifest["status"] = "error"
            manifest["verification_error"] = f"Missing required output files: {', '.join(missing_files)}"
        elif not report_ok:
            manifest["status"] = "partial_error"
        report["status"] = "error" if missing_files else final_status
        report_path.write_text(json.dumps(report, indent=2, default=str))
        manifest.update(
            {
                "issues": issues,
                "summary_status": summary.get("status"),
                "best_experiment": report.get("best_experiment"),
                "best_retained_experiment": report.get("best_retained_experiment"),
                "audit_status": "recorded" if audit_payload is not None else "failed",
                "audit_error": audit_error,
            }
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
        if missing_files:
            print(json.dumps({"status": "error", "missing_files": missing_files}, indent=2), file=sys.stderr)
            return 2
        print(report["report_md"])
        return 0 if report_ok else 1
    except Exception as exc:
        error_payload = {
            "status": "error",
            "run_id": run_id,
            "preset": LIVE_EVAL_PRESET,
            "virus_typ": LIVE_EVAL_VIRUS,
            "horizon_days": LIVE_EVAL_HORIZON,
            "archive_dir": str(archive_dir),
            "summary_path": str(summary_path),
            "report_path": str(report_path),
            "manifest_path": str(manifest_path),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        error_path.write_text(json.dumps(error_payload, indent=2, default=str))
        error_md_path.write_text(
            "\n".join(
                [
                    "# RSV A / h7 Live Evaluation Failed",
                    "",
                    f"- run_id: `{run_id}`",
                    f"- error_type: `{type(exc).__name__}`",
                    f"- error: `{exc}`",
                    f"- archive_dir: `{archive_dir}`",
                    "",
                ]
            )
        )
        manifest.update(
            {
                "status": "error",
                "finished_at": datetime.utcnow().isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
        print(json.dumps(error_payload, indent=2, default=str), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
