"""PitchGenerator — Sales-Pitch-Generierung (LLM-first, Template-Fallback).

UI erwartet:
  sales_pitch = {headline_email, script_phone, call_to_action}
"""

from __future__ import annotations

import json
import logging

from app.services.llm.vllm_service import generate_text, generate_text_sync
from app.services.media.campaign_guardrails import HWG_SYSTEM_PROMPT, check_hwg_compliance

logger = logging.getLogger(__name__)


TEMPLATES = {
    "RESOURCE_SCARCITY": {
        "Antibiotika": {
            "headline_email": ("Wichtiger Hinweis: {wave_type}-Engpass bei {category_de}"),
            "script_phone": (
                "Guten Tag, wir sehen im System, dass {top_drug} derzeit auf 'Defekt' steht. "
                "Bevor Sie Restbestände auf Verdacht nutzen: Mit einem CRP-Schnelltest "
                "filtern Sie virale Infekte sofort raus und sparen Antibiotika für die "
                "wirklich bakteriellen Fälle. Sollen wir Ihren Bestand aufstocken?"
            ),
            "call_to_action": "CRP-Diagnostik sichern",
        },
        "Atemwege": {
            "headline_email": ("Atemwegsmedikamenten-Engpass: Gezielte Diagnostik statt Blindtherapie"),
            "script_phone": (
                "Kurze Info: Mehrere Atemwegsmedikamente sind aktuell nicht lieferbar. "
                "Mit einem Multiplex-PCR-Panel können Sie den Erreger identifizieren "
                "und gezielt die verfügbaren Alternativen einsetzen. "
                "Wir haben Panels auf Lager."
            ),
            "call_to_action": "Multiplex PCR Panel bestellen",
        },
        "Fieber_Schmerz": {
            "headline_email": ("Ibuprofen/Paracetamol knapp: Differentialdiagnose wird wichtiger"),
            "script_phone": (
                "Weil Fieber- und Schmerzmittel derzeit schwer verfügbar sind, "
                "wird eine saubere Differentialdiagnose umso wichtiger. "
                "Haben Sie genug Laborkapazität für CRP und Blutbild?"
            ),
            "call_to_action": "Laborkapazität prüfen",
        },
    },
    "SEASONAL_DEFICIENCY": {
        "default": {
            "headline_email": ("Patienten müde & infektanfällig? Der Wetterbericht liefert den Grund."),
            "script_phone": (
                "Kurze Info aus unserer Datenanalyse: In Ihrer Region hatten wir "
                "seit über {consecutive_days} Tagen keine vitaminwirksame UV-Strahlung. "
                "Wenn Ihre Patienten über 'Winterblues' klagen, ist es wahrscheinlich "
                "ein Vitamin-D-Mangel. Wir haben dafür Infomaterial für Ihr Wartezimmer."
            ),
            "call_to_action": "Vitamin-D Laborkapazität prüfen",
        },
        "cold_fallback": {
            "headline_email": ("Kälteperiode: Vitamin-D-Screening für Risikopatienten"),
            "script_phone": (
                "Bei den aktuellen Temperaturen ({avg_temperature}°C Durchschnitt) "
                "und fehlender Sonneneinstrahlung steigt das Risiko für Vitamin-D-Mangel. "
                "Besonders bei älteren Patienten und chronisch Kranken empfehlen wir "
                "ein Screening."
            ),
            "call_to_action": "Vitamin-D-Screening-Kit anfragen",
        },
    },
    "PREDICTIVE_SALES_SPIKE": {
        "default": {
            "headline_email": ("Hohe Nachfrage in {region}: {article_name} jetzt sichern"),
            "script_phone": (
                "Ich rufe an, weil wir in {region} seit gestern einen massiven "
                "Ansturm auf {article_name} sehen — Ihre Nachbarpraxen decken sich "
                "gerade ein. {velocity_info} "
                "Sollen wir noch schnell eine Lieferung losschicken, "
                "bevor wir Lieferzeiten bekommen?"
            ),
            "call_to_action": "Sofortversand anbieten",
        },
    },
    "WEATHER_FORECAST": {
        "low_sunshine_forecast": {
            "headline_email": ("8-Tage-Prognose: Keine Sonne in Sicht — Vitamin-D-Screening jetzt ansprechen"),
            "script_phone": (
                "Guten Tag, kurzer Hinweis aus unserer Wetterdaten-Analyse: "
                "Die nächsten {low_days} von {total_days} Tagen zeigen einen UV-Index unter {uv_threshold} — "
                "das bedeutet, Ihre Patienten können kein Vitamin D bilden. "
                "Jetzt ist der ideale Zeitpunkt, um bei Risikopatienten ein 25-OH-Vitamin-D "
                "Screening anzubieten, bevor die Beschwerden einsetzen."
            ),
            "call_to_action": "Vitamin-D Screening proaktiv anbieten",
        },
        "nasskalt_forecast": {
            "headline_email": ("Nasskalte Woche voraus: Erkältungswelle vorbereiten"),
            "script_phone": (
                "Laut unserer Prognose stehen {nasskalt_days} nasskalte Tage bevor — "
                "ideal für eine Erkältungswelle. Jetzt ist der richtige Zeitpunkt, "
                "Ihre Vorräte an respiratorischen Schnelltests aufzustocken, "
                "damit Sie im Ansturm handlungsfähig bleiben."
            ),
            "call_to_action": "Atemwegs-Schnelltests bevorraten",
        },
        "extreme_cold_forecast": {
            "headline_email": ("Extremkälte-Warnung: Infektionswelle steht bevor"),
            "script_phone": (
                "Achtung: Die Wetterprognose zeigt {extreme_days} Tage mit "
                "Temperaturen bis zu {min_temp}°C. Erfahrungsgemäß steigt die "
                "Infektionsrate in solchen Phasen stark an. Haben Sie genügend "
                "CRP-Tests und Multiplex-Panels auf Lager?"
            ),
            "call_to_action": "Diagnostik-Vorräte sichern",
        },
    },
}

# Kategorie-Übersetzungen
CATEGORY_DE = {
    "Antibiotika": "Antibiotika",
    "Atemwege": "Atemwegsmedikamenten",
    "Fieber_Schmerz": "Fieber-/Schmerzmitteln",
}

WAVE_TYPE_DE = {
    "Bacterial": "Bakterielle Welle",
    "Respiratory_Viral": "Respiratorische Viruswelle",
    "General_Infection": "Allgemeine Infektionswelle",
    "Mixed": "Gemischte Welle",
    "None": "Unbestimmt",
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
    """Generiert Sales-Pitch-Texte (LLM-first; deterministic fallback)."""

    def generate(self, opportunity_type: str, context: dict) -> dict:
        """Erzeugt Sales Pitch basierend auf Typ und Kontext."""
        llm_pitch = self._generate_llm_sales_pitch(opportunity_type=opportunity_type, context=context)
        if llm_pitch:
            return llm_pitch

        # fallback: deterministic templates
        if opportunity_type == "RESOURCE_SCARCITY":
            return self._generate_scarcity(context)
        elif opportunity_type == "SEASONAL_DEFICIENCY":
            return self._generate_seasonal(context)
        elif opportunity_type == "PREDICTIVE_SALES_SPIKE":
            return self._generate_spike(context)
        elif opportunity_type == "WEATHER_FORECAST":
            return self._generate_weather_forecast(context)
        else:
            return {
                "headline_email": "Neue Vertriebschance erkannt",
                "script_phone": "Wir haben eine relevante Marktveränderung festgestellt.",
                "call_to_action": "Kontaktieren Sie uns",
            }

    async def generate_pitch(self, product_name: str, target_audience: str, context_data: dict) -> str:
        """Generiert einen kurzen Marketing-Pitch (Text) über den lokalen vLLM Endpunkt."""
        user_prompt = (
            f"Erstelle einen kurzen Marketing-Pitch für das Produkt '{product_name}'.\n"
            f"Zielgruppe: {target_audience}.\n"
            f"Aktuelle Datenlage (Wetter/Pollen/RKI): {context_data}."
        )

        messages = [
            {"role": "system", "content": HWG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        generated_pitch = await generate_text(messages=messages, temperature=0.3)
        if not check_hwg_compliance(generated_pitch):
            logger.warning("HWG blockiert in PitchGenerator für %s", product_name)
            return "Aus rechtlichen Gründen (HWG) wurde dieser Text blockiert. Bitte manuell anpassen."
        return generated_pitch

    def _generate_llm_sales_pitch(self, *, opportunity_type: str, context: dict) -> dict | None:
        prompt = (
            "Erstelle einen kurzen Sales Pitch für ein B2B Labordiagnostik-Angebot.\n"
            "Output: NUR valides JSON (eine Zeile, ohne Markdown) mit Keys:\n"
            '- "headline_email" (max 120 Zeichen),\n'
            '- "script_phone" (max 400 Zeichen),\n'
            '- "call_to_action" (max 60 Zeichen).\n'
            "Sprache: Deutsch. Konservativ, keine Heilversprechen oder Garantien.\n\n"
            f"Opportunity-Type: {opportunity_type}\n"
            f"Context: {json.dumps(context or {}, ensure_ascii=True)}\n"
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
            logger.warning("HWG blockiert LLM Sales-Pitch (type=%s)", opportunity_type)
            return None

        return {
            "headline_email": headline,
            "script_phone": script,
            "call_to_action": cta,
        }

    def _generate_scarcity(self, ctx: dict) -> dict:
        category = ctx.get("_category", "Antibiotika")
        template = TEMPLATES["RESOURCE_SCARCITY"].get(
            category, TEMPLATES["RESOURCE_SCARCITY"]["Antibiotika"]
        )

        top_drugs = ctx.get("_top_drugs", [])
        top_drug = top_drugs[0] if top_drugs else "verschiedene Präparate"
        wave_type = WAVE_TYPE_DE.get(ctx.get("_wave_type", "None"), "Unbestimmt")
        category_de = CATEGORY_DE.get(category, category)

        return {
            "headline_email": template["headline_email"].format(
                wave_type=wave_type,
                category_de=category_de,
            ),
            "script_phone": template["script_phone"].format(
                top_drug=top_drug,
            ),
            "call_to_action": template["call_to_action"],
        }

    def _generate_seasonal(self, ctx: dict) -> dict:
        consecutive_days = ctx.get("_consecutive_days", 0)
        avg_temp = ctx.get("_avg_temperature", None)

        if consecutive_days > 0:
            template = TEMPLATES["SEASONAL_DEFICIENCY"]["default"]
            return {
                "headline_email": template["headline_email"],
                "script_phone": template["script_phone"].format(
                    consecutive_days=consecutive_days,
                ),
                "call_to_action": template["call_to_action"],
            }
        else:
            template = TEMPLATES["SEASONAL_DEFICIENCY"]["cold_fallback"]
            return {
                "headline_email": template["headline_email"],
                "script_phone": template["script_phone"].format(
                    avg_temperature=avg_temp or "niedrig",
                ),
                "call_to_action": template["call_to_action"],
            }

    def _generate_weather_forecast(self, ctx: dict) -> dict:
        condition = ctx.get("_condition", "low_sunshine_forecast")
        template = TEMPLATES["WEATHER_FORECAST"].get(
            condition, TEMPLATES["WEATHER_FORECAST"]["low_sunshine_forecast"]
        )

        format_vars = {
            "low_days": ctx.get("_low_days", 0),
            "total_days": ctx.get("_total_days", 8),
            "uv_threshold": 3.0,
            "avg_uv": ctx.get("_avg_uv", "niedrig"),
            "nasskalt_days": ctx.get("_nasskalt_days", 0),
            "extreme_days": ctx.get("_extreme_days", 0),
            "min_temp": ctx.get("_min_temp", "sehr niedrig"),
        }

        return {
            "headline_email": template["headline_email"].format(**format_vars),
            "script_phone": template["script_phone"].format(**format_vars),
            "call_to_action": template["call_to_action"],
        }

    def _generate_spike(self, ctx: dict) -> dict:
        template = TEMPLATES["PREDICTIVE_SALES_SPIKE"]["default"]
        article_id = ctx.get("_article_id", "Testkits")
        velocity = ctx.get("_velocity", 0)
        plz = ctx.get("region_target", {}).get("plz_cluster", "Ihrer Region")
        region = plz if plz != "ALL" else "Ihrer Region"

        velocity_info = f"Die Bestellungen sind um {abs(velocity) * 100:.0f}% gestiegen in 48h."

        return {
            "headline_email": template["headline_email"].format(
                region=region,
                article_name=article_id,
            ),
            "script_phone": template["script_phone"].format(
                region=region,
                article_name=article_id,
                velocity_info=velocity_info,
            ),
            "call_to_action": template["call_to_action"],
        }

