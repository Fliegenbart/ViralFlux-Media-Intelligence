from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ARTIFACT_SOURCE_COVERAGE_SCOPE = "artifact"
UNKNOWN_LIVE_SOURCE_STATUS = "unknown"


def source_coverage_scope(payload: Mapping[str, Any] | None) -> str:
    return str((payload or {}).get("source_coverage_scope") or ARTIFACT_SOURCE_COVERAGE_SCOPE)


def artifact_source_coverage(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = (
        (payload or {}).get("artifact_source_coverage")
        or (payload or {}).get("training_source_coverage")
        or (payload or {}).get("source_coverage")
        or {}
    )
    return dict(source)


def live_source_coverage_status(payload: Mapping[str, Any] | None) -> str:
    return str(
        (payload or {}).get("live_source_coverage_status")
        or (payload or {}).get("source_coverage_required_status")
        or UNKNOWN_LIVE_SOURCE_STATUS
    ).strip().lower()


def live_source_freshness_status(payload: Mapping[str, Any] | None) -> str:
    return str(
        (payload or {}).get("live_source_freshness_status")
        or (payload or {}).get("source_freshness_status")
        or "ok"
    ).strip().lower()


def live_source_readiness(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    metadata = payload or {}
    return {
        "coverage_status": live_source_coverage_status(metadata),
        "freshness_status": live_source_freshness_status(metadata),
        "coverage": dict(metadata.get("live_source_coverage") or {}),
        "freshness": dict(metadata.get("live_source_freshness") or {}),
        "source_criticality": dict(metadata.get("source_criticality") or {}),
        "source_coverage_scope": source_coverage_scope(metadata),
    }
