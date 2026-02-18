"""AI Campaign Planner via strictly local vLLM (OpenAI-compatible API)."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any

from app.services.llm.vllm_service import generate_text, generate_text_sync
from app.services.media.campaign_guardrails import HWG_SYSTEM_PROMPT, check_hwg_compliance

logger = logging.getLogger(__name__)

_CAMPAIGN_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campaign_name": {"type": "string"},
        "objective": {"type": "string"},
        "budget_shift_pct": {"type": "number"},
        "activation_window_days": {"type": "integer"},
        "channel_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "share_pct": {"type": "number"},
                    "message_angle": {"type": "string"},
                    "kpi_primary": {"type": "string"},
                    "kpi_secondary": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["channel", "share_pct"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "campaign_name",
        "objective",
        "budget_shift_pct",
        "activation_window_days",
        "channel_plan",
    ],
    "additionalProperties": False,
}


class AICampaignPlanner:
    """Einfacher Text-Planer (Banner-Aufhänger), HWG-gesichert."""

    async def plan_campaign(self, region: str, outbreak_score: float) -> str:
        user_prompt = (
            f"Plane eine Kampagnen-Strategie für die Region {region}. "
            f"Aktueller Erkältungs-Score (0-100): {outbreak_score}. "
            f"Schreibe 3 kurze Aufhänger für Bannerwerbung."
        )

        messages = [
            {"role": "system", "content": HWG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        strategy_text = await generate_text(messages=messages, temperature=0.2)

        if not check_hwg_compliance(strategy_text):
            logger.warning("HWG blockiert in AICampaignPlanner für %s", region)
            return "Aus rechtlichen Gründen (HWG) wurde diese Kampagnenplanung blockiert. Bitte manuell anpassen."

        return strategy_text


class AiCampaignPlanner:
    """Generiert strukturierte Kampagnenplaene via strikt lokalem vLLM."""

    def __init__(self) -> None:
        self.model = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"

    def generate_plan(
        self,
        *,
        playbook_candidate: dict[str, Any],
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
        skip_ollama: bool = False,
    ) -> dict[str, Any]:
        # Backwards-compatible flag-name (skip_ollama) but now means "skip LLM".
        if skip_ollama:
            fallback = self._deterministic_fallback(
                playbook_candidate=playbook_candidate,
                campaign_goal=campaign_goal,
                brand=brand,
                product=product,
                weekly_budget=weekly_budget,
            )
            return {
                "ai_generation_status": "fallback_template",
                "ai_plan": fallback,
                "ai_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "model": self.model,
                    "provider": "vllm_local",
                    "fallback_used": True,
                    "error": "skipped_llm_after_previous_failure",
                },
            }

        prompt = self._build_prompt(
            playbook_candidate=playbook_candidate,
            brand=brand,
            product=product,
            campaign_goal=campaign_goal,
            weekly_budget=weekly_budget,
        )

        try:
            raw = self._call_vllm(prompt)
            ai_plan = self._parse_json_response(raw)
            if not isinstance(ai_plan, dict):
                raise ValueError("LLM Antwort ist kein JSON-Objekt.")

            # quick compliance check on raw string (before normalization)
            if not check_hwg_compliance(raw):
                raise ValueError("HWG Blocklist in LLM Rohantwort getriggert.")

            normalized = self._normalize_plan(ai_plan, playbook_candidate, campaign_goal)
            return {
                "ai_generation_status": "success",
                "ai_plan": normalized,
                "ai_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "model": self.model,
                    "provider": "vllm_local",
                    "fallback_used": False,
                },
            }
        except Exception as exc:
            logger.warning("AI Kampagnenplan fehlgeschlagen, fallback aktiv: %s", exc)
            fallback = self._deterministic_fallback(
                playbook_candidate=playbook_candidate,
                campaign_goal=campaign_goal,
                brand=brand,
                product=product,
                weekly_budget=weekly_budget,
            )
            return {
                "ai_generation_status": "fallback_template",
                "ai_plan": fallback,
                "ai_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "model": self.model,
                    "provider": "vllm_local",
                    "fallback_used": True,
                    "error": str(exc),
                },
            }

    def _build_prompt(
        self,
        *,
        playbook_candidate: dict[str, Any],
        brand: str,
        product: str,
        campaign_goal: str,
        weekly_budget: float,
    ) -> str:
        channel_mix = playbook_candidate.get("channel_mix") or {}
        trigger = playbook_candidate.get("trigger_snapshot") or {}
        min_shift = (playbook_candidate.get("shift_bounds") or {}).get("min")
        max_shift = (playbook_candidate.get("shift_bounds") or {}).get("max")
        copy_pack = playbook_candidate.get("copy_pack") or {}
        direction = playbook_candidate.get("message_direction") or copy_pack.get("message_direction")
        hero = copy_pack.get("hero_message")
        support = copy_pack.get("support_points") or []
        compliance_note = copy_pack.get("compliance_note")

        return (
            "Du bist ein Senior Media Planner für Pharma-Brand-Cases.\n"
            "Erzeuge NUR valides JSON ohne Markdown, ohne Erklaertexte.\n"
            "Sprache: Deutsch. Konservativ formulieren (kein Heilversprechen).\n"
            "Output-Felder: campaign_name, objective, budget_shift_pct, activation_window_days, channel_plan, keyword_clusters, creative_angles, kpi_targets, next_steps, compliance_hinweis.\n"
            "Output: kompaktes JSON in EINER Zeile (kein Pretty-Print).\n\n"
            f"Brand: {brand}\n"
            f"Produkt: {product}\n"
            f"Kampagnenziel: {campaign_goal}\n"
            f"Playbook: {playbook_candidate.get('playbook_title')} ({playbook_candidate.get('playbook_key')})\n"
            f"Region: {playbook_candidate.get('region_name')} ({playbook_candidate.get('region_code')})\n"
            f"PeixEpiScore: {playbook_candidate.get('peix_score')} / Impact {playbook_candidate.get('impact_probability')}%\n"
            f"Trigger: {trigger.get('event')} | {trigger.get('details')}\n"
            f"Message-Direction (fix): {direction}\n"
            f"Hero-Message (fix): {hero}\n"
            f"Support-Points (fix): {json.dumps(support, ensure_ascii=True)}\n"
            f"Compliance-Hinweis (fix): {compliance_note}\n"
            f"Woechentliches Budget (EUR): {weekly_budget:.2f}\n"
            f"Erlaubter Shift-Bereich (%): {min_shift} bis {max_shift}\n"
            f"Kanal-Default-Mix: {json.dumps(channel_mix, ensure_ascii=True)}\n\n"
        )

    def _call_vllm(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": HWG_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        return generate_text_sync(messages=messages, temperature=0.2).strip()

    @staticmethod
    def _parse_json_response(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # defensive extraction: first {...} block
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise

    @staticmethod
    def _normalize_plan(
        ai_plan: dict[str, Any],
        playbook_candidate: dict[str, Any],
        campaign_goal: str,
    ) -> dict[str, Any]:
        channel_default = playbook_candidate.get("channel_mix") or {}
        plan_channels = ai_plan.get("channel_plan")
        if not isinstance(plan_channels, list) or not plan_channels:
            plan_channels = [
                {
                    "channel": channel,
                    "share_pct": float(share),
                    "message_angle": playbook_candidate.get("message_direction") or "Situatives Timing",
                    "kpi_primary": "CTR",
                    "kpi_secondary": ["CPM"],
                }
                for channel, share in channel_default.items()
            ]

        playbook_key = str(playbook_candidate.get("playbook_key") or "").upper()
        keyword_defaults: dict[str, list[str]] = {
            "MYCOPLASMA_JAEGER": [
                "husten geht nicht weg",
                "hartnaeckiger husten",
                "reizhusten nachts",
            ],
            "SUPPLY_SHOCK_ATTACK": [
                "alternative bei engpass",
                "antibiotika lieferengpass",
                "pflanzlich schleimloeser",
            ],
            "WETTER_REFLEX": [
                "nasskaltes wetter",
                "erkaeltung vorbeugen",
                "immunsystem staerken",
            ],
            "ALLERGIE_BREMSE": [
                "heuschnupfen",
                "pollenflug",
                "allergie statt erkaeltung",
            ],
        }
        creative_defaults: dict[str, list[str]] = {
            "MYCOPLASMA_JAEGER": [
                "Dauerhusten: symptomnah",
                "Bronchien: Schleim loesen",
                "Nacht: Reizhusten lindern",
            ],
            "SUPPLY_SHOCK_ATTACK": [
                "Jetzt verfuegbar trotz Engpass",
                "Pflanzliche Alternative",
                "Apotheken-Naehe: sofort finden",
            ],
            "WETTER_REFLEX": [
                "Schietwetter: praeventiv",
                "Alltag: Schutzschild-Story",
                "Kalt+Nass: situatives Motiv",
            ],
            "ALLERGIE_BREMSE": [
                "Allergie vs. Infekt trennen",
                "Budget sparen bei False Positives",
                "Negativ-Keywords / Pause",
            ],
        }
        default_next_steps = [
            {"task": "Kampagnenstruktur im Ad-Setup anlegen", "owner": "Media Ops", "eta": "T+0"},
            {"task": "Creatives mit Compliance abstimmen", "owner": "Account Lead", "eta": "T+1"},
            {"task": "KPI-Dashboard fuer Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1"},
        ]

        keyword_clusters = ai_plan.get("keyword_clusters")
        if not isinstance(keyword_clusters, list) or not keyword_clusters:
            keyword_clusters = keyword_defaults.get(playbook_key, [])

        creative_angles = ai_plan.get("creative_angles")
        if not isinstance(creative_angles, list) or not creative_angles:
            creative_angles = creative_defaults.get(playbook_key, [])

        next_steps = ai_plan.get("next_steps")
        if not isinstance(next_steps, list) or not next_steps:
            next_steps = default_next_steps

        return {
            "campaign_name": ai_plan.get("campaign_name") or (
                f"{playbook_candidate.get('playbook_title')} | {playbook_candidate.get('region_name')}"
            ),
            "objective": ai_plan.get("objective") or campaign_goal,
            "budget_shift_pct": float(ai_plan.get("budget_shift_pct") or playbook_candidate.get("budget_shift_pct") or 0.0),
            "activation_window_days": int(ai_plan.get("activation_window_days") or 10),
            "channel_plan": plan_channels,
            "keyword_clusters": keyword_clusters,
            "creative_angles": creative_angles,
            "kpi_targets": ai_plan.get("kpi_targets") or {
                "primary_kpi": "Qualified Visits",
                "secondary_kpis": ["CTR", "CPM"],
                "success_criteria": "Steigende Nachfrageabdeckung in Triggerregionen",
            },
            "next_steps": next_steps,
            "compliance_hinweis": ai_plan.get("compliance_hinweis")
            or "Hinweis: Aussagen konservativ formulieren (z. B. 'kann', 'Backtest-basiert').",
        }

    def _deterministic_fallback(
        self,
        *,
        playbook_candidate: dict[str, Any],
        campaign_goal: str,
        brand: str,
        product: str,
        weekly_budget: float,
    ) -> dict[str, Any]:
        shift_pct = float(playbook_candidate.get("budget_shift_pct") or 0.0)
        shift_value = round(abs(weekly_budget) * abs(shift_pct) / 100.0, 2)
        channel_mix = playbook_candidate.get("channel_mix") or {}
        channel_plan = []
        for channel, share in channel_mix.items():
            share_num = float(share or 0.0)
            channel_plan.append(
                {
                    "channel": str(channel),
                    "share_pct": share_num,
                    "message_angle": playbook_candidate.get("message_direction") or "Situatives Timing",
                    "kpi_primary": "CTR",
                    "kpi_secondary": ["CPM", "Reach"],
                    "budget_eur": round(shift_value * (share_num / 100.0), 2),
                }
            )

        playbook_title = playbook_candidate.get("playbook_title") or "Playbook"
        region_name = playbook_candidate.get("region_name") or "Region"
        return {
            "campaign_name": f"{brand} | {product} | {region_name} | {playbook_title}",
            "objective": campaign_goal,
            "budget_shift_pct": shift_pct,
            "activation_window_days": 10,
            "channel_plan": channel_plan,
            "keyword_clusters": [
                "symptomnahes Suchverhalten",
                "regionales Bedarfssignal",
                "Verfuegbarkeitskommunikation",
            ],
            "creative_angles": [
                "Problem-Symptom-Ansprache mit konservativem Claim",
                "Regionale Aktivierung bei messbarem Trigger",
                "Verfuegbarkeit im Fokus",
            ],
            "kpi_targets": {
                "primary_kpi": "Qualified Visits",
                "secondary_kpis": ["CTR", "CPM", "Reach"],
                "success_criteria": "Hoehere Nachfrageabdeckung in den naechsten 14 Tagen bei stabiler Effizienz",
            },
            "next_steps": [
                {"task": "Kampagnenstruktur im Ad-Setup anlegen", "owner": "Media Ops", "eta": "T+0"},
                {"task": "Creatives mit Compliance abstimmen", "owner": "Account Lead", "eta": "T+1"},
                {"task": "KPI-Dashboard fuer Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1"},
            ],
            "compliance_hinweis": "Backtest-basierte, konservative Aussagen verwenden; keine Heilversprechen.",
        }
