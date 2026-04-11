from __future__ import annotations

import json
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.services.media.pilot_readout_service import PilotReadoutService


def _scan_for_key(payload, forbidden_key: str) -> bool:
    if isinstance(payload, dict):
        if forbidden_key in payload:
            return True
        return any(_scan_for_key(value, forbidden_key) for value in payload.values())
    if isinstance(payload, list):
        return any(_scan_for_key(item, forbidden_key) for item in payload)
    return False


class PilotReadoutServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _service(self) -> PilotReadoutService:
        service = PilotReadoutService(
            self.db,
            live_evaluation_root=Path(self.tempdir.name),
        )
        service.regional_service.predict_all_regions = lambda **_: {
            "status": "trained",
            "quality_gate": {"overall_passed": True, "forecast_readiness": "GO", "failed_checks": []},
            "predictions": [
                {
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "decision_label": "Activate",
                    "decision_rank": 1,
                    "priority_score": 0.88,
                    "event_probability_calibrated": 0.81,
                    "reason_trace": {
                        "why": ["Berlin leads the current viral wave."],
                        "why_details": [
                            {
                                "code": "event_probability_activate_threshold",
                                "message": "Event probability 0.81 clears the Activate threshold 0.70.",
                                "params": {"event_probability": 0.81, "threshold": 0.70},
                            }
                        ],
                    },
                    "decision": {
                        "explanation_summary": "Berlin leads the current viral wave.",
                        "explanation_summary_detail": {
                            "code": "decision_summary",
                            "message": "Berlin: Activate because event probability is 0.81, forecast confidence is 0.72, trend acceleration is 0.30, and cross-source direction is up.",
                            "params": {
                                "bundesland_name": "Berlin",
                                "stage": "activate",
                                "event_probability": 0.81,
                                "forecast_confidence": 0.72,
                                "agreement_direction": "up",
                            },
                        },
                        "uncertainty_summary_detail": {
                            "code": "uncertainty_summary",
                            "message": "Remaining uncertainty: revision risk 0.33.",
                            "params": {
                                "parts": ["revision_risk"],
                                "revision_risk": 0.33,
                            },
                        },
                    },
                    "uncertainty_summary": "Revision risk remains visible.",
                    "target_week_start": "2026-03-23",
                },
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "decision_label": "Watch",
                    "decision_rank": 2,
                    "priority_score": 0.41,
                    "event_probability_calibrated": 0.36,
                    "reason_trace": {"why": ["Bayern stays below the threshold."]},
                    "decision": {"explanation_summary": "Bayern stays below the threshold."},
                    "uncertainty_summary": "Demand remains soft.",
                    "target_week_start": "2026-03-23",
                },
            ],
            "generated_at": "2026-03-17T10:00:00Z",
            "as_of_date": "2026-03-17",
            "model_version": "regional_v2",
            "calibration_version": "raw_passthrough:h7:2026-03-17",
            "rollout_mode": "pilot",
            "activation_policy": "gated",
            "artifact_transition_mode": None,
        }
        service.regional_service.generate_media_allocation = lambda **_: {
            "status": "ready",
            "headline": "RSV A allocation",
            "summary": {
                "activate_regions": 1,
                "prepare_regions": 0,
                "watch_regions": 1,
                "total_budget_allocated": 120000,
                "spend_enabled": False,
                "spend_blockers": ["Business gate not yet validated."],
            },
            "recommendations": [
                {
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "recommended_activation_level": "Activate",
                    "priority_rank": 1,
                    "allocation_score": 0.79,
                    "confidence": 0.71,
                    "suggested_budget_share": 0.58,
                    "suggested_budget_amount": 64000,
                    "products": ["GeloBronchial"],
                    "reason_trace": {
                        "why": ["Berlin receives the largest share."],
                        "budget_driver_details": [
                            {
                                "code": "budget_driver_suggested_share",
                                "message": "Suggested budget share is 58.00%.",
                                "params": {"suggested_budget_share": 0.58},
                            }
                        ],
                    },
                    "uncertainty_summary": "Revision risk remains visible.",
                    "business_gate": {"evidence_tier": "truth_backed"},
                },
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "recommended_activation_level": "Watch",
                    "priority_rank": 2,
                    "allocation_score": 0.33,
                    "confidence": 0.44,
                    "suggested_budget_share": 0.12,
                    "suggested_budget_amount": 12000,
                    "products": ["GeloMyrtol forte"],
                    "reason_trace": {"why": ["Bayern stays in watch mode."]},
                    "business_gate": {"evidence_tier": "truth_backed"},
                },
            ],
        }
        service.regional_service.campaign_recommendation_service.recommend_from_allocation = lambda **_: {
            "summary": {
                "ready_recommendations": 0,
                "guarded_recommendations": 1,
                "observe_only_recommendations": 1,
            },
            "recommendations": [
                {
                    "region": "BE",
                    "region_name": "Berlin",
                    "activation_level": "Activate",
                    "priority_rank": 1,
                    "confidence": 0.71,
                    "recommended_product_cluster": {"label": "Bronchial Recovery Support"},
                    "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                    "recommendation_rationale": {
                        "why": ["Bronchial support is the best product fit for Berlin."],
                        "why_details": [
                            {
                                "code": "campaign_stage_budget_share",
                                "message": "Berlin stays on Activate with budget share 58.00%.",
                                "params": {
                                    "region_name": "Berlin",
                                    "stage": "activate",
                                    "budget_share": 0.58,
                                },
                            }
                        ],
                    },
                },
                {
                    "region": "BY",
                    "region_name": "Bayern",
                    "activation_level": "Watch",
                    "priority_rank": 2,
                    "confidence": 0.44,
                    "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                    "recommended_keyword_cluster": {"label": "Voice Recovery Search"},
                    "recommendation_rationale": {"why": ["Keep Bayern in observe-only mode."]},
                },
            ],
        }
        service.media_service.get_truth_coverage = lambda **_: {
            "coverage_weeks": 12,
            "required_fields_present": ["Mediabudget"],
            "conversion_fields_present": ["Verkäufe"],
            "truth_freshness_state": "fresh",
            "latest_batch_id": "batch-1",
        }
        service.media_service.truth_gate_service.evaluate = lambda _: {
            "passed": True,
            "learning_state": "im_aufbau",
        }
        service.snapshot_store.latest_scope_snapshot = lambda **_: {
            "run_id": "snapshot-1",
            "forecast_status": "ok",
            "forecast_recency_status": "ok",
            "source_coverage_required_status": "ok",
            "source_freshness_status": "ok",
            "live_source_coverage_status": "ok",
            "live_source_freshness_status": "ok",
            "source_coverage": {"grippeweb_are_available": 0.95},
        }
        service.snapshot_store.recent_scope_snapshots = lambda **_: [
            {
                "run_id": "snapshot-1",
                "forecast_recency_status": "ok",
                "source_coverage_required_status": "ok",
                "source_freshness_status": "ok",
                "live_source_coverage_status": "ok",
                "live_source_freshness_status": "ok",
                "source_coverage": {"grippeweb_are_available": 0.95},
            }
        ]
        return service

    def test_build_readout_returns_watch_when_commercial_data_is_missing(self) -> None:
        archive_dir = Path(self.tempdir.name) / "rsv_a_h7_rsv_ranking" / "20260317T193728Z_forecast_first"
        archive_dir.mkdir(parents=True)
        (archive_dir / "report.json").write_text(json.dumps({
            "run_id": "live-eval-forecast-first",
            "generated_at": "2026-03-17T19:37:28Z",
            "selected_experiment_name": "rsv_signal_core",
            "calibration_mode": "raw_passthrough",
            "gate_outcome": "GO",
            "retained": True,
            "comparison_table": [
                {"role": "baseline", "name": "baseline"},
                {"role": "experiment", "name": "rsv_signal_core"},
            ],
        }))

        service = self._service()
        service.business_validation_service.evaluate = lambda **_: {
            "coverage_weeks": 12,
            "holdout_ready": False,
            "validated_for_budget_activation": False,
            "validation_status": "pending_holdout_validation",
            "activation_cycles": 1,
            "lift_metrics_available": False,
        }

        payload = service.build_readout(brand="gelo", virus_typ="RSV A", horizon_days=7)

        self.assertEqual(payload["run_context"]["scope_readiness"], "GO")
        self.assertEqual(payload["run_context"]["forecast_readiness"], "GO")
        self.assertEqual(payload["run_context"]["commercial_validation_status"], "WATCH")
        self.assertEqual(payload["run_context"]["budget_mode"], "scenario_split")
        self.assertEqual(payload["run_context"]["pilot_mode"], "forecast_first")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["epidemiology_status"], "GO")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["budget_release_status"], "WATCH")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["commercial_validation_status"], "WATCH")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["operational_readiness"]["live_source_coverage_readiness"], "GO")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["operational_readiness"]["live_source_freshness_readiness"], "GO")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["operational_readiness"]["source_coverage_scope"], "artifact")
        self.assertEqual(payload["executive_summary"]["budget_mode"], "scenario_split")
        self.assertEqual(payload["executive_summary"]["budget_recommendation"]["budget_mode"], "scenario_split")
        self.assertEqual(payload["empty_state"]["code"], "ready")
        self.assertTrue(payload["executive_summary"]["reason_trace_details"])
        self.assertEqual(payload["executive_summary"]["reason_trace_details"][0]["code"], "event_probability_activate_threshold")
        self.assertEqual(payload["executive_summary"]["uncertainty_summary_detail"]["code"], "uncertainty_summary")
        self.assertTrue(payload["operational_recommendations"]["regions"][0]["reason_trace_details"])
        self.assertIn(
            "forecast-basierten Szenario-Split",
            payload["executive_summary"]["what_should_we_do_now"],
        )
        self.assertIn("Validierte inkrementelle Lift-Metriken fehlen noch.", payload["run_context"]["gate_snapshot"]["missing_requirements"])
        self.assertNotIn("GELO", payload["run_context"]["validation_disclaimer"])
        self.assertNotIn("GELO", payload["empty_state"]["body"])
        self.assertTrue(
            all("GELO" not in item for item in payload["run_context"]["gate_snapshot"]["missing_requirements"])
        )
        self.assertFalse(_scan_for_key(payload, "impact_probability"))

    def test_build_readout_returns_go_when_scope_and_business_gate_both_pass(self) -> None:
        archive_dir = Path(self.tempdir.name) / "rsv_a_h7_rsv_ranking" / "20260317T193728Z_test"
        archive_dir.mkdir(parents=True)
        (archive_dir / "report.json").write_text(json.dumps({
            "run_id": "live-eval-1",
            "generated_at": "2026-03-17T19:37:28Z",
            "selected_experiment_name": "rsv_signal_core",
            "calibration_mode": "raw_passthrough",
            "gate_outcome": "GO",
            "retained": True,
            "comparison_table": [
                {"role": "baseline", "name": "baseline"},
                {"role": "experiment", "name": "rsv_signal_core"},
            ],
        }))

        service = self._service()
        service.business_validation_service.evaluate = lambda **_: {
            "coverage_weeks": 30,
            "holdout_ready": True,
            "validated_for_budget_activation": True,
            "validation_status": "passed_holdout_validation",
            "activation_cycles": 2,
            "lift_metrics_available": True,
        }

        payload = service.build_readout(brand="gelo", virus_typ="RSV A", horizon_days=7)

        self.assertEqual(payload["run_context"]["scope_readiness"], "GO")
        self.assertEqual(payload["run_context"]["forecast_readiness"], "GO")
        self.assertEqual(payload["run_context"]["commercial_validation_status"], "GO")
        self.assertEqual(payload["run_context"]["budget_mode"], "validated_allocation")
        self.assertEqual(payload["pilot_evidence"]["evaluation"]["selected_experiment_name"], "rsv_signal_core")
        self.assertEqual(payload["pilot_evidence"]["legacy_context"]["status"], "frozen")
        self.assertEqual(payload["pilot_evidence"]["legacy_context"]["sunset_date"], "2026-04-30")

    def test_build_readout_degrades_forecast_status_when_live_sources_are_stale(self) -> None:
        service = self._service()
        service.snapshot_store.latest_scope_snapshot = lambda **_: {
            "run_id": "snapshot-1",
            "forecast_status": "ok",
            "forecast_recency_status": "ok",
            "source_coverage_required_status": "ok",
            "source_freshness_status": "warning",
            "live_source_coverage_status": "ok",
            "live_source_freshness_status": "warning",
            "source_coverage": {"grippeweb_are_available": 0.95},
        }

        payload = service.build_readout(brand="gelo", virus_typ="RSV A", horizon_days=7)

        self.assertEqual(payload["run_context"]["forecast_readiness"], "WATCH")
        self.assertEqual(payload["run_context"]["scope_readiness"], "WATCH")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["epidemiology_status"], "WATCH")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["operational_readiness"]["live_source_freshness_readiness"], "WATCH")

    def test_build_readout_blocks_scope_when_critical_live_source_is_missing(self) -> None:
        service = self._service()
        service.snapshot_store.latest_scope_snapshot = lambda **_: {
            "run_id": "snapshot-1",
            "forecast_status": "ok",
            "forecast_recency_status": "ok",
            "source_coverage_required_status": "critical",
            "source_freshness_status": "ok",
            "live_source_coverage_status": "critical",
            "live_source_freshness_status": "ok",
            "source_coverage": {"grippeweb_are_available": 0.95},
        }

        payload = service.build_readout(brand="gelo", virus_typ="RSV A", horizon_days=7)

        self.assertEqual(payload["run_context"]["forecast_readiness"], "NO_GO")
        self.assertEqual(payload["run_context"]["scope_readiness"], "NO_GO")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["epidemiology_status"], "NO_GO")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["operational_readiness"]["live_source_coverage_readiness"], "NO_GO")

    def test_build_readout_does_not_treat_artifact_source_coverage_as_live_go(self) -> None:
        service = self._service()
        service.snapshot_store.latest_scope_snapshot = lambda **_: {
            "run_id": "snapshot-1",
            "forecast_status": "ok",
            "forecast_recency_status": "ok",
            "source_coverage": {"grippeweb_are_available": 0.95},
            "source_coverage_scope": "artifact",
        }

        payload = service.build_readout(brand="gelo", virus_typ="RSV A", horizon_days=7)

        self.assertEqual(payload["run_context"]["forecast_readiness"], "WATCH")
        self.assertEqual(payload["run_context"]["scope_readiness"], "WATCH")
        self.assertEqual(
            payload["run_context"]["gate_snapshot"]["operational_readiness"]["source_coverage_scope"],
            "artifact",
        )
        self.assertEqual(
            payload["run_context"]["gate_snapshot"]["operational_readiness"]["live_source_coverage_readiness"],
            "WATCH",
        )

    def test_gate_snapshot_delegates_to_readiness_module(self) -> None:
        service = self._service()

        with patch(
            "app.services.media.pilot_readout_readiness._gate_snapshot",
            return_value={"scope_readiness": "WATCH"},
        ) as mocked:
            result = service._gate_snapshot(
                forecast={"quality_gate": {}},
                truth_coverage={},
                business_validation={},
                evaluation=None,
                operational_snapshot=None,
                forecast_readiness="WATCH",
                commercial_validation_status="WATCH",
                overall_scope_readiness="WATCH",
                missing_requirements=[],
            )

        mocked.assert_called_once()
        self.assertEqual(result["scope_readiness"], "WATCH")

    def test_forecast_scope_readiness_delegates_to_readiness_module(self) -> None:
        service = self._service()

        with patch(
            "app.services.media.pilot_readout_readiness._forecast_scope_readiness",
            return_value="GO",
        ) as mocked:
            result = service._forecast_scope_readiness(
                {"status": "trained", "predictions": [{}], "quality_gate": {"overall_passed": True}},
                operational_snapshot=None,
            )

        mocked.assert_called_once_with(
            service,
            {"status": "trained", "predictions": [{}], "quality_gate": {"overall_passed": True}},
            operational_snapshot=None,
        )
        self.assertEqual(result, "GO")

    def test_promotion_status_still_uses_service_override_for_forecast_scope_readiness(self) -> None:
        class OverrideService(PilotReadoutService):
            def _forecast_scope_readiness(
                self,
                forecast: dict[str, object],
                *,
                operational_snapshot: dict[str, object] | None = None,
            ) -> str:
                return "GO"

        service = OverrideService(self.db, live_evaluation_root=Path(self.tempdir.name))

        result = service._promotion_status(
            evaluation=None,
            forecast={"status": "no_model"},
            operational_snapshot=None,
        )

        self.assertEqual(result, "operational_go_without_budget_release")


if __name__ == "__main__":
    unittest.main()
