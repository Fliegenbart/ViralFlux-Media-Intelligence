"""Base Detector — Abstrakte Basisklasse für Opportunity-Detektoren."""

from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session


# Landkreis-Prefix → PLZ-Bereich (2-stellig). Approximation basierend auf
# KFZ-Kennzeichen / Bundesland-Zuordnung.
_BUNDESLAND_PLZ: dict[str, str] = {
    "Schleswig-Holstein": "2xxxx",
    "Hamburg": "2xxxx",
    "Niedersachsen": "3xxxx",
    "Bremen": "2xxxx",
    "Nordrhein-Westfalen": "4xxxx",
    "Hessen": "3xxxx",
    "Rheinland-Pfalz": "5xxxx",
    "Baden-Württemberg": "7xxxx",
    "Bayern": "8xxxx",
    "Saarland": "6xxxx",
    "Berlin": "1xxxx",
    "Brandenburg": "1xxxx",
    "Mecklenburg-Vorpommern": "1xxxx",
    "Sachsen": "0xxxx",
    "Sachsen-Anhalt": "0xxxx",
    "Thüringen": "0xxxx",
}


class OpportunityDetector(ABC):
    """Basisklasse für alle Opportunity-Typ-Detektoren."""

    OPPORTUNITY_TYPE: str = ""

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def detect(self) -> list[dict]:
        """Opportunities erkennen. Gibt Liste von rohen Opportunity-Dicts zurück."""
        pass

    @abstractmethod
    def calculate_urgency(self, context: dict) -> float:
        """Urgency Score 0-100 berechnen."""
        pass

    def _generate_id(self, suffix: str) -> str:
        """Generiert eine eindeutige Opportunity-ID."""
        today = datetime.now().strftime("%Y-%m-%d")
        type_short = self.OPPORTUNITY_TYPE.split("_")[0][:8].upper()
        return f"OPP-{today}-{type_short}-{suffix[:12].upper()}"

    def _derive_plz_from_states(self, states: list[str]) -> str:
        """Leitet PLZ-Cluster aus Bundeslaendern ab.

        Gibt den haeufigsten PLZ-Bereich zurueck oder 'ALL' wenn
        keine klare Zuordnung moeglich ist.
        """
        if not states:
            return "ALL"
        plz_list = [_BUNDESLAND_PLZ.get(s) for s in states if s in _BUNDESLAND_PLZ]
        if not plz_list:
            return "ALL"
        most_common = Counter(plz_list).most_common(1)
        return most_common[0][0] if most_common else "ALL"

    def _hotspot_kreise(
        self,
        disease_cluster: str = "RESPIRATORY",
        states: Optional[list[str]] = None,
        top_n: int = 5,
    ) -> list[dict]:
        """Top-N Landkreise nach Fallzahl (letzte 2 Wochen) aus SurvStat."""
        from app.models.database import SurvstatKreisData

        cutoff = datetime.now() - timedelta(days=21)
        q = (
            self.db.query(SurvstatKreisData)
            .filter(
                SurvstatKreisData.disease_cluster == disease_cluster,
                SurvstatKreisData.created_at >= cutoff,
            )
        )
        rows = q.all()
        if not rows:
            return []

        # Aggregiere nach Kreis
        kreis_sum: dict[str, int] = {}
        for r in rows:
            kreis_sum[r.kreis] = kreis_sum.get(r.kreis, 0) + (r.fallzahl or 0)

        # Sortiere absteigend, Top-N
        top = sorted(kreis_sum.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [{"kreis": k, "faelle_4w": v} for k, v in top]
