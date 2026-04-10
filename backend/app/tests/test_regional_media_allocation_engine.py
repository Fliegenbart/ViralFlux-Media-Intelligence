import unittest

from app.services.ml.regional_media_allocation_contracts import RegionalMediaAllocationConfig
from app.services.ml.regional_media_allocation_engine import (
    DEFAULT_MEDIA_ALLOCATION_CONFIG,
    RegionalMediaAllocationEngine,
)


def _prediction(
    *,
    bundesland: str,
    bundesland_name: str,
    stage: str,
    priority_score: float,
    event_probability: float,
    forecast_confidence: float,
    source_freshness_score: float,
    usable_source_share: float,
    source_coverage_score: float,
    source_revision_risk: float,
    state_population_millions: float = 0.0,
    uncertainty: list[str] | None = None,
) -> dict:
    return {
        "bundesland": bundesland,
        "bundesland_name": bundesland_name,
        "decision_label": stage.title(),
        "priority_score": priority_score,
        "event_probability_calibrated": event_probability,
        "state_population_millions": state_population_millions,
        "reason_trace": {
            "why": [],
            "contributing_signals": [],
            "uncertainty": uncertainty or [],
            "policy_overrides": [],
        },
        "decision": {
            "stage": stage,
            "decision_score": priority_score,
            "event_probability": event_probability,
            "forecast_confidence": forecast_confidence,
            "source_freshness_score": source_freshness_score,
            "usable_source_share": usable_source_share,
            "source_coverage_score": source_coverage_score,
            "source_revision_risk": source_revision_risk,
            "reason_trace": {
                "why": [],
                "contributing_signals": [],
                "uncertainty": uncertainty or [],
                "policy_overrides": [],
            },
        },
    }


class RegionalMediaAllocationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RegionalMediaAllocationEngine()

    def test_allocate_prioritizes_activate_over_prepare_and_watch(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=20_000,
            predictions=[
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    stage="activate",
                    priority_score=0.84,
                    event_probability=0.80,
                    forecast_confidence=0.77,
                    source_freshness_score=0.92,
                    usable_source_share=0.95,
                    source_coverage_score=0.93,
                    source_revision_risk=0.10,
                    state_population_millions=13.4,
                ),
                _prediction(
                    bundesland="BE",
                    bundesland_name="Berlin",
                    stage="prepare",
                    priority_score=0.63,
                    event_probability=0.61,
                    forecast_confidence=0.64,
                    source_freshness_score=0.75,
                    usable_source_share=0.81,
                    source_coverage_score=0.82,
                    source_revision_risk=0.18,
                    state_population_millions=3.8,
                ),
                _prediction(
                    bundesland="BB",
                    bundesland_name="Brandenburg",
                    stage="watch",
                    priority_score=0.41,
                    event_probability=0.44,
                    forecast_confidence=0.51,
                    source_freshness_score=0.68,
                    usable_source_share=0.73,
                    source_coverage_score=0.74,
                    source_revision_risk=0.22,
                    state_population_millions=2.6,
                ),
            ],
            spend_enabled=True,
            default_products=["GeloMyrtol forte"],
        )

        recommendations = payload["recommendations"]
        self.assertEqual(recommendations[0]["bundesland"], "BY")
        self.assertEqual(recommendations[0]["recommended_activation_level"], "Activate")
        self.assertEqual(recommendations[1]["recommended_activation_level"], "Prepare")
        self.assertEqual(recommendations[2]["recommended_activation_level"], "Watch")
        self.assertGreater(
            recommendations[0]["suggested_budget_share"],
            recommendations[1]["suggested_budget_share"],
        )
        self.assertEqual(recommendations[2]["suggested_budget_share"], 0.0)

    def test_prepare_regions_stay_ranked_but_receive_zero_budget(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=20_000,
            predictions=[
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    stage="prepare",
                    priority_score=0.61,
                    event_probability=0.004,
                    forecast_confidence=0.66,
                    source_freshness_score=0.78,
                    usable_source_share=0.82,
                    source_coverage_score=0.80,
                    source_revision_risk=0.18,
                ),
                _prediction(
                    bundesland="BB",
                    bundesland_name="Brandenburg",
                    stage="watch",
                    priority_score=0.38,
                    event_probability=0.002,
                    forecast_confidence=0.51,
                    source_freshness_score=0.64,
                    usable_source_share=0.70,
                    source_coverage_score=0.71,
                    source_revision_risk=0.22,
                ),
            ],
            spend_enabled=True,
        )

        prepare_item = next(item for item in payload["recommendations"] if item["bundesland"] == "BY")
        self.assertEqual(prepare_item["recommended_activation_level"], "Prepare")
        self.assertEqual(prepare_item["suggested_budget_share"], 0.0)
        self.assertEqual(prepare_item["suggested_budget_eur"], 0.0)
        self.assertEqual(prepare_item["spend_readiness"], "prepare_only")

    def test_budget_shares_sum_to_one_when_spend_is_enabled(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=15_000,
            predictions=[
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    stage="activate",
                    priority_score=0.82,
                    event_probability=0.79,
                    forecast_confidence=0.75,
                    source_freshness_score=0.90,
                    usable_source_share=0.92,
                    source_coverage_score=0.91,
                    source_revision_risk=0.09,
                ),
                _prediction(
                    bundesland="NW",
                    bundesland_name="Nordrhein-Westfalen",
                    stage="prepare",
                    priority_score=0.65,
                    event_probability=0.62,
                    forecast_confidence=0.67,
                    source_freshness_score=0.84,
                    usable_source_share=0.88,
                    source_coverage_score=0.86,
                    source_revision_risk=0.14,
                ),
            ],
            spend_enabled=True,
        )

        total_share = sum(item["suggested_budget_share"] for item in payload["recommendations"])
        self.assertAlmostEqual(total_share, 1.0, places=6)
        self.assertAlmostEqual(payload["summary"]["budget_share_total"], 1.0, places=6)

    def test_low_confidence_region_gets_reduced_allocation(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=12_000,
            predictions=[
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    stage="activate",
                    priority_score=0.78,
                    event_probability=0.74,
                    forecast_confidence=0.78,
                    source_freshness_score=0.90,
                    usable_source_share=0.92,
                    source_coverage_score=0.91,
                    source_revision_risk=0.10,
                ),
                _prediction(
                    bundesland="HE",
                    bundesland_name="Hessen",
                    stage="activate",
                    priority_score=0.78,
                    event_probability=0.74,
                    forecast_confidence=0.36,
                    source_freshness_score=0.42,
                    usable_source_share=0.58,
                    source_coverage_score=0.60,
                    source_revision_risk=0.58,
                    uncertainty=["Thin agreement evidence", "Revision risk still material"],
                ),
            ],
            spend_enabled=True,
        )

        by = next(item for item in payload["recommendations"] if item["bundesland"] == "BY")
        he = next(item for item in payload["recommendations"] if item["bundesland"] == "HE")
        self.assertGreater(by["suggested_budget_share"], he["suggested_budget_share"])
        self.assertGreater(by["confidence"], he["confidence"])

    def test_region_weights_shift_ranking_without_changing_stage_logic(self) -> None:
        weighted_engine = RegionalMediaAllocationEngine(
            config=RegionalMediaAllocationConfig(
                **{
                    **DEFAULT_MEDIA_ALLOCATION_CONFIG.to_dict(),
                    "region_weights": {"BE": 1.25, "BB": 0.85},
                }
            )
        )
        payload = weighted_engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=20_000,
            predictions=[
                _prediction(
                    bundesland="BE",
                    bundesland_name="Berlin",
                    stage="activate",
                    priority_score=0.78,
                    event_probability=0.75,
                    forecast_confidence=0.72,
                    source_freshness_score=0.90,
                    usable_source_share=0.91,
                    source_coverage_score=0.90,
                    source_revision_risk=0.10,
                ),
                _prediction(
                    bundesland="BB",
                    bundesland_name="Brandenburg",
                    stage="activate",
                    priority_score=0.78,
                    event_probability=0.75,
                    forecast_confidence=0.72,
                    source_freshness_score=0.90,
                    usable_source_share=0.91,
                    source_coverage_score=0.90,
                    source_revision_risk=0.10,
                ),
            ],
            spend_enabled=True,
        )

        first, second = payload["recommendations"]
        self.assertEqual(first["bundesland"], "BE")
        self.assertEqual(second["bundesland"], "BB")
        self.assertGreater(first["allocation_score"], second["allocation_score"])
        self.assertGreater(first["suggested_budget_share"], second["suggested_budget_share"])

    def test_alias_fields_match_existing_budget_and_trace_fields(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=10_000,
            predictions=[
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    stage="activate",
                    priority_score=0.80,
                    event_probability=0.77,
                    forecast_confidence=0.75,
                    source_freshness_score=0.88,
                    usable_source_share=0.90,
                    source_coverage_score=0.89,
                    source_revision_risk=0.12,
                ),
            ],
            spend_enabled=True,
        )

        recommendation = payload["recommendations"][0]
        self.assertEqual(
            recommendation["allocation_reason_trace"],
            recommendation["reason_trace"],
        )
        self.assertEqual(
            recommendation["suggested_budget_amount"],
            recommendation["suggested_budget_eur"],
        )
        self.assertTrue(recommendation["reason_trace"]["why_details"])
        self.assertTrue(recommendation["reason_trace"]["budget_driver_details"])

    def test_blocked_spend_keeps_reason_trace_and_zero_budget(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=10_000,
            predictions=[
                _prediction(
                    bundesland="BY",
                    bundesland_name="Bayern",
                    stage="activate",
                    priority_score=0.80,
                    event_probability=0.77,
                    forecast_confidence=0.75,
                    source_freshness_score=0.88,
                    usable_source_share=0.90,
                    source_coverage_score=0.89,
                    source_revision_risk=0.12,
                ),
            ],
            spend_enabled=False,
            spend_blockers=["Quality Gate blockiert Aktivierung."],
        )

        recommendation = payload["recommendations"][0]
        self.assertEqual(recommendation["suggested_budget_share"], 0.0)
        self.assertEqual(recommendation["suggested_budget_eur"], 0.0)
        self.assertTrue(recommendation["reason_trace"]["blockers"])
        self.assertTrue(recommendation["reason_trace"]["blocker_details"])
        self.assertEqual(recommendation["spend_readiness"], "blocked")

    def test_empty_predictions_return_stable_summary(self) -> None:
        payload = self.engine.allocate(
            virus_typ="Influenza A",
            total_budget_eur=10_000,
            predictions=[],
            spend_enabled=False,
        )

        self.assertEqual(payload["virus_typ"], "Influenza A")
        self.assertEqual(payload["recommendations"], [])
        self.assertEqual(payload["summary"]["budget_share_total"], 0)
        self.assertEqual(payload["summary"]["total_budget_allocated"], 0)
        self.assertIsNone(payload["summary"]["top_region"])


if __name__ == "__main__":
    unittest.main()
