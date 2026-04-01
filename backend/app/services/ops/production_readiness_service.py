"""Operational readiness snapshot for release and pilot gating."""

from __future__ import annotations
from app.core.time import utc_now

from contextlib import AbstractContextManager
from datetime import datetime
import logging
from math import ceil
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import Settings, get_settings
from app.db.session import get_db_context, get_last_init_summary
from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    GrippeWebData,
    InfluenzaData,
    NotaufnahmeSyndromData,
    RSVData,
    WastewaterData,
)
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_horizon_utils import (
    SUPPORTED_FORECAST_HORIZONS,
    regional_horizon_support_status,
    regional_horizon_pilot_status,
)
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.regional_panel_utils import SOURCE_LAG_DAYS, effective_available_time
from app.services.ml.regional_panel_utils import sars_h7_promotion_status
from app.services.source_coverage_semantics import ARTIFACT_SOURCE_COVERAGE_SCOPE
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore

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

_REQUIRED_SOURCE_COVERAGE_KEYS: dict[str, tuple[str, ...]] = {
    "Influenza A": (
        "grippeweb_are_available",
        "grippeweb_ili_available",
        "ifsg_influenza_available",
    ),
    "Influenza B": (
        "grippeweb_are_available",
        "grippeweb_ili_available",
        "ifsg_influenza_available",
    ),
    "SARS-CoV-2": (
        "grippeweb_are_available",
        "grippeweb_ili_available",
        "sars_are_available",
        "sars_notaufnahme_available",
    ),
    "RSV A": (
        "grippeweb_are_available",
        "grippeweb_ili_available",
        "ifsg_rsv_available",
    ),
}

_ADVISORY_SOURCE_COVERAGE_KEYS: dict[str, tuple[str, ...]] = {
    "SARS-CoV-2": ("sars_trends_available",),
}

_LIVE_SOURCE_CONTRACTS_BY_VIRUS: dict[str, tuple[dict[str, Any], ...]] = {
    "Influenza A": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "ifsg_influenza", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "IfSG Influenza"},
    ),
    "Influenza B": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "ifsg_influenza", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "IfSG Influenza"},
    ),
    "RSV A": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "ifsg_rsv", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "IfSG RSV"},
    ),
    "SARS-CoV-2": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "sars_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "ARE Konsultation"},
        {"source_id": "sars_notaufnahme", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Notaufnahme COVID"},
        {"source_id": "sars_trends", "criticality": "advisory", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Google Trends Corona Test"},
    ),
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
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session_factory = session_factory
        base_settings = settings or get_settings()
        self.settings = base_settings.model_copy(deep=True)
        self.models_dir = models_dir
        self.now_provider = now_provider

    def build_snapshot(self, *, deep_checks: bool = True) -> dict[str, Any]:
        observed_at = self.now_provider().replace(tzinfo=None)
        components: dict[str, Any] = {
            "database": self._database_component(),
            "celery_broker": self._broker_component(),
            "schema_bootstrap": self._schema_bootstrap_component(),
        }
        blocking_components = ["database", "celery_broker", "schema_bootstrap"]
        advisory_components: list[str] = []
        has_core_scopes = bool(self.settings.EFFECTIVE_CORE_PRODUCTION_SCOPES)

        if components["database"]["status"] == "ok" and deep_checks:
            components["forecast_monitoring"] = self._safe_component(
                "forecast_monitoring",
                lambda: self._with_db_session(self._forecast_monitoring_component),
            )
            advisory_components.append("forecast_monitoring")
            components["regional_operational"] = self._safe_component(
                "regional_operational",
                lambda: self._with_db_session(
                    lambda db: self._regional_operational_component(db, observed_at=observed_at)
                ),
            )
            if has_core_scopes:
                advisory_components.append("regional_operational")
                components["core_regional_operational"] = self._safe_component(
                    "core_regional_operational",
                    lambda: self._with_db_session(
                        lambda db: self._core_regional_operational_component(
                            db,
                            observed_at=observed_at,
                        )
                    ),
                )
                blocking_components.append("core_regional_operational")
            else:
                blocking_components.append("regional_operational")
        else:
            reason = "database_unavailable" if components["database"]["status"] != "ok" else "startup_light_mode"
            components["forecast_monitoring"] = self._skipped_component(reason)
            components["regional_operational"] = self._skipped_component(reason)
            advisory_components.extend(["forecast_monitoring", "regional_operational"])
            if has_core_scopes:
                components["core_regional_operational"] = self._skipped_component(reason)
                blocking_components.append("core_regional_operational")

        overall_component_status = self._worst_status(
            components[name].get("status")
            for name in blocking_components
            if name in components
        )
        overall_status = _HEALTH_BY_STATUS.get(overall_component_status, "degraded")
        if overall_status == "healthy":
            advisory_has_critical = any(
                str((components.get(name) or {}).get("status") or "unknown") == "critical"
                for name in advisory_components
            )
            if advisory_has_critical:
                overall_status = "degraded"
        blockers = [
            {"component": name, "message": component.get("message")}
            for name, component in components.items()
            if name in blocking_components
            if component.get("status") == "critical"
        ]

        return {
            "status": overall_status,
            "checked_at": observed_at.isoformat(),
            "environment": self.settings.ENVIRONMENT,
            "app_version": self.settings.APP_VERSION,
            "blocking_components": blocking_components,
            "advisory_components": advisory_components,
            "components": components,
            "blockers": blockers,
        }

    def build_core_snapshot(self, *, deep_checks: bool = True) -> dict[str, Any]:
        observed_at = self.now_provider().replace(tzinfo=None)
        allowlist = [
            {"virus_typ": virus_typ, "horizon_days": horizon_days}
            for virus_typ, horizon_days in self.settings.EFFECTIVE_CORE_PRODUCTION_SCOPES
        ]
        components: dict[str, Any] = {
            "database": self._database_component(),
            "celery_broker": self._broker_component(),
            "schema_bootstrap": self._schema_bootstrap_component(),
        }

        if components["database"]["status"] == "ok" and deep_checks:
            components["core_regional_operational"] = self._safe_component(
                "core_regional_operational",
                lambda: self._with_db_session(
                    lambda db: self._core_regional_operational_component(
                        db,
                        observed_at=observed_at,
                    )
                ),
            )
        else:
            reason = "database_unavailable" if components["database"]["status"] != "ok" else "startup_light_mode"
            components["core_regional_operational"] = self._skipped_component(reason)

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
            "scope_mode": "core_production",
            "scope_allowlist": allowlist,
            "blocking_components": ["database", "celery_broker", "schema_bootstrap", "core_regional_operational"],
            "advisory_components": [],
            "components": components,
            "blockers": blockers,
        }

    @staticmethod
    def http_status_code(snapshot: dict[str, Any]) -> int:
        return 503 if str(snapshot.get("status")) == "unhealthy" else 200

    def _with_db_session(self, loader: Callable[[Session], dict[str, Any]]) -> dict[str, Any]:
        with self.session_factory() as db:
            return loader(db)

    @staticmethod
    def _component_failure(name: str, exc: Exception) -> dict[str, Any]:
        return {
            "status": "critical",
            "message": f"{name} failed: {exc}",
            "error_type": exc.__class__.__name__,
        }

    def _safe_component(
        self,
        name: str,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return loader()
        except Exception as exc:
            logger.exception("Production readiness component %s failed: %s", name, exc)
            return self._component_failure(name, exc)

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
                db.rollback()
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
        snapshot_store = RegionalOperationalSnapshotStore(db)
        operational_snapshots = snapshot_store.latest_scope_snapshots(
            virus_types=SUPPORTED_VIRUS_TYPES,
            horizon_days_list=SUPPORTED_FORECAST_HORIZONS,
        )
        matrix: list[dict[str, Any]] = []
        for virus_typ in SUPPORTED_VIRUS_TYPES:
            latest_source_state = self._latest_source_state(
                db,
                virus_typ=virus_typ,
                observed_at=observed_at,
            )
            for horizon_days in SUPPORTED_FORECAST_HORIZONS:
                matrix.append(
                    self._regional_matrix_item(
                        service=service,
                        virus_typ=virus_typ,
                        horizon_days=horizon_days,
                        observed_at=observed_at,
                        latest_source_state=latest_source_state,
                        operational_snapshot=operational_snapshots.get((virus_typ, horizon_days)),
                        recent_operational_snapshots=snapshot_store.recent_scope_snapshots(
                            virus_typ=virus_typ,
                            horizon_days=horizon_days,
                            limit=2,
                        ),
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
                "missing_models": sum(1 for item in matrix if item["model_availability"] == "missing"),
                "unsupported": sum(1 for item in matrix if item["model_availability"] == "unsupported"),
                "stale_forecasts": sum(1 for item in matrix if item["forecast_recency_status"] == "critical"),
                "stale_sources": sum(1 for item in matrix if item["source_freshness_status"] == "critical"),
                "quality_gate_failures": sum(
                    1
                    for item in matrix
                    if item["model_availability"] != "unsupported"
                    if str(item.get("quality_gate", {}).get("forecast_readiness") or "WATCH") != "GO"
                ),
            },
            "matrix": matrix,
        }

    def _core_regional_operational_component(
        self,
        db: Session,
        *,
        observed_at: datetime,
    ) -> dict[str, Any]:
        allowlist = list(self.settings.EFFECTIVE_CORE_PRODUCTION_SCOPES)
        if not allowlist:
            return {
                "status": "unknown",
                "message": "No core production scopes are configured.",
                "summary": {
                    "ready": 0,
                    "warning": 0,
                    "critical": 0,
                    "scopes": 0,
                },
                "matrix": [],
            }

        service = RegionalForecastService(db, models_dir=self.models_dir)
        snapshot_store = RegionalOperationalSnapshotStore(db)
        operational_snapshots = snapshot_store.latest_scope_snapshots(
            virus_types=sorted({virus_typ for virus_typ, _ in allowlist}),
            horizon_days_list=sorted({horizon_days for _, horizon_days in allowlist}),
        )
        latest_source_states: dict[str, dict[str, Any]] = {}
        matrix: list[dict[str, Any]] = []

        for virus_typ, horizon_days in allowlist:
            latest_source_state = latest_source_states.get(virus_typ)
            if latest_source_state is None:
                latest_source_state = self._latest_source_state(
                    db,
                    virus_typ=virus_typ,
                    observed_at=observed_at,
                )
                latest_source_states[virus_typ] = latest_source_state
            item = self._regional_matrix_item(
                service=service,
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                observed_at=observed_at,
                latest_source_state=latest_source_state,
                operational_snapshot=operational_snapshots.get((virus_typ, horizon_days)),
                recent_operational_snapshots=snapshot_store.recent_scope_snapshots(
                    virus_typ=virus_typ,
                    horizon_days=horizon_days,
                    limit=2,
                ),
            )
            matrix.append(self._core_scope_item(item))

        overall_status = self._worst_status(item["status"] for item in matrix)
        return {
            "status": overall_status,
            "message": "Core production readiness evaluated.",
            "summary": {
                "ready": sum(1 for item in matrix if item["status"] == "ok"),
                "warning": sum(1 for item in matrix if item["status"] == "warning"),
                "critical": sum(1 for item in matrix if item["status"] == "critical"),
                "scopes": len(matrix),
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
        operational_snapshot: dict[str, Any] | None,
        recent_operational_snapshots: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        support = regional_horizon_support_status(virus_typ, horizon_days)
        pilot = regional_horizon_pilot_status(virus_typ, horizon_days)
        if not support["supported"]:
            return {
                "virus_typ": virus_typ,
                "horizon_days": horizon_days,
                "status": "warning",
                "model_availability": "unsupported",
                "load_error": None,
                "artifact_transition_mode": None,
                "quality_gate": {"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
                "model_version": None,
                "calibration_version": None,
                "trained_at": None,
                "model_age_days": None,
                "model_age_status": "unknown",
                "latest_available_as_of": latest_source_state.get("latest_available_as_of").isoformat()
                if latest_source_state.get("latest_available_as_of")
                else None,
                "source_age_days": latest_source_state.get("source_age_days"),
                "source_freshness_status": latest_source_state.get("status") or "unknown",
                "point_in_time_snapshot_end": None,
                "forecast_lag_days": None,
                "forecast_recency_status": "unknown",
                "forecast_recency_basis": "unsupported",
                "source_coverage_floor": None,
                "source_coverage_status": "unknown",
                "source_coverage": {},
                "source_coverage_scope": ARTIFACT_SOURCE_COVERAGE_SCOPE,
                "artifact_source_coverage": {},
                "artifact_source_coverage_floor": None,
                "artifact_source_coverage_status": "unknown",
                "training_source_coverage": {},
                "live_source_coverage": {},
                "live_source_freshness": {},
                "source_criticality": {},
                "live_source_coverage_status": "unknown",
                "live_source_freshness_status": "unknown",
                "dataset_rows": None,
                "dataset_states": None,
                "supported_horizon_days_for_virus": support["supported_horizons"],
                "pilot_contract_supported": False,
                "pilot_contract_reason": support["reason"],
                "unsupported_reason": support["reason"] or f"{virus_typ} unterstützt h{horizon_days} operativ nicht.",
                "quality_gate_profile": None,
                "quality_gate_failed_checks": [],
                "operational_snapshot_as_of": None,
                "operational_snapshot_generated_at": None,
                "operational_snapshot_status": None,
                "sars_h7_promotion": None,
                "blockers": [],
            }
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
        source_freshness_status = (
            latest_source_state.get("live_source_freshness_status")
            or latest_source_state.get("status")
            or "unknown"
        )
        source_freshness_message = latest_source_state.get("message")
        live_source_coverage = latest_source_state.get("live_source_coverage") or {}
        live_source_freshness = latest_source_state.get("live_source_freshness") or {}
        source_criticality = latest_source_state.get("source_criticality") or {}
        live_source_coverage_status = str(latest_source_state.get("live_source_coverage_status") or "unknown")
        live_source_freshness_status = str(latest_source_state.get("live_source_freshness_status") or source_freshness_status)
        live_source_advisories = list(latest_source_state.get("advisories") or [])
        live_source_blockers = list(latest_source_state.get("blockers") or [])

        operational_snapshot_as_of = None
        operational_snapshot_status = None
        operational_snapshot_generated_at = None
        if operational_snapshot:
            operational_snapshot_status = str(operational_snapshot.get("forecast_status") or "ok").strip().lower()
            operational_snapshot_as_of = _parse_timestamp(operational_snapshot.get("forecast_as_of_date"))
            operational_snapshot_generated_at = operational_snapshot.get("recorded_at")

        snapshot_end = _parse_timestamp(
            ((point_in_time_snapshot.get("as_of_range") or {}).get("end"))
            or ((dataset_manifest.get("as_of_range") or {}).get("end"))
        )
        forecast_recency_reference = operational_snapshot_as_of or snapshot_end
        forecast_recency_basis = "operational_snapshot" if operational_snapshot_as_of else "training_snapshot"
        forecast_lag_days = _day_delta(latest_source_as_of, forecast_recency_reference)
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

        artifact_source_coverage = dict(dataset_manifest.get("training_source_coverage") or dataset_manifest.get("source_coverage") or {})
        training_source_coverage = dict(dataset_manifest.get("training_source_coverage") or artifact_source_coverage)
        artifact_coverage_contract = self._source_coverage_contract(
            virus_typ=virus_typ,
            source_coverage=artifact_source_coverage,
        )
        coverage_floor = latest_source_state.get("source_coverage_floor")
        source_coverage_status = live_source_coverage_status
        quality_gate_profile = str(quality_gate.get("profile") or "").strip() or None
        quality_gate_failed_checks = list(quality_gate.get("failed_checks") or [])
        sars_promotion = None
        if virus_typ == "SARS-CoV-2" and horizon_days == 7:
            sars_promotion = sars_h7_promotion_status(
                recent_snapshots=recent_operational_snapshots,
                promotion_flag_enabled=bool(self.settings.REGIONAL_SARS_H7_PROMOTION_ENABLED),
            )

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
        blockers.extend(live_source_blockers)
        if source_freshness_status == "critical" and source_freshness_message and source_freshness_message not in blockers:
            blockers.append(source_freshness_message)
        if forecast_recency_status == "critical":
            if operational_snapshot_as_of:
                blockers.append("Operational forecast snapshot lags behind latest available source data.")
            else:
                blockers.append("Model snapshot lags behind latest available source data.")
        if artifact_transition_mode:
            blockers.append("Legacy artifact fallback is still active.")
        blockers = list(dict.fromkeys(blockers))

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
            "forecast_recency_basis": forecast_recency_basis,
            "source_coverage_floor": round(float(coverage_floor), 4) if coverage_floor is not None else None,
            "source_coverage_status": source_coverage_status,
            "source_coverage_required_floor": (
                round(float(latest_source_state.get("required_coverage_floor")), 4)
                if latest_source_state.get("required_coverage_floor") is not None
                else None
            ),
            "source_coverage_required_status": latest_source_state.get("source_coverage_required_status") or "unknown",
            "source_coverage_required_keys": latest_source_state.get("required_live_sources") or [],
            "source_coverage_optional_floor": (
                round(float(latest_source_state.get("optional_coverage_floor")), 4)
                if latest_source_state.get("optional_coverage_floor") is not None
                else None
            ),
            "source_coverage_optional_status": latest_source_state.get("source_coverage_optional_status") or "unknown",
            "source_coverage_optional_keys": latest_source_state.get("optional_live_sources") or [],
            "source_coverage_missing_required": latest_source_state.get("missing_required_live_sources") or [],
            "source_coverage_advisories": live_source_advisories,
            "source_coverage": artifact_source_coverage,
            "source_coverage_scope": ARTIFACT_SOURCE_COVERAGE_SCOPE,
            "artifact_source_coverage": artifact_source_coverage,
            "artifact_source_coverage_floor": (
                round(float(artifact_coverage_contract["effective_floor"]), 4)
                if artifact_coverage_contract["effective_floor"] is not None
                else None
            ),
            "artifact_source_coverage_status": artifact_coverage_contract["effective_status"],
            "training_source_coverage": training_source_coverage,
            "live_source_coverage": live_source_coverage,
            "live_source_freshness": live_source_freshness,
            "source_criticality": source_criticality,
            "live_source_coverage_status": live_source_coverage_status,
            "live_source_freshness_status": live_source_freshness_status,
            "live_source_advisories": live_source_advisories,
            "dataset_rows": dataset_manifest.get("rows"),
            "dataset_states": dataset_manifest.get("states"),
            "supported_horizon_days_for_virus": support["supported_horizons"],
            "pilot_contract_supported": pilot["pilot_supported"],
            "pilot_contract_reason": pilot["reason"],
            "unsupported_reason": None,
            "quality_gate_profile": quality_gate_profile,
            "quality_gate_failed_checks": quality_gate_failed_checks,
            "operational_snapshot_as_of": operational_snapshot_as_of.isoformat() if operational_snapshot_as_of else None,
            "operational_snapshot_generated_at": operational_snapshot_generated_at,
            "operational_snapshot_status": operational_snapshot_status,
            "sars_h7_promotion": sars_promotion,
            "blockers": blockers,
        }

    def _latest_source_state(
        self,
        db: Session,
        *,
        virus_typ: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        source_frames = self._load_live_source_frames(
            db,
            virus_typ=virus_typ,
            observed_at=observed_at,
        )
        source_states = {
            spec["source_id"]: self._live_source_state_entry(
                frame=source_frames.get(spec["source_id"]),
                observed_at=observed_at,
                source_id=str(spec["source_id"]),
                label=str(spec["label"]),
                criticality=str(spec["criticality"]),
                cadence_days=int(spec["cadence_days"]),
                coverage_window_days=int(spec["coverage_window_days"]),
                minimum_points=int(spec.get("minimum_points") or 0),
            )
            for spec in self._live_source_specs(virus_typ)
        }
        return self._aggregate_live_source_state(source_states=source_states)

    def _load_live_source_frames(
        self,
        db: Session,
        *,
        virus_typ: str,
        observed_at: datetime,
    ) -> dict[str, pd.DataFrame]:
        observed_ts = pd.Timestamp(observed_at).normalize()
        specs = self._live_source_specs(virus_typ)
        max_window_days = max((int(spec.get("coverage_window_days") or 0) for spec in specs), default=28)
        start_date = observed_ts - pd.Timedelta(days=max(max_window_days, 28))
        frames: dict[str, pd.DataFrame] = {
            "wastewater": self._load_live_wastewater_frame(
                db,
                virus_typ=virus_typ,
                start_date=start_date,
                end_date=observed_ts,
            ),
            "grippeweb_are": self._load_live_grippeweb_frame(
                db,
                signal_type="ARE",
                start_date=start_date,
                end_date=observed_ts,
            ),
            "grippeweb_ili": self._load_live_grippeweb_frame(
                db,
                signal_type="ILI",
                start_date=start_date,
                end_date=observed_ts,
            ),
        }
        if virus_typ in {"Influenza A", "Influenza B"}:
            frames["ifsg_influenza"] = self._load_live_ifsg_frame(
                db,
                model=InfluenzaData,
                lag_days=SOURCE_LAG_DAYS["influenza_ifsg"],
                start_date=start_date,
                end_date=observed_ts,
            )
        elif virus_typ == "RSV A":
            frames["ifsg_rsv"] = self._load_live_ifsg_frame(
                db,
                model=RSVData,
                lag_days=SOURCE_LAG_DAYS["rsv_ifsg"],
                start_date=start_date,
                end_date=observed_ts,
            )
        elif virus_typ == "SARS-CoV-2":
            frames["sars_are"] = self._load_live_are_frame(
                db,
                start_date=start_date,
                end_date=observed_ts,
            )
            frames["sars_notaufnahme"] = self._load_live_notaufnahme_frame(
                db,
                start_date=start_date,
                end_date=observed_ts,
            )
            frames["sars_trends"] = self._load_live_trends_frame(
                db,
                start_date=start_date,
                end_date=observed_ts,
            )
        return frames

    def _load_live_wastewater_frame(
        self,
        db: Session,
        *,
        virus_typ: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            db.query(
                WastewaterData.datum,
                func.max(WastewaterData.available_time).label("available_time"),
            )
            .filter(
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.datum >= start_date.to_pydatetime(),
                WastewaterData.datum <= end_date.to_pydatetime(),
            )
            .group_by(WastewaterData.datum)
            .order_by(WastewaterData.datum.asc())
            .all()
        )
        return self._live_frame_from_available_rows(rows=rows, lag_days=0)

    def _load_live_grippeweb_frame(
        self,
        db: Session,
        *,
        signal_type: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            db.query(
                GrippeWebData.datum,
                func.max(GrippeWebData.created_at).label("created_at"),
            )
            .filter(
                GrippeWebData.datum >= start_date.to_pydatetime(),
                GrippeWebData.datum <= end_date.to_pydatetime(),
                GrippeWebData.erkrankung_typ == signal_type,
                GrippeWebData.altersgruppe.in_(["00+", "Gesamt"]),
            )
            .group_by(GrippeWebData.datum)
            .order_by(GrippeWebData.datum.asc())
            .all()
        )
        return self._live_frame_from_created_rows(
            rows=rows,
            lag_days=SOURCE_LAG_DAYS["grippeweb"],
        )

    def _load_live_ifsg_frame(
        self,
        db: Session,
        *,
        model: Any,
        lag_days: int,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            db.query(
                model.datum,
                func.max(model.available_time).label("available_time"),
            )
            .filter(
                model.datum >= start_date.to_pydatetime(),
                model.datum <= end_date.to_pydatetime(),
                model.altersgruppe.in_(["00+", "Gesamt"]),
            )
            .group_by(model.datum)
            .order_by(model.datum.asc())
            .all()
        )
        return self._live_frame_from_available_rows(rows=rows, lag_days=lag_days)

    def _load_live_are_frame(
        self,
        db: Session,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            db.query(
                AREKonsultation.datum,
                func.max(AREKonsultation.available_time).label("available_time"),
            )
            .filter(
                AREKonsultation.datum >= start_date.to_pydatetime(),
                AREKonsultation.datum <= end_date.to_pydatetime(),
                AREKonsultation.altersgruppe == "00+",
            )
            .group_by(AREKonsultation.datum)
            .order_by(AREKonsultation.datum.asc())
            .all()
        )
        return self._live_frame_from_available_rows(
            rows=rows,
            lag_days=SOURCE_LAG_DAYS["are_konsultation"],
        )

    def _load_live_notaufnahme_frame(
        self,
        db: Session,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            db.query(
                NotaufnahmeSyndromData.datum,
                func.max(NotaufnahmeSyndromData.created_at).label("created_at"),
            )
            .filter(
                NotaufnahmeSyndromData.datum >= start_date.to_pydatetime(),
                NotaufnahmeSyndromData.datum <= end_date.to_pydatetime(),
                NotaufnahmeSyndromData.syndrome == "COVID",
                NotaufnahmeSyndromData.ed_type == "all",
                NotaufnahmeSyndromData.age_group == "00+",
            )
            .group_by(NotaufnahmeSyndromData.datum)
            .order_by(NotaufnahmeSyndromData.datum.asc())
            .all()
        )
        return self._live_frame_from_created_rows(
            rows=rows,
            lag_days=SOURCE_LAG_DAYS["notaufnahme"],
        )

    def _load_live_trends_frame(
        self,
        db: Session,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        rows = (
            db.query(
                GoogleTrendsData.datum,
                func.max(GoogleTrendsData.available_time).label("available_time"),
            )
            .filter(
                GoogleTrendsData.datum >= start_date.to_pydatetime(),
                GoogleTrendsData.datum <= end_date.to_pydatetime(),
                func.lower(GoogleTrendsData.keyword) == "corona test",
                GoogleTrendsData.region == "DE",
            )
            .group_by(GoogleTrendsData.datum)
            .order_by(GoogleTrendsData.datum.asc())
            .all()
        )
        return self._live_frame_from_available_rows(
            rows=rows,
            lag_days=SOURCE_LAG_DAYS["google_trends"],
        )

    @staticmethod
    def _live_frame_from_available_rows(*, rows: Any, lag_days: int) -> pd.DataFrame:
        frame = pd.DataFrame(
            [
                {
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": effective_available_time(row.datum, row.available_time, lag_days),
                }
                for row in rows
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values("datum").reset_index(drop=True)

    @staticmethod
    def _live_frame_from_created_rows(*, rows: Any, lag_days: int) -> pd.DataFrame:
        frame = pd.DataFrame(
            [
                {
                    "datum": pd.Timestamp(row.datum).normalize(),
                    "available_time": ProductionReadinessService._proxy_available_time_from_created(
                        datum=row.datum,
                        created_at=row.created_at,
                        lag_days=lag_days,
                    ),
                }
                for row in rows
            ]
        )
        if frame.empty:
            return frame
        return frame.sort_values("datum").reset_index(drop=True)

    @staticmethod
    def _proxy_available_time_from_created(
        *,
        datum: datetime | pd.Timestamp,
        created_at: datetime | pd.Timestamp | None,
        lag_days: int,
        max_created_delay_days: int = 14,
    ) -> pd.Timestamp:
        base_available_time = effective_available_time(datum, None, lag_days)
        if created_at is None or pd.isna(created_at):
            return base_available_time
        created_ts = pd.Timestamp(created_at)
        if created_ts <= base_available_time + pd.Timedelta(days=max_created_delay_days):
            return created_ts
        return base_available_time

    @staticmethod
    def _live_source_specs(virus_typ: str) -> tuple[dict[str, Any], ...]:
        return _LIVE_SOURCE_CONTRACTS_BY_VIRUS.get(str(virus_typ or "").strip(), tuple())

    def _live_source_state_entry(
        self,
        *,
        frame: Any,
        observed_at: datetime,
        source_id: str,
        label: str,
        criticality: str,
        cadence_days: int,
        coverage_window_days: int,
        minimum_points: int = 0,
    ) -> dict[str, Any]:
        observed_ts = _parse_timestamp(observed_at) or observed_at
        observed_date = observed_ts.date()
        latest_available_as_of = None
        visible = frame.copy() if frame is not None and hasattr(frame, "copy") else None

        if visible is not None and not visible.empty and "datum" in visible.columns:
            visible = visible.copy()
            visible["datum"] = pd.to_datetime(visible["datum"], errors="coerce").dt.normalize()
            visible = visible.loc[visible["datum"].notna() & (visible["datum"] <= pd.Timestamp(observed_date))].copy()
            if "available_time" in visible.columns:
                visible["available_time"] = pd.to_datetime(visible["available_time"], errors="coerce")
                visible = visible.loc[
                    visible["available_time"].notna()
                    & (visible["available_time"] <= pd.Timestamp(observed_ts))
                ].copy()
                latest_available_as_of = (
                    _parse_timestamp(visible["available_time"].max())
                    if not visible.empty
                    else None
                )
            elif not visible.empty:
                latest_available_as_of = _parse_timestamp(visible["datum"].max())

        coverage_window_start = pd.Timestamp(observed_date) - pd.Timedelta(days=max(int(coverage_window_days) - 1, 0))
        recent = (
            visible.loc[visible["datum"] >= coverage_window_start].copy()
            if visible is not None and not visible.empty
            else None
        )
        available_points = int(visible["datum"].nunique()) if visible is not None and not visible.empty else 0
        observed_points = int(recent["datum"].nunique()) if recent is not None and not recent.empty else 0
        expected_points = max(int(ceil(float(max(int(coverage_window_days), 1)) / max(int(cadence_days), 1))), 1)
        coverage_ratio = round(min(float(observed_points) / float(expected_points), 1.0), 4) if expected_points else 0.0
        if available_points == 0:
            coverage_status = "critical"
        elif int(minimum_points) > 0:
            coverage_status = "ok" if available_points >= int(minimum_points) else "critical"
        else:
            coverage_status = "critical" if observed_points == 0 else self._coverage_status(coverage_ratio)
        age_days = _day_delta(observed_ts, latest_available_as_of)
        fresh_days, warning_days = self._source_freshness_windows(cadence_days=cadence_days)
        freshness_status = self._age_status(
            age_days,
            fresh_days=fresh_days,
            warning_days=warning_days,
            missing_status="critical",
        )
        return {
            "source_id": source_id,
            "label": label,
            "criticality": criticality,
            "observed_points": observed_points,
            "expected_points": expected_points,
            "coverage_ratio": coverage_ratio,
            "coverage_status": coverage_status,
            "latest_available_as_of": latest_available_as_of,
            "age_days": age_days,
            "freshness_status": freshness_status,
        }

    def _aggregate_live_source_state(
        self,
        *,
        source_states: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        critical_states = [state for state in source_states.values() if state.get("criticality") == "critical"]
        advisory_states = [state for state in source_states.values() if state.get("criticality") == "advisory"]
        required_live_sources = [str(state.get("source_id")) for state in critical_states]
        optional_live_sources = [str(state.get("source_id")) for state in advisory_states]
        missing_required_live_sources = [
            str(state.get("source_id"))
            for state in critical_states
            if str(state.get("coverage_status") or "critical") == "critical"
        ]

        required_coverage_floor = (
            min(float(state.get("coverage_ratio") or 0.0) for state in critical_states)
            if critical_states
            else None
        )
        optional_coverage_floor = (
            min(float(state.get("coverage_ratio") or 0.0) for state in advisory_states)
            if advisory_states
            else None
        )
        required_coverage_status = (
            self._worst_status(state.get("coverage_status") for state in critical_states)
            if critical_states
            else "unknown"
        )
        optional_coverage_raw_status = (
            self._worst_status(state.get("coverage_status") for state in advisory_states)
            if advisory_states
            else "unknown"
        )
        required_freshness_status = (
            self._worst_status(state.get("freshness_status") for state in critical_states)
            if critical_states
            else "unknown"
        )
        optional_freshness_raw_status = (
            self._worst_status(state.get("freshness_status") for state in advisory_states)
            if advisory_states
            else "unknown"
        )

        optional_coverage_status = (
            "unknown"
            if not advisory_states
            else ("ok" if optional_coverage_raw_status == "ok" else "warning")
        )
        optional_freshness_status = (
            "unknown"
            if not advisory_states
            else ("ok" if optional_freshness_raw_status == "ok" else "warning")
        )
        live_source_coverage_status = self._worst_status(
            [
                required_coverage_status,
                "warning" if optional_coverage_raw_status in {"warning", "critical"} else "ok",
            ]
        )
        live_source_freshness_status = self._worst_status(
            [
                required_freshness_status,
                "warning" if optional_freshness_raw_status in {"warning", "critical"} else "ok",
            ]
        )
        driver_state = max(
            critical_states or advisory_states or [{}],
            key=lambda state: int(state.get("age_days")) if state.get("age_days") is not None else -1,
        )

        blockers: list[str] = []
        advisories: list[str] = []
        for state in critical_states:
            label = str(state.get("label") or state.get("source_id") or "source")
            source_id = str(state.get("source_id") or "source")
            coverage_ratio = float(state.get("coverage_ratio") or 0.0)
            age_days = state.get("age_days")
            if str(state.get("coverage_status") or "unknown") == "critical":
                blockers.append(f"Critical live source coverage is missing or too low: {source_id}.")
            elif str(state.get("coverage_status") or "unknown") == "warning":
                advisories.append(f"Critical live source coverage is below the ideal threshold: {source_id}={coverage_ratio:.4f}.")
            if str(state.get("freshness_status") or "unknown") == "critical":
                blockers.append(f"Critical live source is stale: {source_id}.")
            elif str(state.get("freshness_status") or "unknown") == "warning":
                advisories.append(f"Critical live source freshness is outside the ideal window: {source_id} age={age_days}d.")
        for state in advisory_states:
            source_id = str(state.get("source_id") or "source")
            coverage_ratio = float(state.get("coverage_ratio") or 0.0)
            age_days = state.get("age_days")
            if str(state.get("coverage_status") or "unknown") != "ok":
                advisories.append(f"Advisory live source coverage needs attention: {source_id}={coverage_ratio:.4f}.")
            if str(state.get("freshness_status") or "unknown") != "ok":
                advisories.append(f"Advisory live source freshness needs attention: {source_id} age={age_days}d.")

        blockers = list(dict.fromkeys(blockers))
        advisories = list(dict.fromkeys(advisories))
        if blockers:
            message = blockers[0]
        elif advisories:
            message = "Live source coverage or freshness has active warnings."
        else:
            message = "Live source coverage and freshness evaluated."

        return {
            "status": live_source_freshness_status,
            "message": message,
            "latest_available_as_of": driver_state.get("latest_available_as_of"),
            "source_age_days": driver_state.get("age_days"),
            "source_coverage_floor": required_coverage_floor,
            "required_coverage_floor": required_coverage_floor,
            "optional_coverage_floor": optional_coverage_floor,
            "source_coverage_required_status": required_coverage_status,
            "source_coverage_optional_status": optional_coverage_status,
            "required_live_sources": required_live_sources,
            "optional_live_sources": optional_live_sources,
            "missing_required_live_sources": missing_required_live_sources,
            "live_source_coverage_status": live_source_coverage_status,
            "live_source_freshness_status": live_source_freshness_status,
            "blockers": blockers,
            "advisories": advisories,
            "source_criticality": {
                str(source_id): str((state or {}).get("criticality") or "unknown")
                for source_id, state in source_states.items()
            },
            "live_source_coverage": {
                str(source_id): {
                    "criticality": str((state or {}).get("criticality") or "unknown"),
                    "observed_points": int((state or {}).get("observed_points") or 0),
                    "expected_points": int((state or {}).get("expected_points") or 0),
                    "coverage_ratio": round(float((state or {}).get("coverage_ratio") or 0.0), 4),
                    "status": str((state or {}).get("coverage_status") or "unknown"),
                }
                for source_id, state in source_states.items()
            },
            "live_source_freshness": {
                str(source_id): {
                    "criticality": str((state or {}).get("criticality") or "unknown"),
                    "latest_available_as_of": (
                        (state or {}).get("latest_available_as_of").isoformat()
                        if (state or {}).get("latest_available_as_of") is not None
                        else None
                    ),
                    "age_days": (state or {}).get("age_days"),
                    "status": str((state or {}).get("freshness_status") or "unknown"),
                }
                for source_id, state in source_states.items()
            },
        }

    def _core_scope_item(self, item: dict[str, Any]) -> dict[str, Any]:
        model_availability = str(item.get("model_availability") or "missing")
        pilot_contract_supported = bool(item.get("pilot_contract_supported"))
        quality_gate = item.get("quality_gate") or {}
        quality_readiness = str(quality_gate.get("forecast_readiness") or "WATCH").upper()
        source_freshness_status = str(item.get("source_freshness_status") or "unknown").lower()
        forecast_recency_status = str(item.get("forecast_recency_status") or "unknown").lower()
        source_coverage_required_status = str(item.get("source_coverage_required_status") or "unknown").lower()
        artifact_transition_mode = str(item.get("artifact_transition_mode") or "").strip()
        source_freshness_core_status = (
            "ok"
            if source_freshness_status == "warning"
            and forecast_recency_status == "ok"
            else source_freshness_status
        )
        source_coverage_core_status = (
            "ok"
            if source_coverage_required_status == "warning"
            and forecast_recency_status == "ok"
            else source_coverage_required_status
        )

        availability_status = "ok" if model_availability == "available" else "critical"
        contract_status = "ok" if pilot_contract_supported else "critical"
        quality_status = "ok" if quality_readiness == "GO" else "warning"
        transition_status = "warning" if artifact_transition_mode else "ok"

        status = self._worst_status(
            [
                availability_status,
                contract_status,
                source_freshness_core_status,
                forecast_recency_status,
                source_coverage_core_status,
                quality_status,
                transition_status,
            ]
        )

        blockers = list(item.get("blockers") or [])
        advisories = []
        if model_availability != "available":
            blockers.append("Core scope has no loadable regional model artifacts.")
        if not pilot_contract_supported:
            blockers.append("Scope is not part of the active core production contract.")
        if quality_readiness != "GO":
            blockers.append("Core scope quality gate is not at GO.")
        if source_freshness_status == "warning" and forecast_recency_status == "ok":
            advisories.append("Core scope source freshness is outside the ideal window, but forecast recency is current.")
        elif source_freshness_status != "ok":
            blockers.append("Core scope source freshness is not in the OK window.")
        if forecast_recency_status != "ok":
            blockers.append("Core scope forecast recency is not in the OK window.")
        if source_coverage_required_status == "warning" and forecast_recency_status == "ok":
            advisories.append("Core scope required source coverage is below the ideal threshold, but forecast recency is current.")
        elif source_coverage_required_status != "ok":
            blockers.append("Core scope required source coverage is not OK.")
        if artifact_transition_mode:
            blockers.append("Core scope still uses an artifact transition fallback.")

        return {
            **item,
            "portfolio_status": item.get("status"),
            "status": status,
            "scope_contract": "core_production",
            "core_scope_passed": status == "ok",
            "core_scope_advisories": advisories,
            "blockers": list(dict.fromkeys(blockers)),
        }

    def _coverage_status(self, coverage_floor: float | None) -> str:
        if coverage_floor is None:
            return "warning"
        if float(coverage_floor) >= float(self.settings.READINESS_MIN_SOURCE_COVERAGE):
            return "ok"
        if float(coverage_floor) >= float(self.settings.READINESS_MIN_SOURCE_COVERAGE) * 0.75:
            return "warning"
        return "critical"

    def _source_coverage_contract(
        self,
        *,
        virus_typ: str,
        source_coverage: dict[str, Any],
    ) -> dict[str, Any]:
        coverage_map = {
            str(key): float(value or 0.0)
            for key, value in (source_coverage or {}).items()
        }
        required_keys = list(_REQUIRED_SOURCE_COVERAGE_KEYS.get(virus_typ, tuple(coverage_map.keys())))
        optional_keys = list(_ADVISORY_SOURCE_COVERAGE_KEYS.get(virus_typ, ()))
        if coverage_map and required_keys and not any(key in coverage_map for key in required_keys):
            required_keys = list(coverage_map.keys())
            optional_keys = []
        missing_required_keys = [key for key in required_keys if key not in coverage_map]

        required_values = [
            coverage_map[key]
            for key in required_keys
            if key in coverage_map
        ]
        optional_values = [
            coverage_map[key]
            for key in optional_keys
            if key in coverage_map
        ]

        required_floor = min(required_values) if required_values else None
        optional_floor = min(optional_values) if optional_values else None

        required_status = "critical" if missing_required_keys else self._coverage_status(required_floor)
        optional_status = "unknown"
        if optional_keys:
            if optional_values:
                optional_status = self._coverage_status(optional_floor)
            else:
                optional_status = "warning"

        effective_status = required_status
        advisories: list[str] = []
        if optional_status in {"warning", "critical"}:
            effective_status = self._worst_status([required_status, "warning"])
            if optional_keys:
                if optional_values:
                    advisories.append(
                        "Advisory source coverage is below the ideal threshold: "
                        + ", ".join(
                            f"{key}={coverage_map[key]:.4f}"
                            for key in optional_keys
                            if key in coverage_map
                        )
                        + "."
                    )
                else:
                    advisories.append(
                        "Advisory source coverage fields are missing: "
                        + ", ".join(optional_keys)
                        + "."
                    )

        effective_floor = required_floor
        return {
            "required_keys": required_keys,
            "optional_keys": optional_keys,
            "missing_required_keys": missing_required_keys,
            "required_floor": required_floor,
            "required_status": required_status,
            "optional_floor": optional_floor,
            "optional_status": optional_status,
            "effective_floor": effective_floor,
            "effective_status": effective_status,
            "advisories": advisories,
        }

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

    def _source_freshness_windows(self, *, cadence_days: int) -> tuple[int, int]:
        cadence = max(int(cadence_days or 1), 1)
        fresh_days = max(int(self.settings.READINESS_SOURCE_FRESH_DAYS), cadence)
        warning_days = max(int(self.settings.READINESS_SOURCE_WARNING_DAYS), cadence * 3)
        return fresh_days, warning_days
