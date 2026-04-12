"""Transparent campaign recommendations built on top of regional allocation output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.media import campaign_recommendation_rationale, campaign_recommendation_scoring
from app.services.media.campaign_recommendation_contracts import (
    CampaignClusterSelection,
    CampaignRecommendation,
    CampaignRecommendationConfig,
    CampaignRecommendationRationale,
    CampaignSpendGuardrails,
    KeywordClusterConfig,
    ProductClusterConfig,
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_CAMPAIGN_RECOMMENDATION_CONFIG = CampaignRecommendationConfig(
    version="campaign_recommendation_v1",
    max_recommendations=12,
    product_clusters=(
        ProductClusterConfig(
            cluster_key="respiratory_core_support",
            label="Respiratory Core Demand",
            products=("GeloMyrtol forte",),
            supported_viruses=("Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"),
            base_fit=0.86,
            activation_fit={"activate": 1.0, "prepare": 0.92, "watch": 0.70},
            metadata={
                "source": "campaign_recommendation_v1",
                "positioning": "broad respiratory symptom demand",
            },
        ),
        ProductClusterConfig(
            cluster_key="voice_recovery_support",
            label="Voice And Throat Support",
            products=("GeloRevoice",),
            supported_viruses=("Influenza A", "Influenza B"),
            base_fit=0.74,
            activation_fit={"activate": 0.90, "prepare": 0.88, "watch": 0.68},
            metadata={
                "source": "campaign_recommendation_v1",
                "positioning": "upper-respiratory and voice-led demand",
            },
        ),
        ProductClusterConfig(
            cluster_key="bronchial_support",
            label="Bronchial Recovery Support",
            products=("GeloBronchial", "GeloMyrtol forte"),
            supported_viruses=("RSV A", "Influenza A", "Influenza B"),
            base_fit=0.78,
            activation_fit={"activate": 0.94, "prepare": 0.86, "watch": 0.65},
            metadata={
                "source": "campaign_recommendation_v1",
                "positioning": "bronchial recovery and mucus-relief demand",
            },
        ),
    ),
    keyword_clusters=(
        KeywordClusterConfig(
            cluster_key="respiratory_relief_search",
            label="Respiratory Relief Search",
            product_cluster_key="respiratory_core_support",
            keywords=("husten schleim loesen", "bronchitis schleim", "atemwege befreien"),
            supported_viruses=("Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"),
            base_fit=0.84,
            activation_fit={"activate": 1.0, "prepare": 0.92, "watch": 0.70},
            metadata={"intent": "symptom relief", "channel_bias": "search+social"},
        ),
        KeywordClusterConfig(
            cluster_key="voice_relief_search",
            label="Voice Recovery Search",
            product_cluster_key="voice_recovery_support",
            keywords=("heiserkeit schnell loswerden", "stimme weg erkaltung", "hals und stimme beruhigen"),
            supported_viruses=("Influenza A", "Influenza B"),
            base_fit=0.80,
            activation_fit={"activate": 0.92, "prepare": 0.90, "watch": 0.72},
            metadata={"intent": "voice/throat", "channel_bias": "search"},
        ),
        KeywordClusterConfig(
            cluster_key="bronchial_recovery_search",
            label="Bronchial Recovery Search",
            product_cluster_key="bronchial_support",
            keywords=("bronchien verschleimt", "husten bronchien loesen", "atemwege beruhigen"),
            supported_viruses=("RSV A", "Influenza A", "Influenza B"),
            base_fit=0.82,
            activation_fit={"activate": 0.96, "prepare": 0.88, "watch": 0.70},
            metadata={"intent": "bronchial recovery", "channel_bias": "search+programmatic"},
        ),
    ),
    region_product_fit={
        "BE": {"voice_recovery_support": 1.18, "respiratory_core_support": 0.96},
        "HH": {"voice_recovery_support": 1.16, "respiratory_core_support": 0.97},
        "HB": {"voice_recovery_support": 1.12},
        "BY": {"respiratory_core_support": 1.08},
        "BW": {"respiratory_core_support": 1.06},
        "NW": {"respiratory_core_support": 1.05},
        "BB": {"bronchial_support": 1.06},
        "MV": {"bronchial_support": 1.04},
        "SN": {"bronchial_support": 1.04},
    },
    spend_guardrails=CampaignSpendGuardrails(
        min_budget_share=0.06,
        min_budget_amount_eur=2_500.0,
        min_confidence_for_activate=0.60,
        min_confidence_for_prepare=0.48,
    ),
)


class CampaignRecommendationService:
    """Turn allocation output into concrete, discussion-ready campaign recommendations."""

    def __init__(
        self,
        config: CampaignRecommendationConfig = DEFAULT_CAMPAIGN_RECOMMENDATION_CONFIG,
    ) -> None:
        self.config = config

    @staticmethod
    def _reason_detail(code: str, message: str, **params: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": code, "message": message}
        if params:
            payload["params"] = params
        return payload

    def recommend_from_allocation(
        self,
        *,
        allocation_payload: Mapping[str, Any],
        top_n: int | None = None,
    ) -> dict[str, Any]:
        virus_typ = str(allocation_payload.get("virus_typ") or "")
        recommendations = list(allocation_payload.get("recommendations") or [])
        limit = max(1, min(int(top_n or self.config.max_recommendations), self.config.max_recommendations))

        if not recommendations:
            return {
                "virus_typ": virus_typ,
                "status": allocation_payload.get("status"),
                "message": allocation_payload.get("message"),
                "headline": allocation_payload.get("headline") or f"{virus_typ}: keine Campaign Recommendations verfügbar",
                "summary": {
                    "total_recommendations": 0,
                    "ready_recommendations": 0,
                    "guarded_recommendations": 0,
                    "observe_only_recommendations": 0,
                    "top_region": None,
                    "top_product_cluster": None,
                },
                "config": self.config.to_dict(),
                "allocation_summary": allocation_payload.get("summary") or {},
                "truth_layer": allocation_payload.get("truth_layer") or {
                    "enabled": False,
                    "scopes_evaluated": 0,
                },
                "generated_at": _utc_now_iso(),
                "recommendations": [],
            }

        built = [
            self._build_recommendation(
                virus_typ=virus_typ,
                allocation_item=item,
            )
            for item in recommendations
        ]
        built.sort(key=self._sort_key, reverse=True)
        built = built[:limit]

        for priority_rank, item in enumerate(built, start=1):
            item["priority_rank"] = priority_rank

        ready_count = sum(1 for item in built if item["spend_guardrail_status"] == "ready")
        guarded_count = sum(
            1
            for item in built
            if item["spend_guardrail_status"] in {"bundle_with_neighbor_region", "low_confidence_review"}
        )
        observe_count = len(built) - ready_count - guarded_count
        top_item = built[0] if built else {}

        return {
            "virus_typ": virus_typ,
            "headline": self._headline(virus_typ=virus_typ, recommendations=built),
            "summary": {
                "total_recommendations": len(built),
                "ready_recommendations": ready_count,
                "guarded_recommendations": guarded_count,
                "observe_only_recommendations": observe_count,
                "top_region": top_item.get("region"),
                "top_product_cluster": (top_item.get("recommended_product_cluster") or {}).get("label"),
                "campaign_recommendation_policy_version": self.config.version,
            },
            "config": self.config.to_dict(),
            "allocation_summary": allocation_payload.get("summary") or {},
            "truth_layer": allocation_payload.get("truth_layer") or {
                "enabled": False,
                "scopes_evaluated": 0,
            },
            "generated_at": _utc_now_iso(),
            "recommendations": built,
        }

    def _build_recommendation(
        self,
        *,
        virus_typ: str,
        allocation_item: Mapping[str, Any],
    ) -> dict[str, Any]:
        stage = str(
            allocation_item.get("recommended_activation_level")
            or allocation_item.get("decision_label")
            or "Watch"
        ).strip()
        stage_key = stage.lower()
        region = str(allocation_item.get("bundesland") or allocation_item.get("region") or "")
        region_name = str(
            allocation_item.get("bundesland_name")
            or allocation_item.get("region_name")
            or region
        )
        confidence = _clamp(
            float(
                allocation_item.get("allocation_support_score")
                or allocation_item.get("confidence")
                or 0.0
            )
        )
        evidence_class = self._evidence_class(allocation_item)
        available_products = self._available_products(allocation_item)
        recommended_product_cluster = self._select_product_cluster(
            virus_typ=virus_typ,
            stage=stage_key,
            region=region,
            confidence=confidence,
            available_products=available_products,
            allocation_item=allocation_item,
        )
        recommended_keyword_cluster = self._select_keyword_cluster(
            virus_typ=virus_typ,
            stage=stage_key,
            region=region,
            confidence=confidence,
            product_cluster=recommended_product_cluster,
        )
        budget_share = round(float(allocation_item.get("suggested_budget_share") or 0.0), 6)
        budget_amount = round(
            float(
                allocation_item.get("suggested_budget_amount")
                or allocation_item.get("suggested_budget_eur")
                or allocation_item.get("budget_eur")
                or 0.0
            ),
            2,
        )
        guardrail_status = self._guardrail_status(
            stage=stage_key,
            budget_share=budget_share,
            budget_amount=budget_amount,
            confidence=confidence,
            spend_gate_status=str(allocation_item.get("spend_gate_status") or ""),
        )
        rationale = self._rationale(
            stage=stage,
            allocation_item=allocation_item,
            product_cluster=recommended_product_cluster,
            keyword_cluster=recommended_keyword_cluster,
            evidence_class=evidence_class,
            guardrail_status=guardrail_status,
            budget_share=budget_share,
            budget_amount=budget_amount,
        )

        recommendation = CampaignRecommendation(
            region=region,
            region_name=region_name,
            virus_typ=virus_typ,
            activation_level=stage,
            priority_rank=int(allocation_item.get("priority_rank") or 0),
            suggested_budget_share=budget_share,
            suggested_budget_amount=budget_amount,
            confidence=round(confidence, 4),
            evidence_class=evidence_class,
            recommended_product_cluster=recommended_product_cluster,
            recommended_keyword_cluster=recommended_keyword_cluster,
            recommendation_rationale=rationale,
            channels=[str(item) for item in (allocation_item.get("channels") or []) if str(item).strip()],
            timeline=str(allocation_item.get("timeline") or ""),
            products=available_products,
            keywords=recommended_keyword_cluster.keywords,
            spend_guardrail_status=guardrail_status,
            metadata={
                "allocation_score": round(float(allocation_item.get("allocation_score") or 0.0), 4),
                "allocation_priority_rank": int(allocation_item.get("priority_rank") or 0),
                "spend_gate_status": allocation_item.get("spend_gate_status"),
                "budget_release_recommendation": allocation_item.get("budget_release_recommendation"),
                "truth_layer_enabled": bool(allocation_item.get("truth_layer_enabled")),
                "region_product_fit_multiplier": self._region_fit_multiplier(
                    region=region,
                    cluster_key=recommended_product_cluster.cluster_key,
                ),
            },
        ).to_dict()
        return recommendation

    @staticmethod
    def _available_products(allocation_item: Mapping[str, Any]) -> list[str]:
        return campaign_recommendation_scoring.available_products(allocation_item)

    def _select_product_cluster(
        self,
        *,
        virus_typ: str,
        stage: str,
        region: str,
        confidence: float,
        available_products: Sequence[str],
        allocation_item: Mapping[str, Any],
    ) -> CampaignClusterSelection:
        return campaign_recommendation_scoring.select_product_cluster(
            self.config,
            virus_typ=virus_typ,
            stage=stage,
            region=region,
            confidence=confidence,
            available_products=available_products,
            allocation_item=allocation_item,
        )

    def _select_keyword_cluster(
        self,
        *,
        virus_typ: str,
        stage: str,
        region: str,
        confidence: float,
        product_cluster: CampaignClusterSelection,
    ) -> CampaignClusterSelection:
        return campaign_recommendation_scoring.select_keyword_cluster(
            self.config,
            virus_typ=virus_typ,
            stage=stage,
            region=region,
            confidence=confidence,
            product_cluster=product_cluster,
        )

    @staticmethod
    def _product_overlap(
        *,
        cluster: ProductClusterConfig,
        available_products: set[str],
    ) -> float:
        return campaign_recommendation_scoring.product_overlap(
            cluster=cluster,
            available_products=available_products,
        )

    def _region_fit_multiplier(self, *, region: str, cluster_key: str) -> float:
        return campaign_recommendation_scoring.region_fit_multiplier(
            self.config,
            region=region,
            cluster_key=cluster_key,
        )

    def _guardrail_status(
        self,
        *,
        stage: str,
        budget_share: float,
        budget_amount: float,
        confidence: float,
        spend_gate_status: str,
    ) -> str:
        return campaign_recommendation_scoring.guardrail_status(
            self.config,
            stage=stage,
            budget_share=budget_share,
            budget_amount=budget_amount,
            confidence=confidence,
            spend_gate_status=spend_gate_status,
        )

    @staticmethod
    def _evidence_class(allocation_item: Mapping[str, Any]) -> str:
        return campaign_recommendation_scoring.evidence_class(allocation_item)

    def _rationale(
        self,
        *,
        stage: str,
        allocation_item: Mapping[str, Any],
        product_cluster: CampaignClusterSelection,
        keyword_cluster: CampaignClusterSelection,
        evidence_class: str,
        guardrail_status: str,
        budget_share: float,
        budget_amount: float,
    ) -> CampaignRecommendationRationale:
        return campaign_recommendation_rationale.build_rationale(
            reason_detail_builder=self._reason_detail,
            stage=stage,
            allocation_item=allocation_item,
            product_cluster=product_cluster,
            keyword_cluster=keyword_cluster,
            evidence_class=evidence_class,
            guardrail_status=guardrail_status,
            budget_share=budget_share,
            budget_amount=budget_amount,
        )

    @staticmethod
    def _sort_key(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
        return campaign_recommendation_scoring.sort_key(item)

    @staticmethod
    def _headline(
        *,
        virus_typ: str,
        recommendations: Sequence[Mapping[str, Any]],
    ) -> str:
        return campaign_recommendation_scoring.headline(
            virus_typ=virus_typ,
            recommendations=recommendations,
        )
