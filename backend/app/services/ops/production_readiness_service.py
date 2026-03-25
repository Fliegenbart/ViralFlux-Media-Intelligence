"""Operational readiness snapshot for release and pilot gating."""

from __future__ import annotations
from app.core.time import utc_now

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
from app.services.ml.forecast_horizon_utils import (
    SUPPORTED_FORECAST_HORIZONS,
    regional_horizon_support_status,
    regional_horizon_pilot_status,
)
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.regional_panel_utils import sars_h7_promotion_status
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
            latest_source_state = self._latest_source_state(db, virus_typ=virus_typ, observed_at=observed_at)
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
                latest_source_state = self._latest_source_state(db, virus_typ=virus_typ, observed_at=observed_at)
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
        source_freshness_status = latest_source_state.get("status") or "unknown"
        source_freshness_message = latest_source_state.get("message")

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

        source_coverage = dataset_manifest.get("source_coverage") or {}
        coverage_contract = self._source_coverage_contract(
            virus_typ=virus_typ,
            source_coverage=source_coverage,
        )
        coverage_floor = coverage_contract["effective_floor"]
        source_coverage_status = str(coverage_contract["effective_status"] or "warning")
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
        if source_freshness_status == "critical":
            blockers.append(source_freshness_message or "Underlying wastewater source is stale.")
        if forecast_recency_status == "critical":
            if operational_snapshot_as_of:
                blockers.append("Operational forecast snapshot lags behind latest available source data.")
            else:
                blockers.append("Model snapshot lags behind latest available source data.")
        if coverage_contract["missing_required_keys"]:
            blockers.append(
                "Required source coverage fields are missing: "
                + ", ".join(coverage_contract["missing_required_keys"])
                + "."
            )
        elif coverage_contract["required_status"] == "critical":
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
            "forecast_recency_basis": forecast_recency_basis,
            "source_coverage_floor": round(float(coverage_floor), 4) if coverage_floor is not None else None,
            "source_coverage_status": source_coverage_status,
            "source_coverage_required_floor": (
                round(float(coverage_contract["required_floor"]), 4)
                if coverage_contract["required_floor"] is not None
                else None
            ),
            "source_coverage_required_status": coverage_contract["required_status"],
            "source_coverage_required_keys": coverage_contract["required_keys"],
            "source_coverage_optional_floor": (
                round(float(coverage_contract["optional_floor"]), 4)
                if coverage_contract["optional_floor"] is not None
                else None
            ),
            "source_coverage_optional_status": coverage_contract["optional_status"],
            "source_coverage_optional_keys": coverage_contract["optional_keys"],
            "source_coverage_missing_required": coverage_contract["missing_required_keys"],
            "source_coverage_advisories": coverage_contract["advisories"],
            "source_coverage": source_coverage,
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
                source_coverage_required_status,
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
        if source_coverage_required_status != "ok":
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
