"""Transparent campaign recommendations built on top of regional allocation output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

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


DEFAULT_CAMPAIGN_RECOMMENDATION_CONFIG = CampaignRecommendationConfig(
    version="campaign_recommendation_v1",
    max_recommendations=12,
    product_clusters=(
        ProductClusterConfig(
            cluster_key="gelo_core_respiratory",
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
            cluster_key="gelo_voice_recovery",
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
            cluster_key="gelo_bronchial_support",
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
            product_cluster_key="gelo_core_respiratory",
            keywords=("husten schleim loesen", "bronchitis schleim", "atemwege befreien"),
            supported_viruses=("Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"),
            base_fit=0.84,
            activation_fit={"activate": 1.0, "prepare": 0.92, "watch": 0.70},
            metadata={"intent": "symptom relief", "channel_bias": "search+social"},
        ),
        KeywordClusterConfig(
            cluster_key="voice_relief_search",
            label="Voice Recovery Search",
            product_cluster_key="gelo_voice_recovery",
            keywords=("heiserkeit schnell loswerden", "stimme weg erkaltung", "hals und stimme beruhigen"),
            supported_viruses=("Influenza A", "Influenza B"),
            base_fit=0.80,
            activation_fit={"activate": 0.92, "prepare": 0.90, "watch": 0.72},
            metadata={"intent": "voice/throat", "channel_bias": "search"},
        ),
        KeywordClusterConfig(
            cluster_key="bronchial_recovery_search",
            label="Bronchial Recovery Search",
            product_cluster_key="gelo_bronchial_support",
            keywords=("bronchien verschleimt", "husten bronchien loesen", "atemwege beruhigen"),
            supported_viruses=("RSV A", "Influenza A", "Influenza B"),
            base_fit=0.82,
            activation_fit={"activate": 0.96, "prepare": 0.88, "watch": 0.70},
            metadata={"intent": "bronchial recovery", "channel_bias": "search+programmatic"},
        ),
    ),
    region_product_fit={
        "BE": {"gelo_voice_recovery": 1.18, "gelo_core_respiratory": 0.96},
        "HH": {"gelo_voice_recovery": 1.16, "gelo_core_respiratory": 0.97},
        "HB": {"gelo_voice_recovery": 1.12},
        "BY": {"gelo_core_respiratory": 1.08},
        "BW": {"gelo_core_respiratory": 1.06},
        "NW": {"gelo_core_respiratory": 1.05},
        "BB": {"gelo_bronchial_support": 1.06},
        "MV": {"gelo_bronchial_support": 1.04},
        "SN": {"gelo_bronchial_support": 1.04},
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
                "generated_at": datetime.utcnow().isoformat(),
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
            "generated_at": datetime.utcnow().isoformat(),
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
        confidence = _clamp(float(allocation_item.get("confidence") or 0.0))
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
        products = [str(item) for item in (allocation_item.get("products") or []) if str(item).strip()]
        if products:
            return products
        clusters = allocation_item.get("product_clusters") or []
        collected: list[str] = []
        for cluster in clusters:
            for product in cluster.get("products") or []:
                value = str(product).strip()
                if value and value not in collected:
                    collected.append(value)
        return collected

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
        hinted_clusters = {
            str(item.get("cluster_key") or ""): float(item.get("fit_score") or 0.0)
            for item in (allocation_item.get("product_clusters") or [])
        }
        candidates: list[CampaignClusterSelection] = []
        available_set = {str(product).strip() for product in available_products if str(product).strip()}
        for cluster in self.config.product_clusters:
            if cluster.supported_viruses and virus_typ not in set(cluster.supported_viruses):
                continue
            overlap = self._product_overlap(cluster=cluster, available_products=available_set)
            if overlap <= 0.0:
                continue
            allocation_hint = _clamp(hinted_clusters.get(cluster.cluster_key, 0.0))
            stage_fit = _clamp(float(cluster.activation_fit.get(stage, 0.70)))
            region_multiplier = self._region_fit_multiplier(region=region, cluster_key=cluster.cluster_key)
            raw_fit = (
                0.35 * float(cluster.base_fit)
                + 0.25 * overlap
                + 0.20 * stage_fit
                + 0.10 * confidence
                + 0.10 * allocation_hint
            ) * region_multiplier
            candidates.append(
                CampaignClusterSelection(
                    cluster_key=cluster.cluster_key,
                    label=cluster.label,
                    fit_score=round(_clamp(raw_fit, 0.0, 1.25), 4),
                    products=[product for product in cluster.products if product in available_set],
                    metadata={
                        "source": "campaign_recommendation_v1",
                        "base_fit": round(float(cluster.base_fit), 4),
                        "product_overlap": round(overlap, 4),
                        "stage_fit": round(stage_fit, 4),
                        "allocation_hint": round(allocation_hint, 4),
                        "region_fit_multiplier": round(region_multiplier, 4),
                        **dict(cluster.metadata or {}),
                    },
                )
            )
        if candidates:
            candidates.sort(key=lambda item: (float(item.fit_score), len(item.products)), reverse=True)
            return candidates[0]

        return CampaignClusterSelection(
            cluster_key="unmapped_product_cluster",
            label="Fallback Product Cluster",
            fit_score=round(_clamp(0.40 + (confidence * 0.20)), 4),
            products=list(available_products),
            metadata={"source": "campaign_recommendation_fallback"},
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
        candidates: list[CampaignClusterSelection] = []
        for cluster in self.config.keyword_clusters:
            if cluster.product_cluster_key != product_cluster.cluster_key:
                continue
            if cluster.supported_viruses and virus_typ not in set(cluster.supported_viruses):
                continue
            stage_fit = _clamp(float(cluster.activation_fit.get(stage, 0.70)))
            region_multiplier = self._region_fit_multiplier(region=region, cluster_key=cluster.product_cluster_key)
            raw_fit = (
                0.50 * float(product_cluster.fit_score)
                + 0.25 * float(cluster.base_fit)
                + 0.15 * stage_fit
                + 0.10 * confidence
            ) * region_multiplier
            candidates.append(
                CampaignClusterSelection(
                    cluster_key=cluster.cluster_key,
                    label=cluster.label,
                    fit_score=round(_clamp(raw_fit, 0.0, 1.25), 4),
                    keywords=list(cluster.keywords),
                    metadata={
                        "source": "campaign_recommendation_v1",
                        "product_cluster_key": cluster.product_cluster_key,
                        "base_fit": round(float(cluster.base_fit), 4),
                        "stage_fit": round(stage_fit, 4),
                        "region_fit_multiplier": round(region_multiplier, 4),
                        **dict(cluster.metadata or {}),
                    },
                )
            )
        if candidates:
            candidates.sort(key=lambda item: (float(item.fit_score), len(item.keywords)), reverse=True)
            return candidates[0]

        return CampaignClusterSelection(
            cluster_key="fallback_keyword_cluster",
            label="Fallback Search Demand Cluster",
            fit_score=round(_clamp(0.35 + (0.25 * confidence)), 4),
            keywords=["atemwege beruhigen", "husten symptomhilfe", "erkaltung beschwerden"],
            metadata={"source": "campaign_recommendation_fallback"},
        )

    @staticmethod
    def _product_overlap(
        *,
        cluster: ProductClusterConfig,
        available_products: set[str],
    ) -> float:
        if not cluster.products:
            return 0.0
        overlap = len(set(cluster.products) & set(available_products))
        return _clamp(overlap / max(len(set(cluster.products)), 1))

    def _region_fit_multiplier(self, *, region: str, cluster_key: str) -> float:
        region_fits = self.config.region_product_fit or {}
        return max(float((region_fits.get(region) or {}).get(cluster_key) or 1.0), 0.0)

    def _guardrail_status(
        self,
        *,
        stage: str,
        budget_share: float,
        budget_amount: float,
        confidence: float,
        spend_gate_status: str,
    ) -> str:
        guardrails = self.config.spend_guardrails
        normalized_spend_status = str(spend_gate_status or "").strip()
        if stage == "watch" or budget_amount <= 0.0:
            return "observe_only"
        if normalized_spend_status in set(guardrails.blocked_spend_statuses):
            return "blocked"
        confidence_floor = (
            float(guardrails.min_confidence_for_activate)
            if stage == "activate"
            else float(guardrails.min_confidence_for_prepare)
        )
        if confidence < confidence_floor:
            return "low_confidence_review"
        if (
            budget_amount < float(guardrails.min_budget_amount_eur)
            or budget_share < float(guardrails.min_budget_share)
        ):
            return "bundle_with_neighbor_region"
        return "ready"

    @staticmethod
    def _evidence_class(allocation_item: Mapping[str, Any]) -> str:
        evidence_status = str(allocation_item.get("evidence_status") or "").strip()
        if evidence_status:
            return evidence_status
        if allocation_item.get("truth_layer_enabled"):
            return "truth_layer_pending"
        return "epidemiological_only"

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
        region_name = str(
            allocation_item.get("bundesland_name")
            or allocation_item.get("region_name")
            or allocation_item.get("bundesland")
            or ""
        )
        confidence = float(allocation_item.get("confidence") or 0.0)
        why = [
            f"{region_name} stays on {stage} with budget share {budget_share:.2%}.",
            f"Allocation confidence {confidence:.2f} and priority rank {int(allocation_item.get('priority_rank') or 0)} keep the region in the current wave plan.",
        ]
        product_fit = [
            f"{product_cluster.label} scores {float(product_cluster.fit_score):.2f} for the available product set {product_cluster.products or allocation_item.get('products') or []}.",
        ]
        region_multiplier = float(product_cluster.metadata.get("region_fit_multiplier") or 1.0)
        if region_multiplier > 1.0:
            product_fit.append(f"Region/product fit boosts this cluster by {region_multiplier:.2f}.")
        keyword_fit = [
            f"{keyword_cluster.label} translates the product cluster into concrete search intent with fit {float(keyword_cluster.fit_score):.2f}.",
        ]
        budget_notes = [
            f"Suggested campaign budget is {budget_amount:.2f} EUR.",
        ]
        if budget_share > 0.0:
            budget_notes.append(f"Budget share contribution is {budget_share:.2%}.")

        evidence_notes = [
            f"Evidence class is {evidence_class}.",
        ]
        signal_outcome_agreement = allocation_item.get("signal_outcome_agreement") or {}
        if signal_outcome_agreement.get("status"):
            evidence_notes.append(
                f"Signal/outcome agreement is {signal_outcome_agreement.get('status')}."
            )

        guardrails: list[str] = []
        if guardrail_status == "ready":
            guardrails.append("Spend guardrails are currently satisfied.")
        elif guardrail_status == "bundle_with_neighbor_region":
            guardrails.append("Budget is below the standalone threshold and should be bundled with a neighboring region or shared flight.")
        elif guardrail_status == "low_confidence_review":
            guardrails.append("Confidence is below the stage-specific guardrail, so the recommendation needs manual PEIX review.")
        elif guardrail_status == "blocked":
            guardrails.append("Operational or commercial spend gate is still blocking execution.")
        else:
            guardrails.append("Recommendation stays discussion-only for now.")

        return CampaignRecommendationRationale(
            why=why,
            product_fit=product_fit,
            keyword_fit=keyword_fit,
            budget_notes=budget_notes,
            evidence_notes=evidence_notes,
            guardrails=guardrails,
        )

    @staticmethod
    def _sort_key(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
        stage = str(item.get("activation_level") or "Watch").strip().lower()
        stage_order = {"activate": 3, "prepare": 2, "watch": 1}.get(stage, 0)
        guardrail_order = {
            "ready": 3,
            "bundle_with_neighbor_region": 2,
            "low_confidence_review": 1.5,
            "observe_only": 1,
            "blocked": 0,
        }.get(str(item.get("spend_guardrail_status") or ""), 0)
        return (
            float(stage_order),
            float(guardrail_order),
            float(item.get("suggested_budget_share") or 0.0),
            float(item.get("confidence") or 0.0),
        )

    @staticmethod
    def _headline(
        *,
        virus_typ: str,
        recommendations: Sequence[Mapping[str, Any]],
    ) -> str:
        if not recommendations:
            return f"{virus_typ}: keine Campaign Recommendations verfügbar"
        lead = recommendations[0]
        region = str(lead.get("region") or lead.get("bundesland") or "")
        cluster = ((lead.get("recommended_product_cluster") or {}).get("label")) or "Campaign Cluster"
        return f"{virus_typ}: {region} jetzt mit {cluster} diskutieren"
