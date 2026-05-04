"""Delayed-convolution observation engine."""

from __future__ import annotations

import numpy as np

from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.mappings import SourceMapping


def incidence_from_x(x: np.ndarray, epsilon: float) -> np.ndarray:
    return np.clip(np.exp(np.asarray(x, dtype=float)) - float(epsilon), 0.0, None)


def _log_alpha_for_date(log_alpha: float | np.ndarray, date_index: int, units: int) -> np.ndarray:
    alpha = np.asarray(log_alpha, dtype=float)
    if alpha.ndim == 0:
        return np.full(units, float(alpha))
    if alpha.ndim == 1:
        if alpha.shape[0] != units:
            raise ValueError("one-dimensional log_alpha must have one value per observation unit")
        return alpha
    if alpha.ndim == 2:
        if alpha.shape[0] != units:
            raise ValueError("two-dimensional log_alpha must have shape (observation_units, dates)")
        return alpha[:, date_index]
    raise ValueError("log_alpha must be scalar, (observation_units,), or (observation_units, dates)")


def compute_mu(
    *,
    x_window: np.ndarray,
    source_mapping: SourceMapping,
    kernel: ObservationKernel,
    log_alpha: float | np.ndarray,
    pathogen_index: int,
    epsilon: float,
    missing_history: str = "pad_earliest",
) -> np.ndarray:
    """Compute mu[observation_unit, date] via delayed convolution.

    Default missing-history behavior pads with the earliest available latent
    value. That default is explicit because real fits must know how pre-window
    infection history is handled.
    """

    x_window = np.asarray(x_window, dtype=float)
    if x_window.ndim != 3:
        raise ValueError("x_window must have shape (dates, regions, pathogens)")
    if pathogen_index < 0 or pathogen_index >= x_window.shape[2]:
        raise ValueError("pathogen_index is out of bounds")
    if missing_history != "pad_earliest":
        raise ValueError("Only missing_history='pad_earliest' is implemented in the MVP")

    dates = x_window.shape[0]
    units = len(source_mapping.observation_units)
    mu = np.zeros((units, dates), dtype=float)
    weights = kernel.values()
    for t_idx in range(dates):
        latent_conv = np.zeros(len(source_mapping.latent_regions), dtype=float)
        for age, weight in enumerate(weights):
            lag_idx = max(0, t_idx - age)
            latent_conv += float(weight) * incidence_from_x(
                x_window[lag_idx, :, pathogen_index],
                epsilon=epsilon,
            )
        mapped = source_mapping.apply(latent_conv)
        mu[:, t_idx] = np.exp(_log_alpha_for_date(log_alpha, t_idx, units)) * mapped
    return np.clip(mu, 1.0e-12, None)
