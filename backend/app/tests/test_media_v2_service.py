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

    def test_evidence_payload_hides_truth_validation_without_coverage(self) -> None:
        cockpit_payload = {
            "backtest_summary": {
                "latest_market": {"run_id": "market-1"},
                "latest_customer": {
                    "run_id": "customer-legacy",
                    "metrics": {"data_points": 7, "r2_score": -2.32},
                },
                "recent_runs": [],
            },
            "data_freshness": {},
            "source_status": {"items": []},
        }

        with (
            patch.object(self.service.cockpit_service, "get_cockpit_payload", return_value=cockpit_payload),
            patch.object(self.service, "get_truth_coverage", return_value={"coverage_weeks": 0, "trust_readiness": "noch_nicht_angeschlossen"}),
            patch.object(self.service, "get_signal_stack", return_value={"summary": {}, "items": []}),
            patch.object(self.service, "get_model_lineage", return_value={"drift_state": "warning"}),
        ):
            payload = self.service.get_evidence_payload()

        self.assertIsNone(payload["truth_validation"])
        self.assertEqual(payload["truth_validation_legacy"]["run_id"], "customer-legacy")
        self.assertTrue(any("Legacy-Run" in item for item in payload["known_limits"]))

    def test_regions_payload_exposes_severity_momentum_and_actionability(self) -> None:
        cockpit_payload = {
            "peix_epi_score": {
                "regions": {
                    "SH": {
                        "score_0_100": 62.0,
                        "top_drivers": [{"label": "Epidemiologie", "strength_pct": 70.0}],
                        "layer_contributions": {"Bio": 22.0, "Forecast": 18.0, "Weather": 10.0, "Shortage": 6.0, "Baseline": 5.0},
                    },
                    "HH": {
                        "score_0_100": 60.0,
                        "top_drivers": [{"label": "Versorgungslage", "strength_pct": 72.0}],
                        "layer_contributions": {"Bio": 12.0, "Forecast": 10.0, "Weather": 8.0, "Shortage": 16.0, "Baseline": 4.0},
                    },
                },
            },
            "map": {
                "has_data": True,
                "date": "2026-02-25T00:00:00",
                "regions": {
                    "SH": {
                        "name": "Schleswig-Holstein",
                        "impact_probability": 74.0,
                        "intensity": 0.9,
                        "trend": "fallend",
                        "change_pct": -18.0,
                        "tooltip": {"recommended_product": "GeloProsed"},
                        "recommendation_ref": {"urgency_score": 150, "card_id": "card-sh"},
                    },
                    "HH": {
                        "name": "Hamburg",
                        "impact_probability": 68.0,
                        "intensity": 0.6,
                        "trend": "steigend",
                        "change_pct": 12.0,
                        "tooltip": {"recommended_product": "GeloProsed"},
                        "recommendation_ref": {"urgency_score": 120, "card_id": "card-hh"},
                    },
                },
                "activation_suggestions": [
                    {"region": "SH", "reason": "SH aktivieren", "budget_shift_pct": 15.0},
                    {"region": "HH", "reason": "HH aktivieren", "budget_shift_pct": 12.0},
                ],
            },
        }

        with (
            patch.object(self.service.cockpit_service, "get_cockpit_payload", return_value=cockpit_payload),
            patch.object(self.service, "get_decision_payload", return_value={"weekly_decision": {"decision_state": "WATCH"}}),
        ):
            payload = self.service.get_regions_payload()

        top_region = payload["top_regions"][0]
        self.assertIn("severity_score", top_region)
        self.assertIn("momentum_score", top_region)
        self.assertIn("actionability_score", top_region)
        self.assertIn(top_region["decision_mode"], {"epidemic_wave", "mixed", "supply_window"})


if __name__ == "__main__":
    unittest.main()
