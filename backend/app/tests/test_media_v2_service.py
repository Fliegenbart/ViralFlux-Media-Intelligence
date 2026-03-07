import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.services.media.v2_service import MediaV2Service


class MediaV2ServiceTruthCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MediaV2Service(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_import_outcomes_from_records_updates_truth_coverage(self) -> None:
        result = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[
                {
                    "week_start": "2026-01-05T00:00:00",
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "media_spend_eur": 10000,
                    "sales_units": 120,
                },
                {
                    "week_start": "2026-01-12T00:00:00",
                    "product": "GeloRevoice",
                    "region_code": "HH",
                    "media_spend_eur": 9000,
                    "order_count": 44,
                },
            ],
        )

        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["coverage"]["coverage_weeks"], 2)
        self.assertEqual(result["coverage"]["regions_covered"], 2)
        self.assertEqual(result["coverage"]["products_covered"], 2)
        self.assertIn("Media Spend", result["coverage"]["outcome_fields_present"])
        self.assertEqual(result["coverage"]["trust_readiness"], "erste_signale")

    def test_import_outcomes_supports_inline_csv_payload(self) -> None:
        csv_payload = (
            "week_start,product,region_code,media_spend_eur,qualified_visits\n"
            "2026-02-02T00:00:00,GeloProsed,SH,12000,320\n"
            "2026-02-09T00:00:00,GeloProsed,HH,14000,410\n"
        )

        result = self.service.import_outcomes(
            source_label="csv_upload",
            brand="gelo",
            csv_payload=csv_payload,
        )

        self.assertEqual(result["imported"], 2)
        coverage = self.service.get_truth_coverage(brand="gelo")
        self.assertEqual(coverage["coverage_weeks"], 2)
        self.assertIn("Qualifizierte Besuche", coverage["outcome_fields_present"])
        self.assertIn("csv_upload", coverage["source_labels"])

    def test_decision_payload_suppresses_hard_shift_in_watch(self) -> None:
        cockpit_payload = {
            "map": {
                "date": "2026-02-25T00:00:00",
                "top_regions": [
                    {"code": "SH", "name": "Schleswig-Holstein", "peix_score": 68, "trend": "steigend"},
                ],
            },
            "backtest_summary": {
                "latest_market": {
                    "quality_gate": {
                        "overall_passed": False,
                    },
                },
            },
            "source_status": {
                "items": [
                    {"source_key": "wastewater", "is_live": True},
                    {"source_key": "survstat", "is_live": True},
                    {"source_key": "are_konsultation", "is_live": True},
                    {"source_key": "notaufnahme", "is_live": True},
                ],
            },
            "peix_epi_score": {
                "top_drivers": [{"label": "AMELAG", "strength_pct": 44}],
            },
        }
        cards = [
            {
                "id": "card-1",
                "lifecycle_state": "REVIEW",
                "is_publishable": False,
                "recommended_product": "GeloProsed",
                "product": "GeloProsed",
                "budget_shift_pct": 18.0,
                "decision_brief": {
                    "summary_sentence": "Starke Aktivierung.",
                    "recommendation": {"primary_region": "Schleswig-Holstein"},
                },
            },
        ]

        with (
            patch.object(self.service.cockpit_service, "get_cockpit_payload", return_value=cockpit_payload),
            patch.object(self.service, "get_truth_coverage", return_value={"coverage_weeks": 0, "trust_readiness": "noch_nicht_angeschlossen"}),
            patch.object(self.service, "get_model_lineage", return_value={"drift_state": "warning"}),
            patch.object(self.service, "get_signal_stack", return_value={"summary": {"top_drivers": [], "math_stack": {}}}),
            patch.object(self.service, "_build_campaign_queue", return_value={
                "visible_cards": cards,
                "primary_cards": cards,
                "summary": {"visible_cards": 1, "hidden_backlog_cards": 0},
            }),
            patch.object(self.service, "_campaign_cards", return_value=cards),
        ):
            payload = self.service.get_decision_payload()

        weekly_decision = payload["weekly_decision"]
        self.assertEqual(weekly_decision["decision_state"], "WATCH")
        self.assertIsNone(weekly_decision["budget_shift"])
        self.assertIn("vorbereiten", weekly_decision["recommended_action"].lower())

    def test_campaigns_payload_limits_visible_board_to_eight_cards(self) -> None:
        cards = []
        for index in range(10):
            cards.append({
                "id": f"card-{index}",
                "lifecycle_state": "REVIEW",
                "is_publishable": False,
                "publish_blockers": ["Paket ist noch nicht in Prüfung."],
                "freshness_state": "current",
                "urgency_score": 80 - index,
                "confidence": 0.8,
                "updated_at": f"2026-03-{20-index:02d}T00:00:00",
                "condition_key": f"condition-{index}",
                "recommended_product": "GeloProsed",
                "product": "GeloProsed",
                "region_codes": ["SH"],
                "activation_window": {
                    "start": "2026-03-09T00:00:00",
                    "end": "2026-03-16T00:00:00",
                },
            })

        with patch.object(self.service, "_campaign_cards", return_value=cards):
            payload = self.service.get_campaigns_payload(limit=120)

        self.assertEqual(len(payload["cards"]), 8)
        self.assertEqual(payload["summary"]["visible_cards"], 8)
        self.assertEqual(payload["summary"]["hidden_backlog_cards"], 2)


if __name__ == "__main__":
    unittest.main()
