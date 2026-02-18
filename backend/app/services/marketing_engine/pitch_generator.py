"""PitchGenerator — Gelo OTC Copy (LLM-first, deterministic fallback).

This codebase is scoped to consumer OTC marketing for Gelo products.
Hard rules:
- HWG compliance (no healing promises, no guarantees, no "side-effect free").
- No lab diagnostics sales copy.

UI expects:
  sales_pitch = {headline_email, script_phone, call_to_action}
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any

from app.services.llm.vllm_service import generate_text_sync
from app.services.media.campaign_guardrails import HWG_SYSTEM_PROMPT, check_hwg_compliance
from app.services.media.message_library import select_gelo_message_pack

logger = logging.getLogger(__name__)

LLM_PITCHES_ENABLED = os.getenv("MEDIA_LLM_PITCHES_ENABLED", "0").strip() == "1"

TEMPLATES: dict[str, dict[str, Any]] = {
    "RESOURCE_SCARCITY": {
        "default": {
            "headline_email": "Engpass-Signal im Markt: jetzt konservativ kommunizieren",
            "script_phone": (
                "Kurzer Hinweis aus unserer Marktbeobachtung: In Ihrer Region gibt es aktuell Engpasssignale. "
                "Empfehlung: Verfuegbarkeit und konservative, symptomnahe Kommunikation betonen "
                "(ohne Heilversprechen). Soll die Aktivierung in den betroffenen Regionen priorisiert werden?"
            ),
            "call_to_action": "Aktivierung priorisieren",
        }
    },
    "PREDICTIVE_SALES_SPIKE": {
        "default": {
            "headline_email": "Nachfrage-Signal: {product_or_article} in {region} priorisieren",
            "script_phone": (
                "Wir sehen ein klares Nachfrage-/Velocity-Signal fuer {product_or_article}. "
                "{velocity_info} "
                "Empfehlung: Budget und Sichtbarkeit in den betroffenen Regionen kurzfristig anheben, "
                "mit konservativen symptomnahen Botschaften (HWG-konform)."
            ),
            "call_to_action": "Kampagne ausspielen",
        }
    },
    "WEATHER_FORECAST": {
        "immun_support": {
            "headline_email": "Weniger Sonne voraus: Immun-Support im Alltag positionieren",
            "script_phone": (
                "Die Wetterprognose zeigt mehrere Tage mit niedriger UV-Intensitaet. "
                "Konservatives Signal fuer saisonale Belastung: Jetzt ist ein gutes Zeitfenster, "
                "um 'Immunsystem im Alltag unterstuetzen' zu positionieren (ohne Therapieanweisungen)."
            ),
            "call_to_action": "Praeventive Aktivierung starten",
        },
        "erkaltung_akut": {
            "headline_email": "Nasskalt voraus: Erkältung im Anflug, jetzt sichtbar werden",
            "script_phone": (
                "Die Prognose zeigt mehrere nasskalte Tage. Erfahrungsgemaess steigt in solchen Phasen "
                "das Erkältungs-Interesse. Empfehlung: symptomnahe, konservative Botschaften ausspielen "
                "und regionale Flights priorisieren."
            ),
            "call_to_action": "Regional aktivieren",
        },
        "default": {
            "headline_email": "Wetter-Trigger erkannt: konservativ und symptomnah aktivieren",
            "script_phone": (
                "Ein Wetter-Trigger deutet auf ein moegliches Nachfragefenster hin. "
                "Empfehlung: regional priorisieren und Copy streng HWG-konform halten."
            ),
            "call_to_action": "Empfehlung pruefen",
        },
    },
}


def _parse_json_response(raw: str) -> dict | None:
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(raw[start : end + 1])
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        return None


class PitchGenerator:
    """Generiert consumer-OTC Pitches (LLM-first; deterministic fallback)."""

    def generate(self, opportunity_type: str, context: dict) -> dict:
        # Default: deterministic only (fast + predictable). Enable LLM explicitly via env.
        if LLM_PITCHES_ENABLED:
            llm_pitch = self._generate_llm_pitch(opportunity_type=opportunity_type, context=context or {})
            if llm_pitch:
                return llm_pitch

        # fallback: deterministic templates
        if opportunity_type == "RESOURCE_SCARCITY":
            return self._generate_resource_scarcity(context or {})
        if opportunity_type == "PREDICTIVE_SALES_SPIKE":
            return self._generate_sales_spike(context or {})
        if opportunity_type == "WEATHER_FORECAST":
            return self._generate_weather(context or {})

        return {
            "headline_email": "Neue Aktivierungs-Chance erkannt",
            "script_phone": "Wir haben ein relevantes, triggerbasiertes Bedarfssignal erkannt.",
            "call_to_action": "Empfehlung pruefen",
        }

    def _generate_llm_pitch(self, *, opportunity_type: str, context: dict) -> dict | None:
        brand = str(context.get("brand") or "Gelo")
        product = str(context.get("product") or context.get("_article_id") or "Gelo Produkt")
        region = str((context.get("region_target") or {}).get("plz_cluster") or "DE")
        condition_key = str(context.get("_condition") or "erkaltung_akut")

        pack = select_gelo_message_pack(
            brand=brand,
            product=product,
            condition_key=condition_key,
            playbook_key=None,
            region_code=None,
            trigger_event=str((context.get("trigger_context") or {}).get("event") or ""),
        )
        hints = pack.to_prompt_hints()

        prompt = (
            "Erstelle einen kurzen Marketing-Pitch fuer ein OTC-Produkt (Gelo) fuer den deutschen Markt.\n"
            "Hard Rules (HWG): Keine Heilversprechen, keine Garantien, keine Nebenwirkungsfreiheit.\n"
            "Output: NUR valides JSON (eine Zeile, ohne Markdown) mit Keys:\n"
            '- "headline_email" (max 120 Zeichen),\n'
            '- "script_phone" (max 420 Zeichen),\n'
            '- "call_to_action" (max 60 Zeichen).\n'
            "Sprache: Deutsch. Konservativ und professionell.\n\n"
            f"Opportunity-Type: {opportunity_type}\n"
            f"Region/Context: {json.dumps(context, ensure_ascii=True)}\n"
            f"Copy-Hints (deterministisch, nicht erfinden): {json.dumps(hints, ensure_ascii=True)}\n"
        )

        messages = [
            {"role": "system", "content": HWG_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        raw = generate_text_sync(messages=messages, temperature=0.2)
        pitch = _parse_json_response(raw)
        if not pitch:
            return None

        headline = str(pitch.get("headline_email") or "").strip()
        script = str(pitch.get("script_phone") or "").strip()
        cta = str(pitch.get("call_to_action") or "").strip()
        if not headline or not script or not cta:
            return None

        combined = f"{headline}\n{script}\n{cta}"
        if not check_hwg_compliance(combined):
            logger.warning("HWG blockiert LLM Pitch (type=%s)", opportunity_type)
            return None

        return {
            "headline_email": headline,
            "script_phone": script,
            "call_to_action": cta,
        }

    def _generate_resource_scarcity(self, ctx: dict) -> dict:
        template = TEMPLATES["RESOURCE_SCARCITY"]["default"]
        return {
            "headline_email": template["headline_email"],
            "script_phone": template["script_phone"],
            "call_to_action": template["call_to_action"],
        }

    def _generate_sales_spike(self, ctx: dict) -> dict:
        template = TEMPLATES["PREDICTIVE_SALES_SPIKE"]["default"]
        region = str((ctx.get("region_target") or {}).get("plz_cluster") or "DE")
        article = str(ctx.get("_article_id") or "Produkt")
        velocity = float(ctx.get("_velocity") or 0.0)
        velocity_info = f"Signalstaerke: {abs(velocity) * 100:.0f}%."
        return {
            "headline_email": template["headline_email"].format(product_or_article=article, region=region),
            "script_phone": template["script_phone"].format(product_or_article=article, region=region, velocity_info=velocity_info),
            "call_to_action": template["call_to_action"],
        }

    def _generate_weather(self, ctx: dict) -> dict:
        condition = str(ctx.get("_condition") or "default")
        templates = TEMPLATES["WEATHER_FORECAST"]
        template = templates.get(condition) or templates["default"]
        return {
            "headline_email": template["headline_email"],
            "script_phone": template["script_phone"],
            "call_to_action": template["call_to_action"],
        }
