"""Playbook and campaign-building helpers for the marketing opportunity engine."""

from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import TYPE_CHECKING, Any

from app.core.time import utc_now
from app.models.database import AuditLog, MarketingOpportunity
from app.services.media.message_library import select_gelo_message_pack
from app.services.media.ranking_signal_service import RankingSignalService
from app.services.media.playbook_engine import PLAYBOOK_CATALOG
from app.services.media.semantic_contracts import (
    forecast_probability_contract,
    priority_score_contract,
    ranking_signal_contract,
    signal_confidence_contract,
)

if TYPE_CHECKING:
    from .opportunity_engine import MarketingOpportunityEngine


def generate_playbook_ai_cards(
    engine: "MarketingOpportunityEngine",
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
    candidates = engine._forecast_first_candidates(
        opportunities=opportunities,
        brand=brand,
        virus_typ=virus_typ,
        region_scope=region_scope,
        max_cards=max_cards,
    )
    cards: list[dict[str, Any]] = []
    now = utc_now()
    ai_disabled = True
    started = time.monotonic()
    latest_market_backtest = engine._latest_market_backtest(virus_typ=virus_typ)

    for candidate in candidates:
        if time.monotonic() - started > 110:
            ai_disabled = True

        playbook_key = str(candidate.get("playbook_key") or "")
        cfg = PLAYBOOK_CATALOG.get(playbook_key) or {}
        if not playbook_key or not cfg:
            continue

        region_code = str(candidate.get("region_code") or "DE")
        region_name = str(candidate.get("region_name") or engine._region_label(region_code))
        condition_key = str(candidate.get("condition_key") or cfg.get("condition_key") or "bronchitis_husten")
        synthetic_opportunity = engine._synthetic_playbook_opportunity(
            playbook_key=playbook_key,
            region_code=region_code,
            region_label=region_name,
            candidate=candidate,
            now=now,
        )
        opp_id = engine._ensure_synthetic_opportunity_row(
            synthetic_opportunity=synthetic_opportunity,
            strategy_mode="PLAYBOOK_AI",
            playbook_key=playbook_key,
        )

        product_mapping = engine.product_catalog_service.resolve_product_for_opportunity(
            brand=brand,
            opportunity=synthetic_opportunity,
            fallback_product=product,
        )
        selected_product = engine._select_product_for_opportunity(
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
            "forecast_assessment": {
                "forecast_quality": candidate.get("forecast_quality") or {},
                "event_forecast": candidate.get("event_forecast") or {},
            },
            "opportunity_assessment": candidate.get("opportunity_assessment") or {},
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

        ai_generated = engine.ai_planner.generate_plan(
            playbook_candidate=enriched_candidate,
            brand=brand,
            product=selected_product,
            campaign_goal=campaign_goal,
            weekly_budget=weekly_budget,
            skip_llm=ai_disabled,
        )
        guarded = engine.guardrails.apply(
            playbook_key=playbook_key,
            ai_plan=ai_generated.get("ai_plan") or {},
            weekly_budget=weekly_budget,
        )
        ai_plan = guarded["ai_plan"]
        guardrail_report = guarded["guardrail_report"]
        guardrail_notes = guarded["guardrail_notes"]

        forecast_quality = candidate.get("forecast_quality") or {}
        event_forecast = candidate.get("event_forecast") or {}
        opportunity_assessment = candidate.get("opportunity_assessment") or {}
        exploratory_signals = candidate.get("exploratory_signals") or []
        model_readiness_status = str(forecast_quality.get("forecast_readiness") or "WATCH")
        workflow_status = (
            "READY"
            if model_readiness_status == "GO"
            and str(opportunity_assessment.get("action_class") or "") == "customer_lift_ready"
            else "DRAFT"
        )
        urgency = float(candidate.get("priority_score") or candidate.get("trigger_strength") or 50.0)
        confidence_0_1 = round(float(candidate.get("confidence") or 60.0) / 100.0, 2)
        budget_shift_pct = float(
            candidate.get("budget_shift_pct")
            if candidate.get("budget_shift_pct") is not None
            else (ai_plan.get("budget_shift_pct") or 0.0)
        )
        budget_shift_value = round((weekly_budget or 0.0) * (abs(budget_shift_pct) / 100.0), 2)
        channel_mix = {
            str(item.get("channel")).lower(): float(item.get("share_pct") or 0.0)
            for item in (ai_plan.get("channel_plan") or [])
            if item.get("channel")
        } or (candidate.get("channel_mix") or {})

        activation_days = int(ai_plan.get("activation_window_days") or 10)
        activation_window = engine._derive_activation_window_from_days(activation_days)
        ranking_signal_context = {
            "region_code": region_code,
            "score": round(urgency, 1),
            "signal_score": round(float(candidate.get("signal_score") or candidate.get("impact_probability") or urgency), 1),
            "ranking_signal_score": round(float(candidate.get("signal_score") or candidate.get("impact_probability") or urgency), 1),
            "band": "ready" if model_readiness_status == "GO" else "watch",
            "signal_band": "ready" if model_readiness_status == "GO" else "watch",
            "impact_probability": (
                round(float(candidate.get("impact_probability") or 0.0), 1)
                if candidate.get("impact_probability") is not None
                else None
            ),
            "drivers": exploratory_signals,
            "signal_drivers": exploratory_signals,
            "trigger_event": str(trigger_snapshot.get("event") or ""),
            "model_readiness_status": model_readiness_status,
            "model_backtest_run_id": latest_market_backtest.run_id if latest_market_backtest else None,
        }
        campaign_payload_signal_contracts = {
            "signal_score": ranking_signal_contract(source="ForecastDecisionService"),
            "priority_score": priority_score_contract(source="MarketingOpportunityEngine"),
            "signal_confidence_pct": signal_confidence_contract(
                source="ForecastDecisionService",
                derived_from="event_forecast.confidence",
            ),
            "event_probability": forecast_probability_contract(),
        }

        campaign_payload = engine._build_campaign_pack(
            opportunity=synthetic_opportunity,
            brand=brand,
            product=selected_product,
            campaign_goal=campaign_goal,
            region=region_name,
            urgency=urgency,
            confidence=confidence_0_1,
            weekly_budget=weekly_budget,
            budget_shift_pct=budget_shift_pct,
            budget_shift_value=budget_shift_value,
            channel_mix=channel_mix,
            activation_window=activation_window,
            product_mapping={**product_mapping, "condition_key": condition_key},
            region_codes=[region_code] if region_code != "Gesamt" else [],
            peix_context=ranking_signal_context,
        )
        campaign_payload["forecast_assessment"] = {
            "forecast_quality": forecast_quality,
            "event_forecast": event_forecast,
        }
        campaign_payload["opportunity_assessment"] = opportunity_assessment
        campaign_payload["exploratory_signals"] = exploratory_signals
        campaign_payload["signal_contracts"] = campaign_payload_signal_contracts
        engine._merge_ai_playbook_payload(
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

        if "message_framework" not in campaign_payload or not isinstance(campaign_payload["message_framework"], dict):
            campaign_payload["message_framework"] = {}
        campaign_payload["message_framework"].update(pack.to_framework())

        engine._enrich_opportunity_for_media(
            opportunity_id=opp_id,
            brand=brand,
            product=selected_product,
            budget_shift_pct=budget_shift_pct,
            channel_mix=channel_mix,
            reason=str(trigger_snapshot.get("event") or "") or playbook_key,
            campaign_payload=campaign_payload,
            status=workflow_status,
            activation_start=engine._parse_iso_datetime(activation_window.get("start")),
            activation_end=engine._parse_iso_datetime(activation_window.get("end")),
            playbook_key=playbook_key,
            strategy_mode="PLAYBOOK_AI",
        )

        campaign_preview = engine._campaign_preview_from_payload(campaign_payload)
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
                "peix_context": ranking_signal_context,
                "ranking_signal_context": ranking_signal_context,
                "campaign_payload": campaign_payload,
                "detail_url": f"/kampagnen/{opp_id}",
                "playbook_key": playbook_key,
                "playbook_title": cfg.get("title"),
                "trigger_snapshot": trigger_snapshot,
                "guardrail_notes": guardrail_notes,
                "ai_generation_status": ai_generated.get("ai_generation_status"),
                "strategy_mode": "PLAYBOOK_AI",
                "copy_status": pack.status,
                "model_readiness_status": model_readiness_status,
                "forecast_assessment": campaign_payload.get("forecast_assessment"),
                "opportunity_assessment": campaign_payload.get("opportunity_assessment"),
                "exploratory_signals": exploratory_signals,
            }
        )

    return cards


def generate_rule_based_action_cards(
    engine: "MarketingOpportunityEngine",
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
        engine._normalize_region_token(item)
        for item in (region_scope or [])
        if item
    ]
    allowed_region_set = {item for item in allowed_regions if item}
    channels = channel_pool or ["programmatic", "social", "search", "ctv"]
    peix_build = RankingSignalService(engine.db).build()
    peix_regions = peix_build.get("regions") or {}

    cards: list[dict[str, Any]] = []
    for opp in opportunities:
        region_codes = engine._extract_region_codes_from_opportunity(opp)
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

        region_name = engine._region_label(selected_region)
        ranking_signal_context = engine._derive_ranking_signal_context(
            peix_regions,
            selected_region,
            opp,
            ranking_signal_national=peix_build,
        )

        urgency = float(opp.get("urgency_score") or 50.0)
        budget_shift_pct = round(max(8.0, min(45.0, urgency * 0.4)), 1)
        channel_mix = engine._build_channel_mix(channels, opp.get("type", ""), urgency)
        budget_shift_value = round((weekly_budget or 0.0) * (budget_shift_pct / 100.0), 2)
        confidence = round(min(0.98, max(0.45, urgency / 100.0)), 2)
        workflow_status = engine._normalize_workflow_status(opp.get("status", "DRAFT"))
        product_mapping = engine.product_catalog_service.resolve_product_for_opportunity(
            brand=brand,
            opportunity=opp,
            fallback_product=product,
        )
        selected_product = engine._select_product_for_opportunity(
            fallback_product=product,
            product_mapping=product_mapping,
        )

        activation_window = engine._derive_activation_window(urgency)
        campaign_payload = engine._build_campaign_pack(
            opportunity=opp,
            brand=brand,
            product=selected_product,
            campaign_goal=campaign_goal,
            region=region_name,
            urgency=urgency,
            confidence=confidence,
            weekly_budget=weekly_budget,
            budget_shift_pct=budget_shift_pct,
            budget_shift_value=budget_shift_value,
            channel_mix=channel_mix,
            activation_window=activation_window,
            product_mapping=product_mapping,
            region_codes=region_codes or ([selected_region] if selected_region != "Gesamt" else []),
            peix_context=ranking_signal_context,
        )

        opp_id = opp.get("id")
        engine._enrich_opportunity_for_media(
            opportunity_id=opp_id,
            brand=brand,
            product=selected_product,
            budget_shift_pct=budget_shift_pct,
            channel_mix=channel_mix,
            reason=opp.get("trigger_context", {}).get("event") or opp.get("type"),
            campaign_payload=campaign_payload,
            status=workflow_status,
            activation_start=engine._parse_iso_datetime(activation_window.get("start")),
            activation_end=engine._parse_iso_datetime(activation_window.get("end")),
        )

        campaign_preview = engine._campaign_preview_from_payload(campaign_payload)
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
                "peix_context": ranking_signal_context,
                "ranking_signal_context": ranking_signal_context,
                "detail_url": f"/kampagnen/{opp_id}",
                "strategy_mode": "RULE_BASED",
            }
        )

    cards.sort(key=lambda item: (item["urgency_score"], item["confidence"]), reverse=True)
    top_card_id = cards[0]["id"] if cards else None
    return {
        "meta": {"generated_at": utc_now().isoformat() + "Z"},
        "cards": cards,
        "total_cards": len(cards),
        "top_card_id": top_card_id,
        "auto_open_url": f"/kampagnen/{top_card_id}" if top_card_id else None,
    }


def get_playbook_catalog(engine: "MarketingOpportunityEngine") -> dict[str, Any]:
    playbooks = engine.playbook_engine.get_catalog()
    return {
        "count": len(playbooks),
        "playbooks": playbooks,
        "strategy_mode": "PLAYBOOK_AI",
    }


def regenerate_ai_plan(engine: "MarketingOpportunityEngine", opportunity_id: str) -> dict[str, Any]:
    row = (
        engine.db.query(MarketingOpportunity)
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
        region_code = engine._normalize_region_token(str(scope[0])) or "DE"
    elif isinstance(scope, str):
        region_code = engine._normalize_region_token(scope) or "DE"
    else:
        region_code = "DE"

    ranking_signal_context = payload.get("ranking_signal_context") or payload.get("peix_context") or {}
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

    condition_key = (
        playbook.get("condition_key")
        or (payload.get("product_mapping") or {}).get("condition_key")
        or cfg.get("condition_key")
        or "erkaltung_akut"
    )

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
        "region_name": engine._region_label(region_code),
        "impact_probability": float(ranking_signal_context.get("impact_probability") or 0.0),
        "ranking_signal_score": float(ranking_signal_context.get("score") or 0.0),
        "peix_score": float(ranking_signal_context.get("score") or 0.0),
        "signal_band": ranking_signal_context.get("band"),
        "peix_band": ranking_signal_context.get("band"),
        "signal_drivers": ranking_signal_context.get("drivers") or [],
        "peix_drivers": ranking_signal_context.get("drivers") or [],
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
    generated = engine.ai_planner.generate_plan(
        playbook_candidate=candidate,
        brand=row.brand or "PEIX Partner",
        product=row.product or "Atemwegslinie",
        campaign_goal=objective,
        weekly_budget=weekly_budget,
    )
    guarded = engine.guardrails.apply(
        playbook_key=playbook_key,
        ai_plan=generated.get("ai_plan") or {},
        weekly_budget=weekly_budget,
    )

    payload["ai_plan"] = guarded["ai_plan"]
    payload["guardrail_report"] = guarded["guardrail_report"]

    fixes = guarded.get("guardrail_report", {}).get("applied_fixes", [])
    if fixes:
        engine.db.add(AuditLog(
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
        "regenerated_at": utc_now().isoformat() + "Z",
    }

    if "message_framework" not in payload or not isinstance(payload["message_framework"], dict):
        payload["message_framework"] = {}
    payload["message_framework"].update(pack.to_framework())

    row.campaign_payload = payload
    row.strategy_mode = row.strategy_mode or "PLAYBOOK_AI"
    row.playbook_key = row.playbook_key or playbook_key
    row.updated_at = utc_now()
    engine.db.commit()

    result = engine._model_to_dict(row, normalize_status=True)
    result["guardrail_notes"] = guarded.get("guardrail_notes") or []
    result["ai_generation_status"] = generated.get("ai_generation_status")
    return result


def synthetic_playbook_opportunity(
    engine: "MarketingOpportunityEngine",
    *,
    playbook_key: str,
    region_code: str,
    region_label: str,
    candidate: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    del engine
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


def ensure_synthetic_opportunity_row(
    engine: "MarketingOpportunityEngine",
    *,
    synthetic_opportunity: dict[str, Any],
    strategy_mode: str,
    playbook_key: str,
) -> str:
    trigger_ctx = synthetic_opportunity.get("trigger_context") or {}
    detected_at_raw = trigger_ctx.get("detected_at")
    detected_at = engine._parse_iso_datetime(detected_at_raw) or utc_now()

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
        expires_at=utc_now() + timedelta(days=14),
    )
    engine.db.add(entry)
    engine.db.flush()
    return entry.opportunity_id


def merge_ai_playbook_payload(
    engine: "MarketingOpportunityEngine",
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
    del engine
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


def build_campaign_pack(
    engine: "MarketingOpportunityEngine",
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
    ranking_signal_context = dict(peix_context or {})
    channel_plan = engine._build_channel_plan(channel_mix, budget_shift_value, campaign_goal)
    measurement_plan = engine._build_measurement_plan(campaign_goal, channel_plan)
    flight_days = int(activation_window.get("flight_days") or 7)

    return {
        "meta": {
            "version": "1.0",
            "generated_at": utc_now().isoformat() + "Z",
            "generator": "ViralFlux-Media-v3",
        },
        "campaign": {
            "campaign_name": engine._derive_campaign_name(brand, product, region, opportunity.get("type", "")),
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
        "peix_context": ranking_signal_context,
        "ranking_signal_context": ranking_signal_context,
        "measurement_plan": measurement_plan,
        "execution_checklist": [
            {"task": "Media-Flight in DSP/Ads Manager anlegen", "owner": "Media Ops", "eta": "T+0", "status": "open"},
            {"task": "Search-Keyword-Set nach Trigger-Region ausrollen", "owner": "Performance Team", "eta": "T+1", "status": "open"},
            {"task": "Creative-Freigabe mit Compliance abstimmen", "owner": "Account Lead", "eta": "T+1", "status": "open"},
            {"task": "KPI-Dashboard für Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1", "status": "open"},
        ],
    }


def campaign_preview_from_payload(
    engine: "MarketingOpportunityEngine",
    payload: dict[str, Any],
) -> dict[str, Any]:
    del engine
    campaign = payload.get("campaign") or {}
    budget = payload.get("budget_plan") or {}
    measurement = payload.get("measurement_plan") or {}
    window = payload.get("activation_window") or {}
    product_mapping = payload.get("product_mapping") or {}
    ranking_signal_context = payload.get("ranking_signal_context") or payload.get("peix_context") or {}
    peix_context = ranking_signal_context
    forecast_assessment = payload.get("forecast_assessment") or {}
    opportunity_assessment = payload.get("opportunity_assessment") or {}
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
        "ranking_signal_context": ranking_signal_context,
        "forecast_assessment": forecast_assessment,
        "opportunity_assessment": opportunity_assessment,
        "playbook_key": playbook.get("key"),
        "playbook_title": playbook.get("title"),
        "ai_generation_status": ai_meta.get("status"),
    }


def enrich_opportunity_for_media(
    engine: "MarketingOpportunityEngine",
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
    if not opportunity_id:
        return
    row = (
        engine.db.query(MarketingOpportunity)
        .filter(MarketingOpportunity.opportunity_id == opportunity_id)
        .first()
    )
    if not row:
        return

    now = utc_now()
    row.brand = engine._canonical_brand(brand) or "gelo"
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
    engine.db.commit()
