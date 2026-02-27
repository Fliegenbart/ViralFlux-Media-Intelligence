"""Media API: Map-first Cockpit + Action Cards."""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.cockpit_service import MediaCockpitService
from app.services.media.product_catalog_service import (
    DEFAULT_GELO_SOURCE_URL,
    ProductCatalogService,
)
from app.services.media.tasks import refine_recommendation_ai_task
from app.schemas.brand_product import BrandProductCreateInput, BrandProductUpdate


router = APIRouter()
settings = get_settings()

BUNDESLAND_NAMES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
REGION_NAME_TO_CODE = {name.lower(): code for code, name in BUNDESLAND_NAMES.items()}

EVENT_LABELS: dict[str, str] = {
    "COMPETITOR_SHORTAGE_GELO-PRO": "Wettbewerber-Engpass: Erkältungsmittel",
    "COMPETITOR_SHORTAGE_GELO-GMF": "Wettbewerber-Engpass: Bronchitis/Husten",
    "COMPETITOR_SHORTAGE_GELO-RVC": "Wettbewerber-Engpass: Halsschmerzmittel",
    "COMPETITOR_SHORTAGE_GELO-BRO": "Wettbewerber-Engpass: Hustenstiller",
    "COMPETITOR_SHORTAGE_GELO-SIT": "Wettbewerber-Engpass: Sinusitis-Mittel",
    "COMPETITOR_SHORTAGE_GELO-DUR": "Wettbewerber-Engpass: Schnupfenmittel",
    "COMPETITOR_SHORTAGE_GELO-VOX": "Wettbewerber-Engpass: Heiserkeit-Mittel",
    "COMPETITOR_SHORTAGE_GELO-VIT": "Wettbewerber-Engpass: Immunpräparate",
    "COMPETITOR_SHORTAGE_GELO-MUC": "Wettbewerber-Engpass: Schleimlöser",
    "CRITICAL_SHORTAGE_ANTIBIOTICS": "Kritischer Engpass: Antibiotika",
    "CRITICAL_SHORTAGE_RESPIRATORY": "Kritischer Engpass: Atemwegsmedikamente",
    "CRITICAL_SHORTAGE_FEVER": "Kritischer Engpass: Fieber-/Schmerzmittel",
    "ORDER_VELOCITY_SURGE": "Bestellanstieg erkannt",
    "LOW_UV_EXTENDED": "Anhaltend niedriger UV-Index",
    "WINTER_COLD_STREAK": "Winterliche Kältewelle",
    "LOW_SUNSHINE_FORECAST": "Wenig Sonnenschein vorhergesagt",
    "NASSKALT_FORECAST": "Nasskaltes Wetter vorhergesagt",
    "EXTREME_COLD_FORECAST": "Extremkälte vorhergesagt",
}

CONDITION_LABELS: dict[str, str] = {
    "erkaltung_akut": "Akute Erkältung",
    "bronchitis_husten": "Bronchitis & Husten",
    "halsschmerz": "Halsschmerzen",
    "husten_reizhusten": "Reizhusten",
    "sinusitis": "Sinusitis",
    "schnupfen": "Schnupfen",
    "heiserkeit": "Heiserkeit",
    "immun_support": "Immununterstützung",
    "schleimloeser": "Schleimlösung",
}

STATUS_LABELS: dict[str, str] = {
    "NEW": "Neu",
    "URGENT": "Dringend",
    "DRAFT": "Entwurf",
    "READY": "Bereit",
    "APPROVED": "Freigegeben",
    "ACTIVATED": "Aktiviert",
}


class RecommendationGenerateRequest(BaseModel):
    brand: str = Field(default="gelo")
    product: str = Field(default="Alle Gelo-Produkte")
    campaign_goal: str = Field(default="Awareness + Abverkauf")
    weekly_budget: float = Field(default=100000.0, ge=0)
    channel_pool: List[str] = Field(default_factory=lambda: ["programmatic", "social", "search", "ctv"])
    region_scope: Optional[List[str]] = None
    strategy_mode: str = Field(default="PLAYBOOK_AI")
    max_cards: int = Field(default=8, ge=1, le=20)
    virus_typ: str = Field(default="Influenza A")


class RecommendationOpenRegionRequest(BaseModel):
    region_code: str = Field(..., min_length=2)
    brand: str = Field(default="gelo")
    product: str = Field(default="Alle Gelo-Produkte")
    campaign_goal: str = Field(default="Top-of-Mind vor Erkältungswelle")
    weekly_budget: float = Field(default=100000.0, ge=0)
    virus_typ: str = Field(default="Influenza A")


class ChannelPlanItem(BaseModel):
    channel: str
    share_pct: float
    role: Optional[str] = None
    formats: Optional[List[str]] = None
    message_angle: Optional[str] = None
    kpi_primary: Optional[str] = None
    kpi_secondary: Optional[List[str]] = None


class CampaignUpdateRequest(BaseModel):
    activation_window: Optional[dict] = None
    budget: Optional[dict] = None
    channel_plan: Optional[List[ChannelPlanItem]] = None
    kpi_targets: Optional[dict] = None


class RecommendationStatusUpdateRequest(BaseModel):
    status: str


class RecommendationBackfillPeixRequest(BaseModel):
    force: bool = Field(default=False)
    limit: int = Field(default=1000, ge=1, le=10000)


class ProductMappingUpdateRequest(BaseModel):
    is_approved: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0, le=999)
    notes: Optional[str] = None


class ProductConditionLinkRequest(BaseModel):
    condition_key: str = Field(..., min_length=1)
    is_approved: bool = False
    fit_score: float = Field(default=0.8, ge=0.0, le=1.0)
    priority: int = Field(default=600, ge=0, le=999)
    mapping_reason: str | None = None
    notes: str | None = None


@router.get("/cockpit")
async def get_media_cockpit(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    db: Session = Depends(get_db),
):
    """Aggregierter One-shot Payload für das Map-first Dashboard."""
    service = MediaCockpitService(db)
    return service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)


@router.post("/recommendations/generate")
@limiter.limit("10/minute")
async def generate_media_recommendations(
    request: Request,
    payload: RecommendationGenerateRequest,
    db: Session = Depends(get_db),
):
    """Generiert strukturierte Action-Cards für Media-Steuerung."""
    engine = MarketingOpportunityEngine(db)
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

    cards = [_to_card_response(card) for card in generated.get("cards", [])]
    cards.sort(key=lambda item: (item.get("urgency_score", 0), item.get("confidence", 0)), reverse=True)
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
                # Keep generate endpoint responsive; card remains available without async refinement.
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


@router.get("/playbooks/catalog")
async def get_playbook_catalog(db: Session = Depends(get_db)):
    """Liefert aktiven Playbook-Katalog inkl. Triggerrahmen."""
    engine = MarketingOpportunityEngine(db)
    return engine.get_playbook_catalog()


@router.post("/recommendations/open-region")
async def open_or_create_region_recommendation(
    payload: RecommendationOpenRegionRequest,
    db: Session = Depends(get_db),
):
    """Map-Klick Flow: vorhandene Card wiederverwenden oder regionale Draft-Card erzeugen."""
    region_code = _normalize_region_code(payload.region_code)
    engine = MarketingOpportunityEngine(db)

    existing = engine.get_opportunities(
        brand_filter=payload.brand,
        limit=300,
        normalize_status=True,
    )
    existing_cards = [
        _to_card_response(item, include_preview=True)
        for item in existing
        if str(item.get("status") or "").upper() not in {"DISMISSED", "EXPIRED"}
    ]
    existing_cards.sort(key=lambda item: (item.get("urgency_score", 0), item.get("confidence", 0)), reverse=True)

    for card in existing_cards:
        if region_code in _extract_region_codes_from_card(card):
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
    generated_cards = [_to_card_response(card, include_preview=True) for card in generated.get("cards", [])]
    generated_cards.sort(key=lambda item: (item.get("urgency_score", 0), item.get("confidence", 0)), reverse=True)

    selected = None
    for card in generated_cards:
        if region_code in _extract_region_codes_from_card(card):
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


@router.get("/recommendations/list")
async def list_media_recommendations(
    status: Optional[str] = None,
    min_urgency: Optional[float] = None,
    brand: Optional[str] = None,
    region: Optional[str] = None,
    condition_key: Optional[str] = None,
    limit: int = 50,
    with_campaign_preview: bool = True,
    db: Session = Depends(get_db),
):
    """Listet persistierte Action-Cards / Opportunities."""
    engine = MarketingOpportunityEngine(db)
    opportunities = engine.get_opportunities(
        status_filter=status,
        min_urgency=min_urgency,
        brand_filter=brand,
        limit=limit,
        normalize_status=True,
    )

    cards = [_to_card_response(opp, include_preview=with_campaign_preview) for opp in opportunities]
    if region:
        region_code = _normalize_region_code(region)
        cards = [
            card for card in cards
            if region_code in _extract_region_codes_from_card(card)
        ]
    if condition_key:
        ck = condition_key.strip().lower()
        cards = [
            card for card in cards
            if str(card.get("condition_key") or "").strip().lower() == ck
        ]
    cards.sort(key=lambda item: (item.get("urgency_score", 0), item.get("confidence", 0)), reverse=True)

    return {
        "total": len(cards),
        "cards": cards,
    }


@router.get("/recommendations/refinement-task/{task_id}")
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


@router.post("/recommendations/backfill-peix")
async def backfill_recommendation_peix_context(
    payload: RecommendationBackfillPeixRequest,
    db: Session = Depends(get_db),
):
    """Backfill von PeixEpiScore-Context für bestehende Recommendations."""
    engine = MarketingOpportunityEngine(db)
    return engine.backfill_peix_context(force=payload.force, limit=payload.limit)


@router.post("/recommendations/backfill-products")
async def backfill_recommendation_product_mapping(
    force: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Re-resolve Produkt-Mappings für bestehende Recommendations."""
    engine = MarketingOpportunityEngine(db)
    return engine.backfill_product_mapping(force=force, limit=limit)


@router.get("/recommendations/{opportunity_id}")
async def get_media_recommendation_detail(
    opportunity_id: str,
    db: Session = Depends(get_db),
):
    """Liefert detaillierte Recommendation inkl. Campaign Pack."""
    engine = MarketingOpportunityEngine(db)
    item = engine.get_recommendation_by_id(opportunity_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Recommendation {opportunity_id} nicht gefunden")

    payload = item.get("campaign_payload") or {}
    return {
        **_to_card_response(item, include_preview=True),
        "campaign_pack": payload,
        "trigger_evidence": item.get("trigger_evidence") or payload.get("trigger_evidence"),
        "decision_brief": item.get("decision_brief"),
        "target_audience": item.get("target_audience") or [],
        "sales_pitch": item.get("sales_pitch"),
        "suggested_products": item.get("suggested_products") or [],
    }


@router.patch("/recommendations/{opportunity_id}/campaign")
async def update_media_recommendation_campaign(
    opportunity_id: str,
    payload: CampaignUpdateRequest,
    db: Session = Depends(get_db),
):
    """Aktualisiert editierbare Kampagnenfelder auf einer Recommendation."""
    engine = MarketingOpportunityEngine(db)
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
        **_to_card_response(result, include_preview=True),
        "campaign_pack": result.get("campaign_payload") or {},
    }


@router.patch("/recommendations/{opportunity_id}/status")
async def update_media_recommendation_status(
    opportunity_id: str,
    payload: RecommendationStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Aktualisiert den Workflow-Status einer Recommendation."""
    engine = MarketingOpportunityEngine(db)
    result = engine.update_status(opportunity_id, payload.status)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/recommendations/{opportunity_id}/regenerate-ai")
async def regenerate_media_recommendation_ai(
    opportunity_id: str,
    db: Session = Depends(get_db),
):
    """Regeneriert KI-Plan (nur ai_* Bereiche im Campaign Payload)."""
    engine = MarketingOpportunityEngine(db)
    result = engine.regenerate_ai_plan(opportunity_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        **_to_card_response(result, include_preview=True),
        "campaign_pack": result.get("campaign_payload") or {},
        "trigger_evidence": result.get("trigger_evidence"),
    }


@router.post("/products/refresh")
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


@router.post("/products")
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


@router.patch("/products/{product_id}")
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


@router.delete("/products/{product_id}")
async def delete_media_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    """Deaktiviert ein Produkt (Soft-Delete)."""
    service = ProductCatalogService(db)
    deleted = service.soft_delete_product(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Produkt {product_id} nicht gefunden")
    return deleted


@router.post("/products/{product_id}/match/run")
async def run_media_product_match(
    product_id: int,
    db: Session = Depends(get_db),
):
    """Berechnet Mapping-Regeln für ein einzelnes Produkt neu."""
    service = ProductCatalogService(db)
    result = service.run_match_for_product(product_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Produkt {product_id} nicht gefunden")
    return result


@router.post("/products/{product_id}/condition-links")
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


@router.get("/products/match-preview")
async def preview_media_product_match(
    brand: str = Query(default="gelo"),
    opportunity_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Gibt aktuelle Produkt-Match-Vorschläge für Opportunities zurück."""
    service = ProductCatalogService(db)
    try:
        data = service.preview_matches(
            brand=brand,
            opportunity_id=opportunity_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return data


@router.get("/products")
async def list_media_products(
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Aktueller Produktkatalog inklusive Aktivstatus."""
    service = ProductCatalogService(db)
    products = service.list_products(brand=brand)
    return {
        "brand": brand,
        "total": len(products),
        "products": products,
    }


@router.get("/product-mapping")
async def list_media_product_mapping(
    brand: str = Query(default="gelo"),
    include_inactive_products: bool = Query(default=False),
    only_pending: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Zeigt Lage->Produkt Mappings inkl. Review-Status."""
    service = ProductCatalogService(db)
    mappings = service.list_mappings(
        brand=brand,
        include_inactive_products=include_inactive_products,
        only_pending=only_pending,
    )
    return {
        "brand": brand,
        "total": len(mappings),
        "mappings": mappings,
    }


@router.post("/seed-products")
async def seed_missing_products(
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Fehlende SEED_PRODUCTS als BrandProduct + Mappings anlegen (idempotent)."""
    service = ProductCatalogService(db)
    return service.seed_missing_products(brand=brand)


# ── Weekly Brief Endpoints ────────────────────────────────────────────────────


@router.post("/weekly-brief/generate")
async def generate_weekly_brief(
    virus_typ: str = Query(default="Influenza A"),
    db: Session = Depends(get_db),
):
    """Manueller Trigger: Generiert den Action Brief für die aktuelle KW."""
    from app.services.media.weekly_brief_service import WeeklyBriefService

    service = WeeklyBriefService(db)
    result = service.generate(virus_typ=virus_typ)
    return {
        "status": "success",
        "calendar_week": result["calendar_week"],
        "pages": result["pages"],
        "summary": result["summary"],
    }


@router.get("/weekly-brief/latest")
async def get_latest_weekly_brief(
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Download des neuesten Action Brief als PDF."""
    import io
    from app.models.database import WeeklyBrief

    brief = (
        db.query(WeeklyBrief)
        .filter_by(brand=brand)
        .order_by(WeeklyBrief.generated_at.desc())
        .first()
    )
    if not brief or not brief.pdf_bytes:
        raise HTTPException(status_code=404, detail="Kein Weekly Brief vorhanden. Bitte zuerst generieren.")

    filename = f"Gelo_Action_Brief_{brief.calendar_week}.pdf"
    return StreamingResponse(
        io.BytesIO(brief.pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/weekly-brief/{calendar_week}")
async def get_weekly_brief_by_week(
    calendar_week: str,
    brand: str = Query(default="gelo"),
    db: Session = Depends(get_db),
):
    """Download eines spezifischen Action Brief nach Kalenderwoche."""
    import io
    from app.models.database import WeeklyBrief

    brief = (
        db.query(WeeklyBrief)
        .filter_by(calendar_week=calendar_week, brand=brand)
        .first()
    )
    if not brief or not brief.pdf_bytes:
        raise HTTPException(status_code=404, detail=f"Kein Brief für {calendar_week} vorhanden.")

    filename = f"Gelo_Action_Brief_{calendar_week}.pdf"
    return StreamingResponse(
        io.BytesIO(brief.pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/product-mapping/{mapping_id}")
async def update_media_product_mapping(
    mapping_id: int,
    payload: ProductMappingUpdateRequest,
    db: Session = Depends(get_db),
):
    """Review/Freigabe für ein Produkt-Mapping."""
    service = ProductCatalogService(db)
    updated = service.update_mapping(
        mapping_id,
        is_approved=payload.is_approved,
        priority=payload.priority,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} nicht gefunden")
    return updated


def _build_display_title(opp: dict[str, Any], product: str | None) -> str:
    """Baut einen lesbaren Titel aus Trigger-Kontext."""
    event = (opp.get("trigger_context") or {}).get("event", "")
    label = EVENT_LABELS.get(event)
    prod = product or opp.get("product") or "Atemwegslinie"
    if label:
        return f"{prod}: {label}"
    cond = CONDITION_LABELS.get(opp.get("condition_key", ""), "")
    if cond:
        return f"{prod} – {cond}"
    return prod


def _to_card_response(opp: dict[str, Any], include_preview: bool = True) -> dict[str, Any]:
    preview = opp.get("campaign_preview") or {}
    campaign_pack = opp.get("campaign_payload") or {}
    measurement = campaign_pack.get("measurement_plan") or {}
    product_mapping = campaign_pack.get("product_mapping") or {}
    peix_context = campaign_pack.get("peix_context") or {}
    playbook = campaign_pack.get("playbook") or {}
    ai_meta = campaign_pack.get("ai_meta") or {}
    region_codes = _extract_region_codes_from_card_payload(opp, campaign_pack)
    recommended_product = (
        opp.get("recommended_product")
        or product_mapping.get("recommended_product")
        or opp.get("product")
    )

    trigger_ctx = opp.get("trigger_context") or {}
    condition_key = opp.get("condition_key") or product_mapping.get("condition_key", "")

    card = {
        "id": opp.get("id"),
        "status": opp.get("status"),
        "status_label": STATUS_LABELS.get(opp.get("status", ""), opp.get("status")),
        "type": opp.get("type"),
        "urgency_score": opp.get("urgency_score"),
        "brand": opp.get("brand") or "PEIX Partner",
        "product": recommended_product or "Atemwegslinie",
        "recommended_product": recommended_product,
        "region": opp.get("region") or (
            BUNDESLAND_NAMES.get(region_codes[0], region_codes[0]) if region_codes else "National"
        ),
        "region_codes": region_codes,
        "region_codes_display": [BUNDESLAND_NAMES.get(c, c) for c in region_codes],
        "budget_shift_pct": opp.get("budget_shift_pct") or (preview.get("budget") or {}).get("shift_pct") or 15.0,
        "channel_mix": opp.get("channel_mix") or {"programmatic": 35, "social": 30, "search": 20, "ctv": 15},
        "activation_window": {
            "start": opp.get("activation_start") or (preview.get("activation_window") or {}).get("start"),
            "end": opp.get("activation_end") or (preview.get("activation_window") or {}).get("end"),
        },
        "reason": (
            opp.get("recommendation_reason")
            or EVENT_LABELS.get(trigger_ctx.get("event", ""))
            or trigger_ctx.get("details")
            or trigger_ctx.get("event")
        ),
        "confidence": (
            round(float(opp.get("confidence")), 2)
            if opp.get("confidence") is not None
            else round(min(0.98, max(0.45, float(opp.get("urgency_score") or 50.0) / 100.0)), 2)
        ),
        "detail_url": opp.get("detail_url") or f"/dashboard/recommendations/{opp.get('id')}",
        "created_at": opp.get("created_at"),
        "updated_at": opp.get("updated_at"),
        "campaign_name": preview.get("campaign_name") or ((campaign_pack.get("campaign") or {}).get("campaign_name")),
        "primary_kpi": preview.get("primary_kpi") or measurement.get("primary_kpi"),
        "mapping_status": opp.get("mapping_status") or product_mapping.get("mapping_status"),
        "mapping_confidence": opp.get("mapping_confidence") or product_mapping.get("mapping_confidence"),
        "mapping_reason": opp.get("mapping_reason") or product_mapping.get("mapping_reason"),
        "condition_key": condition_key,
        "condition_label": (
            opp.get("condition_label")
            or product_mapping.get("condition_label")
            or CONDITION_LABELS.get(condition_key)
        ),
        "mapping_candidate_product": opp.get("mapping_candidate_product") or product_mapping.get("candidate_product"),
        "mapping_rule_source": opp.get("rule_source") or product_mapping.get("rule_source"),
        "peix_context": opp.get("peix_context") or peix_context,
        "playbook_key": opp.get("playbook_key") or playbook.get("key"),
        "playbook_title": opp.get("playbook_title") or playbook.get("title"),
        "trigger_snapshot": opp.get("trigger_snapshot") or campaign_pack.get("trigger_snapshot"),
        "guardrail_notes": opp.get("guardrail_notes") or (campaign_pack.get("guardrail_report") or {}).get("applied_fixes") or [],
        "ai_generation_status": opp.get("ai_generation_status") or ai_meta.get("status"),
        "strategy_mode": opp.get("strategy_mode") or campaign_pack.get("strategy_mode"),
        "decision_brief": opp.get("decision_brief"),
        "display_title": (
            opp.get("playbook_title")
            or playbook.get("title")
            or preview.get("campaign_name")
            or (campaign_pack.get("campaign") or {}).get("campaign_name")
            or _build_display_title(opp, recommended_product)
        ),
    }

    if include_preview:
        card["campaign_preview"] = {
            "campaign_name": card.get("campaign_name"),
            "activation_window": preview.get("activation_window") or card.get("activation_window"),
            "budget": preview.get("budget") or {},
            "primary_kpi": card.get("primary_kpi"),
            "recommended_product": recommended_product,
            "mapping_status": card.get("mapping_status"),
            "peix_context": card.get("peix_context"),
            "playbook_key": card.get("playbook_key"),
            "playbook_title": card.get("playbook_title"),
            "ai_generation_status": card.get("ai_generation_status"),
        }

    return card


def _normalize_region_code(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "DE"

    upper = raw.upper()
    if upper in BUNDESLAND_NAMES:
        return upper

    mapped = REGION_NAME_TO_CODE.get(raw.lower())
    if mapped:
        return mapped

    return upper


def _extract_region_codes_from_card_payload(opp: dict[str, Any], campaign_pack: dict[str, Any]) -> list[str]:
    existing = opp.get("region_codes")
    if isinstance(existing, list) and existing:
        normalized = [_normalize_region_code(str(item)) for item in existing if item]
        return sorted({code for code in normalized if code in BUNDESLAND_NAMES})

    region = opp.get("region")
    if isinstance(region, str) and region.strip():
        code = _normalize_region_code(region)
        if code in BUNDESLAND_NAMES:
            return [code]
        if region.strip().lower() in {"gesamt", "de", "all", "national"}:
            return sorted(BUNDESLAND_NAMES.keys())

    targeting = campaign_pack.get("targeting") or {}
    scope = targeting.get("region_scope")
    tokens: list[str] = []
    if isinstance(scope, list):
        tokens.extend(str(item) for item in scope if item)
    elif isinstance(scope, str) and scope.strip():
        tokens.append(scope)

    if not tokens:
        return []

    result = set()
    for token in tokens:
        lower = token.strip().lower()
        if lower in {"gesamt", "de", "all", "national", "deutschland"}:
            return sorted(BUNDESLAND_NAMES.keys())
        code = _normalize_region_code(token)
        if code in BUNDESLAND_NAMES:
            result.add(code)

    return sorted(result)


def _extract_region_codes_from_card(card: dict[str, Any]) -> set[str]:
    codes = card.get("region_codes")
    if isinstance(codes, list) and codes:
        normalized = {_normalize_region_code(str(code)) for code in codes if code}
        normalized = {code for code in normalized if code in BUNDESLAND_NAMES}
        if normalized:
            return normalized

    region = str(card.get("region") or "").strip().lower()
    if region in {"gesamt", "de", "all", "national", "deutschland"}:
        return set(BUNDESLAND_NAMES.keys())

    if region:
        code = _normalize_region_code(region)
        if code in BUNDESLAND_NAMES:
            return {code}

    return set()
