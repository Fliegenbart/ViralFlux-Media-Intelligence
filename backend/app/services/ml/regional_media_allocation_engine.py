"""Heuristic, audit-ready regional media allocation on top of decision output."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.ml.regional_media_allocation_contracts import (
    AllocationReasonTrace,
    ClusterRecommendation,
    RegionalAllocationRecommendation,
    RegionalMediaAllocationConfig,
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


DEFAULT_MEDIA_ALLOCATION_CONFIG = RegionalMediaAllocationConfig(
    version="regional_media_allocation_v1",
    baseline_total_budget_eur=50_000.0,
    min_budget_per_active_region_eur=3_000.0,
    max_budget_share_per_region=0.55,
    risk_appetite=0.60,
    label_weights={
        "activate": 1.00,
        "prepare": 0.58,
        "watch": 0.08,
    },
    component_weights={
        "priority_score": 0.34,
        "event_probability": 0.24,
        "forecast_confidence": 0.18,
        "source_quality": 0.14,
        "source_freshness": 0.05,
        "population_weighting": 0.05,
    },
    confidence_thresholds={
        "low": 0.45,
        "medium": 0.60,
    },
    confidence_penalties={
        "low": 0.55,
        "medium": 0.82,
    },
    spend_enabled_labels=("activate",),
    use_population_weighting=True,
    population_reference_millions=8.0,
    watch_budget_share_cap=0.0,
    region_weights={},
)


class RegionalMediaAllocationEngine:
    """Deterministic budget ranking and allocation from regional decision output."""

    def __init__(self, config: RegionalMediaAllocationConfig = DEFAULT_MEDIA_ALLOCATION_CONFIG) -> None:
        self.config = config

    @staticmethod
    def _reason_detail(code: str, message: str, **params: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": code, "message": message}
        if params:
            payload["params"] = params
        return payload

    def allocate(
        self,
        *,
        virus_typ: str,
        predictions: Sequence[Mapping[str, Any]],
        total_budget_eur: float | None = None,
        spend_enabled: bool = True,
        spend_blockers: Sequence[str] | None = None,
        default_products: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        total_budget = max(
            0.0,
            float(
                total_budget_eur
                if total_budget_eur is not None
                else self.config.baseline_total_budget_eur
            ),
        )
        spend_blockers = [str(item) for item in (spend_blockers or []) if str(item).strip()]
        scored_predictions = [
            self._score_prediction(
                virus_typ=virus_typ,
                prediction=prediction,
                default_products=default_products,
                spend_enabled=spend_enabled,
                spend_blockers=spend_blockers,
            )
            for prediction in predictions
        ]
        ranked = sorted(
            scored_predictions,
            key=self._rank_sort_key,
            reverse=True,
        )
        shares = self._allocate_budget_shares(
            ranked,
            total_budget_eur=total_budget,
            spend_enabled=spend_enabled,
        )

        recommendations: list[dict[str, Any]] = []
        for priority_rank, item in enumerate(ranked, start=1):
            share = round(float(shares.get(item["bundesland"]) or 0.0), 6)
            amount = round(total_budget * share, 2)
            reason_trace = self._reason_trace(
                item=item,
                spend_enabled=spend_enabled,
                spend_blockers=spend_blockers,
                share=share,
            )
            recommendation = RegionalAllocationRecommendation(
                bundesland=item["bundesland"],
                bundesland_name=item["bundesland_name"],
                virus_typ=virus_typ,
                recommended_activation_level=item["recommended_activation_level"],
                spend_readiness=item["spend_readiness"],
                priority_rank=priority_rank,
                suggested_budget_share=share,
                suggested_budget_eur=amount,
                allocation_score=round(item["allocation_score"], 4),
                confidence=round(item["confidence"], 4),
                reason_trace=reason_trace,
                product_clusters=item["product_clusters"],
                keyword_clusters=[],
                decision=dict(item["decision"]),
                metadata={
                    "config_version": self.config.version,
                    "event_probability": round(item["event_probability"], 4),
                    "priority_score": round(item["priority_score"], 4),
                    "forecast_confidence": round(item["forecast_confidence"], 4),
                    "source_quality": round(item["source_quality"], 4),
                    "source_freshness": round(item["source_freshness"], 4),
                    "population_weight": round(item["population_weight"], 4),
                    "region_weight": round(item["region_weight"], 4),
                    "uncertainty_count": int(item["uncertainty_count"]),
                    "eligible_for_budget": bool(item["eligible_for_budget"]),
                },
            ).to_dict()
            recommendations.append(recommendation)

        headline = self._headline(
            virus_typ=virus_typ,
            recommendations=recommendations,
            spend_enabled=spend_enabled,
        )
        budget_share_total = round(sum(item["suggested_budget_share"] for item in recommendations), 6)
        return {
            "virus_typ": virus_typ,
            "allocation_policy_version": self.config.version,
            "headline": headline,
            "summary": {
                "activate_regions": sum(
                    1
                    for item in recommendations
                    if str(item["recommended_activation_level"]).lower() == "activate"
                ),
                "prepare_regions": sum(
                    1
                    for item in recommendations
                    if str(item["recommended_activation_level"]).lower() == "prepare"
                ),
                "watch_regions": sum(
                    1
                    for item in recommendations
                    if str(item["recommended_activation_level"]).lower() == "watch"
                ),
                "total_budget_allocated": round(sum(item["suggested_budget_eur"] for item in recommendations), 2),
                "budget_share_total": budget_share_total,
                "weekly_budget": round(total_budget, 2),
                "spend_enabled": bool(spend_enabled),
                "spend_blockers": spend_blockers,
                "top_region": recommendations[0]["bundesland"] if recommendations else None,
                "top_region_activation": (
                    recommendations[0]["recommended_activation_level"] if recommendations else None
                ),
            },
            "recommendations": recommendations,
            "config": self.config.to_dict(),
        }

    def _score_prediction(
        self,
        *,
        virus_typ: str,
        prediction: Mapping[str, Any],
        default_products: Sequence[str] | None,
        spend_enabled: bool,
        spend_blockers: Sequence[str],
    ) -> dict[str, Any]:
        decision = dict(prediction.get("decision") or {})
        bundesland = str(prediction.get("bundesland") or "")
        bundesland_name = str(prediction.get("bundesland_name") or prediction.get("bundesland") or "")
        stage = str(
            decision.get("stage")
            or prediction.get("decision_label")
            or "watch"
        ).strip().lower()
        priority_score = _clamp(float(prediction.get("priority_score") or decision.get("decision_score") or 0.0))
        event_probability = _clamp(
            float(prediction.get("event_probability_calibrated") or decision.get("event_probability") or 0.0)
        )
        forecast_confidence = _clamp(float(decision.get("forecast_confidence") or 0.0))
        source_freshness = _clamp(float(decision.get("source_freshness_score") or 0.0))
        usable_share = _clamp(float(decision.get("usable_source_share") or 0.0))
        coverage_score = _clamp(float(decision.get("source_coverage_score") or 0.0))
        revision_risk = _clamp(float(decision.get("source_revision_risk") or 0.0))
        revision_safety = _clamp(1.0 - revision_risk)
        source_quality = round(
            (source_freshness + usable_share + coverage_score + revision_safety) / 4.0,
            4,
        )
        population_weight = self._population_weight(float(prediction.get("state_population_millions") or 0.0))

        components = {
            "priority_score": priority_score,
            "event_probability": event_probability,
            "forecast_confidence": forecast_confidence,
            "source_quality": source_quality,
            "source_freshness": source_freshness,
            "population_weighting": population_weight if self.config.use_population_weighting else 0.0,
        }
        base_score = sum(
            float(self.config.component_weights.get(key) or 0.0) * float(value)
            for key, value in components.items()
        )

        uncertainty_items = self._uncertainty_items(
            prediction=prediction,
            decision=decision,
        )
        confidence = self._confidence_score(
            forecast_confidence=forecast_confidence,
            source_quality=source_quality,
            uncertainty_count=len(uncertainty_items),
        )
        penalty_multiplier = self._penalty_multiplier(
            confidence=confidence,
            source_freshness=source_freshness,
            revision_risk=revision_risk,
        )
        stage_weight = self._stage_weight(stage)
        region_weight = self._region_weight(
            bundesland=bundesland,
            bundesland_name=bundesland_name,
        )
        allocation_score = round(base_score * stage_weight * penalty_multiplier * region_weight, 4)
        product_clusters = self._default_product_clusters(
            virus_typ=virus_typ,
            allocation_score=allocation_score,
            default_products=default_products,
        )
        eligible_for_budget = bool(
            spend_enabled
            and not spend_blockers
            and stage in set(self.config.spend_enabled_labels)
            and allocation_score > 0.0
        )
        spend_readiness = self._spend_readiness(
            stage=stage,
            confidence=confidence,
            spend_enabled=spend_enabled,
            spend_blockers=spend_blockers,
        )
        return {
            "bundesland": bundesland,
            "bundesland_name": bundesland_name,
            "prediction": dict(prediction),
            "decision": decision,
            "recommended_activation_level": stage.title(),
            "priority_score": priority_score,
            "event_probability": event_probability,
            "forecast_confidence": forecast_confidence,
            "source_quality": source_quality,
            "source_freshness": source_freshness,
            "population_weight": population_weight,
            "region_weight": region_weight,
            "confidence": confidence,
            "allocation_score": allocation_score,
            "eligible_for_budget": eligible_for_budget,
            "spend_readiness": spend_readiness,
            "product_clusters": product_clusters,
            "revision_risk": revision_risk,
            "uncertainty_count": len(uncertainty_items),
        }

    def _stage_weight(self, stage: str) -> float:
        base_weight = float(self.config.label_weights.get(stage) or 0.0)
        risk_appetite = _clamp(float(self.config.risk_appetite))
        if stage == "activate":
            modifier = 0.95 + (0.10 * risk_appetite)
        elif stage == "prepare":
            modifier = 0.55 + (0.75 * risk_appetite)
        else:
            modifier = 0.10 + (0.25 * risk_appetite)
        return round(base_weight * modifier, 4)

    def _population_weight(self, population_millions: float) -> float:
        if not self.config.use_population_weighting or population_millions <= 0.0:
            return 0.0
        reference = max(float(self.config.population_reference_millions), 0.1)
        normalized = math.log1p(max(population_millions, 0.0)) / math.log1p(reference)
        return _clamp(normalized)

    @staticmethod
    def _confidence_score(
        *,
        forecast_confidence: float,
        source_quality: float,
        uncertainty_count: int,
    ) -> float:
        uncertainty_factor = max(0.0, 1.0 - (min(max(uncertainty_count, 0), 4) * 0.10))
        return round(
            _clamp((0.55 * forecast_confidence) + (0.35 * source_quality) + (0.10 * uncertainty_factor)),
            4,
        )

    def _penalty_multiplier(
        self,
        *,
        confidence: float,
        source_freshness: float,
        revision_risk: float,
    ) -> float:
        thresholds = self.config.confidence_thresholds
        penalties = self.config.confidence_penalties
        if confidence < float(thresholds.get("low") or 0.45):
            multiplier = float(penalties.get("low") or 0.55)
        elif confidence < float(thresholds.get("medium") or 0.60):
            multiplier = float(penalties.get("medium") or 0.82)
        else:
            multiplier = 1.0
        if source_freshness < 0.50:
            multiplier *= 0.90
        if revision_risk > 0.55:
            multiplier *= 0.85
        return round(_clamp(multiplier, lower=0.0, upper=1.25), 4)

    @staticmethod
    def _uncertainty_items(
        *,
        prediction: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> list[str]:
        items = list(
            (dict(prediction.get("reason_trace") or {}).get("uncertainty"))
            or (dict(decision.get("reason_trace") or {}).get("uncertainty"))
            or []
        )
        summary = str(prediction.get("uncertainty_summary") or decision.get("uncertainty_summary") or "").strip()
        if summary and summary != "Residual uncertainty is currently limited.":
            items.append(summary)
        return items

    def _region_weight(
        self,
        *,
        bundesland: str,
        bundesland_name: str,
    ) -> float:
        configured = self.config.region_weights or {}
        for key in (
            bundesland,
            bundesland.upper(),
            bundesland_name,
            bundesland_name.lower(),
        ):
            if key in configured:
                return max(float(configured[key]), 0.0)
        return 1.0

    def _allocate_budget_shares(
        self,
        scored_predictions: Sequence[Mapping[str, Any]],
        *,
        total_budget_eur: float,
        spend_enabled: bool,
    ) -> dict[str, float]:
        shares = {
            str(item["bundesland"]): 0.0
            for item in scored_predictions
        }
        if not spend_enabled or total_budget_eur <= 0.0:
            return shares

        eligible = [
            item
            for item in scored_predictions
            if bool(item.get("eligible_for_budget")) and self._share_cap_for_item(item) > 0.0
        ]
        if not eligible:
            return shares

        base_min_share = min(
            float(self.config.min_budget_per_active_region_eur) / max(total_budget_eur, 1.0),
            1.0 / max(len(eligible), 1),
        )
        for item in eligible:
            key = str(item["bundesland"])
            shares[key] = min(base_min_share, self._share_cap_for_item(item))

        remaining = max(0.0, 1.0 - sum(shares.values()))
        while remaining > 1e-9:
            candidates = [
                item
                for item in eligible
                if shares[str(item["bundesland"])] < self._share_cap_for_item(item) - 1e-9
            ]
            if not candidates:
                break

            total_score = sum(float(item.get("allocation_score") or 0.0) for item in candidates)
            loop_remaining = remaining
            additions: dict[str, float] = {}
            applied = 0.0

            for item in candidates:
                key = str(item["bundesland"])
                capacity = self._share_cap_for_item(item) - shares[key]
                if capacity <= 1e-9:
                    continue
                if total_score > 0.0:
                    desired = loop_remaining * (float(item.get("allocation_score") or 0.0) / total_score)
                else:
                    desired = loop_remaining / len(candidates)
                addition = min(capacity, desired)
                additions[key] = addition
                applied += addition

            if applied <= 1e-9:
                break

            for key, addition in additions.items():
                shares[key] += addition
            remaining = max(0.0, remaining - applied)

        positive_keys = [key for key, value in shares.items() if value > 0.0]
        total = sum(shares.values())
        if total > 0.0 and positive_keys:
            for key in positive_keys:
                shares[key] = shares[key] / total
            top_key = max(positive_keys, key=lambda key: shares[key])
            drift = 1.0 - sum(shares.values())
            shares[top_key] += drift

        for key in list(shares):
            shares[key] = round(max(0.0, shares[key]), 6)
        return shares

    def _share_cap_for_item(self, item: Mapping[str, Any]) -> float:
        stage = str(item.get("recommended_activation_level") or "Watch").strip().lower()
        max_share = _clamp(float(self.config.max_budget_share_per_region), lower=0.0, upper=1.0)
        if stage == "watch":
            return min(max_share, _clamp(float(self.config.watch_budget_share_cap), lower=0.0, upper=1.0))
        return max_share

    def _reason_trace(
        self,
        *,
        item: Mapping[str, Any],
        spend_enabled: bool,
        spend_blockers: Sequence[str],
        share: float,
    ) -> AllocationReasonTrace:
        stage = str(item["recommended_activation_level"])
        why = [
            f"{stage} from the decision engine sets the base activation level.",
            f"Priority score {float(item['priority_score']):.2f} and event probability {float(item['event_probability']):.2f} drive the ranking.",
        ]
        why_details = [
            self._reason_detail(
                "decision_stage_base",
                why[0],
                stage=stage.lower(),
            ),
            self._reason_detail(
                "ranking_priority_and_probability",
                why[1],
                priority_score=round(float(item["priority_score"]), 4),
                event_probability=round(float(item["event_probability"]), 4),
            ),
        ]
        budget_drivers: list[str] = []
        budget_driver_details: list[dict[str, Any]] = []
        if stage.lower() == "activate":
            message = "Activate regions receive the strongest label multiplier."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail("budget_driver_activate_multiplier", message)
            )
        elif stage.lower() == "prepare":
            message = "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail("budget_driver_prepare_no_budget_release", message)
            )
        else:
            message = "Watch regions are observation-first and usually receive no spend."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail("budget_driver_watch_observe_only", message)
            )

        if float(item["confidence"]) >= float(self.config.confidence_thresholds.get("medium") or 0.60):
            message = f"Confidence {float(item['confidence']):.2f} keeps the allocation penalty low."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_confidence_low_penalty",
                    message,
                    confidence=round(float(item["confidence"]), 4),
                )
            )
        elif float(item["confidence"]) >= float(self.config.confidence_thresholds.get("low") or 0.45):
            message = f"Confidence {float(item['confidence']):.2f} leads to a moderate spend penalty."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_confidence_moderate_penalty",
                    message,
                    confidence=round(float(item["confidence"]), 4),
                )
            )
        else:
            message = f"Low confidence {float(item['confidence']):.2f} sharply reduces allocation."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_confidence_high_penalty",
                    message,
                    confidence=round(float(item["confidence"]), 4),
                )
            )

        if float(item["population_weight"]) > 0.0:
            message = (
                f"Population weighting contributes {float(item['population_weight']):.2f} to addressable reach."
            )
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_population_weight",
                    message,
                    population_weight=round(float(item["population_weight"]), 4),
                )
            )
        if float(item["region_weight"]) > 1.0:
            message = (
                f"Configured region weight {float(item['region_weight']):.2f} boosts the allocation score."
            )
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_region_weight_boost",
                    message,
                    region_weight=round(float(item["region_weight"]), 4),
                )
            )
        elif float(item["region_weight"]) < 1.0:
            message = (
                f"Configured region weight {float(item['region_weight']):.2f} reduces the allocation score."
            )
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_region_weight_reduce",
                    message,
                    region_weight=round(float(item["region_weight"]), 4),
                )
            )
        if float(item["source_freshness"]) < 0.50:
            message = "Low source freshness adds an extra allocation penalty."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_source_freshness_penalty",
                    message,
                    source_freshness=round(float(item["source_freshness"]), 4),
                )
            )
        if float(item["revision_risk"]) > 0.55:
            message = "High revision risk adds an extra allocation penalty."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_revision_risk_penalty",
                    message,
                    revision_risk=round(float(item["revision_risk"]), 4),
                )
            )
        if share > 0.0:
            message = f"Suggested budget share is {share:.2%}."
            budget_drivers.append(message)
            budget_driver_details.append(
                self._reason_detail(
                    "budget_driver_suggested_share",
                    message,
                    suggested_budget_share=round(float(share), 6),
                )
            )

        uncertainty = list(
            self._uncertainty_items(
                prediction=dict(item["prediction"] or {}),
                decision=dict(item["decision"] or {}),
            )
        )
        uncertainty_details = [
            self._reason_detail("upstream_uncertainty", message)
            for message in uncertainty
        ]
        if float(item["revision_risk"]) > 0.45:
            message = f"Revision risk remains material at {float(item['revision_risk']):.2f}."
            uncertainty.append(message)
            uncertainty_details.append(
                self._reason_detail(
                    "uncertainty_revision_risk_material",
                    message,
                    revision_risk=round(float(item["revision_risk"]), 4),
                )
            )
        if float(item["source_freshness"]) < 0.50:
            message = f"Source freshness is soft at {float(item['source_freshness']):.2f}."
            uncertainty.append(message)
            uncertainty_details.append(
                self._reason_detail(
                    "uncertainty_source_freshness_soft",
                    message,
                    source_freshness=round(float(item["source_freshness"]), 4),
                )
            )

        blockers: list[str] = []
        blocker_details: list[dict[str, Any]] = []
        if stage.lower() == "prepare":
            message = "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet."
            blockers.append(message)
            blocker_details.append(
                self._reason_detail("budget_prepare_no_release", message)
            )
        for blocker in spend_blockers:
            message = str(blocker)
            blockers.append(message)
            blocker_details.append(self._reason_detail("spend_blocker", message))
        if not spend_enabled and not spend_blockers:
            message = "Spend is currently disabled."
            blockers.append(message)
            blocker_details.append(self._reason_detail("spend_disabled", message))
        elif not bool(item["eligible_for_budget"]) and stage.lower() != "prepare" and not spend_blockers:
            message = "Region is not currently eligible for spend under the configured label rules."
            blockers.append(message)
            blocker_details.append(
                self._reason_detail("budget_ineligible_region", message)
            )

        return AllocationReasonTrace(
            why=why,
            why_details=why_details,
            budget_drivers=budget_drivers,
            budget_driver_details=budget_driver_details,
            uncertainty=uncertainty,
            uncertainty_details=uncertainty_details,
            blockers=blockers,
            blocker_details=blocker_details,
        )

    @staticmethod
    def _headline(
        *,
        virus_typ: str,
        recommendations: Sequence[Mapping[str, Any]],
        spend_enabled: bool,
    ) -> str:
        if not recommendations:
            return f"{virus_typ}: keine regionalen Allocation-Empfehlungen verfügbar"
        active_regions = [
            item["bundesland"]
            for item in recommendations
            if float(item.get("suggested_budget_share") or 0.0) > 0.0
        ]
        if active_regions and spend_enabled:
            return f"{virus_typ}: Budget auf {', '.join(active_regions[:3])} fokussieren"
        return f"{virus_typ}: aktuell Beobachtung priorisieren"

    def _spend_readiness(
        self,
        *,
        stage: str,
        confidence: float,
        spend_enabled: bool,
        spend_blockers: Sequence[str],
    ) -> str:
        if not spend_enabled:
            return "blocked"
        if stage == "prepare":
            return "prepare_only"
        if stage not in set(self.config.spend_enabled_labels):
            return "observe"
        if confidence < float(self.config.confidence_thresholds.get("low") or 0.45):
            return "cautious"
        if confidence < float(self.config.confidence_thresholds.get("medium") or 0.60):
            return "guarded"
        if spend_blockers:
            return "blocked"
        return "ready"

    @staticmethod
    def _rank_sort_key(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
        stage = str(item.get("recommended_activation_level") or "Watch").strip().lower()
        stage_order = {"activate": 3, "prepare": 2, "watch": 1}.get(stage, 0)
        return (
            float(stage_order),
            float(item.get("allocation_score") or 0.0),
            float(item.get("priority_score") or 0.0),
            float(item.get("event_probability") or 0.0),
        )

    @staticmethod
    def _default_product_clusters(
        *,
        virus_typ: str,
        allocation_score: float,
        default_products: Sequence[str] | None,
    ) -> list[ClusterRecommendation]:
        products = [str(item) for item in (default_products or []) if str(item).strip()]
        if not products:
            return []
        return [
            ClusterRecommendation(
                cluster_key="gelo_core_respiratory",
                label=f"{virus_typ} core demand cluster",
                priority_rank=1,
                fit_score=round(_clamp(0.45 + (allocation_score * 0.55)), 4),
                products=products,
                metadata={"source": "heuristic_default_product_cluster_v1"},
            )
        ]
