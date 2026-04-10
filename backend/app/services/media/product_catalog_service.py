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
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.database import BrandProduct, MarketingOpportunity, ProductConditionMapping
from app.services.media import product_catalog_matching

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
        brand_key = self._normalize_brand(brand)
        rows = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.brand == brand_key)
            .order_by(BrandProduct.active.desc(), BrandProduct.product_name.asc())
            .all()
        )
        return [
            self._serialize_product(row)
            for row in rows
        ]

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
        brand_key = self._normalize_brand(brand)
        now = utc_now()
        normalized_name = self._normalize_name(product_name)
        existing = (
            self.db.query(BrandProduct)
            .filter(
                BrandProduct.brand == brand_key,
                func.lower(BrandProduct.product_name) == normalized_name,
            )
            .first()
        )
        if existing:
            raise ValueError("Produkt existiert bereits. Bitte bearbeiten statt neu anlegen.")

        normalized_source_url = (source_url or "manual://gelo-product-upload").strip()
        normalized_source_hash = source_hash or self._default_source_hash(
            product_name=product_name,
            source_url=normalized_source_url,
            now=now,
        )

        merged_extra = self._merge_product_extra_data(
            base=extra_data,
            attributes=attributes,
        )
        merged_extra.setdefault("created_via", "manual")

        row = BrandProduct(
            brand=brand_key,
            product_name=product_name.strip(),
            source_url=normalized_source_url,
            source_hash=normalized_source_hash,
            active=active,
            extra_data=merged_extra,
            last_seen_at=now,
        )
        self.db.add(row)
        self.db.flush()

        self._upsert_auto_mappings(
            brand=brand_key,
            product=row,
            text_blob=self._build_product_text_blob(row),
            reset_approval=True,
        )
        self._upsert_hard_rule_mappings(
            brand=brand_key,
            product=row,
        )
        self.db.commit()
        self.db.refresh(row)

        return self._serialize_product(row)

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
        row = self._get_product_by_id(product_id)
        if not row:
            return None

        now = utc_now()
        if product_name is not None:
            normalized_name = self._normalize_name(product_name)
            existing = (
                self.db.query(BrandProduct)
                .filter(
                    BrandProduct.brand == row.brand,
                    func.lower(BrandProduct.product_name) == normalized_name,
                    BrandProduct.id != row.id,
                )
                .first()
            )
            if existing:
                raise ValueError("Produktname bereits vorhanden.")
            row.product_name = product_name.strip()
            row.updated_at = now

        if source_url is not None:
            row.source_url = source_url.strip() or row.source_url
            row.updated_at = now

        if source_hash is not None:
            row.source_hash = source_hash.strip() or self._default_source_hash(
                product_name=row.product_name,
                source_url=row.source_url or "manual://gelo-product-upload",
                now=now,
            )
            row.updated_at = now

        if active is not None:
            row.active = bool(active)
            row.updated_at = now

        if extra_data is not None or attributes is not None:
            row.extra_data = self._merge_product_extra_data(
                base=row.extra_data,
                attributes=attributes,
                extra=extra_data,
            )
            row.updated_at = now

        self.db.commit()
        self.db.refresh(row)
        return self._serialize_product(row)

    def soft_delete_product(self, product_id: int) -> dict[str, Any] | None:
        row = self._get_product_by_id(product_id)
        if not row:
            return None

        row.active = False
        row.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(row)
        return self._serialize_product(row)

    def run_match_for_product(self, product_id: int) -> dict[str, Any] | None:
        row = self._get_product_by_id(product_id)
        if not row:
            return None

        self._upsert_auto_mappings(
            brand=row.brand,
            product=row,
            text_blob=self._build_product_text_blob(row),
            reset_approval=True,
        )
        self._upsert_hard_rule_mappings(
            brand=row.brand,
            product=row,
        )
        self.db.commit()
        self.db.refresh(row)

        mappings = self._serialize_product_mappings(row.id)
        return {
            "product": self._serialize_product(row),
            "product_id": row.id,
            "mapping_count": len(mappings),
            "mappings": mappings,
        }

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
        product = self._get_product_by_id(product_id)
        if not product:
            return None

        normalized_condition = condition_key.strip().lower().replace(" ", "_")
        if not normalized_condition:
            raise ValueError("condition_key ist leer.")

        row = (
            self.db.query(ProductConditionMapping)
            .filter(
                ProductConditionMapping.product_id == product.id,
                ProductConditionMapping.condition_key == normalized_condition,
            )
            .first()
        )

        now = utc_now()
        if row is None:
            row = ProductConditionMapping(
                brand=product.brand,
                product_id=product.id,
                condition_key=normalized_condition,
                rule_source=rule_source,
                fit_score=max(0.0, float(fit_score)),
                mapping_reason=(mapping_reason or "Manuelle Produkt-Lage-Verknuepfung."),
                is_approved=bool(is_approved),
                priority=int(priority or 0),
                notes=(notes or "").strip() or None,
                updated_at=now,
            )
            self.db.add(row)
        else:
            if (row.rule_source or "auto") != "hard_rule":
                row.rule_source = rule_source
            if mapping_reason is not None:
                row.mapping_reason = mapping_reason
            if notes is not None:
                row.notes = notes.strip() or None
            row.fit_score = max(0.0, float(fit_score))
            row.priority = int(priority or 0)
            row.is_approved = bool(is_approved)
            row.updated_at = now

        self.db.commit()
        self.db.refresh(row)
        return self._serialize_mapping(row)

    def preview_matches(
        self,
        *,
        brand: str = "gelo",
        opportunity_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        brand_key = self._normalize_brand(brand)
        query = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.created_at.desc()
        )
        if opportunity_id:
            query = query.filter(MarketingOpportunity.opportunity_id == opportunity_id)
        if brand_key:
            if brand_key == "gelo":
                query = query.filter(func.lower(MarketingOpportunity.brand).like("%gelo%"))
            else:
                query = query.filter(func.lower(MarketingOpportunity.brand) == brand_key)

        rows = query.limit(max(1, min(100, limit))).all()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            opportunity = self._opportunity_payload(row)
            mapping = self.resolve_product_for_opportunity(
                brand=brand_key,
                opportunity=opportunity,
                fallback_product=row.product,
            )
            candidates.append(
                {
                    "opportunity_id": row.opportunity_id,
                    "opportunity_type": row.opportunity_type,
                    "status": row.status,
                    "region_target": row.region_target,
                    "urgency_score": row.urgency_score,
                    "trigger_event": row.trigger_event,
                    "candidate_product": mapping.get("candidate_product"),
                    "recommended_product": mapping.get("recommended_product"),
                    "mapping_status": mapping.get("mapping_status"),
                    "mapping_confidence": mapping.get("mapping_confidence"),
                    "mapping_reason": mapping.get("mapping_reason"),
                    "condition_key": mapping.get("condition_key"),
                    "condition_label": mapping.get("condition_label"),
                    "rule_source": mapping.get("rule_source"),
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
            )

        if opportunity_id and not candidates:
            raise ValueError("Opportunity nicht gefunden.")

        return {
            "brand": brand_key,
            "total": len(candidates),
            "items": candidates,
        }

    def list_mappings(
        self,
        *,
        brand: str = "gelo",
        include_inactive_products: bool = False,
        only_pending: bool = False,
    ) -> list[dict[str, Any]]:
        brand_key = self._normalize_brand(brand)
        query = (
            self.db.query(ProductConditionMapping, BrandProduct)
            .join(BrandProduct, ProductConditionMapping.product_id == BrandProduct.id)
            .filter(ProductConditionMapping.brand == brand_key)
        )

        if not include_inactive_products:
            query = query.filter(BrandProduct.active.is_(True))
        if only_pending:
            query = query.filter(ProductConditionMapping.is_approved.is_(False))

        rows = (
            query.order_by(
                ProductConditionMapping.condition_key.asc(),
                case((ProductConditionMapping.rule_source == "hard_rule", 1), else_=0).desc(),
                ProductConditionMapping.fit_score.desc(),
                ProductConditionMapping.priority.desc(),
                BrandProduct.product_name.asc(),
            )
            .all()
        )

        return [
            {
                "mapping_id": mapping.id,
                "brand": mapping.brand,
                "product_id": product.id,
                "product_name": product.product_name,
                "product_active": bool(product.active),
                "condition_key": mapping.condition_key,
                "condition_label": self.condition_label(mapping.condition_key),
                "rule_source": mapping.rule_source or "auto",
                "fit_score": round(float(mapping.fit_score or 0.0), 3),
                "mapping_reason": mapping.mapping_reason,
                "is_approved": bool(mapping.is_approved),
                "priority": int(mapping.priority or 0),
                "notes": mapping.notes,
                "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
            }
            for mapping, product in rows
        ]

    def update_mapping(
        self,
        mapping_id: int,
        *,
        is_approved: bool | None = None,
        priority: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        mapping = (
            self.db.query(ProductConditionMapping)
            .filter(ProductConditionMapping.id == mapping_id)
            .first()
        )
        if not mapping:
            return None

        if is_approved is not None:
            mapping.is_approved = bool(is_approved)
        if priority is not None:
            mapping.priority = int(priority)
        if notes is not None:
            cleaned = notes.strip()
            mapping.notes = cleaned or None

        mapping.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(mapping)

        product = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.id == mapping.product_id)
            .first()
        )

        return {
            "mapping_id": mapping.id,
            "brand": mapping.brand,
            "product_id": mapping.product_id,
            "product_name": product.product_name if product else None,
            "condition_key": mapping.condition_key,
            "condition_label": self.condition_label(mapping.condition_key),
            "rule_source": mapping.rule_source or "auto",
            "fit_score": round(float(mapping.fit_score or 0.0), 3),
            "mapping_reason": mapping.mapping_reason,
            "is_approved": bool(mapping.is_approved),
            "priority": int(mapping.priority or 0),
            "notes": mapping.notes,
            "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
        }

    def seed_missing_products(self, *, brand: str = "gelo") -> dict[str, Any]:
        """Fehlende SEED_PRODUCTS als BrandProduct + Mappings anlegen."""
        from app.services.marketing_engine.product_matcher import SEED_PRODUCTS

        brand_key = self._normalize_brand(brand)
        now = utc_now()

        existing_names = {
            row.product_name.strip().lower()
            for row in self.db.query(BrandProduct).filter(BrandProduct.brand == brand_key).all()
        }

        added_products: list[str] = []
        added_mappings = 0

        for seed in SEED_PRODUCTS:
            name = seed["name"]
            if name.strip().lower() in existing_names:
                continue

            product = BrandProduct(
                brand=brand_key,
                product_name=name,
                source_url="seed://gelo-katalog",
                source_hash=f"seed-{seed['sku']}-{now.isoformat()}",
                active=True,
                extra_data={"sku": seed["sku"], "category": seed.get("category")},
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            self.db.add(product)
            self.db.flush()

            for condition_key in seed.get("applicable_conditions", []):
                existing_mapping = (
                    self.db.query(ProductConditionMapping)
                    .filter(
                        ProductConditionMapping.product_id == product.id,
                        ProductConditionMapping.condition_key == condition_key,
                    )
                    .first()
                )
                if existing_mapping:
                    continue
                self.db.add(ProductConditionMapping(
                    brand=brand_key,
                    product_id=product.id,
                    condition_key=condition_key,
                    rule_source="seed_catalog",
                    fit_score=0.85,
                    mapping_reason=f"Seed-Katalog: {name} → {condition_key}",
                    is_approved=False,
                    priority=500,
                    updated_at=now,
                ))
                added_mappings += 1

            added_products.append(name)

        if added_products:
            self.db.commit()

        return {
            "added_products": added_products,
            "added_mappings": added_mappings,
            "total_seed_products": len(SEED_PRODUCTS),
            "already_existed": len(SEED_PRODUCTS) - len(added_products),
        }

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
        attrs = self._extract_product_attributes(row.extra_data)
        last_seen = row.last_seen_at.isoformat() if row.last_seen_at else None
        updated = row.updated_at.isoformat() if row.updated_at else None

        mappings = (
            self.db.query(ProductConditionMapping)
            .filter(ProductConditionMapping.product_id == row.id)
            .order_by(ProductConditionMapping.updated_at.desc())
            .all()
        )
        review_state = "unreviewed"
        if mappings:
            any_pending = any(not mapping.is_approved for mapping in mappings)
            review_state = "needs_review" if any_pending else "approved"

        latest_mapping_change = None
        for mapping in mappings:
            if mapping.updated_at:
                latest_mapping_change = mapping.updated_at.isoformat()
                break

        return {
            "id": row.id,
            "brand": row.brand,
            "product_name": row.product_name,
            "active": bool(row.active),
            "source_url": row.source_url,
            "source_hash": row.source_hash,
            "last_seen_at": last_seen,
            "updated_at": updated,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "sku": attrs.get("sku"),
            "target_segments": attrs.get("target_segments", []),
            "conditions": attrs.get("conditions", []),
            "forms": attrs.get("forms", []),
            "age_min_months": attrs.get("age_min_months"),
            "age_max_months": attrs.get("age_max_months"),
            "audience_mode": attrs.get("audience_mode"),
            "channel_fit": attrs.get("channel_fit", []),
            "compliance_notes": attrs.get("compliance_notes"),
            "review_state": review_state,
            "last_change": latest_mapping_change or updated,
        }

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
        product = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.id == mapping.product_id)
            .first()
        )

        return {
            "mapping_id": mapping.id,
            "brand": mapping.brand,
            "product_id": mapping.product_id,
            "product_name": product.product_name if product else None,
            "product_active": bool(product.active) if product is not None else None,
            "condition_key": mapping.condition_key,
            "condition_label": self.condition_label(mapping.condition_key),
            "rule_source": mapping.rule_source or "auto",
            "fit_score": round(float(mapping.fit_score or 0.0), 3),
            "mapping_reason": mapping.mapping_reason,
            "is_approved": bool(mapping.is_approved),
            "priority": int(mapping.priority or 0),
            "notes": mapping.notes,
            "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
        }

    def _extract_product_attributes(self, extra_data: dict[str, Any] | None) -> dict[str, Any]:
        base: dict[str, Any] = {}
        if isinstance(extra_data, dict):
            base.update(extra_data)

        return {
            "sku": str(base.get("sku")).strip() if base.get("sku") else None,
            "target_segments": self._to_str_list(base.get("target_segments")),
            "conditions": self._to_str_list(base.get("conditions")),
            "forms": self._to_str_list(base.get("forms")),
            "age_min_months": self._to_int(base.get("age_min_months")),
            "age_max_months": self._to_int(base.get("age_max_months")),
            "audience_mode": str(base.get("audience_mode") or "b2c").strip() or "b2c",
            "channel_fit": self._to_str_list(base.get("channel_fit")),
            "compliance_notes": str(base.get("compliance_notes") or "").strip() or None,
        }

    def _merge_product_extra_data(
        self,
        base: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = {}
        if isinstance(base, dict):
            merged.update(base)
        if isinstance(extra, dict):
            merged.update(extra)

        if isinstance(attributes, dict):
            if "sku" in attributes:
                merged["sku"] = attributes.get("sku")
            if "target_segments" in attributes:
                merged["target_segments"] = self._to_str_list(attributes.get("target_segments"))
            if "conditions" in attributes:
                merged["conditions"] = self._to_str_list(attributes.get("conditions"))
            if "forms" in attributes:
                merged["forms"] = self._to_str_list(attributes.get("forms"))
            if "age_min_months" in attributes:
                merged["age_min_months"] = self._to_int(attributes.get("age_min_months"))
            if "age_max_months" in attributes:
                merged["age_max_months"] = self._to_int(attributes.get("age_max_months"))
            if "audience_mode" in attributes:
                merged["audience_mode"] = str(attributes.get("audience_mode") or "b2c").strip() or "b2c"
            if "channel_fit" in attributes:
                merged["channel_fit"] = self._to_str_list(attributes.get("channel_fit"))
            if "compliance_notes" in attributes:
                merged["compliance_notes"] = str(attributes.get("compliance_notes") or "").strip() or None
        return merged

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
        attrs = self._extract_product_attributes(product.extra_data)
        parts = [product.product_name]
        for key in ("short_text", "subline", "details_text"):
            val = ""
            if isinstance(product.extra_data, dict):
                val = str(product.extra_data.get(key) or "")
            if val:
                parts.append(val)
        parts.extend(attrs.get("target_segments", []) or [])
        parts.extend(attrs.get("conditions", []) or [])
        parts.extend(attrs.get("forms", []) or [])
        if attrs.get("compliance_notes"):
            parts.append(str(attrs.get("compliance_notes")))
        return " ".join(p.strip() for p in parts if p).strip()

    def _default_source_hash(self, product_name: str, source_url: str, now: datetime) -> str:
        base = f"{self._normalize_name(product_name)}|{(source_url or '').strip().lower()}|{now.isoformat()}".encode("utf-8")
        return hashlib.sha256(base).hexdigest()

    def _opportunity_payload(self, row: MarketingOpportunity) -> dict[str, Any]:
        trigger_details = row.trigger_details or {}
        return {
            "id": row.opportunity_id,
            "type": row.opportunity_type,
            "status": row.status,
            "urgency_score": row.urgency_score,
            "region_target": row.region_target or {},
            "target_audience": row.target_audience or [],
            "trigger_context": {
                "source": row.trigger_source or "",
                "event": row.trigger_event or "",
                "details": str(trigger_details.get("details") or trigger_details.get("event") or ""),
                "detected_at": row.trigger_detected_at.isoformat() if row.trigger_detected_at else None,
            },
            "recommendation_reason": row.recommendation_reason or "",
        }

    def _extract_products_from_html(self, html: str) -> list[dict[str, Any]]:
        chunks = re.split(r'(?=<div class="product product--)', html)
        products: list[dict[str, Any]] = []
        seen: set[str] = set()

        for chunk in chunks:
            if not chunk.startswith('<div class="product product--'):
                continue

            name_html = self._first_match(chunk, r'<h2 class="product__name">\s*(.*?)\s*</h2>')
            product_name = self._normalize_product_name(self._strip_html(name_html))
            if not product_name:
                continue
            normalized = self._normalize_name(product_name)
            if normalized in seen:
                continue
            seen.add(normalized)

            short_text_html = self._first_match(chunk, r'<div class="product__short-text">\s*(.*?)\s*</div>')
            subline_html = self._first_match(chunk, r'<div class="product__subline">\s*(.*?)\s*</div>')
            details_html = self._first_match(chunk, r'<div class="product__more-content">\s*(.*?)\s*</div>')

            short_text = self._strip_html(short_text_html)
            subline = self._strip_html(subline_html)
            details_text = self._strip_html(details_html)

            text_blob = " ".join(
                part for part in [product_name, subline, short_text, details_text] if part
            ).strip()
            source_hash = hashlib.sha256(text_blob.lower().encode("utf-8")).hexdigest()

            products.append(
                {
                    "product_name": product_name,
                    "short_text": short_text,
                    "subline": subline,
                    "details_text": details_text,
                    "text_blob": text_blob,
                    "source_hash": source_hash,
                }
            )

        return products

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
