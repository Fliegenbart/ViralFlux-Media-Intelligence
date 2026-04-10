"""Produktkatalog + Auto/Review Mapping für Media-Empfehlungen."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime
from html import unescape
import hashlib
import logging
import re
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.models.database import BrandProduct, MarketingOpportunity, ProductConditionMapping
from app.services.media import product_catalog_admin
from app.services.media import product_catalog_matching
from app.services.media import product_catalog_serialization

logger = logging.getLogger(__name__)

DEFAULT_GELO_SOURCE_URL = "https://www.gelomyrtol-forte.de/gelo-produkte"


class ProductCatalogService:
    """Lädt Produktkataloge und verwaltet Lage-Mappings mit Review-Status."""

    def __init__(self, db: Session):
        self.db = db

    def refresh_brand_catalog(
        self,
        *,
        brand: str = "gelo",
        source_url: str = DEFAULT_GELO_SOURCE_URL,
        timeout_seconds: int = 20,
        overwrite_rules: bool = False,
    ) -> dict[str, Any]:
        """Manueller Refresh einer externen Produktseite."""
        brand_key = self._normalize_brand(brand)
        source_url = source_url.strip() or DEFAULT_GELO_SOURCE_URL

        try:
            response = requests.get(source_url, timeout=timeout_seconds)
            response.raise_for_status()
            html = response.text
        except requests.RequestException as exc:
            logger.error("Produktkatalog konnte nicht geladen werden: %s", exc)
            return {"error": f"Produktquelle nicht erreichbar: {exc}"}

        parsed_products = self._extract_products_from_html(html)
        if not parsed_products:
            return {"error": "Keine Produktkarten in der Quelle erkannt."}

        now = utc_now()
        existing_rows = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.brand == brand_key)
            .all()
        )
        existing_by_name = {
            self._normalize_name(row.product_name): row
            for row in existing_rows
        }

        added: list[str] = []
        updated: list[str] = []
        removed: list[str] = []
        mapping_candidates: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        for parsed in parsed_products:
            product_name = parsed["product_name"]
            normalized_name = self._normalize_name(product_name)
            source_hash = parsed["source_hash"]
            row = existing_by_name.get(normalized_name)
            was_new = row is None
            hash_changed = False

            if was_new:
                row = BrandProduct(
                    brand=brand_key,
                    product_name=product_name,
                    source_url=source_url,
                    source_hash=source_hash,
                    active=True,
                    last_seen_at=now,
                    extra_data={
                        "short_text": parsed.get("short_text"),
                        "subline": parsed.get("subline"),
                        "details_text": parsed.get("details_text"),
                    },
                )
                self.db.add(row)
                self.db.flush()
                existing_by_name[normalized_name] = row
                added.append(product_name)
            else:
                hash_changed = row.source_hash != source_hash
                if hash_changed or not row.active:
                    updated.append(product_name)
                row.source_url = source_url
                row.source_hash = source_hash
                row.active = True
                row.last_seen_at = now
                row.updated_at = now
                row.extra_data = {
                    "short_text": parsed.get("short_text"),
                    "subline": parsed.get("subline"),
                    "details_text": parsed.get("details_text"),
                }

            seen_ids.add(row.id)
            reset_approval = was_new or hash_changed or overwrite_rules
            candidates = self._upsert_auto_mappings(
                brand=brand_key,
                product=row,
                text_blob=parsed.get("text_blob", ""),
                reset_approval=reset_approval,
            )
            candidates.extend(
                self._upsert_hard_rule_mappings(
                    brand=brand_key,
                    product=row,
                )
            )
            for candidate in candidates:
                mapping_candidates.append(
                    {
                        "product_name": product_name,
                        "condition_key": candidate["condition_key"],
                        "condition_label": self.condition_label(candidate["condition_key"]),
                        "fit_score": candidate["fit_score"],
                        "mapping_reason": candidate["mapping_reason"],
                        "is_approved": candidate["is_approved"],
                        "priority": candidate["priority"],
                        "rule_source": candidate.get("rule_source", "auto"),
                    }
                )

        for row in existing_rows:
            is_manual_product = str(row.source_url or "").startswith("manual://")
            if row.id in seen_ids or not row.active or is_manual_product:
                continue
            row.active = False
            row.updated_at = now
            removed.append(row.product_name)

        self.db.commit()

        return {
            "brand": brand_key,
            "source_url": source_url,
            "added": sorted(added),
            "updated": sorted(updated),
            "removed": sorted(removed),
            "mapping_candidates": mapping_candidates,
            "run_timestamp": now.isoformat() + "Z",
            "counts": {
                "products_detected": len(parsed_products),
                "added": len(added),
                "updated": len(updated),
                "removed": len(removed),
                "mapping_candidates": len(mapping_candidates),
            },
        }

    def list_products(self, *, brand: str = "gelo") -> list[dict[str, Any]]:
        return product_catalog_admin.list_products(self, brand=brand)

    def create_product(
        self,
        *,
        brand: str,
        product_name: str,
        source_url: str | None = None,
        source_hash: str | None = None,
        active: bool = True,
        extra_data: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return product_catalog_admin.create_product(
            self,
            brand=brand,
            product_name=product_name,
            source_url=source_url,
            source_hash=source_hash,
            active=active,
            extra_data=extra_data,
            attributes=attributes,
        )

    def update_product(
        self,
        product_id: int,
        *,
        product_name: str | None = None,
        source_url: str | None = None,
        source_hash: str | None = None,
        active: bool | None = None,
        extra_data: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return product_catalog_admin.update_product(
            self,
            product_id,
            product_name=product_name,
            source_url=source_url,
            source_hash=source_hash,
            active=active,
            extra_data=extra_data,
            attributes=attributes,
        )

    def soft_delete_product(self, product_id: int) -> dict[str, Any] | None:
        return product_catalog_admin.soft_delete_product(self, product_id)

    def run_match_for_product(self, product_id: int) -> dict[str, Any] | None:
        return product_catalog_admin.run_match_for_product(self, product_id)

    def upsert_condition_link(
        self,
        product_id: int,
        *,
        condition_key: str,
        is_approved: bool = False,
        fit_score: float = 0.8,
        priority: int = 600,
        mapping_reason: str | None = None,
        notes: str | None = None,
        rule_source: str = "manual",
    ) -> dict[str, Any] | None:
        return product_catalog_admin.upsert_condition_link(
            self,
            product_id,
            condition_key=condition_key,
            is_approved=is_approved,
            fit_score=fit_score,
            priority=priority,
            mapping_reason=mapping_reason,
            notes=notes,
            rule_source=rule_source,
        )

    def preview_matches(
        self,
        *,
        brand: str = "gelo",
        opportunity_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return product_catalog_admin.preview_matches(
            self,
            brand=brand,
            opportunity_id=opportunity_id,
            limit=limit,
        )

    def list_mappings(
        self,
        *,
        brand: str = "gelo",
        include_inactive_products: bool = False,
        only_pending: bool = False,
    ) -> list[dict[str, Any]]:
        return product_catalog_admin.list_mappings(
            self,
            brand=brand,
            include_inactive_products=include_inactive_products,
            only_pending=only_pending,
        )

    def update_mapping(
        self,
        mapping_id: int,
        *,
        is_approved: bool | None = None,
        priority: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        return product_catalog_admin.update_mapping(
            self,
            mapping_id,
            is_approved=is_approved,
            priority=priority,
            notes=notes,
        )

    def seed_missing_products(self, *, brand: str = "gelo") -> dict[str, Any]:
        return product_catalog_admin.seed_missing_products(self, brand=brand)

    def resolve_product_for_opportunity(
        self,
        *,
        brand: str,
        opportunity: dict[str, Any],
        fallback_product: str | None = None,
    ) -> dict[str, Any]:
        return product_catalog_matching.resolve_product_for_opportunity(
            self,
            brand=brand,
            opportunity=opportunity,
            fallback_product=fallback_product,
        )

    def _preferred_hard_rule_mapping(
        self,
        *,
        brand_key: str,
        condition_key: str,
        pediatric_context: bool,
    ) -> dict[str, Any] | None:
        return product_catalog_matching._preferred_hard_rule_mapping(
            self,
            brand_key=brand_key,
            condition_key=condition_key,
            pediatric_context=pediatric_context,
        )

    def _is_pediatric_context(self, opportunity: dict[str, Any]) -> bool:
        return product_catalog_matching._is_pediatric_context(opportunity)

    def infer_condition_from_opportunity(self, opportunity: dict[str, Any]) -> str:
        return product_catalog_matching.infer_condition_from_opportunity(self, opportunity)

    @staticmethod
    def condition_label(condition_key: str | None) -> str:
        return product_catalog_matching.condition_label(condition_key)

    def _best_mapping(
        self,
        brand_key: str,
        condition_key: str,
        *,
        approved_only: bool,
    ) -> dict[str, Any] | None:
        return product_catalog_matching._best_mapping(
            self,
            brand_key,
            condition_key,
            approved_only=approved_only,
        )

    def _upsert_auto_mappings(
        self,
        *,
        brand: str,
        product: BrandProduct,
        text_blob: str,
        reset_approval: bool,
    ) -> list[dict[str, Any]]:
        return product_catalog_matching._upsert_auto_mappings(
            self,
            brand=brand,
            product=product,
            text_blob=text_blob,
            reset_approval=reset_approval,
        )

    def _upsert_hard_rule_mappings(
        self,
        *,
        brand: str,
        product: BrandProduct,
    ) -> list[dict[str, Any]]:
        return product_catalog_matching._upsert_hard_rule_mappings(
            self,
            brand=brand,
            product=product,
        )

    def _derive_condition_candidates(
        self,
        *,
        product_name: str,
        text_blob: str,
    ) -> list[dict[str, Any]]:
        return product_catalog_matching._derive_condition_candidates(
            self,
            product_name=product_name,
            text_blob=text_blob,
        )

    def _condition_scores(self, text: str) -> dict[str, dict[str, Any]]:
        return product_catalog_matching._condition_scores(text)

    def _get_product_by_id(self, product_id: int) -> BrandProduct | None:
        return (
            self.db.query(BrandProduct)
            .filter(BrandProduct.id == product_id)
            .first()
        )

    def _serialize_product(self, row: BrandProduct) -> dict[str, Any]:
        return product_catalog_serialization.serialize_product(self, row)

    def _serialize_product_mappings(self, product_id: int) -> list[dict[str, Any]]:
        rows = (
            self.db.query(ProductConditionMapping, BrandProduct)
            .join(BrandProduct, ProductConditionMapping.product_id == BrandProduct.id)
            .filter(ProductConditionMapping.product_id == product_id)
            .all()
        )
        return [
            self._serialize_mapping(mapping)
            for mapping, _ in rows
        ]

    def _serialize_mapping(self, mapping: ProductConditionMapping) -> dict[str, Any]:
        return product_catalog_serialization.serialize_mapping(self, mapping)

    def _extract_product_attributes(self, extra_data: dict[str, Any] | None) -> dict[str, Any]:
        return product_catalog_serialization.extract_product_attributes(self, extra_data)

    def _merge_product_extra_data(
        self,
        base: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return product_catalog_serialization.merge_product_extra_data(
            self,
            base=base,
            attributes=attributes,
            extra=extra,
        )

    def _to_str_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(part).strip() for part in value if str(part).strip()]
        return []

    def _to_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            raw = int(value)
        except (TypeError, ValueError):
            return None
        return raw if raw >= 0 else None

    def _build_product_text_blob(self, product: BrandProduct) -> str:
        return product_catalog_serialization.build_product_text_blob(self, product)

    def _default_source_hash(self, product_name: str, source_url: str, now: datetime) -> str:
        base = f"{self._normalize_name(product_name)}|{(source_url or '').strip().lower()}|{now.isoformat()}".encode("utf-8")
        return hashlib.sha256(base).hexdigest()

    def _opportunity_payload(self, row: MarketingOpportunity) -> dict[str, Any]:
        return product_catalog_serialization.opportunity_payload(row)

    def _extract_products_from_html(self, html: str) -> list[dict[str, Any]]:
        return product_catalog_serialization.extract_products_from_html(self, html)

    @staticmethod
    def _first_match(text: str, pattern: str) -> str:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else ""

    @staticmethod
    def _strip_html(raw: str) -> str:
        if not raw:
            return ""
        text = re.sub(r"<br\s*/?>", " ", raw, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = text.replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_product_name(value: str) -> str:
        cleaned = value.replace("®", "").replace("™", "").replace("️", "")
        cleaned = cleaned.replace("  ", " ")
        return cleaned.strip()

    @staticmethod
    def _normalize_name(value: str) -> str:
        base = ProductCatalogService._normalize_product_name(value or "")
        return re.sub(r"\s+", " ", base.lower()).strip()

    @staticmethod
    def _normalize_brand(brand: str | None) -> str:
        raw = (brand or "").strip().lower()
        if "gelo" in raw:
            return "gelo"
        return raw or "generic"
