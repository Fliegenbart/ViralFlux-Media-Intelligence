"""Operational readiness snapshot for release and pilot gating."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import Settings, get_settings
from app.db.session import get_db_context, get_last_init_summary
from app.models.database import WastewaterData
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)

_STATUS_SEVERITY = {
    "ok": 0,
    "warning": 1,
    "critical": 2,
    "unknown": 1,
}
_HEALTH_BY_STATUS = {
    "ok": "healthy",
    "warning": "degraded",
    "critical": "unhealthy",
    "unknown": "degraded",
}


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _day_delta(later: datetime | None, earlier: datetime | None) -> int | None:
    if later is None or earlier is None:
        return None
    return max((later.date() - earlier.date()).days, 0)


class ProductionReadinessService:
    """Build a release-grade readiness snapshot from live dependencies and artifacts."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AbstractContextManager[Session]] = get_db_context,
        settings: Settings | None = None,
        models_dir: Path | None = None,
        now_provider: Callable[[], datetime] = datetime.utcnow,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.models_dir = models_dir
        self.now_provider = now_provider

    def build_snapshot(self, *, deep_checks: bool = True) -> dict[str, Any]:
        observed_at = self.now_provider().replace(tzinfo=None)
        components: dict[str, Any] = {
            "database": self._database_component(),
            "celery_broker": self._broker_component(),
            "schema_bootstrap": self._schema_bootstrap_component(),
        }

        if components["database"]["status"] == "ok" and deep_checks:
            with self.session_factory() as db:
                components["forecast_monitoring"] = self._forecast_monitoring_component(db)
                components["regional_operational"] = self._regional_operational_component(db, observed_at=observed_at)
        else:
            reason = "database_unavailable" if components["database"]["status"] != "ok" else "startup_light_mode"
            components["forecast_monitoring"] = self._skipped_component(reason)
            components["regional_operational"] = self._skipped_component(reason)

        overall_component_status = self._worst_status(
            component.get("status") for component in components.values()
        )
        overall_status = _HEALTH_BY_STATUS.get(overall_component_status, "degraded")
        blockers = [
            {"component": name, "message": component.get("message")}
            for name, component in components.items()
            if component.get("status") == "critical"
        ]

        return {
            "status": overall_status,
            "checked_at": observed_at.isoformat(),
            "environment": self.settings.ENVIRONMENT,
            "app_version": self.settings.APP_VERSION,
            "components": components,
            "blockers": blockers,
        }

    @staticmethod
    def http_status_code(snapshot: dict[str, Any]) -> int:
        return 503 if str(snapshot.get("status")) == "unhealthy" else 200

    def _database_component(self) -> dict[str, Any]:
        try:
            with self.session_factory() as db:
                db.execute(text("SELECT 1"))
            return {
                "status": "ok",
                "message": "Database connection available.",
            }
        except Exception as exc:
            logger.warning("Database readiness check failed: %s", exc)
            return {
                "status": "critical",
                "message": f"Database unavailable: {exc}",
            }

    def _broker_component(self) -> dict[str, Any]:
        try:
            connection = celery_app.connection_for_read()
            try:
                connection.ensure_connection(max_retries=1)
            finally:
                connection.release()
            return {
                "status": "ok",
                "message": "Celery broker reachable.",
            }
        except Exception as exc:
            status = "critical" if self.settings.EFFECTIVE_READINESS_REQUIRE_BROKER else "warning"
            return {
                "status": status,
                "message": f"Celery broker unavailable: {exc}",
            }

    @staticmethod
    def _schema_bootstrap_component() -> dict[str, Any]:
        summary = get_last_init_summary()
        if not summary:
            return {
                "status": "unknown",
                "message": "No startup schema summary recorded yet.",
            }
        warnings = list(summary.get("warnings") or [])
        status = "warning" if warnings else str(summary.get("status") or "ok")
        if status not in _STATUS_SEVERITY:
            status = "warning"
        return {
            "status": status,
            "message": summary.get("message") or "Startup schema verification completed.",
            "details": summary,
        }

    def _forecast_monitoring_component(self, db: Session) -> dict[str, Any]:
        service = ForecastDecisionService(db)
        items: list[dict[str, Any]] = []
        for virus_typ in SUPPORTED_VIRUS_TYPES:
            try:
                snapshot = service.build_monitoring_snapshot(
                    virus_typ=virus_typ,
                    target_source="RKI_ARE",
                )
                monitoring_status = str(snapshot.get("monitoring_status") or "unknown").strip().lower()
                status = {
                    "healthy": "ok",
                    "warning": "warning",
                    "critical": "critical",
                }.get(monitoring_status, "unknown")
                items.append(
                    {
                        "virus_typ": virus_typ,
                        "status": status,
                        "monitoring_status": snapshot.get("monitoring_status"),
                        "forecast_readiness": snapshot.get("forecast_readiness"),
                        "freshness_status": snapshot.get("freshness_status"),
                        "accuracy_freshness_status": snapshot.get("accuracy_freshness_status"),
                        "backtest_freshness_status": snapshot.get("backtest_freshness_status"),
                        "model_version": snapshot.get("model_version"),
                    }
                )
            except Exception as exc:
                items.append(
                    {
                        "virus_typ": virus_typ,
                        "status": "critical",
                        "monitoring_status": "error",
                        "message": str(exc),
                    }
                )

        overall_status = self._worst_status(item["status"] for item in items)
        return {
            "status": overall_status,
            "message": "Forecast monitoring snapshot loaded." if items else "No forecast monitoring available.",
            "summary": {
                "healthy": sum(1 for item in items if item["status"] == "ok"),
                "warning": sum(1 for item in items if item["status"] == "warning"),
                "critical": sum(1 for item in items if item["status"] == "critical"),
            },
            "items": items,
        }

    def _regional_operational_component(
        self,
        db: Session,
        *,
        observed_at: datetime,
    ) -> dict[str, Any]:
        service = RegionalForecastService(db, models_dir=self.models_dir)
        matrix: list[dict[str, Any]] = []
        for virus_typ in SUPPORTED_VIRUS_TYPES:
            latest_source_state = self._latest_source_state(db, virus_typ=virus_typ, observed_at=observed_at)
            for horizon_days in SUPPORTED_FORECAST_HORIZONS:
                matrix.append(
                    self._regional_matrix_item(
                        service=service,
                        virus_typ=virus_typ,
                        horizon_days=horizon_days,
                        observed_at=observed_at,
                        latest_source_state=latest_source_state,
                    )
                )

        overall_status = self._worst_status(item["status"] for item in matrix)
        return {
            "status": overall_status,
            "message": "Regional operational readiness evaluated.",
            "summary": {
                "ready": sum(1 for item in matrix if item["status"] == "ok"),
                "warning": sum(1 for item in matrix if item["status"] == "warning"),
                "critical": sum(1 for item in matrix if item["status"] == "critical"),
                "missing_models": sum(1 for item in matrix if item["model_availability"] != "available"),
                "stale_forecasts": sum(1 for item in matrix if item["forecast_recency_status"] == "critical"),
                "stale_sources": sum(1 for item in matrix if item["source_freshness_status"] == "critical"),
                "quality_gate_failures": sum(
                    1
                    for item in matrix
                    if str(item.get("quality_gate", {}).get("forecast_readiness") or "WATCH") != "GO"
                ),
            },
            "matrix": matrix,
        }

    def _regional_matrix_item(
        self,
        *,
        service: RegionalForecastService,
        virus_typ: str,
        horizon_days: int,
        observed_at: datetime,
        latest_source_state: dict[str, Any],
    ) -> dict[str, Any]:
        artifacts = service._load_artifacts(virus_typ, horizon_days=horizon_days)
        metadata = artifacts.get("metadata") or {}
        dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
        point_in_time_snapshot = artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {}
        quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
        load_error = str(artifacts.get("load_error") or "").strip()
        feature_columns = metadata.get("feature_columns") or []
        artifact_transition_mode = str(
            artifacts.get("artifact_transition_mode")
            or metadata.get("artifact_transition_mode")
            or ""
        ).strip() or None

        latest_source_as_of = latest_source_state.get("latest_available_as_of")
        source_age_days = latest_source_state.get("source_age_days")
        source_freshness_status = latest_source_state.get("status") or "unknown"
        source_freshness_message = latest_source_state.get("message")

        snapshot_end = _parse_timestamp(
            ((point_in_time_snapshot.get("as_of_range") or {}).get("end"))
            or ((dataset_manifest.get("as_of_range") or {}).get("end"))
        )
        forecast_lag_days = _day_delta(latest_source_as_of, snapshot_end)
        forecast_recency_status = self._age_status(
            forecast_lag_days,
            fresh_days=self.settings.READINESS_FORECAST_LAG_FRESH_DAYS,
            warning_days=self.settings.READINESS_FORECAST_LAG_WARNING_DAYS,
            missing_status="critical",
        )

        trained_at = _parse_timestamp(metadata.get("trained_at"))
        model_age_days = _day_delta(observed_at, trained_at)
        model_age_status = self._age_status(
            model_age_days,
            fresh_days=self.settings.READINESS_MODEL_WARNING_AGE_DAYS,
            warning_days=self.settings.READINESS_MODEL_MAX_AGE_DAYS,
            missing_status="warning",
        )

        source_coverage = dataset_manifest.get("source_coverage") or {}
        coverage_floor = None
        if source_coverage:
            coverage_floor = min(float(value or 0.0) for value in source_coverage.values())
        source_coverage_status = self._coverage_status(coverage_floor)

        model_available = bool(artifacts and not load_error and feature_columns)
        model_availability = "available" if model_available else "missing"
        availability_status = "ok" if model_available else "critical"
        quality_status = "ok" if bool(quality_gate.get("overall_passed")) else "warning"
        transition_status = "warning" if artifact_transition_mode else "ok"

        overall_status = self._worst_status(
            [
                availability_status,
                source_freshness_status,
                forecast_recency_status,
                model_age_status,
                source_coverage_status,
                quality_status,
                transition_status,
            ]
        )

        blockers: list[str] = []
        if not model_available:
            blockers.append(load_error or "Regional model artifacts missing.")
        if source_freshness_status == "critical":
            blockers.append(source_freshness_message or "Underlying wastewater source is stale.")
        if forecast_recency_status == "critical":
            blockers.append("Model snapshot lags behind latest available source data.")
        if source_coverage_status == "critical":
            blockers.append("Source coverage is below the minimum operational threshold.")
        if artifact_transition_mode:
            blockers.append("Legacy artifact fallback is still active.")

        return {
            "virus_typ": virus_typ,
            "horizon_days": horizon_days,
            "status": overall_status,
            "model_availability": model_availability,
            "load_error": load_error or None,
            "artifact_transition_mode": artifact_transition_mode,
            "quality_gate": quality_gate,
            "model_version": metadata.get("model_version"),
            "calibration_version": metadata.get("calibration_version"),
            "trained_at": metadata.get("trained_at"),
            "model_age_days": model_age_days,
            "model_age_status": model_age_status,
            "latest_available_as_of": latest_source_as_of.isoformat() if latest_source_as_of else None,
            "source_age_days": source_age_days,
            "source_freshness_status": source_freshness_status,
            "point_in_time_snapshot_end": snapshot_end.isoformat() if snapshot_end else None,
            "forecast_lag_days": forecast_lag_days,
            "forecast_recency_status": forecast_recency_status,
            "source_coverage_floor": round(float(coverage_floor), 4) if coverage_floor is not None else None,
            "source_coverage_status": source_coverage_status,
            "source_coverage": source_coverage,
            "dataset_rows": dataset_manifest.get("rows"),
            "dataset_states": dataset_manifest.get("states"),
            "blockers": blockers,
        }

    def _latest_source_state(
        self,
        db: Session,
        *,
        virus_typ: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        row = (
            db.query(
                func.max(WastewaterData.available_time).label("available_time"),
                func.max(WastewaterData.datum).label("datum"),
                func.count(WastewaterData.id).label("rows"),
            )
            .filter(WastewaterData.virus_typ == virus_typ)
            .first()
        )
        if row is None or int(row.rows or 0) == 0:
            return {
                "status": "critical",
                "message": "No wastewater source rows available for regional forecasting.",
                "latest_available_as_of": None,
                "source_age_days": None,
            }

        latest_available_as_of = _parse_timestamp(row.available_time or row.datum)
        source_age_days = _day_delta(observed_at, latest_available_as_of)
        status = self._age_status(
            source_age_days,
            fresh_days=self.settings.READINESS_SOURCE_FRESH_DAYS,
            warning_days=self.settings.READINESS_SOURCE_WARNING_DAYS,
            missing_status="critical",
        )
        return {
            "status": status,
            "message": "Wastewater source freshness evaluated.",
            "latest_available_as_of": latest_available_as_of,
            "source_age_days": source_age_days,
        }

    def _coverage_status(self, coverage_floor: float | None) -> str:
        if coverage_floor is None:
            return "warning"
        if float(coverage_floor) >= float(self.settings.READINESS_MIN_SOURCE_COVERAGE):
            return "ok"
        if float(coverage_floor) >= float(self.settings.READINESS_MIN_SOURCE_COVERAGE) * 0.75:
            return "warning"
        return "critical"

    @staticmethod
    def _skipped_component(reason: str) -> dict[str, Any]:
        return {
            "status": "unknown",
            "message": f"Skipped because {reason}.",
        }

    @staticmethod
    def _worst_status(statuses: Any) -> str:
        normalized = [str(status or "unknown") for status in statuses]
        if not normalized:
            return "unknown"
        return max(normalized, key=lambda value: _STATUS_SEVERITY.get(value, 1))

    @staticmethod
    def _age_status(
        age_days: int | None,
        *,
        fresh_days: int,
        warning_days: int,
        missing_status: str = "unknown",
    ) -> str:
        if age_days is None:
            return missing_status
        if age_days <= int(fresh_days):
            return "ok"
        if age_days <= int(warning_days):
            return "warning"
        return "critical"
