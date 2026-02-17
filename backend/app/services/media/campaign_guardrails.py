"""Guardrails fuer AI-generierte Campaign-Plans."""

from __future__ import annotations

import re
from typing import Any

from app.services.media.playbook_engine import PLAYBOOK_CATALOG


_BANNED_PHRASES = [
    r"\bheilt\b",
    r"\bheilung\b",
    r"\bgarantiert\b",
    r"\b100%\b",
    r"\bsicher wirksam\b",
    r"\bsofort(?:ige)? heilung\b",
]


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
            items = [{"channel": "programmatic", "share_pct": 100.0, "message_angle": "Kontextbasiertes Timing", "kpi_primary": "CTR", "kpi_secondary": ["CPM"]}]
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
