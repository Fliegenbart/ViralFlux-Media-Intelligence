import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.forecast import router
from app.db.schema_contracts import MLForecastSchemaMismatchError
from app.db.session import get_db


class ForecastApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()

        def override_get_db():
            try:
                yield None
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(router, prefix="/api/v1/forecast")
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()

    def test_regional_predict_response_contains_decision_payload(self) -> None:
        payload = {
            "virus_typ": "Influenza A",
            "as_of_date": "2026-03-14 00:00:00",
            "horizon_days": 7,
            "supported_horizon_days": [3, 5, 7],
            "target_window_days": [7, 7],
            "decision_policy_version": "regional_decision_v1",
            "decision_summary": {
                "watch_regions": 0,
                "prepare_regions": 1,
                "activate_regions": 0,
                "avg_priority_score": 0.64,
                "top_region": "BY",
                "top_region_decision": "Prepare",
            },
            "total_regions": 1,
            "predictions": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "target_date": "2026-03-21 00:00:00",
                    "target_window_days": [7, 7],
                    "horizon_days": 7,
                    "event_probability_calibrated": 0.61,
                    "decision_label": "Prepare",
                    "priority_score": 0.64,
                    "reason_trace": {
                        "why": ["Event probability clears the Prepare threshold."],
                        "contributing_signals": [],
                        "uncertainty": [],
                        "policy_overrides": [],
                    },
                    "uncertainty_summary": "Residual uncertainty is currently limited.",
                    "decision": {
                        "stage": "prepare",
                        "signal_stage": "prepare",
                        "decision_score": 0.64,
                    },
                    "expected_target_incidence": 18.2,
                }
            ],
            "top_5": [],
            "top_decisions": [],
            "generated_at": "2026-03-14T12:00:00",
        }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService.predict_all_regions",
            return_value=payload,
        ):
            response = self.client.get(
                "/api/v1/forecast/regional/predict?virus_typ=Influenza%20A&horizon_days=7"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision_policy_version"], "regional_decision_v1")
        self.assertEqual(body["horizon_days"], 7)
        self.assertEqual(body["target_window_days"], [7, 7])
        self.assertIn("decision_summary", body)
        self.assertEqual(body["decision_summary"]["prepare_regions"], 1)
        first_prediction = body["predictions"][0]
        self.assertEqual(first_prediction["decision_label"], "Prepare")
        self.assertEqual(first_prediction["horizon_days"], 7)
        self.assertEqual(first_prediction["target_window_days"], [7, 7])
        self.assertIn("priority_score", first_prediction)
        self.assertIn("reason_trace", first_prediction)
        self.assertEqual(first_prediction["decision"]["stage"], "prepare")
        self.assertIn("expected_target_incidence", first_prediction)

    def test_media_allocation_response_contains_budget_fields(self) -> None:
        payload = {
            "virus_typ": "Influenza A",
            "headline": "Influenza A: Budget auf BY fokussieren",
            "summary": {
                "activate_regions": 1,
                "prepare_regions": 0,
                "watch_regions": 0,
                "total_budget_allocated": 50000.0,
                "budget_share_total": 1.0,
                "weekly_budget": 50000.0,
                "allocation_policy_version": "regional_media_allocation_v1",
                "spend_enabled": True,
                "spend_blockers": [],
            },
            "truth_layer": {
                "enabled": True,
                "lookback_weeks": 26,
                "scopes_evaluated": 1,
                "evidence_status_counts": {"commercially_validated": 1},
                "spend_gate_status_counts": {"released": 1},
                "budget_release_recommendation_counts": {"release": 1},
            },
            "recommendations": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "action": "activate",
                    "recommended_activation_level": "Activate",
                    "priority_rank": 1,
                    "suggested_budget_share": 1.0,
                    "suggested_budget_eur": 50000.0,
                    "suggested_budget_amount": 50000.0,
                    "confidence": 0.79,
                    "reason_trace": {
                        "why": ["Activate from the decision engine sets the base activation level."],
                        "budget_drivers": ["Activate regions receive the strongest label multiplier."],
                        "uncertainty": [],
                        "blockers": [],
                    },
                    "allocation_reason_trace": {
                        "why": ["Activate from the decision engine sets the base activation level."],
                        "budget_drivers": ["Activate regions receive the strongest label multiplier."],
                        "uncertainty": [],
                        "blockers": [],
                    },
                    "outcome_readiness": {"status": "ready", "coverage_weeks": 30},
                    "evidence_status": "commercially_validated",
                    "signal_outcome_agreement": {
                        "status": "strong",
                        "signal_present": True,
                        "historical_response_observed": True,
                    },
                    "spend_gate_status": "released",
                    "budget_release_recommendation": "release",
                }
            ],
            "generated_at": "2026-03-14T12:00:00",
        }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService.generate_media_allocation",
            return_value=payload,
        ):
            response = self.client.get(
                "/api/v1/forecast/regional/media-allocation?virus_typ=Influenza%20A&weekly_budget_eur=50000&horizon_days=7"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"]["allocation_policy_version"], "regional_media_allocation_v1")
        first = body["recommendations"][0]
        self.assertEqual(first["recommended_activation_level"], "Activate")
        self.assertEqual(first["suggested_budget_share"], 1.0)
        self.assertEqual(first["suggested_budget_amount"], first["suggested_budget_eur"])
        self.assertIn("confidence", first)
        self.assertIn("reason_trace", first)
        self.assertEqual(first["allocation_reason_trace"], first["reason_trace"])
        self.assertEqual(first["evidence_status"], "commercially_validated")
        self.assertEqual(first["spend_gate_status"], "released")
        self.assertEqual(first["budget_release_recommendation"], "release")
        self.assertTrue(first["signal_outcome_agreement"]["historical_response_observed"])
        self.assertEqual(body["truth_layer"]["evidence_status_counts"]["commercially_validated"], 1)

    def test_media_activation_alias_endpoint_returns_allocation_alias_fields(self) -> None:
        payload = {
            "virus_typ": "Influenza A",
            "headline": "Influenza A: aktuell Beobachtung priorisieren",
            "summary": {
                "activate_regions": 0,
                "prepare_regions": 0,
                "watch_regions": 1,
                "total_budget_allocated": 0.0,
                "budget_share_total": 0.0,
                "weekly_budget": 50000.0,
                "allocation_policy_version": "regional_media_allocation_v1",
                "spend_enabled": False,
                "spend_blockers": [],
            },
            "recommendations": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "action": "watch",
                    "recommended_activation_level": "Watch",
                    "priority_rank": 1,
                    "suggested_budget_share": 0.0,
                    "suggested_budget_eur": 0.0,
                    "suggested_budget_amount": 0.0,
                    "confidence": 0.42,
                    "reason_trace": {
                        "why": ["Watch from the decision engine sets the base activation level."],
                        "budget_drivers": ["Watch regions are observation-first and usually receive no spend."],
                        "uncertainty": [],
                        "blockers": [],
                    },
                    "allocation_reason_trace": {
                        "why": ["Watch from the decision engine sets the base activation level."],
                        "budget_drivers": ["Watch regions are observation-first and usually receive no spend."],
                        "uncertainty": [],
                        "blockers": [],
                    },
                }
            ],
            "generated_at": "2026-03-14T12:00:00",
        }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService.generate_media_allocation",
            return_value=payload,
        ):
            response = self.client.get(
                "/api/v1/forecast/regional/media-activation?virus_typ=Influenza%20A&weekly_budget_eur=50000&horizon_days=7"
            )

        self.assertEqual(response.status_code, 200)
        first = response.json()["recommendations"][0]
        self.assertEqual(first["recommended_activation_level"], "Watch")
        self.assertEqual(first["suggested_budget_amount"], 0.0)
        self.assertEqual(first["allocation_reason_trace"], first["reason_trace"])

    def test_media_allocation_no_data_response_stays_stable(self) -> None:
        payload = {
            "virus_typ": "Influenza A",
            "status": "no_data",
            "message": "Keine regionalen Forecast-/Decision-Daten verfügbar.",
            "headline": "Influenza A: keine regionalen Allocation-Empfehlungen verfügbar",
            "summary": {
                "activate_regions": 0,
                "prepare_regions": 0,
                "watch_regions": 0,
                "total_budget_allocated": 0.0,
                "budget_share_total": 0.0,
                "weekly_budget": 50000.0,
                "allocation_policy_version": "regional_media_allocation_v1",
                "spend_enabled": False,
                "spend_blockers": [],
                "quality_gate": {"overall_passed": False},
                "business_gate": {"validated_for_budget_activation": False},
                "evidence_tier": None,
                "rollout_mode": "gated",
                "activation_policy": "quality_gate",
            },
            "allocation_config": {"version": "regional_media_allocation_v1"},
            "horizon_days": 7,
            "supported_horizon_days": [3, 5, 7],
            "target_window_days": [7, 7],
            "truth_layer": {
                "enabled": True,
                "lookback_weeks": 26,
                "scopes_evaluated": 0,
                "evidence_status_counts": {},
                "spend_gate_status_counts": {},
                "budget_release_recommendation_counts": {},
            },
            "generated_at": "2026-03-14T12:00:00",
            "recommendations": [],
        }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService.generate_media_allocation",
            return_value=payload,
        ):
            response = self.client.get(
                "/api/v1/forecast/regional/media-allocation?virus_typ=Influenza%20A&weekly_budget_eur=50000&horizon_days=7"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "no_data")
        self.assertEqual(body["recommendations"], [])
        self.assertEqual(body["horizon_days"], 7)
        self.assertEqual(body["target_window_days"], [7, 7])
        self.assertEqual(body["summary"]["allocation_policy_version"], "regional_media_allocation_v1")
        self.assertEqual(body["truth_layer"]["scopes_evaluated"], 0)
        self.assertIn("allocation_config", body)

    def test_campaign_recommendation_endpoint_returns_clustered_output(self) -> None:
        payload = {
            "virus_typ": "Influenza A",
            "headline": "Influenza A: BY jetzt mit Respiratory Core Demand diskutieren",
            "summary": {
                "total_recommendations": 1,
                "ready_recommendations": 1,
                "guarded_recommendations": 0,
                "observe_only_recommendations": 0,
                "top_region": "BY",
                "top_product_cluster": "Respiratory Core Demand",
                "campaign_recommendation_policy_version": "campaign_recommendation_v1",
            },
            "config": {"version": "campaign_recommendation_v1"},
            "allocation_summary": {"total_budget_allocated": 12000.0},
            "truth_layer": {"enabled": False, "scopes_evaluated": 1},
            "horizon_days": 7,
            "target_window_days": [7, 7],
            "generated_at": "2026-03-17T12:00:00",
            "recommendations": [
                {
                    "region": "BY",
                    "region_name": "Bayern",
                    "activation_level": "Activate",
                    "priority_rank": 1,
                    "suggested_budget_share": 0.24,
                    "suggested_budget_amount": 12000.0,
                    "confidence": 0.78,
                    "evidence_class": "truth_backed",
                    "recommended_product_cluster": {
                        "cluster_key": "gelo_core_respiratory",
                        "label": "Respiratory Core Demand",
                        "fit_score": 0.91,
                        "products": ["GeloMyrtol forte"],
                    },
                    "recommended_keyword_cluster": {
                        "cluster_key": "respiratory_relief_search",
                        "label": "Respiratory Relief Search",
                        "fit_score": 0.89,
                        "keywords": ["husten schleim loesen"],
                    },
                    "recommendation_rationale": {
                        "why": ["Bayern stays on Activate."],
                        "product_fit": ["Respiratory cluster fits the product set."],
                        "keyword_fit": ["Keyword cluster matches symptom demand."],
                        "budget_notes": ["Suggested campaign budget is 12000 EUR."],
                        "evidence_notes": ["Evidence class is truth_backed."],
                        "guardrails": ["Spend guardrails are currently satisfied."],
                    },
                    "spend_guardrail_status": "ready",
                }
            ],
        }

        with patch(
            "app.services.ml.regional_forecast.RegionalForecastService.generate_campaign_recommendations",
            return_value=payload,
        ):
            response = self.client.get(
                "/api/v1/forecast/regional/campaign-recommendations?virus_typ=Influenza%20A&weekly_budget_eur=50000&horizon_days=7"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"]["campaign_recommendation_policy_version"], "campaign_recommendation_v1")
        first = body["recommendations"][0]
        self.assertEqual(first["region"], "BY")
        self.assertEqual(first["recommended_product_cluster"]["cluster_key"], "gelo_core_respiratory")
        self.assertEqual(first["recommended_keyword_cluster"]["cluster_key"], "respiratory_relief_search")
        self.assertEqual(first["spend_guardrail_status"], "ready")
        self.assertTrue(first["recommendation_rationale"]["guardrails"])

    def test_regional_predict_rejects_invalid_horizon(self) -> None:
        response = self.client.get(
            "/api/v1/forecast/regional/predict?virus_typ=Influenza%20A&horizon_days=4"
        )

        self.assertEqual(response.status_code, 422)

    def test_monitoring_endpoint_maps_schema_mismatch_to_503(self) -> None:
        with patch(
            "app.services.ml.forecast_decision_service.ForecastDecisionService.build_monitoring_snapshot",
            side_effect=MLForecastSchemaMismatchError("MLForecast schema mismatch detected."),
        ):
            response = self.client.get("/api/v1/forecast/monitoring/Influenza%20A")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "MLForecast schema mismatch detected.")


if __name__ == "__main__":
    unittest.main()
