"""Persistence and maintenance helpers for the marketing opportunity engine."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.core.time import utc_now
from app.models.database import MarketingOpportunity
from app.services.media.ranking_signal_service import RankingSignalService

if TYPE_CHECKING:
    from .opportunity_engine import MarketingOpportunityEngine


def _require_brand(engine: "MarketingOpportunityEngine", value: Any) -> str:
    brand = engine._canonical_brand(value)
    if brand:
        return brand
    raise ValueError("brand must be provided")


def save_opportunity(engine: "MarketingOpportunityEngine", opp: dict[str, Any]) -> bool:
    """Persist a marketing opportunity with simple dedup handling."""
    opp_id = opp.get("id", "")
    existing = (
        engine.db.query(MarketingOpportunity)
        .filter(MarketingOpportunity.opportunity_id == opp_id)
        .first()
    )

    supply_gap_data = None
    if opp.get("_supply_gap_applied"):
        supply_gap_data = {
            "is_active": True,
            "priority_multiplier": opp.get("_supply_gap_priority_multiplier", 1.0),
            "sku": opp.get("_supply_gap_sku", ""),
            "product": opp.get("_supply_gap_product", ""),
            "matched_products": opp.get("_supply_gap_matched_products", []),
        }

    if existing:
        existing.urgency_score = opp.get("urgency_score", existing.urgency_score)
        existing.sales_pitch = opp.get("sales_pitch", existing.sales_pitch)
        existing.suggested_products = opp.get("suggested_products", existing.suggested_products)
        if supply_gap_data:
            payload = (existing.campaign_payload or {}).copy()
            payload["supply_gap"] = supply_gap_data
            existing.campaign_payload = payload
        existing.updated_at = utc_now()
        engine.db.commit()
        return False

    trigger_ctx = opp.get("trigger_context", {})
    detected_at_str = trigger_ctx.get("detected_at", "")
    try:
        detected_at = datetime.fromisoformat(detected_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        detected_at = utc_now()

    campaign_payload: dict[str, Any] = {}
    if supply_gap_data:
        campaign_payload["supply_gap"] = supply_gap_data

    entry = MarketingOpportunity(
        opportunity_id=opp_id,
        opportunity_type=opp.get("type", ""),
        status=opp.get("status", "NEW"),
        urgency_score=opp.get("urgency_score", 0),
        region_target=opp.get("region_target"),
        trigger_source=trigger_ctx.get("source"),
        trigger_event=trigger_ctx.get("event"),
        trigger_details=trigger_ctx,
        trigger_detected_at=detected_at,
        target_audience=opp.get("target_audience"),
        sales_pitch=opp.get("sales_pitch"),
        suggested_products=opp.get("suggested_products"),
        campaign_payload=campaign_payload if campaign_payload else None,
        expires_at=utc_now() + timedelta(days=14),
    )
    engine.db.add(entry)
    engine.db.commit()
    return True


def backfill_peix_context(
    engine: "MarketingOpportunityEngine",
    *,
    force: bool = False,
    limit: int = 1000,
) -> dict[str, Any]:
    """Backfill missing ranking-signal context blocks for existing recommendations."""
    query = engine.db.query(MarketingOpportunity).order_by(MarketingOpportunity.created_at.desc())
    if limit > 0:
        query = query.limit(limit)
    rows = query.all()

    ranking_signal_build = RankingSignalService(engine.db).build()
    ranking_signal_regions = ranking_signal_build.get("regions") or {}

    scanned = 0
    updated = 0
    skipped_existing = 0
    skipped_no_region = 0

    for row in rows:
        scanned += 1
        payload = (row.campaign_payload or {}).copy()
        existing = payload.get("peix_context") or {}

        if (
            not force
            and isinstance(existing, dict)
            and existing.get("score") is not None
            and existing.get("region_code")
        ):
            skipped_existing += 1
            continue

        opportunity = {
            "region_target": row.region_target or {},
            "campaign_payload": payload,
            "trigger_context": row.trigger_details
            or {
                "source": row.trigger_source,
                "event": row.trigger_event,
                "detected_at": row.trigger_detected_at.isoformat() if row.trigger_detected_at else None,
            },
        }

        region_codes = engine._extract_region_codes_from_opportunity(opportunity)
        selected_region = region_codes[0] if region_codes else "Gesamt"
        ranking_signal_context = engine._derive_ranking_signal_context(
            ranking_signal_regions,
            selected_region,
            opportunity,
            ranking_signal_national=ranking_signal_build,
        )

        if not ranking_signal_context:
            skipped_no_region += 1
            continue

        payload["peix_context"] = ranking_signal_context
        payload["ranking_signal_context"] = ranking_signal_context
        row.campaign_payload = payload
        row.updated_at = utc_now()
        updated += 1

    if updated > 0:
        engine.db.commit()

    return {
        "success": True,
        "scanned": scanned,
        "updated": updated,
        "skipped_existing": skipped_existing,
        "skipped_no_region": skipped_no_region,
        "force": force,
        "timestamp": utc_now().isoformat(),
    }


def backfill_product_mapping(
    engine: "MarketingOpportunityEngine",
    *,
    force: bool = False,
    limit: int = 1000,
) -> dict[str, Any]:
    """Re-resolve product mappings for existing recommendations."""
    query = engine.db.query(MarketingOpportunity).order_by(MarketingOpportunity.created_at.desc())
    if limit > 0:
        query = query.limit(limit)
    rows = query.all()

    scanned = 0
    updated = 0
    skipped = 0

    for row in rows:
        scanned += 1
        payload = (row.campaign_payload or {}).copy()
        old_pm = payload.get("product_mapping") or {}
        old_status = str(old_pm.get("mapping_status") or "").strip().lower()

        if not force and old_status == "approved":
            skipped += 1
            continue

        condition_key = old_pm.get("condition_key")
        brand = _require_brand(engine, row.brand)

        opp_dict = {
            "region_target": row.region_target or {},
            "campaign_payload": payload,
            "trigger_context": row.trigger_details or {},
        }
        new_pm = engine.product_catalog_service.resolve_product_for_opportunity(
            brand=brand,
            opportunity=opp_dict,
            fallback_product=row.product,
        )

        if condition_key and not new_pm.get("condition_key"):
            new_pm["condition_key"] = condition_key
            new_pm["condition_label"] = old_pm.get("condition_label")

        selected = engine._select_product_for_opportunity(
            fallback_product=row.product or "Alle Produkte",
            product_mapping=new_pm,
        )

        payload["product_mapping"] = new_pm
        row.campaign_payload = payload

        products_set: set[str] = {new_pm["recommended_product"]} if new_pm.get("recommended_product") else set()
        if new_pm.get("candidate_product"):
            products_set.add(new_pm["candidate_product"])
        old_suggested = row.suggested_products or []
        if isinstance(old_suggested, list):
            for item in old_suggested:
                name = item if isinstance(item, str) else (
                    item.get("product_name") if isinstance(item, dict) else None
                )
                if name and "test" not in name.lower() and "652238" not in name:
                    products_set.add(name)
        if selected and "freigabe ausstehend" not in selected.lower():
            products_set.add(selected)
        row.suggested_products = [{"product_name": p} for p in sorted(products_set) if p]

        row.updated_at = utc_now()
        updated += 1

    if updated > 0:
        engine.db.commit()

    return {
        "success": True,
        "scanned": scanned,
        "updated": updated,
        "skipped_approved": skipped,
        "force": force,
        "timestamp": utc_now().isoformat(),
    }
