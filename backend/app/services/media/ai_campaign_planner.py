"""AI Campaign Planner (Ollama-only) fuer Playbook-Kampagnenplaene."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any

import requests

from app.core.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

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
                "required": ["channel", "share_pct", "message_angle", "kpi_primary", "kpi_secondary"],
            },
        },
        "keyword_clusters": {"type": "array", "items": {"type": "string"}},
        "creative_angles": {"type": "array", "items": {"type": "string"}},
        "kpi_targets": {
            "type": "object",
            "properties": {
                "primary_kpi": {"type": "string"},
                "secondary_kpis": {"type": "array", "items": {"type": "string"}},
                "success_criteria": {"type": "string"},
            },
            "required": ["primary_kpi", "secondary_kpis", "success_criteria"],
        },
        "next_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "eta": {"type": "string"},
                },
                "required": ["task", "owner", "eta"],
            },
        },
        "compliance_hinweis": {"type": "string"},
    },
    "required": [
        "campaign_name",
        "objective",
        "budget_shift_pct",
        "activation_window_days",
        "channel_plan",
        "keyword_clusters",
        "creative_angles",
        "kpi_targets",
        "next_steps",
        "compliance_hinweis",
    ],
}


class AiCampaignPlanner:
    """Generiert strukturierte Kampagnenplaene via lokalem Ollama."""

    def __init__(self) -> None:
        self.ollama_url = settings.OLLAMA_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL

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
                    "provider": "ollama_local",
                    "fallback_used": True,
                    "error": "skipped_ollama_after_previous_failure",
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
            raw, used_model = self._call_ollama(prompt)
            ai_plan = self._parse_json_response(raw)
            if not isinstance(ai_plan, dict):
                raise ValueError("Ollama Antwort ist kein JSON-Objekt.")
            normalized = self._normalize_plan(ai_plan, playbook_candidate, campaign_goal)
            return {
                "ai_generation_status": "success",
                "ai_plan": normalized,
                "ai_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "model": used_model,
                    "provider": "ollama_local",
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
                    "provider": "ollama_local",
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

        return (
            "Du bist ein Senior Media Planner für Pharma-Brand-Cases.\n"
            "Erzeuge NUR valides JSON ohne Markdown, ohne Erklaertexte.\n"
            "Sprache: Deutsch. Konservativ formulieren (kein Heilversprechen).\n\n"
            f"Brand: {brand}\n"
            f"Produkt: {product}\n"
            f"Kampagnenziel: {campaign_goal}\n"
            f"Playbook: {playbook_candidate.get('playbook_title')} ({playbook_candidate.get('playbook_key')})\n"
            f"Region: {playbook_candidate.get('region_name')} ({playbook_candidate.get('region_code')})\n"
            f"PeixEpiScore: {playbook_candidate.get('peix_score')} / Impact {playbook_candidate.get('impact_probability')}%\n"
            f"Trigger: {trigger.get('event')} | {trigger.get('details')}\n"
            f"Woechentliches Budget (EUR): {weekly_budget:.2f}\n"
            f"Erlaubter Shift-Bereich (%): {min_shift} bis {max_shift}\n"
            f"Kanal-Default-Mix: {json.dumps(channel_mix, ensure_ascii=True)}\n\n"
            "Wichtig: Antworte kompakt (max. 4 channel_plan Eintraege, max. 6 Keywords, max. 6 Creative Angles, max. 4 Next Steps).\n"
            "Output-Schema (strict):\n"
            "{\n"
            '  "campaign_name": "string",\n'
            '  "objective": "string",\n'
            '  "budget_shift_pct": number,\n'
            '  "activation_window_days": integer,\n'
            '  "channel_plan": [\n'
            '    {"channel":"string","share_pct":number,"message_angle":"string","kpi_primary":"string","kpi_secondary":["string"]}\n'
            "  ],\n"
            '  "keyword_clusters": ["string"],\n'
            '  "creative_angles": ["string"],\n'
            '  "kpi_targets": {"primary_kpi":"string","secondary_kpis":["string"],"success_criteria":"string"},\n'
            '  "next_steps": [{"task":"string","owner":"string","eta":"string"}],\n'
            '  "compliance_hinweis": "string"\n'
            "}\n"
        )

    def _call_ollama(self, prompt: str) -> tuple[str, str]:
        candidate_models = self._resolve_model_candidates()
        last_error: Exception | None = None

        for model_name in candidate_models:
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "format": _CAMPAIGN_PLAN_SCHEMA,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_predict": 120,
                },
            }
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=30,
                )
                if response.status_code == 404 and "model" in response.text.lower():
                    last_error = ValueError(
                        f"Ollama Modell nicht vorhanden: {model_name}"
                    )
                    continue
                response.raise_for_status()
                data = response.json()
                text = data.get("response")
                if not text:
                    raise ValueError("Leere Ollama-Antwort.")
                return str(text).strip(), model_name
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Ollama generate fehlgeschlagen (model=%s): %s",
                    model_name,
                    exc,
                )

        if last_error is not None:
            raise last_error
        raise ValueError("Kein verfuegbares Ollama-Modell gefunden.")

    def _resolve_model_candidates(self) -> list[str]:
        """Configured model first, then discovered local models from /api/tags."""
        candidates: list[str] = []
        configured = (self.model or "").strip()
        if configured:
            candidates.append(configured)

        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=4)
            response.raise_for_status()
            payload = response.json() or {}
            for entry in payload.get("models") or []:
                model_name = str(entry.get("name") or "").strip()
                if model_name and model_name not in candidates:
                    candidates.append(model_name)
        except Exception as exc:
            logger.warning("Ollama /api/tags nicht lesbar: %s", exc)

        return candidates or ["qwen2.5:7b"]

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

        return {
            "campaign_name": ai_plan.get("campaign_name") or (
                f"{playbook_candidate.get('playbook_title')} | {playbook_candidate.get('region_name')}"
            ),
            "objective": ai_plan.get("objective") or campaign_goal,
            "budget_shift_pct": float(ai_plan.get("budget_shift_pct") or playbook_candidate.get("budget_shift_pct") or 0.0),
            "activation_window_days": int(ai_plan.get("activation_window_days") or 10),
            "channel_plan": plan_channels,
            "keyword_clusters": ai_plan.get("keyword_clusters") or [],
            "creative_angles": ai_plan.get("creative_angles") or [],
            "kpi_targets": ai_plan.get("kpi_targets") or {
                "primary_kpi": "Qualified Visits",
                "secondary_kpis": ["CTR", "CPM"],
                "success_criteria": "Steigende Nachfrageabdeckung in Triggerregionen",
            },
            "next_steps": ai_plan.get("next_steps") or [],
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
