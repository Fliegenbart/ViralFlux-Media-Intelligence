"""Media API: Map-first Cockpit + Action Cards."""

import io
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.schema_contracts import MLForecastSchemaMismatchError
from app.db.session import get_db
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.connector_payload_service import ConnectorPayloadService
from app.services.media.cockpit_service import MediaCockpitService
from app.services.media.copy_service import (
    public_display_title,
    public_playbook_title,
    public_reason_text,
)
from app.services.media.product_catalog_service import (
    DEFAULT_GELO_SOURCE_URL,
    ProductCatalogService,
)
from app.services.media.recommendation_contracts import (
    extract_region_codes_from_card as contract_extract_region_codes_from_card,
    extract_region_codes_from_card_payload as contract_extract_region_codes_from_card_payload,
    normalize_region_code as contract_normalize_region_code,
    to_card_response as contract_to_card_response,
)
from app.services.media.tasks import refine_recommendation_ai_task
from app.services.media.v2_service import MediaV2Service
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
    "DRAFT": "Vorbereitung",
    "READY": "In Prüfung",
    "APPROVED": "Freigegeben",
    "ACTIVATED": "Live",
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
    campaign_goal: str = Field(default="Sichtbarkeit aufbauen, bevor die Nachfrage steigt")
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


class PrepareSyncRequest(BaseModel):
    connector_key: Optional[str] = Field(default=None)


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


class OutcomeImportRecord(BaseModel):
    week_start: str
    product: str
    region_code: str
    media_spend_eur: float | None = None
    impressions: float | None = None
    clicks: float | None = None
    qualified_visits: float | None = None
    search_lift_index: float | None = None
    sales_units: float | None = None
    order_count: float | None = None
    revenue_eur: float | None = None
    extra_data: dict[str, Any] | None = None


class OutcomeImportRequest(BaseModel):
    brand: str = Field(default="gelo")
    source_label: str = Field(default="manual")
    replace_existing: bool = Field(default=False)
    validate_only: bool = Field(default=False)
    file_name: str | None = None
    records: list[OutcomeImportRecord] = Field(default_factory=list)
    csv_payload: str | None = None


def _json_safe_response(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe_response(item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): _json_safe_response(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_response(v) for v in value]
    return str(value)


@router.get("/cockpit")
async def get_media_cockpit(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    db: Session = Depends(get_db),
):
    """Aggregierter One-shot Payload für das Map-first Dashboard."""
    service = MediaCockpitService(db)
    try:
        return service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
    except MLForecastSchemaMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/decision")
async def get_media_decision(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
    db: Session = Depends(get_db),
):
    """V2 Decision-View Payload mit WeeklyDecision, Gate-Mix und Model/Truth-Kontext."""
    return _json_safe_response(
        MediaV2Service(db).get_decision_payload(
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )
    )


@router.get("/regions")
async def get_media_regions(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
    db: Session = Depends(get_db),
):
    """V2 Regionen-Workbench Payload mit Signal-Treibern und Prioritätslogik."""
    return _json_safe_response(
        MediaV2Service(db).get_regions_payload(
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )
    )


@router.get("/campaigns")
async def get_media_campaigns(
    brand: str = "gelo",
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """V2 Campaign-Queue mit Deduplizierung, Lifecycle-State und Publish-Blockern."""
    return _json_safe_response(MediaV2Service(db).get_campaigns_payload(brand=brand, limit=limit))


@router.get("/evidence")
async def get_media_evidence(
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str = "gelo",
    db: Session = Depends(get_db),
):
    """V2 Evidenz-View mit Proxy, Truth, SignalStack und ModelLineage."""
    return _json_safe_response(
        MediaV2Service(db).get_evidence_payload(
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )
    )


@router.get("/signal-stack")
async def get_media_signal_stack(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Technischer V2-Endpunkt für den expliziten Signal-Stack."""
    return _json_safe_response(MediaV2Service(db).get_signal_stack(virus_typ=virus_typ))


@router.get("/model-lineage")
async def get_media_model_lineage(
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Liefert Modellversion, Feature-Set und Drift-Status des aktuellen Forecast-Stacks."""
    return _json_safe_response(MediaV2Service(db).get_model_lineage(virus_typ=virus_typ))


@router.get("/outcomes/coverage")
async def get_media_outcomes_coverage(
    brand: str = "gelo",
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Truth-Layer Coverage über importierte Outcome-Daten."""
    return _json_safe_response(MediaV2Service(db).get_truth_coverage(brand=brand, virus_typ=virus_typ))


@router.get("/pilot-reporting")
async def get_media_pilot_reporting(
    brand: str = "gelo",
    lookback_weeks: int = Query(default=26, ge=1, le=104),
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    region_code: str | None = Query(default=None),
    product: str | None = Query(default=None),
    include_draft: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Pilot readout for recommendation history, activations and outcome evidence."""
    from app.services.media.pilot_reporting_service import PilotReportingService

    try:
        return _json_safe_response(
            PilotReportingService(db).build_pilot_report(
                brand=brand,
                lookback_weeks=lookback_weeks,
                window_start=window_start,
                window_end=window_end,
                region_code=region_code,
                product=product,
                include_draft=include_draft,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/evidence/truth")
async def get_media_truth_evidence(
    brand: str = "gelo",
    virus_typ: str = "Influenza A",
    db: Session = Depends(get_db),
):
    """Truth-Evidence Snapshot für Analysten-Ansicht, Coverage und Import-Historie."""
    return _json_safe_response(MediaV2Service(db).get_truth_evidence(brand=brand, virus_typ=virus_typ))


@router.get("/outcomes/import-batches")
async def list_media_outcome_import_batches(
    brand: str = "gelo",
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Listet die letzten Truth-Import-Batches mit Status und Coverage-Snapshot."""
    return _json_safe_response({
        "brand": brand,
        "batches": MediaV2Service(db).list_outcome_import_batches(brand=brand, limit=limit),
    })


@router.get("/outcomes/import-batches/{batch_id}")
async def get_media_outcome_import_batch_detail(
    batch_id: str,
    db: Session = Depends(get_db),
):
    """Liefert Detailansicht eines Truth-Import-Batches inklusive Issues."""
    detail = MediaV2Service(db).get_outcome_import_batch_detail(batch_id=batch_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Outcome-Import-Batch {batch_id} nicht gefunden")
    return _json_safe_response(detail)


@router.get("/outcomes/template")
async def download_media_outcome_template(
    db: Session = Depends(get_db),
):
    """CSV-Template für manuelle Truth-/Outcome-Uploads."""
    content = MediaV2Service(db).outcome_template_csv()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="viralflux_truth_template.csv"'},
    )


@router.post("/outcomes/import")
async def import_media_outcomes(
    payload: OutcomeImportRequest,
    db: Session = Depends(get_db),
):
    """Importiert Truth-/Outcome-Daten per JSON oder CSV-String für den Kundenbeweis-Layer."""
    service = MediaV2Service(db)
    return _json_safe_response(
        service.import_outcomes(
            source_label=payload.source_label,
            records=[item.model_dump(exclude_none=True) for item in payload.records],
            csv_payload=payload.csv_payload,
            brand=payload.brand,
            replace_existing=payload.replace_existing,
            validate_only=payload.validate_only,
            file_name=payload.file_name,
        )
    )


@router.post("/recommendations/generate")
@limiter.limit("10/minute")
async def generate_media_recommendations(
    request: Request,
    payload: RecommendationGenerateRequest,
    db: Session = Depends(get_db),
):
    """Generiert strukturierte Action-Cards für Media-Steuerung."""
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


@router.get("/connectors/catalog")
async def get_media_connector_catalog():
    """Liefert verfügbare Media-Connectoren für spätere Tool-Syncs."""
    return ConnectorPayloadService.get_catalog()


@router.post("/recommendations/open-region")
async def open_or_create_region_recommendation(
    payload: RecommendationOpenRegionRequest,
    db: Session = Depends(get_db),
):
    """Map-Klick Flow: vorhandene Card wiederverwenden oder regionale Draft-Card erzeugen."""
    region_code = _normalize_region_code(payload.region_code)
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


@router.patch("/recommendations/{opportunity_id}/campaign")
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


@router.patch("/recommendations/{opportunity_id}/status")
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


@router.post("/recommendations/{opportunity_id}/regenerate-ai")
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


@router.post("/recommendations/{opportunity_id}/prepare-sync")
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
    prod = product or opp.get("product") or "Atemwegslinie"
    condition = CONDITION_LABELS.get(opp.get("condition_key", ""), "")
    return public_display_title(
        playbook_key=opp.get("playbook_key"),
        playbook_title=opp.get("playbook_title"),
        campaign_name=((opp.get("campaign_preview") or {}).get("campaign_name") or ((opp.get("campaign_payload") or {}).get("campaign") or {}).get("campaign_name")),
        product=prod,
        trigger_event=event,
        condition_label=condition,
    )


def _to_card_response(opp: dict[str, Any], include_preview: bool = True) -> dict[str, Any]:
    return contract_to_card_response(opp, include_preview=include_preview)


def _decorate_card_response(
    service: MediaV2Service,
    opp: dict[str, Any],
    *,
    include_preview: bool = True,
) -> dict[str, Any]:
    card = _to_card_response(opp, include_preview=include_preview)
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


def _normalize_region_code(value: str) -> str:
    return contract_normalize_region_code(value)


def _extract_region_codes_from_card_payload(opp: dict[str, Any], campaign_pack: dict[str, Any]) -> list[str]:
    return contract_extract_region_codes_from_card_payload(opp, campaign_pack)


def _extract_region_codes_from_card(card: dict[str, Any]) -> set[str]:
    return contract_extract_region_codes_from_card(card)
