from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, BacktestRun, MarketingOpportunity, SurvstatWeeklyData
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine


class OpportunityEngineRetrospectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MarketingOpportunityEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_roi_retrospective_returns_unavailable_without_opportunities(self) -> None:
        result = self.service.get_roi_retrospective()

        self.assertEqual(
            result,
            {"available": False, "reason": "Keine Opportunities vorhanden"},
        )

    def test_roi_retrospective_aggregates_stats_and_signal_quality(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        opportunities = [
            MarketingOpportunity(
                opportunity_id="opp-1",
                opportunity_type="RESOURCE_SCARCITY",
                status="APPROVED",
                urgency_score=82.0,
                created_at=now,
            ),
            MarketingOpportunity(
                opportunity_id="opp-2",
                opportunity_type="WEATHER_FORECAST",
                status="DISMISSED",
                urgency_score=74.0,
                created_at=now,
            ),
            MarketingOpportunity(
                opportunity_id="opp-3",
                opportunity_type="SEASONAL_DEFICIENCY",
                status="READY",
                urgency_score=51.0,
                created_at=now,
            ),
        ]
        self.db.add_all(opportunities)
        self.db.add(
            BacktestRun(
                run_id="market-check-1",
                mode="MARKET_CHECK",
                status="success",
                virus_typ="Influenza A",
                target_source="RKI_ARE",
                metrics={
                    "r2_score": 0.812,
                    "correlation": 0.744,
                    "mae": 4.18,
                    "quality_gate": {"overall_passed": True, "lead_passed": True},
                    "timing_metrics": {"best_lag_days": 14},
                },
                improvement_vs_baselines={
                    "mae_vs_persistence_pct": 11.2,
                    "mae_vs_seasonal_pct": 6.8,
                },
                created_at=now,
            )
        )
        self.db.add_all(
            [
                SurvstatWeeklyData(
                    week_label="2026_13",
                    week_start=now - timedelta(days=7),
                    year=2026,
                    week=13,
                    bundesland="Bundesweit",
                    disease="ARE",
                    disease_cluster="RESPIRATORY",
                    incidence=100.0,
                ),
                SurvstatWeeklyData(
                    week_label="2026_14",
                    week_start=now + timedelta(days=7),
                    year=2026,
                    week=14,
                    bundesland="Bundesweit",
                    disease="ARE",
                    disease_cluster="RESPIRATORY",
                    incidence=118.0,
                ),
                SurvstatWeeklyData(
                    week_label="2026_15",
                    week_start=now + timedelta(days=14),
                    year=2026,
                    week=15,
                    bundesland="Bundesweit",
                    disease="ARE",
                    disease_cluster="RESPIRATORY",
                    incidence=130.0,
                ),
            ]
        )
        self.db.commit()

        result = self.service.get_roi_retrospective()

        self.assertTrue(result["available"])
        self.assertEqual(result["summary"]["total_opportunities"], 3)
        self.assertEqual(result["summary"]["acted_on"], 1)
        self.assertEqual(result["summary"]["missed"], 1)
        self.assertEqual(result["summary"]["pending"], 1)
        self.assertEqual(result["summary"]["conversion_rate"], 0.0)
        self.assertEqual(result["signal_quality"]["samples_analyzed"], 3)
        self.assertEqual(result["signal_quality"]["avg_demand_increase_pct"], 30.0)
        self.assertEqual(result["signal_quality"]["signal_hit_rate_pct"], 100.0)
        self.assertEqual(result["model_accuracy"]["readiness_status"], "GO")
        self.assertEqual(result["model_accuracy"]["best_lag_days"], 14)
        self.assertEqual(result["missed_opportunity_value"]["high_urgency_missed"], 1)

    def test_brand_filtered_opportunity_queries_require_exact_brand_match(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.db.add_all(
            [
                MarketingOpportunity(
                    opportunity_id="opp-gelo",
                    opportunity_type="RESOURCE_SCARCITY",
                    status="READY",
                    brand="gelo",
                    urgency_score=82.0,
                    created_at=now,
                ),
                MarketingOpportunity(
                    opportunity_id="opp-gelo-health",
                    opportunity_type="RESOURCE_SCARCITY",
                    status="READY",
                    brand="gelo-health",
                    urgency_score=79.0,
                    created_at=now,
                ),
            ]
        )
        self.db.commit()

        rows = self.service.get_opportunities(brand_filter="gelo")
        count = self.service.count_opportunities(brand_filter="gelo")

        self.assertEqual(count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "opp-gelo")


if __name__ == "__main__":
    unittest.main()
