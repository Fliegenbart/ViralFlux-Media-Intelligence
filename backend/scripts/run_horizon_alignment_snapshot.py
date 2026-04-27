#!/usr/bin/env python3
"""Build a conservative h5+h7 regional horizon alignment snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.regional_horizon_alignment import build_horizon_alignment_snapshot
from app.services.ml.regional_live_shift_snapshot import RegionalLiveShiftSnapshotService


DEFAULT_VIRUSES = ("Influenza A", "Influenza B", "RSV A")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--virus", dest="viruses", action="append", choices=list(DEFAULT_VIRUSES))
    parser.add_argument("--brand", default="gelo")
    parser.add_argument("--top-n", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    viruses = args.viruses or list(DEFAULT_VIRUSES)
    with SessionLocal() as db:
        h5_snapshot = RegionalLiveShiftSnapshotService(db).build_snapshot(
            virus_types=viruses,
            horizon_days=5,
            top_n=args.top_n,
            brand=args.brand,
        )
        forecast_service = RegionalForecastService(db)
        h7_forecasts = {
            virus: forecast_service.predict_all_regions(
                virus_typ=virus,
                brand=args.brand,
                horizon_days=7,
            )
            for virus in viruses
        }
        payload = build_horizon_alignment_snapshot(
            h5_snapshot=h5_snapshot,
            h7_forecasts=h7_forecasts,
        )

    print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
