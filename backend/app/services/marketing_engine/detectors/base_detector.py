"""Base Detector — Abstrakte Basisklasse für Opportunity-Detektoren."""

from abc import ABC, abstractmethod
from datetime import datetime
from sqlalchemy.orm import Session


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
