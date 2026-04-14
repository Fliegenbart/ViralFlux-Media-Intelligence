from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, MarketingOpportunity
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine


class OpportunityEngineMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MarketingOpportunityEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_save_opportunity_deduplicates_and_updates_supply_gap_payload(self) -> None:
        created = self.service._save_opportunity(
            {
                "id": "opp-save-1",
                "type": "RESOURCE_SCARCITY",
                "status": "NEW",
                "urgency_score": 61.0,
                "trigger_context": {
                    "source": "BfArM_API",
                    "event": "SUPPLY_SHOCK_WINDOW",
                    "detected_at": "2026-04-08T09:00:00Z",
                },
                "sales_pitch": {"headline": "Erster Pitch"},
                "suggested_products": [{"product_name": "Altprodukt"}],
                "_supply_gap_applied": True,
                "_supply_gap_priority_multiplier": 1.4,
                "_supply_gap_product": "GeloProsed",
                "_supply_gap_matched_products": ["GeloProsed"],
            }
        )
        updated = self.service._save_opportunity(
            {
                "id": "opp-save-1",
                "urgency_score": 88.0,
                "sales_pitch": {"headline": "Neuer Pitch"},
                "suggested_products": [{"product_name": "Neuprodukt"}],
                "_supply_gap_applied": True,
                "_supply_gap_priority_multiplier": 1.8,
                "_supply_gap_product": "GeloMyrtol forte",
                "_supply_gap_matched_products": ["GeloMyrtol forte"],
            }
        )

        row = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == "opp-save-1")
            .one()
        )

        self.assertTrue(created)
        self.assertFalse(updated)
        self.assertEqual(row.urgency_score, 88.0)
        self.assertEqual(row.sales_pitch["headline"], "Neuer Pitch")
        self.assertEqual(
            row.campaign_payload["supply_gap"]["priority_multiplier"],
            1.8,
        )

    def test_backfill_peix_context_populates_missing_context(self) -> None:
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-peix-1",
            opportunity_type="RESOURCE_SCARCITY",
            status="DRAFT",
            urgency_score=70.0,
            region_target={"states": ["SH"]},
            trigger_source="BfArM_API",
            trigger_event="SUPPLY_SHOCK_WINDOW",
            trigger_details={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            campaign_payload={},
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()

        with patch(
            "app.services.marketing_engine.opportunity_engine_maintenance.RankingSignalService"
        ) as service_cls:
            service_cls.return_value.build.return_value = {
                "regions": {
                    "SH": {
                        "score_0_100": 66.0,
                        "risk_band": "ready",
                        "impact_probability": 71.0,
                        "top_drivers": [{"label": "Nordsignal"}],
                    }
                }
            }
            result = self.service.backfill_peix_context(limit=10)

        refreshed = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == "opp-peix-1")
            .one()
        )

        self.assertEqual(result["updated"], 1)
        self.assertEqual(refreshed.campaign_payload["peix_context"]["region_code"], "SH")
        self.assertEqual(refreshed.campaign_payload["peix_context"]["score"], 66.0)
        self.assertEqual(
            refreshed.campaign_payload["ranking_signal_context"]["ranking_signal_score"],
            66.0,
        )
        self.assertEqual(
            refreshed.campaign_payload["ranking_signal_context"]["signal_band"],
            "ready",
        )

    def test_backfill_product_mapping_updates_mapping_and_suggested_products(self) -> None:
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-map-1",
            opportunity_type="RESOURCE_SCARCITY",
            status="DRAFT",
            urgency_score=68.0,
            region_target={"states": ["SH"]},
            trigger_details={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            brand="gelo",
            product="Alle Produkte",
            suggested_products=[{"product_name": "Bestandsprodukt"}],
            campaign_payload={
                "product_mapping": {
                    "mapping_status": "needs_review",
                    "condition_key": "bronchitis_husten",
                    "condition_label": "Bronchitis / Husten",
                }
            },
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()

        self.service.product_catalog_service.resolve_product_for_opportunity = Mock(
            return_value={
                "mapping_status": "approved",
                "recommended_product": "GeloMyrtol forte",
                "candidate_product": "GeloBronchial",
                "mapping_confidence": 0.93,
                "mapping_reason": "Passt zur Lageklasse.",
                "condition_key": "bronchitis_husten",
                "condition_label": "Bronchitis / Husten",
            }
        )

        result = self.service.backfill_product_mapping(limit=10)

        refreshed = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == "opp-map-1")
            .one()
        )
        suggested_names = {
            item["product_name"]
            for item in (refreshed.suggested_products or [])
            if isinstance(item, dict) and item.get("product_name")
        }

        self.assertEqual(result["updated"], 1)
        self.assertEqual(
            refreshed.campaign_payload["product_mapping"]["recommended_product"],
            "GeloMyrtol forte",
        )
        self.assertIn("GeloMyrtol forte", suggested_names)
        self.assertIn("GeloBronchial", suggested_names)

    def test_backfill_product_mapping_rejects_missing_brand(self) -> None:
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-map-blank-brand",
            opportunity_type="RESOURCE_SCARCITY",
            status="DRAFT",
            urgency_score=68.0,
            region_target={"states": ["SH"]},
            trigger_details={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            brand=None,
            product="Alle Produkte",
            campaign_payload={
                "product_mapping": {
                    "mapping_status": "needs_review",
                }
            },
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()

        with self.assertRaises(ValueError):
            self.service.backfill_product_mapping(limit=10)

    def test_backfill_product_mapping_uses_brand_neutral_fallback_label_when_product_missing(self) -> None:
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-map-missing-product",
            opportunity_type="RESOURCE_SCARCITY",
            status="DRAFT",
            urgency_score=68.0,
            region_target={"states": ["SH"]},
            trigger_details={"source": "BfArM_API", "event": "SUPPLY_SHOCK_WINDOW"},
            brand="gelo",
            product=None,
            suggested_products=[],
            campaign_payload={
                "product_mapping": {
                    "mapping_status": "needs_review",
                    "condition_key": "bronchitis_husten",
                    "condition_label": "Bronchitis / Husten",
                }
            },
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()

        self.service.product_catalog_service.resolve_product_for_opportunity = Mock(
            return_value={
                "mapping_status": "needs_review",
                "recommended_product": None,
                "candidate_product": None,
                "mapping_confidence": 0.5,
                "mapping_reason": "Noch offen.",
            }
        )
        self.service._select_product_for_opportunity = Mock(return_value="Freigabe ausstehend")

        result = self.service.backfill_product_mapping(limit=10)

        self.assertEqual(result["updated"], 1)
        self.service._select_product_for_opportunity.assert_called_once_with(
            fallback_product="Alle Produkte",
            product_mapping={
                "mapping_status": "needs_review",
                "recommended_product": None,
                "candidate_product": None,
                "mapping_confidence": 0.5,
                "mapping_reason": "Noch offen.",
                "condition_key": "bronchitis_husten",
                "condition_label": "Bronchitis / Husten",
            },
        )

    def test_enrich_opportunity_for_media_rejects_blank_brand(self) -> None:
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-enrich-blank-brand",
            opportunity_type="RESPIRATORY_ALERT",
            status="DRAFT",
            urgency_score=55.0,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()

        with self.assertRaises(ValueError):
            self.service._enrich_opportunity_for_media(
                opportunity_id="opp-enrich-blank-brand",
                brand="   ",
                product="GeloProsed",
                budget_shift_pct=10.0,
                channel_mix={"search": 100.0},
                reason="test",
                campaign_payload={},
                status="READY",
                activation_start=None,
                activation_end=None,
            )

    def test_regenerate_ai_plan_rejects_missing_brand(self) -> None:
        now = datetime.now(timezone.utc)
        row = MarketingOpportunity(
            opportunity_id="opp-regen-missing-brand",
            opportunity_type="PLAYBOOK_AI",
            status="DRAFT",
            urgency_score=55.0,
            brand=None,
            product="GeloProsed",
            playbook_key="WETTER_REFLEX",
            campaign_payload={
                "playbook": {"key": "WETTER_REFLEX"},
                "targeting": {"region_scope": ["SH"]},
                "trigger_snapshot": {"event": "Influenza A Forecast Event Window"},
                "campaign": {"objective": "Awareness"},
                "budget_plan": {"weekly_budget_eur": 10000.0},
            },
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()

        pack = SimpleNamespace(
            status="ready",
            message_direction="north",
            hero_message="Signal erkannt",
            support_points=[],
            creative_angles=[],
            keyword_clusters=[],
            cta="Mehr erfahren",
            compliance_note="ok",
            library_version="v1",
            library_source="test",
            to_framework=lambda: {},
        )

        with patch(
            "app.services.marketing_engine.opportunity_engine_playbooks.select_gelo_message_pack",
            return_value=pack,
        ), patch.object(
            self.service.ai_planner,
            "generate_plan",
            return_value={"ai_plan": {}, "ai_generation_status": "generated", "ai_meta": {}},
        ), patch.object(
            self.service.guardrails,
            "apply",
            return_value={"ai_plan": {}, "guardrail_report": {}},
        ), patch.object(
            self.service,
            "_model_to_dict",
            return_value={"id": "opp-regen-missing-brand"},
        ):
            with self.assertRaises(ValueError):
                self.service.regenerate_ai_plan("opp-regen-missing-brand")

    def test_generate_action_cards_labels_playbook_fallback_as_rule_based(self) -> None:
        opportunity = {
            "id": "opp-fallback-1",
            "type": "RESOURCE_SCARCITY",
            "status": "DRAFT",
            "urgency_score": 72.0,
            "trigger_context": {"event": "SUPPLY_SHOCK_WINDOW"},
            "region_target": {"states": ["SH"]},
            "sales_pitch": {"headline": "Signal erkannt"},
            "suggested_products": [{"product_name": "GeloProsed"}],
        }

        with patch.object(
            self.service,
            "generate_opportunities",
            return_value={"meta": {"source": "test"}, "opportunities": [opportunity]},
        ), patch.object(
            self.service,
            "_generate_playbook_ai_cards",
            return_value=[],
        ), patch(
            "app.services.marketing_engine.opportunity_engine_playbooks.RankingSignalService.build",
            return_value={"regions": {}},
        ), patch.object(
            self.service,
            "_derive_ranking_signal_context",
            return_value={"region_code": "SH", "score": 72.0},
        ), patch.object(
            self.service.product_catalog_service,
            "resolve_product_for_opportunity",
            return_value={
                "mapping_status": "approved",
                "recommended_product": "GeloProsed",
                "mapping_confidence": 0.91,
            },
        ), patch.object(
            self.service,
            "_build_channel_mix",
            return_value={"search": 100.0},
        ), patch.object(
            self.service,
            "_derive_activation_window",
            return_value={
                "start": "2026-04-11T00:00:00",
                "end": "2026-04-18T00:00:00",
            },
        ), patch.object(
            self.service,
            "_build_campaign_pack",
            return_value={},
        ), patch.object(
            self.service,
            "_enrich_opportunity_for_media",
            return_value=None,
        ), patch.object(
            self.service,
            "_campaign_preview_from_payload",
            return_value={"budget": {}},
        ), patch.object(
            self.service,
            "_parse_iso_datetime",
            return_value=None,
        ):
            result = self.service.generate_action_cards(
                brand="gelo",
                product="GeloProsed",
                campaign_goal="Awareness",
                weekly_budget=100000.0,
                strategy_mode="PLAYBOOK_AI",
                max_cards=4,
                virus_typ="Influenza A",
            )

        self.assertEqual(result["meta"]["strategy_mode"], "RULE_BASED_FALLBACK")
        self.assertEqual(result["cards"][0]["strategy_mode"], "RULE_BASED")

    def test_service_no_longer_exposes_legacy_action_card_wrapper(self) -> None:
        self.assertFalse(hasattr(MarketingOpportunityEngine, "_generate_legacy_action_cards"))


if __name__ == "__main__":
    unittest.main()
