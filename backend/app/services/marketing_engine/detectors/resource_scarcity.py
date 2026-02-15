"""ResourceScarcityDetector — BfArM-Lieferengpässe → Diagnostik-Opportunities.

Nutzt den DrugShortageAnalyzer Singleton, um aus Medikamenten-Engpässen
Vertriebschancen für diagnostische Produkte abzuleiten.

Logik: Antibiotika-Engpass → CRP-/PCT-Tests empfehlen (viral/bakteriell differenzieren)
       Atemwege-Engpass  → Multiplex PCR empfehlen (Erreger identifizieren)
       Fieber-Engpass    → Blutbild empfehlen (Differentialdiagnostik)
"""

from datetime import datetime
import logging

from .base_detector import OpportunityDetector

logger = logging.getLogger(__name__)

# Mapping: Engpass-Kategorie → Opportunity-Kontext
CATEGORY_MAP = {
    "Antibiotika": {
        "condition": "antibiotika_shortage",
        "audience": ["Pädiater", "Hausärzte"],
        "event": "CRITICAL_SHORTAGE_ANTIBIOTICS",
        "rationale": "Antibiotika-Engpass erfordert präzise viral/bakterielle Differenzierung",
    },
    "Atemwege": {
        "condition": "atemwege_shortage",
        "audience": ["Allgemeinmediziner", "Pädiater", "Pneumologen"],
        "event": "CRITICAL_SHORTAGE_RESPIRATORY",
        "rationale": "Atemwegsmedikamenten-Engpass — Erreger-Identifikation wird kritisch",
    },
    "Fieber_Schmerz": {
        "condition": "fieber_shortage",
        "audience": ["Hausärzte", "Internisten"],
        "event": "CRITICAL_SHORTAGE_FEVER",
        "rationale": "Fieber-/Schmerzmittel-Engpass — Differentialdiagnostik notwendig",
    },
}


class ResourceScarcityDetector(OpportunityDetector):
    """Erkennt Vertriebschancen aus BfArM-Lieferengpässen."""

    OPPORTUNITY_TYPE = "RESOURCE_SCARCITY"

    def detect(self) -> list[dict]:
        """Prüft DrugShortageAnalyzer auf aktive Engpässe."""
        try:
            from app.api.drug_shortage import _analyzer
        except ImportError:
            logger.warning("drug_shortage Modul nicht verfügbar")
            return []

        if _analyzer is None or _analyzer.df_filtered is None or _analyzer.df_filtered.empty:
            logger.info("Keine BfArM-Daten geladen — ResourceScarcityDetector übersprungen")
            return []

        signals = _analyzer.get_infection_signals()
        if signals["current_risk_score"] == 0:
            return []

        opportunities = []
        by_category = signals.get("by_category", {})
        wave_type = signals.get("wave_type", "None")
        pediatric_alert = signals.get("pediatric_alert", False)
        risk_score = signals["current_risk_score"]
        top_drugs = signals.get("top_missing_drugs", [])

        for cat_name, cat_info in CATEGORY_MAP.items():
            cat_data = by_category.get(cat_name, {})
            high_demand = cat_data.get("high_demand", 0)

            if high_demand == 0:
                continue

            urgency = self.calculate_urgency({
                "risk_score": risk_score,
                "high_demand": high_demand,
                "pediatric_alert": pediatric_alert,
                "category": cat_name,
            })

            audience = list(cat_info["audience"])
            if pediatric_alert and "Pädiater" not in audience:
                audience.insert(0, "Pädiater")

            # Top fehlende Medikamente für diese Kategorie
            cat_drugs = []
            if _analyzer.df_filtered is not None:
                cat_df = _analyzer.df_filtered[
                    _analyzer.df_filtered["category"] == cat_name
                ]
                if not cat_df.empty:
                    cat_drugs = (
                        cat_df["Arzneimittlbezeichnung"]
                        .drop_duplicates()
                        .head(5)
                        .tolist()
                    )

            opp = {
                "id": self._generate_id(f"{cat_name[:4]}-{high_demand}"),
                "type": self.OPPORTUNITY_TYPE,
                "status": "NEW" if urgency < 90 else "URGENT",
                "urgency_score": urgency,
                "region_target": {
                    "country": "DE",
                    "states": [],
                    "plz_cluster": "ALL",
                },
                "trigger_context": {
                    "source": "BfArM_API",
                    "event": cat_info["event"],
                    "details": (
                        f"{high_demand} Engpässe in Kategorie {cat_name} "
                        f"durch erhöhte Nachfrage. Wellentyp: {wave_type}. "
                        f"Fehlend: {', '.join(cat_drugs[:3])}"
                    ),
                    "detected_at": datetime.now().strftime("%Y-%m-%d"),
                },
                "target_audience": audience,
                "_condition": cat_info["condition"],
                "_category": cat_name,
                "_pediatric_alert": pediatric_alert,
                "_pediatric_count": cat_data.get("pediatric", 0),
                "_wave_type": wave_type,
                "_top_drugs": cat_drugs,
            }
            opportunities.append(opp)

        return opportunities

    def calculate_urgency(self, context: dict) -> float:
        """Urgency basiert auf BfArM risk_score + Pädiatrie-Bonus."""
        base = context.get("risk_score", 0)
        if context.get("pediatric_alert"):
            base = min(100, base + 10)
        high_demand = context.get("high_demand", 0)
        if high_demand >= 5:
            base = min(100, base + 5)
        return float(base)
