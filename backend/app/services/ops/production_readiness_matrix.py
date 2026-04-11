"""Readiness matrix and policy helpers for production readiness snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.ml.forecast_horizon_utils import (
    regional_horizon_pilot_status,
    regional_horizon_support_status,
)
from app.services.ml.regional_panel_utils import sars_h7_promotion_status
from app.services.source_coverage_semantics import ARTIFACT_SOURCE_COVERAGE_SCOPE

_STATUS_SEVERITY = {
    "ok": 0,
    "warning": 1,
    "critical": 2,
    "unknown": 1,
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


def regional_matrix_item(
    readiness_service,
    *,
    service: Any,
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
            "regional_artifacts_ready": False,
            "regional_artifact_blockers": [],
            "regional_artifact_bootstrap_command": None,
            "artifact_diagnostic": None,
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
    artifact_diagnostic = dict(artifacts.get("artifact_diagnostic") or {})
    bootstrap_command = str(artifact_diagnostic.get("bootstrap_command") or "").strip() or None
    operator_message = str(artifact_diagnostic.get("operator_message") or "").strip() or None
    diagnostic_missing_files = [
        str(name)
        for name in (artifact_diagnostic.get("missing_files") or [])
        if str(name)
    ]
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
    forecast_recency_status = readiness_service._age_status(
        forecast_lag_days,
        fresh_days=readiness_service.settings.READINESS_FORECAST_LAG_FRESH_DAYS,
        warning_days=readiness_service.settings.READINESS_FORECAST_LAG_WARNING_DAYS,
        missing_status="critical",
    )

    trained_at = _parse_timestamp(metadata.get("trained_at"))
    model_age_days = _day_delta(observed_at, trained_at)
    model_age_status = readiness_service._age_status(
        model_age_days,
        fresh_days=readiness_service.settings.READINESS_MODEL_WARNING_AGE_DAYS,
        warning_days=readiness_service.settings.READINESS_MODEL_MAX_AGE_DAYS,
        missing_status="warning",
    )

    artifact_source_coverage = dict(dataset_manifest.get("training_source_coverage") or dataset_manifest.get("source_coverage") or {})
    training_source_coverage = dict(dataset_manifest.get("training_source_coverage") or artifact_source_coverage)
    artifact_coverage_contract = readiness_service._source_coverage_contract(
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
            promotion_flag_enabled=bool(readiness_service.settings.REGIONAL_SARS_H7_PROMOTION_ENABLED),
        )

    model_available = bool(artifacts and not load_error and feature_columns)
    model_availability = "available" if model_available else "missing"
    availability_status = "ok" if model_available else "critical"
    quality_status = "ok" if bool(quality_gate.get("overall_passed")) else "warning"
    transition_status = "warning" if artifact_transition_mode else "ok"

    overall_status = readiness_service._worst_status(
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
        if operator_message and operator_message not in blockers:
            blockers.append(operator_message)
        if diagnostic_missing_files:
            missing_files_message = (
                "Missing regional artifact files: " + ", ".join(diagnostic_missing_files)
            )
            if missing_files_message not in blockers:
                blockers.append(missing_files_message)
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
        "regional_artifacts_ready": model_available,
        "regional_artifact_blockers": list(dict.fromkeys(blockers)),
        "regional_artifact_bootstrap_command": bootstrap_command,
        "artifact_diagnostic": artifact_diagnostic or None,
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


def core_scope_item(service, item: dict[str, Any]) -> dict[str, Any]:
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

    status = service._worst_status(
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


def coverage_status(service, coverage_floor: float | None) -> str:
    if coverage_floor is None:
        return "warning"
    if float(coverage_floor) >= float(service.settings.READINESS_MIN_SOURCE_COVERAGE):
        return "ok"
    if float(coverage_floor) >= float(service.settings.READINESS_MIN_SOURCE_COVERAGE) * 0.75:
        return "warning"
    return "critical"


def source_coverage_contract(
    service,
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

    required_values = [coverage_map[key] for key in required_keys if key in coverage_map]
    optional_values = [coverage_map[key] for key in optional_keys if key in coverage_map]

    required_floor = min(required_values) if required_values else None
    optional_floor = min(optional_values) if optional_values else None

    required_status = "critical" if missing_required_keys else service._coverage_status(required_floor)
    optional_status = "unknown"
    if optional_keys:
        if optional_values:
            optional_status = service._coverage_status(optional_floor)
        else:
            optional_status = "warning"

    effective_status = required_status
    advisories: list[str] = []
    if optional_status in {"warning", "critical"}:
        effective_status = service._worst_status([required_status, "warning"])
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


def worst_status(statuses: Any) -> str:
    normalized = [str(status or "unknown") for status in statuses]
    if not normalized:
        return "unknown"
    return max(normalized, key=lambda value: _STATUS_SEVERITY.get(value, 1))


def age_status(
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


def source_freshness_windows(service, *, cadence_days: int) -> tuple[int, int]:
    cadence = max(int(cadence_days or 1), 1)
    fresh_days = max(int(service.settings.READINESS_SOURCE_FRESH_DAYS), cadence)
    warning_days = max(int(service.settings.READINESS_SOURCE_WARNING_DAYS), cadence * 3)
    return fresh_days, warning_days


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
