import os
import unittest
from unittest.mock import patch

# Minimal env bootstrap for app settings during module import.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine


class OpportunityEngineGenerationWrapperTests(unittest.TestCase):
    def test_generate_opportunities_delegates_to_generation_module(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        with patch(
            "app.services.marketing_engine.opportunity_engine_generation.generate_opportunities",
            return_value={"meta": {"total_opportunities": 0}, "opportunities": []},
        ) as mocked:
            result = MarketingOpportunityEngine.generate_opportunities(engine)

        mocked.assert_called_once_with(engine)
        self.assertEqual(result["opportunities"], [])

    def test_forecast_first_candidates_delegates_to_generation_module(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)
        expected = [{"region_code": "SH"}]

        with patch(
            "app.services.marketing_engine.opportunity_engine_generation._forecast_first_candidates",
            return_value=expected,
        ) as mocked:
            result = MarketingOpportunityEngine._forecast_first_candidates(
                engine,
                opportunities=[{"id": "opp-1"}],
                brand="gelo",
                virus_typ="Influenza A",
                region_scope=["SH"],
                max_cards=2,
            )

        mocked.assert_called_once_with(
            engine,
            opportunities=[{"id": "opp-1"}],
            brand="gelo",
            virus_typ="Influenza A",
            region_scope=["SH"],
            max_cards=2,
        )
        self.assertEqual(result, expected)


class OpportunityEngineGenerationBehaviorTests(unittest.TestCase):
    def test_supply_gap_priority_uses_highest_multiplier_for_condition(self) -> None:
        opportunities = [
            {
                "id": "epi-1",
                "type": "RESPIRATORY_ALERT",
                "_condition": "bronchitis_husten",
                "urgency_score": 70.0,
            },
            {
                "id": "gap-1",
                "type": "MARKET_SUPPLY_GAP",
                "_condition": "bronchitis_husten",
                "_priority_multiplier": 1.2,
                "_supply_gap_sku": "SKU-1",
                "_supply_gap_product": "Product 1",
                "_matched_products": ["Product 1"],
            },
            {
                "id": "gap-2",
                "type": "MARKET_SUPPLY_GAP",
                "_condition": "bronchitis_husten",
                "_priority_multiplier": 1.5,
                "_supply_gap_sku": "SKU-2",
                "_supply_gap_product": "Product 2",
                "_matched_products": ["Product 2"],
            },
        ]

        result = MarketingOpportunityEngine._apply_supply_gap_priority_multipliers(opportunities)

        self.assertEqual(result[0]["urgency_score"], 105.0)
        self.assertTrue(result[0]["_supply_gap_applied"])
        self.assertEqual(result[0]["_supply_gap_priority_multiplier"], 1.5)
        self.assertEqual(result[0]["_supply_gap_sku"], "SKU-2")

    def test_forecast_first_candidates_still_respects_service_override_for_secondary_modifier(self) -> None:
        class OverrideEngine(MarketingOpportunityEngine):
            def _secondary_modifier_from_opportunities(
                self,
                *,
                opportunities,
                region_code,
            ):
                return 1.15, [{"type": "override", "reason": region_code, "urgency_score": 77.0}]

        engine = OverrideEngine.__new__(OverrideEngine)
        engine._normalize_region_token = lambda value: value
        engine._select_forecast_playbook_key = lambda virus_typ: "ERKAELTUNGSWELLE"
        engine._region_label = lambda code: f"Region {code}"
        engine.db = object()

        class StubForecastDecisionService:
            def __init__(self, db):
                self.db = db

            def build_forecast_bundle(self, *, virus_typ, target_source):
                return {
                    "burden_forecast": {"points": [{"forecast_date": "2026-01-01", "predicted_value": 1}]},
                    "event_forecast": {
                        "event_probability": 0.42,
                        "reliability_score": 0.61,
                        "calibration_passed": True,
                        "threshold_value": 10.0,
                        "baseline_value": 8.0,
                    },
                    "forecast_quality": {"forecast_readiness": "GO", "timing_metrics": {"best_lag_days": 9}},
                }

            def build_opportunity_assessment(self, *, virus_typ, target_source, brand, secondary_modifier):
                return {
                    "decision_priority_index": 57.0,
                    "action_class": "market_watch",
                    "secondary_modifier_seen": secondary_modifier,
                }

        with patch(
            "app.services.marketing_engine.opportunity_engine_generation.ForecastDecisionService",
            StubForecastDecisionService,
        ):
            candidates = MarketingOpportunityEngine._forecast_first_candidates(
                engine,
                opportunities=[{"id": "opp-1"}],
                brand="gelo",
                virus_typ="Influenza A",
                region_scope=["SH"],
                max_cards=1,
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["opportunity_assessment"]["secondary_modifier_seen"],
            1.15,
        )
        self.assertEqual(candidates[0]["priority_score"], 57.0)
        self.assertEqual(
            candidates[0]["trigger_snapshot"]["values"]["decision_priority_index"],
            57.0,
        )
        self.assertNotIn("expected_value_index", candidates[0]["trigger_snapshot"]["values"])
        self.assertEqual(candidates[0]["exploratory_signals"][0]["type"], "override")

    def test_kreis_bundesland_still_respects_engine_override_map(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)
        engine._KREIS_BL_MAP = {"LK Override": "Override-Land"}

        result = MarketingOpportunityEngine._kreis_bundesland(engine, "LK Override")

        self.assertEqual(result, "Override-Land")

    def test_enrich_kreis_targeting_uses_engine_override_condition_cluster_map(self) -> None:
        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def group_by(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def all(self):
                return [type("Row", (), {"kreis": "LK Override", "total_faelle": 44})()]

            def scalar(self):
                return None

        class FakeDb:
            def query(self, *args, **kwargs):
                return FakeQuery()

        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)
        engine.db = FakeDb()
        engine._CONDITION_CLUSTER_MAP = {"custom_condition": "RESPIRATORY"}
        engine._kreis_bundesland = lambda kreis_name: "Override-Land"

        opportunities = [{"_condition": "custom_condition", "region_target": {}}]

        result = MarketingOpportunityEngine._enrich_kreis_targeting(engine, opportunities)

        self.assertEqual(result[0]["region_target"]["top_kreise"], ["LK Override"])
        self.assertEqual(
            result[0]["region_target"]["kreis_detail"][0]["bundesland"],
            "Override-Land",
        )
        self.assertEqual(result[0]["region_target"]["states"], ["Override-Land"])


if __name__ == "__main__":
    unittest.main()
