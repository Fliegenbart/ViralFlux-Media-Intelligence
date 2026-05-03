from __future__ import annotations

from app.services.research.tri_layer.evidence_weights import normalize_evidence_weights
from app.services.research.tri_layer.fusion import fuse_latent_wave_state
from app.services.research.tri_layer.schema import SourceEvidence


def _high_quality_source(*, intensity: float, growth: float) -> SourceEvidence:
    return SourceEvidence(
        status="connected",
        freshness=0.95,
        reliability=0.90,
        baseline_stability=0.90,
        snr=0.90,
        consistency=0.90,
        drift=0.05,
        coverage=0.95,
        signal=intensity,
        intensity=intensity,
        growth=growth,
    )


def test_agreeing_wastewater_and_clinical_lower_uncertainty() -> None:
    wastewater = _high_quality_source(intensity=0.72, growth=0.18)
    clinical = _high_quality_source(intensity=0.70, growth=0.16)

    single_sources = {"wastewater": wastewater, "clinical": SourceEvidence(), "sales": SourceEvidence()}
    agreeing_sources = {"wastewater": wastewater, "clinical": clinical, "sales": SourceEvidence()}

    single = fuse_latent_wave_state(single_sources, normalize_evidence_weights(single_sources))
    agreeing = fuse_latent_wave_state(agreeing_sources, normalize_evidence_weights(agreeing_sources))

    assert agreeing.intensity_mean is not None
    assert agreeing.intensity_p10 is not None
    assert agreeing.intensity_p90 is not None
    assert agreeing.uncertainty is not None
    assert single.uncertainty is not None
    assert agreeing.uncertainty < single.uncertainty


def test_wastewater_only_keeps_early_growth_but_higher_uncertainty() -> None:
    wastewater = _high_quality_source(intensity=0.76, growth=0.14)
    clinical = _high_quality_source(intensity=0.74, growth=0.13)

    wastewater_only_sources = {"wastewater": wastewater, "clinical": SourceEvidence(), "sales": SourceEvidence()}
    confirmed_sources = {"wastewater": wastewater, "clinical": clinical, "sales": SourceEvidence()}

    wastewater_only = fuse_latent_wave_state(wastewater_only_sources, normalize_evidence_weights(wastewater_only_sources))
    confirmed = fuse_latent_wave_state(confirmed_sources, normalize_evidence_weights(confirmed_sources))

    assert wastewater_only.wave_phase in {"early_growth", "acceleration"}
    assert wastewater_only.uncertainty is not None
    assert confirmed.uncertainty is not None
    assert wastewater_only.uncertainty > confirmed.uncertainty


def test_conflicting_sources_increase_uncertainty() -> None:
    agreeing_sources = {
        "wastewater": _high_quality_source(intensity=0.70, growth=0.14),
        "clinical": _high_quality_source(intensity=0.72, growth=0.13),
        "sales": SourceEvidence(),
    }
    conflicting_sources = {
        "wastewater": _high_quality_source(intensity=0.88, growth=0.25),
        "clinical": _high_quality_source(intensity=0.20, growth=-0.12),
        "sales": SourceEvidence(),
    }

    agreeing = fuse_latent_wave_state(agreeing_sources, normalize_evidence_weights(agreeing_sources))
    conflicting = fuse_latent_wave_state(conflicting_sources, normalize_evidence_weights(conflicting_sources))

    assert agreeing.uncertainty is not None
    assert conflicting.uncertainty is not None
    assert conflicting.uncertainty > agreeing.uncertainty


def test_stale_source_gets_low_weight() -> None:
    stale_wastewater = SourceEvidence(
        status="connected",
        freshness=0.02,
        reliability=0.20,
        baseline_stability=0.30,
        snr=0.25,
        consistency=0.30,
        drift=0.20,
        coverage=0.40,
        signal=0.95,
        intensity=0.95,
        growth=0.40,
    )
    fresh_clinical = _high_quality_source(intensity=0.30, growth=0.02)
    sources = {"wastewater": stale_wastewater, "clinical": fresh_clinical, "sales": SourceEvidence()}

    posterior = fuse_latent_wave_state(sources, normalize_evidence_weights(sources))

    assert posterior.intensity_mean is not None
    assert posterior.intensity_mean < 0.55


def test_drifted_source_gets_low_weight() -> None:
    drifted_wastewater = SourceEvidence(
        status="connected",
        freshness=0.90,
        reliability=0.30,
        baseline_stability=0.20,
        snr=0.25,
        consistency=0.20,
        drift=0.95,
        coverage=0.50,
        signal=0.95,
        intensity=0.95,
        growth=0.35,
    )
    stable_clinical = _high_quality_source(intensity=0.35, growth=0.03)
    sources = {"wastewater": drifted_wastewater, "clinical": stable_clinical, "sales": SourceEvidence()}

    posterior = fuse_latent_wave_state(sources, normalize_evidence_weights(sources))

    assert posterior.intensity_mean is not None
    assert posterior.intensity_mean < 0.60


def test_sales_source_does_not_change_epidemiological_posterior() -> None:
    epi_sources = {
        "wastewater": _high_quality_source(intensity=0.62, growth=0.09),
        "clinical": _high_quality_source(intensity=0.60, growth=0.08),
        "sales": SourceEvidence(status="not_connected"),
    }
    with_sales_sources = {
        **epi_sources,
        "sales": _high_quality_source(intensity=0.99, growth=0.50),
    }

    epi_only = fuse_latent_wave_state(epi_sources, normalize_evidence_weights(epi_sources))
    with_sales = fuse_latent_wave_state(with_sales_sources, normalize_evidence_weights(with_sales_sources))

    assert with_sales.intensity_mean == epi_only.intensity_mean
    assert with_sales.growth_mean == epi_only.growth_mean

