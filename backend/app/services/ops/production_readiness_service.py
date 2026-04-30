"""Operational readiness snapshot for release and pilot gating."""

from __future__ import annotations
from app.core.time import utc_now

from contextlib import AbstractContextManager
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import Settings, get_settings
from app.db.session import get_db_context, get_last_init_summary
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops import production_readiness_live_sources
from app.services.ops import production_readiness_matrix
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore

logger = logging.getLogger(__name__)

_HEALTH_BY_STATUS = {
    "ok": "healthy",
    "warning": "degraded",
    "critical": "unhealthy",
    "unknown": "degraded",
}
READINESS_MODE = "layered_operational_v1"
BUDGET_STATUS = "diagnostic_only"
_SCIENCE_ONLY_CORE_BLOCKERS = {
    "Core scope quality gate is not at GO.",
}
_OPERATIONAL_WARNING_CORE_BLOCKERS = {
    "Core scope still uses an artifact transition fallback.",
    "Legacy artifact fallback is still active.",
}

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

        readiness_layers = self._build_readiness_layers(
            components=components,
            has_core_scopes=has_core_scopes,
        )
        overall_status = self._overall_status_from_layers(readiness_layers)
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
            "readiness_mode": READINESS_MODE,
            "operational_status": readiness_layers["operational"]["status"],
            "science_status": readiness_layers["science_validation"]["status"],
            "forecast_monitoring_status": readiness_layers["forecast_monitoring"]["status"],
            "budget_status": BUDGET_STATUS,
            "readiness_layers": readiness_layers,
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

        readiness_layers = self._build_readiness_layers(
            components=components,
            has_core_scopes=True,
        )
        overall_status = self._overall_status_from_layers(readiness_layers)
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
            "readiness_mode": READINESS_MODE,
            "operational_status": readiness_layers["operational"]["status"],
            "science_status": readiness_layers["science_validation"]["status"],
            "forecast_monitoring_status": readiness_layers["forecast_monitoring"]["status"],
            "budget_status": BUDGET_STATUS,
            "readiness_layers": readiness_layers,
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
        if status not in _HEALTH_BY_STATUS:
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
                        "drift_status": snapshot.get("drift_status"),
                        "model_version": snapshot.get("model_version"),
                        "alerts": list(snapshot.get("alerts") or []),
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
        supported_matrix = [
            item
            for item in matrix
            if item["model_availability"] != "unsupported"
        ]
        return {
            "status": overall_status,
            "message": "Regional operational readiness evaluated.",
            "summary": {
                "ready": sum(1 for item in matrix if item["status"] == "ok"),
                "warning": sum(1 for item in matrix if item["status"] == "warning"),
                "critical": sum(1 for item in matrix if item["status"] == "critical"),
                "missing_models": sum(1 for item in matrix if item["model_availability"] == "missing"),
                "regional_artifacts_ready": sum(
                    1 for item in supported_matrix if item.get("regional_artifacts_ready")
                ),
                "regional_artifacts_missing": sum(
                    1 for item in supported_matrix if item.get("regional_artifacts_ready") is False
                ),
                "regional_artifact_blockers": sorted(
                    {
                        blocker
                        for item in supported_matrix
                        for blocker in item.get("regional_artifact_blockers") or []
                    }
                ),
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
        return production_readiness_matrix.regional_matrix_item(
            self,
            service=service,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            observed_at=observed_at,
            latest_source_state=latest_source_state,
            operational_snapshot=operational_snapshot,
            recent_operational_snapshots=recent_operational_snapshots,
        )

    def _latest_source_state(
        self,
        db: Session,
        *,
        virus_typ: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        return production_readiness_live_sources.latest_source_state(
            self,
            db,
            virus_typ=virus_typ,
            observed_at=observed_at,
        )

    def _load_live_source_frames(
        self,
        db: Session,
        *,
        virus_typ: str,
        observed_at: datetime,
    ) -> dict[str, pd.DataFrame]:
        return production_readiness_live_sources.load_live_source_frames(
            self,
            db,
            virus_typ=virus_typ,
            observed_at=observed_at,
        )

    def _load_live_wastewater_frame(
        self,
        db: Session,
        *,
        virus_typ: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return production_readiness_live_sources.load_live_wastewater_frame(
            self,
            db,
            virus_typ=virus_typ,
            start_date=start_date,
            end_date=end_date,
        )

    def _load_live_grippeweb_frame(
        self,
        db: Session,
        *,
        signal_type: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return production_readiness_live_sources.load_live_grippeweb_frame(
            self,
            db,
            signal_type=signal_type,
            start_date=start_date,
            end_date=end_date,
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
        return production_readiness_live_sources.load_live_ifsg_frame(
            self,
            db,
            model=model,
            lag_days=lag_days,
            start_date=start_date,
            end_date=end_date,
        )

    def _load_live_are_frame(
        self,
        db: Session,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return production_readiness_live_sources.load_live_are_frame(
            self,
            db,
            start_date=start_date,
            end_date=end_date,
        )

    def _load_live_notaufnahme_frame(
        self,
        db: Session,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return production_readiness_live_sources.load_live_notaufnahme_frame(
            self,
            db,
            start_date=start_date,
            end_date=end_date,
        )

    def _load_live_trends_frame(
        self,
        db: Session,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return production_readiness_live_sources.load_live_trends_frame(
            self,
            db,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def _live_frame_from_available_rows(*, rows: Any, lag_days: int) -> pd.DataFrame:
        return production_readiness_live_sources.live_frame_from_available_rows(
            rows=rows,
            lag_days=lag_days,
        )

    def _live_frame_from_created_rows(self, *, rows: Any, lag_days: int) -> pd.DataFrame:
        return production_readiness_live_sources.live_frame_from_created_rows(
            self,
            rows=rows,
            lag_days=lag_days,
        )

    @staticmethod
    def _proxy_available_time_from_created(
        *,
        datum: datetime | pd.Timestamp,
        created_at: datetime | pd.Timestamp | None,
        lag_days: int,
        max_created_delay_days: int = 14,
    ) -> pd.Timestamp:
        return production_readiness_live_sources.proxy_available_time_from_created(
            datum=datum,
            created_at=created_at,
            lag_days=lag_days,
            max_created_delay_days=max_created_delay_days,
        )

    @staticmethod
    def _live_source_specs(virus_typ: str) -> tuple[dict[str, Any], ...]:
        return production_readiness_live_sources.live_source_specs(virus_typ)

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
        return production_readiness_live_sources.live_source_state_entry(
            self,
            frame=frame,
            observed_at=observed_at,
            source_id=source_id,
            label=label,
            criticality=criticality,
            cadence_days=cadence_days,
            coverage_window_days=coverage_window_days,
            minimum_points=minimum_points,
        )

    def _aggregate_live_source_state(
        self,
        *,
        source_states: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return production_readiness_live_sources.aggregate_live_source_state(
            self,
            source_states=source_states,
        )

    def _core_scope_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return production_readiness_matrix.core_scope_item(self, item)

    def _coverage_status(self, coverage_floor: float | None) -> str:
        return production_readiness_matrix.coverage_status(self, coverage_floor)

    def _source_coverage_contract(
        self,
        *,
        virus_typ: str,
        source_coverage: dict[str, Any],
    ) -> dict[str, Any]:
        return production_readiness_matrix.source_coverage_contract(
            self,
            virus_typ=virus_typ,
            source_coverage=source_coverage,
        )

    @staticmethod
    def _skipped_component(reason: str) -> dict[str, Any]:
        return {
            "status": "unknown",
            "message": f"Skipped because {reason}.",
        }

    @staticmethod
    def _worst_status(statuses: Any) -> str:
        return production_readiness_matrix.worst_status(statuses)

    def _build_readiness_layers(
        self,
        *,
        components: dict[str, Any],
        has_core_scopes: bool,
    ) -> dict[str, dict[str, Any]]:
        operational = self._operational_layer(components)
        core_operational = self._core_operational_layer(
            components,
            has_core_scopes=has_core_scopes,
        )
        science_validation = self._science_validation_layer(
            components,
            has_core_scopes=has_core_scopes,
        )
        forecast_monitoring = self._forecast_monitoring_layer(components)
        return {
            "operational": operational,
            "core_operational": core_operational,
            "science_validation": science_validation,
            "forecast_monitoring": forecast_monitoring,
        }

    def _operational_layer(self, components: dict[str, Any]) -> dict[str, Any]:
        component_names = ["database", "celery_broker", "schema_bootstrap"]
        statuses = [
            str((components.get(name) or {}).get("status") or "unknown")
            for name in component_names
        ]
        worst_status = self._worst_status(statuses)
        hard_blockers = sum(1 for status in statuses if status == "critical")
        warning_count = sum(1 for status in statuses if status in {"warning", "unknown"})
        return {
            "status": _HEALTH_BY_STATUS.get(worst_status, "degraded"),
            "hard_blockers": hard_blockers,
            "warning_count": warning_count,
        }

    def _core_operational_layer(
        self,
        components: dict[str, Any],
        *,
        has_core_scopes: bool,
    ) -> dict[str, Any]:
        component_name = (
            "core_regional_operational" if has_core_scopes else "regional_operational"
        )
        component = components.get(component_name) or {}
        component_status = str(component.get("status") or "unknown").strip().lower()
        matrix = list(component.get("matrix") or [])

        hard_blockers = 0
        warning_count = 0
        operational_warning_count = 0
        for item in matrix:
            item_hard_blockers = self._core_operational_hard_blockers(item)
            item_warning_blockers = self._core_operational_warning_blockers(item)
            hard_blockers += len(item_hard_blockers)
            operational_warning_count += len(item_warning_blockers)
            if (
                str(item.get("status") or "").strip().lower() == "critical"
                and not item_hard_blockers
            ):
                hard_blockers += 1
            warning_count += len(item.get("core_scope_advisories") or [])
            warning_count += len(item_warning_blockers)

        if component_status == "critical":
            hard_blockers = max(hard_blockers, 1)
            status = "unhealthy"
        elif hard_blockers:
            status = "unhealthy"
        elif operational_warning_count:
            status = "degraded"
        elif component_status == "unknown":
            warning_count = max(warning_count, 1)
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "hard_blockers": hard_blockers,
            "warning_count": warning_count,
        }

    def _science_validation_layer(
        self,
        components: dict[str, Any],
        *,
        has_core_scopes: bool,
    ) -> dict[str, Any]:
        component_name = (
            "core_regional_operational" if has_core_scopes else "regional_operational"
        )
        component = components.get(component_name) or {}
        warning_count = 0
        for item in list(component.get("matrix") or []):
            quality_gate = item.get("quality_gate") or {}
            quality_readiness = (
                str(quality_gate.get("forecast_readiness") or "").strip().upper()
            )
            failed_checks = list(
                quality_gate.get("failed_checks")
                or item.get("quality_gate_failed_checks")
                or []
            )
            if (quality_readiness and quality_readiness != "GO") or failed_checks:
                warning_count += 1

        forecast_component = components.get("forecast_monitoring") or {}
        for item in list(forecast_component.get("items") or []):
            alerts = [str(alert or "") for alert in list(item.get("alerts") or [])]
            if any(
                "Kalibrier" in alert or "Event-Wahrscheinlichkeit" in alert
                for alert in alerts
            ):
                warning_count += 1

        return {
            "status": "review" if warning_count else "healthy",
            "hard_blockers": 0,
            "warning_count": warning_count,
        }

    def _forecast_monitoring_layer(self, components: dict[str, Any]) -> dict[str, Any]:
        if "forecast_monitoring" not in components:
            return {
                "status": "healthy",
                "hard_blockers": 0,
                "warning_count": 0,
            }
        component = components.get("forecast_monitoring") or {}
        component_status = str(component.get("status") or "unknown").strip().lower()
        items = list(component.get("items") or [])
        warning_count = sum(
            1
            for item in items
            if str(item.get("status") or "").strip().lower()
            in {"warning", "unknown", "critical"}
        )
        if component_status == "critical":
            status = "critical"
        elif component_status in {"warning", "unknown"}:
            status = "warning"
        else:
            status = "healthy"
        return {
            "status": status,
            "hard_blockers": sum(
                1
                for item in items
                if str(item.get("status") or "").strip().lower() == "critical"
            ),
            "warning_count": warning_count,
        }

    @staticmethod
    def _core_operational_hard_blockers(item: dict[str, Any]) -> list[str]:
        blockers = [
            str(blocker or "").strip()
            for blocker in list(item.get("blockers") or [])
            if str(blocker or "").strip()
            and str(blocker or "").strip() not in _SCIENCE_ONLY_CORE_BLOCKERS
            and str(blocker or "").strip() not in _OPERATIONAL_WARNING_CORE_BLOCKERS
        ]
        if str(item.get("model_availability") or "").strip().lower() not in {
            "available",
            "unsupported",
        }:
            blockers.append("Core scope has no loadable regional model artifacts.")
        if str(item.get("forecast_recency_status") or "").strip().lower() == "critical":
            blockers.append("Core scope forecast recency is not in the OK window.")
        if str(item.get("source_freshness_status") or "").strip().lower() == "critical":
            blockers.append("Core scope source freshness is not in the OK window.")
        if (
            str(item.get("source_coverage_required_status") or "").strip().lower()
            == "critical"
        ):
            blockers.append("Core scope required source coverage is not OK.")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _core_operational_warning_blockers(item: dict[str, Any]) -> list[str]:
        return [
            str(blocker or "").strip()
            for blocker in list(item.get("blockers") or [])
            if str(blocker or "").strip() in _OPERATIONAL_WARNING_CORE_BLOCKERS
        ]

    @staticmethod
    def _overall_status_from_layers(layers: dict[str, dict[str, Any]]) -> str:
        operational_status = str((layers.get("operational") or {}).get("status") or "degraded")
        core_status = str((layers.get("core_operational") or {}).get("status") or "degraded")
        forecast_status = str((layers.get("forecast_monitoring") or {}).get("status") or "warning")
        if "unhealthy" in {operational_status, core_status}:
            return "unhealthy"
        if "degraded" in {operational_status, core_status}:
            return "degraded"
        if forecast_status == "critical":
            return "degraded"
        return "healthy"

    @staticmethod
    def _age_status(
        age_days: int | None,
        *,
        fresh_days: int,
        warning_days: int,
        missing_status: str = "unknown",
    ) -> str:
        return production_readiness_matrix.age_status(
            age_days,
            fresh_days=fresh_days,
            warning_days=warning_days,
            missing_status=missing_status,
        )

    def _source_freshness_windows(self, *, cadence_days: int) -> tuple[int, int]:
        return production_readiness_matrix.source_freshness_windows(
            self,
            cadence_days=cadence_days,
        )
