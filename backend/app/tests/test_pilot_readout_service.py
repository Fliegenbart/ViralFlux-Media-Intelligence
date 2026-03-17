from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
                    "reason_trace": {"why": ["Berlin leads the current viral wave."]},
                    "decision": {"explanation_summary": "Berlin leads the current viral wave."},
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
                    "reason_trace": {"why": ["Berlin receives the largest share."]},
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
                    "recommendation_rationale": {"why": ["Bronchial support is the best product fit for Berlin."]},
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
            "required_fields_present": ["Media Spend"],
            "conversion_fields_present": ["Sales"],
            "truth_freshness_state": "fresh",
            "latest_batch_id": "batch-1",
        }
        service.media_service.truth_gate_service.evaluate = lambda _: {
            "passed": True,
            "learning_state": "im_aufbau",
        }
        service.snapshot_store.latest_scope_snapshot = lambda **_: {"run_id": "snapshot-1", "forecast_status": "ok"}
        service.snapshot_store.recent_scope_snapshots = lambda **_: [{"run_id": "snapshot-1"}]
        return service

    def test_build_readout_returns_watch_when_commercial_data_is_missing(self) -> None:
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

        self.assertEqual(payload["run_context"]["scope_readiness"], "WATCH")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["epidemiology_status"], "GO")
        self.assertEqual(payload["run_context"]["gate_snapshot"]["budget_release_status"], "WATCH")
        self.assertIn("Validated incremental lift metrics are still missing.", payload["run_context"]["gate_snapshot"]["missing_requirements"])
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
        self.assertEqual(payload["pilot_evidence"]["evaluation"]["selected_experiment_name"], "rsv_signal_core")
        self.assertEqual(payload["pilot_evidence"]["legacy_context"]["status"], "frozen")
        self.assertEqual(payload["pilot_evidence"]["legacy_context"]["sunset_date"], "2026-04-30")


if __name__ == "__main__":
    unittest.main()
