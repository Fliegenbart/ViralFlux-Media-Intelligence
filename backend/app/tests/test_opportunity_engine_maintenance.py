from datetime import datetime, timezone
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
            "app.services.marketing_engine.opportunity_engine_maintenance.PeixEpiScoreService"
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
            product="Alle Gelo-Produkte",
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


if __name__ == "__main__":
    unittest.main()
