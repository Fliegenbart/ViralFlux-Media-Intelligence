import math

from app.services.research.tri_layer.evidence_weights import normalize_evidence_weights
from app.services.research.tri_layer.gates import evaluate_budget_permission
from app.services.research.tri_layer.schema import (
    BudgetIsolationEvidence,
    SourceEvidence,
    TriLayerRegionEvidence,
)
from app.services.research.tri_layer.service import build_region_snapshot


def test_evidence_weight_normalization_excludes_missing_sources() -> None:
    weights = normalize_evidence_weights(
        {
            "wastewater": SourceEvidence(status="connected", freshness=0.9, reliability=0.8, signal=0.8),
            "clinical": SourceEvidence(status="partial", freshness=0.7, reliability=0.7, signal=0.4),
            "sales": SourceEvidence(status="not_connected"),
        }
    )

    assert weights["sales"] is None
    assert weights["wastewater"] is not None
    assert weights["clinical"] is not None
    assert math.isclose((weights["wastewater"] or 0.0) + (weights["clinical"] or 0.0), 1.0)
    assert (weights["wastewater"] or 0.0) > (weights["clinical"] or 0.0)


def test_missing_sales_forces_budget_can_change_false() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Hamburg",
            region_code="HH",
            wastewater=SourceEvidence(status="connected", signal=0.85, growth=0.22, intensity=0.7),
            clinical=SourceEvidence(status="connected", signal=0.75, growth=0.12, intensity=0.55),
            sales=SourceEvidence(status="not_connected"),
        )
    )

    assert snapshot.commercial_relevance_score is None
    assert snapshot.gates.sales_calibration == "not_available"
    assert snapshot.budget_permission_state == "shadow_only"
    assert snapshot.budget_can_change is False


def test_strong_wastewater_weak_clinical_raises_early_warning_but_not_budget() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Bayern",
            region_code="BY",
            wastewater=SourceEvidence(status="connected", signal=0.92, growth=0.28, intensity=0.85),
            clinical=SourceEvidence(status="connected", signal=0.25, growth=0.02, intensity=0.25),
            sales=SourceEvidence(status="not_connected"),
        )
    )

    assert snapshot.early_warning_score is not None
    assert snapshot.early_warning_score > 50
    assert snapshot.gates.epidemiological_signal == "pass"
    assert snapshot.gates.clinical_confirmation in {"watch", "fail"}
    assert snapshot.budget_permission_state == "calibration_window"
    assert snapshot.budget_can_change is False


def test_clinical_confirmation_improves_gate_status() -> None:
    weak = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Berlin",
            region_code="BE",
            wastewater=SourceEvidence(status="connected", signal=0.75, growth=0.15, intensity=0.65),
            clinical=SourceEvidence(status="connected", signal=0.35, growth=0.03, intensity=0.35),
            sales=SourceEvidence(status="not_connected"),
        )
    )
    confirmed = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Berlin",
            region_code="BE",
            wastewater=SourceEvidence(status="connected", signal=0.75, growth=0.15, intensity=0.65),
            clinical=SourceEvidence(status="connected", signal=0.78, growth=0.13, intensity=0.58),
            sales=SourceEvidence(status="not_connected"),
        )
    )

    assert weak.gates.clinical_confirmation != "pass"
    assert confirmed.gates.clinical_confirmation == "pass"
    assert confirmed.budget_permission_state == "shadow_only"


def test_drift_failure_blocks_budget() -> None:
    permission = evaluate_budget_permission(
        epidemiological_signal="pass",
        clinical_confirmation="pass",
        sales_calibration="pass",
        coverage="pass",
        drift="fail",
        budget_isolation="pass",
    )

    assert permission.state == "blocked"
    assert permission.budget_can_change is False
    assert "drift_failed" in permission.reasons


def test_budget_isolation_failure_blocks_even_with_high_scores() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Nordrhein-Westfalen",
            region_code="NW",
            wastewater=SourceEvidence(status="connected", signal=0.95, growth=0.3, intensity=0.9),
            clinical=SourceEvidence(status="connected", signal=0.9, growth=0.25, intensity=0.85),
            sales=SourceEvidence(
                status="connected",
                signal=0.88,
                reliability=0.9,
                coverage=0.9,
                causal_adjusted=True,
            ),
            budget_isolation=BudgetIsolationEvidence(status="fail"),
        )
    )

    assert snapshot.commercial_relevance_score is not None
    assert snapshot.gates.sales_calibration == "pass"
    assert snapshot.gates.budget_isolation == "fail"
    assert snapshot.budget_permission_state == "blocked"
    assert snapshot.budget_can_change is False
