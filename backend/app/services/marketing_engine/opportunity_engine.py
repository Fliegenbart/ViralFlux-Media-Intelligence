"""MarketingOpportunityEngine — Hauptorchestrator.

Fuehrt alle Detektoren aus, erzeugt Sales Pitches, matcht Produkte,
persistiert Opportunities und liefert CRM-faehiges JSON.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import MarketingOpportunity
from app.services.media.product_catalog_service import ProductCatalogService
from app.services.media.peix_score_service import PeixEpiScoreService

from .detectors.predictive_sales_spike import PredictiveSalesSpikeDetector
from .detectors.resource_scarcity import ResourceScarcityDetector
from .detectors.seasonal_deficiency import SeasonalDeficiencyDetector
from .detectors.weather_forecast import WeatherForecastDetector
from .pitch_generator import PitchGenerator
from .product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SYSTEM_VERSION = "ViralFlux-Media-v3.0"

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
            SeasonalDeficiencyDetector(db),
            PredictiveSalesSpikeDetector(db),
            WeatherForecastDetector(db),
        ]
        self.pitch_generator = PitchGenerator()
        self.product_matcher = ProductMatcher(db)
        self.product_catalog_service = ProductCatalogService(db)

    def generate_opportunities(self) -> dict:
        """Alle Detektoren ausfuehren -> Pitches -> Products -> Persist -> JSON."""
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

    def get_opportunities(
        self,
        type_filter: str | None = None,
        status_filter: str | None = None,
        brand_filter: str | None = None,
        min_urgency: float | None = None,
        limit: int = 50,
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
            query = query.filter(MarketingOpportunity.brand == brand_filter)
        if min_urgency is not None:
            query = query.filter(MarketingOpportunity.urgency_score >= min_urgency)

        results = query.limit(limit).all()
        return [self._model_to_dict(r, normalize_status=normalize_status) for r in results]

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
    ) -> dict:
        """Erzeugt strukturierte Media-Action-Cards fuer das Cockpit."""
        generation = self.generate_opportunities()
        opportunities = generation.get("opportunities", [])
        allowed_regions = [
            self._normalize_region_token(item)
            for item in (region_scope or [])
            if item
        ]
        allowed_region_set = {item for item in allowed_regions if item}
        channels = channel_pool or ["programmatic", "social", "search", "ctv"]
        peix_regions = (PeixEpiScoreService(self.db).build().get("regions") or {})

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
            peix_context = self._derive_peix_context(peix_regions, selected_region, opp)

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
            selected_product = product_mapping.get("recommended_product") or product

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
                }
            )

        cards.sort(key=lambda x: (x["urgency_score"], x["confidence"]), reverse=True)
        top_card_id = cards[0]["id"] if cards else None
        return {
            "meta": generation.get("meta", {}),
            "cards": cards,
            "total_cards": len(cards),
            "top_card_id": top_card_id,
            "auto_open_url": f"/dashboard/recommendations/{top_card_id}" if top_card_id else None,
        }

    def backfill_peix_context(self, *, force: bool = False, limit: int = 1000) -> dict[str, Any]:
        """Nachtraegliches Auffuellen von peix_context fuer bestehende Recommendations."""
        query = self.db.query(MarketingOpportunity).order_by(MarketingOpportunity.created_at.desc())
        if limit > 0:
            query = query.limit(limit)
        rows = query.all()

        peix_regions = (PeixEpiScoreService(self.db).build().get("regions") or {})

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
            peix_context = self._derive_peix_context(peix_regions, selected_region, opportunity)

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
            if weekly < 0 or shift_pct < 0:
                return {"error": "Budgets duerfen nicht negativ sein"}
            if shift_pct > 100:
                return {"error": "budget_shift_pct darf maximal 100 sein"}

            shift_value = round(weekly * (shift_pct / 100.0), 2)
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
                return {"error": "Channel-Shares muessen in Summe 100 ergeben"}

            budget_plan = payload.get("budget_plan") or {}
            shift_value = float(budget_plan.get("budget_shift_value_eur", 0.0))

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
                        "message_angle": item.get("message_angle") or "Verfuegbarkeit + frueher Bedarf",
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

    def update_status(self, opportunity_id: str, new_status: str) -> dict:
        """Status einer Opportunity aktualisieren (Workflow + Legacy kompatibel)."""
        target = self._normalize_workflow_status(new_status)
        if target not in WORKFLOW_STATUSES:
            return {"error": f"Ungueltiger Status: {new_status}. Erlaubt: {sorted(WORKFLOW_STATUSES)}"}

        opp = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )
        if not opp:
            return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

        current = self._normalize_workflow_status(opp.status)
        if current != target and target not in ALLOWED_TRANSITIONS.get(current, set()):
            return {"error": f"Ungueltiger Transition: {current} -> {target}"}

        opp.status = target
        opp.updated_at = datetime.utcnow()

        payload = (opp.campaign_payload or {}).copy()
        campaign = (payload.get("campaign") or {}).copy()
        campaign["status"] = target
        payload["campaign"] = campaign
        opp.campaign_payload = payload

        self.db.commit()
        return {
            "opportunity_id": opportunity_id,
            "old_status": current,
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

        return {
            "total": total,
            "recent_7d": recent,
            "by_type": by_type,
            "by_status": by_status,
            "avg_urgency": round(avg_urgency, 1) if avg_urgency else 0,
        }

    def _save_opportunity(self, opp: dict) -> bool:
        """Opportunity in DB speichern (mit Dedup)."""
        opp_id = opp.get("id", "")
        existing = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opp_id)
            .first()
        )
        if existing:
            existing.urgency_score = opp.get("urgency_score", existing.urgency_score)
            existing.sales_pitch = opp.get("sales_pitch", existing.sales_pitch)
            existing.suggested_products = opp.get("suggested_products", existing.suggested_products)
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            return False

        trigger_ctx = opp.get("trigger_context", {})
        detected_at_str = trigger_ctx.get("detected_at", "")
        try:
            detected_at = datetime.fromisoformat(detected_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            detected_at = datetime.utcnow()

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
                    "message_angle": f"{campaign_goal}: regionaler Trigger + Verfuegbarkeit",
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
                    "Trigger-basiertes Timing statt Rueckspiegel-Steuerung",
                    "Regionale Budgetverschiebung nach epidemiologischen Signalen",
                    "Verfuegbarkeitskommunikation bei Wettbewerbsengpaessen",
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
                {"task": "KPI-Dashboard fuer Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1", "status": "open"},
            ],
        }

    def _campaign_preview_from_payload(self, payload: dict) -> dict:
        campaign = payload.get("campaign") or {}
        budget = payload.get("budget_plan") or {}
        measurement = payload.get("measurement_plan") or {}
        window = payload.get("activation_window") or {}
        product_mapping = payload.get("product_mapping") or {}
        peix_context = payload.get("peix_context") or {}
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
        row.brand = brand
        row.product = product
        row.status = status
        row.budget_shift_pct = budget_shift_pct
        row.channel_mix = channel_mix
        row.activation_start = activation_start
        row.activation_end = activation_end
        row.recommendation_reason = reason
        row.campaign_payload = campaign_payload
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
    ) -> dict[str, Any]:
        if selected_region == "Gesamt":
            return {}

        peix_entry = peix_regions.get(selected_region) or {}
        trigger = opportunity.get("trigger_context") or {}
        return {
            "region_code": selected_region,
            "score": peix_entry.get("score_0_100"),
            "band": peix_entry.get("risk_band"),
            "impact_probability": peix_entry.get("impact_probability"),
            "drivers": peix_entry.get("top_drivers") or [],
            "trigger_event": trigger.get("event"),
        }

    def _clean_for_output(self, opp: dict) -> dict:
        """Entfernt interne _-Felder fuer den API-Output."""
        return {k: v for k, v in opp.items() if not k.startswith("_")}

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
        region_codes = self._extract_region_codes_from_opportunity(
            {
                "region_target": m.region_target or {},
                "campaign_payload": campaign_payload,
            }
        )

        return {
            "id": m.opportunity_id,
            "type": m.opportunity_type,
            "status": status,
            "legacy_status": WORKFLOW_TO_LEGACY.get(status, m.status),
            "urgency_score": m.urgency_score,
            "region_target": m.region_target,
            "trigger_context": m.trigger_details
            or {
                "source": m.trigger_source,
                "event": m.trigger_event,
                "detected_at": m.trigger_detected_at.isoformat() if m.trigger_detected_at else None,
            },
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
            "recommended_product": product_mapping.get("recommended_product") or m.product,
            "mapping_status": product_mapping.get("mapping_status"),
            "mapping_confidence": product_mapping.get("mapping_confidence"),
            "mapping_reason": product_mapping.get("mapping_reason"),
            "condition_key": product_mapping.get("condition_key"),
            "condition_label": product_mapping.get("condition_label"),
            "mapping_candidate_product": product_mapping.get("candidate_product"),
            "rule_source": product_mapping.get("rule_source"),
            "peix_context": peix_context,
            "trigger_evidence": (campaign_payload or {}).get("trigger_evidence"),
            "detail_url": f"/dashboard/recommendations/{m.opportunity_id}",
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            "exported_at": m.exported_at.isoformat() if m.exported_at else None,
        }
