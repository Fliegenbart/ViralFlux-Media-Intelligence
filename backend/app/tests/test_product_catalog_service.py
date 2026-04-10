from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, BrandProduct, MarketingOpportunity, ProductConditionMapping
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

    @patch("app.services.media.product_catalog_serialization.serialize_product")
    def test_serialize_product_delegates_to_serialization_module(self, serialize_mock) -> None:
        product = BrandProduct(
            brand="gelo",
            product_name="GeloMyrtol forte",
            source_url="https://example.test/gelo",
            source_hash="hash-5",
            active=True,
        )
        expected = {"product_name": "patched"}
        serialize_mock.return_value = expected

        payload = self.service._serialize_product(product)

        self.assertIs(payload, expected)
        serialize_mock.assert_called_once_with(self.service, product)

    @patch("app.services.media.product_catalog_serialization.serialize_mapping")
    def test_serialize_mapping_delegates_to_serialization_module(self, serialize_mock) -> None:
        mapping = ProductConditionMapping(
            brand="gelo",
            product_id=1,
            condition_key="bronchitis_husten",
            rule_source="auto",
            fit_score=0.9,
            mapping_reason="Patched",
            is_approved=True,
            priority=90,
        )
        expected = {"mapping_id": 123}
        serialize_mock.return_value = expected

        payload = self.service._serialize_mapping(mapping)

        self.assertIs(payload, expected)
        serialize_mock.assert_called_once_with(self.service, mapping)

    @patch("app.services.media.product_catalog_serialization.extract_product_attributes")
    def test_extract_product_attributes_delegates_to_serialization_module(self, extract_mock) -> None:
        expected = {"sku": "patched"}
        extract_mock.return_value = expected

        payload = self.service._extract_product_attributes({"sku": "ABC"})

        self.assertIs(payload, expected)
        extract_mock.assert_called_once_with(self.service, {"sku": "ABC"})

    @patch("app.services.media.product_catalog_serialization.merge_product_extra_data")
    def test_merge_product_extra_data_delegates_to_serialization_module(self, merge_mock) -> None:
        expected = {"sku": "merged"}
        merge_mock.return_value = expected

        payload = self.service._merge_product_extra_data(
            base={"a": 1},
            attributes={"sku": "ABC"},
            extra={"b": 2},
        )

        self.assertIs(payload, expected)
        merge_mock.assert_called_once_with(
            self.service,
            base={"a": 1},
            attributes={"sku": "ABC"},
            extra={"b": 2},
        )

    @patch("app.services.media.product_catalog_serialization.build_product_text_blob")
    def test_build_product_text_blob_delegates_to_serialization_module(self, blob_mock) -> None:
        product = BrandProduct(
            brand="gelo",
            product_name="GeloProsed",
            source_url="https://example.test/gelo",
            source_hash="hash-6",
            active=True,
        )
        blob_mock.return_value = "patched text"

        payload = self.service._build_product_text_blob(product)

        self.assertEqual(payload, "patched text")
        blob_mock.assert_called_once_with(self.service, product)

    @patch("app.services.media.product_catalog_serialization.opportunity_payload")
    def test_opportunity_payload_delegates_to_serialization_module(self, payload_mock) -> None:
        row = MarketingOpportunity(opportunity_id="opp-1")
        expected = {"id": "patched"}
        payload_mock.return_value = expected

        payload = self.service._opportunity_payload(row)

        self.assertIs(payload, expected)
        payload_mock.assert_called_once_with(row)

    @patch("app.services.media.product_catalog_serialization.extract_products_from_html")
    def test_extract_products_from_html_delegates_to_serialization_module(self, extract_mock) -> None:
        expected = [{"product_name": "patched"}]
        extract_mock.return_value = expected

        payload = self.service._extract_products_from_html("<html></html>")

        self.assertIs(payload, expected)
        extract_mock.assert_called_once_with(self.service, "<html></html>")

    @patch("app.services.media.product_catalog_admin.list_products")
    def test_list_products_delegates_to_admin_module(self, list_mock) -> None:
        expected = [{"product_name": "patched"}]
        list_mock.return_value = expected

        payload = self.service.list_products(brand="gelo")

        self.assertIs(payload, expected)
        list_mock.assert_called_once_with(self.service, brand="gelo")

    @patch("app.services.media.product_catalog_admin.create_product")
    def test_create_product_delegates_to_admin_module(self, create_mock) -> None:
        expected = {"product_name": "patched"}
        create_mock.return_value = expected

        payload = self.service.create_product(
            brand="gelo",
            product_name="GeloTest",
            source_url="https://example.test/gelo",
        )

        self.assertIs(payload, expected)
        create_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            product_name="GeloTest",
            source_url="https://example.test/gelo",
            source_hash=None,
            active=True,
            extra_data=None,
            attributes=None,
        )

    @patch("app.services.media.product_catalog_admin.update_product")
    def test_update_product_delegates_to_admin_module(self, update_mock) -> None:
        expected = {"product_name": "patched"}
        update_mock.return_value = expected

        payload = self.service.update_product(7, product_name="Neu")

        self.assertIs(payload, expected)
        update_mock.assert_called_once_with(
            self.service,
            7,
            product_name="Neu",
            source_url=None,
            source_hash=None,
            active=None,
            extra_data=None,
            attributes=None,
        )

    @patch("app.services.media.product_catalog_admin.soft_delete_product")
    def test_soft_delete_product_delegates_to_admin_module(self, delete_mock) -> None:
        expected = {"active": False}
        delete_mock.return_value = expected

        payload = self.service.soft_delete_product(9)

        self.assertIs(payload, expected)
        delete_mock.assert_called_once_with(self.service, 9)

    @patch("app.services.media.product_catalog_admin.run_match_for_product")
    def test_run_match_for_product_delegates_to_admin_module(self, run_mock) -> None:
        expected = {"mapping_count": 2}
        run_mock.return_value = expected

        payload = self.service.run_match_for_product(11)

        self.assertIs(payload, expected)
        run_mock.assert_called_once_with(self.service, 11)

    @patch("app.services.media.product_catalog_admin.upsert_condition_link")
    def test_upsert_condition_link_delegates_to_admin_module(self, link_mock) -> None:
        expected = {"mapping_id": 5}
        link_mock.return_value = expected

        payload = self.service.upsert_condition_link(
            3,
            condition_key="bronchitis_husten",
            is_approved=True,
        )

        self.assertIs(payload, expected)
        link_mock.assert_called_once_with(
            self.service,
            3,
            condition_key="bronchitis_husten",
            is_approved=True,
            fit_score=0.8,
            priority=600,
            mapping_reason=None,
            notes=None,
            rule_source="manual",
        )

    @patch("app.services.media.product_catalog_admin.preview_matches")
    def test_preview_matches_delegates_to_admin_module(self, preview_mock) -> None:
        expected = {"total": 1}
        preview_mock.return_value = expected

        payload = self.service.preview_matches(brand="gelo", opportunity_id="opp-1", limit=5)

        self.assertIs(payload, expected)
        preview_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            opportunity_id="opp-1",
            limit=5,
        )

    @patch("app.services.media.product_catalog_admin.list_mappings")
    def test_list_mappings_delegates_to_admin_module(self, list_mock) -> None:
        expected = [{"mapping_id": 1}]
        list_mock.return_value = expected

        payload = self.service.list_mappings(brand="gelo", include_inactive_products=True, only_pending=True)

        self.assertIs(payload, expected)
        list_mock.assert_called_once_with(
            self.service,
            brand="gelo",
            include_inactive_products=True,
            only_pending=True,
        )

    @patch("app.services.media.product_catalog_admin.update_mapping")
    def test_update_mapping_delegates_to_admin_module(self, update_mock) -> None:
        expected = {"mapping_id": 8}
        update_mock.return_value = expected

        payload = self.service.update_mapping(8, is_approved=True, priority=900, notes="ok")

        self.assertIs(payload, expected)
        update_mock.assert_called_once_with(
            self.service,
            8,
            is_approved=True,
            priority=900,
            notes="ok",
        )

    @patch("app.services.media.product_catalog_admin.seed_missing_products")
    def test_seed_missing_products_delegates_to_admin_module(self, seed_mock) -> None:
        expected = {"added_products": ["patched"]}
        seed_mock.return_value = expected

        payload = self.service.seed_missing_products(brand="gelo")

        self.assertIs(payload, expected)
        seed_mock.assert_called_once_with(self.service, brand="gelo")


if __name__ == "__main__":
    unittest.main()
