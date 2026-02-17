"""Produktkatalog + Auto/Review Mapping für Media-Empfehlungen."""

from __future__ import annotations

from datetime import datetime
from html import unescape
import hashlib
import logging
import re
from typing import Any

import requests
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.database import BrandProduct, ProductConditionMapping

logger = logging.getLogger(__name__)

DEFAULT_GELO_SOURCE_URL = "https://www.gelomyrtol-forte.de/gelo-produkte"

CONDITION_LABELS = {
    "bronchitis_husten": "Bronchitis / Husten",
    "sinusitis_nebenhoehlen": "Sinusitis / Nebenhöhlen",
    "halsschmerz_heiserkeit": "Halsschmerz / Heiserkeit",
    "rhinitis_trockene_nase": "Rhinitis / trockene Nase",
    "immun_support": "Immun-Support",
    "erkaltung_akut": "Erkältung akut",
}

CONDITION_KEYWORDS = {
    "bronchitis_husten": [
        "husten",
        "bronch",
        "atemweg",
        "schleim",
        "abhusten",
        "lunge",
        "copd",
        "asthma",
    ],
    "sinusitis_nebenhoehlen": [
        "sinusitis",
        "nebenhoeh",
        "nebenhöh",
        "druckkopfschmerz",
        "stirnhöhle",
        "kieferhoehle",
        "kieferhöh",
        "schnupfen",
        "nase zu",
    ],
    "halsschmerz_heiserkeit": [
        "halsschmerz",
        "halskratzen",
        "hustenreiz",
        "heiser",
        "stimme",
        "schluckbeschwerden",
        "raeusper",
        "räusper",
        "rachen",
    ],
    "rhinitis_trockene_nase": [
        "rhinitis",
        "nasenschleimhaut",
        "trockene nase",
        "juckreiz",
        "brennen",
        "verstopfte nase",
        "nasenpflege",
    ],
    "immun_support": [
        "immun",
        "omega",
        "vitamin",
        "nahrungserg",
        "praevent",
        "prävent",
    ],
    "erkaltung_akut": [
        "erkaelt",
        "erkält",
        "fieber",
        "schmerz",
        "paracetamol",
        "grippal",
        "infekt",
        "akut",
    ],
}

NAME_HINTS = {
    "gelomyrtol forte": ["bronchitis_husten", "sinusitis_nebenhoehlen"],
    "myrtol": ["bronchitis_husten", "sinusitis_nebenhoehlen"],
    "gelobronchial": ["bronchitis_husten"],
    "gelomuc": ["bronchitis_husten"],
    "gelorevoice": ["halsschmerz_heiserkeit"],
    "gelotonsil": ["halsschmerz_heiserkeit"],
    "gelositin": ["rhinitis_trockene_nase"],
    "geloprosed": ["erkaltung_akut", "rhinitis_trockene_nase", "halsschmerz_heiserkeit"],
    "gelovital": ["immun_support"],
}

HARD_RULES_BY_PRODUCT = {
    "gelositin": ["rhinitis_trockene_nase"],
    "gelobronchial": ["bronchitis_husten"],
    "gelovital": ["immun_support"],
    "geloprosed": ["erkaltung_akut"],
    "gelomyrtol forte": ["bronchitis_husten", "sinusitis_nebenhoehlen"],
}

PEDIATRIC_HARD_RULES = {
    "bronchitis_husten": [
        "myrtol kinder",
        "myrtol für kinder",
        "myrtol fuer kinder",
        "myrtol junior",
        "gelomyrtol forte",
    ],
    "sinusitis_nebenhoehlen": [
        "myrtol kinder",
        "myrtol für kinder",
        "myrtol fuer kinder",
        "gelomyrtol forte",
    ],
}

OPPORTUNITY_TYPE_FALLBACK = {
    "RESOURCE_SCARCITY": "bronchitis_husten",
    "PREDICTIVE_SALES_SPIKE": "bronchitis_husten",
    "WEATHER_FORECAST": "sinusitis_nebenhoehlen",
    "SEASONAL_DEFICIENCY": "immun_support",
}


class ProductCatalogService:
    """Lädt Produktkataloge und verwaltet Lage-Mappings mit Review-Status."""

    def __init__(self, db: Session):
        self.db = db

    def refresh_brand_catalog(
        self,
        *,
        brand: str = "gelo",
        source_url: str = DEFAULT_GELO_SOURCE_URL,
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        """Manueller Refresh einer externen Produktseite."""
        brand_key = self._normalize_brand(brand)
        source_url = source_url.strip() or DEFAULT_GELO_SOURCE_URL

        try:
            response = requests.get(source_url, timeout=timeout_seconds)
            response.raise_for_status()
            html = response.text
        except requests.RequestException as exc:
            logger.error("Produktkatalog konnte nicht geladen werden: %s", exc)
            return {"error": f"Produktquelle nicht erreichbar: {exc}"}

        parsed_products = self._extract_products_from_html(html)
        if not parsed_products:
            return {"error": "Keine Produktkarten in der Quelle erkannt."}

        now = datetime.utcnow()
        existing_rows = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.brand == brand_key)
            .all()
        )
        existing_by_name = {
            self._normalize_name(row.product_name): row
            for row in existing_rows
        }

        added: list[str] = []
        updated: list[str] = []
        removed: list[str] = []
        mapping_candidates: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        for parsed in parsed_products:
            product_name = parsed["product_name"]
            normalized_name = self._normalize_name(product_name)
            source_hash = parsed["source_hash"]
            row = existing_by_name.get(normalized_name)
            was_new = row is None
            hash_changed = False

            if was_new:
                row = BrandProduct(
                    brand=brand_key,
                    product_name=product_name,
                    source_url=source_url,
                    source_hash=source_hash,
                    active=True,
                    last_seen_at=now,
                    extra_data={
                        "short_text": parsed.get("short_text"),
                        "subline": parsed.get("subline"),
                        "details_text": parsed.get("details_text"),
                    },
                )
                self.db.add(row)
                self.db.flush()
                existing_by_name[normalized_name] = row
                added.append(product_name)
            else:
                hash_changed = row.source_hash != source_hash
                if hash_changed or not row.active:
                    updated.append(product_name)
                row.source_url = source_url
                row.source_hash = source_hash
                row.active = True
                row.last_seen_at = now
                row.updated_at = now
                row.extra_data = {
                    "short_text": parsed.get("short_text"),
                    "subline": parsed.get("subline"),
                    "details_text": parsed.get("details_text"),
                }

            seen_ids.add(row.id)
            reset_approval = was_new or hash_changed
            candidates = self._upsert_auto_mappings(
                brand=brand_key,
                product=row,
                text_blob=parsed.get("text_blob", ""),
                reset_approval=reset_approval,
            )
            candidates.extend(
                self._upsert_hard_rule_mappings(
                    brand=brand_key,
                    product=row,
                )
            )
            for candidate in candidates:
                mapping_candidates.append(
                    {
                        "product_name": product_name,
                        "condition_key": candidate["condition_key"],
                        "condition_label": self.condition_label(candidate["condition_key"]),
                        "fit_score": candidate["fit_score"],
                        "mapping_reason": candidate["mapping_reason"],
                        "is_approved": candidate["is_approved"],
                        "priority": candidate["priority"],
                        "rule_source": candidate.get("rule_source", "auto"),
                    }
                )

        for row in existing_rows:
            if row.id in seen_ids or not row.active:
                continue
            row.active = False
            row.updated_at = now
            removed.append(row.product_name)

        self.db.commit()

        return {
            "brand": brand_key,
            "source_url": source_url,
            "added": sorted(added),
            "updated": sorted(updated),
            "removed": sorted(removed),
            "mapping_candidates": mapping_candidates,
            "run_timestamp": now.isoformat() + "Z",
            "counts": {
                "products_detected": len(parsed_products),
                "added": len(added),
                "updated": len(updated),
                "removed": len(removed),
                "mapping_candidates": len(mapping_candidates),
            },
        }

    def list_products(self, *, brand: str = "gelo") -> list[dict[str, Any]]:
        brand_key = self._normalize_brand(brand)
        rows = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.brand == brand_key)
            .order_by(BrandProduct.active.desc(), BrandProduct.product_name.asc())
            .all()
        )
        return [
            {
                "id": row.id,
                "brand": row.brand,
                "product_name": row.product_name,
                "active": bool(row.active),
                "source_url": row.source_url,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

    def list_mappings(
        self,
        *,
        brand: str = "gelo",
        include_inactive_products: bool = False,
        only_pending: bool = False,
    ) -> list[dict[str, Any]]:
        brand_key = self._normalize_brand(brand)
        query = (
            self.db.query(ProductConditionMapping, BrandProduct)
            .join(BrandProduct, ProductConditionMapping.product_id == BrandProduct.id)
            .filter(ProductConditionMapping.brand == brand_key)
        )

        if not include_inactive_products:
            query = query.filter(BrandProduct.active.is_(True))
        if only_pending:
            query = query.filter(ProductConditionMapping.is_approved.is_(False))

        rows = (
            query.order_by(
                ProductConditionMapping.condition_key.asc(),
                case((ProductConditionMapping.rule_source == "hard_rule", 1), else_=0).desc(),
                ProductConditionMapping.fit_score.desc(),
                ProductConditionMapping.priority.desc(),
                BrandProduct.product_name.asc(),
            )
            .all()
        )

        return [
            {
                "mapping_id": mapping.id,
                "brand": mapping.brand,
                "product_id": product.id,
                "product_name": product.product_name,
                "product_active": bool(product.active),
                "condition_key": mapping.condition_key,
                "condition_label": self.condition_label(mapping.condition_key),
                "rule_source": mapping.rule_source or "auto",
                "fit_score": round(float(mapping.fit_score or 0.0), 3),
                "mapping_reason": mapping.mapping_reason,
                "is_approved": bool(mapping.is_approved),
                "priority": int(mapping.priority or 0),
                "notes": mapping.notes,
                "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
            }
            for mapping, product in rows
        ]

    def update_mapping(
        self,
        mapping_id: int,
        *,
        is_approved: bool | None = None,
        priority: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        mapping = (
            self.db.query(ProductConditionMapping)
            .filter(ProductConditionMapping.id == mapping_id)
            .first()
        )
        if not mapping:
            return None

        if is_approved is not None:
            mapping.is_approved = bool(is_approved)
        if priority is not None:
            mapping.priority = int(priority)
        if notes is not None:
            cleaned = notes.strip()
            mapping.notes = cleaned or None

        mapping.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(mapping)

        product = (
            self.db.query(BrandProduct)
            .filter(BrandProduct.id == mapping.product_id)
            .first()
        )

        return {
            "mapping_id": mapping.id,
            "brand": mapping.brand,
            "product_id": mapping.product_id,
            "product_name": product.product_name if product else None,
            "condition_key": mapping.condition_key,
            "condition_label": self.condition_label(mapping.condition_key),
            "rule_source": mapping.rule_source or "auto",
            "fit_score": round(float(mapping.fit_score or 0.0), 3),
            "mapping_reason": mapping.mapping_reason,
            "is_approved": bool(mapping.is_approved),
            "priority": int(mapping.priority or 0),
            "notes": mapping.notes,
            "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
        }

    def resolve_product_for_opportunity(
        self,
        *,
        brand: str,
        opportunity: dict[str, Any],
        fallback_product: str | None = None,
    ) -> dict[str, Any]:
        """Liefert Produkt-Mapping für eine Opportunity (nur approved produktiv)."""
        brand_key = self._normalize_brand(brand)
        default_product = (fallback_product or "").strip()
        condition_key = self.infer_condition_from_opportunity(opportunity)
        pediatric_context = self._is_pediatric_context(opportunity)

        if brand_key != "gelo":
            return {
                "recommended_product": default_product,
                "mapping_status": "not_applicable",
                "mapping_confidence": None,
                "mapping_reason": "Produkt-Mapping nur für Gelo-Brand aktiviert.",
                "condition_key": condition_key,
                "condition_label": self.condition_label(condition_key),
                "candidate_product": None,
                "rule_source": None,
            }

        # Kontextabhängige Hard Rule (z. B. pädiatrische Fälle) vor generischer Auswahl.
        preferred_hard = self._preferred_hard_rule_mapping(
            brand_key=brand_key,
            condition_key=condition_key,
            pediatric_context=pediatric_context,
        )
        if preferred_hard:
            return {
                "recommended_product": preferred_hard["product_name"],
                "mapping_status": "approved",
                "mapping_confidence": preferred_hard["fit_score"],
                "mapping_reason": preferred_hard["mapping_reason"] or "Hard Rule aktiv.",
                "condition_key": condition_key,
                "condition_label": self.condition_label(condition_key),
                "candidate_product": preferred_hard["product_name"],
                "rule_source": preferred_hard.get("rule_source", "hard_rule"),
            }

        approved = self._best_mapping(brand_key, condition_key, approved_only=True)
        if approved:
            return {
                "recommended_product": approved["product_name"],
                "mapping_status": "approved",
                "mapping_confidence": approved["fit_score"],
                "mapping_reason": approved["mapping_reason"] or "Freigegebenes Mapping.",
                "condition_key": condition_key,
                "condition_label": self.condition_label(condition_key),
                "candidate_product": approved["product_name"],
                "rule_source": approved.get("rule_source", "auto"),
            }

        candidate = self._best_mapping(brand_key, condition_key, approved_only=False)
        neutral_product = default_product or "Produktfreigabe ausstehend"
        if candidate:
            reason = (
                f"Zuordnung für {candidate['product_name']} vorhanden, "
                "aber noch nicht freigegeben."
            )
            confidence = candidate["fit_score"]
            candidate_product = candidate["product_name"]
        else:
            reason = "Keine passende Zuordnung gefunden. Mapping-Review erforderlich."
            confidence = None
            candidate_product = None

        return {
            "recommended_product": neutral_product,
            "mapping_status": "needs_review",
            "mapping_confidence": confidence,
            "mapping_reason": reason,
            "condition_key": condition_key,
            "condition_label": self.condition_label(condition_key),
            "candidate_product": candidate_product,
            "rule_source": candidate.get("rule_source") if candidate else None,
        }

    def _preferred_hard_rule_mapping(
        self,
        *,
        brand_key: str,
        condition_key: str,
        pediatric_context: bool,
    ) -> dict[str, Any] | None:
        """Liefert kontextabhängige Hard Rules, sofern freigegeben."""
        preferred_names = []
        if pediatric_context:
            preferred_names.extend(PEDIATRIC_HARD_RULES.get(condition_key, []))

        for product_name in preferred_names:
            normalized = self._normalize_name(product_name)
            row = (
                self.db.query(ProductConditionMapping, BrandProduct)
                .join(BrandProduct, ProductConditionMapping.product_id == BrandProduct.id)
                .filter(
                    ProductConditionMapping.brand == brand_key,
                    ProductConditionMapping.condition_key == condition_key,
                    ProductConditionMapping.is_approved.is_(True),
                    ProductConditionMapping.rule_source == "hard_rule",
                    BrandProduct.active.is_(True),
                    func.lower(BrandProduct.product_name).like(f"%{normalized}%"),
                )
                .first()
            )
            if not row:
                continue
            mapping, product = row
            return {
                "product_name": product.product_name,
                "fit_score": round(float(mapping.fit_score or 0.0), 3),
                "mapping_reason": mapping.mapping_reason,
                "is_approved": bool(mapping.is_approved),
                "priority": int(mapping.priority or 0),
                "rule_source": mapping.rule_source or "hard_rule",
            }

        return None

    def _is_pediatric_context(self, opportunity: dict[str, Any]) -> bool:
        audience = opportunity.get("target_audience") or []
        trigger = opportunity.get("trigger_context") or {}
        text_parts = [
            " ".join(str(a) for a in audience),
            str(trigger.get("event", "")),
            str(trigger.get("details", "")),
            str(opportunity.get("type", "")),
        ]
        text = " ".join(text_parts).lower()
        pediatric_markers = ("pädi", "paedi", "kinder", "pediatric", "kita", "schule")
        return any(marker in text for marker in pediatric_markers)

    def infer_condition_from_opportunity(self, opportunity: dict[str, Any]) -> str:
        """Leitet die Lageklasse aus Opportunity-Inhalten ab."""
        trigger = opportunity.get("trigger_context") or {}
        parts = [
            opportunity.get("type", ""),
            trigger.get("event", ""),
            trigger.get("details", ""),
            opportunity.get("recommendation_reason", ""),
        ]
        text = " ".join(str(p) for p in parts if p).lower()

        scores = self._condition_scores(text)
        if scores:
            best = max(scores.items(), key=lambda item: item[1]["score"])[0]
            return best

        fallback = OPPORTUNITY_TYPE_FALLBACK.get(str(opportunity.get("type", "")).upper())
        return fallback or "bronchitis_husten"

    @staticmethod
    def condition_label(condition_key: str | None) -> str:
        if not condition_key:
            return "Unbekannt"
        return CONDITION_LABELS.get(condition_key, condition_key)

    def _best_mapping(
        self,
        brand_key: str,
        condition_key: str,
        *,
        approved_only: bool,
    ) -> dict[str, Any] | None:
        query = (
            self.db.query(ProductConditionMapping, BrandProduct)
            .join(BrandProduct, ProductConditionMapping.product_id == BrandProduct.id)
            .filter(
                ProductConditionMapping.brand == brand_key,
                ProductConditionMapping.condition_key == condition_key,
                BrandProduct.active.is_(True),
            )
        )
        if approved_only:
            query = query.filter(ProductConditionMapping.is_approved.is_(True))

        row = (
            query.order_by(
                case((ProductConditionMapping.rule_source == "hard_rule", 1), else_=0).desc(),
                ProductConditionMapping.priority.desc(),
                ProductConditionMapping.fit_score.desc(),
                ProductConditionMapping.updated_at.desc(),
            )
            .first()
        )
        if not row:
            return None
        mapping, product = row
        return {
            "product_name": product.product_name,
            "fit_score": round(float(mapping.fit_score or 0.0), 3),
            "mapping_reason": mapping.mapping_reason,
            "is_approved": bool(mapping.is_approved),
            "priority": int(mapping.priority or 0),
            "rule_source": mapping.rule_source or "auto",
        }

    def _upsert_auto_mappings(
        self,
        *,
        brand: str,
        product: BrandProduct,
        text_blob: str,
        reset_approval: bool,
    ) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        candidates = self._derive_condition_candidates(
            product_name=product.product_name,
            text_blob=text_blob,
        )
        candidate_keys = {item["condition_key"] for item in candidates}

        existing_rows = (
            self.db.query(ProductConditionMapping)
            .filter(ProductConditionMapping.product_id == product.id)
            .all()
        )
        existing_by_key = {row.condition_key: row for row in existing_rows}

        serialized: list[dict[str, Any]] = []
        for candidate in candidates:
            condition_key = candidate["condition_key"]
            row = existing_by_key.get(condition_key)
            if row is None:
                row = ProductConditionMapping(
                    brand=brand,
                    product_id=product.id,
                    condition_key=condition_key,
                    rule_source="auto",
                    fit_score=candidate["fit_score"],
                    mapping_reason=candidate["mapping_reason"],
                    is_approved=False,
                    priority=candidate["priority"],
                    updated_at=now,
                )
                self.db.add(row)
            else:
                row.brand = brand
                if (row.rule_source or "auto") != "hard_rule":
                    row.rule_source = "auto"
                row.fit_score = candidate["fit_score"]
                row.mapping_reason = candidate["mapping_reason"]
                row.priority = candidate["priority"]
                row.updated_at = now
                if reset_approval:
                    row.is_approved = False

            serialized.append(
                {
                    "condition_key": condition_key,
                    "fit_score": candidate["fit_score"],
                    "mapping_reason": candidate["mapping_reason"],
                    "is_approved": bool(row.is_approved),
                    "priority": int(row.priority or candidate["priority"]),
                    "rule_source": row.rule_source or "auto",
                }
            )

        for condition_key, row in existing_by_key.items():
            if condition_key in candidate_keys:
                continue
            if (row.rule_source or "auto") == "hard_rule":
                continue
            row.fit_score = max(0.05, float(row.fit_score or 0.0) * 0.5)
            row.mapping_reason = "Historische Zuordnung, aktuell nicht im Auto-Mapping priorisiert."
            if reset_approval:
                row.is_approved = False
            row.updated_at = now

        return serialized

    def _upsert_hard_rule_mappings(
        self,
        *,
        brand: str,
        product: BrandProduct,
    ) -> list[dict[str, Any]]:
        """Pflegt deterministische Hard Rules als priorisierte Mapping-Kandidaten."""
        normalized_name = self._normalize_name(product.product_name)
        hard_conditions = HARD_RULES_BY_PRODUCT.get(normalized_name, [])
        if not hard_conditions:
            return []

        now = datetime.utcnow()
        existing_rows = (
            self.db.query(ProductConditionMapping)
            .filter(ProductConditionMapping.product_id == product.id)
            .all()
        )
        existing_by_key = {row.condition_key: row for row in existing_rows}

        candidates: list[dict[str, Any]] = []
        for condition_key in hard_conditions:
            reason = f"Hard Rule ({product.product_name}) für {self.condition_label(condition_key)}."
            row = existing_by_key.get(condition_key)
            if row is None:
                row = ProductConditionMapping(
                    brand=brand,
                    product_id=product.id,
                    condition_key=condition_key,
                    rule_source="hard_rule",
                    fit_score=0.97,
                    mapping_reason=reason,
                    is_approved=True,
                    priority=980,
                    updated_at=now,
                )
                self.db.add(row)
                approved_flag = True
                priority_value = 980
            else:
                approved_flag = bool(row.is_approved)
                priority_value = int(row.priority or 980)
                row.brand = brand
                row.rule_source = "hard_rule"
                row.fit_score = max(0.92, float(row.fit_score or 0.0))
                row.mapping_reason = reason
                row.priority = max(priority_value, 900)
                row.updated_at = now
                priority_value = int(row.priority or 900)

            candidates.append(
                {
                    "condition_key": condition_key,
                    "fit_score": round(float(row.fit_score or 0.0), 3),
                    "mapping_reason": reason,
                    "is_approved": approved_flag,
                    "priority": priority_value,
                    "rule_source": "hard_rule",
                }
            )

        return candidates

    def _derive_condition_candidates(
        self,
        *,
        product_name: str,
        text_blob: str,
    ) -> list[dict[str, Any]]:
        text = (text_blob or "").lower()
        scores = self._condition_scores(text)

        normalized_name = self._normalize_name(product_name)
        for hinted in NAME_HINTS.get(normalized_name, []):
            if hinted not in scores:
                scores[hinted] = {"score": 0.0, "hits": []}
            scores[hinted]["score"] += 2.5

        if not scores:
            return [
                {
                    "condition_key": "bronchitis_husten",
                    "fit_score": 0.35,
                    "mapping_reason": "Fallback-Zuordnung ohne klare Keyword-Treffer.",
                    "priority": 35,
                }
            ]

        max_score = max(item["score"] for item in scores.values()) or 1.0
        ranked = sorted(scores.items(), key=lambda item: item[1]["score"], reverse=True)
        top = ranked[:3]

        candidates: list[dict[str, Any]] = []
        for condition_key, data in top:
            relative = data["score"] / max_score
            fit_score = round(min(0.99, 0.35 + (relative * 0.55)), 3)
            hits = ", ".join(data["hits"][:4]) if data["hits"] else "Name/Indikations-Hinweis"
            candidates.append(
                {
                    "condition_key": condition_key,
                    "fit_score": fit_score,
                    "mapping_reason": f"Keyword-/Indikations-Treffer: {hits}",
                    "priority": int(round(fit_score * 100)),
                }
            )
        return candidates

    def _condition_scores(self, text: str) -> dict[str, dict[str, Any]]:
        scores: dict[str, dict[str, Any]] = {}
        if not text:
            return scores

        for condition_key, keywords in CONDITION_KEYWORDS.items():
            hits = [kw for kw in keywords if kw in text]
            if not hits:
                continue
            # Längere Treffer erhöhen den Score leicht für spezifischere Signale.
            score = float(len(hits)) + sum(min(0.5, len(hit) / 20.0) for hit in hits)
            scores[condition_key] = {"score": score, "hits": hits}
        return scores

    def _extract_products_from_html(self, html: str) -> list[dict[str, Any]]:
        chunks = re.split(r'(?=<div class="product product--)', html)
        products: list[dict[str, Any]] = []
        seen: set[str] = set()

        for chunk in chunks:
            if not chunk.startswith('<div class="product product--'):
                continue

            name_html = self._first_match(chunk, r'<h2 class="product__name">\s*(.*?)\s*</h2>')
            product_name = self._normalize_product_name(self._strip_html(name_html))
            if not product_name:
                continue
            normalized = self._normalize_name(product_name)
            if normalized in seen:
                continue
            seen.add(normalized)

            short_text_html = self._first_match(chunk, r'<div class="product__short-text">\s*(.*?)\s*</div>')
            subline_html = self._first_match(chunk, r'<div class="product__subline">\s*(.*?)\s*</div>')
            details_html = self._first_match(chunk, r'<div class="product__more-content">\s*(.*?)\s*</div>')

            short_text = self._strip_html(short_text_html)
            subline = self._strip_html(subline_html)
            details_text = self._strip_html(details_html)

            text_blob = " ".join(
                part for part in [product_name, subline, short_text, details_text] if part
            ).strip()
            source_hash = hashlib.sha256(text_blob.lower().encode("utf-8")).hexdigest()

            products.append(
                {
                    "product_name": product_name,
                    "short_text": short_text,
                    "subline": subline,
                    "details_text": details_text,
                    "text_blob": text_blob,
                    "source_hash": source_hash,
                }
            )

        return products

    @staticmethod
    def _first_match(text: str, pattern: str) -> str:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else ""

    @staticmethod
    def _strip_html(raw: str) -> str:
        if not raw:
            return ""
        text = re.sub(r"<br\s*/?>", " ", raw, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = text.replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_product_name(value: str) -> str:
        cleaned = value.replace("®", "").replace("™", "").replace("️", "")
        cleaned = cleaned.replace("  ", " ")
        return cleaned.strip()

    @staticmethod
    def _normalize_name(value: str) -> str:
        base = ProductCatalogService._normalize_product_name(value or "")
        return re.sub(r"\s+", " ", base.lower()).strip()

    @staticmethod
    def _normalize_brand(brand: str | None) -> str:
        raw = (brand or "").strip().lower()
        if "gelo" in raw:
            return "gelo"
        return raw or "generic"
