from app.core.time import utc_now
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
from app.services.ml.forecast_contracts import (
    BACKTEST_RELIABILITY_PROXY_SOURCE,
    HEURISTIC_EVENT_SCORE_SOURCE,
)
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_service import ForecastService


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
        now = utc_now().replace(microsecond=0)
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
        event = bundle["event_forecast"]
        self.assertIsNone(event["event_probability"])
        self.assertIsNotNone(event["heuristic_event_score"])
        self.assertEqual(event["signal_source"], HEURISTIC_EVENT_SCORE_SOURCE)
        self.assertIsNone(event["probability_source"])
        self.assertIsNone(event["calibration_passed"])
        self.assertNotIn("confidence", event)
        self.assertNotIn("confidence_label", event)
        self.assertNotIn("event_signal_score", event)
        self.assertNotIn("confidence_semantics", event)
        self.assertIsNotNone(event["reliability_score"])
        self.assertIsNotNone(event["reliability_label"])
        self.assertGreater(bundle["decision_summary"]["decision_priority_index"], 0.0)
        self.assertEqual(bundle["decision_summary"]["decision_basis_type"], "heuristic_signal")
        self.assertEqual(
            bundle["decision_summary"]["decision_basis_score"],
            event["heuristic_event_score"],
        )
        self.assertNotIn("compatibility", bundle)
        self.assertEqual(len(bundle["burden_forecast"]["points"]), 14)

    def test_build_forecast_bundle_prefers_stored_learned_event_probability(self) -> None:
        self._seed_forecast_bundle_inputs()
        stored_forecast = (
            self.db.query(MLForecast)
            .filter(MLForecast.virus_typ == "Influenza A")
            .order_by(MLForecast.forecast_date.asc())
            .offset(6)
            .limit(1)
            .one()
        )
        stored_forecast.features_used = {
            "event_forecast": {
                "event_probability": 0.64,
                "heuristic_event_score": 0.58,
                "probability_source": "learned_exceedance_logistic_regression",
                "learned_model_version": "xgb_stack_v1",
                "fallback_used": False,
            }
        }
        self.db.commit()

        bundle = ForecastDecisionService(self.db).build_forecast_bundle(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        event = bundle["event_forecast"]
        self.assertEqual(event["event_probability"], 0.64)
        self.assertEqual(event["heuristic_event_score"], 0.58)
        self.assertEqual(event["signal_source"], "learned_exceedance_logistic_regression")
        self.assertEqual(
            event["probability_source"],
            "learned_exceedance_logistic_regression",
        )
        self.assertTrue(event["calibration_passed"])
        self.assertNotIn("confidence", event)
        self.assertNotIn("event_signal_score", event)
        self.assertEqual(bundle["decision_summary"]["decision_basis_type"], "learned_probability")
        self.assertEqual(bundle["decision_summary"]["decision_basis_score"], 0.64)

    def test_save_load_bundle_round_trip_preserves_event_semantics_fields(self) -> None:
        now = utc_now().replace(microsecond=0)
        self._seed_forecast_bundle_inputs(
            forecast_created_at=now - timedelta(days=2),
            backtest_created_at=now,
            accuracy_created_at=now,
        )
        forecast_service = ForecastService(self.db)
        forecast_dates = [now + timedelta(days=offset + 1) for offset in range(7)]

        forecast_service.save_forecast(
            {
                "virus_typ": "Influenza A",
                "region": "DE",
                "horizon_days": 7,
                "model_version": "xgb_stack_direct_h7_inline",
                "confidence": 0.18,
                "feature_names": ["hw_pred", "ridge_pred"],
                "feature_importance": {"hw_pred": 0.6, "ridge_pred": 0.4},
                "training_window": {"samples": 120},
                "backtest_metrics": {"mape": 12.0},
                "forecast": [
                    {
                        "ds": forecast_date,
                        "yhat": 130.0 + offset,
                        "yhat_lower": 120.0 + offset,
                        "yhat_upper": 145.0 + offset,
                    }
                    for offset, forecast_date in enumerate(forecast_dates)
                ],
                "contracts": {
                    "event_forecast": {
                        "event_probability": 0.67,
                        "confidence": 0.18,
                        "reliability_score": 0.77,
                        "backtest_quality_score": 0.83,
                        "probability_source": "learned_exceedance_logistic_regression",
                        "calibration_mode": "platt",
                        "uncertainty_source": "backtest_interval_coverage",
                        "fallback_reason": None,
                        "learned_model_version": "xgb_stack_direct_h7_inline",
                        "fallback_used": False,
                    },
                    "forecast_quality": {
                        "forecast_readiness": "GO",
                        "drift_status": "ok",
                        "freshness_status": "fresh",
                    },
                },
            }
        )

        stored_rows = (
            self.db.query(MLForecast)
            .filter(MLForecast.model_version == "xgb_stack_direct_h7_inline")
            .order_by(MLForecast.forecast_date.asc())
            .all()
        )
        self.assertTrue(stored_rows)
        self.assertEqual(stored_rows[0].confidence, 0.77)
        stored_event = (stored_rows[0].features_used or {}).get("event_forecast") or {}
        self.assertEqual(stored_event.get("reliability_score"), 0.77)
        self.assertEqual(stored_event.get("uncertainty_source"), BACKTEST_RELIABILITY_PROXY_SOURCE)

        bundle = ForecastDecisionService(self.db).build_forecast_bundle(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        event = bundle["event_forecast"]
        self.assertEqual(event["event_probability"], 0.67)
        self.assertEqual(event["reliability_score"], 0.77)
        self.assertEqual(event["reliability_label"], "Hoch")
        self.assertEqual(event["backtest_quality_score"], 0.83)
        self.assertEqual(event["probability_source"], "learned_exceedance_logistic_regression")
        self.assertEqual(event["signal_source"], "learned_exceedance_logistic_regression")
        self.assertEqual(event["calibration_mode"], "platt")
        self.assertEqual(event["uncertainty_source"], BACKTEST_RELIABILITY_PROXY_SOURCE)
        self.assertIsNone(event["fallback_reason"])
        self.assertNotIn("confidence", event)
        self.assertNotIn("event_signal_score", event)
        self.assertNotIn("confidence_semantics", event)

    def test_build_monitoring_snapshot_carries_semantics_fields(self) -> None:
        self._seed_forecast_bundle_inputs()
        stored_forecast = (
            self.db.query(MLForecast)
            .filter(MLForecast.virus_typ == "Influenza A")
            .order_by(MLForecast.forecast_date.asc())
            .offset(6)
            .limit(1)
            .one()
        )
        stored_forecast.features_used = {
            "event_forecast": {
                "event_probability": 0.64,
                "confidence": 0.22,
                "reliability_score": 0.71,
                "backtest_quality_score": 0.79,
                "probability_source": "learned_exceedance_logistic_regression",
                "calibration_mode": "isotonic",
                "uncertainty_source": "backtest_interval_coverage",
                "fallback_used": False,
            }
        }
        self.db.commit()

        snapshot = ForecastDecisionService(self.db).build_monitoring_snapshot(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        event = snapshot["event_forecast"]
        self.assertEqual(event["event_probability"], 0.64)
        self.assertEqual(event["reliability_score"], 0.71)
        self.assertEqual(event["reliability_label"], "Hoch")
        self.assertEqual(event["backtest_quality_score"], 0.79)
        self.assertEqual(event["uncertainty_source"], BACKTEST_RELIABILITY_PROXY_SOURCE)
        self.assertNotIn("confidence", event)
        self.assertNotIn("event_signal_score", event)

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

    def test_build_legacy_outbreak_score_exposes_honest_signal_fields(self) -> None:
        self._seed_forecast_bundle_inputs()

        result = ForecastDecisionService(self.db).build_legacy_outbreak_score(
            virus_typ="Influenza A",
            target_source="RKI_ARE",
        )

        self.assertIn("decision_priority_index", result)
        self.assertIn("reliability_label", result)
        self.assertNotIn("confidence_level", result)
        self.assertNotIn("final_risk_score", result)
        self.assertGreater(result["decision_priority_index"], 0.0)
        self.assertIn("decision_basis_type", result)
        self.assertIn("decision_basis_score", result)
        self.assertNotIn("decision_signal_index", result)

    def test_get_legacy_score_history_uses_signal_fields_without_score_alias(self) -> None:
        self._seed_forecast_bundle_inputs()

        history_payload = ForecastDecisionService(self.db).get_legacy_score_history(
            virus_typ="Influenza A",
            days=30,
        )

        self.assertTrue(history_payload["history"])
        first = history_payload["history"][0]
        self.assertIn("decision_priority_index", first)
        self.assertIn("decision_basis_score", first)
        self.assertIn("decision_basis_type", first)
        self.assertIn("signal_source", first)
        self.assertNotIn("score", first)
        self.assertNotIn("decision_signal_index", first)
        self.assertNotIn("event_signal_score", first)

    def test_latest_forecasts_are_scoped_to_national_default_horizon(self) -> None:
        now = utc_now().replace(microsecond=0)
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
        now = utc_now().replace(microsecond=0)
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
        now = utc_now()
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
        self.assertIsNone(candidate["impact_probability"])
        self.assertIsNone(candidate["event_forecast"]["event_probability"])
        self.assertIsNotNone(candidate["event_forecast"]["heuristic_event_score"])

    def test_confidence_pct_requires_explicit_signal_confidence(self) -> None:
        self.assertIsNone(MarketingOpportunityEngine._confidence_pct(None, 92.0))
        self.assertEqual(MarketingOpportunityEngine._confidence_pct(0.81, None), 81.0)


if __name__ == "__main__":
    unittest.main()
