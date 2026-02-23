"""Guardrails für AI-generierte Campaign-Plans und HWG-Compliance."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services.media.playbook_engine import PLAYBOOK_CATALOG

logger = logging.getLogger(__name__)

# Deterministischer System Prompt, um das Modell "einzuzäunen"
HWG_SYSTEM_PROMPT = """Du bist ein hochqualifizierter, juristisch geschulter Medical Copywriter für den deutschen Pharma-Markt (Marke Gelo).
Deine absolute, unverrückbare Basis ist das Heilmittelwerbegesetz (HWG).
Du darfst NIEMALS Heilversprechen machen.
Du darfst NIEMALS Garantien abgeben oder von Nebenwirkungsfreiheit sprechen.
Nutze ausschließlich lindernde, unterstützende und wohltuende Formulierungen (z.B. "unterstützt die Heilung", "lindert die Symptome", "befreit spürbar", "hilft bei").
Verhalte dich stets objektiv, professionell und wissenschaftlich fundiert.
"""

# Hardcoded Regex-Blockliste als finale Sicherung (falls die KI halluziniert).
# Abgedeckt: §1 HWG (Heilversprechen), §3 (irreführende Werbung),
# §9 (Gutachten-/Testimonial-Missbrauch), §14 (Fernbehandlung).
HWG_BLOCKLIST = [
    # ── §1 / §3 HWG: Heilversprechen & Garantien ──
    r"\bheilt\b",
    r"\bHeilung\b",
    r"\bgarantiert\b",
    r"\bsofortige\s+Heilung\b",
    r"100\s*%",
    r"\bWundermittel\b",
    r"\bnebenwirkungsfrei\b",
    r"\bmacht\s+gesund\b",
    r"\bsicher\s+wirksam\b",
    r"\bklinisch\s+bewiesen\b",
    r"\bwissenschaftlich\s+bewiesen\b",
    r"\bnachweislich\s+heilt\b",
    r"\bbeseitigt\b",
    r"\bvernichtet\b",
    r"\btoetet\s+(?:Viren|Bakterien|Keime)\b",
    r"\bsofort\s+(?:gesund|beschwerdefrei|symptomfrei)\b",
    r"\bein\s+fuer\s+alle\s+[Mm]al\b",
    r"\bendgueltig\b",
    r"\bfuer\s+immer\b",
    r"\bohnmachtssicher\b",
    r"\brisikolos\b",
    r"\brisikofrei\b",
    r"\bvollstaendige?\s+(?:Heilung|Genesung)\b",
    r"\b(?:keinerlei|ohne\s+jede)\s+Nebenwirkung",
    r"\bfrei\s+von\s+Nebenwirkungen\b",
    r"\bunbedingt\s+wirksam\b",
    r"\bnachgewiesene\s+Heilwirkung\b",
    r"\bAlternative\s+zu[rm]?\s+(?:Arzt|Arztbesuch|Operation)\b",
    # ── §3 HWG: irreführende Superlative & Vergleiche ──
    r"\bbeste[rs]?\s+(?:Mittel|Medikament|Arznei)\b",
    r"\bNr\.?\s*1\b",
    r"\bMarktfuehrer\b",
    r"\bunerreicht\b",
    r"\beinzigartig\s+wirksam\b",
    r"\bstaerker\s+als\s+(?:jedes?\s+andere|Antibiotika)\b",
    r"\bwirksamer\s+als\b",
    r"\bnichts\s+(?:hilft|wirkt)\s+besser\b",
    r"\bersetzt\s+(?:den\s+)?Arzt",
    # ── §9 HWG: Gutachten / Testimonials (fiktiv) ──
    r"\bArzt\s+empfiehlt\b",
    r"\bAerzte\s+empfehlen\b",
    r"\bApotheker\s+empfiehlt\b",
    r"\b(?:laut|nach)\s+(?:einer\s+)?(?:Studie|Untersuchung)\s+(?:heilt|beseitigt)\b",
    r"\bvon\s+Aerzten\s+(?:empfohlen|verordnet)\b",
    # ── §14 HWG: Fernbehandlung / Eigendiagnose ──
    r"\bSelbstdiagnose\b",
    r"\bersetzt\s+(?:die\s+)?(?:aerztliche|medizinische)\s+(?:Beratung|Behandlung)\b",
    r"\bstatt\s+(?:zum\s+)?Arzt\b",
    r"\bkein\s+Arzt\s+(?:noetig|notwendig|erforderlich)\b",
]


def check_hwg_compliance(text: str) -> bool:
    """
    Prüft, ob der generierte Text gegen das Heilmittelwerbegesetz (HWG) verstößt.
    Gibt True zurück (Safe), wenn kein Regelverstoß gefunden wurde.
    """
    if not text:
        return False

    for pattern in HWG_BLOCKLIST:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"HWG Guardrail ausgelöst! Verbotenes Muster: {pattern}")
            return False

    return True


_BANNED_PHRASES = list(dict.fromkeys(HWG_BLOCKLIST))


class CampaignGuardrails:
    """Validiert und korrigiert KI-Ausgaben innerhalb harter Produktregeln."""

    def apply(
        self,
        *,
        playbook_key: str,
        ai_plan: dict[str, Any],
        weekly_budget: float,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "passed": True,
            "notes": [],
            "applied_fixes": [],
        }
        safe_plan = dict(ai_plan or {})
        cfg = PLAYBOOK_CATALOG.get(playbook_key) or {}

        # 1) Shift-Grenzen
        requested_shift = float(safe_plan.get("budget_shift_pct") or 0.0)
        shift_min = float(cfg.get("shift_min", -100.0))
        shift_max = float(cfg.get("shift_max", 100.0))
        clamped_shift = max(min(requested_shift, max(shift_min, shift_max)), min(shift_min, shift_max))
        if clamped_shift != requested_shift:
            report["applied_fixes"].append(
                f"budget_shift_pct von {requested_shift:.1f} auf {clamped_shift:.1f} angepasst (Playbook-Grenzen)."
            )
        safe_plan["budget_shift_pct"] = round(clamped_shift, 1)

        # 2) Aktivierungsfenster
        window_days = int(safe_plan.get("activation_window_days") or 10)
        bounded_days = max(1, min(28, window_days))
        if bounded_days != window_days:
            report["applied_fixes"].append(
                f"activation_window_days von {window_days} auf {bounded_days} angepasst (1-28)."
            )
        safe_plan["activation_window_days"] = bounded_days

        # 3) Channel shares = 100 + budget >= 0
        channel_plan = safe_plan.get("channel_plan")
        if not isinstance(channel_plan, list) or not channel_plan:
            defaults = cfg.get("default_mix") or {}
            channel_plan = [{"channel": channel, "share_pct": share} for channel, share in defaults.items()]
            report["applied_fixes"].append("channel_plan fehlte und wurde mit Playbook-Defaults gesetzt.")

        normalized = self._normalize_channel_plan(
            channel_plan=channel_plan,
            shift_pct=abs(float(safe_plan.get("budget_shift_pct") or 0.0)),
            weekly_budget=max(0.0, float(weekly_budget or 0.0)),
            report=report,
        )
        safe_plan["channel_plan"] = normalized

        # 4) Claims sanitizen
        self._sanitize_text_fields(safe_plan, report)

        # 5) Compliance-Hinweis erzwingen
        compliance = str(safe_plan.get("compliance_hinweis") or "").strip()
        if not compliance:
            compliance = "Hinweis: Aussagen konservativ halten (z. B. 'kann', 'Backtest-basiert')."
            report["applied_fixes"].append("compliance_hinweis ergänzt.")
        if "kann" not in compliance.lower() and "backtest" not in compliance.lower():
            compliance = compliance.rstrip(".") + ". Claims nur konservativ formulieren (z. B. 'kann')."
            report["applied_fixes"].append("compliance_hinweis um konservative Claim-Regel erweitert.")
        safe_plan["compliance_hinweis"] = compliance

        # Final-Check (sollte nach Sanitizing i.d.R. OK sein)
        combined = " ".join(
            str(v)
            for v in (
                safe_plan.get("campaign_name"),
                safe_plan.get("objective"),
                safe_plan.get("compliance_hinweis"),
            )
            if v
        )
        if combined and not check_hwg_compliance(combined):
            report["passed"] = False
            report["notes"].append("HWG Final-Check fehlgeschlagen (nach Sanitizing).")

        return {
            "ai_plan": safe_plan,
            "guardrail_report": report,
            "guardrail_notes": report["applied_fixes"] or ["Keine Korrekturen erforderlich."],
        }

    @staticmethod
    def _normalize_channel_plan(
        *,
        channel_plan: list[dict[str, Any]],
        shift_pct: float,
        weekly_budget: float,
        report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        total = 0.0
        for row in channel_plan:
            channel = str(row.get("channel") or "").strip().lower()
            if not channel:
                continue
            share = float(row.get("share_pct") or 0.0)
            share = max(0.0, share)
            total += share
            items.append(
                {
                    "channel": channel,
                    "share_pct": share,
                    "message_angle": row.get("message_angle") or "Kontextbasiertes Timing",
                    "kpi_primary": row.get("kpi_primary") or "CTR",
                    "kpi_secondary": row.get("kpi_secondary") or ["CPM"],
                }
            )

        if not items:
            items = [
                {
                    "channel": "programmatic",
                    "share_pct": 100.0,
                    "message_angle": "Kontextbasiertes Timing",
                    "kpi_primary": "CTR",
                    "kpi_secondary": ["CPM"],
                }
            ]
            total = 100.0
            report["applied_fixes"].append("Leerer channel_plan auf programmatic 100% gesetzt.")

        if total <= 0:
            equal = round(100.0 / len(items), 1)
            for row in items:
                row["share_pct"] = equal
            total = sum(float(row["share_pct"]) for row in items)
            report["applied_fixes"].append("Channel-Shares waren 0 und wurden gleichmäßig verteilt.")

        normalized: list[dict[str, Any]] = []
        for row in items:
            share = (float(row["share_pct"]) / total) * 100.0
            normalized.append({**row, "share_pct": round(share, 1)})
        diff = round(100.0 - sum(float(row["share_pct"]) for row in normalized), 1)
        normalized[0]["share_pct"] = round(float(normalized[0]["share_pct"]) + diff, 1)
        if abs(diff) > 0:
            report["applied_fixes"].append("Channel-Shares auf exakt 100% normalisiert.")

        shift_value = weekly_budget * (shift_pct / 100.0)
        for row in normalized:
            row["budget_eur"] = round(max(0.0, shift_value * (float(row["share_pct"]) / 100.0)), 2)
        return normalized

    def _sanitize_text_fields(self, safe_plan: dict[str, Any], report: dict[str, Any]) -> None:
        def _clean(text: str) -> str:
            out = text
            for pattern in _BANNED_PHRASES:
                out = re.sub(pattern, "kann unterstützen", out, flags=re.IGNORECASE)
            out = out.replace("SOFORT VERFÜGBAR", "verfügbar").replace("SOFORT VERFUEGBAR", "verfügbar")
            return out

        # string fields
        for field in ("campaign_name", "objective", "compliance_hinweis"):
            value = safe_plan.get(field)
            if isinstance(value, str):
                cleaned = _clean(value)
                if cleaned != value:
                    safe_plan[field] = cleaned
                    report["applied_fixes"].append(f"Claim-Sanitizing auf Feld '{field}' angewendet.")

        # list fields
        for list_field in ("creative_angles", "keyword_clusters"):
            values = safe_plan.get(list_field)
            if isinstance(values, list):
                new_values = []
                touched = False
                for item in values:
                    if not isinstance(item, str):
                        continue
                    cleaned = _clean(item)
                    if cleaned != item:
                        touched = True
                    new_values.append(cleaned)
                safe_plan[list_field] = new_values
                if touched:
                    report["applied_fixes"].append(f"Claim-Sanitizing auf Liste '{list_field}' angewendet.")

        channel_plan = safe_plan.get("channel_plan")
        if isinstance(channel_plan, list):
            touched = False
            for item in channel_plan:
                angle = item.get("message_angle")
                if isinstance(angle, str):
                    cleaned = _clean(angle)
                    if cleaned != angle:
                        item["message_angle"] = cleaned
                        touched = True
            if touched:
                report["applied_fixes"].append("Claim-Sanitizing auf channel_plan.message_angle angewendet.")

