from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


CANONICAL_FORECAST_QUANTILES: tuple[float, ...] = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)
BENCHMARK_BASELINE_NAME = "persistence"
DEFAULT_EVENT_RECALL_CONSTRAINT = 0.35


def quantile_key(value: float) -> str:
    return f"q{int(round(float(value) * 1000)):04d}"


@dataclass(frozen=True)
class BenchmarkArtifactSummary:
    virus_typ: str
    horizon_days: int
    issue_dates: list[str]
    primary_metric: str
    champion_name: str | None
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metrics: dict[str, Any] = field(default_factory=dict)
    leaderboard: list[dict[str, Any]] = field(default_factory=list)
    diagnostics_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegistryEntry:
    model_family: str
    status: str
    metrics: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
