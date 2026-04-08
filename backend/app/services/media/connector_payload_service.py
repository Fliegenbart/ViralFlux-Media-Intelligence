"""Prepare connector-ready campaign payload previews for future media syncs."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime
from typing import Any


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

CONNECTOR_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "key": "meta_ads",
        "label": "Meta Ads",
        "status": "preview",
        "description": "Vorschau für die regionale Übergabe in Meta Ads.",
        "supported_channels": ["social", "video", "display"],
        "supported_objectives": ["Awareness", "Traffic", "Conversions"],
    },
    {
        "key": "google_ads",
        "label": "Google Ads",
        "status": "preview",
        "description": "Vorschau für die Übergabe in Google Ads mit Kampagnen- und Anzeigengruppen-Logik.",
        "supported_channels": ["search", "video", "display"],
        "supported_objectives": ["Search", "Video", "Performance"],
    },
    {
        "key": "dv360",
        "label": "DV360",
        "status": "preview",
        "description": "Vorschau für die programmatic Übergabe in DV360.",
        "supported_channels": ["programmatic", "display", "video", "ctv"],
        "supported_objectives": ["Awareness", "Reach", "Consideration"],
    },
)


class ConnectorPayloadService:
    """Build normalized sync previews from existing campaign packages."""

    DEFAULT_CONNECTOR = "meta_ads"

    @classmethod
    def get_catalog(cls) -> dict[str, Any]:
        return {
            "default_connector": cls.DEFAULT_CONNECTOR,
            "connectors": [dict(item) for item in CONNECTOR_CATALOG],
        }

    @classmethod
    def prepare_sync_package(
        cls,
        *,
        opportunity: dict[str, Any],
        connector_key: str | None = None,
    ) -> dict[str, Any]:
        connector = cls._resolve_connector(connector_key)
        payload = opportunity.get("campaign_payload") or {}
        if not payload:
            raise ValueError("Für diese Empfehlung liegt noch kein Kampagnenvorschlag vor.")

        normalized_package = cls._build_normalized_package(opportunity=opportunity, campaign_payload=payload)
        readiness = cls._build_readiness(
            opportunity=opportunity,
            normalized_package=normalized_package,
            connector=connector,
        )
        connector_payload = cls._build_connector_payload(
            normalized_package=normalized_package,
            connector=connector,
        )

        return {
            "opportunity_id": opportunity.get("id") or opportunity.get("opportunity_id"),
            "connector_key": connector["key"],
            "connector_label": connector["label"],
            "generated_at": utc_now().isoformat() + "Z",
            "available_connectors": [dict(item) for item in CONNECTOR_CATALOG],
            "readiness": readiness,
            "normalized_package": normalized_package,
            "connector_payload": connector_payload,
        }

    @classmethod
    def _resolve_connector(cls, connector_key: str | None) -> dict[str, Any]:
        key = str(connector_key or cls.DEFAULT_CONNECTOR).strip().lower()
        for item in CONNECTOR_CATALOG:
            if item["key"] == key:
                return dict(item)
        raise ValueError(f"Unbekannter Connector: {key}")

    @classmethod
    def _build_normalized_package(
        cls,
        *,
        opportunity: dict[str, Any],
        campaign_payload: dict[str, Any],
    ) -> dict[str, Any]:
        campaign = campaign_payload.get("campaign") or {}
        targeting = campaign_payload.get("targeting") or {}
        activation_window = campaign_payload.get("activation_window") or {}
        budget_plan = campaign_payload.get("budget_plan") or {}
        measurement_plan = campaign_payload.get("measurement_plan") or {}
        message_framework = campaign_payload.get("message_framework") or {}
        playbook = campaign_payload.get("playbook") or {}
        trigger_snapshot = campaign_payload.get("trigger_snapshot") or {}
        product_mapping = campaign_payload.get("product_mapping") or {}
        ai_plan = campaign_payload.get("ai_plan") or {}
        guardrails = campaign_payload.get("guardrail_report") or {}
        execution_checklist = campaign_payload.get("execution_checklist") or []

        region_codes = cls._extract_region_codes(opportunity=opportunity, campaign_payload=campaign_payload)
        recommended_product = (
            product_mapping.get("recommended_product")
            or opportunity.get("recommended_product")
            or opportunity.get("product")
        )

        return {
            "campaign_name": campaign.get("campaign_name") or opportunity.get("campaign_name") or "Kampagnenvorschlag",
            "workflow_status": str(opportunity.get("status") or campaign.get("status") or "DRAFT").upper(),
            "brand": opportunity.get("brand") or "gelo",
            "objective": campaign.get("objective") or ai_plan.get("objective") or "Awareness",
            "recommended_product": recommended_product,
            "region_codes": region_codes,
            "region_labels": [BUNDESLAND_NAMES.get(code, code) for code in region_codes],
            "audience_segments": targeting.get("audience_segments") or [],
            "primary_kpi": measurement_plan.get("primary_kpi"),
            "secondary_kpis": measurement_plan.get("secondary_kpis") or [],
            "budget_plan": {
                "weekly_budget_eur": budget_plan.get("weekly_budget_eur"),
                "budget_shift_pct": budget_plan.get("budget_shift_pct"),
                "budget_shift_value_eur": budget_plan.get("budget_shift_value_eur"),
                "total_flight_budget_eur": budget_plan.get("total_flight_budget_eur"),
                "currency": budget_plan.get("currency") or "EUR",
            },
            "activation_window": {
                "start": activation_window.get("start"),
                "end": activation_window.get("end"),
                "flight_days": activation_window.get("flight_days"),
            },
            "channel_plan": cls._normalize_channel_plan(campaign_payload.get("channel_plan")),
            "message_framework": {
                "hero_message": message_framework.get("hero_message"),
                "support_points": message_framework.get("support_points") or [],
                "cta": message_framework.get("cta"),
                "compliance_note": message_framework.get("compliance_note"),
            },
            "creative_angles": ai_plan.get("creative_angles") or [],
            "keyword_clusters": ai_plan.get("keyword_clusters") or [],
            "next_steps": ai_plan.get("next_steps") or execution_checklist,
            "playbook": {
                "key": playbook.get("key"),
                "title": playbook.get("title"),
                "kind": playbook.get("kind"),
            },
            "trigger": {
                "source": trigger_snapshot.get("source"),
                "event": trigger_snapshot.get("event"),
                "details": trigger_snapshot.get("details"),
                "lead_time_days": trigger_snapshot.get("lead_time_days"),
            },
            "guardrails": {
                "passed": bool(guardrails.get("passed", True)),
                "notes": guardrails.get("notes") or [],
                "applied_fixes": guardrails.get("applied_fixes") or [],
            },
        }

    @classmethod
    def _build_readiness(
        cls,
        *,
        opportunity: dict[str, Any],
        normalized_package: dict[str, Any],
        connector: dict[str, Any],
    ) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []

        workflow_status = str(normalized_package.get("workflow_status") or "DRAFT").upper()
        if workflow_status not in {"APPROVED", "ACTIVATED"}:
            blockers.append("Die Kampagne muss vor einer Übergabe zuerst freigegeben werden.")

        if not normalized_package.get("campaign_name"):
            blockers.append("Kampagnenname fehlt.")
        if not normalized_package.get("recommended_product"):
            blockers.append("Kein Produkt-Mapping vorhanden.")
        if not normalized_package.get("channel_plan"):
            blockers.append("Es ist kein Channel-Plan hinterlegt.")
        if not normalized_package.get("guardrails", {}).get("passed", True):
            blockers.append("Die Prüfkriterien sind noch nicht erfüllt.")

        if not normalized_package.get("region_codes"):
            warnings.append("Keine regionale Zielsteuerung vorhanden; die Vorschau wird national vorbereitet.")
        if not normalized_package.get("message_framework", {}).get("hero_message"):
            warnings.append("Die Leitbotschaft fehlt und sollte vor der Freigabe ergaenzt werden.")

        connector_channels = {
            item.get("channel")
            for item in normalized_package.get("channel_plan") or []
            if item.get("channel")
        }
        supported_channels = set(connector.get("supported_channels") or [])
        if connector_channels and connector_channels.isdisjoint(supported_channels):
            warnings.append(
                f"Der aktuelle Channel-Mix passt nur eingeschränkt zu {connector.get('label')}."
            )

        can_sync_now = not blockers
        if can_sync_now:
            state = "ready"
        elif blockers == ["Kampagne muss vor einem Tool-Sync zuerst freigegeben werden."]:
            state = "approval_required"
        else:
            state = "needs_work"

        return {
            "state": state,
            "can_sync_now": can_sync_now,
            "blockers": blockers,
            "warnings": warnings,
            "connector_status": connector.get("status"),
        }

    @classmethod
    def _build_connector_payload(
        cls,
        *,
        normalized_package: dict[str, Any],
        connector: dict[str, Any],
    ) -> dict[str, Any]:
        key = connector["key"]
        if key == "google_ads":
            return cls._build_google_ads_payload(normalized_package)
        if key == "dv360":
            return cls._build_dv360_payload(normalized_package)
        return cls._build_meta_ads_payload(normalized_package)

    @classmethod
    def _build_meta_ads_payload(cls, normalized_package: dict[str, Any]) -> dict[str, Any]:
        daily_budget = cls._daily_budget(normalized_package)
        ad_sets = []
        for region_code, region_label in cls._region_pairs(normalized_package):
            ad_sets.append(
                {
                    "name": f"{normalized_package['campaign_name']} | {region_label}",
                    "regions": [region_code],
                    "daily_budget_eur": daily_budget,
                    "placements": ["facebook_feed", "instagram_feed", "reels"],
                    "primary_message": normalized_package.get("message_framework", {}).get("hero_message"),
                }
            )

        return {
            "campaign": {
                "name": normalized_package["campaign_name"],
                "objective": cls._map_meta_objective(normalized_package.get("objective")),
                "status": "PAUSED",
            },
            "ad_sets": ad_sets or [
                {
                    "name": f"{normalized_package['campaign_name']} | National",
                    "regions": ["DE"],
                    "daily_budget_eur": daily_budget,
                    "placements": ["facebook_feed", "instagram_feed", "reels"],
                    "primary_message": normalized_package.get("message_framework", {}).get("hero_message"),
                }
            ],
            "creative_brief": {
                "headline": normalized_package.get("message_framework", {}).get("hero_message"),
                "angles": (normalized_package.get("creative_angles") or [])[:3],
                "cta": normalized_package.get("message_framework", {}).get("cta") or "Mehr erfahren",
            },
        }

    @classmethod
    def _build_google_ads_payload(cls, normalized_package: dict[str, Any]) -> dict[str, Any]:
        daily_budget = cls._daily_budget(normalized_package)
        search_keywords = (normalized_package.get("keyword_clusters") or [])[:8]
        ad_groups = []
        for region_code, region_label in cls._region_pairs(normalized_package):
            ad_groups.append(
                {
                    "name": f"{region_label} | {normalized_package['recommended_product'] or 'Brand'}",
                    "region": region_code,
                    "keywords": search_keywords,
                    "headlines": cls._headline_variants(normalized_package),
                }
            )

        return {
            "campaign": {
                "name": normalized_package["campaign_name"],
                "advertising_channel_type": "SEARCH",
                "daily_budget_eur": daily_budget,
                "status": "PAUSED",
            },
            "ad_groups": ad_groups or [
                {
                    "name": normalized_package["campaign_name"],
                    "region": "DE",
                    "keywords": search_keywords,
                    "headlines": cls._headline_variants(normalized_package),
                }
            ],
        }

    @classmethod
    def _build_dv360_payload(cls, normalized_package: dict[str, Any]) -> dict[str, Any]:
        line_items = []
        total_budget = cls._total_budget(normalized_package)
        region_pairs = cls._region_pairs(normalized_package)
        per_region_budget = round(total_budget / max(1, len(region_pairs)), 2)

        for region_code, region_label in region_pairs:
            line_items.append(
                {
                    "name": f"{normalized_package['campaign_name']} | {region_label}",
                    "region": region_code,
                    "budget_eur": per_region_budget,
                    "inventory_mix": [
                        item.get("channel")
                        for item in normalized_package.get("channel_plan") or []
                        if item.get("channel") in {"programmatic", "display", "video", "ctv"}
                    ] or ["programmatic"],
                    "creative_message": normalized_package.get("message_framework", {}).get("hero_message"),
                }
            )

        return {
            "insertion_order": {
                "name": normalized_package["campaign_name"],
                "objective": normalized_package.get("objective"),
                "status": "DRAFT",
                "budget_eur": total_budget,
            },
            "line_items": line_items or [
                {
                    "name": normalized_package["campaign_name"],
                    "region": "DE",
                    "budget_eur": total_budget,
                    "inventory_mix": ["programmatic"],
                    "creative_message": normalized_package.get("message_framework", {}).get("hero_message"),
                }
            ],
        }

    @staticmethod
    def _normalize_channel_plan(channel_plan: Any) -> list[dict[str, Any]]:
        if not isinstance(channel_plan, list):
            return []

        result: list[dict[str, Any]] = []
        for item in channel_plan:
            if not isinstance(item, dict):
                continue
            channel = str(item.get("channel") or "").strip().lower()
            if not channel:
                continue
            result.append(
                {
                    "channel": channel,
                    "share_pct": float(item.get("share_pct") or 0.0),
                    "role": item.get("role"),
                    "formats": item.get("formats") or [],
                    "message_angle": item.get("message_angle"),
                    "kpi_primary": item.get("kpi_primary"),
                    "kpi_secondary": item.get("kpi_secondary") or [],
                }
            )
        return result

    @classmethod
    def _extract_region_codes(
        cls,
        *,
        opportunity: dict[str, Any],
        campaign_payload: dict[str, Any],
    ) -> list[str]:
        existing = opportunity.get("region_codes")
        if isinstance(existing, list) and existing:
            normalized = [cls._normalize_region_code(str(item)) for item in existing if item]
            return sorted({code for code in normalized if code in BUNDESLAND_NAMES})

        region = opportunity.get("region")
        if isinstance(region, str) and region.strip():
            code = cls._normalize_region_code(region)
            if code in BUNDESLAND_NAMES:
                return [code]

        targeting = campaign_payload.get("targeting") or {}
        scope = targeting.get("region_scope")
        tokens: list[str] = []
        if isinstance(scope, list):
            tokens.extend(str(item) for item in scope if item)
        elif isinstance(scope, str) and scope.strip():
            tokens.append(scope)

        result = set()
        for token in tokens:
            lower = token.strip().lower()
            if lower in {"gesamt", "de", "all", "national", "deutschland"}:
                return sorted(BUNDESLAND_NAMES.keys())
            code = cls._normalize_region_code(token)
            if code in BUNDESLAND_NAMES:
                result.add(code)

        return sorted(result)

    @staticmethod
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

    @staticmethod
    def _map_meta_objective(objective: Any) -> str:
        raw = str(objective or "").strip().lower()
        if "conversion" in raw or "abverkauf" in raw:
            return "OUTCOME_SALES"
        if "traffic" in raw:
            return "OUTCOME_TRAFFIC"
        return "OUTCOME_AWARENESS"

    @staticmethod
    def _total_budget(normalized_package: dict[str, Any]) -> float:
        budget_plan = normalized_package.get("budget_plan") or {}
        total = budget_plan.get("total_flight_budget_eur")
        weekly = budget_plan.get("weekly_budget_eur")
        shift_value = budget_plan.get("budget_shift_value_eur")
        for value in (total, weekly, shift_value):
            if value not in (None, ""):
                return round(float(value), 2)
        return 0.0

    @classmethod
    def _daily_budget(cls, normalized_package: dict[str, Any]) -> float:
        total_budget = cls._total_budget(normalized_package)
        flight_days = (normalized_package.get("activation_window") or {}).get("flight_days") or 7
        return round(total_budget / max(1, int(flight_days)), 2)

    @staticmethod
    def _headline_variants(normalized_package: dict[str, Any]) -> list[str]:
        message = normalized_package.get("message_framework") or {}
        hero_message = message.get("hero_message")
        angles = normalized_package.get("creative_angles") or []
        variants = [str(item).strip() for item in [hero_message, *angles] if str(item or "").strip()]
        return variants[:5]

    @staticmethod
    def _region_pairs(normalized_package: dict[str, Any]) -> list[tuple[str, str]]:
        region_codes = normalized_package.get("region_codes") or []
        region_labels = normalized_package.get("region_labels") or []
        if not region_codes:
            return []
        return list(zip(region_codes, region_labels or region_codes))
