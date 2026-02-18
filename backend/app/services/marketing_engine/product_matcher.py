"""ProductMatcher — Ordnet Opportunities passende Gelo-OTC Produkte aus dem Katalog zu.

Liest den ProductCatalog aus der DB und matcht basierend auf
`applicable_types` und `applicable_conditions`.
"""

from sqlalchemy.orm import Session
import logging

from app.models.database import ProductCatalog

logger = logging.getLogger(__name__)

# Seed-Daten für den initialen Produktkatalog (Gelo OTC).
SEED_PRODUCTS = [
    {
        "sku": "GELO-GMF",
        "name": "GeloMyrtol forte",
        "category": "Atemwege",
        "applicable_types": ["RESOURCE_SCARCITY", "WEATHER_FORECAST", "PREDICTIVE_SALES_SPIKE"],
        "applicable_conditions": ["bronchitis_husten", "sinusitis_nebenhoehlen", "erkaltung_akut"],
    },
    {
        "sku": "GELO-GBR",
        "name": "GeloBronchial",
        "category": "Atemwege",
        "applicable_types": ["WEATHER_FORECAST", "PREDICTIVE_SALES_SPIKE"],
        "applicable_conditions": ["bronchitis_husten", "erkaltung_akut"],
    },
    {
        "sku": "GELO-REV",
        "name": "GeloRevoice",
        "category": "Hals",
        "applicable_types": ["WEATHER_FORECAST", "PREDICTIVE_SALES_SPIKE"],
        "applicable_conditions": ["halsschmerz_heiserkeit", "erkaltung_akut"],
    },
    {
        "sku": "GELO-SIT",
        "name": "GeloSitin",
        "category": "Nase",
        "applicable_types": ["WEATHER_FORECAST", "PREDICTIVE_SALES_SPIKE"],
        "applicable_conditions": ["rhinitis_trockene_nase", "erkaltung_akut"],
    },
    {
        "sku": "GELO-VIT",
        "name": "GeloVital",
        "category": "Immunsupport",
        "applicable_types": ["WEATHER_FORECAST", "PREDICTIVE_SALES_SPIKE", "RESOURCE_SCARCITY"],
        "applicable_conditions": ["immun_support", "erkaltung_akut"],
    },
    {
        "sku": "GELO-PRO",
        "name": "GeloProsed",
        "category": "Erkaeltung",
        "applicable_types": ["WEATHER_FORECAST", "PREDICTIVE_SALES_SPIKE", "RESOURCE_SCARCITY"],
        "applicable_conditions": ["erkaltung_akut", "rhinitis_trockene_nase", "halsschmerz_heiserkeit"],
    },
]


class ProductMatcher:
    """Ordnet Marketing-Opportunities passende Produkte zu."""

    def __init__(self, db: Session):
        self.db = db
        self._ensure_catalog()

    def _ensure_catalog(self):
        """Seed-Produkte einfügen falls Katalog leer."""
        count = self.db.query(ProductCatalog).count()
        if count > 0:
            return

        logger.info("Produktkatalog leer — Seed-Daten einfügen")
        for product in SEED_PRODUCTS:
            self.db.add(ProductCatalog(**product))
        self.db.commit()
        logger.info(f"{len(SEED_PRODUCTS)} Produkte geseedet")

    def match(self, opportunity_type: str, context: dict) -> list[dict]:
        """Findet passende Produkte für eine Opportunity."""
        condition = context.get("_condition", "")

        # Query: applicable_types enthält den Opportunity-Typ
        products = (
            self.db.query(ProductCatalog)
            .filter(ProductCatalog.is_active == True)
            .all()
        )

        matched = []
        for p in products:
            types = p.applicable_types or []
            conditions = p.applicable_conditions or []

            # Match: Typ muss passen
            if opportunity_type not in types:
                continue

            # Priorität: Condition-Match = HIGH, nur Typ-Match = MEDIUM
            priority = "HIGH" if condition in conditions else "MEDIUM"

            matched.append({
                "sku": p.sku,
                "name": p.name,
                "priority": priority,
            })

        # Sortiere: HIGH zuerst
        matched.sort(key=lambda x: 0 if x["priority"] == "HIGH" else 1)

        return matched
