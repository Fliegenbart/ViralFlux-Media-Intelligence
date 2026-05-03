"""Bayesian-lite latent-state fusion for TLEF-BICG."""

from __future__ import annotations

import math
from typing import Mapping

from app.services.research.tri_layer.evidence_weights import evidence_quality
from app.services.research.tri_layer.schema import LatentWaveState, SourceEvidence, WavePhase


EPIDEMIOLOGICAL_SOURCE_NAMES = ("wastewater", "clinical")
_NORMAL_Z_10_90 = 1.2815515655446004


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float | None, lower: float = 0.0, upper: float = 1.0) -> float | None:
    if value is None:
        return None
    return max(lower, min(upper, float(value)))


def _component(source: SourceEvidence, attr: str, default: float) -> float:
    value = _safe_float(getattr(source, attr, None))
    if value is None:
        return default
    return float(_clamp(value, 0.0, 1.0))


def _quality(source: SourceEvidence) -> float | None:
    quality = evidence_quality(source)
    if quality is None:
        return None
    quality = float(_clamp(float(quality), 0.0, 1.0))
    if source.status == "partial":
        quality *= 0.80
    return quality


def _source_variance(source: SourceEvidence) -> float:
    quality = _quality(source)
    if quality is None:
        return 0.35
    freshness = _component(source, "freshness", quality)
    reliability = _component(source, "reliability", quality)
    baseline_stability = _component(source, "baseline_stability", quality)
    snr = _component(source, "snr", quality)
    consistency = _component(source, "consistency", quality)
    drift = _component(source, "drift", 0.0)
    coverage = _component(source, "coverage", 0.6 if source.status == "connected" else 0.35)

    component_quality = (
        0.18 * freshness
        + 0.20 * reliability
        + 0.12 * baseline_stability
        + 0.14 * snr
        + 0.14 * consistency
        + 0.20 * coverage
        - 0.22 * drift
    )
    q = float(_clamp((quality + component_quality) / 2.0, 0.01, 0.99))
    variance = (
        0.018
        + ((1.0 - q) ** 2) * 0.22
        + drift * 0.08
        + (1.0 - coverage) * 0.05
        + (1.0 - freshness) * 0.03
    )
    return max(0.012, min(0.40, variance))


def _softmax(qualities: Mapping[str, float]) -> dict[str, float]:
    if not qualities:
        return {}
    max_quality = max(qualities.values())
    exp_values = {
        name: math.exp(float(quality) - max_quality)
        for name, quality in qualities.items()
    }
    denom = sum(exp_values.values())
    if denom <= 0:
        return {name: 1.0 / len(exp_values) for name in exp_values}
    return {name: value / denom for name, value in exp_values.items()}


def _epidemiological_sources(sources: Mapping[str, SourceEvidence]) -> dict[str, SourceEvidence]:
    return {
        name: source
        for name in EPIDEMIOLOGICAL_SOURCE_NAMES
        if (source := sources.get(name)) is not None and source.status != "not_connected"
    }


def _posterior_dimension(
    sources: Mapping[str, SourceEvidence],
    omegas: Mapping[str, float],
    attr: str,
    *,
    prior_mean: float,
    prior_variance: float,
) -> tuple[float | None, float | None]:
    precision_prior = 1.0 / prior_variance
    weighted_precision = precision_prior
    weighted_mean = precision_prior * prior_mean
    used = 0

    for name, source in sources.items():
        value = _safe_float(getattr(source, attr, None))
        omega = _safe_float(omegas.get(name))
        if value is None or omega is None or omega <= 0:
            continue
        variance = _source_variance(source)
        precision = float(omega) / variance
        weighted_precision += precision
        weighted_mean += precision * float(value)
        used += 1

    if used <= 0 or weighted_precision <= 0:
        return None, None
    return weighted_mean / weighted_precision, 1.0 / weighted_precision


def _weighted_source_values(
    sources: Mapping[str, SourceEvidence],
    omegas: Mapping[str, float],
    attr: str,
) -> list[tuple[float, float]]:
    values: list[tuple[float, float]] = []
    for name, source in sources.items():
        value = _safe_float(getattr(source, attr, None))
        omega = _safe_float(omegas.get(name))
        if value is None or omega is None:
            continue
        values.append((float(value), float(omega)))
    return values


def _weighted_disagreement(values: list[tuple[float, float]]) -> float:
    if len(values) < 2:
        return 0.0
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return 0.0
    mean = sum(value * weight for value, weight in values) / total_weight
    variance = sum(weight * ((value - mean) ** 2) for value, weight in values) / total_weight
    return float(_clamp(math.sqrt(max(0.0, variance)) * 2.0, 0.0, 1.0))


def _mean_component(sources: Mapping[str, SourceEvidence], attr: str, default: float) -> float:
    values = [_component(source, attr, default) for source in sources.values()]
    if not values:
        return default
    return sum(values) / len(values)


def _max_component(sources: Mapping[str, SourceEvidence], attr: str, default: float) -> float:
    values = [_component(source, attr, default) for source in sources.values()]
    if not values:
        return default
    return max(values)


def _uncertainty(
    *,
    sources: Mapping[str, SourceEvidence],
    intensity_variance: float | None,
    growth_variance: float | None,
    intensity_disagreement: float,
    growth_disagreement: float,
    lead_lag_uncertainty: float | None,
) -> float | None:
    variances = [value for value in (intensity_variance, growth_variance) if value is not None]
    if not variances:
        return None

    posterior_sd = math.sqrt(sum(variances) / len(variances))
    disagreement = max(intensity_disagreement, growth_disagreement)
    coverage_penalty = 1.0 - _mean_component(sources, "coverage", 0.6)
    drift_penalty = _max_component(sources, "drift", 0.0)
    single_source_penalty = 0.12 if len(sources) == 1 else 0.0
    lead_lag_penalty = float(_clamp(lead_lag_uncertainty, 0.0, 1.0) or 0.0)

    uncertainty = (
        posterior_sd * 2.0
        + 0.28 * disagreement
        + 0.12 * coverage_penalty
        + 0.18 * drift_penalty
        + 0.12 * lead_lag_penalty
        + single_source_penalty
    )
    return round(float(_clamp(uncertainty)), 6)


def classify_wave_phase(
    *,
    intensity_mean: float | None,
    growth_mean: float | None,
) -> WavePhase:
    if intensity_mean is None and growth_mean is None:
        return "unknown"

    growth = growth_mean or 0.0
    intensity = intensity_mean or 0.0
    if intensity >= 0.60 and growth <= -0.07:
        return "decline"
    if growth >= 0.18:
        return "acceleration"
    if intensity >= 0.78 and abs(growth) <= 0.07:
        return "peak"
    if intensity >= 0.40 and growth >= 0.05:
        return "early_growth"
    if growth <= -0.07:
        return "decline"
    return "baseline"


def fuse_latent_wave_state(
    sources: Mapping[str, SourceEvidence],
    weights: Mapping[str, float | None],
    *,
    lead_lag_uncertainty: float | None = None,
) -> LatentWaveState:
    """Fuse epidemiological source evidence into a posterior-like wave state."""
    del weights  # v1 recomputes source precision from raw quality components.
    epi_sources = _epidemiological_sources(sources)
    if not epi_sources:
        return LatentWaveState()

    qualities = {
        name: quality
        for name, source in epi_sources.items()
        if (quality := _quality(source)) is not None
    }
    if not qualities:
        return LatentWaveState()

    omegas = _softmax(qualities)
    intensity, intensity_variance = _posterior_dimension(
        epi_sources,
        omegas,
        "intensity",
        prior_mean=0.35,
        prior_variance=0.25,
    )
    growth, growth_variance = _posterior_dimension(
        epi_sources,
        omegas,
        "growth",
        prior_mean=0.0,
        prior_variance=0.20,
    )

    intensity_values = _weighted_source_values(epi_sources, omegas, "intensity")
    growth_values = _weighted_source_values(epi_sources, omegas, "growth")
    uncertainty = _uncertainty(
        sources=epi_sources,
        intensity_variance=intensity_variance,
        growth_variance=growth_variance,
        intensity_disagreement=_weighted_disagreement(intensity_values),
        growth_disagreement=_weighted_disagreement(growth_values),
        lead_lag_uncertainty=lead_lag_uncertainty,
    )

    intensity_p10 = None
    intensity_p90 = None
    if intensity is not None and intensity_variance is not None:
        inflation = 1.0 + float(uncertainty or 0.0)
        sd = math.sqrt(max(0.0, intensity_variance)) * inflation
        intensity_p10 = _clamp(float(intensity) - _NORMAL_Z_10_90 * sd)
        intensity_p90 = _clamp(float(intensity) + _NORMAL_Z_10_90 * sd)

    return LatentWaveState(
        intensity_mean=round(float(intensity), 6) if intensity is not None else None,
        intensity_p10=round(float(intensity_p10), 6) if intensity_p10 is not None else None,
        intensity_p90=round(float(intensity_p90), 6) if intensity_p90 is not None else None,
        growth_mean=round(float(growth), 6) if growth is not None else None,
        uncertainty=uncertainty,
        wave_phase=classify_wave_phase(intensity_mean=intensity, growth_mean=growth),
    )


def early_warning_score(
    *,
    event_probability: float | None,
    growth_mean: float | None,
    intensity_mean: float | None,
    epi_quality: float | None,
) -> float | None:
    del event_probability  # v1 derives warning attention from fused latent state.
    proxy_parts = [
        value
        for value in (growth_mean, intensity_mean)
        if value is not None
    ]
    if not proxy_parts or epi_quality is None:
        return None

    p_wave_proxy = max(0.0, min(1.0, max(proxy_parts)))
    return round(100.0 * p_wave_proxy * max(0.0, min(1.0, epi_quality)), 2)


def commercial_relevance_score(*, sales_signal: float | None, sales_quality: float | None) -> float | None:
    if sales_signal is None or sales_quality is None:
        return None
    return round(100.0 * max(0.0, min(1.0, sales_signal)) * max(0.0, min(1.0, sales_quality)), 2)
