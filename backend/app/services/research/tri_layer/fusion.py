"""Deterministic v0 latent-state fusion for TLEF-BICG."""

from __future__ import annotations

import math
from typing import Mapping

from app.services.research.tri_layer.evidence_weights import evidence_quality
from app.services.research.tri_layer.schema import LatentWaveState, SourceEvidence, WavePhase


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _weighted_mean(
    sources: Mapping[str, SourceEvidence],
    weights: Mapping[str, float | None],
    attr: str,
) -> float | None:
    total = 0.0
    weight_total = 0.0
    for name, source in sources.items():
        weight = weights.get(name)
        value = _safe_float(getattr(source, attr, None))
        if weight is None or value is None:
            continue
        total += float(weight) * value
        weight_total += float(weight)
    if weight_total <= 0:
        return None
    return round(total / weight_total, 6)


def classify_wave_phase(*, intensity_mean: float | None, growth_mean: float | None) -> WavePhase:
    if intensity_mean is None and growth_mean is None:
        return "unknown"
    growth = growth_mean or 0.0
    intensity = intensity_mean or 0.0
    if growth >= 0.20:
        return "acceleration"
    if growth >= 0.07:
        return "early_growth"
    if growth <= -0.07:
        return "decline"
    if intensity >= 0.78:
        return "peak"
    return "baseline"


def fuse_latent_wave_state(
    sources: Mapping[str, SourceEvidence],
    weights: Mapping[str, float | None],
) -> LatentWaveState:
    intensity = _weighted_mean(sources, weights, "intensity")
    growth = _weighted_mean(sources, weights, "growth")
    qualities = [
        evidence_quality(source)
        for source in sources.values()
        if source.status != "not_connected"
    ]
    quality_mean = sum(q for q in qualities if q is not None) / len(qualities) if qualities else None
    uncertainty = round(max(0.0, min(1.0, 1.0 - quality_mean)), 6) if quality_mean is not None else None
    return LatentWaveState(
        intensity_mean=intensity,
        growth_mean=growth,
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
    proxy_parts = [
        value
        for value in (event_probability, growth_mean, intensity_mean)
        if value is not None
    ]
    if not proxy_parts or epi_quality is None:
        return None
    # A strong leading source should be allowed to raise warning attention,
    # while budget permission remains governed by the separate gates.
    p_wave_proxy = max(0.0, min(1.0, max(proxy_parts)))
    return round(100.0 * p_wave_proxy * max(0.0, min(1.0, epi_quality)), 2)


def commercial_relevance_score(*, sales_signal: float | None, sales_quality: float | None) -> float | None:
    if sales_signal is None or sales_quality is None:
        return None
    return round(100.0 * max(0.0, min(1.0, sales_signal)) * max(0.0, min(1.0, sales_quality)), 2)
