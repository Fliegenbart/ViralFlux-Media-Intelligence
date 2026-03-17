from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_rsv_h7_live_evaluation.py"
SPEC = importlib.util.spec_from_file_location("run_rsv_h7_live_evaluation", SCRIPT_PATH)
assert SPEC and SPEC.loader
run_rsv_h7_live_evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_rsv_h7_live_evaluation)


def _sample_summary() -> dict[str, object]:
    return {
        "status": "success",
        "generated_at": "2026-03-17T00:00:00Z",
        "baseline_models_dir": "/baseline",
        "experiment_models_dir": "/experiment",
        "viruses": {
            "RSV A": {
                "best_experiment": "rsv_signal_core",
                "best_retained_experiment": "rsv_signal_core",
                "comparison_table": [
                    {
                        "source": "baseline",
                        "name": "live_baseline",
                        "status": "available",
                        "artifact_dir": "/baseline/artifact",
                        "calibration_version": "base:v1",
                        "calibration_mode": "raw_passthrough",
                        "gate_outcome": "WATCH",
                        "retained": True,
                        "metrics": {
                            "precision_at_top3": 0.5,
                            "activation_false_positive_rate": 0.01,
                            "ece": 0.03,
                            "brier_score": 0.04,
                            "pr_auc": 0.6,
                        },
                        "gate_summary": {"failed_checks": ["precision_at_top3_passed"]},
                    },
                    {
                        "source": "experiment",
                        "name": "rsv_signal_core",
                        "status": "success",
                        "artifact_dir": "/experiment/artifact",
                        "calibration_version": "exp:v1",
                        "calibration_mode": "raw_passthrough",
                        "gate_outcome": "WATCH",
                        "retained": True,
                        "metrics": {
                            "precision_at_top3": 0.55,
                            "activation_false_positive_rate": 0.009,
                            "ece": 0.029,
                            "brier_score": 0.038,
                            "pr_auc": 0.61,
                        },
                        "gate_summary": {"failed_checks": ["precision_at_top3_passed"]},
                    },
                ],
            }
        },
    }


def test_build_report_exports_persistent_selection_fields(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    report = run_rsv_h7_live_evaluation._build_report(
        summary=_sample_summary(),
        run_id="smoke",
        archive_dir=archive_dir,
        summary_path=archive_dir / "summary.json",
        report_path=archive_dir / "report.json",
        manifest_path=archive_dir / "run_manifest.json",
        artifacts_dir=archive_dir / "artifacts",
        audit_payload=None,
        audit_error=None,
    )

    assert report["selected_experiment_name"] == "rsv_signal_core"
    assert report["selected_experiment_calibration_version"] == "exp:v1"
    assert report["baseline_artifact_version"] == "base:v1"
    assert report["experiment_artifact_version"] == "exp:v1"
    assert report["calibration_mode"] == "raw_passthrough"
    assert report["gate_outcome"] == "WATCH (precision_at_top3_passed)"
    assert report["retained"] is True

    ok, issues = run_rsv_h7_live_evaluation._required_fields_present(report)
    assert ok is True
    assert issues == []
