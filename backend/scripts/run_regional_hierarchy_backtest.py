#!/usr/bin/env python3
"""Run a real regional historical backtest and write a hierarchy-focused report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(REPO_ROOT / ".env")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--virus", default="Influenza A", help="Virus type to benchmark.")
    parser.add_argument("--horizon", type=int, default=7, help="Forecast horizon in days.")
    parser.add_argument("--lookback-days", type=int, default=900, help="Training/backtest lookback window.")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist trained artifacts. Default is benchmark-only without touching live artifacts.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "output" / "regional_hierarchy_backtests",
        help="Folder that receives the JSON summary and markdown report.",
    )
    return parser.parse_args()


def _run_id(virus_typ: str, horizon: int) -> str:
    slug = virus_typ.lower().replace(" ", "_").replace("-", "_")
    return f"{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{slug}_h{horizon}"


def _format_metric(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


def _extract_candidate_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidate_rows = (((result.get("benchmark_summary") or {}).get("candidate_summaries")) or [])
    return {
        str(item.get("candidate")): dict(item.get("metrics") or {})
        for item in candidate_rows
    }


def _build_report(result: dict[str, Any]) -> str:
    candidate_map = _extract_candidate_map(result)
    raw_metrics = candidate_map.get("regional_pooled_panel") or {}
    reconciled_metrics = candidate_map.get("regional_pooled_panel_mint") or {}
    hierarchy_meta = result.get("hierarchy_reconciliation") or {}
    hierarchy_diagnostics = ((result.get("benchmark_summary") or {}).get("hierarchy_diagnostics")) or {}
    cluster_homogeneity = ((result.get("benchmark_summary") or {}).get("cluster_homogeneity")) or {}
    hierarchy_benchmark = ((result.get("benchmark_summary") or {}).get("hierarchy_benchmark")) or {}

    lines = [
        "# Regional Hierarchy Backtest",
        "",
        f"- Virus: `{result.get('virus_typ')}`",
        f"- Horizon: `{result.get('horizon_days')}`",
        f"- Generated at: `{datetime.utcnow().isoformat()}`",
        f"- Reconciliation method: `{hierarchy_meta.get('reconciliation_method')}`",
        f"- Consistency status: `{hierarchy_meta.get('hierarchy_consistency_status')}`",
        "",
        "## Candidate Comparison",
        "",
        "| Candidate | WIS | CRPS | Coverage 95 | Winkler 95 | Brier | Utility |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        "| regional_pooled_panel | {wis} | {crps} | {coverage_95} | {winkler_95} | {brier_score} | {decision_utility} |".format(
            **{key: _format_metric(raw_metrics.get(key)) for key in ("wis", "crps", "coverage_95", "winkler_95", "brier_score", "decision_utility")}
        ),
        "| regional_pooled_panel_mint | {wis} | {crps} | {coverage_95} | {winkler_95} | {brier_score} | {decision_utility} |".format(
            **{key: _format_metric(reconciled_metrics.get(key)) for key in ("wis", "crps", "coverage_95", "winkler_95", "brier_score", "decision_utility")}
        ),
        "",
        "## Component Diagnostics",
        "",
        "| Level | Samples | Baseline MAE | Aggregate-Model MAE | Delta | Recommended Blend Weight |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        "| cluster | {samples} | {baseline_mae} | {model_mae} | {mae_delta_model_minus_baseline} | {recommended_blend_weight} |".format(
            **{key: _format_metric((hierarchy_diagnostics.get("cluster") or {}).get(key)) for key in ("samples", "baseline_mae", "model_mae", "mae_delta_model_minus_baseline", "recommended_blend_weight")}
        ),
        "| national | {samples} | {baseline_mae} | {model_mae} | {mae_delta_model_minus_baseline} | {recommended_blend_weight} |".format(
            **{key: _format_metric((hierarchy_diagnostics.get("national") or {}).get(key)) for key in ("samples", "baseline_mae", "model_mae", "mae_delta_model_minus_baseline", "recommended_blend_weight")}
        ),
        "",
        "## Cluster Homogeneity",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Rating | {cluster_homogeneity.get('homogeneity_rating') or '-'} |",
        f"| Evaluation Dates | {_format_metric(cluster_homogeneity.get('evaluation_dates'))} |",
        f"| Mean Within-Cluster Correlation | {_format_metric(cluster_homogeneity.get('within_cluster_corr_mean'))} |",
        f"| Mean Between-Cluster Correlation | {_format_metric(cluster_homogeneity.get('between_cluster_corr_mean'))} |",
        f"| Separation Gap | {_format_metric(cluster_homogeneity.get('separation_gap'))} |",
        f"| State Reassignment Rate | {_format_metric(cluster_homogeneity.get('state_reassignment_rate'))} |",
        f"| Stable States Share | {_format_metric(cluster_homogeneity.get('stable_states_share'))} |",
        "",
        "### Latest Cluster Snapshot",
        "",
        "| Cluster | Members | Within Corr Mean | Incidence Range | Hot State | Hot State Pop Share |",
        "| --- | ---: | ---: | ---: | --- | ---: |",
    ]
    latest_clusters = cluster_homogeneity.get("latest_clusters") or {}
    for cluster_id, payload in sorted(latest_clusters.items()):
        lines.append(
            "| {cluster_id} | {member_count} | {corr} | {incidence_range} | {hot_state} | {hot_share} |".format(
                cluster_id=cluster_id,
                member_count=_format_metric(payload.get("member_count")),
                corr=_format_metric(payload.get("within_cluster_corr_mean")),
                incidence_range=_format_metric(payload.get("current_incidence_range")),
                hot_state=payload.get("hot_state") or "-",
                hot_share=_format_metric(payload.get("hot_state_population_share")),
            )
        )
    if not latest_clusters:
        lines.append("| - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `regional_pooled_panel` ist der rohe regionale Forecast ohne nachträgliche Hierarchie-Abstimmung.",
            "- `regional_pooled_panel_mint` ist derselbe Forecast nach MinT-artiger Reconciliation über Länder, Cluster und national.",
            "- Die Komponentendiagnostik zeigt, ob eher das Cluster- oder das National-Modell gegen die bessere State-Summen-Basis verliert.",
            "- Die Homogenitätsdiagnose zeigt, ob die States innerhalb eines Clusters historisch wirklich ähnlich genug laufen und ob die Cluster stabil bleiben.",
            "- `Recommended Blend Weight` nahe `0` bedeutet: Die zusätzliche Aggregate-Ebene sollte aktuell kaum Einfluss bekommen.",
            "- Benchmark-Entscheidung: `{selection}`.".format(
                selection=hierarchy_benchmark.get("selection_basis") or "unbekannt"
            ),
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    required_env = ("POSTGRES_USER", "POSTGRES_DB", "SECRET_KEY", "OPENWEATHER_API_KEY")
    missing_env = [key for key in required_env if not os.environ.get(key)]
    if "POSTGRES_PASSWORD" not in os.environ:
        missing_env.append("POSTGRES_PASSWORD")
    if missing_env:
        print(
            json.dumps(
                {
                    "status": "missing_environment",
                    "message": "Der Hierarchie-Backtest braucht eine laufende App-Datenbank mit gesetzten Backend-Umgebungsvariablen.",
                    "missing_env": missing_env,
                },
                indent=2,
            )
        )
        return 2

    from app.db.session import get_db_context
    from app.services.ml.regional_trainer import RegionalModelTrainer

    run_id = _run_id(args.virus, int(args.horizon))
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    with get_db_context() as db:
        trainer = RegionalModelTrainer(db)
        result = trainer.train_all_regions(
            virus_typ=args.virus,
            lookback_days=int(args.lookback_days),
            persist=bool(args.persist),
            horizon_days=int(args.horizon),
        )

    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(json.dumps(result, indent=2, default=str))
    report_path.write_text(_build_report(result))

    print(json.dumps({"run_id": run_id, "summary": str(summary_path), "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
