import unittest
from unittest.mock import patch

from app.services.media.campaign_recommendation_contracts import (
    CampaignClusterSelection,
    CampaignRecommendationRationale,
)
from app.services.media.campaign_recommendation_service import CampaignRecommendationService


def _allocation_item(
    *,
    bundesland: str,
    bundesland_name: str,
    activation_level: str,
    budget_share: float,
    budget_amount: float,
    confidence: float,
    products: list[str],
    evidence_status: str = "truth_backed",
    spend_gate_status: str = "released",
    budget_release_recommendation: str = "release",
) -> dict:
    return {
        "bundesland": bundesland,
        "bundesland_name": bundesland_name,
        "recommended_activation_level": activation_level,
        "priority_rank": 1,
        "suggested_budget_share": budget_share,
        "suggested_budget_eur": budget_amount,
        "suggested_budget_amount": budget_amount,
        "confidence": confidence,
        "products": products,
        "channels": ["Banner (programmatic)", "Meta (regional)"],
        "timeline": "Sofort aktivieren",
        "allocation_score": 0.9,
        "spend_gate_status": spend_gate_status,
        "budget_release_recommendation": budget_release_recommendation,
        "evidence_status": evidence_status,
        "signal_outcome_agreement": {
            "status": "strong",
            "signal_present": True,
            "historical_response_observed": True,
        },
        "truth_layer_enabled": True,
        "product_clusters": [
            {
                "cluster_key": "gelo_core_respiratory",
                "label": "Influenza A core demand cluster",
                "priority_rank": 1,
                "fit_score": 0.84,
                "products": products,
            }
        ],
    }


class CampaignRecommendationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CampaignRecommendationService()

    def test_recommend_from_allocation_builds_ranked_campaign_output(self) -> None:
        payload = self.service.recommend_from_allocation(
            allocation_payload={
                "virus_typ": "Influenza A",
                "summary": {"total_budget_allocated": 30000.0},
                "truth_layer": {"enabled": True, "scopes_evaluated": 2},
                "recommendations": [
                    _allocation_item(
                        bundesland="BY",
                        bundesland_name="Bayern",
                        activation_level="Activate",
                        budget_share=0.42,
                        budget_amount=21000.0,
                        confidence=0.83,
                        products=["GeloMyrtol forte", "GeloRevoice"],
                        evidence_status="commercially_validated",
                    ),
                    _allocation_item(
                        bundesland="BE",
                        bundesland_name="Berlin",
                        activation_level="Prepare",
                        budget_share=0.18,
                        budget_amount=9000.0,
                        confidence=0.69,
                        products=["GeloMyrtol forte", "GeloRevoice"],
                    ),
                ],
            }
        )

        self.assertEqual(payload["summary"]["total_recommendations"], 2)
        first = payload["recommendations"][0]
        self.assertEqual(first["region"], "BY")
        self.assertEqual(first["activation_level"], "Activate")
        self.assertEqual(first["recommended_product_cluster"]["cluster_key"], "gelo_core_respiratory")
        self.assertEqual(first["recommended_keyword_cluster"]["cluster_key"], "respiratory_relief_search")
        self.assertEqual(first["spend_guardrail_status"], "ready")
        self.assertTrue(first["recommendation_rationale"]["why"])
        self.assertTrue(first["recommendation_rationale"]["why_details"])
        self.assertTrue(first["recommendation_rationale"]["product_fit"])
        self.assertTrue(first["recommendation_rationale"]["product_fit_details"])
        self.assertTrue(first["recommendation_rationale"]["keyword_fit"])
        self.assertTrue(first["recommendation_rationale"]["keyword_fit_details"])
        self.assertTrue(first["recommendation_rationale"]["guardrail_details"])

    def test_region_product_fit_can_boost_voice_cluster_for_berlin(self) -> None:
        payload = self.service.recommend_from_allocation(
            allocation_payload={
                "virus_typ": "Influenza A",
                "recommendations": [
                    _allocation_item(
                        bundesland="BE",
                        bundesland_name="Berlin",
                        activation_level="Prepare",
                        budget_share=0.16,
                        budget_amount=8000.0,
                        confidence=0.72,
                        products=["GeloRevoice", "GeloMyrtol forte"],
                    ),
                ],
            }
        )

        first = payload["recommendations"][0]
        self.assertEqual(first["recommended_product_cluster"]["cluster_key"], "gelo_voice_recovery")
        self.assertEqual(first["recommended_keyword_cluster"]["cluster_key"], "voice_relief_search")
        self.assertIn("boosts this cluster", " ".join(first["recommendation_rationale"]["product_fit"]))

    def test_guardrails_mark_small_budget_campaign_for_bundling(self) -> None:
        payload = self.service.recommend_from_allocation(
            allocation_payload={
                "virus_typ": "Influenza A",
                "recommendations": [
                    _allocation_item(
                        bundesland="HH",
                        bundesland_name="Hamburg",
                        activation_level="Prepare",
                        budget_share=0.03,
                        budget_amount=1200.0,
                        confidence=0.64,
                        products=["GeloRevoice"],
                        spend_gate_status="guarded_release",
                        budget_release_recommendation="limited_release",
                    ),
                ],
            }
        )

        first = payload["recommendations"][0]
        self.assertEqual(first["spend_guardrail_status"], "bundle_with_neighbor_region")
        self.assertIn(
            "bundled with a neighboring region",
            " ".join(first["recommendation_rationale"]["guardrails"]),
        )

    def test_prepare_recommendation_without_budget_stays_discussion_only(self) -> None:
        payload = self.service.recommend_from_allocation(
            allocation_payload={
                "virus_typ": "Influenza A",
                "recommendations": [
                    _allocation_item(
                        bundesland="BE",
                        bundesland_name="Berlin",
                        activation_level="Prepare",
                        budget_share=0.0,
                        budget_amount=0.0,
                        confidence=0.69,
                        products=["GeloRevoice"],
                        spend_gate_status="guarded_release",
                        budget_release_recommendation="hold",
                    ),
                ],
            }
        )

        first = payload["recommendations"][0]
        self.assertEqual(first["spend_guardrail_status"], "observe_only")
        self.assertIn(
            "Berlin is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
            first["recommendation_rationale"]["why"],
        )
        self.assertEqual(
            first["recommendation_rationale"]["guardrails"],
            ["Recommendation stays preparation-only for now."],
        )
        self.assertIn(
            "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
            first["recommendation_rationale"]["budget_notes"],
        )

    def test_empty_allocation_returns_stable_payload(self) -> None:
        payload = self.service.recommend_from_allocation(
            allocation_payload={
                "virus_typ": "Influenza A",
                "status": "no_data",
                "message": "Keine regionalen Forecast-/Decision-Daten verfügbar.",
                "recommendations": [],
            }
        )

        self.assertEqual(payload["status"], "no_data")
        self.assertEqual(payload["recommendations"], [])
        self.assertEqual(payload["summary"]["total_recommendations"], 0)
        self.assertIn("config", payload)

    def test_available_products_wrapper_delegates_to_scoring_module(self) -> None:
        allocation_item = _allocation_item(
            bundesland="BY",
            bundesland_name="Bayern",
            activation_level="Activate",
            budget_share=0.42,
            budget_amount=21000.0,
            confidence=0.83,
            products=["GeloMyrtol forte"],
        )

        with patch(
            "app.services.media.campaign_recommendation_scoring.available_products",
            return_value=["Delegated Product"],
        ) as mocked:
            result = self.service._available_products(allocation_item)

        self.assertEqual(result, ["Delegated Product"])
        mocked.assert_called_once_with(allocation_item)

    def test_guardrail_status_wrapper_delegates_to_scoring_module(self) -> None:
        with patch(
            "app.services.media.campaign_recommendation_scoring.guardrail_status",
            return_value="delegated_guardrail",
        ) as mocked:
            result = self.service._guardrail_status(
                stage="prepare",
                budget_share=0.2,
                budget_amount=6000.0,
                confidence=0.7,
                spend_gate_status="released",
            )

        self.assertEqual(result, "delegated_guardrail")
        mocked.assert_called_once_with(
            self.service.config,
            stage="prepare",
            budget_share=0.2,
            budget_amount=6000.0,
            confidence=0.7,
            spend_gate_status="released",
        )

    def test_rationale_wrapper_delegates_to_rationale_module(self) -> None:
        allocation_item = _allocation_item(
            bundesland="BE",
            bundesland_name="Berlin",
            activation_level="Prepare",
            budget_share=0.18,
            budget_amount=9000.0,
            confidence=0.69,
            products=["GeloRevoice"],
        )
        product_cluster = CampaignClusterSelection(
            cluster_key="voice_cluster",
            label="Voice Cluster",
            fit_score=0.9,
        )
        keyword_cluster = CampaignClusterSelection(
            cluster_key="voice_keywords",
            label="Voice Keywords",
            fit_score=0.88,
            keywords=["voice help"],
        )
        delegated = CampaignRecommendationRationale(guardrails=["delegated"])

        with patch(
            "app.services.media.campaign_recommendation_rationale.build_rationale",
            return_value=delegated,
        ) as mocked:
            result = self.service._rationale(
                stage="Prepare",
                allocation_item=allocation_item,
                product_cluster=product_cluster,
                keyword_cluster=keyword_cluster,
                evidence_class="truth_backed",
                guardrail_status="ready",
                budget_share=0.18,
                budget_amount=9000.0,
            )

        self.assertIs(result, delegated)
        mocked.assert_called_once_with(
            reason_detail_builder=self.service._reason_detail,
            stage="Prepare",
            allocation_item=allocation_item,
            product_cluster=product_cluster,
            keyword_cluster=keyword_cluster,
            evidence_class="truth_backed",
            guardrail_status="ready",
            budget_share=0.18,
            budget_amount=9000.0,
        )

    def test_headline_wrapper_delegates_to_scoring_module(self) -> None:
        recommendations = [{"region": "BY"}]

        with patch(
            "app.services.media.campaign_recommendation_scoring.headline",
            return_value="delegated headline",
        ) as mocked:
            result = self.service._headline(virus_typ="Influenza A", recommendations=recommendations)

        self.assertEqual(result, "delegated headline")
        mocked.assert_called_once_with(virus_typ="Influenza A", recommendations=recommendations)


if __name__ == "__main__":
    unittest.main()
