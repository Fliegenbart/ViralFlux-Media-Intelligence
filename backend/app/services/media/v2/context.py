from __future__ import annotations

from typing import Any


def normalize_brand(value: Any) -> str:
    if value is None:
        raise ValueError("brand must be provided")
    brand_value = str(value).strip().lower()
    if not brand_value:
        raise ValueError("brand must be a non-empty string")
    return brand_value


def build_truth_learning_context(
    service: Any,
    *,
    brand: str,
    virus_typ: str | None = None,
    truth_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    brand_value = normalize_brand(brand)
    coverage = truth_coverage or service.get_truth_coverage(
        brand=brand_value,
        virus_typ=virus_typ,
    )
    truth_gate = service.truth_gate_service.evaluate(coverage)
    learning_bundle = service.outcome_signal_service.build_learning_bundle(
        brand=brand_value,
        truth_coverage=coverage,
        truth_gate=truth_gate,
    )
    return {
        "brand": brand_value,
        "truth_coverage": coverage,
        "truth_gate": truth_gate,
        "learning_bundle": learning_bundle,
    }


def build_truth_validation_context(
    service: Any,
    *,
    brand: str,
    virus_typ: str | None = None,
    truth_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = build_truth_learning_context(
        service,
        brand=brand,
        virus_typ=virus_typ,
        truth_coverage=truth_coverage,
    )
    business_validation = service.business_validation_service.evaluate(
        brand=context["brand"],
        virus_typ=virus_typ,
        truth_coverage=context["truth_coverage"],
        truth_gate=context["truth_gate"],
        outcome_learning_summary=context["learning_bundle"]["summary"],
    )
    return {
        **context,
        "business_validation": business_validation,
    }
