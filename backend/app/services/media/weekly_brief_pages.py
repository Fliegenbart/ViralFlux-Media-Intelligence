from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fpdf import FPDF


def render_signal_page(
    service,
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
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*service._INDIGO)
    pdf.cell(
        0,
        12,
        service._safe(f"PEIX x GELO Wochenbericht  -  KW {iso_week}/{iso_year}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*service._SLATE_700)
    pdf.multi_cell(
        0,
        6,
        service._safe(
            f"Automatisierte Lageeinschätzung für PEIX und GELO. "
            f"Sie zeigt, wo in den nächsten 3 bis 7 Tagen die frühesten regionalen Signale einer Atemwegswelle entstehen könnten. "
            f"Generiert: {now.strftime('%d.%m.%Y %H:%M')} UTC."
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    if region_list:
        top_region = region_list[0]
        top_region_name = top_region.get("name", top_region.get("code", "der Fokusregion"))
        top_region_score = service._primary_signal_score(top_region)
        pdf.set_fill_color(238, 242, 255)
        pdf.set_draw_color(*service._INDIGO)
        pdf.set_line_width(0.2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*service._INDIGO)
        pdf.multi_cell(
            0,
            7,
            service._safe(
                "Aktuelle Hauptaussage: "
                f"Das früheste relevante Signal sehen wir derzeit in {top_region_name}. "
                f"Die Region führt die Priorisierung mit einem Signalwert von {service._format_signal_score(top_region_score)} an."
            ),
            border=1,
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(4)

    service._section(pdf, "Signalbild Deutschland")
    national_score = peix.get("national_score", 0)
    national_band = peix.get("national_band", "-")
    service._kv(pdf, "Nationaler Index:", f"{national_score:.0f} / 100", bold_value=True)
    service._kv(pdf, "Risiko-Band:", str(national_band).upper(), bold_value=True)
    service._kv(
        pdf,
        "Signalwert:",
        service._format_signal_score(national_score, digits=1),
        bold_value=True,
    )
    service._kv(pdf, "Einordnung:", "Priorisierung für frühe regionale Signale", bold_value=True)
    service._kv(pdf, "Dominanter Virus:", virus_typ)
    pdf.ln(2)

    service._section(pdf, "Signal-Übersicht")
    for tile in tiles[:8]:
        title = service._tile_display_title(tile.get("title", ""))
        value = tile.get("value", "")
        unit = tile.get("unit", "")
        signal_score = service._primary_signal_score(tile)
        is_live = tile.get("is_live", False)

        pdf.set_font("Helvetica", "B" if is_live else "", 9)
        pdf.set_text_color(*service._SLATE_700)
        display_val = f"{value}{unit}" if unit else str(value)
        impact_str = (
            f"Signalwert: {service._format_signal_score(signal_score)}" if signal_score > 0 else ""
        )
        live_marker = "[LIVE]" if is_live else "[STALE]"
        signal_line = service._normalize_tile_line(
            f"  {live_marker} {title}: {display_val}   {impact_str}"
        )
        pdf.cell(0, 6, service._safe(signal_line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    service._section(pdf, "Regionen mit dem frühesten Signal")
    if not region_list:
        return

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*service._WHITE)
    pdf.set_fill_color(*service._INDIGO)
    pdf.cell(40, 7, "  Region", fill=True)
    pdf.cell(25, 7, "Score", align="C", fill=True)
    pdf.cell(25, 7, "Signalwert", align="C", fill=True)
    pdf.cell(25, 7, "Trend", align="C", fill=True)
    pdf.cell(0, 7, "Änderung", align="C", fill=True, new_x="LMARGIN", new_y="NEXT")

    for i, reg in enumerate(region_list[:8]):
        pdf.set_font("Helvetica", "B" if i < 3 else "", 9)
        pdf.set_text_color(*service._SLATE_700)
        bg = service._BG if i % 2 == 0 else service._WHITE
        pdf.set_fill_color(*bg)

        name = reg.get("name", reg.get("code", "?"))
        score = reg.get("peix_score", reg.get("score_0_100", 0))
        signal_score = service._primary_signal_score(reg)
        trend = reg.get("trend", "-")
        change = reg.get("change_pct", 0)

        trend_arrow = "^" if trend == "steigend" else ("v" if trend == "fallend" else "->")
        change_str = f"{change:+.1f}%" if change else "-"

        pdf.cell(40, 6, service._safe(f"  {name}"), fill=True)
        pdf.cell(25, 6, f"{float(score or 0):.0f}", align="C", fill=True)
        pdf.cell(
            25,
            6,
            service._safe(service._format_signal_score(signal_score)),
            align="C",
            fill=True,
        )
        pdf.cell(25, 6, service._safe(trend_arrow), align="C", fill=True)
        pdf.cell(0, 6, service._safe(change_str), align="C", fill=True, new_x="LMARGIN", new_y="NEXT")


def render_action_page(
    service,
    pdf: FPDF,
    *,
    region_list: list[dict[str, Any]],
    top_cards: list[dict[str, Any]],
) -> None:
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*service._INDIGO)
    pdf.cell(0, 10, "Arbeitsvorschlag für Regionen und Produkte", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    service._section(pdf, "Regionale Budget-Prüfung")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*service._SLATE_700)
    pdf.multi_cell(
        0,
        5,
        service._safe(
            "Hinweis für Budget- und Produktprüfung basierend auf Signalwert und Vorhersage im 3-, 5- oder 7-Tage-Fenster. "
            "Die Tabelle ist eine Priorisierung, keine automatische Freigabe."
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*service._WHITE)
    pdf.set_fill_color(*service._INDIGO)
    pdf.cell(45, 7, "  Region", fill=True)
    pdf.cell(25, 7, "Score", align="C", fill=True)
    pdf.cell(25, 7, "Signalwert", align="C", fill=True)
    pdf.cell(30, 7, "Empfehlung", align="C", fill=True)
    pdf.cell(0, 7, "Begründung", fill=True, new_x="LMARGIN", new_y="NEXT")

    for i, reg in enumerate(region_list[:8]):
        score = float(reg.get("peix_score", reg.get("score_0_100", 0)) or 0)
        signal_score = service._primary_signal_score(reg)
        name = reg.get("name", reg.get("code", "?"))

        if signal_score >= 80:
            shift = "+30-40%"
            reason = "sehr frühes Signal - zuerst prüfen"
            color = service._RED
        elif signal_score >= 60:
            shift = "+15-25%"
            reason = "frühes Signal - Budgeterhöhung prüfen"
            color = service._AMBER
        elif signal_score >= 40:
            shift = "Halten"
            reason = "beobachten - noch nicht freigeben"
            color = service._SLATE_700
        else:
            shift = "-10-20%"
            reason = "späteres Signal - eher umschichten"
            color = service._GREEN

        bg = service._BG if i % 2 == 0 else service._WHITE
        pdf.set_fill_color(*bg)
        pdf.set_font("Helvetica", "B" if i < 3 else "", 9)
        pdf.set_text_color(*service._SLATE_700)
        pdf.cell(45, 6, service._safe(f"  {name}"), fill=True)
        pdf.cell(25, 6, f"{score:.0f}", align="C", fill=True)
        pdf.cell(25, 6, service._safe(service._format_signal_score(signal_score)), align="C", fill=True)
        pdf.set_text_color(*color)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(30, 6, service._safe(shift), align="C", fill=True)
        pdf.set_text_color(*service._SLATE_700)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 6, service._safe(reason), fill=True, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    service._section(pdf, "Produkt-Priorisierung zur Prüfung")
    if not top_cards:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*service._SLATE_400)
        pdf.cell(0, 7, "Keine aktiven Empfehlungen in dieser Woche.", new_x="LMARGIN", new_y="NEXT")
        return

    for i, card in enumerate(top_cards[:5], start=1):
        product = service._action_card_title(card)
        urgency = float(card.get("urgency_score", 0) or 0)
        reason = card.get("reason", card.get("recommendation_reason", ""))
        card_regions = card.get("region_codes", [])
        budget_shift = card.get("budget_shift_pct", 0)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*service._INDIGO)
        pdf.cell(
            0,
            7,
            service._safe(f"{i}. {product} (Dringlichkeit: {urgency:.0f})"),
            new_x="LMARGIN",
            new_y="NEXT",
        )

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*service._SLATE_700)
        if card_regions:
            pdf.cell(
                0,
                5,
                service._safe(
                    f"   Regionen: {', '.join(card_regions[:5])}  |  Budgetänderung: +{float(budget_shift or 0):.1f}%"
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )
        if reason:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*service._SLATE_400)
            pdf.multi_cell(0, 4, service._safe(f"   {reason[:200]}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)


def render_evidence_page(
    service,
    pdf: FPDF,
    *,
    freshness: dict[str, Any],
    now: datetime,
    pitch_results: list[dict[str, Any]],
) -> None:
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*service._INDIGO)
    pdf.cell(0, 10, "Warum wir die Vorhersage vertreten", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    service._section(pdf, "Rückblicktest auf frühere Wellen")
    if pitch_results:
        for pitch_result in pitch_results:
            season = pitch_result.get("season", "")
            ttd = pitch_result.get("ttd_advantage_days", 0)
            peak_date = pitch_result.get("rki_peak_date", "-")
            peak_cases = pitch_result.get("rki_peak_cases", 0)
            first_alert = pitch_result.get("ml_first_alert_date", "-")

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*service._SLATE_700)
            pdf.cell(0, 7, service._safe(f"Saison {season}:"), new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Helvetica", "", 9)
            service._kv(pdf, "RKI-Peak:", f"{peak_date} ({peak_cases:,} Fälle)".replace(",", "."))
            service._kv(pdf, "Erstes Frühsignal:", str(first_alert))
            service._kv(pdf, "Abstand bis zum späteren Peak:", f"{ttd} Tage", bold_value=True)
            pdf.ln(2)

        avg_ttd = sum(item.get("ttd_advantage_days", 0) for item in pitch_results) / max(len(pitch_results), 1)
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*service._INDIGO)
        pdf.cell(
            0,
            8,
            service._safe(
                f"Im Rückblick lag das erste Signal im Schnitt {avg_ttd:.0f} Tage vor dem späteren RKI-Peak."
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*service._SLATE_700)
        pdf.multi_cell(
            0,
            5,
            service._safe(
                "Für die operative Steuerung nutzen wir trotzdem nur das kurze 3-, 5- oder 7-Tage-Fenster. "
                "Der große historische Abstand zeigt vor allem, dass frühe Signale oft lange vor dem späteren Peak sichtbar werden."
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*service._SLATE_400)
        pdf.cell(0, 7, "Daten aus dem Rückblicktest sind nicht verfügbar.", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    service._section(pdf, "Stand der Datenquellen")
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
        color = service._GREEN if status == "AKTUELL" else service._RED if status == "ALT" else service._AMBER
        pdf.set_text_color(*color)
        pdf.cell(20, 5, service._safe(f"[{status}]"))
        pdf.set_text_color(*service._SLATE_700)
        pdf.cell(56, 5, service._safe(service._source_display_label(source)))
        pdf.set_text_color(*service._SLATE_400)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(
            0,
            5,
            service._safe(f"{age_days:.1f} Tage alt" if age_days >= 0 else "Zeit nicht bekannt"),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    pdf.ln(6)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*service._SLATE_400)
    pdf.multi_cell(
        0,
        4,
        service._safe(
            "Hinweis: Dieser Bericht zeigt wahrscheinliche frühe Starts einer Welle auf Basis historischer Analysen und aktueller Signale. "
            "Die genannten Vorlaufzeiten sind historische Werte und keine Garantie für die nächste Woche. "
            "Alle Empfehlungen dienen als Entscheidungshilfe; die finale Mediaplanung bleibt eine fachliche Freigabe."
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
