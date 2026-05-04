"""Validation metrics for phase-lead forecast experiments."""

from __future__ import annotations

import numpy as np


def brier_score(probabilities: np.ndarray, events: np.ndarray) -> float:
    probabilities = np.asarray(probabilities, dtype=float)
    events = np.asarray(events, dtype=float)
    if probabilities.shape != events.shape:
        raise ValueError("probabilities and events must have matching shapes")
    return float(np.mean((probabilities - events) ** 2))


def top_k_recall(scores: np.ndarray, realized_events: np.ndarray, k: int) -> float:
    scores = np.asarray(scores, dtype=float)
    realized_events = np.asarray(realized_events, dtype=bool)
    if scores.ndim != 1 or realized_events.ndim != 1 or scores.shape != realized_events.shape:
        raise ValueError("scores and realized_events must be one-dimensional arrays with matching shapes")
    if k <= 0:
        raise ValueError("k must be positive")
    true_count = int(realized_events.sum())
    if true_count == 0:
        return 0.0
    top = np.argsort(-scores)[: min(k, scores.size)]
    return float(realized_events[top].sum() / min(k, true_count))


def crps_from_samples(samples: np.ndarray, observed: np.ndarray) -> float:
    samples = np.asarray(samples, dtype=float)
    observed = np.asarray(observed, dtype=float)
    if samples.shape[1:] != observed.shape:
        raise ValueError("samples must have shape (draws, ...) matching observed")
    term1 = np.mean(np.abs(samples - observed[None, ...]))
    pairwise = np.abs(samples[:, None, ...] - samples[None, :, ...])
    term2 = 0.5 * np.mean(pairwise)
    return float(term1 - term2)
