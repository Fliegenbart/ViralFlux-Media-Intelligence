"""Typed output contracts for the heuristic regional media allocation layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AllocationReasonTrace:
    why: list[str] = field(default_factory=list)
    budget_drivers: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionalMediaAllocationConfig:
    version: str
    baseline_total_budget_eur: float
    min_budget_per_active_region_eur: float
    max_budget_share_per_region: float
    risk_appetite: float
    label_weights: dict[str, float] = field(default_factory=dict)
    component_weights: dict[str, float] = field(default_factory=dict)
    confidence_thresholds: dict[str, float] = field(default_factory=dict)
    confidence_penalties: dict[str, float] = field(default_factory=dict)
    spend_enabled_labels: tuple[str, ...] = ("prepare", "activate")
    use_population_weighting: bool = True
    population_reference_millions: float = 8.0
    watch_budget_share_cap: float = 0.0
    region_weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClusterRecommendation:
    cluster_key: str
    label: str
    priority_rank: int
    fit_score: float
    products: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionalAllocationRecommendation:
    bundesland: str
    bundesland_name: str
    virus_typ: str
    recommended_activation_level: str
    spend_readiness: str
    priority_rank: int
    suggested_budget_share: float
    suggested_budget_eur: float
    allocation_score: float
    confidence: float
    reason_trace: AllocationReasonTrace = field(default_factory=AllocationReasonTrace)
    product_clusters: list[ClusterRecommendation] = field(default_factory=list)
    keyword_clusters: list[ClusterRecommendation] = field(default_factory=list)
    decision: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_trace"] = self.reason_trace.to_dict()
        payload["product_clusters"] = [item.to_dict() for item in self.product_clusters]
        payload["keyword_clusters"] = [item.to_dict() for item in self.keyword_clusters]
        payload["allocation_reason_trace"] = payload["reason_trace"]
        payload["suggested_budget_amount"] = payload["suggested_budget_eur"]
        return payload
