from __future__ import annotations

from typing import Any

import numpy as np

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.benchmarking.metrics import monotone_quantiles


class ProbabilisticEnsemble:
    """Simple equal-weight and WIS-weighted probabilistic ensemble."""

    @staticmethod
    def equal_weight(
        component_predictions: dict[str, dict[float, np.ndarray]],
    ) -> dict[float, np.ndarray]:
        if not component_predictions:
            return {}
        quantiles = sorted(next(iter(component_predictions.values())).keys())
        result: dict[float, np.ndarray] = {}
        for quantile in quantiles:
            members = [prediction[quantile] for prediction in component_predictions.values() if quantile in prediction]
            result[quantile] = np.mean(np.vstack(members), axis=0)
        return monotone_quantiles(result)

    @staticmethod
    def performance_weighted(
        component_predictions: dict[str, dict[float, np.ndarray]],
        *,
        component_scores: dict[str, float] | None = None,
    ) -> tuple[dict[float, np.ndarray], dict[str, float]]:
        if not component_predictions:
            return {}, {}

        scores = component_scores or {}
        weights: dict[str, float] = {}
        raw_weights = []
        names = []
        for name in component_predictions:
            wis = max(float(scores.get(name, 1.0)), 1e-6)
            weight = 1.0 / wis
            names.append(name)
            raw_weights.append(weight)
        weight_arr = np.asarray(raw_weights, dtype=float)
        weight_arr = weight_arr / max(float(np.sum(weight_arr)), 1e-9)
        weights = {name: round(float(weight), 6) for name, weight in zip(names, weight_arr, strict=False)}

        quantiles = sorted(next(iter(component_predictions.values())).keys())
        result: dict[float, np.ndarray] = {}
        for quantile in quantiles:
            members = np.vstack([component_predictions[name][quantile] for name in names if quantile in component_predictions[name]])
            result[quantile] = np.average(members, axis=0, weights=weight_arr[: len(members)])
        return monotone_quantiles(result), weights
