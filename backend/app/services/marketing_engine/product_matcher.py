"""ProductMatcher — Ordnet Opportunities passende Produkte aus dem Katalog zu.

Liest den ProductCatalog aus der DB und matcht basierend auf
`applicable_types` und `applicable_conditions`.
"""

from sqlalchemy.orm import Session
import logging

from app.models.database import ProductCatalog

logger = logging.getLogger(__name__)

# Seed-Daten für den initialen Produktkatalog
SEED_PRODUCTS = [
    {
        "sku": "GI-CRP-POC-50",
        "name": "Quantitativer CRP Schnelltest (50er Pack)",
        "category": "CRP",
        "applicable_types": ["RESOURCE_SCARCITY"],
        "applicable_conditions": ["antibiotika_shortage", "fieber_shortage"],
    },
    {
        "sku": "GI-PCT-QUANT-25",
        "name": "Procalcitonin Schnelltest (25er Pack)",
        "category": "PCT",
        "applicable_types": ["RESOURCE_SCARCITY"],
        "applicable_conditions": ["antibiotika_shortage"],
    },
    {
        "sku": "GI-PCR-RESP-PANEL",
        "name": "Multiplex PCR Panel Atemwege",
        "category": "PCR",
        "applicable_types": ["RESOURCE_SCARCITY"],
        "applicable_conditions": ["atemwege_shortage"],
    },
    {
        "sku": "GI-BLUTBILD-10",
        "name": "Differentialblutbild (10er Pack)",
        "category": "Haematologie",
        "applicable_types": ["RESOURCE_SCARCITY"],
        "applicable_conditions": ["fieber_shortage"],
    },
    {
        "sku": "LAB-REQ-VITD3",
        "name": "25-OH-Vitamin-D Laboranforderung",
        "category": "Vitamin_D",
        "applicable_types": ["SEASONAL_DEFICIENCY"],
        "applicable_conditions": ["low_uv"],
    },
    {
        "sku": "GI-INF-AB-RAPID",
        "name": "Influenza A/B Schnelltest (25er Pack)",
        "category": "Influenza",
        "applicable_types": ["PREDICTIVE_SALES_SPIKE", "RESOURCE_SCARCITY"],
        "applicable_conditions": ["influenza_spike", "atemwege_shortage"],
    },
    {
        "sku": "GI-RSV-AG-25",
        "name": "RSV Antigen Schnelltest (25er Pack)",
        "category": "RSV",
        "applicable_types": ["PREDICTIVE_SALES_SPIKE"],
        "applicable_conditions": ["rsv_spike"],
    },
    {
        "sku": "GI-COV2-AG-20",
        "name": "SARS-CoV-2 Antigen Schnelltest (20er Pack)",
        "category": "COVID",
        "applicable_types": ["PREDICTIVE_SALES_SPIKE"],
        "applicable_conditions": ["covid_spike"],
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
