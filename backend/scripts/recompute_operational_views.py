#!/usr/bin/env python3
"""Recompute regional forecast, allocation and recommendation outputs for ops validation."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import get_db_context
from app.services.ml.forecast_horizon_utils import (
    SUPPORTED_FORECAST_HORIZONS,
    regional_horizon_support_status,
)
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.production_readiness_service import ProductionReadinessService
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore
from app.services.ops.run_metadata_service import OperationalRunRecorder


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--virus",
        dest="viruses",
        action="append",
        choices=list(SUPPORTED_VIRUS_TYPES),
    )
    parser.add_argument(
        "--horizon",
        dest="horizons",
        action="append",
        type=int,
        choices=list(SUPPORTED_FORECAST_HORIZONS),
    )
    parser.add_argument("--weekly-budget-eur", type=float, default=50000.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    virus_types = args.viruses or list(SUPPORTED_VIRUS_TYPES)
    horizons = args.horizons or list(SUPPORTED_FORECAST_HORIZONS)

    with get_db_context() as db:
        service = RegionalForecastService(db)
        readiness_service = ProductionReadinessService()
        snapshot_store = RegionalOperationalSnapshotStore(db)
        observed_at = datetime.utcnow().replace(tzinfo=None)
        scopes: list[dict[str, object]] = []
        for virus_typ in virus_types:
            latest_source_state = readiness_service._latest_source_state(
                db,
                virus_typ=virus_typ,
                observed_at=observed_at,
            )
            for horizon_days in horizons:
                support = regional_horizon_support_status(virus_typ, horizon_days)
                if support["supported"]:
                    forecast = service.predict_all_regions(
                        virus_typ=virus_typ,
                        horizon_days=horizon_days,
                    )
                    allocation = service.generate_media_allocation(
                        virus_typ=virus_typ,
                        weekly_budget_eur=args.weekly_budget_eur,
                        horizon_days=horizon_days,
                    )
                    recommendations = service.generate_campaign_recommendations(
                        virus_typ=virus_typ,
                        weekly_budget_eur=args.weekly_budget_eur,
                        horizon_days=horizon_days,
                        top_n=args.top_n,
                    )
                    validation = service.get_validation_summary(
                        virus_typ=virus_typ,
                        brand="gelo",
                        horizon_days=horizon_days,
                    )
                else:
                    forecast = {
                        "virus_typ": virus_typ,
                        "horizon_days": horizon_days,
                        "status": "unsupported",
                        "message": support["reason"] or f"{virus_typ} unterstützt h{horizon_days} operativ nicht.",
                        "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
                        "supported_horizon_days_for_virus": support["supported_horizons"],
                        "predictions": [],
                    }
                    allocation = {
                        "status": "unsupported",
                        "recommendations": [],
                    }
                    recommendations = {
                        "status": "unsupported",
                        "recommendations": [],
                    }
                    validation = {
                        "status": "unsupported",
                        "message": forecast["message"],
                    }

                provisional_snapshot = snapshot_store.build_scope_metadata(
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    forecast=forecast,
                    allocation=allocation,
                    recommendations=recommendations,
                )
                readiness_item = readiness_service._regional_matrix_item(
                    service=service,
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    observed_at=observed_at,
                    latest_source_state=latest_source_state,
                    operational_snapshot=provisional_snapshot,
                    recent_operational_snapshots=snapshot_store.recent_scope_snapshots(
                        virus_typ=virus_typ,
                        horizon_days=horizon_days,
                        limit=2,
                    ),
                )
                scope_snapshot = snapshot_store.record_scope_snapshot(
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    forecast=forecast,
                    allocation=allocation,
                    recommendations=recommendations,
                    readiness=readiness_item,
                )
                scopes.append(
                    {
                        "virus_typ": virus_typ,
                        "horizon_days": horizon_days,
                        "forecast_status": forecast.get("status", "ok"),
                        "forecast_regions": len(forecast.get("predictions") or []),
                        "allocation_status": allocation.get("status", "ok"),
                        "allocation_regions": len(allocation.get("recommendations") or []),
                        "recommendation_status": recommendations.get("status", "ok"),
                        "recommendation_count": len(recommendations.get("recommendations") or []),
                        "artifact_transition_mode": forecast.get("artifact_transition_mode"),
                        "forecast_as_of_date": forecast.get("as_of_date"),
                        "pilot_contract_supported": readiness_item.get("pilot_contract_supported"),
                        "quality_gate_profile": readiness_item.get("quality_gate_profile"),
                        "quality_gate_failed_checks": readiness_item.get("quality_gate_failed_checks"),
                        "sars_h7_promotion": readiness_item.get("sars_h7_promotion"),
                        "validation": validation,
                        "snapshot_run_id": scope_snapshot.get("run_id"),
                    }
                )

        statuses = {
            str(item.get("forecast_status") or "ok").strip().lower()
            for item in scopes
        }
        overall_status = (
            "success"
            if statuses and statuses.issubset({"ok", "unsupported"})
            else "partial_error"
        )
        payload = {
            "status": overall_status,
            "virus_types": virus_types,
            "horizons": horizons,
            "summary": {
                "scopes": len(scopes),
                "ok": sum(1 for item in scopes if item["forecast_status"] == "ok"),
                "unsupported": sum(1 for item in scopes if item["forecast_status"] == "unsupported"),
                "non_ok": sum(1 for item in scopes if item["forecast_status"] not in {"ok", "unsupported"}),
            },
            "scopes": scopes,
        }
        run_metadata = OperationalRunRecorder(db).record_event(
            action="RECOMPUTE_OPERATIONAL_VIEWS",
            status=overall_status,
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
