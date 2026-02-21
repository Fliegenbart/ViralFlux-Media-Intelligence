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
    """Leite die wahrscheinlichste Condition aus regionalen Signalen ab."""
    driver_labels = [
        str(d.get("label", "") if isinstance(d, dict) else d).lower()
        for d in (top_drivers or [])
    ]

    if any("versorgung" in dl or "shortage" in dl for dl in driver_labels):
        return "bronchitis_husten"
    if any("wetter" in dl or "weather" in dl for dl in driver_labels):
        if peix_band in ("low", "elevated"):
            return "rhinitis_trockene_nase"
        return "erkaltung_akut"
    if any("such" in dl or "search" in dl for dl in driver_labels):
        return "immun_support"

    if trend == "steigend":
        if virus_typ in ("Influenza A", "Influenza B", "RSV A"):
            return "bronchitis_husten"
        return "erkaltung_akut"

    if trend == "fallend" and peix_band == "low":
        return "immun_support"

    return "erkaltung_akut"


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
    product = CONDITION_TO_PRODUCT.get(condition, "GeloMyrtol forte")
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
