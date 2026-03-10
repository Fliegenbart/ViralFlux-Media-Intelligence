import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, BrandProduct, MediaOutcomeImportBatch, MediaOutcomeRecord, WastewaterAggregated
from app.services.media.v2_service import MediaV2Service


class MediaV2ServiceTruthCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MediaV2Service(self.db)
        self._seed_brand_products()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _seed_brand_products(self) -> None:
        now = datetime.utcnow()
        self.db.add_all([
            BrandProduct(
                brand="gelo",
                product_name="GeloProsed",
                source_url="manual://seed",
                source_hash="seed-geloprosed",
                active=True,
                created_at=now,
                updated_at=now,
            ),
            BrandProduct(
                brand="gelo",
                product_name="GeloRevoice",
                source_url="manual://seed",
                source_hash="seed-gelorevoice",
                active=True,
                created_at=now,
                updated_at=now,
            ),
        ])
        self.db.commit()

    def _seed_truth_reference(self, latest_week: datetime) -> None:
        self.db.add(
            WastewaterAggregated(
                datum=latest_week,
                available_time=latest_week,
                virus_typ="Influenza A",
                n_standorte=12,
                anteil_bev=0.6,
                viruslast=1.2,
                viruslast_normalisiert=58.0,
            )
        )
        self.db.commit()

    def _seed_outcome_series(
        self,
        *,
        start: datetime,
        weeks: int,
        product: str = "GeloProsed",
        region_code: str = "SH",
    ) -> None:
        records = []
        for offset in range(weeks):
            records.append({
                "week_start": (start + timedelta(days=7 * offset)).isoformat(),
                "product": product,
                "region_code": region_code,
                "media_spend_eur": 10000 + offset * 100,
                "sales_units": 120 + offset * 3,
                "qualified_visits": 200 + offset * 2,
                "search_lift_index": 18 + (offset % 5),
            })
        self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=records,
        )

    def test_validate_only_csv_returns_preview_without_persisting_outcomes(self) -> None:
        self._seed_truth_reference(datetime(2026, 2, 16))
        csv_payload = (
            "week_start,product,region_code,media_spend_eur,sales_units\n"
            "2026-02-02,GeloProsed,SH,12000,320\n"
            "2026-02-09,GeloRevoice,Hamburg,9000,110\n"
        )

        result = self.service.import_outcomes(
            source_label="csv_upload",
            brand="gelo",
            csv_payload=csv_payload,
            validate_only=True,
            file_name="truth.csv",
        )

        self.assertTrue(result["preview_only"])
        self.assertEqual(result["imported"], 0)
        self.assertEqual(result["batch_summary"]["status"], "validated")
        self.assertEqual(result["batch_summary"]["rows_valid"], 2)
        self.assertEqual(result["coverage_after_import"]["coverage_weeks"], 2)
        self.assertEqual(self.db.query(MediaOutcomeRecord).count(), 0)
        self.assertEqual(self.db.query(MediaOutcomeImportBatch).count(), 1)

    def test_import_outcomes_from_records_updates_truth_coverage_and_history(self) -> None:
        self._seed_truth_reference(datetime(2026, 2, 16))
        result = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[
                {
                    "week_start": "2026-02-02T00:00:00",
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "media_spend_eur": 10000,
                    "sales_units": 120,
                },
                {
                    "week_start": "2026-02-09T00:00:00",
                    "product": "GeloRevoice",
                    "region_code": "HH",
                    "media_spend_eur": 9000,
                    "order_count": 44,
                },
            ],
        )

        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["coverage_after_import"]["coverage_weeks"], 2)
        self.assertEqual(result["coverage_after_import"]["regions_covered"], 2)
        self.assertEqual(result["coverage_after_import"]["products_covered"], 2)
        self.assertIn("Media Spend", result["coverage_after_import"]["required_fields_present"])
        self.assertIn("Sales", result["coverage_after_import"]["conversion_fields_present"])
        self.assertEqual(result["coverage_after_import"]["trust_readiness"], "erste_signale")
        self.assertEqual(result["coverage_after_import"]["truth_freshness_state"], "fresh")
        self.assertEqual(result["coverage_after_import"]["latest_batch_id"], result["batch_id"])

        batches = self.service.list_outcome_import_batches(brand="gelo")
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["rows_imported"], 2)
        self.assertEqual(batches[0]["status"], "imported")

    def test_duplicate_rows_and_unknown_products_are_reported_as_issues(self) -> None:
        result = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[
                {
                    "week_start": "2026-02-02T00:00:00",
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "media_spend_eur": 10000,
                    "sales_units": 120,
                },
                {
                    "week_start": "2026-02-02T00:00:00",
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "media_spend_eur": 9000,
                    "sales_units": 99,
                },
                {
                    "week_start": "2026-02-09T00:00:00",
                    "product": "Unbekanntes Produkt",
                    "region_code": "HH",
                    "media_spend_eur": 5000,
                    "sales_units": 20,
                },
            ],
        )

        issue_codes = {issue["issue_code"] for issue in result["issues"]}
        self.assertEqual(result["imported"], 1)
        self.assertIn("duplicate_in_upload", issue_codes)
        self.assertIn("unknown_product", issue_codes)
        self.assertEqual(result["batch_summary"]["rows_duplicate"], 1)
        self.assertEqual(result["batch_summary"]["status"], "partial_success")

    def test_import_respects_replace_existing(self) -> None:
        initial = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[{
                "week_start": "2026-02-02T00:00:00",
                "product": "GeloProsed",
                "region_code": "SH",
                "media_spend_eur": 10000,
                "sales_units": 120,
            }],
        )
        self.assertEqual(initial["imported"], 1)

        blocked = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[{
                "week_start": "2026-02-02T00:00:00",
                "product": "GeloProsed",
                "region_code": "Schleswig-Holstein",
                "media_spend_eur": 15000,
                "sales_units": 180,
            }],
            replace_existing=False,
        )
        self.assertEqual(blocked["imported"], 0)
        self.assertTrue(any(issue["issue_code"] == "duplicate_existing" for issue in blocked["issues"]))

        replaced = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[{
                "week_start": "2026-02-02T00:00:00",
                "product": "GeloProsed",
                "region_code": "Schleswig-Holstein",
                "media_spend_eur": 15000,
                "sales_units": 180,
            }],
            replace_existing=True,
        )
        self.assertEqual(replaced["imported"], 1)
        stored = self.db.query(MediaOutcomeRecord).one()
        self.assertEqual(stored.region_code, "SH")
        self.assertEqual(stored.media_spend_eur, 15000)

    def test_truth_gate_marks_stale_truth_as_risk(self) -> None:
        self._seed_truth_reference(datetime(2026, 3, 3))
        start = datetime(2025, 7, 21)
        records = []
        for offset in range(30):
            records.append({
                "week_start": (start + timedelta(days=7 * offset)).isoformat(),
                "product": "GeloProsed",
                "region_code": "SH",
                "media_spend_eur": 10000 + offset,
                "sales_units": 120 + offset,
            })
        self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=records,
        )

        stale_coverage = self.service.get_truth_coverage(brand="gelo", virus_typ="Influenza A")
        self.assertEqual(stale_coverage["trust_readiness"], "im_aufbau")
        self.assertEqual(stale_coverage["truth_freshness_state"], "stale")

    def test_decision_payload_surfaces_truth_risk_when_truth_is_not_ready(self) -> None:
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
            patch.object(self.service, "get_truth_coverage", return_value={
                "coverage_weeks": 10,
                "trust_readiness": "erste_signale",
                "truth_freshness_state": "fresh",
                "required_fields_present": ["Media Spend"],
                "conversion_fields_present": ["Sales"],
                "last_imported_at": "2026-03-01T00:00:00",
                "latest_batch_id": "batch-1",
            }),
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
        self.assertIn("Kundendaten", weekly_decision["truth_risk_flag"])
        self.assertIsNone(weekly_decision["budget_shift"])
        self.assertEqual(
            weekly_decision["field_contracts"]["event_probability"]["semantics"],
            "forecast_event_probability",
        )
        self.assertEqual(
            weekly_decision["field_contracts"]["signal_score"]["semantics"],
            "ranking_signal",
        )

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

    def test_campaign_cards_include_outcome_learning_fields(self) -> None:
        self._seed_truth_reference(datetime(2026, 3, 3))
        self._seed_outcome_series(
            start=datetime(2025, 8, 18),
            weeks=30,
        )

        opportunity = {
            "id": "opp-1",
            "status": "READY",
            "type": "activation",
            "urgency_score": 62.0,
            "brand": "gelo",
            "product": "GeloProsed",
            "recommended_product": "GeloProsed",
            "region_codes": ["SH"],
            "budget_shift_pct": 16.0,
            "channel_mix": {"programmatic": 35, "social": 30, "search": 20, "ctv": 15},
            "campaign_payload": {
                "message_framework": {"hero_message": "Norddeutschland weiter priorisieren."},
                "channel_plan": [{"channel": "search", "share_pct": 40.0}],
                "guardrail_report": {"passed": True},
            },
            "campaign_preview": {
                "budget": {"weekly_budget_eur": 120000.0},
                "activation_window": {
                    "start": "2026-03-09T00:00:00",
                    "end": "2026-03-22T00:00:00",
                },
            },
            "condition_key": "erkaltung_akut",
        }

        with patch.object(self.service.engine, "get_opportunities", return_value=[opportunity]):
            cards = self.service._campaign_cards(brand="gelo", limit=20)

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertIsNotNone(card["outcome_signal_score"])
        self.assertIsNotNone(card["outcome_confidence_pct"])
        self.assertEqual(card["learning_state"], "im_aufbau")
        self.assertEqual(
            card["field_contracts"]["outcome_signal_score"]["semantics"],
            "observed_outcome_signal",
        )

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
        truth_snapshot = {
            "coverage": {
                "coverage_weeks": 0,
                "trust_readiness": "noch_nicht_angeschlossen",
                "truth_freshness_state": "missing",
                "required_fields_present": [],
                "conversion_fields_present": [],
            },
            "recent_batches": [],
            "known_limits": [],
        }

        with (
            patch.object(self.service.cockpit_service, "get_cockpit_payload", return_value=cockpit_payload),
            patch.object(self.service, "get_truth_evidence", return_value=truth_snapshot),
            patch.object(self.service, "get_signal_stack", return_value={"summary": {}, "items": []}),
            patch.object(self.service, "get_model_lineage", return_value={"drift_state": "warning"}),
            patch.object(self.service, "get_forecast_monitoring", return_value={"monitoring_status": "warning", "alerts": ["Drift aktiv"]}),
        ):
            payload = self.service.get_evidence_payload()

        self.assertIsNone(payload["truth_validation"])
        self.assertEqual(payload["truth_validation_legacy"]["run_id"], "customer-legacy")
        self.assertEqual(payload["truth_snapshot"]["coverage"]["trust_readiness"], "noch_nicht_angeschlossen")
        self.assertEqual(payload["forecast_monitoring"]["monitoring_status"], "warning")
        self.assertEqual(payload["outcome_learning_summary"]["learning_state"], "missing")

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
                        "signal_score": 62.0,
                        "intensity": 0.9,
                        "trend": "fallend",
                        "change_pct": -18.0,
                        "tooltip": {"recommended_product": "GeloProsed"},
                        "recommendation_ref": {"urgency_score": 150, "card_id": "card-sh"},
                    },
                    "HH": {
                        "name": "Hamburg",
                        "impact_probability": 68.0,
                        "signal_score": 60.0,
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
        self.assertEqual(top_region["priority_rank"], 1)
        self.assertIn(top_region["decision_mode"], {"epidemic_wave", "mixed", "supply_window"})
        self.assertEqual(top_region["field_contracts"]["signal_score"]["semantics"], "ranking_signal")

    def test_regions_payload_prefers_signal_score_over_legacy_impact_probability(self) -> None:
        cockpit_payload = {
            "peix_epi_score": {
                "regions": {
                    "SH": {
                        "score_0_100": 48.0,
                        "top_drivers": [{"label": "AMELAG", "strength_pct": 55.0}],
                        "layer_contributions": {"Bio": 18.0, "Forecast": 8.0},
                    },
                    "HH": {
                        "score_0_100": 81.0,
                        "top_drivers": [{"label": "Forecast", "strength_pct": 62.0}],
                        "layer_contributions": {"Bio": 26.0, "Forecast": 18.0},
                    },
                },
            },
            "map": {
                "has_data": True,
                "date": "2026-02-25T00:00:00",
                "regions": {
                    "SH": {
                        "name": "Schleswig-Holstein",
                        "impact_probability": 91.0,
                        "signal_score": 48.0,
                        "intensity": 0.45,
                        "trend": "stabil",
                        "change_pct": 0.0,
                        "tooltip": {"recommended_product": "GeloProsed"},
                        "recommendation_ref": {"urgency_score": 80, "card_id": "card-sh"},
                    },
                    "HH": {
                        "name": "Hamburg",
                        "impact_probability": 64.0,
                        "signal_score": 81.0,
                        "intensity": 0.45,
                        "trend": "stabil",
                        "change_pct": 0.0,
                        "tooltip": {"recommended_product": "GeloProsed"},
                        "recommendation_ref": {"urgency_score": 80, "card_id": "card-hh"},
                    },
                },
                "activation_suggestions": [],
            },
        }

        with (
            patch.object(self.service.cockpit_service, "get_cockpit_payload", return_value=cockpit_payload),
            patch.object(self.service, "get_decision_payload", return_value={"weekly_decision": {"decision_state": "WATCH"}}),
        ):
            payload = self.service.get_regions_payload()

        self.assertEqual(payload["top_regions"][0]["code"], "HH")
        self.assertEqual(payload["map"]["regions"]["HH"]["signal_score"], 81.0)
        self.assertEqual(payload["map"]["regions"]["HH"]["impact_probability"], 64.0)

    def test_signal_stack_uses_feature_families_from_model_lineage(self) -> None:
        cockpit_payload = {
            "data_freshness": {},
            "source_status": {"items": []},
            "peix_epi_score": {
                "national_score": 61.3,
                "national_band": "high",
                "top_drivers": [],
                "context_signals": {},
            },
        }

        with (
            patch.object(self.service.cockpit_service, "get_cockpit_payload", return_value=cockpit_payload),
            patch.object(
                self.service,
                "get_model_lineage",
                return_value={"feature_families": ["AMELAG-Lags", "Google Trends", "Interne Historie"]},
            ),
        ):
            payload = self.service.get_signal_stack(virus_typ="Influenza A")

        self.assertEqual(
            payload["summary"]["math_stack"]["feature_families"],
            ["AMELAG-Lags", "Google Trends", "Interne Historie"],
        )


if __name__ == "__main__":
    unittest.main()
