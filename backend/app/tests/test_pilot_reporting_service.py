from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import AuditLog, Base, MarketingOpportunity, MediaOutcomeRecord
from app.services.media.pilot_reporting_service import PilotReportingService


class PilotReportingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = PilotReportingService(self.db)
        self._seed_recommendations_and_outcomes()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _campaign_payload(self, *, region_code: str, weekly_budget: float, event_probability: float) -> dict:
        return {
            "targeting": {"region_scope": [region_code]},
            "campaign": {"campaign_name": f"Pilot {region_code}", "status": "ACTIVATED"},
            "budget_plan": {"weekly_budget_eur": weekly_budget},
            "trigger_snapshot": {
                "source": "ForecastDecisionService",
                "event": "Influenza A Forecast Event Window",
                "details": f"Regional signal for {region_code}.",
                "confidence": event_probability,
            },
            "forecast_assessment": {
                "event_forecast": {"event_probability": event_probability},
                "forecast_quality": {"forecast_readiness": "GO"},
            },
            "playbook": {"key": "ERKAELTUNGSWELLE", "title": "Atemwegswelle"},
            "campaign_preview": {
                "budget": {
                    "weekly_budget_eur": weekly_budget,
                    "total_flight_budget_eur": weekly_budget * 2,
                },
                "activation_window": {},
            },
        }

    def _add_outcome_rows(
        self,
        *,
        region_code: str,
        product: str,
        week_starts: list[datetime],
        revenue_values: list[float],
        sales_values: list[float],
    ) -> None:
        for week_start, revenue, sales in zip(week_starts, revenue_values, sales_values, strict=True):
            self.db.add(
                MediaOutcomeRecord(
                    week_start=week_start,
                    brand="gelo",
                    product=product,
                    region_code=region_code,
                    media_spend_eur=10000.0,
                    qualified_visits=160.0,
                    sales_units=sales,
                    revenue_eur=revenue,
                    source_label="manual",
                    extra_data={"campaign_id": f"{region_code}-{week_start.date().isoformat()}"},
                )
            )

    def _seed_recommendations_and_outcomes(self) -> None:
        first_created = datetime(2026, 1, 1, 9, 0, 0)
        first_activation_start = datetime(2026, 1, 15, 0, 0, 0)
        first_activation_end = datetime(2026, 1, 28, 0, 0, 0)
        first = MarketingOpportunity(
            opportunity_id="pilot-opp-sh",
            opportunity_type="PLAYBOOK_AI",
            status="ACTIVATED",
            urgency_score=84.0,
            region_target={"states": ["SH"]},
            trigger_source="ForecastDecisionService",
            trigger_event="Influenza A Forecast Event Window",
            brand="gelo",
            product="GeloMyrtol forte",
            budget_shift_pct=28.0,
            channel_mix={"search": 40, "social": 35, "programmatic": 25},
            activation_start=first_activation_start,
            activation_end=first_activation_end,
            recommendation_reason="Norddeutschland jetzt priorisieren.",
            campaign_payload=self._campaign_payload(region_code="SH", weekly_budget=40000.0, event_probability=0.78),
            playbook_key="ERKAELTUNGSWELLE",
            strategy_mode="PLAYBOOK_AI",
            created_at=first_created,
            updated_at=first_activation_end,
        )

        second_created = datetime(2026, 2, 1, 9, 0, 0)
        second_activation_start = datetime(2026, 2, 15, 0, 0, 0)
        second_activation_end = datetime(2026, 2, 28, 0, 0, 0)
        second = MarketingOpportunity(
            opportunity_id="pilot-opp-by",
            opportunity_type="PLAYBOOK_AI",
            status="ACTIVATED",
            urgency_score=55.0,
            region_target={"states": ["BY"]},
            trigger_source="ForecastDecisionService",
            trigger_event="Influenza A Forecast Event Window",
            brand="gelo",
            product="GeloRevoice",
            budget_shift_pct=16.0,
            channel_mix={"search": 50, "social": 25, "programmatic": 25},
            activation_start=second_activation_start,
            activation_end=second_activation_end,
            recommendation_reason="Sueddeutschland testen.",
            campaign_payload=self._campaign_payload(region_code="BY", weekly_budget=30000.0, event_probability=0.61),
            playbook_key="ERKAELTUNGSWELLE",
            strategy_mode="PLAYBOOK_AI",
            created_at=second_created,
            updated_at=second_activation_end,
        )

        self.db.add_all([first, second])
        self.db.commit()

        for row, created_at in ((first, first_created), (second, second_created)):
            self.db.add_all([
                AuditLog(
                    timestamp=created_at + timedelta(days=2),
                    user="system",
                    action="STATUS_CHANGE",
                    entity_type="MarketingOpportunity",
                    entity_id=row.id,
                    old_value="READY",
                    new_value="APPROVED",
                    reason=row.opportunity_id,
                ),
                AuditLog(
                    timestamp=created_at + timedelta(days=4),
                    user="system",
                    action="STATUS_CHANGE",
                    entity_type="MarketingOpportunity",
                    entity_id=row.id,
                    old_value="APPROVED",
                    new_value="ACTIVATED",
                    reason=row.opportunity_id,
                ),
            ])

        self._add_outcome_rows(
            region_code="SH",
            product="GeloMyrtol forte",
            week_starts=[datetime(2025, 12, 29), datetime(2026, 1, 5), datetime(2026, 1, 12), datetime(2026, 1, 19)],
            revenue_values=[5000.0, 5200.0, 8200.0, 8600.0],
            sales_values=[100.0, 104.0, 162.0, 168.0],
        )
        self._add_outcome_rows(
            region_code="BY",
            product="GeloRevoice",
            week_starts=[datetime(2026, 1, 26), datetime(2026, 2, 2), datetime(2026, 2, 9), datetime(2026, 2, 16)],
            revenue_values=[9000.0, 8800.0, 6500.0, 6300.0],
            sales_values=[170.0, 166.0, 120.0, 118.0],
        )
        self.db.commit()

    def test_build_scope_comparison_wrapper_delegates_to_outcomes_module(self) -> None:
        expected = {"comparison_id": "patched"}

        with patch(
            "app.services.media.pilot_reporting_outcomes.build_scope_comparison",
            return_value=expected,
        ) as build_mock:
            payload = self.service._build_scope_comparison(
                brand="gelo",
                card={"id": "opp-1"},
                scope={"region_code": "SH", "region_name": "Schleswig-Holstein"},
                activation_window={"start": "2026-01-15T00:00:00", "end": "2026-01-28T00:00:00"},
                signal_context={"stage": "activate"},
                lead_time_days=14,
                current_status="ACTIVATED",
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            card={"id": "opp-1"},
            scope={"region_code": "SH", "region_name": "Schleswig-Holstein"},
            activation_window={"start": "2026-01-15T00:00:00", "end": "2026-01-28T00:00:00"},
            signal_context={"stage": "activate"},
            lead_time_days=14,
            current_status="ACTIVATED",
        )

    def test_metric_summary_wrapper_delegates_to_outcomes_module(self) -> None:
        expected = {"source_mode": "patched", "observation_count": 1, "coverage_weeks": 1, "metrics": {}}

        with patch(
            "app.services.media.pilot_reporting_outcomes.metric_summary",
            return_value=expected,
        ) as summary_mock:
            payload = self.service._metric_summary(
                brand="gelo",
                product="GeloProsed",
                region_code="SH",
                window_start=datetime(2026, 1, 1),
                window_end=datetime(2026, 1, 31),
            )

        self.assertIs(payload, expected)
        summary_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            product="GeloProsed",
            region_code="SH",
            window_start=datetime(2026, 1, 1),
            window_end=datetime(2026, 1, 31),
        )

    def test_region_evidence_view_wrapper_delegates_to_outcomes_module(self) -> None:
        expected = [{"region_code": "SH"}]

        with patch(
            "app.services.media.pilot_reporting_outcomes.region_evidence_view",
            return_value=expected,
        ) as view_mock:
            payload = self.service._region_evidence_view({"SH": {"recommendations": 1}})

        self.assertIs(payload, expected)
        view_mock.assert_called_once_with({"SH": {"recommendations": 1}})

    def test_pilot_kpi_summary_wrapper_delegates_to_outcomes_module(self) -> None:
        expected = {"hit_rate": {"value": 1.0}}

        with patch(
            "app.services.media.pilot_reporting_outcomes.pilot_kpi_summary",
            return_value=expected,
        ) as summary_mock:
            payload = self.service._pilot_kpi_summary([{"comparison_id": "patched"}])

        self.assertIs(payload, expected)
        summary_mock.assert_called_once_with([{"comparison_id": "patched"}])

    def test_build_pilot_report_returns_history_activation_views_and_kpis(self) -> None:
        report = self.service.build_pilot_report(
            brand="gelo",
            window_start=datetime(2025, 12, 1),
            window_end=datetime(2026, 3, 31),
        )

        self.assertEqual(report["summary"]["total_recommendations"], 2)
        self.assertEqual(report["summary"]["activated_recommendations"], 2)
        self.assertEqual(len(report["recommendation_history"]), 2)
        self.assertEqual(len(report["activation_history"]), 2)
        self.assertEqual(len(report["region_evidence_view"]), 2)
        self.assertEqual(len(report["before_after_comparison"]), 2)

        hit_rate = report["pilot_kpi_summary"]["hit_rate"]
        self.assertEqual(hit_rate["assessed"], 2)
        self.assertAlmostEqual(hit_rate["value"], 0.5, places=4)

        lead_time = report["pilot_kpi_summary"]["early_warning_lead_time_days"]
        self.assertEqual(lead_time["average"], 14.0)
        self.assertEqual(lead_time["median"], 14.0)

        prioritization = report["pilot_kpi_summary"]["share_of_correct_regional_prioritizations"]
        self.assertEqual(prioritization["assessed_high_priority"], 1)
        self.assertEqual(prioritization["value"], 1.0)

        comparisons = {item["region_code"]: item for item in report["before_after_comparison"]}
        self.assertEqual(comparisons["SH"]["outcome_support_status"], "supportive")
        self.assertEqual(comparisons["BY"]["outcome_support_status"], "not_supportive")
        self.assertGreater(comparisons["SH"]["delta_pct"], 0)
        self.assertLess(comparisons["BY"]["delta_pct"], 0)

    def test_recommendation_history_uses_audit_log_for_status_timeline(self) -> None:
        report = self.service.build_pilot_report(
            brand="gelo",
            window_start=datetime(2025, 12, 1),
            window_end=datetime(2026, 3, 31),
        )

        first = next(item for item in report["recommendation_history"] if item["opportunity_id"] == "pilot-opp-sh")
        timeline = first["status_history"]

        self.assertEqual(timeline[0]["source"], "recommendation_created")
        self.assertEqual(timeline[1]["to_status"], "APPROVED")
        self.assertEqual(timeline[2]["to_status"], "ACTIVATED")

        activation = next(item for item in report["activation_history"] if item["opportunity_id"] == "pilot-opp-sh")
        self.assertIsNotNone(activation["approved_at"])
        self.assertIsNotNone(activation["activated_at"])

    def test_build_pilot_report_returns_stable_empty_state_without_recommendations(self) -> None:
        self.db.query(AuditLog).delete()
        self.db.query(MediaOutcomeRecord).delete()
        self.db.query(MarketingOpportunity).delete()
        self.db.commit()

        report = self.service.build_pilot_report(
            brand="gelo",
            window_start=datetime(2025, 12, 1),
            window_end=datetime(2026, 3, 31),
        )

        self.assertEqual(report["summary"]["total_recommendations"], 0)
        self.assertEqual(report["summary"]["activated_recommendations"], 0)
        self.assertEqual(report["summary"]["comparisons_with_evidence"], 0)
        self.assertEqual(report["recommendation_history"], [])
        self.assertEqual(report["activation_history"], [])
        self.assertEqual(report["region_evidence_view"], [])
        self.assertEqual(report["before_after_comparison"], [])
        self.assertIsNone(report["pilot_kpi_summary"]["hit_rate"]["value"])
        self.assertEqual(report["pilot_kpi_summary"]["hit_rate"]["assessed"], 0)
        self.assertIsNone(report["pilot_kpi_summary"]["early_warning_lead_time_days"]["average"])


if __name__ == "__main__":
    unittest.main()
