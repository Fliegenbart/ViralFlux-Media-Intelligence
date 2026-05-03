"""Gate semantics for research-only Tri-Layer Evidence Fusion v0."""

from __future__ import annotations

from app.services.research.tri_layer.schema import BudgetPermission, GateState


def score_gate(value: float | None, *, pass_at: float, watch_at: float) -> GateState:
    if value is None:
        return "not_available"
    if value >= pass_at:
        return "pass"
    if value >= watch_at:
        return "watch"
    return "fail"


def evaluate_budget_permission(
    *,
    epidemiological_signal: GateState,
    clinical_confirmation: GateState,
    sales_calibration: GateState,
    coverage: GateState,
    drift: GateState,
    budget_isolation: GateState,
) -> BudgetPermission:
    """Apply the v0 budget safety cascade.

    This function is intentionally conservative: no budget approval can happen
    unless epidemiology, clinical confirmation, sales calibration, coverage,
    drift and isolation gates all pass.
    """
    reasons: list[str] = []

    if coverage == "fail":
        reasons.append("coverage_failed")
    if drift == "fail":
        reasons.append("drift_failed")
    if budget_isolation == "fail":
        reasons.append("budget_isolation_failed")
    if budget_isolation == "not_available" and sales_calibration == "pass":
        reasons.append("budget_isolation_missing")
    if epidemiological_signal in {"fail", "not_available"}:
        reasons.append("epidemiological_signal_missing")

    if reasons:
        return BudgetPermission(state="blocked", budget_can_change=False, reasons=reasons)

    if clinical_confirmation != "pass":
        return BudgetPermission(
            state="calibration_window",
            budget_can_change=False,
            reasons=["clinical_confirmation_missing"],
        )

    if sales_calibration != "pass":
        return BudgetPermission(
            state="shadow_only",
            budget_can_change=False,
            reasons=["sales_calibration_missing"],
        )

    if budget_isolation == "watch":
        return BudgetPermission(
            state="limited",
            budget_can_change=False,
            reasons=["budget_isolation_requires_manual_review"],
        )

    return BudgetPermission(
        state="limited",
        budget_can_change=False,
        reasons=["research_limited_requires_manual_approval"],
    )
