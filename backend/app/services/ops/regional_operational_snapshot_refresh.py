"""Refresh persisted regional operational snapshots used by readiness checks."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.services.ml.forecast_horizon_utils import supported_regional_horizons_for_virus
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.production_readiness_service import ProductionReadinessService
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore


def _normalize_brand(brand: str) -> str:
    value = str(brand).strip().lower()
    if value:
        return value
    raise ValueError("brand must be provided")


class RegionalOperationalSnapshotRefreshService:
    """Create fresh per-scope operational snapshots for readiness evaluation."""

    def __init__(
        self,
        db: Session,
        *,
        models_dir: Path | None = None,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.db = db
        self.models_dir = models_dir
        self.now_provider = now_provider
        self.regional_service = RegionalForecastService(db, models_dir=models_dir)
        self.snapshot_store = RegionalOperationalSnapshotStore(db)
        self.readiness_service = ProductionReadinessService(
            models_dir=models_dir,
            now_provider=now_provider,
        )

    def refresh_supported_scopes(
        self,
        *,
        brand: str,
        virus_types: Iterable[str] | None = None,
        horizon_days_list: Iterable[int] | None = None,
        weekly_budget_eur: float = 50000.0,
        top_n: int = 12,
    ) -> dict[str, Any]:
        brand_value = _normalize_brand(brand)
        observed_at = self.now_provider().replace(tzinfo=None)
        selected_viruses = [
            virus_typ
            for virus_typ in SUPPORTED_VIRUS_TYPES
            if virus_types is None or virus_typ in set(virus_types)
        ]
        selected_horizons = {int(item) for item in (horizon_days_list or [])}
        latest_source_states: dict[str, dict[str, Any]] = {}
        records: list[dict[str, Any]] = []

        for virus_typ in selected_viruses:
            latest_source_state = latest_source_states.get(virus_typ)
            if latest_source_state is None:
                latest_source_state = self.readiness_service._latest_source_state(
                    self.db,
                    virus_typ=virus_typ,
                    observed_at=observed_at,
                )
                latest_source_states[virus_typ] = latest_source_state

            for horizon_days in supported_regional_horizons_for_virus(virus_typ):
                if selected_horizons and int(horizon_days) not in selected_horizons:
                    continue

                forecast = self.regional_service.predict_all_regions(
                    virus_typ=virus_typ,
                    brand=brand_value,
                    horizon_days=horizon_days,
                )
                allocation = self.regional_service.generate_media_allocation(
                    virus_typ=virus_typ,
                    brand=brand_value,
                    weekly_budget_eur=weekly_budget_eur,
                    horizon_days=horizon_days,
                )
                recommendations = (
                    self.regional_service.campaign_recommendation_service.recommend_from_allocation(
                        allocation_payload=allocation,
                        top_n=top_n,
                    )
                )
                recommendations.setdefault("horizon_days", horizon_days)
                recommendations.setdefault(
                    "target_window_days",
                    allocation.get("target_window_days") or [horizon_days, horizon_days],
                )

                synthetic_operational_snapshot = {
                    "forecast_status": forecast.get("status"),
                    "forecast_as_of_date": forecast.get("as_of_date"),
                    "recorded_at": observed_at.isoformat(),
                }
                readiness = self.readiness_service._regional_matrix_item(
                    service=self.regional_service,
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    observed_at=observed_at,
                    latest_source_state=latest_source_state,
                    operational_snapshot=synthetic_operational_snapshot,
                    recent_operational_snapshots=self.snapshot_store.recent_scope_snapshots(
                        virus_typ=virus_typ,
                        horizon_days=horizon_days,
                        limit=2,
                    ),
                )
                run_metadata = self.snapshot_store.record_scope_snapshot(
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    forecast=forecast,
                    allocation=allocation,
                    recommendations=recommendations,
                    readiness=readiness,
                )
                records.append(
                    {
                        "virus_typ": virus_typ,
                        "horizon_days": int(horizon_days),
                        "status": readiness.get("status"),
                        "run_status": run_metadata.get("status"),
                        "recorded_at": run_metadata.get("timestamp"),
                    }
                )

        return {
            "status": "success",
            "brand": brand_value,
            "virus_types": list(selected_viruses),
            "horizon_days_list": sorted(selected_horizons) if selected_horizons else None,
            "scope_count": len(records),
            "records_written": len(records),
            "records": records,
            "generated_at": observed_at.isoformat(),
        }
