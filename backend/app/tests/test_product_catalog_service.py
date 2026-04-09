from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, BrandProduct, ProductConditionMapping
from app.services.media.product_catalog_service import ProductCatalogService


class ProductCatalogServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = ProductCatalogService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    @patch("app.services.media.product_catalog_matching.resolve_product_for_opportunity")
    def test_resolve_product_for_opportunity_delegates_to_matching_module(self, resolve_mock) -> None:
        resolve_mock.return_value = {"mapping_status": "approved"}

        result = self.service.resolve_product_for_opportunity(
            brand="gelo",
            opportunity={"type": "RESOURCE_SCARCITY"},
            fallback_product="GeloMyrtol forte",
        )

        self.assertEqual(result, {"mapping_status": "approved"})
        resolve_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            opportunity={"type": "RESOURCE_SCARCITY"},
            fallback_product="GeloMyrtol forte",
        )

    @patch("app.services.media.product_catalog_matching._upsert_auto_mappings")
    def test_upsert_auto_mappings_delegates_to_matching_module(self, upsert_mock) -> None:
        product = BrandProduct(
            brand="gelo",
            product_name="GeloMyrtol forte",
            source_url="https://example.test/gelo",
            source_hash="hash-1",
            active=True,
        )
        self.db.add(product)
        self.db.commit()

        upsert_mock.return_value = [{"condition_key": "bronchitis_husten"}]

        result = self.service._upsert_auto_mappings(
            brand="gelo",
            product=product,
            text_blob="Husten und Bronchien",
            reset_approval=True,
        )

        self.assertEqual(result, [{"condition_key": "bronchitis_husten"}])
        upsert_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            product=product,
            text_blob="Husten und Bronchien",
            reset_approval=True,
        )

    def test_resolve_product_for_opportunity_prefers_approved_gelo_mapping(self) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        product = BrandProduct(
            brand="gelo",
            product_name="GeloMyrtol forte",
            source_url="https://example.test/gelo",
            source_hash="hash-2",
            active=True,
            last_seen_at=now,
            updated_at=now,
        )
        self.db.add(product)
        self.db.flush()
        self.db.add(
            ProductConditionMapping(
                brand="gelo",
                product_id=product.id,
                condition_key="bronchitis_husten",
                rule_source="auto",
                fit_score=0.93,
                mapping_reason="Freigegebenes Mapping für Husten.",
                is_approved=True,
                priority=93,
                updated_at=now,
            )
        )
        self.db.commit()

        result = self.service.resolve_product_for_opportunity(
            brand="gelo",
            opportunity={
                "type": "RESOURCE_SCARCITY",
                "trigger_context": {"event": "Hustenlage", "details": "Bronchien und Husten"},
            },
        )

        self.assertEqual(result["mapping_status"], "approved")
        self.assertEqual(result["recommended_product"], "GeloMyrtol forte")
        self.assertEqual(result["condition_key"], "bronchitis_husten")
        self.assertEqual(result["rule_source"], "auto")

    def test_resolve_product_for_opportunity_respects_service_override(self) -> None:
        class OverrideCatalogService(ProductCatalogService):
            def _best_mapping(self, brand_key: str, condition_key: str, *, approved_only: bool):
                if approved_only:
                    return {
                        "product_name": "Override Produkt",
                        "fit_score": 0.77,
                        "mapping_reason": "Override aktiv.",
                        "is_approved": True,
                        "priority": 777,
                        "rule_source": "override",
                    }
                return None

        service = OverrideCatalogService(self.db)

        result = service.resolve_product_for_opportunity(
            brand="gelo",
            opportunity={"type": "RESOURCE_SCARCITY"},
        )

        self.assertEqual(result["mapping_status"], "approved")
        self.assertEqual(result["recommended_product"], "Override Produkt")
        self.assertEqual(result["mapping_reason"], "Override aktiv.")
        self.assertEqual(result["rule_source"], "override")

    def test_upsert_auto_mappings_respects_service_override_for_candidates(self) -> None:
        class OverrideCatalogService(ProductCatalogService):
            def _derive_condition_candidates(self, *, product_name: str, text_blob: str):
                return [
                    {
                        "condition_key": "halsschmerz_heiserkeit",
                        "fit_score": 0.88,
                        "mapping_reason": "Override Kandidat.",
                        "priority": 88,
                    }
                ]

        service = OverrideCatalogService(self.db)
        product = BrandProduct(
            brand="gelo",
            product_name="Beliebiges Produkt",
            source_url="https://example.test/gelo",
            source_hash="hash-3",
            active=True,
        )
        self.db.add(product)
        self.db.commit()

        result = service._upsert_auto_mappings(
            brand="gelo",
            product=product,
            text_blob="Text ohne Standardsignal",
            reset_approval=True,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["condition_key"], "halsschmerz_heiserkeit")
        self.assertEqual(result[0]["mapping_reason"], "Override Kandidat.")

    def test_infer_condition_from_opportunity_respects_service_override_for_scores(self) -> None:
        class OverrideCatalogService(ProductCatalogService):
            def _condition_scores(self, text: str):
                return {
                    "immun_support": {"score": 9.0, "hits": ["override"]},
                    "bronchitis_husten": {"score": 1.0, "hits": ["fallback"]},
                }

        service = OverrideCatalogService(self.db)

        result = service.infer_condition_from_opportunity(
            {
                "type": "RESOURCE_SCARCITY",
                "trigger_context": {"event": "Husten", "details": "Normal wäre anders"},
            }
        )

        self.assertEqual(result, "immun_support")

    def test_upsert_hard_rule_mappings_respects_service_override_for_condition_label(self) -> None:
        class OverrideCatalogService(ProductCatalogService):
            @staticmethod
            def condition_label(condition_key: str | None) -> str:
                return f"Override Label {condition_key}"

        service = OverrideCatalogService(self.db)
        product = BrandProduct(
            brand="gelo",
            product_name="GeloVital",
            source_url="https://example.test/gelo",
            source_hash="hash-4",
            active=True,
        )
        self.db.add(product)
        self.db.commit()

        result = service._upsert_hard_rule_mappings(
            brand="gelo",
            product=product,
        )

        self.assertEqual(len(result), 1)
        self.assertIn("Override Label immun_support", result[0]["mapping_reason"])


if __name__ == "__main__":
    unittest.main()
