#!/usr/bin/env python3
"""Recompute regional forecast, allocation and recommendation outputs for ops validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import get_db_context
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS, ensure_supported_horizon
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.run_metadata_service import OperationalRunRecorder


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--virus",
        default="Influenza A",
        choices=list(SUPPORTED_VIRUS_TYPES),
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=7,
        choices=list(SUPPORTED_FORECAST_HORIZONS),
    )
    parser.add_argument("--weekly-budget-eur", type=float, default=50000.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    horizon_days = ensure_supported_horizon(args.horizon)

    with get_db_context() as db:
        service = RegionalForecastService(db)
        forecast = service.predict_all_regions(
            virus_typ=args.virus,
            horizon_days=horizon_days,
        )
        allocation = service.generate_media_allocation(
            virus_typ=args.virus,
            weekly_budget_eur=args.weekly_budget_eur,
            horizon_days=horizon_days,
        )
        recommendations = service.generate_campaign_recommendations(
            virus_typ=args.virus,
            weekly_budget_eur=args.weekly_budget_eur,
            horizon_days=horizon_days,
            top_n=args.top_n,
        )
        validation = service.get_validation_summary(
            virus_typ=args.virus,
            brand="gelo",
            horizon_days=horizon_days,
        )
        payload = {
            "status": "success",
            "virus_typ": args.virus,
            "horizon_days": horizon_days,
            "forecast_status": forecast.get("status", "ok"),
            "forecast_regions": len(forecast.get("predictions") or []),
            "allocation_status": allocation.get("status", "ok"),
            "allocation_regions": len(allocation.get("recommendations") or []),
            "recommendation_status": recommendations.get("status", "ok"),
            "recommendation_count": len(recommendations.get("recommendations") or []),
            "validation": validation,
        }
        run_metadata = OperationalRunRecorder(db).record_event(
            action="RECOMPUTE_OPERATIONAL_VIEWS",
            status="success",
            summary="Regional operational outputs recomputed for release validation.",
            metadata=payload,
        )
        payload["run_metadata"] = run_metadata

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, default=str))

    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
