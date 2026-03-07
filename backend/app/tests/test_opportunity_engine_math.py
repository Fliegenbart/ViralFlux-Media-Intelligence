import unittest
import os

# Minimal env bootstrap for app settings during module import.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

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


if __name__ == "__main__":
    unittest.main()
