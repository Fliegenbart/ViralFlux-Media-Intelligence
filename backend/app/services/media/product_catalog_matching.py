"""Matching-Logik für den Produktkatalog."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func

from app.core.time import utc_now
from app.models.database import BrandProduct, ProductConditionMapping

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
    "myrtol 120mg": ["bronchitis_husten", "sinusitis_nebenhoehlen"],
    "myrtol 120": ["bronchitis_husten", "sinusitis_nebenhoehlen"],
    "gelobronchial": ["bronchitis_husten"],
    "gelomuc": ["bronchitis_husten"],
    "gelorevoice": ["halsschmerz_heiserkeit"],
    "gelotonsil": ["halsschmerz_heiserkeit", "erkaltung_akut"],
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
    "myrtol 120mg": ["bronchitis_husten", "sinusitis_nebenhoehlen"],
    "gelotonsil": ["halsschmerz_heiserkeit", "erkaltung_akut"],
}

PEDIATRIC_HARD_RULES = {
    "bronchitis_husten": [
        "myrtol kinder",
        "myrtol für kinder",
        "myrtol fuer kinder",
        "myrtol junior",
        "myrtol 120mg",
        "myrtol 120",
        "gelomyrtol forte",
    ],
    "sinusitis_nebenhoehlen": [
        "myrtol kinder",
        "myrtol für kinder",
        "myrtol fuer kinder",
        "myrtol 120mg",
        "myrtol 120",
        "gelomyrtol forte",
    ],
}

OPPORTUNITY_TYPE_FALLBACK = {
    "RESOURCE_SCARCITY": "bronchitis_husten",
    "PREDICTIVE_SALES_SPIKE": "bronchitis_husten",
    "WEATHER_FORECAST": "sinusitis_nebenhoehlen",
    "SEASONAL_DEFICIENCY": "immun_support",
}


def resolve_product_for_opportunity(
    service,
    *,
    brand: str,
    opportunity: dict[str, Any],
    fallback_product: str | None = None,
) -> dict[str, Any]:
    """Liefert Produkt-Mapping für eine Opportunity (nur approved produktiv)."""
    brand_key = service._normalize_brand(brand)
    condition_key = service.infer_condition_from_opportunity(opportunity)
    pediatric_context = service._is_pediatric_context(opportunity)

    if brand_key != "gelo":
        return {
            "recommended_product": None,
            "mapping_status": "not_applicable",
            "mapping_confidence": None,
            "mapping_reason": "Produkt-Mapping nur für Gelo-Brand aktiviert.",
            "condition_key": condition_key,
            "condition_label": service.condition_label(condition_key),
            "candidate_product": None,
            "rule_source": None,
        }

    preferred_hard = service._preferred_hard_rule_mapping(
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
            "condition_label": service.condition_label(condition_key),
            "candidate_product": preferred_hard["product_name"],
            "rule_source": preferred_hard.get("rule_source", "hard_rule"),
        }

    approved = service._best_mapping(brand_key, condition_key, approved_only=True)
    if approved:
        return {
            "recommended_product": approved["product_name"],
            "mapping_status": "approved",
            "mapping_confidence": approved["fit_score"],
            "mapping_reason": approved["mapping_reason"] or "Freigegebenes Mapping.",
            "condition_key": condition_key,
            "condition_label": service.condition_label(condition_key),
            "candidate_product": approved["product_name"],
            "rule_source": approved.get("rule_source", "auto"),
        }

    candidate = service._best_mapping(brand_key, condition_key, approved_only=False)
    if candidate:
        reason = (
            f"Zuordnung für {candidate['product_name']} vorhanden, "
            "aber noch nicht freigegeben."
        )
        confidence = candidate["fit_score"]
        candidate_product = candidate["product_name"]
    else:
        reason = "Keine passende Zuordnung gefunden. Eine Pruefung des Mappings ist erforderlich."
        confidence = None
        candidate_product = None

    return {
        "recommended_product": None,
        "mapping_status": "needs_review",
        "mapping_confidence": confidence,
        "mapping_reason": reason,
        "condition_key": condition_key,
        "condition_label": service.condition_label(condition_key),
        "candidate_product": candidate_product,
        "rule_source": candidate.get("rule_source") if candidate else None,
    }


def infer_condition_from_opportunity(opportunity: dict[str, Any]) -> str:
    """Leitet die Lageklasse aus Opportunity-Inhalten ab."""
    trigger = opportunity.get("trigger_context") or {}
    parts = [
        opportunity.get("type", ""),
        trigger.get("event", ""),
        trigger.get("details", ""),
        opportunity.get("recommendation_reason", ""),
    ]
    text = " ".join(str(p) for p in parts if p).lower()

    scores = _condition_scores(text)
    if scores:
        best = max(scores.items(), key=lambda item: item[1]["score"])[0]
        return best

    fallback = OPPORTUNITY_TYPE_FALLBACK.get(str(opportunity.get("type", "")).upper())
    return fallback or "bronchitis_husten"


def condition_label(condition_key: str | None) -> str:
    if not condition_key:
        return "Unbekannt"
    return CONDITION_LABELS.get(condition_key, condition_key)


def _preferred_hard_rule_mapping(
    service,
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
        normalized = service._normalize_name(product_name)
        row = (
            service.db.query(ProductConditionMapping, BrandProduct)
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


def _is_pediatric_context(opportunity: dict[str, Any]) -> bool:
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


def _best_mapping(
    service,
    brand_key: str,
    condition_key: str,
    *,
    approved_only: bool,
) -> dict[str, Any] | None:
    query = (
        service.db.query(ProductConditionMapping, BrandProduct)
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
    service,
    *,
    brand: str,
    product: BrandProduct,
    text_blob: str,
    reset_approval: bool,
) -> list[dict[str, Any]]:
    now = utc_now()
    candidates = service._derive_condition_candidates(
        product_name=product.product_name,
        text_blob=text_blob,
    )
    candidate_keys = {item["condition_key"] for item in candidates}

    existing_rows = (
        service.db.query(ProductConditionMapping)
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
            service.db.add(row)
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
    service,
    *,
    brand: str,
    product: BrandProduct,
) -> list[dict[str, Any]]:
    """Pflegt deterministische Hard Rules als priorisierte Mapping-Kandidaten."""
    normalized_name = service._normalize_name(product.product_name)
    hard_conditions = HARD_RULES_BY_PRODUCT.get(normalized_name, [])
    if not hard_conditions:
        return []

    now = utc_now()
    existing_rows = (
        service.db.query(ProductConditionMapping)
        .filter(ProductConditionMapping.product_id == product.id)
        .all()
    )
    existing_by_key = {row.condition_key: row for row in existing_rows}

    candidates: list[dict[str, Any]] = []
    for condition_key in hard_conditions:
        reason = f"Hard Rule ({product.product_name}) für {condition_label(condition_key)}."
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
            service.db.add(row)
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
    service,
    *,
    product_name: str,
    text_blob: str,
) -> list[dict[str, Any]]:
    text = (text_blob or "").lower()
    scores = service._condition_scores(text)

    normalized_name = service._normalize_name(product_name)
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


def _condition_scores(text: str) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    if not text:
        return scores

    for condition_key, keywords in CONDITION_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if not hits:
            continue
        score = float(len(hits)) + sum(min(0.5, len(hit) / 20.0) for hit in hits)
        scores[condition_key] = {"score": score, "hits": hits}
    return scores
