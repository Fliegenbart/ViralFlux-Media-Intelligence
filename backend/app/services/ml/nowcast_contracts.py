"""Typed contracts for revision-aware nowcast scoring and snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RevisionBucket:
    max_age_days: int
    completeness_factor: float
    revision_risk: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NowcastSourceConfig:
    source_id: str
    regional_granularity: str
    availability_strategy: str
    timing_provenance: str
    correction_enabled: bool
    revision_window_days: int
    revision_buckets: tuple[RevisionBucket, ...]
    max_staleness_days: int
    confidence_threshold: float
    coverage_window_days: int
    expected_cadence_days: int
    snapshot_lookback_days: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["revision_buckets"] = [bucket.to_dict() for bucket in self.revision_buckets]
        return payload


@dataclass(frozen=True)
class NowcastObservation:
    source_id: str
    signal_id: str
    region_code: str | None
    reference_date: datetime
    as_of_date: datetime
    raw_value: float
    effective_available_time: datetime
    timing_provenance: str
    coverage_ratio: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reference_date"] = self.reference_date.isoformat()
        payload["as_of_date"] = self.as_of_date.isoformat()
        payload["effective_available_time"] = self.effective_available_time.isoformat()
        return payload


@dataclass(frozen=True)
class NowcastResult:
    source_id: str
    signal_id: str
    region_code: str | None
    raw_observed_value: float
    revision_adjusted_value: float
    revision_risk_score: float
    source_freshness_days: int
    usable_confidence_score: float
    usable_for_forecast: bool
    coverage_ratio: float
    correction_applied: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NowcastSnapshotRecord:
    source_id: str
    signal_id: str
    region_code: str | None
    reference_date: datetime
    effective_available_time: datetime
    raw_value: float
    snapshot_captured_at: datetime
    timing_provenance: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reference_date"] = self.reference_date.isoformat()
        payload["effective_available_time"] = self.effective_available_time.isoformat()
        payload["snapshot_captured_at"] = self.snapshot_captured_at.isoformat()
        return payload
