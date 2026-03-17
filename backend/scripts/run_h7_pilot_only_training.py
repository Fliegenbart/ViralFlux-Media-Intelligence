#!/usr/bin/env python3
"""Run the targeted h7-only pilot training path and optional influenza calibration experiments."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DAY_ONE_PILOT_VIRUS_TYPES = (
    "Influenza A",
    "Influenza B",
    "RSV A",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=("pilot_baseline", "influenza_calibration"),
        default="pilot_baseline",
        help="Choose the baseline-only pilot path or the focused Influenza A/B calibration experiments.",
    )
    parser.add_argument(
        "--virus",
        dest="viruses",
        action="append",
        choices=list(DAY_ONE_PILOT_VIRUS_TYPES),
        help="Run only the selected day-one pilot virus. Can be passed multiple times.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Override lookback_days for every selected experiment spec.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(BACKEND_ROOT) / "ml_models" / "regional_panel_h7_pilot_only",
        help="Separate artifact root for pilot-only runs.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional path for the JSON summary output.",
    )
    return parser.parse_args()


def _specs_for_args(args: argparse.Namespace):
    from app.services.ml.h7_pilot_training import (
        default_h7_influenza_calibration_specs_by_virus,
        default_h7_pilot_specs_by_virus,
    )

    if args.preset == "influenza_calibration":
        viruses = args.viruses or ["Influenza A", "Influenza B"]
        spec_map = default_h7_influenza_calibration_specs_by_virus(viruses)
    else:
        viruses = args.viruses or list(DAY_ONE_PILOT_VIRUS_TYPES)
        spec_map = default_h7_pilot_specs_by_virus(viruses)

    if args.lookback_days is None:
        return list(viruses), spec_map

    adjusted = {
        virus_typ: tuple(
            replace(spec, lookback_days=int(args.lookback_days))
            for spec in specs
        )
        for virus_typ, specs in spec_map.items()
    }
    return list(viruses), adjusted


def main() -> int:
    args = _parse_args()
    viruses, spec_map = _specs_for_args(args)
    summary_output = args.summary_output or (args.output_root / f"{args.preset}_summary.json")

    from app.db.session import get_db_context
    from app.services.ml.h7_pilot_training import H7PilotExperimentRunner

    with get_db_context() as db:
        runner = H7PilotExperimentRunner(
            db,
            experiment_models_dir=args.output_root,
        )
        summary = runner.run(
            virus_types=viruses,
            specs_by_virus=spec_map,
            summary_output=summary_output,
        )

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
