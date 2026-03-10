"""AI Campaign Planner via strictly local vLLM (OpenAI-compatible API)."""

from __future__ import annotations

from datetime import datetime
import json
import logging
import re
from typing import Any

from app.services.llm.vllm_service import generate_text, generate_text_sync
from app.services.media.campaign_guardrails import HWG_SYSTEM_PROMPT, check_hwg_compliance

logger = logging.getLogger(__name__)
_NUMBER_PATTERN = re.compile(r"-?\d+(?:[.,]\d+)?")

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
    """Generiert strukturierte Kampagnenpläne via strikt lokalem vLLM."""

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

            normalized, normalization_warnings, raw_validation_flags = self._normalize_plan(
                ai_plan,
                playbook_candidate,
                campaign_goal,
            )
            if normalization_warnings:
                logger.warning(
                    "AI plan normalized with warnings: %s",
                    " | ".join(normalization_warnings[:5]),
                )
            return {
                "ai_generation_status": "success",
                "ai_plan": normalized,
                "ai_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "model": self.model,
                    "provider": "vllm_local",
                    "fallback_used": False,
                    "normalization_warnings": normalization_warnings,
                    "raw_validation_flags": raw_validation_flags,
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
        forecast_assessment = playbook_candidate.get("forecast_assessment") or {}
        event_forecast = forecast_assessment.get("event_forecast") or playbook_candidate.get("event_forecast") or {}
        opportunity_assessment = playbook_candidate.get("opportunity_assessment") or {}
        readiness = (forecast_assessment.get("forecast_quality") or {}).get("forecast_readiness")

        return (
            "Du bist ein Senior Media Planner für Pharma-Brand-Cases.\n"
            "Erzeuge NUR valides JSON ohne Markdown, ohne Erklärtexte.\n"
            "Sprache: Deutsch. Konservativ formulieren (kein Heilversprechen).\n"
            "Output-Felder: campaign_name, objective, budget_shift_pct, activation_window_days, channel_plan, keyword_clusters, creative_angles, kpi_targets, next_steps, compliance_hinweis.\n"
            "budget_shift_pct MUSS eine einzelne Zahl sein (kein Text, keine Range, kein 'bis').\n"
            "activation_window_days MUSS ein Integer sein.\n"
            "channel_plan[].share_pct MUSS eine Zahl sein.\n"
            "Output: kompaktes JSON in EINER Zeile (kein Pretty-Print).\n\n"
            f"Brand: {brand}\n"
            f"Produkt: {product}\n"
            f"Kampagnenziel: {campaign_goal}\n"
            f"Playbook: {playbook_candidate.get('playbook_title')} ({playbook_candidate.get('playbook_key')})\n"
            f"Region: {playbook_candidate.get('region_name')} ({playbook_candidate.get('region_code')})\n"
            f"Forecast-Readiness: {readiness}\n"
            f"Event-Wahrscheinlichkeit 7T: {round(float(event_forecast.get('event_probability') or 0.0) * 100.0, 1)}%\n"
            f"Opportunity-Index: {opportunity_assessment.get('expected_value_index')}\n"
            f"Trigger: {trigger.get('event')} | {trigger.get('details')}\n"
            f"Message-Direction (fix): {direction}\n"
            f"Hero-Message (fix): {hero}\n"
            f"Support-Points (fix): {json.dumps(support, ensure_ascii=True)}\n"
            f"Compliance-Hinweis (fix): {compliance_note}\n"
            f"Wöchentliches Budget (EUR): {weekly_budget:.2f}\n"
            f"min_shift_pct: {min_shift}\n"
            f"max_shift_pct: {max_shift}\n"
            f"Kanal-Default-Mix: {json.dumps(channel_mix, ensure_ascii=True)}\n\n"
            "Beispiel (einzeilig): "
            "{\"campaign_name\":\"...\",\"objective\":\"...\",\"budget_shift_pct\":28.0,"
            "\"activation_window_days\":10,"
            "\"channel_plan\":[{\"channel\":\"programmatic\",\"share_pct\":35.0,"
            "\"message_angle\":\"...\",\"kpi_primary\":\"CTR\",\"kpi_secondary\":[\"CPM\"]}]}\n"
        )

    def _call_vllm(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": HWG_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        return generate_text_sync(messages=messages, temperature=0.2).strip()

    @staticmethod
    def _parse_json_response(raw: str) -> dict[str, Any]:
        cleaned = (raw or "").strip()
        # Remove markdown fences if present.
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # defensive extraction: first {...} block
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                return json.loads(cleaned[start : end + 1])
            raise

    @classmethod
    def _normalize_plan(
        cls,
        ai_plan: dict[str, Any],
        playbook_candidate: dict[str, Any],
        campaign_goal: str,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        warnings: list[str] = []
        flags: list[str] = []
        channel_default = playbook_candidate.get("channel_mix") or {}
        shift_bounds = playbook_candidate.get("shift_bounds") or {}
        min_shift = cls._to_float(
            shift_bounds.get("min"),
            default=-100.0,
            min_value=-100.0,
            max_value=100.0,
            warnings=warnings,
            flags=flags,
            field_name="shift_bounds.min",
        )
        max_shift = cls._to_float(
            shift_bounds.get("max"),
            default=100.0,
            min_value=-100.0,
            max_value=100.0,
            warnings=warnings,
            flags=flags,
            field_name="shift_bounds.max",
        )
        if min_shift > max_shift:
            min_shift, max_shift = max_shift, min_shift
            warnings.append("shift_bounds were inverted and have been swapped.")
            flags.append("shift_bounds_swapped")

        default_shift = cls._to_float(
            playbook_candidate.get("budget_shift_pct"),
            default=0.0,
            min_value=min_shift,
            max_value=max_shift,
            percent=True,
            warnings=warnings,
            flags=flags,
            field_name="playbook_candidate.budget_shift_pct",
        )
        budget_shift_pct = cls._to_float(
            ai_plan.get("budget_shift_pct"),
            default=default_shift,
            min_value=min_shift,
            max_value=max_shift,
            percent=True,
            warnings=warnings,
            flags=flags,
            field_name="budget_shift_pct",
        )

        activation_window_days = cls._to_int(
            ai_plan.get("activation_window_days"),
            default=10,
            min_value=1,
            max_value=30,
            warnings=warnings,
            flags=flags,
            field_name="activation_window_days",
        )

        plan_channels_raw = ai_plan.get("channel_plan")
        plan_channels: list[dict[str, Any]] = []
        if isinstance(plan_channels_raw, list):
            for idx, item in enumerate(plan_channels_raw):
                if not isinstance(item, dict):
                    warnings.append(f"channel_plan[{idx}] ignored because it is not an object.")
                    flags.append(f"channel_plan_{idx}_invalid")
                    continue
                channel = str(item.get("channel") or "").strip()
                if not channel:
                    warnings.append(f"channel_plan[{idx}] ignored because channel is missing.")
                    flags.append(f"channel_plan_{idx}_missing_channel")
                    continue
                share_pct = cls._to_float(
                    item.get("share_pct"),
                    default=0.0,
                    min_value=0.0,
                    max_value=100.0,
                    percent=True,
                    warnings=warnings,
                    flags=flags,
                    field_name=f"channel_plan[{idx}].share_pct",
                )
                if share_pct <= 0:
                    continue
                kpi_secondary_raw = item.get("kpi_secondary")
                if isinstance(kpi_secondary_raw, list):
                    kpi_secondary = [str(v).strip() for v in kpi_secondary_raw if str(v).strip()]
                else:
                    kpi_secondary = ["CPM"]
                plan_channels.append(
                    {
                        "channel": channel,
                        "share_pct": share_pct,
                        "message_angle": str(
                            item.get("message_angle")
                            or playbook_candidate.get("message_direction")
                            or "Situatives Timing"
                        ),
                        "kpi_primary": str(item.get("kpi_primary") or "CTR"),
                        "kpi_secondary": kpi_secondary or ["CPM"],
                    }
                )

        if not plan_channels:
            plan_channels = [
                {
                    "channel": str(channel),
                    "share_pct": cls._to_float(
                        share,
                        default=0.0,
                        min_value=0.0,
                        max_value=100.0,
                        percent=True,
                    ),
                    "message_angle": playbook_candidate.get("message_direction") or "Situatives Timing",
                    "kpi_primary": "CTR",
                    "kpi_secondary": ["CPM"],
                }
                for channel, share in channel_default.items()
                if str(channel).strip()
            ]
            if plan_channels:
                warnings.append("channel_plan replaced with channel defaults.")
                flags.append("channel_plan_defaulted")

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
                "Jetzt verfügbar trotz Engpass",
                "Pflanzliche Alternative",
                "Apotheken-Nähe: sofort finden",
            ],
            "WETTER_REFLEX": [
                "Schietwetter: präventiv",
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
            {"task": "KPI-Dashboard für Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1"},
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

        normalized = {
            "campaign_name": ai_plan.get("campaign_name") or (
                f"{playbook_candidate.get('playbook_title')} | {playbook_candidate.get('region_name')}"
            ),
            "objective": ai_plan.get("objective") or campaign_goal,
            "budget_shift_pct": budget_shift_pct,
            "activation_window_days": activation_window_days,
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
        unique_warnings = list(dict.fromkeys(warnings))
        unique_flags = list(dict.fromkeys(flags))
        return normalized, unique_warnings, unique_flags

    @staticmethod
    def _to_float(
        value: Any,
        default: float,
        min_value: float | None = None,
        max_value: float | None = None,
        percent: bool = False,
        warnings: list[str] | None = None,
        flags: list[str] | None = None,
        field_name: str = "value",
    ) -> float:
        def _warn(msg: str, flag: str | None = None) -> None:
            if warnings is not None:
                warnings.append(msg)
            if flags is not None and flag:
                flags.append(flag)

        result = float(default)
        if isinstance(value, bool):
            _warn(f"{field_name} was bool and defaulted.", f"{field_name}_bool_default")
        elif isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            text = value.strip()
            if text:
                text = text.replace("%", "") if percent else text
                matches = _NUMBER_PATTERN.findall(text)
                if matches:
                    if len(matches) > 1:
                        _warn(
                            f"{field_name} had range/text input and was normalized to first number.",
                            f"{field_name}_range_text",
                        )
                    token = matches[0].replace(",", ".")
                    try:
                        result = float(token)
                    except ValueError:
                        _warn(f"{field_name} could not be parsed and defaulted.", f"{field_name}_parse_default")
                else:
                    _warn(f"{field_name} had no numeric token and defaulted.", f"{field_name}_missing_number")
            else:
                _warn(f"{field_name} was empty string and defaulted.", f"{field_name}_empty")
        elif value is None:
            pass
        else:
            _warn(f"{field_name} had unsupported type and defaulted.", f"{field_name}_unsupported")

        if min_value is not None and result < min_value:
            _warn(f"{field_name} was clamped to min {min_value}.", f"{field_name}_clamped_min")
            result = min_value
        if max_value is not None and result > max_value:
            _warn(f"{field_name} was clamped to max {max_value}.", f"{field_name}_clamped_max")
            result = max_value
        return result

    @classmethod
    def _to_int(
        cls,
        value: Any,
        default: int,
        min_value: int | None = None,
        max_value: int | None = None,
        warnings: list[str] | None = None,
        flags: list[str] | None = None,
        field_name: str = "value",
    ) -> int:
        parsed = cls._to_float(
            value,
            default=float(default),
            min_value=float(min_value) if min_value is not None else None,
            max_value=float(max_value) if max_value is not None else None,
            warnings=warnings,
            flags=flags,
            field_name=field_name,
        )
        return int(round(parsed))

    def _deterministic_fallback(
        self,
        *,
        playbook_candidate: dict[str, Any],
        campaign_goal: str,
        brand: str,
        product: str,
        weekly_budget: float,
    ) -> dict[str, Any]:
        shift_pct = self._to_float(playbook_candidate.get("budget_shift_pct"), default=0.0, min_value=-100.0, max_value=100.0, percent=True)
        shift_value = round(abs(weekly_budget) * abs(shift_pct) / 100.0, 2)
        channel_mix = playbook_candidate.get("channel_mix") or {}
        channel_plan = []
        for channel, share in channel_mix.items():
            share_num = self._to_float(share, default=0.0, min_value=0.0, max_value=100.0, percent=True)
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
                "Verfügbarkeitskommunikation",
            ],
            "creative_angles": [
                "Problem-Symptom-Ansprache mit konservativem Claim",
                "Regionale Aktivierung bei messbarem Trigger",
                "Verfügbarkeit im Fokus",
            ],
            "kpi_targets": {
                "primary_kpi": "Qualified Visits",
                "secondary_kpis": ["CTR", "CPM", "Reach"],
                "success_criteria": "Höhere Nachfrageabdeckung in den nächsten 14 Tagen bei stabiler Effizienz",
            },
            "next_steps": [
                {"task": "Kampagnenstruktur im Ad-Setup anlegen", "owner": "Media Ops", "eta": "T+0"},
                {"task": "Creatives mit Compliance abstimmen", "owner": "Account Lead", "eta": "T+1"},
                {"task": "KPI-Dashboard für Daily Monitoring aktivieren", "owner": "Analytics", "eta": "T+1"},
            ],
            "compliance_hinweis": "Backtest-basierte, konservative Aussagen verwenden; keine Heilversprechen.",
        }
