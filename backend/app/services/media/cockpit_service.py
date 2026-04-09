"""Media Cockpit Service: bündelt Bento, Karte, Empfehlungen, Backtest und Datenfrische."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.database import (
    MarketingOpportunity,
)
from app.services.media.cockpit.backtest import build_backtest_summary
from app.services.media.cockpit.bento_section import build_bento_section
from app.services.media.cockpit.constants import BUNDESLAND_NAMES, REGION_NAME_TO_CODE
from app.services.media.cockpit.freshness import (
    build_data_freshness,
    build_source_freshness_summary,
    build_source_status,
)
from app.services.media.cockpit.map_section import build_map_section
from app.services.media.cockpit.signals import (
    build_campaign_refs_section as cockpit_build_campaign_refs_section,
    build_ranking_signal_fields as cockpit_build_ranking_signal_fields,
    build_signal_snapshot_section as cockpit_build_signal_snapshot_section,
    coerce_float as cockpit_coerce_float,
    normalize_recommendation_ref as cockpit_normalize_recommendation_ref,
    primary_signal_score as cockpit_primary_signal_score,
)
from app.services.media.peix_score_service import PeixEpiScoreService
from app.services.media.recommendation_contracts import to_card_response
from app.services.media.semantic_contracts import (
    normalize_confidence_pct,
    signal_confidence_contract,
)

LEGACY_TO_WORKFLOW = {
    "NEW": "DRAFT",
    "URGENT": "DRAFT",
    "SENT": "APPROVED",
    "CONVERTED": "ACTIVATED",
}

class MediaCockpitService:
    """Aggregierter Read-Service für das map-first Media Cockpit."""

    def __init__(self, db: Session):
        self.db = db

    def get_cockpit_payload(
        self,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
    ) -> dict:
        """Liefert einen einzigen Payload für Dashboard-Tabstruktur."""
        peix = PeixEpiScoreService(self.db).build(virus_typ=virus_typ)
        data_freshness = self._data_freshness()
        source_status = self._source_status(data_freshness)
        region_refs = self._region_recommendation_refs()

        map_section = self._map_section(
            virus_typ=virus_typ,
            peix_score=peix,
            region_recommendations=region_refs,
        )
        signal_snapshot = self._signal_snapshot_section(
            virus_typ=virus_typ,
            peix_score=peix,
            map_section=map_section,
        )

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "bento": self._bento_section(
                virus_typ=virus_typ,
                map_section=map_section,
                peix_score=peix,
                source_status=source_status,
            ),
            "peix_epi_score": peix,
            "signal_snapshot": signal_snapshot,
            "source_status": source_status,
            "source_freshness": self._source_freshness_summary(source_status),
            "map": map_section,
            "campaign_refs": self._campaign_refs_section(region_refs),
            "recommendations": self._recommendation_section(),
            "backtest_summary": self._backtest_summary(
                virus_typ=virus_typ,
                target_source=target_source,
            ),
            "data_freshness": data_freshness,
            "timestamp": utc_now().isoformat(),
        }

    @staticmethod
    def _normalize_freshness_timestamp(
        value: datetime | None,
        *,
        now: datetime | None = None,
    ) -> str | None:
        """Return an ISO timestamp that never points into the future."""
        if value is None:
            return None

        effective_now = now or utc_now()
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.replace(tzinfo=None)
        if normalized > effective_now:
            normalized = effective_now
        return normalized.isoformat()

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        return cockpit_coerce_float(value)

    @classmethod
    def _primary_signal_score(cls, item: dict[str, Any] | None) -> float:
        return cockpit_primary_signal_score(item)

    def _ranking_signal_fields(
        self,
        *,
        signal_score: Any,
        source: str,
        legacy_alias: Any = None,
        label: str = "Signal-Score",
    ) -> dict[str, Any]:
        return cockpit_build_ranking_signal_fields(
            signal_score=signal_score,
            source=source,
            legacy_alias=legacy_alias,
            label=label,
        )

    @staticmethod
    def _normalize_recommendation_ref(
        recommendation_ref: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return cockpit_normalize_recommendation_ref(recommendation_ref)

    def _signal_snapshot_section(
        self,
        *,
        virus_typ: str,
        peix_score: dict[str, Any],
        map_section: dict[str, Any],
    ) -> dict[str, Any]:
        return cockpit_build_signal_snapshot_section(
            virus_typ=virus_typ,
            peix_score=peix_score,
            map_section=map_section,
        )

    def _source_freshness_summary(self, source_status: dict[str, Any]) -> dict[str, Any]:
        return build_source_freshness_summary(source_status)

    def _campaign_refs_section(
        self,
        region_recommendations: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return cockpit_build_campaign_refs_section(region_recommendations)

    def _map_section(
        self,
        *,
        virus_typ: str,
        peix_score: dict[str, Any],
        region_recommendations: dict[str, dict[str, Any]],
    ) -> dict:
        return build_map_section(
            self.db,
            virus_typ=virus_typ,
            peix_score=peix_score,
            region_recommendations=region_recommendations,
        )

    def _bento_section(
        self,
        *,
        virus_typ: str,
        map_section: dict[str, Any],
        peix_score: dict[str, Any],
        source_status: dict[str, Any],
    ) -> dict[str, Any]:
        return build_bento_section(
            self.db,
            virus_typ=virus_typ,
            map_section=map_section,
            peix_score=peix_score,
            source_status=source_status,
        )

    def _recommendation_section(self) -> dict:
        rows = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.urgency_score.desc(),
            MarketingOpportunity.created_at.desc(),
        ).limit(20).all()

        cards: list[dict] = []
        for row in rows:
            region_codes = self._extract_region_codes_from_row(row)
            primary_region = region_codes[0] if region_codes else "Gesamt"
            channel_mix = row.channel_mix or {"programmatic": 35, "social": 30, "search": 20, "ctv": 15}
            campaign_payload = row.campaign_payload or {}
            campaign = campaign_payload.get("campaign") or {}
            budget = campaign_payload.get("budget_plan") or {}
            measurement = campaign_payload.get("measurement_plan") or {}
            activation = campaign_payload.get("activation_window") or {}
            product_mapping = campaign_payload.get("product_mapping") or {}
            peix_context = campaign_payload.get("peix_context") or {}
            playbook = campaign_payload.get("playbook") or {}
            ai_meta = campaign_payload.get("ai_meta") or {}
            status = LEGACY_TO_WORKFLOW.get(str(row.status or "").upper(), row.status or "DRAFT")
            recommended_product = product_mapping.get("recommended_product") or row.product or "Atemwegslinie"
            decision_expectation = (campaign_payload.get("decision_brief") or {}).get("expectation") or {}
            signal_confidence_pct = (
                normalize_confidence_pct(decision_expectation.get("signal_confidence_pct"))
                or normalize_confidence_pct(decision_expectation.get("confidence_pct"))
                or normalize_confidence_pct(
                    ((campaign_payload.get("forecast_assessment") or {}).get("event_forecast") or {}).get("confidence")
                )
            )
            signal_score = (
                self._coerce_float((peix_context or {}).get("signal_score"))
                or self._coerce_float((peix_context or {}).get("score"))
                or self._coerce_float((peix_context or {}).get("impact_probability"))
            )
            opp_payload = {
                "id": row.opportunity_id,
                "status": status,
                "type": row.opportunity_type,
                "urgency_score": row.urgency_score,
                "priority_score": row.urgency_score,
                "brand": row.brand or "PEIX Partner",
                "product": recommended_product,
                "recommended_product": recommended_product,
                "region": primary_region,
                "region_codes": region_codes,
                "budget_shift_pct": row.budget_shift_pct if row.budget_shift_pct is not None else 15.0,
                "channel_mix": channel_mix,
                "activation_window": {
                    "start": (
                        row.activation_start.isoformat() if row.activation_start
                        else activation.get("start")
                    ),
                    "end": (
                        row.activation_end.isoformat() if row.activation_end
                        else activation.get("end")
                    ),
                },
                "recommendation_reason": row.recommendation_reason or (row.trigger_event or "Epidemiologisches Trigger-Signal"),
                "confidence": (
                    round(float(signal_confidence_pct) / 100.0, 2)
                    if signal_confidence_pct is not None
                    else None
                ),
                "signal_score": signal_score,
                "signal_confidence_pct": signal_confidence_pct,
                "mapping_status": product_mapping.get("mapping_status"),
                "mapping_confidence": product_mapping.get("mapping_confidence"),
                "mapping_reason": product_mapping.get("mapping_reason"),
                "condition_key": product_mapping.get("condition_key"),
                "condition_label": product_mapping.get("condition_label"),
                "mapping_candidate_product": product_mapping.get("candidate_product"),
                "playbook_key": row.playbook_key or playbook.get("key"),
                "playbook_title": playbook.get("title"),
                "strategy_mode": row.strategy_mode or campaign_payload.get("strategy_mode"),
                "trigger_snapshot": campaign_payload.get("trigger_snapshot"),
                "guardrail_notes": (campaign_payload.get("guardrail_report") or {}).get("applied_fixes") or [],
                "ai_generation_status": ai_meta.get("status"),
                "campaign_name": campaign.get("campaign_name"),
                "primary_kpi": measurement.get("primary_kpi"),
                "peix_context": peix_context,
                "campaign_payload": campaign_payload,
                "campaign_preview": {
                    "campaign_name": campaign.get("campaign_name"),
                    "activation_window": {
                        "start": activation.get("start"),
                        "end": activation.get("end"),
                    },
                    "budget": {
                        "weekly_budget_eur": budget.get("weekly_budget_eur"),
                        "shift_pct": budget.get("budget_shift_pct"),
                        "shift_value_eur": budget.get("budget_shift_value_eur"),
                        "total_flight_budget_eur": budget.get("total_flight_budget_eur"),
                    },
                    "primary_kpi": measurement.get("primary_kpi"),
                    "recommended_product": recommended_product,
                    "mapping_status": product_mapping.get("mapping_status"),
                },
                "detail_url": f"/kampagnen/{row.opportunity_id}",
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            card = to_card_response(opp_payload, include_preview=True)
            card.setdefault("field_contracts", {})
            card["field_contracts"]["signal_confidence_pct"] = signal_confidence_contract(
                source=str(
                    (campaign_payload.get("trigger_snapshot") or {}).get("source")
                    or "Signal-Fusion"
                ),
                derived_from="trigger_evidence.confidence",
            )
            cards.append(card)

        return {
            "total": len(cards),
            "cards": cards,
        }

    def _region_recommendation_refs(self) -> dict[str, dict[str, Any]]:
        refs: dict[str, dict[str, Any]] = {}
        rows = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.urgency_score.desc(),
            MarketingOpportunity.created_at.desc(),
        ).limit(250).all()

        for row in rows:
            status = LEGACY_TO_WORKFLOW.get(str(row.status or "").upper(), str(row.status or "DRAFT").upper())
            if status in {"DISMISSED", "EXPIRED"}:
                continue

            region_codes = self._extract_region_codes_from_row(row)
            if not region_codes:
                region_codes = sorted(BUNDESLAND_NAMES.keys())

            payload = {
                "card_id": row.opportunity_id,
                "detail_url": f"/kampagnen/{row.opportunity_id}",
                "status": status,
                "urgency_score": row.urgency_score,
                "priority_score": row.urgency_score,
                "brand": row.brand,
                "product": row.product,
            }

            for code in region_codes:
                if code not in refs:
                    refs[code] = payload

        return refs

    def _extract_region_codes_from_row(self, row: MarketingOpportunity) -> list[str]:
        region_target = row.region_target or {}
        campaign_payload = row.campaign_payload or {}
        targeting = campaign_payload.get("targeting") or {}

        tokens: list[str] = []
        states = region_target.get("states")
        if isinstance(states, list):
            tokens.extend(str(item) for item in states)

        scope = targeting.get("region_scope")
        if isinstance(scope, list):
            tokens.extend(str(item) for item in scope)
        elif isinstance(scope, str):
            tokens.append(scope)

        normalized: set[str] = set()
        for token in tokens:
            lower = token.strip().lower()
            if lower in {"gesamt", "all", "de", "national", "deutschland"}:
                return []

            code = token.strip().upper()
            if code in BUNDESLAND_NAMES:
                normalized.add(code)
                continue

            mapped = REGION_NAME_TO_CODE.get(lower)
            if mapped:
                normalized.add(mapped)

        return sorted(normalized)

    def _backtest_summary(self, virus_typ: str, target_source: str) -> dict:
        return build_backtest_summary(
            self.db,
            virus_typ=virus_typ,
            target_source=target_source,
        )

    def _data_freshness(self) -> dict:
        return build_data_freshness(
            self.db,
            normalize_freshness_timestamp=self._normalize_freshness_timestamp,
        )

    def _source_status(self, data_freshness: dict[str, Any]) -> dict[str, Any]:
        return build_source_status(data_freshness)
