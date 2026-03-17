#!/usr/bin/env python3
"""Backfill regional multi-horizon model artifacts for release preparation."""

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
from app.services.ml.regional_trainer import RegionalTrainer
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.run_metadata_service import OperationalRunRecorder


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
    parser.add_argument("--lookback-days", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    virus_types = args.viruses or list(SUPPORTED_VIRUS_TYPES)
    horizons = args.horizons or list(SUPPORTED_FORECAST_HORIZONS)

    with get_db_context() as db:
        trainer = RegionalTrainer(db)
        results = trainer.train_selected_viruses_all_regions(
            virus_types=virus_types,
            lookback_days=args.lookback_days,
            horizon_days_list=horizons,
        )
        run_metadata = OperationalRunRecorder(db).record_event(
            action="BACKFILL_REGIONAL_MODEL_ARTIFACTS",
            status="success",
            summary="Regional multi-horizon artifacts backfilled.",
            metadata={
                "virus_types": virus_types,
                "horizons": horizons,
                "lookback_days": args.lookback_days,
                "results": results,
            },
        )

    payload = {
        "status": "success",
        "virus_types": virus_types,
        "horizons": horizons,
        "results": results,
        "run_metadata": run_metadata,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
