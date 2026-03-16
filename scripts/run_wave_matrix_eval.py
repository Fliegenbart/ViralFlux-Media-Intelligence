#!/usr/bin/env python3
"""Run the wave-v1 backtest harness across a pathogen/region matrix."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from itertools import product
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKTEST_SCRIPT = REPO_ROOT / "scripts" / "run_wave_v1_backtest.py"

DEFAULT_PATHOGENS = ["Influenza A", "SARS-CoV-2"]
DEFAULT_REGIONS = ["BY", "HH"]

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pathogens = _parse_csv_list(args.pathogens) or DEFAULT_PATHOGENS
    regions = _parse_csv_list(args.regions) or DEFAULT_REGIONS

    summary_rows: list[dict[str, object]] = []
    for pathogen, region in product(pathogens, regions):
        combo_dir = output_dir / f"{_slugify(pathogen)}__{region.lower()}"
        combo_dir.mkdir(parents=True, exist_ok=True)
        print(f"RUN {pathogen} / {region}", flush=True)
        command = [
            sys.executable,
            str(BACKTEST_SCRIPT),
            "--source",
            args.source,
            "--pathogen",
            pathogen,
            "--region",
            region,
            "--horizon",
            str(args.horizon),
            "--output-dir",
            str(combo_dir),
        ]
        if args.source == "fixture":
            command.extend(["--fixture", args.fixture])

        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.stdout:
            print(completed.stdout.strip(), flush=True)
        if completed.stderr:
            print(completed.stderr.strip(), file=sys.stderr, flush=True)

        summary_rows.append(
            _build_summary_row(
                pathogen=pathogen,
                region=region,
                combo_dir=combo_dir,
                exit_code=completed.returncode,
            )
        )

    summary_rows.sort(
        key=lambda row: (
            1 if row.get("status") != "ok" else 0,
            -float(row.get("f1") or 0.0),
            -float(row.get("pr_auc") or 0.0),
        )
    )
    _write_json(output_dir / "summary.json", summary_rows)
    _write_csv(output_dir / "summary.csv", summary_rows)
    print(f"SUMMARY_WRITTEN {output_dir}", flush=True)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the wave-v1 harness across a matrix.")
    parser.add_argument("--source", choices=["db", "fixture"], default="db")
    parser.add_argument("--fixture", default="default")
    parser.add_argument(
        "--pathogens",
        help="Comma-separated pathogen names. Defaults to the current pilot scope (Influenza A,SARS-CoV-2).",
    )
    parser.add_argument(
        "--regions",
        help="Comma-separated region codes. Defaults to the current pilot scope (BY,HH).",
    )
    parser.add_argument("--horizon", type=int, default=14)
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "data" / "processed" / "wave_matrix_eval" / datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")),
    )
    return parser.parse_args(argv)


def _resolve_output_dir(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _slugify(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _build_summary_row(
    *,
    pathogen: str,
    region: str,
    combo_dir: Path,
    exit_code: int,
) -> dict[str, object]:
    fold_path = combo_dir / "fold_metrics.json"
    panel_path = combo_dir / "panel_summary.json"
    row: dict[str, object] = {
        "pathogen": pathogen,
        "region": region,
        "exit_code": int(exit_code),
        "status": "error",
        "artifact_dir": str(combo_dir),
    }

    fold_metrics = _read_json_if_exists(fold_path)
    panel_summary = _read_json_if_exists(panel_path)
    if panel_summary:
        row["rows"] = panel_summary.get("rows")
        row["positive_rows"] = panel_summary.get("positive_rows")
        row["positive_rate"] = panel_summary.get("positive_rate")
        row["source_coverage"] = panel_summary.get("source_coverage")

    if not fold_metrics:
        row["error"] = "Missing fold_metrics.json"
        return row

    row["status"] = fold_metrics.get("status") or ("ok" if exit_code == 0 else "error")
    if row["status"] != "ok":
        row["error"] = fold_metrics.get("error") or f"Backtest exited with code {exit_code}"
        return row

    aggregate = fold_metrics.get("aggregate_metrics") or {}
    calibration = fold_metrics.get("calibration_summary") or {}
    for key in [
        "mae",
        "rmse",
        "pr_auc",
        "brier_score",
        "precision",
        "recall",
        "f1",
        "ece",
        "false_alarm_rate",
        "tp",
        "fp",
        "tn",
        "fn",
    ]:
        row[key] = aggregate.get(key)
    row["decision_output_field"] = calibration.get("decision_output_field")
    row["mixed_fold_outputs"] = calibration.get("mixed_fold_outputs")
    return row


def _read_json_if_exists(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
