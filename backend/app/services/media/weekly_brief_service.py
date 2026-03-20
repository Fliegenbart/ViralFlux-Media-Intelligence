"""PEIX x GELO Wochenbericht als automatisierter PDF-Report.

Generiert jeden Montag ein 3-seitiges PDF:
  Seite 1: Lagebild Deutschland (PeixEpiScore, Bento-Tiles, Regionen mit frühem Signal)
  Seite 2: Arbeitsvorschlag (regionale Allokation + Produkt-Priorisierung)
  Seite 3: Begründung (Rückblicktest + Stabilität der Vorhersage)
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from fpdf import FPDF
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Brand Colors (shared with briefing_pdf.py) ──
_INDIGO = (67, 56, 202)
_SLATE_700 = (51, 65, 85)
_SLATE_400 = (148, 163, 184)
_AMBER = (217, 119, 6)
_GREEN = (22, 163, 74)
_RED = (220, 38, 38)
_WHITE = (255, 255, 255)
_BG = (248, 250, 252)

_SOURCE_LABELS = {
    "wastewater": "Abwasser",
    "are konsultation": "ARE-Konsultation",
    "survstat": "SurvStat",
    "notaufnahme": "Notaufnahme",
    "weather": "Wetter",
    "pollen": "Pollen",
    "google trends": "Google Trends",
    "bfarm shortage": "BfArM-Engpässe",
    "marketing": "Kundendaten",
    "backtest": "Rückblicktest",
}

_TILE_LABELS = {
    "SURVSTAT Respiratory": "SurvStat Atemwege",
    "Top Chancenregion": "Früheste Signalregion",
    "Signalscore Deutschland": "Signalwert Deutschland",
    "BfArM Engpass-Signal": "BfArM-Engpasssignal",
    "Google Trends Infekt": "Google Trends Atemwege",
    "ARE Konsultationsinzidenz": "ARE-Konsultationsinzidenz",
}


def _safe(text: Any) -> str:
    """Sanitize text for Latin-1 encoding (core PDF fonts).

    Latin-1 natively supports ä ö ü Ä Ö Ü ß — only replace characters
    outside the Latin-1 range (smart quotes, em-dashes, arrows, etc.).
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    replacements = {
        "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2022": "*",
        "\u00a0": " ", "\u2197": "^", "\u2198": "v", "\u2192": "->",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class _ActionBriefPDF(FPDF):
    """Custom FPDF for the PEIX x GELO weekly brief."""

    def __init__(self, calendar_week: str):
        super().__init__()
        self._calendar_week = calendar_week

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_SLATE_400)
        self.cell(0, 6, "PEIX x GELO Frühwarnung", align="L")
        self.cell(
            0, 6,
            f"Wochenbericht - {self._calendar_week} - {datetime.now().strftime('%d.%m.%Y')}",
            align="R", new_x="LMARGIN", new_y="NEXT",
        )
        self.set_draw_color(*_INDIGO)
        self.set_line_width(0.6)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_SLATE_400)
        self.cell(
            0, 8,
            f"Seite {self.page_no()} | PEIX x GELO Wochenbericht | Vertraulich",
            align="C",
        )


def _section(pdf: FPDF, title: str) -> None:
    """Render a styled section header."""
    pdf.set_draw_color(*_INDIGO)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_INDIGO)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def _kv(pdf: FPDF, label: str, value: str, bold_value: bool = False) -> None:
    """Key-value row."""
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_SLATE_400)
    pdf.cell(55, 7, _safe(label), new_x="RIGHT")
    pdf.set_font("Helvetica", "B" if bold_value else "", 10)
    pdf.set_text_color(*_SLATE_700)
    pdf.cell(0, 7, _safe(value), new_x="LMARGIN", new_y="NEXT")


def _source_display_label(source: str | None) -> str:
    raw = str(source or "").strip()
    if not raw:
        return "-"
    normalized = raw.lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    if normalized in _SOURCE_LABELS:
        return _SOURCE_LABELS[normalized]
    return raw.replace("_", " ").title()


def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    for card in cards:
        product = str(card.get("recommended_product", card.get("product", "")) or "").strip().lower()
        reason = str(card.get("reason", card.get("recommendation_reason", "")) or "").strip().lower()
        regions = tuple(sorted(str(region).strip().upper() for region in card.get("region_codes", []) if region))
        signature = (product, reason, regions)
        if signature in seen:
            continue
        seen.add(signature)
        unique_cards.append(card)

    return unique_cards


def _tile_display_title(title: str | None) -> str:
    raw = str(title or "").strip()
    if not raw:
        return "-"
    if raw in _TILE_LABELS:
        return _TILE_LABELS[raw]
    return raw.replace("Signalscore", "Signalwert")


def _normalize_tile_line(text: str) -> str:
    normalized = str(text or "")
    for source, replacement in _TILE_LABELS.items():
        normalized = normalized.replace(source, replacement)
    return normalized.replace("Signalscore", "Signalwert")


def _action_card_title(card: dict[str, Any]) -> str:
    title = str(
        card.get("display_title")
        or card.get("recommended_product")
        or card.get("product")
        or "Kampagnenvorschlag"
    ).strip()
    reason = str(card.get("reason") or card.get("recommendation_reason") or "").strip()
    if reason and reason.lower() not in title.lower():
        return f"{title}: {reason}"
    return title


class WeeklyBriefService:
    """Assembles cockpit data into a weekly PDF action brief."""

    def __init__(self, db: Session):
        self.db = db

    def generate(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        """Generate the weekly brief PDF. Returns dict with pdf_bytes + metadata."""
        from app.services.media.cockpit_service import MediaCockpitService

        now = datetime.utcnow()
        iso_cal = now.isocalendar()
        calendar_week = f"{iso_cal.year}-W{iso_cal.week:02d}"

        logger.info("Generating weekly brief for %s", calendar_week)

        cockpit_svc = MediaCockpitService(self.db)
        cockpit = cockpit_svc.get_cockpit_payload(virus_typ=virus_typ)

        # Extract key data
        peix = cockpit.get("peix_epi_score") or {}
        bento = cockpit.get("bento", {})
        tiles = bento.get("tiles") or []
        map_data = cockpit.get("map") or {}
        regions = map_data.get("regions") or {}
        recs = cockpit.get("recommendations") or {}
        cards = recs.get("cards") or []
        freshness = cockpit.get("data_freshness") or {}

        # Sort regions by impact
        region_list = sorted(
            [
                {"code": code, **data}
                for code, data in regions.items()
                if isinstance(data, dict)
            ],
            key=lambda r: float(r.get("impact_probability", 0) or 0),
            reverse=True,
        )

        # Sort cards by urgency
        top_cards = _dedupe_cards(sorted(
            cards, key=lambda c: float(c.get("urgency_score", 0) or 0), reverse=True,
        ))[:5]

        # Build PDF
        pdf = _ActionBriefPDF(calendar_week)
        pdf.set_auto_page_break(auto=True, margin=20)

        # ═══════════════════════════════════════════════════════════════
        # SEITE 1: LAGEBILD DEUTSCHLAND
        # ═══════════════════════════════════════════════════════════════
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(0, 12, _safe(f"PEIX x GELO Wochenbericht  -  KW {iso_cal.week}/{iso_cal.year}"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*_SLATE_700)
        pdf.multi_cell(0, 6, _safe(
            f"Automatisierte Lageeinschätzung für PEIX und GELO. "
            f"Sie zeigt, wo in den nächsten 3 bis 7 Tagen die frühesten regionalen Signale einer Atemwegswelle entstehen könnten. "
            f"Generiert: {now.strftime('%d.%m.%Y %H:%M')} UTC."
        ), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        if region_list:
            top_region = region_list[0]
            top_region_name = top_region.get("name", top_region.get("code", "der Fokusregion"))
            top_region_score = float(top_region.get("peix_score", top_region.get("score_0_100", 0)) or 0)
            top_region_impact = float(top_region.get("impact_probability", 0) or 0)
            pdf.set_fill_color(238, 242, 255)
            pdf.set_draw_color(*_INDIGO)
            pdf.set_line_width(0.2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_INDIGO)
            pdf.multi_cell(
                0,
                7,
                _safe(
                    "Aktuelle Hauptaussage: "
                    f"Das früheste relevante Signal sehen wir derzeit in {top_region_name}. "
                    f"Die Region führt die Priorisierung mit {top_region_score:.0f}/100 und einem Frühsignal von {top_region_impact:.0f}% an."
                ),
                border=1,
                fill=True,
                new_x="LMARGIN",
                new_y="NEXT",
            )
            pdf.ln(4)

        # Signalscore national
        _section(pdf, "Signalbild Deutschland")
        national_score = peix.get("national_score", 0)
        national_band = peix.get("national_band", "-")
        national_impact = peix.get("national_impact_probability", 0)
        _kv(pdf, "Nationaler Index:", f"{national_score:.0f} / 100", bold_value=True)
        _kv(pdf, "Risiko-Band:", str(national_band).upper(), bold_value=True)
        _kv(pdf, "Signalwert:", f"{national_impact:.1f}%", bold_value=True)
        _kv(pdf, "Einordnung:", "Priorisierung für frühe regionale Signale", bold_value=True)
        _kv(pdf, "Dominanter Virus:", virus_typ)
        pdf.ln(2)

        # Bento-Tiles Zusammenfassung
        _section(pdf, "Signal-Übersicht")
        for tile in tiles[:8]:
            title = _tile_display_title(tile.get("title", ""))
            value = tile.get("value", "")
            unit = tile.get("unit", "")
            impact = tile.get("impact_probability")
            is_live = tile.get("is_live", False)

            pdf.set_font("Helvetica", "B" if is_live else "", 9)
            pdf.set_text_color(*_SLATE_700)
            display_val = f"{value}{unit}" if unit else str(value)
            impact_str = f"Signalwert: {impact:.0f}%" if impact is not None else ""
            live_marker = "[LIVE]" if is_live else "[STALE]"
            signal_line = _normalize_tile_line(f"  {live_marker} {title}: {display_val}   {impact_str}")
            pdf.cell(0, 6,
                     _safe(signal_line),
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Top-Regionen
        _section(pdf, "Regionen mit dem frühesten Signal")
        if region_list:
            # Table header
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_WHITE)
            pdf.set_fill_color(*_INDIGO)
            pdf.cell(40, 7, "  Region", fill=True)
            pdf.cell(25, 7, "Score", align="C", fill=True)
            pdf.cell(25, 7, "Frühsignal", align="C", fill=True)
            pdf.cell(25, 7, "Trend", align="C", fill=True)
            pdf.cell(0, 7, "Änderung", align="C", fill=True,
                     new_x="LMARGIN", new_y="NEXT")

            for i, reg in enumerate(region_list[:8]):
                pdf.set_font("Helvetica", "B" if i < 3 else "", 9)
                pdf.set_text_color(*_SLATE_700)
                bg = _BG if i % 2 == 0 else _WHITE
                pdf.set_fill_color(*bg)

                name = reg.get("name", reg.get("code", "?"))
                score = reg.get("peix_score", reg.get("score_0_100", 0))
                impact = reg.get("impact_probability", 0)
                trend = reg.get("trend", "-")
                change = reg.get("change_pct", 0)

                trend_arrow = "^" if trend == "steigend" else ("v" if trend == "fallend" else "->")
                change_str = f"{change:+.1f}%" if change else "-"

                pdf.cell(40, 6, _safe(f"  {name}"), fill=True)
                pdf.cell(25, 6, f"{float(score or 0):.0f}", align="C", fill=True)
                pdf.cell(25, 6, f"{float(impact or 0):.0f}%", align="C", fill=True)
                pdf.cell(25, 6, _safe(trend_arrow), align="C", fill=True)
                pdf.cell(0, 6, _safe(change_str), align="C", fill=True,
                         new_x="LMARGIN", new_y="NEXT")

        # ═══════════════════════════════════════════════════════════════
        # SEITE 2: ARBEITSVORSCHLAG
        # ═══════════════════════════════════════════════════════════════
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(0, 10, "Arbeitsvorschlag für Regionen und Produkte",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Regionale Allokation
        _section(pdf, "Regionale Budget-Prüfung")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_SLATE_700)
        pdf.multi_cell(0, 5, _safe(
            "Hinweis für Budget- und Produktprüfung basierend auf Signalwert und Vorhersage im 3-, 5- oder 7-Tage-Fenster. "
            "Die Tabelle ist eine Priorisierung, keine automatische Freigabe."
        ), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        # Budget shift table
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_WHITE)
        pdf.set_fill_color(*_INDIGO)
        pdf.cell(45, 7, "  Region", fill=True)
        pdf.cell(25, 7, "Score", align="C", fill=True)
        pdf.cell(25, 7, "Frühsignal", align="C", fill=True)
        pdf.cell(30, 7, "Empfehlung", align="C", fill=True)
        pdf.cell(0, 7, "Begründung", fill=True, new_x="LMARGIN", new_y="NEXT")

        for i, reg in enumerate(region_list[:8]):
            score = float(reg.get("peix_score", reg.get("score_0_100", 0)) or 0)
            impact = float(reg.get("impact_probability", 0) or 0)
            name = reg.get("name", reg.get("code", "?"))

            if impact >= 80:
                shift = "+30-40%"
                reason = "sehr frühes Signal - zuerst prüfen"
                color = _RED
            elif impact >= 60:
                shift = "+15-25%"
                reason = "frühes Signal - Budgeterhöhung prüfen"
                color = _AMBER
            elif impact >= 40:
                shift = "Halten"
                reason = "beobachten - noch nicht freigeben"
                color = _SLATE_700
            else:
                shift = "-10-20%"
                reason = "späteres Signal - eher umschichten"
                color = _GREEN

            bg = _BG if i % 2 == 0 else _WHITE
            pdf.set_fill_color(*bg)
            pdf.set_font("Helvetica", "B" if i < 3 else "", 9)
            pdf.set_text_color(*_SLATE_700)
            pdf.cell(45, 6, _safe(f"  {name}"), fill=True)
            pdf.cell(25, 6, f"{score:.0f}", align="C", fill=True)
            pdf.cell(25, 6, f"{impact:.0f}%", align="C", fill=True)
            pdf.set_text_color(*color)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(30, 6, _safe(shift), align="C", fill=True)
            pdf.set_text_color(*_SLATE_700)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(0, 6, _safe(reason), fill=True, new_x="LMARGIN", new_y="NEXT")

        pdf.ln(6)

        # Top Action Cards
        _section(pdf, "Produkt-Priorisierung zur Prüfung")
        if top_cards:
            for i, card in enumerate(top_cards[:5], start=1):
                product = _action_card_title(card)
                urgency = float(card.get("urgency_score", 0) or 0)
                reason = card.get("reason", card.get("recommendation_reason", ""))
                card_regions = card.get("region_codes", [])
                budget_shift = card.get("budget_shift_pct", 0)

                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*_INDIGO)
                pdf.cell(0, 7, _safe(f"{i}. {product} (Dringlichkeit: {urgency:.0f})"),
                         new_x="LMARGIN", new_y="NEXT")

                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*_SLATE_700)
                if card_regions:
                    pdf.cell(0, 5,
                             _safe(f"   Regionen: {', '.join(card_regions[:5])}  |  "
                                   f"Budgetänderung: +{float(budget_shift or 0):.1f}%"),
                             new_x="LMARGIN", new_y="NEXT")
                if reason:
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.set_text_color(*_SLATE_400)
                    pdf.multi_cell(0, 4, _safe(f"   {reason[:200]}"),
                                   new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
        else:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(*_SLATE_400)
            pdf.cell(0, 7, "Keine aktiven Empfehlungen in dieser Woche.",
                     new_x="LMARGIN", new_y="NEXT")

        # ═══════════════════════════════════════════════════════════════
        # SEITE 3: BEGRÜNDUNG
        # ═══════════════════════════════════════════════════════════════
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(0, 10, "Warum wir die Vorhersage vertreten", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Business Pitch Report
        _section(pdf, "Rückblicktest auf frühere Wellen")

        pitch_results = self._run_backtest_pitches()
        if pitch_results:
            for pr in pitch_results:
                season = pr.get("season", "")
                ttd = pr.get("ttd_advantage_days", 0)
                peak_date = pr.get("rki_peak_date", "-")
                peak_cases = pr.get("rki_peak_cases", 0)
                first_alert = pr.get("ml_first_alert_date", "-")

                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*_SLATE_700)
                pdf.cell(0, 7, _safe(f"Saison {season}:"),
                         new_x="LMARGIN", new_y="NEXT")

                pdf.set_font("Helvetica", "", 9)
                _kv(pdf, "RKI-Peak:", f"{peak_date} ({peak_cases:,} Fälle)".replace(",", "."))
                _kv(pdf, "Erstes Frühsignal:", str(first_alert))
                _kv(pdf, "Abstand bis zum späteren Peak:", f"{ttd} Tage", bold_value=True)
                pdf.ln(2)

            # Summary
            avg_ttd = sum(p.get("ttd_advantage_days", 0) for p in pitch_results) / max(len(pitch_results), 1)
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*_INDIGO)
            pdf.cell(0, 8, _safe(
                f"Im Rückblick lag das erste Signal im Schnitt {avg_ttd:.0f} Tage vor dem späteren RKI-Peak."
            ), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*_SLATE_700)
            pdf.multi_cell(
                0,
                5,
                _safe(
                    "Für die operative Steuerung nutzen wir trotzdem nur das kurze 3-, 5- oder 7-Tage-Fenster. "
                    "Der große historische Abstand zeigt vor allem, dass frühe Signale oft lange vor dem späteren Peak sichtbar werden."
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )
        else:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(*_SLATE_400)
            pdf.cell(0, 7, "Daten aus dem Rückblicktest sind nicht verfügbar.",
                     new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)

        # Data Freshness
        _section(pdf, "Stand der Datenquellen")
        for source, ts_str in freshness.items():
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                age_days = (now - ts.replace(tzinfo=None)).total_seconds() / 86400
                status = "AKTUELL" if age_days < 7 else "ALT"
            except (ValueError, TypeError):
                age_days = -1
                status = "?"

            pdf.set_font("Helvetica", "B", 8)
            color = _GREEN if status == "AKTUELL" else _RED if status == "ALT" else _AMBER
            pdf.set_text_color(*color)
            pdf.cell(20, 5, _safe(f"[{status}]"))
            pdf.set_text_color(*_SLATE_700)
            pdf.cell(56, 5, _safe(_source_display_label(source)))
            pdf.set_text_color(*_SLATE_400)
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(
                0,
                5,
                _safe(f"{age_days:.1f} Tage alt" if age_days >= 0 else "Zeit nicht bekannt"),
                new_x="LMARGIN",
                new_y="NEXT",
            )

        pdf.ln(6)

        # Disclaimer
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*_SLATE_400)
        pdf.multi_cell(0, 4, _safe(
            "Hinweis: Dieser Bericht zeigt wahrscheinliche frühe Starts einer Welle auf Basis historischer Analysen und aktueller Signale. "
            "Die genannten Vorlaufzeiten sind historische Werte und keine Garantie für die nächste Woche. "
            "Alle Empfehlungen dienen als Entscheidungshilfe; die finale Mediaplanung bleibt eine fachliche Freigabe."
        ), new_x="LMARGIN", new_y="NEXT")

        # ── Output ──
        buf = io.BytesIO()
        pdf.output(buf)
        pdf_bytes = buf.getvalue()

        summary = {
            "calendar_week": calendar_week,
            "generated_at": now.isoformat(),
            "national_score": national_score,
            "national_band": national_band,
            "national_impact": national_impact,
            "top_region": region_list[0]["code"] if region_list else None,
            "action_cards_count": len(top_cards),
            "pages": pdf.page_no(),
        }

        # Persist to DB
        self._save_to_db(calendar_week, pdf_bytes, summary, virus_typ)

        logger.info(
            "Weekly brief generated: %s, %d pages, %d bytes",
            calendar_week, pdf.page_no(), len(pdf_bytes),
        )

        return {
            "calendar_week": calendar_week,
            "pages": pdf.page_no(),
            "pdf_bytes": pdf_bytes,
            "summary": summary,
        }

    def _run_backtest_pitches(self) -> list[dict[str, Any]]:
        """Run business pitch for the last 2 seasons."""
        from app.services.ml.backtester import BacktestService

        results = []
        svc = BacktestService(self.db)
        seasons = [
            ("2023-10-01", "2024-03-31"),
            ("2024-10-01", "2025-03-31"),
        ]
        for start, end in seasons:
            try:
                r = svc.generate_business_pitch_report(
                    disease="GELO_ATEMWEG",
                    virus_typ="Influenza A",
                    season_start=start,
                    season_end=end,
                )
                if r.get("status") == "success":
                    results.append(r)
            except Exception as e:
                logger.warning("Backtest pitch failed for %s-%s: %s", start, end, e)
        return results

    def _save_to_db(
        self,
        calendar_week: str,
        pdf_bytes: bytes,
        summary: dict[str, Any],
        virus_typ: str,
    ) -> None:
        """Persist the brief to the weekly_briefs table."""
        from app.models.database import WeeklyBrief

        existing = (
            self.db.query(WeeklyBrief)
            .filter_by(calendar_week=calendar_week, brand="gelo")
            .first()
        )
        if existing:
            existing.pdf_bytes = pdf_bytes
            existing.summary_json = summary
            existing.generated_at = datetime.utcnow()
            existing.virus_typ = virus_typ
        else:
            brief = WeeklyBrief(
                calendar_week=calendar_week,
                generated_at=datetime.utcnow(),
                pdf_bytes=pdf_bytes,
                summary_json=summary,
                virus_typ=virus_typ,
                brand="gelo",
            )
            self.db.add(brief)

        self.db.commit()
