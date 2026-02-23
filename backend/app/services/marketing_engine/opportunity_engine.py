"""MarketingOpportunityEngine — Hauptorchestrator.

Fuehrt alle Detektoren aus, erzeugt Sales Pitches, matcht Produkte,
persistiert Opportunities und liefert CRM-faehiges JSON.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Any
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import AuditLog, MarketingOpportunity
from app.services.media.ai_campaign_planner import AiCampaignPlanner
from app.services.media.campaign_guardrails import CampaignGuardrails
from app.services.media.message_library import select_gelo_message_pack
from app.services.media.product_catalog_service import ProductCatalogService
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.playbook_engine import PLAYBOOK_CATALOG, PlaybookEngine

from .detectors.competitor_shortage_detector import CompetitorShortageDetector
from .detectors.predictive_sales_spike import PredictiveSalesSpikeDetector
from .detectors.resource_scarcity import ResourceScarcityDetector
from .detectors.weather_forecast import WeatherForecastDetector
from .pitch_generator import PitchGenerator
from .product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SYSTEM_VERSION = "ViralFlux-Media-v3.0"
settings = get_settings()

LEGACY_TO_WORKFLOW = {
    "NEW": "DRAFT",
    "URGENT": "DRAFT",
    "SENT": "APPROVED",
    "CONVERTED": "ACTIVATED",
}

WORKFLOW_TO_LEGACY = {
    "DRAFT": "NEW",
    "READY": "NEW",
    "APPROVED": "SENT",
    "ACTIVATED": "CONVERTED",
    "DISMISSED": "DISMISSED",
    "EXPIRED": "EXPIRED",
}

WORKFLOW_STATUSES = {
    "DRAFT",
    "READY",
    "APPROVED",
    "ACTIVATED",
    "DISMISSED",
    "EXPIRED",
}

ALLOWED_TRANSITIONS = {
    "DRAFT": {"READY", "DISMISSED"},
    "READY": {"APPROVED", "DISMISSED"},
    "APPROVED": {"ACTIVATED", "DISMISSED"},
    "ACTIVATED": {"EXPIRED", "DISMISSED"},
    "DISMISSED": set(),
    "EXPIRED": set(),
}

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


class MarketingOpportunityEngine:
    """Orchestriert alle Opportunity-Detektoren und CRM-Output."""

    def __init__(self, db: Session):
        self.db = db
        self.detectors = [
            ResourceScarcityDetector(db),
            CompetitorShortageDetector(db),
            PredictiveSalesSpikeDetector(db),
            WeatherForecastDetector(db),
        ]
        self.pitch_generator = PitchGenerator()
        self.product_matcher = ProductMatcher(db)
        self.product_catalog_service = ProductCatalogService(db)
        self.playbook_engine = PlaybookEngine(db)
        self.ai_planner = AiCampaignPlanner()
        self.guardrails = CampaignGuardrails()

    def generate_opportunities(self) -> dict:
        """Alle Detektoren ausführen -> Pitches -> Products -> Fuse Conquesting -> Persist -> JSON."""
        all_opportunities = []

        for detector in self.detectors:
            try:
                raw_opps = detector.detect()
                logger.info(
                    "%s: %s Opportunities erkannt",
                    detector.OPPORTUNITY_TYPE,
                    len(raw_opps),
                )
                for raw in raw_opps:
                    raw["sales_pitch"] = self.pitch_generator.generate(raw["type"], raw)
                    raw["suggested_products"] = self.product_matcher.match(raw["type"], raw)
                    all_opportunities.append(raw)
            except Exception as exc:
                logger.error("Detector %s fehlgeschlagen: %s", detector.OPPORTUNITY_TYPE, exc)

        # ── Signal-Deduplizierung: gleiche Condition + Region → nur höchste Urgency behalten ──
        all_opportunities = self._deduplicate_signals(all_opportunities)

        # ── Conquesting Fusion: amplify epidemiological opportunities with bid multipliers ──
        all_opportunities = self._fuse_conquesting_multipliers(all_opportunities)

        # ── Kreis-Targeting: Top-Kreise nach aktueller Inzidenz anreichern ──
        all_opportunities = self._enrich_kreis_targeting(all_opportunities)

        all_opportunities.sort(key=lambda x: x.get("urgency_score", 0), reverse=True)

        saved = 0
        for opp in all_opportunities:
            if self._save_opportunity(opp):
                saved += 1

        logger.info(
            "MarketingOpportunityEngine: %s erkannt, %s neu gespeichert",
            len(all_opportunities),
            saved,
        )

        clean_opps = [self._clean_for_output(o) for o in all_opportunities]
        return {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "system_version": SYSTEM_VERSION,
                "total_opportunities": len(clean_opps),
                "new_saved": saved,
            },
            "opportunities": clean_opps,
        }

    @staticmethod
    def _deduplicate_signals(opportunities: list[dict]) -> list[dict]:
        """Dedupliziere Detektor-Signale: gleiche Condition + Region-Fingerprint
        aus verschiedenen Detektoren → nur die Opportunity mit der höchsten
        Urgency behalten. COMPETITOR_SHORTAGE wird nicht dedupliziert (ist
        Modifier, kein eigenständiger Trigger)."""
        seen: dict[str, dict] = {}
        passthrough: list[dict] = []

        for opp in opportunities:
            opp_type = opp.get("type", "")
            if opp_type == "COMPETITOR_SHORTAGE":
                passthrough.append(opp)
                continue

            condition = opp.get("_condition", "")
            region = opp.get("region_target", {})
            states = tuple(sorted(region.get("states", []))) if isinstance(region, dict) else ()
            dedup_key = f"{condition}::{states}"

            existing = seen.get(dedup_key)
            if existing is None or opp.get("urgency_score", 0) > existing.get("urgency_score", 0):
                seen[dedup_key] = opp

        deduped = list(seen.values()) + passthrough
        removed = len(opportunities) - len(deduped)
        if removed > 0:
            logger.info("Signal-Deduplizierung: %d Duplikate entfernt", removed)
        return deduped

    @staticmethod
    def _fuse_conquesting_multipliers(opportunities: list[dict]) -> list[dict]:
        """Fuse COMPETITOR_SHORTAGE bid_multipliers into epidemiological opportunities.

        When a COMPETITOR_SHORTAGE opportunity exists for a condition, its
        bid_multiplier is applied to all other opportunities sharing that condition.
        The conquesting opportunity itself is kept for audit/tracking but marked
        as a modifier (not a standalone campaign trigger).

        Fusion rules:
        - Match on _condition field (e.g. "bronchitis_husten")
        - Multiply urgency_score by bid_multiplier (capped at 100)
        - Annotate the fused opportunity with conquesting metadata
        - If multiple conquesting opps match, use the highest multiplier
        """
        # Collect conquesting multipliers by condition
        conquesting_by_condition: dict[str, dict] = {}
        for opp in opportunities:
            if opp.get("type") != "COMPETITOR_SHORTAGE":
                continue
            condition = opp.get("_condition", "")
            if not condition:
                continue
            existing = conquesting_by_condition.get(condition)
            if not existing or opp.get("_bid_multiplier", 1.0) > existing.get("_bid_multiplier", 1.0):
                conquesting_by_condition[condition] = opp

        if not conquesting_by_condition:
            return opportunities

        # Apply multipliers to non-conquesting opportunities
        for opp in opportunities:
            if opp.get("type") == "COMPETITOR_SHORTAGE":
                continue

            condition = opp.get("_condition", "")
            conquesting = conquesting_by_condition.get(condition)
            if not conquesting:
                continue

            multiplier = float(conquesting.get("_bid_multiplier", 1.0))
            original_urgency = float(opp.get("urgency_score", 0))
            # Kein Cap bei 100: erlaubt Ranking unter mehreren urgenten
            # Opportunities wenn Conquesting-Multiplikator angewendet wird.
            fused_urgency = original_urgency * multiplier

            opp["urgency_score"] = round(fused_urgency, 1)
            opp["_conquesting_applied"] = True
            opp["_conquesting_multiplier"] = multiplier
            opp["_conquesting_sku"] = conquesting.get("_conquesting_sku")
            opp["_conquesting_product"] = conquesting.get("_conquesting_product")
            opp["_conquesting_matched_drugs"] = conquesting.get("_matched_drugs", [])

            logger.info(
                "Conquesting fusion: %s urgency %.0f → %.0f (×%.1f from %s)",
                opp.get("id", "?"),
                original_urgency,
                fused_urgency,
                multiplier,
                conquesting.get("_conquesting_sku"),
            )

        return opportunities

    # ── Condition → Disease-Cluster Mapping ──
    _CONDITION_CLUSTER_MAP = {
        "bronchitis_husten": "RESPIRATORY",
        "sinusitis_nebenhoehlen": "RESPIRATORY",
        "erkaltung_akut": "RESPIRATORY",
        "halsschmerz_heiserkeit": "RESPIRATORY",
        "rhinitis_trockene_nase": "RESPIRATORY",
        "immun_support": "RESPIRATORY",
    }

    # Grossstädte → Bundesland (für schnelle Zuordnung ohne DB-Lookup)
    _KREIS_BL_MAP = {
        "SK Hamburg": "Hamburg", "SK München": "Bayern", "SK Berlin": "Berlin",
        "SK Dresden": "Sachsen", "SK Leipzig": "Sachsen", "SK Köln": "Nordrhein-Westfalen",
        "SK Frankfurt am Main": "Hessen", "SK Stuttgart": "Baden-Württemberg",
        "SK Düsseldorf": "Nordrhein-Westfalen", "SK Hannover": "Niedersachsen",
        "SK Bremen": "Bremen", "SK Nürnberg": "Bayern", "SK Dortmund": "Nordrhein-Westfalen",
        "SK Essen": "Nordrhein-Westfalen", "SK Duisburg": "Nordrhein-Westfalen",
        "SK Chemnitz": "Sachsen", "SK Erfurt": "Thüringen", "SK Magdeburg": "Sachsen-Anhalt",
        "SK Rostock": "Mecklenburg-Vorpommern", "SK Potsdam": "Brandenburg",
        "SK Kiel": "Schleswig-Holstein", "SK Mainz": "Rheinland-Pfalz",
        "SK Saarbrücken": "Saarland", "SK Freiburg i.Breisgau": "Baden-Württemberg",
    }

    def _kreis_bundesland(self, kreis_name: str) -> str:
        """Bundesland aus Kreisname ableiten (Lookup + KreisEinwohner Fallback)."""
        return self._KREIS_BL_MAP.get(kreis_name, "")

    def _enrich_kreis_targeting(self, opportunities: list[dict]) -> list[dict]:
        """Anreicherung mit Top-Kreisen nach aktueller Fallzahl.

        Liest SurvstatKreisData der letzten 4 Wochen, gruppiert nach
        Disease-Cluster, und fügt die Top-10 Kreise in region_target ein.
        """
        from app.models.database import SurvstatKreisData

        needed_clusters = set()
        for opp in opportunities:
            condition = opp.get("_condition", "")
            cluster = self._CONDITION_CLUSTER_MAP.get(condition)
            if cluster:
                needed_clusters.add(cluster)

        if not needed_clusters:
            return opportunities

        now = datetime.utcnow()
        current_week = now.isocalendar()[1]
        current_year = now.year

        kreise_by_cluster: dict[str, list[dict]] = {}
        for cluster in needed_clusters:
            # Letzte 4 verfügbare Wochen (aktuelles Jahr)
            rows = (
                self.db.query(
                    SurvstatKreisData.kreis,
                    func.sum(SurvstatKreisData.fallzahl).label("total_faelle"),
                )
                .filter(
                    SurvstatKreisData.disease_cluster == cluster,
                    SurvstatKreisData.year == current_year,
                    SurvstatKreisData.week >= max(1, current_week - 4),
                )
                .group_by(SurvstatKreisData.kreis)
                .order_by(func.sum(SurvstatKreisData.fallzahl).desc())
                .limit(10)
                .all()
            )

            if not rows:
                # Fallback: letztes verfügbares Jahr
                latest_year = (
                    self.db.query(func.max(SurvstatKreisData.year))
                    .filter(SurvstatKreisData.disease_cluster == cluster)
                    .scalar()
                )
                if latest_year and latest_year != current_year:
                    latest_week = (
                        self.db.query(func.max(SurvstatKreisData.week))
                        .filter(SurvstatKreisData.disease_cluster == cluster, SurvstatKreisData.year == latest_year)
                        .scalar()
                    ) or 52
                    rows = (
                        self.db.query(
                            SurvstatKreisData.kreis,
                            func.sum(SurvstatKreisData.fallzahl).label("total_faelle"),
                        )
                        .filter(
                            SurvstatKreisData.disease_cluster == cluster,
                            SurvstatKreisData.year == latest_year,
                            SurvstatKreisData.week >= max(1, latest_week - 4),
                        )
                        .group_by(SurvstatKreisData.kreis)
                        .order_by(func.sum(SurvstatKreisData.fallzahl).desc())
                        .limit(10)
                        .all()
                    )

            if rows:
                kreise_by_cluster[cluster] = [
                    {
                        "kreis": r.kreis,
                        "bundesland": self._kreis_bundesland(r.kreis),
                        "faelle_4w": int(r.total_faelle or 0),
                    }
                    for r in rows
                ]

        for opp in opportunities:
            condition = opp.get("_condition", "")
            cluster = self._CONDITION_CLUSTER_MAP.get(condition)
            top_kreise = kreise_by_cluster.get(cluster, []) if cluster else []

            if top_kreise:
                region = opp.get("region_target", {})
                region["top_kreise"] = [k["kreis"] for k in top_kreise]
                region["kreis_detail"] = top_kreise
                if not region.get("states"):
                    unique_bl = list(dict.fromkeys(k["bundesland"] for k in top_kreise if k["bundesland"]))
                    region["states"] = unique_bl
                opp["region_target"] = region

        return opportunities

    def get_opportunities(
        self,
        type_filter: str | None = None,
        status_filter: str | None = None,
        brand_filter: str | None = None,
        min_urgency: float | None = None,
        limit: int = 50,
        skip: int = 0,
        normalize_status: bool = True,
    ) -> list[dict]:
        """Gespeicherte Opportunities mit Filtern abrufen."""
        query = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.urgency_score.desc(),
            MarketingOpportunity.created_at.desc(),
        )

        if type_filter:
            query = query.filter(MarketingOpportunity.opportunity_type == type_filter)
        if status_filter:
            query = query.filter(MarketingOpportunity.status.in_(self._status_filter_values(status_filter)))
        if brand_filter:
            canonical_brand = self._canonical_brand(brand_filter)
            if canonical_brand == "gelo":
                query = query.filter(func.lower(MarketingOpportunity.brand).like("%gelo%"))
            else:
                query = query.filter(func.lower(MarketingOpportunity.brand) == canonical_brand)
        if min_urgency is not None:
            query = query.filter(MarketingOpportunity.urgency_score >= min_urgency)

        results = query.offset(skip).limit(limit).all()
        return [self._model_to_dict(r, normalize_status=normalize_status) for r in results]

    def count_opportunities(
        self,
        type_filter: str | None = None,
        status_filter: str | None = None,
        brand_filter: str | None = None,
        min_urgency: float | None = None,
    ) -> int:
        """Gesamtanzahl der Opportunities mit denselben Filtern."""
        query = self.db.query(func.count(MarketingOpportunity.id))

        if type_filter:
            query = query.filter(MarketingOpportunity.opportunity_type == type_filter)
        if status_filter:
            query = query.filter(MarketingOpportunity.status.in_(self._status_filter_values(status_filter)))
        if brand_filter:
            canonical_brand = self._canonical_brand(brand_filter)
            if canonical_brand == "gelo":
                query = query.filter(func.lower(MarketingOpportunity.brand).like("%gelo%"))
            else:
                query = query.filter(func.lower(MarketingOpportunity.brand) == canonical_brand)
        if min_urgency is not None:
            query = query.filter(MarketingOpportunity.urgency_score >= min_urgency)

        return query.scalar() or 0

    def get_recommendation_by_id(self, opportunity_id: str) -> dict | None:
        row = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )
        if not row:
            return None
        return self._model_to_dict(row, normalize_status=True)

    def generate_action_cards(
        self,
        *,
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        channel_pool: list[str] | None = None,
        region_scope: list[str] | None = None,
        strategy_mode: str = "PLAYBOOK_AI",
        max_cards: int = 4,
        virus_typ: str = "Influenza A",
    ) -> dict:
        """Erzeugt strukturierte Media-Action-Cards für das Cockpit."""
        normalized_mode = str(strategy_mode or "PLAYBOOK_AI").upper()
        generation = self.generate_opportunities()
        opportunities = generation.get("opportunities", [])
        if normalized_mode == "PLAYBOOK_AI" and settings.MEDIA_AI_PLAYBOOKS_ENABLED:
            playbook_cards = self._generate_playbook_ai_cards(
                opportunities=opportunities,
                brand=brand,
                product=product,
                campaign_goal=campaign_goal,
                weekly_budget=weekly_budget,
                region_scope=region_scope,
                max_cards=max_cards,
                virus_typ=virus_typ,
            )
            if playbook_cards:
                playbook_cards.sort(
                    key=lambda x: (float(x.get("urgency_score") or 0.0), float(x.get("confidence") or 0.0)),
                    reverse=True,
                )
                top_card_id = playbook_cards[0]["id"] if playbook_cards else None
                return {
                    "meta": {
                        **generation.get("meta", {}),
                        "strategy_mode": normalized_mode,
                        "cards_generated": len(playbook_cards),
                    },
                    "cards": playbook_cards,
                    "total_cards": len(playbook_cards),
                    "top_card_id": top_card_id,
                    "auto_open_url": f"/dashboard/recommendations/{top_card_id}" if top_card_id else None,
                }

        legacy = self._generate_legacy_action_cards(
            opportunities=opportunities,
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            weekly_budget=weekly_budget,
            channel_pool=channel_pool,
            region_scope=region_scope,
        )
        legacy_meta = legacy.get("meta", {})
        legacy_meta["strategy_mode"] = normalized_mode if normalized_mode != "PLAYBOOK_AI" else "LEGACY_FALLBACK"
        legacy["meta"] = legacy_meta
        return legacy

    def _generate_playbook_ai_cards(
        self,
        *,
        opportunities: list[dict[str, Any]],
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        region_scope: list[str] | None,
        max_cards: int,
        virus_typ: str,
    ) -> list[dict[str, Any]]:
        selection = self.playbook_engine.select_candidates(
            virus_typ=virus_typ,
            region_scope=region_scope,
            max_cards=max_cards,
        )
        candidates = selection.get("selected") or []
        cards: list[dict[str, Any]] = []
        now = datetime.utcnow()
        # Bulk generation must stay fast/reliable for dashboards. We therefore
        # default to deterministic fallback plans and reserve LLM usage for
        # per-card regeneration flows.
        ai_disabled = True
        started = time.monotonic()

        for candidate in candidates:
            # Guard against long-running multi-card generation: once vLLM times out,
            # skip further calls and use deterministic templates to keep API responsive.
            if time.monotonic() - started > 110:
                ai_disabled = True

            playbook_key = str(candidate.get("playbook_key") or "")
            cfg = PLAYBOOK_CATALOG.get(playbook_key) or {}
            if not playbook_key or not cfg:
                continue

            region_code = str(candidate.get("region_code") or "DE")
            region_label = str(candidate.get("region_name") or self._region_label(region_code))
            condition_key = str(candidate.get("condition_key") or cfg.get("condition_key") or "bronchitis_husten")
            synthetic_opportunity = self._synthetic_playbook_opportunity(
                playbook_key=playbook_key,
                region_code=region_code,
                region_label=region_label,
                candidate=candidate,
                now=now,
            )
            opp_id = self._ensure_synthetic_opportunity_row(
                synthetic_opportunity=synthetic_opportunity,
                strategy_mode="PLAYBOOK_AI",
                playbook_key=playbook_key,
            )

            product_mapping = self.product_catalog_service.resolve_product_for_opportunity(
                brand=brand,
                opportunity=synthetic_opportunity,
                fallback_product=product,
            )
            selected_product = self._select_product_for_opportunity(
                fallback_product=product,
                product_mapping=product_mapping,
            )

            trigger_snapshot = candidate.get("trigger_snapshot") or {}
            pack = select_gelo_message_pack(
                brand=brand,
                product=selected_product,
                condition_key=condition_key,
                playbook_key=playbook_key,
                region_code=region_code,
                trigger_event=str(trigger_snapshot.get("event") or ""),
            )
            enriched_candidate = {
                **candidate,
                "message_direction": pack.message_direction,
                "copy_pack": {
                    "status": pack.status,
                    "message_direction": pack.message_direction,
                    "hero_message": pack.hero_message,
                    "support_points": pack.support_points,
                    "creative_angles": pack.creative_angles,
                    "keyword_clusters": pack.keyword_clusters,
                    "cta": pack.cta,
                    "compliance_note": pack.compliance_note,
                    "library_version": pack.library_version,
                    "library_source": pack.library_source,
                },
            }

            ai_generated = self.ai_planner.generate_plan(
                playbook_candidate=enriched_candidate,
                brand=brand,
                product=selected_product,
                campaign_goal=campaign_goal,
                weekly_budget=weekly_budget,
                skip_ollama=ai_disabled,
            )
            # Note: ai_disabled stays True in bulk mode. Single-card regeneration
            # can use vLLM if desired.
            guarded = self.guardrails.apply(
                playbook_key=playbook_key,
                ai_plan=ai_generated.get("ai_plan") or {},
                weekly_budget=weekly_budget,
            )
            ai_plan = guarded["ai_plan"]
            guardrail_report = guarded["guardrail_report"]
            guardrail_notes = guarded["guardrail_notes"]

            peix_score = float(candidate.get("peix_score") or 0.0)
            workflow_status = "READY" if peix_score >= 80.0 else "DRAFT"
            urgency = float(candidate.get("priority_score") or candidate.get("trigger_strength") or 50.0)
            confidence_0_1 = round(float(candidate.get("confidence") or 60.0) / 100.0, 2)
            budget_shift_pct = float(ai_plan.get("budget_shift_pct") or candidate.get("budget_shift_pct") or 0.0)
            budget_shift_value = round((weekly_budget or 0.0) * (abs(budget_shift_pct) / 100.0), 2)
            channel_mix = {
                str(item.get("channel")).lower(): float(item.get("share_pct") or 0.0)
                for item in (ai_plan.get("channel_plan") or [])
                if item.get("channel")
            } or (candidate.get("channel_mix") or {})

            activation_days = int(ai_plan.get("activation_window_days") or 10)
            activation_window = self._derive_activation_window_from_days(activation_days)
            peix_context = {
                "region_code": region_code,
                "score": round(peix_score, 1),
                "band": candidate.get("peix_band"),
                "impact_probability": round(float(candidate.get("impact_probability") or 0.0), 1),
                "drivers": candidate.get("peix_drivers") or [],
                "trigger_event": str(trigger_snapshot.get("event") or ""),
            }

            campaign_payload = self._build_campaign_pack(
                opportunity=synthetic_opportunity,
                brand=brand,
                product=selected_product,
                campaign_goal=campaign_goal,
                region=region_label,
                urgency=urgency,
                confidence=confidence_0_1,
                weekly_budget=weekly_budget,
                budget_shift_pct=budget_shift_pct,
                budget_shift_value=budget_shift_value,
                channel_mix=channel_mix,
                activation_window=activation_window,
                product_mapping={**product_mapping, "condition_key": condition_key},
                region_codes=[region_code] if region_code != "Gesamt" else [],
                peix_context=peix_context,
            )
            self._merge_ai_playbook_payload(
                campaign_payload=campaign_payload,
                playbook_key=playbook_key,
                candidate=enriched_candidate,
                ai_plan=ai_plan,
                ai_generated=ai_generated,
                guardrail_report=guardrail_report,
                workflow_status=workflow_status,
                budget_shift_pct=budget_shift_pct,
                budget_shift_value=budget_shift_value,
                weekly_budget=weekly_budget,
                activation_window=activation_window,
                condition_key=condition_key,
            )

            # Enforce deterministic OTC message framework (avoid LLM drift/hallucinations).
            if "message_framework" not in campaign_payload or not isinstance(campaign_payload["message_framework"], dict):
                campaign_payload["message_framework"] = {}
            campaign_payload["message_framework"].update(pack.to_framework())

            self._enrich_opportunity_for_media(
                opportunity_id=opp_id,
                brand=brand,
                product=selected_product,
                budget_shift_pct=budget_shift_pct,
                channel_mix=channel_mix,
                reason=str(trigger_snapshot.get("event") or "") or playbook_key,
                campaign_payload=campaign_payload,
                status=workflow_status,
                activation_start=self._parse_iso_datetime(activation_window.get("start")),
                activation_end=self._parse_iso_datetime(activation_window.get("end")),
                playbook_key=playbook_key,
                strategy_mode="PLAYBOOK_AI",
            )

            campaign_preview = self._campaign_preview_from_payload(campaign_payload)
            cards.append(
                {
                    "id": opp_id,
                    "status": workflow_status,
                    "type": synthetic_opportunity.get("type", "PLAYBOOK_AI"),
                    "urgency_score": round(urgency, 2),
                    "brand": brand,
                    "product": selected_product,
                    "recommended_product": selected_product,
                    "campaign_goal": campaign_goal,
                    "region": region_code,
                    "region_codes": [region_code],
                    "budget_shift_pct": round(budget_shift_pct, 1),
                    "weekly_budget": round(float(weekly_budget or 0.0), 2),
                    "budget_shift_value": budget_shift_value,
                    "channel_mix": channel_mix,
                    "reason": (candidate.get("trigger_snapshot") or {}).get("details")
                    or (candidate.get("trigger_snapshot") or {}).get("event"),
                    "confidence": confidence_0_1,
                    "activation_window": activation_window,
                    "campaign_preview": campaign_preview,
                    "mapping_status": product_mapping.get("mapping_status"),
                    "mapping_confidence": product_mapping.get("mapping_confidence"),
                    "mapping_reason": product_mapping.get("mapping_reason"),
                    "condition_key": condition_key,
                    "condition_label": product_mapping.get("condition_label"),
                    "mapping_candidate_product": product_mapping.get("candidate_product"),
                    "rule_source": product_mapping.get("rule_source"),
                    "peix_context": peix_context,
                    "campaign_payload": campaign_payload,
                    "detail_url": f"/dashboard/recommendations/{opp_id}",
                    "playbook_key": playbook_key,
                    "playbook_title": cfg.get("title"),
                    "trigger_snapshot": trigger_snapshot,
                    "guardrail_notes": guardrail_notes,
                    "ai_generation_status": ai_generated.get("ai_generation_status"),
                    "strategy_mode": "PLAYBOOK_AI",
                    "copy_status": pack.status,
                }
            )

        return cards

    def _generate_legacy_action_cards(
        self,
        *,
        opportunities: list[dict[str, Any]],
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        channel_pool: list[str] | None,
        region_scope: list[str] | None,
    ) -> dict[str, Any]:
        allowed_regions = [
            self._normalize_region_token(item)
            for item in (region_scope or [])
            if item
        ]
        allowed_region_set = {item for item in allowed_regions if item}
        channels = channel_pool or ["programmatic", "social", "search", "ctv"]
        peix_build = PeixEpiScoreService(self.db).build()
        peix_regions = peix_build.get("regions") or {}

        cards: list[dict[str, Any]] = []
        for opp in opportunities:
            region_codes = self._extract_region_codes_from_opportunity(opp)
            is_national = len(region_codes) == 0

            if allowed_region_set:
                matched = [code for code in region_codes if code in allowed_region_set]
                if matched:
                    selected_region = matched[0]
                elif is_national:
                    selected_region = allowed_regions[0]
                    region_codes = [selected_region]
                else:
                    continue
            else:
                selected_region = region_codes[0] if region_codes else "Gesamt"

            region_label = self._region_label(selected_region)
            peix_context = self._derive_peix_context(peix_regions, selected_region, opp, peix_national=peix_build)

            urgency = float(opp.get("urgency_score") or 50.0)
            budget_shift_pct = round(max(8.0, min(45.0, urgency * 0.4)), 1)
            channel_mix = self._build_channel_mix(channels, opp.get("type", ""), urgency)
            budget_shift_value = round((weekly_budget or 0.0) * (budget_shift_pct / 100.0), 2)
            confidence = round(min(0.98, max(0.45, urgency / 100.0)), 2)
            workflow_status = self._normalize_workflow_status(opp.get("status", "DRAFT"))
            product_mapping = self.product_catalog_service.resolve_product_for_opportunity(
                brand=brand,
                opportunity=opp,
                fallback_product=product,
            )
            selected_product = self._select_product_for_opportunity(
                fallback_product=product,
                product_mapping=product_mapping,
            )

            activation_window = self._derive_activation_window(urgency)
            campaign_payload = self._build_campaign_pack(
                opportunity=opp,
                brand=brand,
                product=selected_product,
                campaign_goal=campaign_goal,
                region=region_label,
                urgency=urgency,
                confidence=confidence,
                weekly_budget=weekly_budget,
                budget_shift_pct=budget_shift_pct,
                budget_shift_value=budget_shift_value,
                channel_mix=channel_mix,
                activation_window=activation_window,
                product_mapping=product_mapping,
                region_codes=region_codes or ([selected_region] if selected_region != "Gesamt" else []),
                peix_context=peix_context,
            )

            opp_id = opp.get("id")
            self._enrich_opportunity_for_media(
                opportunity_id=opp_id,
                brand=brand,
                product=selected_product,
                budget_shift_pct=budget_shift_pct,
                channel_mix=channel_mix,
                reason=opp.get("trigger_context", {}).get("event") or opp.get("type"),
                campaign_payload=campaign_payload,
                status=workflow_status,
                activation_start=self._parse_iso_datetime(activation_window.get("start")),
                activation_end=self._parse_iso_datetime(activation_window.get("end")),
            )

            campaign_preview = self._campaign_preview_from_payload(campaign_payload)
            cards.append(
                {
                    "id": opp_id,
                    "status": workflow_status,
                    "type": opp.get("type", "UNKNOWN"),
                    "urgency_score": urgency,
                    "brand": brand,
                    "product": selected_product,
                    "campaign_goal": campaign_goal,
                    "region": selected_region,
                    "region_codes": region_codes or ([selected_region] if selected_region != "Gesamt" else []),
                    "budget_shift_pct": budget_shift_pct,
                    "weekly_budget": weekly_budget,
                    "budget_shift_value": budget_shift_value,
                    "channel_mix": channel_mix,
                    "reason": opp.get("trigger_context", {}).get("event") or "Epidemiologischer Trigger",
                    "confidence": confidence,
                    "sales_pitch": opp.get("sales_pitch"),
                    "suggested_products": opp.get("suggested_products"),
                    "activation_window": activation_window,
                    "campaign_preview": campaign_preview,
                    "recommended_product": selected_product,
                    "mapping_status": product_mapping.get("mapping_status"),
                    "mapping_confidence": product_mapping.get("mapping_confidence"),
                    "mapping_reason": product_mapping.get("mapping_reason"),
                    "condition_key": product_mapping.get("condition_key"),
                    "condition_label": product_mapping.get("condition_label"),
                    "mapping_candidate_product": product_mapping.get("candidate_product"),
                    "rule_source": product_mapping.get("rule_source"),
                    "peix_context": peix_context,
                    "detail_url": f"/dashboard/recommendations/{opp_id}",
                    "strategy_mode": "LEGACY",
                }
            )

        cards.sort(key=lambda x: (x["urgency_score"], x["confidence"]), reverse=True)
        top_card_id = cards[0]["id"] if cards else None
        return {
            "meta": {"generated_at": datetime.utcnow().isoformat() + "Z"},
            "cards": cards,
            "total_cards": len(cards),
            "top_card_id": top_card_id,
            "auto_open_url": f"/dashboard/recommendations/{top_card_id}" if top_card_id else None,
        }

    @staticmethod
    def _select_product_for_opportunity(
        *,
        fallback_product: str,
        product_mapping: dict[str, Any],
    ) -> str:
        status = str(product_mapping.get("mapping_status") or "").strip().lower()
        if status == "approved":
            recommended = product_mapping.get("recommended_product")
            if recommended:
                return str(recommended)

        # Multi-Produkt-Modus: wenn kein fixes Produkt vorgegeben, bestes
        # Candidate-Produkt aus dem Mapping verwenden (auch bei needs_review).
        is_multi = not fallback_product or "alle" in fallback_product.lower()
        if is_multi:
            candidate = product_mapping.get("candidate_product")
            if candidate:
                return str(candidate)
            # Fallback: SEED_PRODUCTS-Katalog nach condition_key durchsuchen
            condition_key = product_mapping.get("condition_key")
            if condition_key:
                from app.services.marketing_engine.product_matcher import SEED_PRODUCTS
                for seed in SEED_PRODUCTS:
                    if condition_key in seed.get("applicable_conditions", []):
                        return seed["name"]

        if status == "not_applicable":
            return fallback_product or "Produktfreigabe ausstehend"

        return "Produktfreigabe ausstehend"

    def backfill_peix_context(self, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        """Nachträgliches Auffüllen von peix_context für bestehende Recommendations."""
        query = self.db.query(MarketingOpportunity).order_by(MarketingOpportunity.created_at.desc())
        if limit > 0:
            query = query.limit(limit)
        rows = query.all()

        peix_build = PeixEpiScoreService(self.db).build()
        peix_regions = peix_build.get("regions") or {}

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

            region_codes = self._extract_region_codes_from_opportunity(opportunity)
            selected_region = region_codes[0] if region_codes else "Gesamt"
            peix_context = self._derive_peix_context(peix_regions, selected_region, opportunity, peix_national=peix_build)

            if not peix_context:
                skipped_no_region += 1
                continue

            payload["peix_context"] = peix_context
            row.campaign_payload = payload
            row.updated_at = datetime.utcnow()
            updated += 1

        if updated > 0:
            self.db.commit()

        return {
            "success": True,
            "scanned": scanned,
            "updated": updated,
            "skipped_existing": skipped_existing,
            "skipped_no_region": skipped_no_region,
            "force": force,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def backfill_product_mapping(self, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        """Re-resolve product mappings for all existing recommendations.

        Re-runs ``resolve_product_for_opportunity()`` against current
        ``product_condition_mapping`` table and updates stored
        ``campaign_payload.product_mapping`` + ``suggested_products``.
        """
        query = self.db.query(MarketingOpportunity).order_by(MarketingOpportunity.created_at.desc())
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
            brand = str(row.brand or "gelo").strip().lower()

            opp_dict = {
                "region_target": row.region_target or {},
                "campaign_payload": payload,
                "trigger_context": row.trigger_details or {},
            }
            new_pm = self.product_catalog_service.resolve_product_for_opportunity(
                brand=brand,
                opportunity=opp_dict,
                fallback_product=row.product,
            )

            if condition_key and not new_pm.get("condition_key"):
                new_pm["condition_key"] = condition_key
                new_pm["condition_label"] = old_pm.get("condition_label")

            selected = self._select_product_for_opportunity(
                fallback_product=row.product or "Alle Gelo-Produkte",
                product_mapping=new_pm,
            )

            payload["product_mapping"] = new_pm
            row.campaign_payload = payload

            if new_pm.get("recommended_product"):
                products_set = {new_pm["recommended_product"]}
            else:
                products_set = set()
            if new_pm.get("candidate_product"):
                products_set.add(new_pm["candidate_product"])
            old_suggested = row.suggested_products or []
            if isinstance(old_suggested, list):
                for item in old_suggested:
                    name = item if isinstance(item, str) else (item.get("product_name") if isinstance(item, dict) else None)
                    if name and "test" not in name.lower() and "652238" not in name:
                        products_set.add(name)
            row.suggested_products = [{"product_name": p} for p in sorted(products_set) if p]

            row.updated_at = datetime.utcnow()
            updated += 1

        if updated > 0:
            self.db.commit()

        return {
            "success": True,
            "scanned": scanned,
            "updated": updated,
            "skipped_approved": skipped,
            "force": force,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def update_campaign(
        self,
        opportunity_id: str,
        *,
        activation_window: dict | None = None,
        budget: dict | None = None,
        channel_plan: list[dict] | None = None,
        kpi_targets: dict | None = None,
    ) -> dict:
        row = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )
        if not row:
            return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

        payload = (row.campaign_payload or {}).copy()
        payload.setdefault("meta", {
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "generator": "ViralFlux-Media-v3",
        })

        if activation_window:
            start = self._parse_iso_datetime(activation_window.get("start"))
            end = self._parse_iso_datetime(activation_window.get("end"))
            if not start or not end:
                return {"error": "activation_window.start und activation_window.end sind erforderlich"}
            if start > end:
                return {"error": "activation_window.start darf nicht nach activation_window.end liegen"}

            payload["activation_window"] = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "flight_days": max(1, (end - start).days + 1),
            }
            row.activation_start = start
            row.activation_end = end

        if budget:
            weekly = float(budget.get("weekly_budget_eur", 0.0))
            shift_pct = float(budget.get("budget_shift_pct", 0.0))
            if weekly < 0:
                return {"error": "Budgets dürfen nicht negativ sein"}
            if shift_pct > 100 or shift_pct < -100:
                return {"error": "budget_shift_pct muss zwischen -100 und 100 liegen"}

            shift_value = round(weekly * (abs(shift_pct) / 100.0), 2)
            window = payload.get("activation_window") or {}
            flight_days = int(window.get("flight_days") or 7)
            total_flight_budget = round((weekly / 7.0) * flight_days, 2)

            payload["budget_plan"] = {
                "weekly_budget_eur": weekly,
                "budget_shift_pct": shift_pct,
                "budget_shift_value_eur": shift_value,
                "total_flight_budget_eur": total_flight_budget,
                "currency": "EUR",
            }
            row.budget_shift_pct = shift_pct

        if channel_plan is not None:
            if not channel_plan:
                return {"error": "channel_plan darf nicht leer sein"}

            total_share = round(sum(float(item.get("share_pct", 0.0)) for item in channel_plan), 1)
            if abs(total_share - 100.0) > 0.2:
                return {"error": "Channel-Shares müssen in Summe 100 ergeben"}

            budget_plan = payload.get("budget_plan") or {}
            shift_value = abs(float(budget_plan.get("budget_shift_value_eur", 0.0)))

            normalized = []
            mix = {}
            for item in channel_plan:
                channel = str(item.get("channel", "")).strip().lower()
                share = round(float(item.get("share_pct", 0.0)), 1)
                mix[channel] = share
                normalized.append(
                    {
                        "channel": channel,
                        "role": item.get("role") or "reach",
                        "share_pct": share,
                        "budget_eur": round(shift_value * (share / 100.0), 2),
                        "formats": item.get("formats") or [],
                        "message_angle": item.get("message_angle") or "Verfügbarkeit + früher Bedarf",
                        "kpi_primary": item.get("kpi_primary") or "CTR",
                        "kpi_secondary": item.get("kpi_secondary") or ["CPM"],
                    }
                )

            payload["channel_plan"] = normalized
            row.channel_mix = mix

        if kpi_targets:
            measurement = payload.get("measurement_plan") or {}
            measurement["primary_kpi"] = kpi_targets.get("primary_kpi") or measurement.get("primary_kpi")
            measurement["secondary_kpis"] = kpi_targets.get("secondary_kpis") or measurement.get("secondary_kpis") or []
            measurement["success_criteria"] = kpi_targets.get("success_criteria") or measurement.get("success_criteria")
            payload["measurement_plan"] = measurement

        row.campaign_payload = payload
        row.updated_at = datetime.utcnow()
        self.db.commit()
        return self._model_to_dict(row, normalize_status=True)

    def get_playbook_catalog(self) -> dict[str, Any]:
        playbooks = self.playbook_engine.get_catalog()
        return {
            "count": len(playbooks),
            "playbooks": playbooks,
            "strategy_mode": "PLAYBOOK_AI",
        }

    def regenerate_ai_plan(self, opportunity_id: str) -> dict[str, Any]:
        row = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )
        if not row:
            return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

        payload = (row.campaign_payload or {}).copy()
        playbook = payload.get("playbook") or {}
        playbook_key = str(row.playbook_key or playbook.get("key") or "").upper()
        if not playbook_key or playbook_key not in PLAYBOOK_CATALOG:
            return {"error": "Kein gültiges Playbook auf der Recommendation hinterlegt."}

        cfg = PLAYBOOK_CATALOG[playbook_key]
        targeting = payload.get("targeting") or {}
        scope = targeting.get("region_scope")
        if isinstance(scope, list) and scope:
            region_code = self._normalize_region_token(str(scope[0])) or "DE"
        elif isinstance(scope, str):
            region_code = self._normalize_region_token(scope) or "DE"
        else:
            region_code = "DE"

        peix_context = payload.get("peix_context") or {}
        trigger_snapshot = payload.get("trigger_snapshot") or payload.get("trigger_evidence") or {}
        budget_plan = payload.get("budget_plan") or {}
        channel_plan = payload.get("channel_plan") or []
        channel_mix = {}
        for item in channel_plan:
            channel = str(item.get("channel") or "").strip().lower()
            if not channel:
                continue
            channel_mix[channel] = float(item.get("share_pct") or 0.0)
        if not channel_mix:
            channel_mix = cfg.get("default_mix") or {}

        trigger_snapshot = payload.get("trigger_snapshot") or payload.get("trigger_evidence") or {}
        condition_key = (
            playbook.get("condition_key")
            or (payload.get("product_mapping") or {}).get("condition_key")
            or cfg.get("condition_key")
            or "erkaltung_akut"
        )

        # Deterministic OTC copy guardrails for the card detail.
        pack = select_gelo_message_pack(
            brand=row.brand or "gelo",
            product=row.product or "gelomyrtol forte",
            condition_key=str(condition_key),
            playbook_key=playbook_key,
            region_code=region_code,
            trigger_event=str(trigger_snapshot.get("event") or ""),
        )

        candidate = {
            "playbook_key": playbook_key,
            "playbook_title": cfg.get("title"),
            "playbook_kind": cfg.get("kind"),
            "condition_key": str(condition_key),
            "message_direction": pack.message_direction,
            "region_code": region_code,
            "region_name": self._region_label(region_code),
            "impact_probability": float(peix_context.get("impact_probability") or 0.0),
            "peix_score": float(peix_context.get("score") or 0.0),
            "peix_band": peix_context.get("band"),
            "peix_drivers": peix_context.get("drivers") or [],
            "trigger_strength": float((trigger_snapshot.get("values") or {}).get("signal_strength") or 55.0),
            "confidence": float((trigger_snapshot.get("confidence") or 0.65) * 100.0),
            "priority_score": float(row.urgency_score or 55.0),
            "budget_shift_pct": float(budget_plan.get("budget_shift_pct") or row.budget_shift_pct or 0.0),
            "channel_mix": channel_mix,
            "channels": cfg.get("channels") or [],
            "shift_bounds": {"min": cfg.get("shift_min"), "max": cfg.get("shift_max")},
            "trigger_snapshot": trigger_snapshot,
            "copy_pack": {
                "status": pack.status,
                "message_direction": pack.message_direction,
                "hero_message": pack.hero_message,
                "support_points": pack.support_points,
                "creative_angles": pack.creative_angles,
                "keyword_clusters": pack.keyword_clusters,
                "cta": pack.cta,
                "compliance_note": pack.compliance_note,
                "library_version": pack.library_version,
                "library_source": pack.library_source,
            },
        }

        weekly_budget = float(budget_plan.get("weekly_budget_eur") or 0.0)
        objective = ((payload.get("campaign") or {}).get("objective") or "Media-Optimierung")
        generated = self.ai_planner.generate_plan(
            playbook_candidate=candidate,
            brand=row.brand or "PEIX Partner",
            product=row.product or "Atemwegslinie",
            campaign_goal=objective,
            weekly_budget=weekly_budget,
        )
        guarded = self.guardrails.apply(
            playbook_key=playbook_key,
            ai_plan=generated.get("ai_plan") or {},
            weekly_budget=weekly_budget,
        )

        payload["ai_plan"] = guarded["ai_plan"]
        payload["guardrail_report"] = guarded["guardrail_report"]

        # AuditLog: Guardrail-Anwendung dokumentieren
        fixes = guarded.get("guardrail_report", {}).get("applied_fixes", [])
        if fixes:
            self.db.add(AuditLog(
                user="system",
                action="GUARDRAIL_APPLIED",
                entity_type="MarketingOpportunity",
                entity_id=row.id,
                old_value=None,
                new_value="; ".join(fixes),
                reason=row.opportunity_id,
            ))
        payload["ai_meta"] = {
            **(generated.get("ai_meta") or {}),
            "status": generated.get("ai_generation_status"),
            "regenerated_at": datetime.utcnow().isoformat() + "Z",
        }

        # Enforce deterministic OTC message framework (avoid LLM drift/hallucinations).
        if "message_framework" not in payload or not isinstance(payload["message_framework"], dict):
            payload["message_framework"] = {}
        payload["message_framework"].update(pack.to_framework())

        row.campaign_payload = payload
        row.strategy_mode = row.strategy_mode or "PLAYBOOK_AI"
        row.playbook_key = row.playbook_key or playbook_key
        row.updated_at = datetime.utcnow()
        self.db.commit()

        result = self._model_to_dict(row, normalize_status=True)
        result["guardrail_notes"] = guarded.get("guardrail_notes") or []
        result["ai_generation_status"] = generated.get("ai_generation_status")
        return result

    def update_status(
        self,
        opportunity_id: str,
        new_status: str,
        *,
        dismiss_reason: str | None = None,
        dismiss_comment: str | None = None,
    ) -> dict:
        """Status einer Opportunity aktualisieren (Workflow + Legacy kompatibel)."""
        target = self._normalize_workflow_status(new_status)
        if target not in WORKFLOW_STATUSES:
            return {"error": f"Ungültiger Status: {new_status}. Erlaubt: {sorted(WORKFLOW_STATUSES)}"}

        opp = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )
        if not opp:
            return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

        current = self._normalize_workflow_status(opp.status)
        if current != target and target not in ALLOWED_TRANSITIONS.get(current, set()):
            return {"error": f"Ungültiger Transition: {current} -> {target}"}

        old_status = current
        opp.status = target
        opp.updated_at = datetime.utcnow()

        payload = (opp.campaign_payload or {}).copy()
        campaign = (payload.get("campaign") or {}).copy()
        campaign["status"] = target
        payload["campaign"] = campaign

        # Dismiss-Grund persistieren
        if target == "DISMISSED" and (dismiss_reason or dismiss_comment):
            payload["dismiss_info"] = {
                "reason": dismiss_reason or "",
                "comment": (dismiss_comment or "").strip()[:500],
                "dismissed_at": datetime.utcnow().isoformat() + "Z",
            }

        opp.campaign_payload = payload

        # AuditLog
        self.db.add(AuditLog(
            user="system",
            action="STATUS_CHANGE",
            entity_type="MarketingOpportunity",
            entity_id=opp.id,
            old_value=old_status,
            new_value=target,
            reason=opportunity_id,
        ))

        self.db.commit()
        return {
            "opportunity_id": opportunity_id,
            "old_status": old_status,
            "new_status": target,
            "legacy_status": WORKFLOW_TO_LEGACY.get(target, target),
        }

    def export_crm_json(self, opportunity_ids: list[str] | None = None) -> dict:
        """CRM-Export: Markiert Opportunities als exportiert."""
        query = self.db.query(MarketingOpportunity)

        if opportunity_ids:
            query = query.filter(MarketingOpportunity.opportunity_id.in_(opportunity_ids))
        else:
            query = query.filter(
                MarketingOpportunity.status.in_(["NEW", "URGENT", "DRAFT", "READY"])
            )

        results = query.order_by(MarketingOpportunity.urgency_score.desc()).all()

        now = datetime.utcnow()
        for opp in results:
            opp.exported_at = now

        self.db.commit()

        opportunities = [self._model_to_dict(r, normalize_status=True) for r in results]
        return {
            "meta": {
                "generated_at": now.isoformat() + "Z",
                "system_version": SYSTEM_VERSION,
                "total_opportunities": len(opportunities),
                "exported_at": now.isoformat() + "Z",
            },
            "opportunities": opportunities,
        }

    def get_stats(self) -> dict:
        """Aggregierte Statistiken."""
        total = self.db.query(MarketingOpportunity).count()

        by_type = dict(
            self.db.query(
                MarketingOpportunity.opportunity_type,
                func.count(MarketingOpportunity.id),
            )
            .group_by(MarketingOpportunity.opportunity_type)
            .all()
        )

        raw_by_status = dict(
            self.db.query(
                MarketingOpportunity.status,
                func.count(MarketingOpportunity.id),
            )
            .group_by(MarketingOpportunity.status)
            .all()
        )

        by_status: dict[str, int] = {}
        for status, count in raw_by_status.items():
            normalized = self._normalize_workflow_status(status)
            by_status[normalized] = by_status.get(normalized, 0) + count

        avg_urgency = self.db.query(func.avg(MarketingOpportunity.urgency_score)).scalar()

        recent = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.created_at >= datetime.utcnow() - timedelta(days=7))
            .count()
        )

        # Daily breakdown for sparkline (last 7 days)
        daily_counts: list[int] = []
        now = datetime.utcnow()
        for days_ago in range(6, -1, -1):
            day_start = (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = (
                self.db.query(MarketingOpportunity)
                .filter(
                    MarketingOpportunity.created_at >= day_start,
                    MarketingOpportunity.created_at < day_end,
                )
                .count()
            )
            daily_counts.append(count)

        return {
            "total": total,
            "recent_7d": recent,
            "daily_counts_7d": daily_counts,
            "by_type": by_type,
            "by_status": by_status,
            "avg_urgency": round(avg_urgency, 1) if avg_urgency else 0,
        }

    def get_roi_retrospective(self) -> dict:
        """ROI-Retrospektive: Simuliert den Wert vergangener Opportunities.

        Korreliert generierte Empfehlungen mit tatsächlich eingetretenen
        Infektionswellen (SurvStat) und Modell-Genauigkeit (Backtest).
        """
        from app.models.database import BacktestRun, SurvstatWeeklyData

        # 1. Opportunity-Statistiken
        all_opps = self.db.query(MarketingOpportunity).all()
        if not all_opps:
            return {"available": False, "reason": "Keine Opportunities vorhanden"}

        acted_on = [o for o in all_opps if o.status in ("SENT", "APPROVED", "CONVERTED", "ACTIVATED")]
        missed = [o for o in all_opps if o.status in ("EXPIRED", "DISMISSED")]
        pending = [o for o in all_opps if o.status in ("NEW", "URGENT", "DRAFT", "READY")]

        avg_urgency_acted = (
            sum(o.urgency_score for o in acted_on) / len(acted_on)
            if acted_on else 0
        )
        avg_urgency_missed = (
            sum(o.urgency_score for o in missed) / len(missed)
            if missed else 0
        )

        # 2. Modell-Genauigkeit aus letztem Backtest
        latest_backtest = (
            self.db.query(BacktestRun)
            .filter(BacktestRun.status == "success")
            .order_by(BacktestRun.created_at.desc())
            .first()
        )

        model_accuracy = {}
        if latest_backtest and latest_backtest.metrics:
            metrics = latest_backtest.metrics
            model_accuracy = {
                "r2_score": round(metrics.get("r2_score", 0), 3),
                "correlation": round(metrics.get("correlation", 0), 3),
                "mae": round(metrics.get("mae", 0), 1),
            }
            if latest_backtest.improvement_vs_baselines:
                imp = latest_backtest.improvement_vs_baselines
                model_accuracy["improvement_vs_persistence"] = round(
                    imp.get("persistence", {}).get("mae_improvement_pct", 0), 1
                )
                model_accuracy["improvement_vs_seasonal"] = round(
                    imp.get("seasonal_naive", {}).get("mae_improvement_pct", 0), 1
                )

        # 3. SurvStat-Trend: Wie hat sich die Infektionslage nach Opportunity-Erstellung entwickelt?
        signal_accuracy_samples = []
        for opp in all_opps[:30]:  # Max 30 für Performance
            created = opp.created_at
            if not created:
                continue

            # Inzidenz in der Woche der Opportunity-Erstellung
            week_at_creation = (
                self.db.query(SurvstatWeeklyData.incidence)
                .filter(
                    SurvstatWeeklyData.bundesland == "Bundesweit",
                    SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                    SurvstatWeeklyData.week_start <= created,
                )
                .order_by(SurvstatWeeklyData.week_start.desc())
                .first()
            )

            # Inzidenz 2-4 Wochen danach (tatsächlicher Peak)
            peak_after = (
                self.db.query(func.max(SurvstatWeeklyData.incidence))
                .filter(
                    SurvstatWeeklyData.bundesland == "Bundesweit",
                    SurvstatWeeklyData.disease_cluster == "RESPIRATORY",
                    SurvstatWeeklyData.week_start > created,
                    SurvstatWeeklyData.week_start <= created + timedelta(weeks=4),
                )
                .scalar()
            )

            if week_at_creation and week_at_creation[0] and peak_after:
                base = week_at_creation[0]
                if base > 0:
                    demand_increase = round(((peak_after - base) / base) * 100, 1)
                    signal_accuracy_samples.append({
                        "urgency": opp.urgency_score,
                        "demand_increase_pct": demand_increase,
                        "type": opp.opportunity_type,
                    })

        # 4. ROI-Schätzung
        # Konversionsrate der bearbeiteten Opportunities
        converted_count = len([o for o in all_opps if o.status in ("CONVERTED", "ACTIVATED")])
        acted_count = len(acted_on)
        conversion_rate = round((converted_count / acted_count * 100) if acted_count else 0, 1)

        # Geschätzter Markteffekt: Durchschnittliche Nachfrage-Steigerung nach Signalen
        avg_demand_increase = (
            round(sum(s["demand_increase_pct"] for s in signal_accuracy_samples) / len(signal_accuracy_samples), 1)
            if signal_accuracy_samples else 0
        )

        # Korrelation: Urgency Score vs. tatsächliche Nachfrage
        high_urgency_hits = [
            s for s in signal_accuracy_samples
            if s["urgency"] >= 70 and s["demand_increase_pct"] > 0
        ]
        signal_hit_rate = (
            round(len(high_urgency_hits) / len([s for s in signal_accuracy_samples if s["urgency"] >= 70]) * 100, 1)
            if any(s["urgency"] >= 70 for s in signal_accuracy_samples) else 0
        )

        # "Was wäre wenn" — Missed Opportunities Wert
        missed_high_urgency = [o for o in missed if o.urgency_score >= 70]
        missed_value_estimate = len(missed_high_urgency) * (avg_demand_increase / 100 + 1) if avg_demand_increase > 0 else 0

        return {
            "available": True,
            "summary": {
                "total_opportunities": len(all_opps),
                "acted_on": acted_count,
                "missed": len(missed),
                "pending": len(pending),
                "conversion_rate": conversion_rate,
            },
            "urgency_comparison": {
                "avg_urgency_acted": round(avg_urgency_acted, 1),
                "avg_urgency_missed": round(avg_urgency_missed, 1),
            },
            "signal_quality": {
                "avg_demand_increase_pct": avg_demand_increase,
                "signal_hit_rate_pct": signal_hit_rate,
                "samples_analyzed": len(signal_accuracy_samples),
            },
            "model_accuracy": model_accuracy,
            "missed_opportunity_value": {
                "high_urgency_missed": len(missed_high_urgency),
                "estimated_campaigns_lost": len(missed_high_urgency),
                "avg_potential_demand_lift_pct": avg_demand_increase,
            },
            "by_type": {},
        }

    def _save_opportunity(self, opp: dict) -> bool:
        """Opportunity in DB speichern (mit Dedup)."""
        opp_id = opp.get("id", "")
        existing = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opp_id)
            .first()
        )

        # Build conquesting payload for persistence
        conquesting_data = None
        if opp.get("_conquesting_applied"):
            conquesting_data = {
                "is_active": True,
                "multiplier": opp.get("_conquesting_multiplier", 1.0),
                "sku": opp.get("_conquesting_sku", ""),
                "product": opp.get("_conquesting_product", ""),
                "matched_drugs": opp.get("_conquesting_matched_drugs", []),
            }

        if existing:
            existing.urgency_score = opp.get("urgency_score", existing.urgency_score)
            existing.sales_pitch = opp.get("sales_pitch", existing.sales_pitch)
            existing.suggested_products = opp.get("suggested_products", existing.suggested_products)
            if conquesting_data:
                payload = (existing.campaign_payload or {}).copy()
                payload["conquesting"] = conquesting_data
                existing.campaign_payload = payload
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            return False

        trigger_ctx = opp.get("trigger_context", {})
        detected_at_str = trigger_ctx.get("detected_at", "")
        try:
            detected_at = datetime.fromisoformat(detected_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            detected_at = datetime.utcnow()

        campaign_payload = {}
        if conquesting_data:
            campaign_payload["conquesting"] = conquesting_data

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
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
        self.db.add(entry)
        self.db.commit()
        return True

    def _build_channel_mix(self, channels: list[str], opportunity_type: str, urgency: float) -> dict:
        """Erzeugt einfachen Kanalmix abhaengig von Typ und Dringlichkeit."""
        normalized = [c.strip().lower() for c in channels if c and c.strip()]
        if not normalized:
            normalized = ["programmatic", "social", "search", "ctv"]

        if len(normalized) == 1:
            return {normalized[0]: 100}

        base = {c: round(100 / len(normalized), 1) for c in normalized}

        if opportunity_type in {"RESOURCE_SCARCITY", "PREDICTIVE_SALES_SPIKE"} and "search" in base:
            base["search"] = min(55.0, base["search"] + 15.0)
        if urgency >= 75 and "programmatic" in base:
            base["programmatic"] = min(60.0, base["programmatic"] + 10.0)
        if opportunity_type in {"SEASONAL_DEFICIENCY", "WEATHER_FORECAST"} and "social" in base:
            base["social"] = min(50.0, base["social"] + 10.0)

        total = sum(base.values()) or 1.0
        normalized_mix = {k: round(v / total * 100.0, 1) for k, v in base.items()}
        diff = round(100.0 - sum(normalized_mix.values()), 1)
        first_key = next(iter(normalized_mix))
        normalized_mix[first_key] = round(normalized_mix[first_key] + diff, 1)
        return normalized_mix

    def _derive_campaign_name(self, brand: str, product: str, region: str, opportunity_type: str) -> str:
        type_label = opportunity_type.replace("_", " ").title()
        return f"{brand} | {product} | {region} | {type_label}"

    def _derive_activation_window(self, urgency: float) -> dict:
        start = datetime.utcnow()
        days = 14 if urgency >= 70 else 10 if urgency >= 50 else 7
        end = start + timedelta(days=days)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "flight_days": days,
        }

    def _build_channel_plan(
        self,
        channel_mix: dict[str, float],
        budget_shift_value: float,
        campaign_goal: str,
    ) -> list[dict[str, Any]]:
        role_map = {
            "programmatic": "reach",
            "social": "consideration",
            "search": "intent",
            "ctv": "awareness",
        }
        format_map = {
            "programmatic": ["Display", "Video"],
            "social": ["Feed", "Story", "Reel"],
            "search": ["Brand", "Symptom", "Wettbewerb"],
            "ctv": ["Pre-Roll", "Connected TV"],
        }
        kpi_map = {
            "programmatic": "Reach",
            "social": "CTR",
            "search": "Qualified Clicks",
            "ctv": "Completed Views",
        }

        plan = []
        for channel, share in channel_mix.items():
            plan.append(
                {
                    "channel": channel,
                    "role": role_map.get(channel, "reach"),
                    "share_pct": round(float(share), 1),
                    "budget_eur": round(budget_shift_value * (float(share) / 100.0), 2),
                    "formats": format_map.get(channel, ["Standard"]),
                    "message_angle": f"{campaign_goal}: regionaler Trigger + Verfügbarkeit",
                    "kpi_primary": kpi_map.get(channel, "CTR"),
                    "kpi_secondary": ["CPM", "Frequency"],
                }
            )

        plan.sort(key=lambda item: item["share_pct"], reverse=True)
        return plan

    def _build_measurement_plan(self, campaign_goal: str, channel_plan: list[dict]) -> dict:
        primary = "Reach in Trigger-Region" if "awareness" in campaign_goal.lower() else "Qualified Visits"
        if channel_plan:
            primary = channel_plan[0].get("kpi_primary") or primary

        return {
            "primary_kpi": primary,
            "secondary_kpis": ["CTR", "CPM", "Landing Conversion"],
            "reporting_cadence": "Daily",
            "success_criteria": "Steigende KPI in aktivierten Trigger-Regionen bei stabiler Effizienz",
        }

    @staticmethod
    def _derive_activation_window_from_days(days: int) -> dict[str, Any]:
        start = datetime.utcnow()
        duration = max(1, min(28, int(days or 10)))
        end = start + timedelta(days=duration)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "flight_days": duration,
        }

    def _synthetic_playbook_opportunity(
        self,
        *,
        playbook_key: str,
        region_code: str,
        region_label: str,
        candidate: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        trigger = candidate.get("trigger_snapshot") or {}
        audience_map = {
            "MYCOPLASMA_JAEGER": ["Erwachsene mit hartnäckigem Husten", "Hausärzte", "HNO"],
            "SUPPLY_SHOCK_ATTACK": ["Eltern", "Pädiater", "Apotheken-nahe Zielgruppen"],
            "WETTER_REFLEX": ["Pendler", "Berufstätige", "Präventionsorientierte Zielgruppen"],
            "ALLERGIE_BREMSE": ["Allergie-affine Zielgruppen", "Search-Intent mit Heuschnupfen-Kontext"],
        }
        return {
            "id": f"OPP-{now.strftime('%Y-%m-%d')}-AI-{playbook_key[:6]}-{region_code}-{now.strftime('%H%M%S%f')}",
            "type": playbook_key,
            "status": "DRAFT",
            "urgency_score": float(candidate.get("priority_score") or candidate.get("trigger_strength") or 50.0),
            "region_target": {
                "country": "DE",
                "states": [region_code],
                "plz_cluster": "ALL",
            },
            "trigger_context": {
                "source": trigger.get("source") or "PlaybookEngine",
                "event": trigger.get("event") or playbook_key,
                "details": trigger.get("details") or f"{playbook_key} Trigger in {region_label}",
                "detected_at": now.isoformat(),
            },
            "target_audience": audience_map.get(playbook_key) or ["Pharma-Interesse"],
            "sales_pitch": None,
            "suggested_products": [],
        }

    def _ensure_synthetic_opportunity_row(
        self,
        *,
        synthetic_opportunity: dict[str, Any],
        strategy_mode: str,
        playbook_key: str,
    ) -> str:
        trigger_ctx = synthetic_opportunity.get("trigger_context") or {}
        detected_at_raw = trigger_ctx.get("detected_at")
        detected_at = self._parse_iso_datetime(detected_at_raw) or datetime.utcnow()

        entry = MarketingOpportunity(
            opportunity_id=synthetic_opportunity["id"],
            opportunity_type=synthetic_opportunity.get("type", "PLAYBOOK_AI"),
            status=synthetic_opportunity.get("status", "DRAFT"),
            urgency_score=float(synthetic_opportunity.get("urgency_score") or 50.0),
            region_target=synthetic_opportunity.get("region_target"),
            trigger_source=trigger_ctx.get("source"),
            trigger_event=trigger_ctx.get("event"),
            trigger_details=trigger_ctx,
            trigger_detected_at=detected_at,
            target_audience=synthetic_opportunity.get("target_audience"),
            sales_pitch=synthetic_opportunity.get("sales_pitch"),
            suggested_products=synthetic_opportunity.get("suggested_products"),
            strategy_mode=strategy_mode,
            playbook_key=playbook_key,
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
        self.db.add(entry)
        self.db.flush()
        return entry.opportunity_id

    def _merge_ai_playbook_payload(
        self,
        *,
        campaign_payload: dict[str, Any],
        playbook_key: str,
        candidate: dict[str, Any],
        ai_plan: dict[str, Any],
        ai_generated: dict[str, Any],
        guardrail_report: dict[str, Any],
        workflow_status: str,
        budget_shift_pct: float,
        budget_shift_value: float,
        weekly_budget: float,
        activation_window: dict[str, Any],
        condition_key: str,
    ) -> None:
        flight_days = int(activation_window.get("flight_days") or 7)
        campaign_payload["meta"]["version"] = "3.0"
        campaign_payload["meta"]["generator"] = "ViralFlux-Media-v5-PlaybookAI"
        campaign_payload["campaign"]["status"] = workflow_status
        campaign_payload["campaign"]["campaign_name"] = ai_plan.get("campaign_name") or campaign_payload["campaign"]["campaign_name"]
        campaign_payload["campaign"]["objective"] = ai_plan.get("objective") or campaign_payload["campaign"]["objective"]
        campaign_payload["playbook"] = {
            "key": playbook_key,
            "title": candidate.get("playbook_title"),
            "kind": candidate.get("playbook_kind"),
            "message_direction": candidate.get("message_direction"),
            "condition_key": condition_key,
        }
        campaign_payload["trigger_snapshot"] = candidate.get("trigger_snapshot") or {}
        campaign_payload["ai_plan"] = ai_plan
        campaign_payload["guardrail_report"] = guardrail_report
        campaign_payload["ai_meta"] = {
            **(ai_generated.get("ai_meta") or {}),
            "status": ai_generated.get("ai_generation_status"),
        }
        campaign_payload["strategy_mode"] = "PLAYBOOK_AI"
        campaign_payload["trigger_evidence"] = {
            "source": (candidate.get("trigger_snapshot") or {}).get("source"),
            "event": (candidate.get("trigger_snapshot") or {}).get("event"),
            "details": (candidate.get("trigger_snapshot") or {}).get("details"),
            "lead_time_days": (candidate.get("trigger_snapshot") or {}).get("lead_time_days"),
            "confidence": round(float(candidate.get("confidence") or 0.0) / 100.0, 2),
        }
        campaign_payload["budget_plan"] = {
            "weekly_budget_eur": round(float(weekly_budget or 0.0), 2),
            "budget_shift_pct": round(float(budget_shift_pct), 1),
            "budget_shift_value_eur": round(float(budget_shift_value), 2),
            "total_flight_budget_eur": round((float(weekly_budget or 0.0) / 7.0) * flight_days, 2),
            "currency": "EUR",
        }
        if isinstance(ai_plan.get("channel_plan"), list) and ai_plan["channel_plan"]:
            campaign_payload["channel_plan"] = ai_plan["channel_plan"]
        kpi_targets = ai_plan.get("kpi_targets") or {}
        campaign_payload["measurement_plan"] = {
            "primary_kpi": kpi_targets.get("primary_kpi") or campaign_payload.get("measurement_plan", {}).get("primary_kpi"),
            "secondary_kpis": kpi_targets.get("secondary_kpis") or campaign_payload.get("measurement_plan", {}).get("secondary_kpis") or [],
            "reporting_cadence": "Daily",
            "success_criteria": kpi_targets.get("success_criteria") or campaign_payload.get("measurement_plan", {}).get("success_criteria"),
        }
        campaign_payload["message_framework"] = {
            "hero_message": (ai_plan.get("creative_angles") or [campaign_payload.get("message_framework", {}).get("hero_message")])[0],
            "support_points": ai_plan.get("creative_angles") or campaign_payload.get("message_framework", {}).get("support_points") or [],
            "compliance_note": ai_plan.get("compliance_hinweis") or campaign_payload.get("message_framework", {}).get("compliance_note"),
        }
        if isinstance(ai_plan.get("next_steps"), list):
            campaign_payload["execution_checklist"] = [
                {
                    "task": item.get("task"),
                    "owner": item.get("owner"),
                    "eta": item.get("eta"),
                    "status": "open",
                }
                for item in ai_plan.get("next_steps")
                if isinstance(item, dict)
            ]
        campaign_payload["activation_window"] = activation_window

    def _build_campaign_pack(
        self,
        *,
        opportunity: dict,
        brand: str,
        product: str,
        campaign_goal: str,
        region: str,
        urgency: float,
        confidence: float,
        weekly_budget: float,
        budget_shift_pct: float,
        budget_shift_value: float,
        channel_mix: dict,
        activation_window: dict,
        product_mapping: dict,
        region_codes: list[str],
        peix_context: dict[str, Any] | None = None,
    ) -> dict:
        trigger = opportunity.get("trigger_context", {})
        channel_plan = self._build_channel_plan(channel_mix, budget_shift_value, campaign_goal)
        measurement_plan = self._build_measurement_plan(campaign_goal, channel_plan)
        flight_days = int(activation_window.get("flight_days") or 7)

        return {
            "meta": {
                "version": "1.0",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "generator": "ViralFlux-Media-v3",
            },
            "campaign": {
                "campaign_name": self._derive_campaign_name(brand, product, region, opportunity.get("type", "")),
                "objective": campaign_goal,
                "status": "DRAFT",
                "priority": "high" if urgency >= 75 else "medium" if urgency >= 50 else "normal",
            },
            "targeting": {
                "region_scope": region_codes or region,
                "audience_segments": opportunity.get("target_audience") or ["Pharma-Interesse"],
            },
            "activation_window": activation_window,
            "budget_plan": {
                "weekly_budget_eur": round(float(weekly_budget), 2),
                "budget_shift_pct": round(float(budget_shift_pct), 1),
                "budget_shift_value_eur": round(float(budget_shift_value), 2),
                "total_flight_budget_eur": round((float(weekly_budget) / 7.0) * flight_days, 2),
                "currency": "EUR",
            },
            "channel_plan": channel_plan,
            "message_framework": {
                "hero_message": f"{product} jetzt in {region} sichtbar machen, bevor die Nachfragewelle voll einsetzt.",
                "support_points": [
                    "Trigger-basiertes Timing statt Rückspiegel-Steuerung",
                    "Regionale Budgetverschiebung nach epidemiologischen Signalen",
                    "Verfügbarkeitskommunikation bei Wettbewerbsengpässen",
                ],
                "compliance_note": "Claims als Backtest-basiert und konservativ formulieren (z. B. 'kann', 'bis zu').",
            },
            "trigger_evidence": {
                "source": trigger.get("source"),
                "event": trigger.get("event"),
                "details": trigger.get("details"),
                "lead_time_days": 14 if urgency >= 70 else 10,
                "confidence": confidence,
            },
            "product_mapping": {
                "recommended_product": product_mapping.get("recommended_product") or product,
                "mapping_status": product_mapping.get("mapping_status"),
                "mapping_confidence": product_mapping.get("mapping_confidence"),
                "mapping_reason": product_mapping.get("mapping_reason"),
                "condition_key": product_mapping.get("condition_key"),
                "condition_label": product_mapping.get("condition_label"),
                "candidate_product": product_mapping.get("candidate_product"),
                "rule_source": product_mapping.get("rule_source"),
            },
            "peix_context": peix_context or {},
            "measurement_plan": measurement_plan,
            "execution_checklist": [
                {"task": "Media-Flight in DSP/Ads Manager anlegen", "owner": "Media Ops", "eta": "T+0", "status": "open"},
                {"task": "Search-Keyword-Set nach Trigger-Region ausrollen", "owner": "Performance Team", "eta": "T+1", "status": "open"},
                {"task": "Creative-Freigabe mit Compliance abstimmen", "owner": "Account Lead", "eta": "T+1", "status": "open"},
                {"task": "KPI-Dashboard für Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1", "status": "open"},
            ],
        }

    def _campaign_preview_from_payload(self, payload: dict) -> dict:
        campaign = payload.get("campaign") or {}
        budget = payload.get("budget_plan") or {}
        measurement = payload.get("measurement_plan") or {}
        window = payload.get("activation_window") or {}
        product_mapping = payload.get("product_mapping") or {}
        peix_context = payload.get("peix_context") or {}
        playbook = payload.get("playbook") or {}
        ai_meta = payload.get("ai_meta") or {}
        return {
            "campaign_name": campaign.get("campaign_name"),
            "activation_window": {
                "start": window.get("start"),
                "end": window.get("end"),
            },
            "budget": {
                "weekly_budget_eur": budget.get("weekly_budget_eur"),
                "shift_pct": budget.get("budget_shift_pct"),
                "shift_value_eur": budget.get("budget_shift_value_eur"),
                "total_flight_budget_eur": budget.get("total_flight_budget_eur"),
            },
            "primary_kpi": measurement.get("primary_kpi"),
            "recommended_product": product_mapping.get("recommended_product"),
            "mapping_status": product_mapping.get("mapping_status"),
            "mapping_confidence": product_mapping.get("mapping_confidence"),
            "peix_context": peix_context,
            "playbook_key": playbook.get("key"),
            "playbook_title": playbook.get("title"),
            "ai_generation_status": ai_meta.get("status"),
        }

    def _enrich_opportunity_for_media(
        self,
        *,
        opportunity_id: str,
        brand: str,
        product: str,
        budget_shift_pct: float,
        channel_mix: dict,
        reason: str,
        campaign_payload: dict,
        status: str,
        activation_start: datetime | None,
        activation_end: datetime | None,
        playbook_key: str | None = None,
        strategy_mode: str | None = None,
    ) -> None:
        """Persistiert Media-spezifische Attribute auf Opportunity-Ebene."""
        if not opportunity_id:
            return
        row = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )
        if not row:
            return

        now = datetime.utcnow()
        row.brand = self._canonical_brand(brand) or "gelo"
        row.product = product
        row.status = status
        row.budget_shift_pct = budget_shift_pct
        row.channel_mix = channel_mix
        row.activation_start = activation_start
        row.activation_end = activation_end
        row.recommendation_reason = reason
        row.campaign_payload = campaign_payload
        if playbook_key is not None:
            row.playbook_key = playbook_key
        if strategy_mode is not None:
            row.strategy_mode = strategy_mode
        row.updated_at = now
        self.db.commit()

    def _normalize_region_token(self, value: str | None) -> str | None:
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None

        upper = raw.upper()
        if upper in BUNDESLAND_NAMES:
            return upper

        lower = raw.lower()
        if lower in {"gesamt", "all", "de", "national", "deutschland"}:
            return "Gesamt"

        return REGION_NAME_TO_CODE.get(lower)

    @staticmethod
    def _canonical_brand(value: str | None) -> str:
        raw = str(value or "").strip().lower()
        if "gelo" in raw:
            return "gelo"
        return raw

    def _region_label(self, region_code: str) -> str:
        if region_code in BUNDESLAND_NAMES:
            return BUNDESLAND_NAMES[region_code]
        return region_code

    def _extract_region_codes_from_opportunity(self, opportunity: dict[str, Any]) -> list[str]:
        region_target = opportunity.get("region_target") or {}
        campaign_payload = opportunity.get("campaign_payload") or {}
        targeting = campaign_payload.get("targeting") or {}

        tokens: list[str] = []
        states = region_target.get("states")
        if isinstance(states, list):
            tokens.extend(str(item) for item in states if item)

        scope = targeting.get("region_scope")
        if isinstance(scope, list):
            tokens.extend(str(item) for item in scope if item)
        elif isinstance(scope, str) and scope.strip():
            tokens.append(scope)

        region_codes: set[str] = set()
        for token in tokens:
            normalized = self._normalize_region_token(token)
            if normalized == "Gesamt":
                return []
            if normalized:
                region_codes.add(normalized)
        return sorted(region_codes)

    def _derive_peix_context(
        self,
        peix_regions: dict[str, Any],
        selected_region: str,
        opportunity: dict[str, Any],
        *,
        peix_national: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trigger = opportunity.get("trigger_context") or {}

        if selected_region == "Gesamt":
            nat = peix_national or {}
            score = nat.get("national_score")
            if score is None:
                return {}
            return {
                "region_code": "Gesamt",
                "score": score,
                "band": nat.get("national_band"),
                "impact_probability": nat.get("national_impact_probability"),
                "drivers": nat.get("top_drivers") or [],
                "trigger_event": trigger.get("event"),
            }

        peix_entry = peix_regions.get(selected_region) or {}
        return {
            "region_code": selected_region,
            "score": peix_entry.get("score_0_100"),
            "band": peix_entry.get("risk_band"),
            "impact_probability": peix_entry.get("impact_probability"),
            "drivers": peix_entry.get("top_drivers") or [],
            "trigger_event": trigger.get("event"),
        }

    @staticmethod
    def _fact_label(key: str) -> str:
        raw = str(key or "").strip().replace("_", " ")
        if not raw:
            return "Fakt"
        return raw[:1].upper() + raw[1:]

    @staticmethod
    def _confidence_pct(raw_confidence: Any, urgency_score: float | None) -> float:
        parsed: float | None = None
        if raw_confidence is not None:
            try:
                parsed = float(raw_confidence)
            except (TypeError, ValueError):
                parsed = None

        if parsed is None:
            parsed = float(urgency_score or 50.0)
        elif parsed <= 1.0:
            parsed = parsed * 100.0

        return round(max(0.0, min(100.0, float(parsed))), 1)

    @staticmethod
    def _secondary_products(
        suggested_products: Any,
        mapping_candidate_product: str | None,
        primary_product: str | None,
    ) -> list[str]:
        primary = str(primary_product or "").strip().lower()
        out: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            raw = str(value or "").strip()
            if not raw:
                return
            norm = raw.lower()
            if primary and norm == primary:
                return
            if norm in seen:
                return
            seen.add(norm)
            out.append(raw)

        if isinstance(suggested_products, list):
            for item in suggested_products:
                if isinstance(item, str):
                    add(item)
                    continue
                if isinstance(item, dict):
                    add(item.get("product_name") or item.get("product") or item.get("name"))
        add(mapping_candidate_product)
        return out

    def _decision_facts(
        self,
        *,
        trigger_snapshot: dict[str, Any],
        trigger_evidence: dict[str, Any],
        peix_context: dict[str, Any],
        confidence_pct: float,
    ) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        source = (
            trigger_evidence.get("source")
            or trigger_snapshot.get("source")
            or "Signal-Fusion"
        )
        values = trigger_snapshot.get("values")
        if isinstance(values, dict):
            for key in sorted(values.keys()):
                value = values.get(key)
                if isinstance(value, (str, int, float, bool)):
                    facts.append(
                        {
                            "key": str(key),
                            "label": self._fact_label(str(key)),
                            "value": value,
                            "source": source,
                        }
                    )

        event = trigger_evidence.get("event") or trigger_snapshot.get("event")
        if event:
            facts.append(
                {
                    "key": "trigger_event",
                    "label": "Trigger Event",
                    "value": str(event),
                    "source": source,
                }
            )

        lead_time = trigger_evidence.get("lead_time_days") or trigger_snapshot.get("lead_time_days")
        if lead_time is not None:
            facts.append(
                {
                    "key": "lead_time_days",
                    "label": "Modell Lead-Time (Tage)",
                    "value": lead_time,
                    "source": source,
                }
            )

        score = peix_context.get("score")
        if score is not None:
            facts.append(
                {
                    "key": "peix_score",
                    "label": "PeixEpiScore",
                    "value": score,
                    "source": "PeixEpiScore",
                }
            )

        impact = peix_context.get("impact_probability")
        if impact is not None:
            facts.append(
                {
                    "key": "impact_probability",
                    "label": "Impact Probability (%)",
                    "value": impact,
                    "source": "PeixEpiScore",
                }
            )

        facts.append(
            {
                "key": "confidence_pct",
                "label": "Konfidenz (%)",
                "value": confidence_pct,
                "source": source,
            }
        )

        return facts

    def _build_decision_brief(
        self,
        *,
        urgency_score: float | None,
        recommendation_reason: str | None,
        trigger_context: dict[str, Any],
        trigger_snapshot: dict[str, Any],
        trigger_evidence: dict[str, Any],
        peix_context: dict[str, Any],
        region_codes: list[str],
        condition_key: str | None,
        condition_label: str | None,
        recommended_product: str | None,
        mapping_status: str | None,
        mapping_reason: str | None,
        mapping_candidate_product: str | None,
        suggested_products: Any,
        budget_shift_pct: float | None,
        budget_shift_pct_fallback: float | None,
    ) -> dict[str, Any]:
        primary_region_code = region_codes[0] if region_codes else "Gesamt"
        primary_region = (
            "Deutschland"
            if primary_region_code == "Gesamt"
            else self._region_label(primary_region_code)
        )
        secondary_regions = [
            self._region_label(code) if code in BUNDESLAND_NAMES else code
            for code in region_codes[1:]
        ]

        raw_confidence = trigger_evidence.get("confidence")
        if raw_confidence is None:
            raw_confidence = trigger_snapshot.get("confidence")
        confidence_pct = self._confidence_pct(raw_confidence, urgency_score)

        lead_time_days = trigger_evidence.get("lead_time_days") or trigger_snapshot.get("lead_time_days")

        mapping_status_value = str(mapping_status or "").strip().lower() or "needs_review"
        action_required = (
            "review_mapping"
            if mapping_status_value == "needs_review"
            else "ready_for_activation"
        )

        primary_product = str(recommended_product or "").strip() or "Produktfreigabe ausstehend"
        secondary_products = self._secondary_products(
            suggested_products=suggested_products,
            mapping_candidate_product=mapping_candidate_product,
            primary_product=primary_product,
        )

        condition_text = str(condition_label or condition_key or "relevante Lageklasse")
        rationale = (
            str(mapping_reason or "").strip()
            or str(recommendation_reason or "").strip()
            or str(trigger_evidence.get("details") or "").strip()
            or str(trigger_context.get("event") or "").strip()
        )

        basis_parts: list[str] = []
        source_label = trigger_evidence.get("source") or trigger_snapshot.get("source")
        if source_label:
            basis_parts.append(str(source_label))
        event_label = trigger_evidence.get("event") or trigger_snapshot.get("event")
        if event_label:
            basis_parts.append(str(event_label).replace("_", " ").lower())
        score = peix_context.get("score")
        if score is not None:
            try:
                basis_parts.append(f"PeixEpiScore {float(score):.1f}")
            except (TypeError, ValueError):
                basis_parts.append(f"PeixEpiScore {score}")
        if not basis_parts:
            basis_parts.append("aktuellen epidemiologischen Signalen")
        basis_text = " / ".join(basis_parts[:3])

        budget_shift = budget_shift_pct if budget_shift_pct is not None else budget_shift_pct_fallback

        summary_sentence = (
            f"Auf Basis von {basis_text} erwarten wir in den nächsten 7-14 Tagen "
            f"{condition_text} in {primary_region}; daher empfehlen wir {primary_product}."
        )

        return {
            "summary_sentence": summary_sentence,
            "horizon": {
                "min_days": 7,
                "max_days": 14,
                "model_lead_time_days": lead_time_days,
            },
            "facts": self._decision_facts(
                trigger_snapshot=trigger_snapshot,
                trigger_evidence=trigger_evidence,
                peix_context=peix_context,
                confidence_pct=confidence_pct,
            ),
            "expectation": {
                "condition_key": condition_key,
                "condition_label": condition_label,
                "region_codes": region_codes,
                "impact_probability": peix_context.get("impact_probability"),
                "peix_score": peix_context.get("score"),
                "confidence_pct": confidence_pct,
                "rationale": rationale,
            },
            "recommendation": {
                "primary_product": primary_product,
                "primary_region": primary_region,
                "secondary_regions": secondary_regions,
                "secondary_products": secondary_products,
                "budget_shift_pct": budget_shift,
                "mapping_status": mapping_status_value,
                "mapping_reason": mapping_reason,
                "action_required": action_required,
            },
        }

    def _clean_for_output(self, opp: dict) -> dict:
        """Entfernt interne _-Felder und promotiert Conquesting-Felder für den API-Output."""
        clean = {k: v for k, v in opp.items() if not k.startswith("_")}

        # Promote conquesting metadata to public API fields
        clean["is_conquesting_active"] = bool(opp.get("_conquesting_applied", False))
        if clean["is_conquesting_active"]:
            matched_drugs = opp.get("_conquesting_matched_drugs", [])
            clean["competitor_shortage_ingredient"] = ", ".join(matched_drugs[:3]) if matched_drugs else ""
            clean["recommended_bid_modifier"] = float(opp.get("_conquesting_multiplier", 1.0))
            clean["conquesting_product"] = opp.get("_conquesting_product", "")
        else:
            clean["competitor_shortage_ingredient"] = ""
            clean["recommended_bid_modifier"] = 1.0
            clean["conquesting_product"] = ""

        return clean

    def _normalize_workflow_status(self, status: str | None) -> str:
        if not status:
            return "DRAFT"
        normalized = str(status).upper()
        if normalized in WORKFLOW_STATUSES:
            return normalized
        return LEGACY_TO_WORKFLOW.get(normalized, normalized)

    def _status_filter_values(self, status_filter: str) -> set[str]:
        normalized = self._normalize_workflow_status(status_filter)
        values = {normalized, status_filter.upper()}
        if normalized == "DRAFT":
            values.update({"NEW", "URGENT"})
        if normalized == "APPROVED":
            values.add("SENT")
        if normalized == "ACTIVATED":
            values.add("CONVERTED")
        return values

    def _parse_iso_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _model_to_dict(self, m: MarketingOpportunity, normalize_status: bool = True) -> dict:
        """Konvertiert DB-Model zu Output-Dict."""
        status = self._normalize_workflow_status(m.status) if normalize_status else m.status
        campaign_payload = m.campaign_payload or {}
        campaign_preview = self._campaign_preview_from_payload(campaign_payload) if campaign_payload else None
        product_mapping = campaign_payload.get("product_mapping") or {}
        peix_context = campaign_payload.get("peix_context") or {}
        playbook = campaign_payload.get("playbook") or {}
        ai_meta = campaign_payload.get("ai_meta") or {}
        region_codes = self._extract_region_codes_from_opportunity(
            {
                "region_target": m.region_target or {},
                "campaign_payload": campaign_payload,
            }
        )
        trigger_context = (
            m.trigger_details
            or {
                "source": m.trigger_source,
                "event": m.trigger_event,
                "detected_at": m.trigger_detected_at.isoformat() if m.trigger_detected_at else None,
            }
        )
        recommended_product = product_mapping.get("recommended_product") or m.product
        decision_brief = self._build_decision_brief(
            urgency_score=m.urgency_score,
            recommendation_reason=m.recommendation_reason,
            trigger_context=trigger_context,
            trigger_snapshot=campaign_payload.get("trigger_snapshot") or {},
            trigger_evidence=campaign_payload.get("trigger_evidence") or {},
            peix_context=peix_context,
            region_codes=region_codes,
            condition_key=product_mapping.get("condition_key"),
            condition_label=product_mapping.get("condition_label"),
            recommended_product=recommended_product,
            mapping_status=product_mapping.get("mapping_status"),
            mapping_reason=product_mapping.get("mapping_reason"),
            mapping_candidate_product=product_mapping.get("candidate_product"),
            suggested_products=m.suggested_products,
            budget_shift_pct=m.budget_shift_pct,
            budget_shift_pct_fallback=(campaign_payload.get("budget_plan") or {}).get("budget_shift_pct"),
        )

        return {
            "id": m.opportunity_id,
            "type": m.opportunity_type,
            "status": status,
            "legacy_status": WORKFLOW_TO_LEGACY.get(status, m.status),
            "urgency_score": m.urgency_score,
            "region_target": m.region_target,
            "trigger_context": trigger_context,
            "target_audience": m.target_audience,
            "sales_pitch": m.sales_pitch,
            "suggested_products": m.suggested_products,
            "brand": m.brand,
            "product": m.product,
            "region": region_codes[0] if region_codes else "Gesamt",
            "region_codes": region_codes,
            "budget_shift_pct": m.budget_shift_pct,
            "channel_mix": m.channel_mix,
            "activation_start": m.activation_start.isoformat() if m.activation_start else None,
            "activation_end": m.activation_end.isoformat() if m.activation_end else None,
            "recommendation_reason": m.recommendation_reason,
            "campaign_payload": campaign_payload,
            "campaign_preview": campaign_preview,
            "recommended_product": recommended_product,
            "mapping_status": product_mapping.get("mapping_status"),
            "mapping_confidence": product_mapping.get("mapping_confidence"),
            "mapping_reason": product_mapping.get("mapping_reason"),
            "condition_key": product_mapping.get("condition_key"),
            "condition_label": product_mapping.get("condition_label"),
            "mapping_candidate_product": product_mapping.get("candidate_product"),
            "rule_source": product_mapping.get("rule_source"),
            "peix_context": peix_context,
            "playbook_key": m.playbook_key or playbook.get("key"),
            "playbook_title": playbook.get("title"),
            "strategy_mode": m.strategy_mode or campaign_payload.get("strategy_mode"),
            "trigger_snapshot": campaign_payload.get("trigger_snapshot"),
            "guardrail_notes": (campaign_payload.get("guardrail_report") or {}).get("applied_fixes"),
            "ai_generation_status": ai_meta.get("status"),
            "trigger_evidence": (campaign_payload or {}).get("trigger_evidence"),
            "decision_brief": decision_brief,
            "detail_url": f"/dashboard/recommendations/{m.opportunity_id}",
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            "exported_at": m.exported_at.isoformat() if m.exported_at else None,
            # Conquesting fields (from persisted campaign_payload)
            "is_conquesting_active": bool((campaign_payload.get("conquesting") or {}).get("is_active", False)),
            "competitor_shortage_ingredient": ", ".join(
                (campaign_payload.get("conquesting") or {}).get("matched_drugs", [])[:3]
            ),
            "recommended_bid_modifier": float(
                (campaign_payload.get("conquesting") or {}).get("multiplier", 1.0)
            ),
            "conquesting_product": (campaign_payload.get("conquesting") or {}).get("product", ""),
        }
