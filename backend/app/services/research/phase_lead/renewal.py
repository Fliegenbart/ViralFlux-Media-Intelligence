"""Renewal-process helpers for fit penalties and forward simulation."""

from __future__ import annotations

import numpy as np
from scipy.special import logsumexp

from app.services.research.phase_lead.graph import RegionalGraph


def normalize_distribution(values: list[float] | np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional distribution")
    if np.any(arr < 0.0) or not np.isfinite(arr).all():
        raise ValueError(f"{name} must contain finite non-negative values")
    total = float(arr.sum())
    if total <= 0.0:
        raise ValueError(f"{name} must contain positive mass")
    return arr / total


def derive_q_c(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    q = np.zeros_like(x)
    c = np.zeros_like(x)
    q[1:] = x[1:] - x[:-1]
    c[2:] = q[2:] - q[1:-1]
    return q, c


def phase_log_r(q: np.ndarray, c: np.ndarray, generation_interval: np.ndarray) -> np.ndarray:
    g = normalize_distribution(generation_interval, "generation_interval")
    s = np.arange(1, g.size + 1, dtype=float)
    log_g = np.log(g)
    flat_q = np.asarray(q, dtype=float).ravel()
    flat_c = np.asarray(c, dtype=float).ravel()
    out = np.empty_like(flat_q)
    for idx, (q_value, c_value) in enumerate(zip(flat_q, flat_c)):
        terms = log_g - s * q_value + 0.5 * s * (s - 1.0) * c_value
        out[idx] = -float(logsumexp(terms))
    return out.reshape(np.asarray(q).shape)


def renewal_mean_next(
    n_history: np.ndarray,
    *,
    graph: RegionalGraph,
    generation_interval: np.ndarray,
    eta_import: float,
    reproduction: np.ndarray,
) -> np.ndarray:
    """Compute renewal mean for the next day.

    `n_history` has shape (dates, regions, pathogens), with the final row being
    the most recent available day.
    """

    n_history = np.asarray(n_history, dtype=float)
    g = normalize_distribution(generation_interval, "generation_interval")
    regions = n_history.shape[1]
    pathogens = n_history.shape[2]
    force = np.zeros((regions, pathogens), dtype=float)
    for lag, weight in enumerate(g, start=1):
        lag_idx = max(0, n_history.shape[0] - lag)
        local = n_history[lag_idx]
        imported = graph.T.T @ local
        force += float(weight) * ((1.0 - eta_import) * local + eta_import * imported)
    return np.clip(np.asarray(reproduction, dtype=float) * force, 1.0e-12, None)
