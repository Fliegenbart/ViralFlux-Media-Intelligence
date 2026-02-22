"""Campaign Briefing PDF — Druckfertiges Briefing aus einer Marketing-Opportunity.

Generiert ein professionelles 1-2 Seiten PDF mit:
- Kampagnen-Headline + Trigger
- Zielgruppe + Region
- Produktempfehlung + Sales Pitch
- Budget-Empfehlung + Zeitfenster
- Conquesting-Info (wenn aktiv)
"""

import io
import logging
from datetime import datetime

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Brand colors
_INDIGO = (67, 56, 202)
_SLATE_700 = (51, 65, 85)
_SLATE_400 = (148, 163, 184)
_AMBER = (217, 119, 6)
_WHITE = (255, 255, 255)
_BG = (248, 250, 252)


class BriefingPDF(FPDF):
    """Custom FPDF subclass for consistent branding."""

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_SLATE_400)
        self.cell(0, 6, "ViralFlux Media Intelligence", align="L")
        self.cell(0, 6, f"Briefing — {datetime.now().strftime('%d.%m.%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_INDIGO)
        self.set_line_width(0.6)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_SLATE_400)
        self.cell(0, 8, f"Seite {self.page_no()} | Vertraulich — nur fuer internen Gebrauch", align="C")


def generate_briefing_pdf(opp: dict) -> bytes:
    """Generate a campaign briefing PDF from an opportunity dict.

    Returns PDF bytes ready for streaming response.
    """
    pdf = BriefingPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    trigger = opp.get("trigger_context", {})
    pitch = opp.get("sales_pitch", {})
    region = opp.get("region_target", {})
    products = opp.get("suggested_products", [])

    # ── Title Block ──
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*_INDIGO)
    title = trigger.get("event", opp.get("type", "")).replace("_", " ")
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*_SLATE_700)
    pdf.multi_cell(0, 6, trigger.get("details", ""), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Urgency + Status Row ──
    urgency = opp.get("urgency_score", 0)
    status = opp.get("status", "")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_SLATE_700)
    pdf.cell(50, 8, f"Dringlichkeit: {urgency:.0f}/100")
    pdf.cell(50, 8, f"Status: {status}")
    pdf.cell(0, 8, f"Datum: {trigger.get('detected_at', '')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # ── Region + Zielgruppe ──
    _section_header(pdf, "Region & Zielgruppe")

    states = region.get("states", [])
    region_text = ", ".join(states) if states else "Bundesweit"
    plz = region.get("plz_cluster", "ALL")
    if plz != "ALL":
        region_text += f" (PLZ: {plz})"

    audience = opp.get("target_audience", [])

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_SLATE_700)
    pdf.cell(35, 7, "Region:", new_x="RIGHT")
    pdf.cell(0, 7, region_text, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(35, 7, "Zielgruppe:", new_x="RIGHT")
    pdf.cell(0, 7, ", ".join(audience) if audience else "Allgemein", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Produktempfehlung ──
    if products:
        _section_header(pdf, "Empfohlene Produkte")
        for prod in products[:5]:
            pdf.set_font("Helvetica", "B" if prod.get("priority") == "HIGH" else "", 10)
            pdf.set_text_color(*_SLATE_700)
            name = prod.get("name", "")
            sku = prod.get("sku", "")
            prio = prod.get("priority", "")
            pdf.cell(0, 7, f"  {name} ({sku}) — Prioritaet: {prio}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Sales Pitch ──
    _section_header(pdf, "Kommunikationsstrategie")

    headline = pitch.get("headline_email", "")
    script = pitch.get("script_phone", "")
    cta = pitch.get("call_to_action", "")

    if headline:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(0, 7, "E-Mail Betreff:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*_SLATE_700)
        pdf.multi_cell(0, 6, headline, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if script:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_INDIGO)
        pdf.cell(0, 7, "Telefon-Script:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*_SLATE_700)
        pdf.multi_cell(0, 6, f'"{script}"', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if cta:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_AMBER)
        pdf.cell(0, 7, f"Call-to-Action: {cta}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Conquesting ──
    if opp.get("is_conquesting_active"):
        _section_header(pdf, "Conquesting-Strategie")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*_SLATE_700)
        ingredient = opp.get("competitor_shortage_ingredient", "")
        multiplier = opp.get("recommended_bid_modifier", 1.0)
        product = opp.get("conquesting_product", "")

        pdf.cell(0, 7, f"Engpass-Wirkstoff: {ingredient}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"Bid-Multiplikator: {multiplier:.1f}x", new_x="LMARGIN", new_y="NEXT")
        if product:
            pdf.cell(0, 7, f"Conquesting-Produkt: {product}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Quelle ──
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_SLATE_400)
    pdf.cell(0, 6, f"Quelle: {trigger.get('source', '').replace('_', ' ')} | Opportunity-ID: {opp.get('id', '')}",
             new_x="LMARGIN", new_y="NEXT")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _section_header(pdf: FPDF, title: str):
    """Render a styled section header."""
    pdf.set_draw_color(*_INDIGO)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_INDIGO)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
