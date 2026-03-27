#!/usr/bin/env python3
"""Run the small end-to-end weather vintage comparison matrix and write JSON/Markdown reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import get_db_context
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_vintage_comparison import (
    DEFAULT_WEATHER_VINTAGE_COMPARISON_HORIZONS,
    DEFAULT_WEATHER_VINTAGE_COMPARISON_VIRUS_TYPES,
    WeatherVintageComparisonRunner,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--virus",
        dest="viruses",
        action="append",
        choices=list(SUPPORTED_VIRUS_TYPES),
        help="Run only the selected virus type. Can be passed multiple times.",
    )
    parser.add_argument(
        "--horizon",
        dest="horizons",
        action="append",
        type=int,
        choices=list(SUPPORTED_FORECAST_HORIZONS),
        help="Run only the selected horizon. Can be passed multiple times.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=900,
        help="Historical training window used for every comparison scope.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(BACKEND_ROOT) / "app" / "ml_models" / "weather_vintage_comparison",
        help="Directory where the JSON and Markdown reports will be written.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional explicit path for the JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional explicit path for the Markdown report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    selected_viruses = args.viruses or list(DEFAULT_WEATHER_VINTAGE_COMPARISON_VIRUS_TYPES)
    selected_horizons = args.horizons or list(DEFAULT_WEATHER_VINTAGE_COMPARISON_HORIZONS)
    json_output = args.json_output or (args.output_root / "weather_vintage_comparison_report.json")
    markdown_output = args.markdown_output or (args.output_root / "weather_vintage_comparison_report.md")

    with get_db_context() as db:
        runner = WeatherVintageComparisonRunner(db)
        report = runner.run(
            virus_types=selected_viruses,
            horizon_days_list=selected_horizons,
            lookback_days=args.lookback_days,
            output_json=json_output,
            output_markdown=markdown_output,
        )

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
