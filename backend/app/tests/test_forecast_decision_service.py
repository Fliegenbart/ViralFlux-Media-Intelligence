import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    BacktestRun,
    Base,
    BrandProduct,
    ForecastAccuracyLog,
    MLForecast,
    MediaOutcomeRecord,
    WastewaterAggregated,
)
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.ml.forecast_decision_service import ForecastDecisionService


class ForecastDecisionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _seed_forecast_bundle_inputs(self) -> None:
        now = datetime.utcnow().replace(microsecond=0)
        for offset in range(16):
            day = now - timedelta(days=offset * 7)
            self.db.add(
                WastewaterAggregated(
                    datum=day,
                    available_time=day,
                    virus_typ="Influenza A",
                    n_standorte=12,
                    anteil_bev=0.6,
                    viruslast=100.0 + offset,
                    viruslast_normalisiert=55.0 + offset,
                )
            )

        created_at = now
        for offset in range(14):
            forecast_date = now + timedelta(days=offset + 1)
            self.db.add(
                MLForecast(
                    forecast_date=forecast_date,
                    virus_typ="Influenza A",
                    predicted_value=130.0 + offset,
                    lower_bound=120.0 + offset,
                    upper_bound=145.0 + offset,
                    confidence=0.8,
                    model_version="xgb_stack_v1",
                    features_used={},
                    trend_momentum_7d=0.12,
                    outbreak_risk_score=0.82,
                    created_at=created_at,
                )
            )

        self.db.add(
            BacktestRun(
                run_id="market-1",
                mode="MARKET_CHECK",
                status="success",
                virus_typ="Influenza A",
                target_source="RKI_ARE",
                target_key="RKI_ARE",
                target_label="RKI ARE",
                strict_vintage_mode=True,
                horizon_days=7,
                min_train_points=20,
                parameters={},
                metrics={
                    "quality_gate": {
                        "overall_passed": True,
                        "forecast_readiness": "GO",
                    },
                    "timing_metrics": {"best_lag_days": 14, "corr_at_best_lag": 0.61},
                    "interval_coverage": {
                        "coverage_80_pct": 82.0,
                        "coverage_80_gap_score": 0.93,
                        "interval_passed": True,
                    },
                    "event_calibration": {
                        "brier_score": 0.12,
                        "ece": 0.05,
                        "calibration_passed": True,
                        "calibration_method": "growth_sigmoid_with_oos_gate",
                    },
                },
                baseline_metrics={},
                improvement_vs_baselines={
                    "mae_vs_persistence_pct": 12.0,
                    "mae_vs_seasonal_pct": 8.0,
                },
                optimized_weights={},
                proof_text="ok",
                llm_insight="ok",
                lead_lag={"effective_lead_days": 14},
                chart_points=14,
                created_at=now,
            )
        )
        self.db.add(
            ForecastAccuracyLog(
                computed_at=now,
                virus_typ="Influenza A",
                window_days=14,
                samples=14,
                mae=4.2,
                rmse=5.1,
                mape=9.2,
                correlation=0.72,
                drift_detected=False,
                details={},
            )
        )
        self.db.commit()

    def test_build_forecast_bundle_returns_event_and_quality_contracts(self) -> None:
        self._seed_forecast_bundle_inputs()

        bundle = ForecastDecisionService(self.db).build_forecast_bundle(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        self.assertEqual(bundle["forecast_quality"]["forecast_readiness"], "GO")
        self.assertIsNotNone(bundle["event_forecast"]["event_probability"])
        self.assertTrue(bundle["event_forecast"]["calibration_passed"])
        self.assertGreater(bundle["compatibility"]["final_risk_score"], 0.0)
        self.assertEqual(len(bundle["burden_forecast"]["points"]), 14)

    def test_truth_readiness_requires_coverage_and_conversion_fields(self) -> None:
        now = datetime.utcnow().replace(microsecond=0)
        for index in range(26):
            week = now - timedelta(days=7 * index)
            self.db.add(
                MediaOutcomeRecord(
                    week_start=week,
                    brand="gelo",
                    product="GeloProsed",
                    region_code="SH",
                    media_spend_eur=1000.0 + index,
                    sales_units=40.0 + index,
                    source_label="manual",
                )
            )
        self.db.commit()

        readiness = ForecastDecisionService(self.db).get_truth_readiness(brand="gelo")

        self.assertEqual(readiness["truth_readiness"], "im_aufbau")
        self.assertTrue(readiness["truth_ready"])
        self.assertTrue(readiness["expected_units_lift_enabled"])


class ForecastFirstOpportunityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self._seed_brand_products()
        ForecastDecisionServiceTests._seed_forecast_bundle_inputs(self)  # reuse helper logic

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _seed_brand_products(self) -> None:
        now = datetime.utcnow()
        self.db.add(
            BrandProduct(
                brand="gelo",
                product_name="GeloProsed",
                source_url="manual://seed",
                source_hash="seed-geloprosed",
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
        self.db.commit()

    def test_forecast_first_candidates_use_forecast_contracts(self) -> None:
        engine = MarketingOpportunityEngine(self.db)

        candidates = engine._forecast_first_candidates(
            opportunities=[],
            brand="gelo",
            virus_typ="Influenza A",
            region_scope=["SH"],
            max_cards=2,
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["forecast_readiness"], "GO")
        self.assertEqual(candidate["action_class"], "market_watch")
        self.assertIn("event_forecast", candidate)
        self.assertIn("opportunity_assessment", candidate)
        self.assertIsNotNone(candidate["impact_probability"])


if __name__ == "__main__":
    unittest.main()
