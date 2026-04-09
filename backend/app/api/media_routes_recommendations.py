"""Recommendation, product, and sync routes for the media API."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.api.media_contracts import (
    CampaignUpdateRequest,
    PrepareSyncRequest,
    ProductConditionLinkRequest,
    ProductMappingUpdateRequest,
    RecommendationBackfillPeixRequest,
    RecommendationGenerateRequest,
    RecommendationOpenRegionRequest,
    RecommendationStatusUpdateRequest,
)
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.connector_payload_service import ConnectorPayloadService
from app.services.media.product_catalog_service import DEFAULT_GELO_SOURCE_URL, ProductCatalogService
from app.services.media.recommendation_contracts import (
    extract_region_codes_from_card as contract_extract_region_codes_from_card,
    normalize_region_code as contract_normalize_region_code,
    to_card_response as contract_to_card_response,
)
from app.services.media.tasks import refine_recommendation_ai_task
from app.services.media.v2_service import MediaV2Service
from app.schemas.brand_product import BrandProductCreateInput, BrandProductUpdate

router = APIRouter()
settings = get_settings()


def _decorate_card_response(
    service: MediaV2Service,
    opp: dict[str, Any],
    *,
    include_preview: bool = True,
) -> dict[str, Any]:
    card = contract_to_card_response(opp, include_preview=include_preview)
    truth_coverage = service.get_truth_coverage(brand=str(card.get("brand") or "gelo"))
    truth_gate = service.truth_gate_service.evaluate(truth_coverage)
    learning_bundle = service.outcome_signal_service.build_learning_bundle(
        brand=str(card.get("brand") or "gelo"),
        truth_coverage=truth_coverage,
        truth_gate=truth_gate,
    )
    return service._attach_outcome_learning_to_card(
        card=card,
        learning_bundle=learning_bundle,
        truth_gate=truth_gate,
    )


@router.post("/recommendations/generate", dependencies=[Depends(get_current_admin)])
@limiter.limit("10/minute")
async def generate_media_recommendations(
    request: Request,
    payload: RecommendationGenerateRequest,
    db: Session = Depends(get_db),
):
    """Generiert strukturierte Action-Cards für Media-Steuerung."""
    del request
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)
    generated = engine.generate_action_cards(
        brand=payload.brand,
        product=payload.product,
        campaign_goal=payload.campaign_goal,
        weekly_budget=payload.weekly_budget,
        channel_pool=payload.channel_pool,
        region_scope=payload.region_scope,
        strategy_mode=payload.strategy_mode,
        max_cards=payload.max_cards,
        virus_typ=payload.virus_typ,
    )

    cards = [_decorate_card_response(service, card) for card in generated.get("cards", [])]
    cards.sort(
        key=lambda item: (
            item.get("priority_score", 0),
            item.get("signal_confidence_pct", item.get("confidence", 0)) or 0,
        ),
        reverse=True,
    )
    top_card_id = generated.get("top_card_id") or (cards[0].get("id") if cards else None)

    refinement_mode = "disabled"
    refinement_tasks: list[dict[str, str]] = []
    refinement_poll_hint_seconds = max(1, int(settings.MEDIA_AI_REFINEMENT_POLL_HINT_SECONDS or 5))
    top_n = max(0, int(settings.MEDIA_AI_BULK_REFINE_TOP_N or 3))

    if settings.MEDIA_AI_ASYNC_REFINEMENT_ENABLED:
        refinement_mode = "async_top3"
        for card in cards[:top_n]:
            card_id = str(card.get("id") or "").strip()
            if not card_id:
                continue
            try:
                task = refine_recommendation_ai_task.delay(opportunity_id=card_id)
                refinement_tasks.append({"card_id": card_id, "task_id": task.id})
            except Exception:
                continue

    return {
        "meta": generated.get("meta", {}),
        "total_cards": generated.get("total_cards", len(cards)),
        "cards": cards,
        "top_card_id": top_card_id,
        "auto_open_url": generated.get("auto_open_url"),
        "refinement_mode": refinement_mode,
        "refinement_tasks": refinement_tasks,
        "refinement_poll_hint_seconds": refinement_poll_hint_seconds,
    }


@router.get("/playbooks/catalog", dependencies=[Depends(get_current_user)])
async def get_playbook_catalog(db: Session = Depends(get_db)):
    """Liefert aktiven Playbook-Katalog inkl. Triggerrahmen."""
    return MarketingOpportunityEngine(db).get_playbook_catalog()


@router.get("/connectors/catalog", dependencies=[Depends(get_current_user)])
async def get_media_connector_catalog():
    """Liefert verfügbare Media-Connectoren für spätere Tool-Syncs."""
    return ConnectorPayloadService.get_catalog()


@router.post("/recommendations/open-region", dependencies=[Depends(get_current_admin)])
async def open_or_create_region_recommendation(
    payload: RecommendationOpenRegionRequest,
    db: Session = Depends(get_db),
):
    """Map-Klick Flow: vorhandene Card wiederverwenden oder regionale Draft-Card erzeugen."""
    region_code = contract_normalize_region_code(payload.region_code)
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)

    existing = engine.get_opportunities(
        brand_filter=payload.brand,
        limit=300,
        normalize_status=True,
    )
    existing_cards = [
        _decorate_card_response(service, item, include_preview=True)
        for item in existing
        if str(item.get("status") or "").upper() not in {"DISMISSED", "EXPIRED"}
    ]
    existing_cards.sort(
        key=lambda item: (
            item.get("priority_score", 0),
            item.get("signal_confidence_pct", item.get("confidence", 0)) or 0,
        ),
        reverse=True,
    )

    for card in existing_cards:
        if region_code in contract_extract_region_codes_from_card(card):
            return {
                "action": "reused",
                "region_code": region_code,
                "card_id": card.get("id"),
                "detail_url": card.get("detail_url"),
                "card_preview": card,
            }

    generated = engine.generate_action_cards(
        brand=payload.brand,
        product=payload.product,
        campaign_goal=payload.campaign_goal,
        weekly_budget=payload.weekly_budget,
        channel_pool=["programmatic", "social", "search", "ctv"],
        region_scope=[region_code],
        strategy_mode="PLAYBOOK_AI",
        max_cards=4,
        virus_typ=payload.virus_typ,
    )
    generated_cards = [
        _decorate_card_response(service, card, include_preview=True)
        for card in generated.get("cards", [])
    ]
    generated_cards.sort(
        key=lambda item: (
            item.get("priority_score", 0),
            item.get("signal_confidence_pct", item.get("confidence", 0)) or 0,
        ),
        reverse=True,
    )

    selected = None
    for card in generated_cards:
        if region_code in contract_extract_region_codes_from_card(card):
            selected = card
            break
    if selected is None and generated_cards:
        selected = generated_cards[0]

    if not selected:
        raise HTTPException(status_code=404, detail="Keine passende Recommendation konnte erzeugt werden.")

    return {
        "action": "created",
        "region_code": region_code,
        "card_id": selected.get("id"),
        "detail_url": selected.get("detail_url"),
        "card_preview": selected,
    }


@router.get("/recommendations/list", dependencies=[Depends(get_current_user)])
async def list_media_recommendations(
    status: str | None = None,
    min_urgency: float | None = None,
    brand: str | None = None,
    region: str | None = None,
    condition_key: str | None = None,
    limit: int = 50,
    with_campaign_preview: bool = True,
    db: Session = Depends(get_db),
):
    """Listet persistierte Action-Cards / Opportunities."""
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)
    opportunities = engine.get_opportunities(
        status_filter=status,
        min_urgency=min_urgency,
        brand_filter=brand,
        limit=limit,
        normalize_status=True,
    )

    cards = [
        _decorate_card_response(service, opp, include_preview=with_campaign_preview)
        for opp in opportunities
    ]
    if region:
        region_code = contract_normalize_region_code(region)
        cards = [card for card in cards if region_code in contract_extract_region_codes_from_card(card)]
    if condition_key:
        ck = condition_key.strip().lower()
        cards = [
            card for card in cards
            if str(card.get("condition_key") or "").strip().lower() == ck
        ]
    cards.sort(
        key=lambda item: (
            item.get("priority_score", 0),
            item.get("signal_confidence_pct", item.get("confidence", 0)) or 0,
        ),
        reverse=True,
    )

    return {
        "total": len(cards),
        "cards": cards,
    }


@router.get("/recommendations/refinement-task/{task_id}", dependencies=[Depends(get_current_user)])
async def get_media_recommendation_refinement_task_status(task_id: str):
    """Polling endpoint for async AI refinement task status."""
    task_result = celery_app.AsyncResult(task_id)

    response: dict[str, Any] = {
        "task_id": task_id,
        "status": task_result.status,
    }
    if task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.info)
    elif task_result.info is not None:
        response["meta"] = task_result.info

    return response


@router.post("/recommendations/backfill-peix", dependencies=[Depends(get_current_admin)])
async def backfill_recommendation_peix_context(
    payload: RecommendationBackfillPeixRequest,
    db: Session = Depends(get_db),
):
    """Backfill von PeixEpiScore-Context für bestehende Recommendations."""
    return MarketingOpportunityEngine(db).backfill_peix_context(force=payload.force, limit=payload.limit)


@router.post("/recommendations/backfill-products", dependencies=[Depends(get_current_admin)])
async def backfill_recommendation_product_mapping(
    force: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Re-resolve Produkt-Mappings für bestehende Recommendations."""
    return MarketingOpportunityEngine(db).backfill_product_mapping(force=force, limit=limit)


@router.get("/recommendations/{opportunity_id}", dependencies=[Depends(get_current_user)])
async def get_media_recommendation_detail(
    opportunity_id: str,
    db: Session = Depends(get_db),
):
    """Liefert detaillierte Recommendation inkl. Campaign Pack."""
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)
    item = engine.get_recommendation_by_id(opportunity_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Recommendation {opportunity_id} nicht gefunden")

    payload = item.get("campaign_payload") or {}
    return {
        **_decorate_card_response(service, item, include_preview=True),
        "campaign_pack": payload,
        "trigger_evidence": item.get("trigger_evidence") or payload.get("trigger_evidence"),
        "decision_brief": item.get("decision_brief"),
        "target_audience": item.get("target_audience") or [],
        "sales_pitch": item.get("sales_pitch"),
        "suggested_products": item.get("suggested_products") or [],
    }


@router.patch("/recommendations/{opportunity_id}/campaign", dependencies=[Depends(get_current_admin)])
async def update_media_recommendation_campaign(
    opportunity_id: str,
    payload: CampaignUpdateRequest,
    db: Session = Depends(get_db),
):
    """Aktualisiert editierbare Kampagnenfelder auf einer Recommendation."""
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)
    result = engine.update_campaign(
        opportunity_id,
        activation_window=payload.activation_window,
        budget=payload.budget,
        channel_plan=[
            item.model_dump(exclude_none=True) for item in payload.channel_plan
        ] if payload.channel_plan is not None else None,
        kpi_targets=payload.kpi_targets,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        **_decorate_card_response(service, result, include_preview=True),
        "campaign_pack": result.get("campaign_payload") or {},
    }


@router.patch("/recommendations/{opportunity_id}/status", dependencies=[Depends(get_current_admin)])
async def update_media_recommendation_status(
    opportunity_id: str,
    payload: RecommendationStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Aktualisiert den Workflow-Status einer Recommendation."""
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)
    result = engine.update_status(opportunity_id, payload.status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        **_decorate_card_response(service, result, include_preview=True),
        "new_status": result.get("new_status") or payload.status,
    }


@router.post("/recommendations/{opportunity_id}/regenerate-ai", dependencies=[Depends(get_current_admin)])
async def regenerate_media_recommendation_ai(
    opportunity_id: str,
    db: Session = Depends(get_db),
):
    """Regeneriert KI-Plan (nur ai_* Bereiche im Campaign Payload)."""
    engine = MarketingOpportunityEngine(db)
    service = MediaV2Service(db)
    result = engine.regenerate_ai_plan(opportunity_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        **_decorate_card_response(service, result, include_preview=True),
        "campaign_pack": result.get("campaign_payload") or {},
        "trigger_evidence": result.get("trigger_evidence"),
    }


@router.post("/recommendations/{opportunity_id}/prepare-sync", dependencies=[Depends(get_current_admin)])
async def prepare_media_recommendation_sync(
    opportunity_id: str,
    payload: PrepareSyncRequest | None = None,
    db: Session = Depends(get_db),
):
    """Erzeugt connector-ready Preview-Payloads für spätere Media-Tool-Syncs."""
    engine = MarketingOpportunityEngine(db)
    item = engine.get_recommendation_by_id(opportunity_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Recommendation {opportunity_id} nicht gefunden")

    try:
        return ConnectorPayloadService.prepare_sync_package(
            opportunity=item,
            connector_key=payload.connector_key if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/products/refresh", dependencies=[Depends(get_current_admin)])
async def refresh_media_products(
    brand: str = Query(default="gelo"),
    source_url: str = Query(default=DEFAULT_GELO_SOURCE_URL),
    overwrite_rules: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Manueller Produktkatalog-Refresh aus externer Quelle."""
    service = ProductCatalogService(db)
    result = service.refresh_brand_catalog(
        brand=brand,
        source_url=source_url,
        overwrite_rules=overwrite_rules,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/products", dependencies=[Depends(get_current_admin)])
async def create_media_product(
    payload: BrandProductCreateInput,
    db: Session = Depends(get_db),
):
    """Legt ein neues Produkt im Gelo-Katalog manuell an."""
    service = ProductCatalogService(db)
    try:
        attributes = {
            "sku": payload.sku,
            "target_segments": payload.target_segments,
            "conditions": payload.conditions,
            "forms": payload.forms,
            "age_min_months": payload.age_min_months,
            "age_max_months": payload.age_max_months,
            "audience_mode": payload.audience_mode,
            "channel_fit": payload.channel_fit,
            "compliance_notes": payload.compliance_notes,
        }
        product = service.create_product(
            brand=payload.brand,
            product_name=payload.product_name,
            source_url=payload.source_url,
            source_hash=payload.source_hash,
            active=payload.active,
            extra_data=None,
            attributes=attributes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return product


@router.patch("/products/{product_id}", dependencies=[Depends(get_current_admin)])
async def update_media_product(
    product_id: int,
    payload: BrandProductUpdate,
    db: Session = Depends(get_db),
):
    """Aktualisiert Produktattribute/Metadaten des Katalogs."""
    service = ProductCatalogService(db)
    payload_data = payload.model_dump(exclude_unset=True)
    attribute_fields = {
        "sku",
        "target_segments",
        "conditions",
        "forms",
        "age_min_months",
        "age_max_months",
        "audience_mode",
        "channel_fit",
        "compliance_notes",
    }
    attributes = {
        key: payload_data[key]
        for key in attribute_fields
        if key in payload_data
    }
    try:
        updated = service.update_product(
            product_id=product_id,
            product_name=payload_data.get("product_name"),
            source_url=payload_data.get("source_url"),
            source_hash=payload_data.get("source_hash"),
            active=payload_data.get("active"),
            extra_data=payload_data.get("extra_data"),
            attributes=attributes or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Produkt {product_id} nicht gefunden")
    return updated


@router.delete("/products/{product_id}", dependencies=[Depends(get_current_admin)])
async def delete_media_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    """Deaktiviert ein Produkt (Soft-Delete)."""
    deleted = ProductCatalogService(db).soft_delete_product(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Produkt {product_id} nicht gefunden")
    return deleted


@router.post("/products/{product_id}/match/run", dependencies=[Depends(get_current_admin)])
async def run_media_product_match(
    product_id: int,
    db: Session = Depends(get_db),
):
    """Berechnet Mapping-Regeln für ein einzelnes Produkt neu."""
    result = ProductCatalogService(db).run_match_for_product(product_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Produkt {product_id} nicht gefunden")
    return result


@router.post("/products/{product_id}/condition-links", dependencies=[Depends(get_current_admin)])
async def add_media_product_condition_link(
    product_id: int,
    payload: ProductConditionLinkRequest,
    db: Session = Depends(get_db),
):
    """Fügt einen manuellen Lagebezug für ein Produkt hinzu oder passt ihn an."""
    service = ProductCatalogService(db)
    try:
        row = service.upsert_condition_link(
            product_id=product_id,
            condition_key=payload.condition_key,
            is_approved=payload.is_approved,
            fit_score=payload.fit_score,
            priority=payload.priority,
            mapping_reason=payload.mapping_reason,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail=f"Produkt {product_id} nicht gefunden")
    return row


@router.get("/products/match-preview", dependencies=[Depends(get_current_user)])
async def preview_media_product_match(
    brand: str = Query(default="gelo"),
    opportunity_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Gibt aktuelle Produkt-Match-Vorschläge für Opportunities zurück."""
    service = ProductCatalogService(db)
    try:
        return service.preview_matches(
            brand=brand,
            opportunity_id=opportunity_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/products", dependencies=[Depends(get_current_user)])
async def list_media_products(
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Aktueller Produktkatalog inklusive Aktivstatus."""
    products = ProductCatalogService(db).list_products(brand=brand)
    return {
        "brand": brand,
        "total": len(products),
        "products": products,
    }


@router.get("/product-mapping", dependencies=[Depends(get_current_user)])
async def list_media_product_mapping(
    brand: str = Query(default="gelo"),
    include_inactive_products: bool = Query(default=False),
    only_pending: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Zeigt Lage->Produkt Mappings inkl. Review-Status."""
    mappings = ProductCatalogService(db).list_mappings(
        brand=brand,
        include_inactive_products=include_inactive_products,
        only_pending=only_pending,
    )
    return {
        "brand": brand,
        "total": len(mappings),
        "mappings": mappings,
    }


@router.post("/seed-products", dependencies=[Depends(get_current_admin)])
async def seed_missing_products(
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Fehlende SEED_PRODUCTS als BrandProduct + Mappings anlegen (idempotent)."""
    return ProductCatalogService(db).seed_missing_products(brand=brand)


@router.patch("/product-mapping/{mapping_id}", dependencies=[Depends(get_current_admin)])
async def update_media_product_mapping(
    mapping_id: int,
    payload: ProductMappingUpdateRequest,
    db: Session = Depends(get_db),
):
    """Review/Freigabe für ein Produkt-Mapping."""
    updated = ProductCatalogService(db).update_mapping(
        mapping_id,
        is_approved=payload.is_approved,
        priority=payload.priority,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} nicht gefunden")
    return updated
