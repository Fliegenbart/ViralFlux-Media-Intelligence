from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.benchmarking.metrics import monotone_quantiles


@dataclass
class StateSpaceProbabilisticBaseline:
    residual_scale: float = 1.0
    last_value: float = 0.0
    recent_trend: float = 0.0

    def fit(self, history: np.ndarray) -> "StateSpaceProbabilisticBaseline":
        values = np.asarray(history, dtype=float)
        if len(values) == 0:
            self.last_value = 0.0
            self.recent_trend = 0.0
            self.residual_scale = 1.0
            return self
        self.last_value = float(values[-1])
        if len(values) >= 2:
            self.recent_trend = float(values[-1] - values[-2])
        residuals = np.diff(values) if len(values) >= 2 else np.asarray([1.0], dtype=float)
        self.residual_scale = float(np.std(residuals)) if len(residuals) >= 2 else max(abs(self.recent_trend), 1.0)
        self.residual_scale = max(self.residual_scale, 1.0)
        return self

    def predict_quantiles(self, n_rows: int = 1) -> dict[float, np.ndarray]:
        center = np.full(int(n_rows), max(self.last_value + self.recent_trend, 0.0), dtype=float)
        z_map = {
            0.025: -1.959964,
            0.1: -1.281552,
            0.25: -0.67449,
            0.5: 0.0,
            0.75: 0.67449,
            0.9: 1.281552,
            0.975: 1.959964,
        }
        return monotone_quantiles(
            {
                quantile: np.maximum(center + z_map[quantile] * self.residual_scale, 0.0)
                for quantile in CANONICAL_FORECAST_QUANTILES
            }
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "model_family": "state_space_baseline",
            "residual_scale": round(float(self.residual_scale), 6),
        }
