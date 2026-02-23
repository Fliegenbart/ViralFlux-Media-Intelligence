"""Deterministic per-region tooltip recommendation generator.

Erzeugt pro Bundesland einen Kampagnenvorschlag mit epidemiologischer
Begründung auf Basis bestehender Signale (PeixEpiScore, Wastewater-Trend,
Vorhersage). Kein LLM — rein template-basiert.
"""

VIRUS_LABEL = {
    "Influenza A": "Influenza-A",
    "Influenza B": "Influenza-B",
    "SARS-CoV-2": "SARS-CoV-2",
    "RSV A": "RSV",
}

TREND_TEXT = {
    "steigend": "einen steigenden {virus}-Trend ({pct} WoW)",
    "fallend": "rückläufige {virus}-Aktivität ({pct} WoW)",
    "stabil": "eine stabile {virus}-Lage ({pct} WoW)",
}

BAND_URGENCY = {
    "critical": "Sofortmaßnahme",
    "high": "Priorität hoch",
    "elevated": "Beobachten & vorbereiten",
    "low": "Präventiv positionieren",
}

CONDITION_TO_PRODUCT = {
    "bronchitis_husten": "GeloMyrtol forte",
    "sinusitis_nebenhoehlen": "GeloMyrtol forte",
    "halsschmerz_heiserkeit": "GeloRevoice",
    "rhinitis_trockene_nase": "GeloSitin",
    "immun_support": "GeloVital",
    "erkaltung_akut": "GeloProsed",
}

CONDITION_TO_REASON = {
    "bronchitis_husten": "weil mit anhaltendem Husten und festsitzendem Schleim zu rechnen ist",
    "sinusitis_nebenhoehlen": "weil Nebenhöhlen-Beschwerden zunehmen können",
    "halsschmerz_heiserkeit": "weil Halsbeschwerden und Heiserkeit wahrscheinlicher werden",
    "rhinitis_trockene_nase": "weil trockene, gereizte Nasenschleimhäute häufiger auftreten",
    "immun_support": "weil präventive Immununterstützung sinnvoll positioniert werden kann",
    "erkaltung_akut": "weil akute Erkältungssymptome zunehmen könnten",
}


def _infer_condition(
    trend: str,
    peix_band: str,
    top_drivers: list | None,
    virus_typ: str,
) -> str:
    """Produktempfehlung nach Region differenzieren — Band + Trend + zweitstärkstem Driver.

    Der stärkste Driver (z.B. Versorgungslage) ist oft für alle Regionen identisch.
    Deshalb nutzen wir peix_band + trend als primäre Differenzierung und den
    zweitstärksten Driver als Tiebreaker.
    """
    driver_labels = [
        str(d.get("label", "") if isinstance(d, dict) else d).lower()
        for d in (top_drivers or [])
    ]
    secondary_driver = driver_labels[1] if len(driver_labels) > 1 else ""

    # ── Akute Welle: steigend + kritisch/hoch ──
    if trend == "steigend" and peix_band == "critical":
        return "bronchitis_husten"              # GeloMyrtol forte — schwerste Lage

    if trend == "steigend" and peix_band == "high":
        if "wetter" in secondary_driver or "weather" in secondary_driver:
            return "sinusitis_nebenhoehlen"      # GeloMyrtol forte (Nebenhöhlen)
        return "erkaltung_akut"                  # GeloProsed — allgemeine Erkältung

    # ── Abklingphase: fallend ──
    if trend == "fallend":
        if peix_band in ("critical", "high"):
            return "halsschmerz_heiserkeit"      # GeloRevoice — Nachwirkungen
        return "immun_support"                   # GeloVital — Prävention

    # ── Stabil oder steigend + elevated ──
    if "wetter" in secondary_driver or "weather" in secondary_driver:
        return "rhinitis_trockene_nase"          # GeloSitin — Wetter-getrieben

    if "such" in secondary_driver or "search" in secondary_driver:
        return "immun_support"                   # GeloVital — Suchtrend

    if trend == "steigend":
        return "erkaltung_akut"                  # GeloProsed

    return "erkaltung_akut"                      # Fallback


def build_region_tooltip(
    *,
    region_name: str,
    virus_typ: str,
    trend: str,
    change_pct: float,
    peix_score: float | None = None,
    peix_band: str = "low",
    impact_probability: float | None = None,
    top_drivers: list | None = None,
    vorhersage_delta_pct: float | None = None,
) -> dict:
    """Erzeuge ein Tooltip-Dict für ein einzelnes Bundesland."""
    virus_label = VIRUS_LABEL.get(virus_typ, virus_typ)
    pct_str = f"{change_pct:+.0f}%"

    # Epi-Outlook
    trend_template = TREND_TEXT.get(trend, TREND_TEXT["stabil"])
    epi_outlook = trend_template.format(virus=virus_label, pct=pct_str)

    if vorhersage_delta_pct is not None and abs(vorhersage_delta_pct) > 5:
        if vorhersage_delta_pct > 0:
            epi_outlook += " — Prognosemodell zeigt weiteren Anstieg"
        else:
            epi_outlook += " — Prognosemodell zeigt Rückgang"

    # Condition + Product
    condition = _infer_condition(trend, peix_band, top_drivers, virus_typ)
    product = CONDITION_TO_PRODUCT.get(condition, "GeloProsed")
    reason = CONDITION_TO_REASON.get(condition, "")

    recommendation_text = (
        f"In {region_name} erwarten wir in den nächsten 7\u201314 Tagen "
        f"{epi_outlook} und empfehlen deshalb {product}, "
        f"{reason}."
    )

    urgency = BAND_URGENCY.get(peix_band, "Beobachten")

    return {
        "region_name": region_name,
        "recommendation_text": recommendation_text,
        "epi_outlook": epi_outlook,
        "recommended_product": product,
        "condition_key": condition,
        "peix_score": round(float(peix_score or 0), 1),
        "peix_band": peix_band,
        "impact_probability": round(float(impact_probability or 0), 1),
        "urgency_label": urgency,
        "trend": trend,
        "change_pct": round(float(change_pct), 1),
        "virus_typ": virus_typ,
    }
