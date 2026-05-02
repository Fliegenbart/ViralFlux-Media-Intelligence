"""Dynamic lead-lag estimates for TLEF-BICG v0."""

from __future__ import annotations

from app.services.research.tri_layer.schema import LeadLagEstimate, SourceEvidence


def estimate_lead_lag(
    *,
    wastewater: SourceEvidence,
    clinical: SourceEvidence,
    sales: SourceEvidence,
) -> LeadLagEstimate:
    """Return deterministic v0 lag estimates only when source pairs exist."""
    wastewater_to_clinical = None
    clinical_to_sales = None
    uncertainties: list[float] = []

    if wastewater.status != "not_connected" and clinical.status != "not_connected":
        wastewater_to_clinical = 5.0
        uncertainties.append(0.35)

    if clinical.status != "not_connected" and sales.status != "not_connected":
        clinical_to_sales = 7.0
        uncertainties.append(0.45)

    lag_uncertainty = round(sum(uncertainties) / len(uncertainties), 4) if uncertainties else None
    return LeadLagEstimate(
        wastewater_to_clinical_days_mean=wastewater_to_clinical,
        clinical_to_sales_days_mean=clinical_to_sales,
        lag_uncertainty=lag_uncertainty,
    )
