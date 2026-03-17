"""Persist and query regional operational forecast snapshots via the audit trail."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.database import AuditLog
from app.services.ops.run_metadata_service import OperationalRunRecorder


class RegionalOperationalSnapshotStore:
    """Store per-virus/per-horizon operational outputs without a new table."""

    ACTION = "REGIONAL_OPERATIONAL_SNAPSHOT"
    ENTITY_TYPE = "RegionalOperationalSnapshot"

    def __init__(self, db: Session):
        self.db = db
        self.recorder = OperationalRunRecorder(db)

    @staticmethod
    def _normalized_status(payload: dict[str, Any] | None) -> str:
        if not payload:
            return "missing"
        return str(payload.get("status") or "ok").strip().lower()

    @classmethod
    def build_scope_metadata(
        cls,
        *,
        virus_typ: str,
        horizon_days: int,
        forecast: dict[str, Any],
        allocation: dict[str, Any],
        recommendations: dict[str, Any],
    ) -> dict[str, Any]:
        forecast_status = cls._normalized_status(forecast)
        allocation_status = cls._normalized_status(allocation)
        recommendation_status = cls._normalized_status(recommendations)
        return {
            "virus_typ": str(virus_typ or "").strip(),
            "horizon_days": int(horizon_days),
            "forecast_status": forecast_status,
            "forecast_as_of_date": forecast.get("as_of_date"),
            "forecast_generated_at": forecast.get("generated_at"),
            "forecast_regions": len(forecast.get("predictions") or []),
            "supported_horizon_days": forecast.get("supported_horizon_days") or [],
            "supported_horizon_days_for_virus": forecast.get("supported_horizon_days_for_virus") or [],
            "artifact_transition_mode": forecast.get("artifact_transition_mode"),
            "model_version": forecast.get("model_version"),
            "calibration_version": forecast.get("calibration_version"),
            "quality_gate": forecast.get("quality_gate") or {},
            "business_gate": forecast.get("business_gate") or {},
            "point_in_time_snapshot": forecast.get("point_in_time_snapshot") or {},
            "allocation_status": allocation_status,
            "allocation_generated_at": allocation.get("generated_at"),
            "allocation_regions": len(allocation.get("recommendations") or []),
            "recommendation_status": recommendation_status,
            "recommendation_generated_at": recommendations.get("generated_at"),
            "recommendation_count": len(recommendations.get("recommendations") or []),
        }

    @classmethod
    def _scope_run_status(cls, metadata: dict[str, Any]) -> str:
        statuses = {
            str(metadata.get("forecast_status") or "missing"),
            str(metadata.get("allocation_status") or "missing"),
            str(metadata.get("recommendation_status") or "missing"),
        }
        if "error" in statuses:
            return "error"
        if "no_model" in statuses or "no_data" in statuses or "missing" in statuses:
            return "degraded"
        if "unsupported" in statuses or "unsupported_horizon" in statuses:
            return "warning"
        return "success"

    def record_scope_snapshot(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        forecast: dict[str, Any],
        allocation: dict[str, Any],
        recommendations: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = self.build_scope_metadata(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            forecast=forecast,
            allocation=allocation,
            recommendations=recommendations,
        )
        return self.recorder.record_event(
            action=self.ACTION,
            status=self._scope_run_status(metadata),
            summary=f"Regional operational outputs snapshotted for {virus_typ} h{horizon_days}.",
            metadata=metadata,
            entity_type=self.ENTITY_TYPE,
        )

    def latest_scope_snapshots(
        self,
        *,
        virus_types: Iterable[str] | None = None,
        horizon_days_list: Iterable[int] | None = None,
        limit: int = 500,
    ) -> dict[tuple[str, int], dict[str, Any]]:
        wanted_viruses = {str(item).strip() for item in (virus_types or []) if str(item).strip()}
        wanted_horizons = {int(item) for item in (horizon_days_list or [])}
        rows = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == self.ACTION, AuditLog.entity_type == self.ENTITY_TYPE)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(max(int(limit), 1))
            .all()
        )
        snapshots: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            payload = dict(row.new_value or {})
            metadata = dict(payload.get("metadata") or {})
            virus_typ = str(metadata.get("virus_typ") or "").strip()
            horizon_days = metadata.get("horizon_days")
            if not virus_typ or horizon_days is None:
                continue
            key = (virus_typ, int(horizon_days))
            if wanted_viruses and virus_typ not in wanted_viruses:
                continue
            if wanted_horizons and int(horizon_days) not in wanted_horizons:
                continue
            if key in snapshots:
                continue
            metadata["run_id"] = payload.get("run_id")
            metadata["run_status"] = payload.get("status")
            metadata["recorded_at"] = payload.get("timestamp")
            snapshots[key] = metadata
        return snapshots

    def latest_scope_snapshot(self, *, virus_typ: str, horizon_days: int) -> dict[str, Any] | None:
        return self.latest_scope_snapshots(
            virus_types=[virus_typ],
            horizon_days_list=[horizon_days],
            limit=200,
        ).get((str(virus_typ or "").strip(), int(horizon_days)))
