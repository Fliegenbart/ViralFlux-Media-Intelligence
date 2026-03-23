from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ml.benchmarking.contracts import BenchmarkArtifactSummary


def write_benchmark_artifacts(
    *,
    output_dir: Path,
    summary: BenchmarkArtifactSummary,
    diagnostics: list[dict[str, Any]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.json"
    leaderboard_path = output_dir / "leaderboard.json"
    diagnostics_path = output_dir / "fold_diagnostics.json"
    report_path = output_dir / "report.md"

    summary_payload = summary.to_dict()
    summary_payload["diagnostics_path"] = str(diagnostics_path)
    summary_path.write_text(json.dumps(summary_payload, indent=2, default=str))
    leaderboard_path.write_text(json.dumps(summary.leaderboard, indent=2, default=str))
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2, default=str))
    report_path.write_text(render_markdown_report(summary_payload))

    return {
        "summary": str(summary_path),
        "leaderboard": str(leaderboard_path),
        "diagnostics": str(diagnostics_path),
        "report": str(report_path),
    }


def render_markdown_report(summary: dict[str, Any]) -> str:
    leaderboard = summary.get("leaderboard") or []
    lines = [
        "# Forecast Benchmark Report",
        "",
        f"- Virus: `{summary.get('virus_typ')}`",
        f"- Horizon: `{summary.get('horizon_days')}`",
        f"- Primary metric: `{summary.get('primary_metric')}`",
        f"- Champion: `{summary.get('champion_name')}`",
        f"- Generated at: `{summary.get('generated_at')}`",
        "",
        "## Leaderboard",
        "",
        "| Candidate | Relative WIS | Coverage 95 | Brier | Utility | Samples |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in leaderboard:
        lines.append(
            "| {candidate} | {relative_wis} | {coverage_95} | {brier_score} | {decision_utility} | {samples} |".format(
                candidate=row.get("candidate"),
                relative_wis=row.get("relative_wis"),
                coverage_95=row.get("coverage_95"),
                brier_score=row.get("brier_score"),
                decision_utility=row.get("decision_utility"),
                samples=row.get("samples"),
            )
        )
    return "\n".join(lines) + "\n"
