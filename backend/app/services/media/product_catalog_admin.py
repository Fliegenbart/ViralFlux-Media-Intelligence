"""Administrative product and mapping operations for the product catalog service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func

from app.core.time import utc_now
from app.models.database import BrandProduct, MarketingOpportunity, ProductConditionMapping


def list_products(service, *, brand: str) -> list[dict[str, Any]]:
    brand_key = service._normalize_brand(brand)
    rows = (
        service.db.query(BrandProduct)
        .filter(BrandProduct.brand == brand_key)
        .order_by(BrandProduct.active.desc(), BrandProduct.product_name.asc())
        .all()
    )
    return [
        service._serialize_product(row)
        for row in rows
    ]


def create_product(
    service,
    *,
    brand: str,
    product_name: str,
    source_url: str | None = None,
    source_hash: str | None = None,
    active: bool = True,
    extra_data: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    brand_key = service._normalize_brand(brand)
    now = utc_now()
    normalized_name = service._normalize_name(product_name)
    existing = (
        service.db.query(BrandProduct)
        .filter(
            BrandProduct.brand == brand_key,
            func.lower(BrandProduct.product_name) == normalized_name,
        )
        .first()
    )
    if existing:
        raise ValueError("Produkt existiert bereits. Bitte bearbeiten statt neu anlegen.")

    normalized_source_url = (source_url or f"manual://product-upload/{brand_key}").strip()
    normalized_source_hash = source_hash or service._default_source_hash(
        product_name=product_name,
        source_url=normalized_source_url,
        now=now,
    )

    merged_extra = service._merge_product_extra_data(
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
    service.db.add(row)
    service.db.flush()

    service._upsert_auto_mappings(
        brand=brand_key,
        product=row,
        text_blob=service._build_product_text_blob(row),
        reset_approval=True,
    )
    service._upsert_hard_rule_mappings(
        brand=brand_key,
        product=row,
    )
    service.db.commit()
    service.db.refresh(row)

    return service._serialize_product(row)


def update_product(
    service,
    product_id: int,
    *,
    product_name: str | None = None,
    source_url: str | None = None,
    source_hash: str | None = None,
    active: bool | None = None,
    extra_data: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = service._get_product_by_id(product_id)
    if not row:
        return None

    now = utc_now()
    if product_name is not None:
        normalized_name = service._normalize_name(product_name)
        existing = (
            service.db.query(BrandProduct)
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
        row.source_hash = source_hash.strip() or service._default_source_hash(
            product_name=row.product_name,
            source_url=row.source_url or f"manual://product-upload/{row.brand}",
            now=now,
        )
        row.updated_at = now

    if active is not None:
        row.active = bool(active)
        row.updated_at = now

    if extra_data is not None or attributes is not None:
        row.extra_data = service._merge_product_extra_data(
            base=row.extra_data,
            attributes=attributes,
            extra=extra_data,
        )
        row.updated_at = now

    service.db.commit()
    service.db.refresh(row)
    return service._serialize_product(row)


def soft_delete_product(service, product_id: int) -> dict[str, Any] | None:
    row = service._get_product_by_id(product_id)
    if not row:
        return None

    row.active = False
    row.updated_at = utc_now()
    service.db.commit()
    service.db.refresh(row)
    return service._serialize_product(row)


def run_match_for_product(service, product_id: int) -> dict[str, Any] | None:
    row = service._get_product_by_id(product_id)
    if not row:
        return None

    service._upsert_auto_mappings(
        brand=row.brand,
        product=row,
        text_blob=service._build_product_text_blob(row),
        reset_approval=True,
    )
    service._upsert_hard_rule_mappings(
        brand=row.brand,
        product=row,
    )
    service.db.commit()
    service.db.refresh(row)

    mappings = service._serialize_product_mappings(row.id)
    return {
        "product": service._serialize_product(row),
        "product_id": row.id,
        "mapping_count": len(mappings),
        "mappings": mappings,
    }


def upsert_condition_link(
    service,
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
    product = service._get_product_by_id(product_id)
    if not product:
        return None

    normalized_condition = condition_key.strip().lower().replace(" ", "_")
    if not normalized_condition:
        raise ValueError("condition_key ist leer.")

    row = (
        service.db.query(ProductConditionMapping)
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
        service.db.add(row)
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

    service.db.commit()
    service.db.refresh(row)
    return service._serialize_mapping(row)


def preview_matches(
    service,
    *,
    brand: str,
    opportunity_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    brand_key = service._normalize_brand(brand)
    query = service.db.query(MarketingOpportunity).order_by(
        MarketingOpportunity.created_at.desc()
    )
    if opportunity_id:
        query = query.filter(MarketingOpportunity.opportunity_id == opportunity_id)
    if brand_key:
        query = query.filter(func.lower(MarketingOpportunity.brand) == brand_key)

    rows = query.limit(max(1, min(100, limit))).all()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        opportunity = service._opportunity_payload(row)
        mapping = service.resolve_product_for_opportunity(
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
    service,
    *,
    brand: str,
    include_inactive_products: bool = False,
    only_pending: bool = False,
) -> list[dict[str, Any]]:
    brand_key = service._normalize_brand(brand)
    query = (
        service.db.query(ProductConditionMapping, BrandProduct)
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
            "condition_label": service.condition_label(mapping.condition_key),
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
    service,
    mapping_id: int,
    *,
    is_approved: bool | None = None,
    priority: int | None = None,
    notes: str | None = None,
) -> dict[str, Any] | None:
    mapping = (
        service.db.query(ProductConditionMapping)
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
    service.db.commit()
    service.db.refresh(mapping)

    product = (
        service.db.query(BrandProduct)
        .filter(BrandProduct.id == mapping.product_id)
        .first()
    )

    return {
        "mapping_id": mapping.id,
        "brand": mapping.brand,
        "product_id": mapping.product_id,
        "product_name": product.product_name if product else None,
        "condition_key": mapping.condition_key,
        "condition_label": service.condition_label(mapping.condition_key),
        "rule_source": mapping.rule_source or "auto",
        "fit_score": round(float(mapping.fit_score or 0.0), 3),
        "mapping_reason": mapping.mapping_reason,
        "is_approved": bool(mapping.is_approved),
        "priority": int(mapping.priority or 0),
        "notes": mapping.notes,
        "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
    }


def seed_missing_products(service, *, brand: str) -> dict[str, Any]:
    from app.services.marketing_engine.product_matcher import SEED_PRODUCTS

    brand_key = service._normalize_brand(brand)
    now = utc_now()

    existing_names = {
        row.product_name.strip().lower()
        for row in service.db.query(BrandProduct).filter(BrandProduct.brand == brand_key).all()
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
            source_url=f"seed://catalog/{brand_key}",
            source_hash=f"seed-{seed['sku']}-{now.isoformat()}",
            active=True,
            extra_data={"sku": seed["sku"], "category": seed.get("category")},
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        service.db.add(product)
        service.db.flush()

        for condition_key in seed.get("applicable_conditions", []):
            existing_mapping = (
                service.db.query(ProductConditionMapping)
                .filter(
                    ProductConditionMapping.product_id == product.id,
                    ProductConditionMapping.condition_key == condition_key,
                )
                .first()
            )
            if existing_mapping:
                continue
            service.db.add(ProductConditionMapping(
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
        service.db.commit()

    return {
        "added_products": added_products,
        "added_mappings": added_mappings,
        "total_seed_products": len(SEED_PRODUCTS),
        "already_existed": len(SEED_PRODUCTS) - len(added_products),
    }
