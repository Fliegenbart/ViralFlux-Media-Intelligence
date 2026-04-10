"""Serialization and parsing helpers for the product catalog service."""

from __future__ import annotations

from html import unescape
import hashlib
import re
from typing import Any

from app.models.database import BrandProduct, MarketingOpportunity, ProductConditionMapping


def serialize_product(service, row: BrandProduct) -> dict[str, Any]:
    attrs = service._extract_product_attributes(row.extra_data)
    last_seen = row.last_seen_at.isoformat() if row.last_seen_at else None
    updated = row.updated_at.isoformat() if row.updated_at else None

    mappings = (
        service.db.query(ProductConditionMapping)
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


def serialize_mapping(service, mapping: ProductConditionMapping) -> dict[str, Any]:
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
        "product_active": bool(product.active) if product is not None else None,
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


def extract_product_attributes(service, extra_data: dict[str, Any] | None) -> dict[str, Any]:
    base: dict[str, Any] = {}
    if isinstance(extra_data, dict):
        base.update(extra_data)

    return {
        "sku": str(base.get("sku")).strip() if base.get("sku") else None,
        "target_segments": service._to_str_list(base.get("target_segments")),
        "conditions": service._to_str_list(base.get("conditions")),
        "forms": service._to_str_list(base.get("forms")),
        "age_min_months": service._to_int(base.get("age_min_months")),
        "age_max_months": service._to_int(base.get("age_max_months")),
        "audience_mode": str(base.get("audience_mode") or "b2c").strip() or "b2c",
        "channel_fit": service._to_str_list(base.get("channel_fit")),
        "compliance_notes": str(base.get("compliance_notes") or "").strip() or None,
    }


def merge_product_extra_data(
    service,
    *,
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
            merged["target_segments"] = service._to_str_list(attributes.get("target_segments"))
        if "conditions" in attributes:
            merged["conditions"] = service._to_str_list(attributes.get("conditions"))
        if "forms" in attributes:
            merged["forms"] = service._to_str_list(attributes.get("forms"))
        if "age_min_months" in attributes:
            merged["age_min_months"] = service._to_int(attributes.get("age_min_months"))
        if "age_max_months" in attributes:
            merged["age_max_months"] = service._to_int(attributes.get("age_max_months"))
        if "audience_mode" in attributes:
            merged["audience_mode"] = str(attributes.get("audience_mode") or "b2c").strip() or "b2c"
        if "channel_fit" in attributes:
            merged["channel_fit"] = service._to_str_list(attributes.get("channel_fit"))
        if "compliance_notes" in attributes:
            merged["compliance_notes"] = str(attributes.get("compliance_notes") or "").strip() or None
    return merged


def build_product_text_blob(service, product: BrandProduct) -> str:
    attrs = service._extract_product_attributes(product.extra_data)
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


def opportunity_payload(row: MarketingOpportunity) -> dict[str, Any]:
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


def extract_products_from_html(service, html: str) -> list[dict[str, Any]]:
    chunks = re.split(r'(?=<div class="product product--)', html)
    products: list[dict[str, Any]] = []
    seen: set[str] = set()

    for chunk in chunks:
        if not chunk.startswith('<div class="product product--'):
            continue

        name_html = service._first_match(chunk, r'<h2 class="product__name">\s*(.*?)\s*</h2>')
        product_name = service._normalize_product_name(_strip_html(name_html))
        if not product_name:
            continue
        normalized = service._normalize_name(product_name)
        if normalized in seen:
            continue
        seen.add(normalized)

        short_text_html = service._first_match(chunk, r'<div class="product__short-text">\s*(.*?)\s*</div>')
        subline_html = service._first_match(chunk, r'<div class="product__subline">\s*(.*?)\s*</div>')
        details_html = service._first_match(chunk, r'<div class="product__more-content">\s*(.*?)\s*</div>')

        short_text = _strip_html(short_text_html)
        subline = _strip_html(subline_html)
        details_text = _strip_html(details_html)

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


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<br\s*/?>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()
