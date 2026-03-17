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

    def _seed_forecast_bundle_inputs(
        self,
        *,
        drift_detected: bool = False,
        forecast_created_at: datetime | None = None,
        backtest_created_at: datetime | None = None,
        accuracy_created_at: datetime | None = None,
        quality_gate_passed: bool = True,
    ) -> None:
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

        created_at = forecast_created_at or now
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
                        "overall_passed": quality_gate_passed,
                        "forecast_readiness": "GO" if quality_gate_passed else "WATCH",
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
                created_at=backtest_created_at or now,
            )
        )
        self.db.add(
            ForecastAccuracyLog(
                computed_at=accuracy_created_at or now,
                virus_typ="Influenza A",
                window_days=14,
                samples=14,
                mae=4.2,
                rmse=5.1,
                mape=9.2,
                correlation=0.72,
                drift_detected=drift_detected,
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

    def test_build_monitoring_snapshot_returns_healthy_state_for_green_stack(self) -> None:
        self._seed_forecast_bundle_inputs()

        snapshot = ForecastDecisionService(self.db).build_monitoring_snapshot(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        self.assertEqual(snapshot["monitoring_status"], "healthy")
        self.assertEqual(snapshot["forecast_readiness"], "GO")
        self.assertEqual(snapshot["accuracy_freshness_status"], "fresh")
        self.assertEqual(snapshot["backtest_freshness_status"], "fresh")
        self.assertEqual(snapshot["alerts"], [])

    def test_build_monitoring_snapshot_warns_on_drift(self) -> None:
        self._seed_forecast_bundle_inputs(drift_detected=True)

        snapshot = ForecastDecisionService(self.db).build_monitoring_snapshot(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        self.assertEqual(snapshot["monitoring_status"], "warning")
        self.assertEqual(snapshot["drift_status"], "warning")
        self.assertTrue(any("Drift" in alert for alert in snapshot["alerts"]))

    def test_latest_forecasts_are_scoped_to_national_default_horizon(self) -> None:
        now = datetime.utcnow().replace(microsecond=0)
        self.db.add_all([
            MLForecast(
                forecast_date=now + timedelta(days=1),
                virus_typ="Influenza A",
                region="DE",
                horizon_days=7,
                predicted_value=100.0,
                created_at=now,
            ),
            MLForecast(
                forecast_date=now + timedelta(days=2),
                virus_typ="Influenza A",
                region="DE",
                horizon_days=7,
                predicted_value=110.0,
                created_at=now,
            ),
            MLForecast(
                forecast_date=now + timedelta(days=1),
                virus_typ="Influenza A",
                region="BY",
                horizon_days=7,
                predicted_value=999.0,
                created_at=now + timedelta(minutes=2),
            ),
            MLForecast(
                forecast_date=now + timedelta(days=1),
                virus_typ="Influenza A",
                region="DE",
                horizon_days=5,
                predicted_value=777.0,
                created_at=now + timedelta(minutes=3),
            ),
        ])
        self.db.commit()

        forecasts = ForecastDecisionService(self.db)._latest_forecasts("Influenza A")

        self.assertEqual(len(forecasts), 2)
        self.assertTrue(all(item.region == "DE" for item in forecasts))
        self.assertTrue(all(item.horizon_days == 7 for item in forecasts))
        self.assertEqual([item.predicted_value for item in forecasts], [100.0, 110.0])

    def test_build_monitoring_snapshot_sanitizes_non_finite_metrics(self) -> None:
        self._seed_forecast_bundle_inputs()
        latest_accuracy = (
            self.db.query(ForecastAccuracyLog)
            .filter(ForecastAccuracyLog.virus_typ == "Influenza A")
            .one()
        )
        latest_accuracy.correlation = float("nan")
        self.db.commit()

        snapshot = ForecastDecisionService(self.db).build_monitoring_snapshot(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        self.assertIsNone(snapshot["latest_accuracy"]["correlation"])

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

    def test_confidence_pct_requires_explicit_signal_confidence(self) -> None:
        self.assertIsNone(MarketingOpportunityEngine._confidence_pct(None, 92.0))
        self.assertEqual(MarketingOpportunityEngine._confidence_pct(0.81, None), 81.0)


if __name__ == "__main__":
    unittest.main()
