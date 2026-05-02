"""Research-only TLEF-BICG v0 service functions."""

from __future__ import annotations

from app.services.research.tri_layer.evidence_weights import evidence_quality, normalize_evidence_weights
from app.services.research.tri_layer.fusion import (
    commercial_relevance_score,
    early_warning_score,
    fuse_latent_wave_state,
)
from app.services.research.tri_layer.gates import evaluate_budget_permission, score_gate
from app.services.research.tri_layer.lead_lag import estimate_lead_lag
from app.services.research.tri_layer.schema import (
    EvidenceWeights,
    GateStates,
    TriLayerRegionEvidence,
    TriLayerRegionSnapshot,
)


def _mean_present(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _max_present(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return max(present)


def _coverage_gate(evidence: TriLayerRegionEvidence) -> str:
    connected = [
        source
        for source in (evidence.wastewater, evidence.clinical, evidence.sales)
        if source.status != "not_connected"
    ]
    if not connected:
        return "not_available"
    coverage = _mean_present([source.coverage for source in connected])
    if coverage is None:
        coverage = 0.6
    return score_gate(coverage, pass_at=0.55, watch_at=0.30)


def _drift_gate(evidence: TriLayerRegionEvidence) -> str:
    connected = [
        source
        for source in (evidence.wastewater, evidence.clinical, evidence.sales)
        if source.status != "not_connected"
    ]
    if not connected:
        return "not_available"
    drift = max(float(source.drift or 0.0) for source in connected)
    if drift >= 0.65:
        return "fail"
    if drift >= 0.35:
        return "watch"
    return "pass"


def _sales_calibration_gate(evidence: TriLayerRegionEvidence) -> str:
    if evidence.sales.status == "not_connected":
        return "not_available"
    if not (evidence.sales.budget_isolated or evidence.sales.causal_adjusted):
        return "fail"
    return score_gate(evidence.sales.signal, pass_at=0.65, watch_at=0.35)


def build_region_snapshot(evidence: TriLayerRegionEvidence) -> TriLayerRegionSnapshot:
    """Build a JSON-safe research snapshot for one region.

    Missing source data is expected and never raises. It simply produces null
    scores plus transparent gate states.
    """
    sources = {
        "wastewater": evidence.wastewater,
        "clinical": evidence.clinical,
        "sales": evidence.sales,
    }
    weights = normalize_evidence_weights(sources)
    latent = fuse_latent_wave_state(sources, weights)
    lead_lag = estimate_lead_lag(
        wastewater=evidence.wastewater,
        clinical=evidence.clinical,
        sales=evidence.sales,
    )

    wastewater_quality = evidence_quality(evidence.wastewater)
    clinical_quality = evidence_quality(evidence.clinical)
    sales_quality = evidence_quality(evidence.sales)
    epi_quality = _max_present([wastewater_quality, clinical_quality])
    epi_signal = _max_present([evidence.wastewater.signal, evidence.clinical.signal])
    ews = early_warning_score(
        event_probability=epi_signal,
        growth_mean=latent.growth_mean,
        intensity_mean=latent.intensity_mean,
        epi_quality=epi_quality,
    )
    crs = commercial_relevance_score(
        sales_signal=evidence.sales.signal if evidence.sales.status != "not_connected" else None,
        sales_quality=sales_quality,
    )

    gates = GateStates(
        epidemiological_signal=score_gate(
            max(
                value
                for value in [
                    evidence.wastewater.signal,
                    evidence.clinical.signal,
                    (ews / 100.0) if ews is not None else None,
                ]
                if value is not None
            )
            if any(value is not None for value in [evidence.wastewater.signal, evidence.clinical.signal, ews])
            else None,
            pass_at=0.65,
            watch_at=0.40,
        ),
        clinical_confirmation=score_gate(evidence.clinical.signal, pass_at=0.65, watch_at=0.30),
        sales_calibration=_sales_calibration_gate(evidence),
        coverage=_coverage_gate(evidence),  # type: ignore[arg-type]
        drift=_drift_gate(evidence),  # type: ignore[arg-type]
        budget_isolation=evidence.budget_isolation.status,
    )
    permission = evaluate_budget_permission(
        epidemiological_signal=gates.epidemiological_signal,
        clinical_confirmation=gates.clinical_confirmation,
        sales_calibration=gates.sales_calibration,
        coverage=gates.coverage,
        drift=gates.drift,
        budget_isolation=gates.budget_isolation,
    )

    explanation = (
        "Research-only TLEF-BICG v0. Budget state follows conservative gates; "
        "missing sources are represented as null or not_available."
    )
    return TriLayerRegionSnapshot(
        region=evidence.region,
        region_code=evidence.region_code,
        early_warning_score=ews,
        commercial_relevance_score=crs,
        budget_permission_state=permission.state,
        budget_can_change=permission.budget_can_change,
        wave_phase=latent.wave_phase,
        posterior=latent,
        evidence_weights=EvidenceWeights(**weights),
        lead_lag=lead_lag,
        gates=gates,
        explanation=explanation,
    )
