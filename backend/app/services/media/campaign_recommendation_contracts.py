"""Typed contracts for the heuristic campaign recommendation layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CampaignSpendGuardrails:
    min_budget_share: float
    min_budget_amount_eur: float
    min_confidence_for_activate: float
    min_confidence_for_prepare: float
    blocked_spend_statuses: tuple[str, ...] = ("blocked_operational_gate", "not_applicable")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductClusterConfig:
    cluster_key: str
    label: str
    products: tuple[str, ...] = ()
    supported_viruses: tuple[str, ...] = ()
    base_fit: float = 0.5
    activation_fit: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KeywordClusterConfig:
    cluster_key: str
    label: str
    product_cluster_key: str
    keywords: tuple[str, ...] = ()
    supported_viruses: tuple[str, ...] = ()
    base_fit: float = 0.5
    activation_fit: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CampaignRecommendationConfig:
    version: str
    max_recommendations: int
    product_clusters: tuple[ProductClusterConfig, ...] = ()
    keyword_clusters: tuple[KeywordClusterConfig, ...] = ()
    region_product_fit: dict[str, dict[str, float]] = field(default_factory=dict)
    spend_guardrails: CampaignSpendGuardrails = field(
        default_factory=lambda: CampaignSpendGuardrails(
            min_budget_share=0.06,
            min_budget_amount_eur=2_500.0,
            min_confidence_for_activate=0.60,
            min_confidence_for_prepare=0.48,
        )
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["product_clusters"] = [item.to_dict() for item in self.product_clusters]
        payload["keyword_clusters"] = [item.to_dict() for item in self.keyword_clusters]
        payload["spend_guardrails"] = self.spend_guardrails.to_dict()
        return payload


@dataclass(frozen=True)
class CampaignClusterSelection:
    cluster_key: str
    label: str
    fit_score: float
    products: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CampaignRecommendationRationale:
    why: list[str] = field(default_factory=list)
    why_details: list[dict[str, Any]] = field(default_factory=list)
    product_fit: list[str] = field(default_factory=list)
    product_fit_details: list[dict[str, Any]] = field(default_factory=list)
    keyword_fit: list[str] = field(default_factory=list)
    keyword_fit_details: list[dict[str, Any]] = field(default_factory=list)
    budget_notes: list[str] = field(default_factory=list)
    budget_note_details: list[dict[str, Any]] = field(default_factory=list)
    evidence_notes: list[str] = field(default_factory=list)
    evidence_note_details: list[dict[str, Any]] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)
    guardrail_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CampaignRecommendation:
    region: str
    region_name: str
    virus_typ: str
    activation_level: str
    priority_rank: int
    suggested_budget_share: float
    suggested_budget_amount: float
    confidence: float
    evidence_class: str
    recommended_product_cluster: CampaignClusterSelection
    recommended_keyword_cluster: CampaignClusterSelection
    recommendation_rationale: CampaignRecommendationRationale = field(
        default_factory=CampaignRecommendationRationale
    )
    channels: list[str] = field(default_factory=list)
    timeline: str | None = None
    products: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    spend_guardrail_status: str = "observe_only"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recommended_product_cluster"] = self.recommended_product_cluster.to_dict()
        payload["recommended_keyword_cluster"] = self.recommended_keyword_cluster.to_dict()
        payload["recommendation_rationale"] = self.recommendation_rationale.to_dict()
        payload["bundesland"] = self.region
        payload["bundesland_name"] = self.region_name
        return payload
