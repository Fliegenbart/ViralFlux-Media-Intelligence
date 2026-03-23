from __future__ import annotations

from typing import Sequence

import numpy as np

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES


def persistence_quantiles(
    *,
    current_values: Sequence[float],
    residual_scale: float | Sequence[float] = 1.0,
) -> dict[float, np.ndarray]:
    current_arr = np.asarray(current_values, dtype=float)
    scale_arr = np.asarray(residual_scale, dtype=float)
    if scale_arr.ndim == 0:
        scale_arr = np.full(len(current_arr), float(scale_arr), dtype=float)

    z_map = {
        0.025: -1.959964,
        0.1: -1.281552,
        0.25: -0.67449,
        0.5: 0.0,
        0.75: 0.67449,
        0.9: 1.281552,
        0.975: 1.959964,
    }
    return {
        quantile: np.maximum(current_arr + z_map[quantile] * scale_arr, 0.0)
        for quantile in CANONICAL_FORECAST_QUANTILES
    }


def seasonal_quantiles(
    *,
    seasonal_baseline: Sequence[float],
    seasonal_scale: float | Sequence[float] = 1.0,
) -> dict[float, np.ndarray]:
    return persistence_quantiles(
        current_values=seasonal_baseline,
        residual_scale=seasonal_scale,
    )
