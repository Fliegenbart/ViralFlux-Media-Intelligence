from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, MediaOutcomeRecord
from app.services.media.truth_layer_contracts import OutcomeObservationInput
from app.services.media.truth_layer_service import TruthLayerService


class TruthLayerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = TruthLayerService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _observation(
        self,
        *,
        week_start: datetime,
        metric_name: str,
        metric_value: float,
        product: str = "GeloMyrtol forte",
        region_code: str = "BY",
        holdout_group: str | None = None,
        metadata: dict | None = None,
    ) -> OutcomeObservationInput:
        return OutcomeObservationInput(
            brand="gelo",
            product=product,
            region_code=region_code,
            metric_name=metric_name,
            metric_value=metric_value,
            window_start=week_start,
            window_end=week_start + timedelta(days=6),
            source_label="manual",
            holdout_group=holdout_group,
            metadata=metadata or {},
        )

    def test_assess_returns_missing_when_scope_has_no_truth(self) -> None:
        result = self.service.assess(
            brand="gelo",
            region_code="BY",
            product="GeloMyrtol forte",
            signal_context={"event_probability": 0.81, "decision_stage": "activate"},
        )

        self.assertEqual(result["evidence_status"], "no_truth")
        self.assertEqual(result["outcome_readiness"]["status"], "missing")
        self.assertEqual(result["signal_outcome_agreement"]["status"], "no_outcome_support")
        self.assertEqual(result["metadata"]["source_mode"], "empty")
        self.assertEqual(
            result["commercial_gate"]["message"],
            "No outcome data is connected for this scope yet.",
        )

    def test_assess_with_generic_observations_returns_truth_backed_scope(self) -> None:
        start = datetime(2026, 1, 5)
        observations: list[OutcomeObservationInput] = []
        for offset in range(16):
            week = start + timedelta(days=7 * offset)
            observations.extend(
                [
                    self._observation(week_start=week, metric_name="media_spend", metric_value=1200 + offset * 25),
                    self._observation(week_start=week, metric_name="sales", metric_value=42 + offset),
                    self._observation(week_start=week, metric_name="search_demand", metric_value=15 + offset * 0.5),
                ]
            )

        self.service.upsert_observations(observations)
        result = self.service.assess(
            brand="gelo",
            region_code="BY",
            product="GeloMyrtol forte",
            signal_context={"event_probability": 0.76, "decision_stage": "prepare", "confidence": 0.71},
        )

        self.assertEqual(result["metadata"]["source_mode"], "outcome_observations")
        self.assertEqual(result["outcome_readiness"]["status"], "partial")
        self.assertTrue(result["signal_outcome_agreement"]["historical_response_observed"])
        self.assertIn(result["signal_outcome_agreement"]["status"], {"moderate", "strong"})
        self.assertEqual(result["evidence_status"], "truth_backed")
        self.assertFalse(result["commercial_gate"]["budget_decision_allowed"])

    def test_holdout_and_lift_metrics_upgrade_scope_to_commercially_validated(self) -> None:
        start = datetime(2025, 7, 7)
        observations: list[OutcomeObservationInput] = []
        for offset in range(30):
            week = start + timedelta(days=7 * offset)
            group = "test" if offset % 2 == 0 else "control"
            metadata = {"holdout_lift_pct": 8.5} if offset >= 20 else {}
            observations.extend(
                [
                    self._observation(
                        week_start=week,
                        metric_name="media_spend",
                        metric_value=1800 + offset * 30,
                        region_code="NW",
                        holdout_group=group,
                        metadata=metadata,
                    ),
                    self._observation(
                        week_start=week,
                        metric_name="revenue",
                        metric_value=5500 + offset * 90,
                        region_code="NW",
                        holdout_group=group,
                        metadata=metadata,
                    ),
                ]
            )

        self.service.upsert_observations(observations)
        result = self.service.assess(
            brand="gelo",
            region_code="NW",
            product="GeloMyrtol forte",
            signal_context={"signal_present": True, "confidence": 0.8},
        )

        self.assertEqual(result["outcome_readiness"]["status"], "ready")
        self.assertTrue(result["holdout_eligibility"]["eligible"])
        self.assertTrue(result["holdout_eligibility"]["ready"])
        self.assertEqual(result["evidence_status"], "commercially_validated")
        self.assertTrue(result["commercial_gate"]["budget_decision_allowed"])

    def test_assess_falls_back_to_media_outcome_records_when_generic_table_is_empty(self) -> None:
        start = datetime(2026, 1, 5)
        for offset in range(14):
            week = start + timedelta(days=7 * offset)
            self.db.add(
                MediaOutcomeRecord(
                    week_start=week,
                    brand="gelo",
                    product="GeloRevoice",
                    region_code="HH",
                    media_spend_eur=900 + offset * 10,
                    qualified_visits=80 + offset,
                    sales_units=25 + offset,
                    source_label="manual",
                    extra_data={"campaign_id": f"hh-{offset}", "channel": "search"},
                )
            )
        self.db.commit()

        result = self.service.assess(
            brand="gelo",
            region_code="HH",
            product="GeloRevoice",
            signal_context={"event_probability": 0.69, "decision_stage": "prepare"},
        )

        self.assertEqual(result["metadata"]["source_mode"], "media_outcome_records_fallback")
        self.assertNotEqual(result["outcome_readiness"]["status"], "missing")
        self.assertGreater(result["outcome_readiness"]["coverage_weeks"], 0)


if __name__ == "__main__":
    unittest.main()
