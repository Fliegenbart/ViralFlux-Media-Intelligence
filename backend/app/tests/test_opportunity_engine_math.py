import unittest
import os
from datetime import datetime, timezone

# Minimal env bootstrap for app settings during module import.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.models.database import MarketingOpportunity
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine


class OpportunityEngineMathTests(unittest.TestCase):
    def test_extract_improvement_vs_baselines_supports_flat_schema(self) -> None:
        persistence, seasonal = MarketingOpportunityEngine._extract_improvement_vs_baselines(
            {
                "mae_vs_persistence_pct": 12.5,
                "mae_vs_seasonal_pct": -4.2,
            }
        )

        self.assertEqual(persistence, 12.5)
        self.assertEqual(seasonal, -4.2)

    def test_extract_improvement_vs_baselines_supports_legacy_nested_schema(self) -> None:
        persistence, seasonal = MarketingOpportunityEngine._extract_improvement_vs_baselines(
            {
                "persistence": {"mae_improvement_pct": 9.1},
                "seasonal_naive": {"mae_improvement_pct": 2.7},
            }
        )

        self.assertEqual(persistence, 9.1)
        self.assertEqual(seasonal, 2.7)

    def test_derive_playbook_workflow_status_requires_model_readiness(self) -> None:
        self.assertEqual(
            MarketingOpportunityEngine._derive_playbook_workflow_status(85.0, True),
            "READY",
        )
        self.assertEqual(
            MarketingOpportunityEngine._derive_playbook_workflow_status(85.0, False),
            "DRAFT",
        )
        self.assertEqual(
            MarketingOpportunityEngine._derive_playbook_workflow_status(70.0, True),
            "DRAFT",
        )

    def test_derive_activation_workflow_status_is_neutral_alias_for_legacy_helper(self) -> None:
        self.assertEqual(
            MarketingOpportunityEngine._derive_activation_workflow_status(85.0, True),
            "READY",
        )
        self.assertEqual(
            MarketingOpportunityEngine._derive_activation_workflow_status(85.0, False),
            "DRAFT",
        )
        self.assertEqual(
            MarketingOpportunityEngine._derive_playbook_workflow_status(85.0, True),
            MarketingOpportunityEngine._derive_activation_workflow_status(85.0, True),
        )

    def test_public_fact_value_humanizes_internal_tokens_and_percentages(self) -> None:
        self.assertEqual(
            MarketingOpportunityEngine._public_fact_value("event", "RESPIRATORY_GROWTH_HALSSCHMERZ"),
            "zunehmende Halsschmerz- und Heiserkeitssignale",
        )
        self.assertEqual(
            MarketingOpportunityEngine._public_fact_value("source", "BfArM_API"),
            "BfArM Engpassmonitor",
        )
        self.assertEqual(
            MarketingOpportunityEngine._public_fact_value("growth_pct", 12.345),
            "12.3%",
        )

    def test_fact_label_uses_customer_facing_overrides(self) -> None:
        self.assertEqual(
            MarketingOpportunityEngine._fact_label("bfarm_risk_score"),
            "BfArM-Risikoscore",
        )
        self.assertEqual(
            MarketingOpportunityEngine._fact_label("latest_incidence"),
            "aktuelle Inzidenz",
        )

    def test_fact_label_uses_neutral_ranking_signal_wording_for_legacy_and_new_keys(self) -> None:
        self.assertEqual(
            MarketingOpportunityEngine._fact_label("peix_score"),
            "Ranking-Signal",
        )
        self.assertEqual(
            MarketingOpportunityEngine._fact_label("ranking_signal_score"),
            "Ranking-Signal",
        )

    def test_derive_ranking_signal_context_exposes_neutral_aliases(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        context = MarketingOpportunityEngine._derive_ranking_signal_context(
            engine,
            {"SH": {
                "score_0_100": 66.0,
                "risk_band": "ready",
                "impact_probability": 71.0,
                "top_drivers": [{"label": "Nordsignal"}],
            }},
            "SH",
            {"trigger_context": {"event": "SUPPLY_SHOCK_WINDOW"}},
        )

        self.assertEqual(context["ranking_signal_score"], 66.0)
        self.assertEqual(context["signal_band"], "ready")
        self.assertEqual(context["signal_drivers"], [{"label": "Nordsignal"}])
        self.assertEqual(context["trigger_event"], "SUPPLY_SHOCK_WINDOW")

    def test_build_decision_brief_sets_signal_confidence_contract_source(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        brief = MarketingOpportunityEngine._build_decision_brief(
            engine,
            urgency_score=82.0,
            recommendation_reason="Frühes Nordsignal",
            trigger_context={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            trigger_snapshot={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            trigger_evidence={"source": "BfArM_API", "confidence": 0.81},
            peix_context={"score": 67.0, "impact_probability": 71.0},
            region_codes=["SH"],
            condition_key="erkaltung_akut",
            condition_label="Akute Erkältung",
            recommended_product="GeloProsed",
            mapping_status="approved",
            mapping_reason="Produkt passt zur Lageklasse.",
            mapping_candidate_product=None,
            suggested_products=[],
            budget_shift_pct=18.0,
            budget_shift_pct_fallback=None,
            forecast_assessment={"event_forecast": {"event_probability": 0.42}},
            opportunity_assessment={"truth_readiness": "im_aufbau", "decision_priority_index": 58.0},
        )

        self.assertEqual(
            brief["expectation"]["field_contracts"]["signal_confidence_pct"]["source"],
            "BfArM Engpassmonitor",
        )
        self.assertEqual(brief["expectation"]["decision_priority_index"], 58.0)
        self.assertNotIn("expected_value_index", brief["expectation"])

    def test_build_decision_brief_uses_neutral_ranking_signal_contract_source(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        brief = MarketingOpportunityEngine._build_decision_brief(
            engine,
            urgency_score=82.0,
            recommendation_reason="Frühes Nordsignal",
            trigger_context={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            trigger_snapshot={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            trigger_evidence={"source": "BfArM_API", "confidence": 0.81},
            peix_context={"score": 67.0, "impact_probability": 71.0},
            region_codes=["SH"],
            condition_key="erkaltung_akut",
            condition_label="Akute Erkältung",
            recommended_product="GeloProsed",
            mapping_status="approved",
            mapping_reason="Produkt passt zur Lageklasse.",
            mapping_candidate_product=None,
            suggested_products=[],
            budget_shift_pct=18.0,
            budget_shift_pct_fallback=None,
            forecast_assessment={"event_forecast": {"event_probability": 0.42}},
            opportunity_assessment={"truth_readiness": "im_aufbau", "decision_priority_index": 58.0},
        )

        self.assertEqual(
            brief["expectation"]["field_contracts"]["signal_score"]["source"],
            "RankingSignal",
        )
        self.assertEqual(
            brief["expectation"]["field_contracts"]["impact_probability"]["source"],
            "RankingSignal",
        )
        self.assertEqual(brief["expectation"]["decision_priority_index"], 58.0)
        self.assertNotIn("expected_value_index", brief["expectation"])

    def test_build_campaign_pack_and_preview_expose_ranking_signal_context_alias(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        campaign_payload = MarketingOpportunityEngine._build_campaign_pack(
            engine,
            opportunity={
                "type": "RESOURCE_SCARCITY",
                "target_audience": ["Apotheken"],
                "trigger_context": {
                    "source": "BfArM_API",
                    "event": "SUPPLY_SHOCK_WINDOW",
                    "details": "Signal aus Norddeutschland",
                },
            },
            brand="gelo",
            product="GeloProsed",
            campaign_goal="Absatz sichern",
            region="Schleswig-Holstein",
            urgency=82.0,
            confidence=0.81,
            weekly_budget=120000.0,
            budget_shift_pct=18.0,
            budget_shift_value=21600.0,
            channel_mix={"search": 50.0, "social": 50.0},
            activation_window={
                "start": "2026-04-10T00:00:00",
                "end": "2026-04-20T00:00:00",
                "flight_days": 11,
            },
            product_mapping={
                "recommended_product": "GeloProsed",
                "mapping_status": "approved",
            },
            region_codes=["SH"],
            peix_context={
                "region_code": "SH",
                "score": 67.0,
                "signal_score": 69.0,
                "impact_probability": 71.0,
            },
        )
        preview = MarketingOpportunityEngine._campaign_preview_from_payload(engine, campaign_payload)

        self.assertEqual(
            campaign_payload["ranking_signal_context"],
            campaign_payload["peix_context"],
        )
        self.assertEqual(
            preview["ranking_signal_context"],
            preview["peix_context"],
        )

    def test_model_to_dict_builds_customer_facing_payload(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-123",
            opportunity_type="SUPPLY_SHOCK_ATTACK",
            status="DRAFT",
            urgency_score=82.0,
            region_target={"states": ["SH"]},
            trigger_source="BfArM_API",
            trigger_event="SUPPLY_SHOCK_WINDOW",
            trigger_details={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            target_audience=["Apotheken"],
            brand="gelo",
            product="GeloProsed",
            budget_shift_pct=18.0,
            channel_mix={"search": 50.0},
            recommendation_reason="Frühes Nordsignal",
            campaign_payload={
                "product_mapping": {
                    "recommended_product": "GeloProsed",
                    "mapping_status": "approved",
                    "condition_key": "erkaltung_akut",
                    "condition_label": "Akute Erkältung",
                },
                "peix_context": {"score": 67.0, "impact_probability": 71.0},
                "trigger_evidence": {"source": "BfArM_API", "confidence": 0.81},
                "budget_plan": {"budget_shift_pct": 18.0},
            },
            created_at=now,
            updated_at=now,
        )

        result = MarketingOpportunityEngine._model_to_dict(engine, row)

        self.assertEqual(result["legacy_status"], "NEW")
        self.assertEqual(
            result["decision_brief"]["recommendation"]["primary_product"],
            "GeloProsed",
        )
        self.assertEqual(result["region_codes"], ["SH"])

    def test_build_channel_mix_normalizes_to_hundred_and_boosts_priority_channels(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        mix = MarketingOpportunityEngine._build_channel_mix(
            engine,
            ["programmatic", "social", "search"],
            "RESOURCE_SCARCITY",
            80.0,
        )

        self.assertAlmostEqual(sum(mix.values()), 100.0, places=1)
        self.assertGreater(mix["search"], mix["social"])
        self.assertGreater(mix["programmatic"], mix["social"])

    def test_build_measurement_plan_prefers_top_channel_kpi(self) -> None:
        engine = MarketingOpportunityEngine.__new__(MarketingOpportunityEngine)

        plan = MarketingOpportunityEngine._build_measurement_plan(
            engine,
            "Awareness Push",
            [{"kpi_primary": "Completed Views"}],
        )

        self.assertEqual(plan["primary_kpi"], "Completed Views")

    def test_derive_activation_window_from_days_clamps_duration(self) -> None:
        window = MarketingOpportunityEngine._derive_activation_window_from_days(99)

        self.assertEqual(window["flight_days"], 28)


if __name__ == "__main__":
    unittest.main()
