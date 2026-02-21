import logging
from typing import Any
from sqlalchemy.orm import Session

from app.models.database import BrandProduct, ProductCatalog, ProductConditionMapping
from app.services.media.product_catalog_service import ProductCatalogService

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
        self.brand_catalog_service = ProductCatalogService(db)

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
        condition = self._resolve_condition(opportunity_type, context)

        legacy = self._match_seed_catalog(opportunity_type, condition)
        brand_products = self._match_brand_products(condition)
        merged = self._merge_suggestions(legacy, brand_products)
        return merged

    def _resolve_condition(self, opportunity_type: str, context: dict) -> str:
        condition = str(context.get("_condition", "")).strip().lower()
        if condition:
            return condition
        try:
            return self.brand_catalog_service.infer_condition_from_opportunity(context)
        except Exception:
            return (opportunity_type or "").lower().strip() or "bronchitis_husten"

    def _match_seed_catalog(self, opportunity_type: str, condition: str) -> list[dict]:
        products = (
            self.db.query(ProductCatalog)
            .filter(ProductCatalog.is_active == True)
            .all()
        )

        matched: list[dict] = []
        for p in products:
            types = p.applicable_types or []
            conditions = p.applicable_conditions or []
            if opportunity_type not in types and (opportunity_type or "").upper() not in types:
                continue

            priority = "HIGH" if condition in conditions else "MEDIUM"
            source = "seed_catalog"
            matched.append({
                "sku": p.sku,
                "name": p.name,
                "priority": priority,
                "source": source,
                "condition_key": condition,
                "mapping_status": "approved" if priority == "HIGH" else "needs_review",
                "mapping_confidence": 0.65 if priority == "HIGH" else 0.45,
                "fit_score": 0.65 if priority == "HIGH" else 0.45,
                "mapping_reason": f"Seed-Katalog-Match via opportunity_type={opportunity_type}.",
                "rule_source": "seed_catalog",
            })

        return matched

    def _match_brand_products(self, condition: str) -> list[dict]:
        if not condition:
            return []

        rows = (
            self.db.query(ProductConditionMapping, BrandProduct)
            .join(BrandProduct, ProductConditionMapping.product_id == BrandProduct.id)
            .filter(
                ProductConditionMapping.brand == "gelo",
                ProductConditionMapping.condition_key == condition,
                BrandProduct.active.is_(True),
            )
            .all()
        )
        if not rows:
            return []

        suggestions = []
        for mapping, product in rows:
            extra = mapping.product.extra_data or {}
            attrs = self._extract_product_attributes(extra)
            mapping_status = "approved" if mapping.is_approved else "needs_review"
            priority = "HIGH" if mapping.is_approved else "MEDIUM"
            suggestions.append({
                "sku": attrs.get("sku"),
                "name": mapping.product.product_name,
                "priority": priority,
                "source": "brand_products",
                "condition_key": mapping.condition_key,
                "mapping_status": mapping_status,
                "mapping_confidence": round(float(mapping.fit_score or 0.0), 3),
                "fit_score": round(float(mapping.fit_score or 0.0), 3),
                "mapping_reason": mapping.mapping_reason or "Automatischer Mapping-Vorschlag aus Produkt-Katalog.",
                "rule_source": mapping.rule_source or "auto",
            })

        suggestions.sort(
            key=lambda item: (
                0 if item["priority"] == "HIGH" else 1,
                -float(item.get("fit_score") or 0.0),
            )
        )
        return suggestions

    def _merge_suggestions(self, legacy: list[dict], manual: list[dict]) -> list[dict]:
        seen: set[tuple[str, str | None]] = set()
        merged: list[dict] = []
        for item in manual + legacy:
            key = (str(item.get("name", "")).lower(), str(item.get("sku") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

        merged.sort(
            key=lambda item: (
                0 if item.get("priority") == "HIGH" else 1,
                -float(item.get("fit_score") or 0.0),
                str(item.get("name") or ""),
            )
        )
        return merged[:20]

    @staticmethod
    def _extract_product_attributes(extra_data: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(extra_data, dict):
            return {}
        return {
            "sku": extra_data.get("sku"),
            "target_segments": extra_data.get("target_segments") or [],
            "conditions": extra_data.get("conditions") or [],
            "forms": extra_data.get("forms") or [],
            "age_min_months": extra_data.get("age_min_months"),
            "age_max_months": extra_data.get("age_max_months"),
            "audience_mode": extra_data.get("audience_mode"),
            "channel_fit": extra_data.get("channel_fit") or [],
            "compliance_notes": extra_data.get("compliance_notes"),
        }
