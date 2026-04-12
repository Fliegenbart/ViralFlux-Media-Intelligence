from __future__ import annotations

from typing import Any

from .shared import JsonDict, generated_at


def build_evidence_payload(
    service: Any,
    *,
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    brand: str,
) -> JsonDict:
    cockpit = service.cockpit_service.get_cockpit_payload(virus_typ=virus_typ, target_source=target_source)
    backtest_summary = cockpit.get("backtest_summary") or {}
    truth_snapshot = service.get_truth_evidence(brand=brand, virus_typ=virus_typ)
    truth_coverage = truth_snapshot["coverage"]
    truth_gate = service.truth_gate_service.evaluate(truth_coverage)
    outcome_learning = service.outcome_signal_service.build_learning_bundle(
        brand=brand,
        truth_coverage=truth_coverage,
        truth_gate=truth_gate,
    )["summary"]
    business_validation = service.business_validation_service.evaluate(
        brand=brand,
        virus_typ=virus_typ,
        truth_coverage=truth_coverage,
        truth_gate=truth_gate,
        outcome_learning_summary=outcome_learning,
    )
    latest_customer = backtest_summary.get("latest_customer")
    truth_validation = latest_customer if truth_coverage.get("coverage_weeks", 0) > 0 else None
    truth_validation_legacy = latest_customer if truth_validation is None and latest_customer else None
    return {
        "virus_typ": virus_typ,
        "target_source": target_source,
        "generated_at": generated_at(),
        "proxy_validation": backtest_summary.get("latest_market"),
        "business_validation": business_validation,
        "operator_context": business_validation.get("operator_context"),
        "truth_validation": truth_validation,
        "truth_validation_legacy": truth_validation_legacy,
        "recent_runs": backtest_summary.get("recent_runs") or [],
        "data_freshness": cockpit.get("data_freshness") or {},
        "source_status": cockpit.get("source_status") or {},
        "signal_stack": service.get_signal_stack(virus_typ=virus_typ),
        "model_lineage": service.get_model_lineage(virus_typ=virus_typ),
        "forecast_monitoring": service.get_forecast_monitoring(virus_typ=virus_typ, target_source=target_source),
        "truth_coverage": truth_coverage,
        "truth_gate": truth_gate,
        "truth_snapshot": truth_snapshot,
        "outcome_learning_summary": outcome_learning,
        "known_limits": service._known_limits(
            cockpit,
            virus_typ,
            truth_coverage=truth_coverage,
            truth_validation_legacy=truth_validation_legacy,
        ),
    }
