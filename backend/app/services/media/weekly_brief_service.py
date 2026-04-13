"""ViralFlux Wochenbericht als automatisierter PDF-Report.

Generiert jeden Montag ein 3-seitiges PDF:
  Seite 1: Lagebild Deutschland (Ranking-Signal, Bento-Tiles, Regionen mit frühem Signal)
  Seite 2: Arbeitsvorschlag (regionale Allokation + Produkt-Priorisierung)
  Seite 3: Begründung (Rückblicktest + Stabilität der Vorhersage)
"""

from __future__ import annotations
from app.core.time import utc_now

import io
import logging
from datetime import datetime
from typing import Any

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.services.media import weekly_brief_formatting
from app.services.media import weekly_brief_pages

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


def _normalize_brand(value: Any) -> str:
    brand = str(value).strip().lower()
    if brand:
        return brand
    raise ValueError("brand must be provided")

def _safe(text: Any) -> str:
    return weekly_brief_formatting.safe(text)


class _ActionBriefPDF(FPDF):
    """Custom FPDF for the ViralFlux weekly brief."""

    def __init__(self, calendar_week: str):
        super().__init__()
        self._calendar_week = calendar_week

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_SLATE_400)
        self.cell(0, 6, "ViralFlux Frühwarnung", align="L")
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
            f"Seite {self.page_no()} | ViralFlux Wochenbericht | Vertraulich",
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
    return weekly_brief_formatting.source_display_label(source)


def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return weekly_brief_formatting.dedupe_cards(cards)


def _tile_display_title(title: str | None) -> str:
    return weekly_brief_formatting.tile_display_title(title)


def _normalize_tile_line(text: str) -> str:
    return weekly_brief_formatting.normalize_tile_line(text)


def _normalize_signal_score(value: Any) -> float:
    return weekly_brief_formatting.normalize_signal_score(value)


def _primary_signal_score(item: dict[str, Any] | None) -> float:
    return weekly_brief_formatting.primary_signal_score(item)


def _format_signal_score(value: Any, digits: int = 0) -> str:
    return weekly_brief_formatting.format_signal_score(value, digits=digits)


def _action_card_title(card: dict[str, Any]) -> str:
    return weekly_brief_formatting.action_card_title(card)


class WeeklyBriefService:
    """Assembles cockpit data into a weekly PDF action brief."""

    def __init__(self, db: Session):
        self.db = db
        self._INDIGO = _INDIGO
        self._SLATE_700 = _SLATE_700
        self._SLATE_400 = _SLATE_400
        self._AMBER = _AMBER
        self._GREEN = _GREEN
        self._RED = _RED
        self._WHITE = _WHITE
        self._BG = _BG
        self._safe = _safe
        self._section = _section
        self._kv = _kv
        self._source_display_label = _source_display_label
        self._dedupe_cards = _dedupe_cards
        self._tile_display_title = _tile_display_title
        self._normalize_tile_line = _normalize_tile_line
        self._normalize_signal_score = _normalize_signal_score
        self._primary_signal_score = _primary_signal_score
        self._format_signal_score = _format_signal_score
        self._action_card_title = _action_card_title

    def generate(self, *, brand: str, virus_typ: str = "Influenza A") -> dict[str, Any]:
        """Generate the weekly brief PDF. Returns dict with pdf_bytes + metadata."""
        from app.services.media.cockpit_service import MediaCockpitService

        brand_value = _normalize_brand(brand)
        now = utc_now()
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
        national_score = peix.get("national_score", 0)
        national_band = peix.get("national_band", "-")
        national_impact = round(
            _normalize_signal_score(
                peix.get("national_score", peix.get("ranking_signal_score", peix.get("national_impact_probability", 0)))
            ),
            1,
        )

        # Sort regions by impact
        region_list = sorted(
            [
                {"code": code, **data}
                for code, data in regions.items()
                if isinstance(data, dict)
            ],
            key=_primary_signal_score,
            reverse=True,
        )

        # Sort cards by urgency
        top_cards = _dedupe_cards(sorted(
            cards, key=lambda c: float(c.get("urgency_score", 0) or 0), reverse=True,
        ))[:5]

        # Build PDF
        pdf = _ActionBriefPDF(calendar_week)
        pdf.set_auto_page_break(auto=True, margin=20)
        self._render_signal_page(
            pdf,
            calendar_week=calendar_week,
            now=now,
            iso_week=iso_cal.week,
            iso_year=iso_cal.year,
            virus_typ=virus_typ,
            peix=peix,
            tiles=tiles,
            region_list=region_list,
        )
        self._render_action_page(
            pdf,
            region_list=region_list,
            top_cards=top_cards,
        )
        pitch_results = self._run_backtest_pitches()
        self._render_evidence_page(
            pdf,
            freshness=freshness,
            now=now,
            pitch_results=pitch_results,
        )

        # ── Output ──
        buf = io.BytesIO()
        pdf.output(buf)
        pdf_bytes = buf.getvalue()

        summary = {
            "calendar_week": calendar_week,
            "brand": brand_value,
            "generated_at": now.isoformat(),
            "national_score": national_score,
            "national_band": national_band,
            "national_impact": national_impact,
            "top_region": region_list[0]["code"] if region_list else None,
            "action_cards_count": len(top_cards),
            "pages": pdf.page_no(),
        }

        # Persist to DB
        self._save_to_db(calendar_week, pdf_bytes, summary, virus_typ, brand_value)

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

    def _render_signal_page(
        self,
        pdf: FPDF,
        *,
        calendar_week: str,
        now: datetime,
        iso_week: int,
        iso_year: int,
        virus_typ: str,
        peix: dict[str, Any],
        tiles: list[dict[str, Any]],
        region_list: list[dict[str, Any]],
    ) -> None:
        weekly_brief_pages.render_signal_page(
            self,
            pdf,
            calendar_week=calendar_week,
            now=now,
            iso_week=iso_week,
            iso_year=iso_year,
            virus_typ=virus_typ,
            peix=peix,
            tiles=tiles,
            region_list=region_list,
        )

    def _render_action_page(
        self,
        pdf: FPDF,
        *,
        region_list: list[dict[str, Any]],
        top_cards: list[dict[str, Any]],
    ) -> None:
        weekly_brief_pages.render_action_page(
            self,
            pdf,
            region_list=region_list,
            top_cards=top_cards,
        )

    def _render_evidence_page(
        self,
        pdf: FPDF,
        *,
        freshness: dict[str, Any],
        now: datetime,
        pitch_results: list[dict[str, Any]],
    ) -> None:
        weekly_brief_pages.render_evidence_page(
            self,
            pdf,
            freshness=freshness,
            now=now,
            pitch_results=pitch_results,
        )

    def _save_to_db(
        self,
        calendar_week: str,
        pdf_bytes: bytes,
        summary: dict[str, Any],
        virus_typ: str,
        brand: str,
    ) -> None:
        """Persist the brief to the weekly_briefs table."""
        from app.models.database import WeeklyBrief

        brand_value = _normalize_brand(brand)
        existing = (
            self.db.query(WeeklyBrief)
            .filter_by(calendar_week=calendar_week, brand=brand_value)
            .first()
        )
        if existing:
            existing.pdf_bytes = pdf_bytes
            existing.summary_json = summary
            existing.generated_at = utc_now()
            existing.virus_typ = virus_typ
        else:
            brief = WeeklyBrief(
                calendar_week=calendar_week,
                generated_at=utc_now(),
                pdf_bytes=pdf_bytes,
                summary_json=summary,
                virus_typ=virus_typ,
                brand=brand_value,
            )
            self.db.add(brief)

        self.db.commit()
