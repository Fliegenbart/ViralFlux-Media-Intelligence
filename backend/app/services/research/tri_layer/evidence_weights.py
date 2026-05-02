"""Evidence quality and source weighting for TLEF-BICG v0."""

from __future__ import annotations

import math
from typing import Mapping

from app.services.research.tri_layer.schema import SourceEvidence

SOURCE_NAMES = ("wastewater", "clinical", "sales")


def _clamp01(value: float | None, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


def evidence_quality(source: SourceEvidence) -> float | None:
    """Compute the transparent v0 quality score Q_m.

    The formula mirrors the requested components. Missing connected-source
    diagnostics fall back to conservative neutral values; not-connected
    sources are excluded by returning ``None``.
    """
    if source.status == "not_connected":
        return None

    neutral_connected = 0.6 if source.status == "connected" else 0.45
    freshness = _clamp01(source.freshness, neutral_connected)
    reliability = _clamp01(source.reliability, 0.6)
    baseline_stability = _clamp01(source.baseline_stability, neutral_connected)
    snr = _clamp01(source.snr, neutral_connected)
    consistency = _clamp01(source.consistency, neutral_connected)
    drift = _clamp01(source.drift, 0.0)
    coverage = _clamp01(source.coverage, 0.6 if source.status == "connected" else 0.35)

    quality = (
        0.18 * freshness
        + 0.20 * reliability
        + 0.12 * baseline_stability
        + 0.14 * snr
        + 0.14 * consistency
        - 0.22 * drift
        + 0.20 * coverage
    )
    return round(max(-1.0, min(1.0, quality)), 6)


def normalize_evidence_weights(sources: Mapping[str, SourceEvidence]) -> dict[str, float | None]:
    """Softmax-normalise connected evidence sources."""
    qualities = {
        name: evidence_quality(sources.get(name, SourceEvidence()))
        for name in SOURCE_NAMES
    }
    connected = {name: value for name, value in qualities.items() if value is not None}
    if not connected:
        return {name: None for name in SOURCE_NAMES}

    max_q = max(connected.values())
    exp_values = {name: math.exp(float(value) - max_q) for name, value in connected.items()}
    denom = sum(exp_values.values())
    weights: dict[str, float | None] = {name: None for name in SOURCE_NAMES}
    for name, value in exp_values.items():
        weights[name] = round(value / denom, 6) if denom > 0 else None
    return weights
