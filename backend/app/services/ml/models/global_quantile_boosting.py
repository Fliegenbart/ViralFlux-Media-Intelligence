from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from xgboost import XGBRegressor

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.benchmarking.metrics import monotone_quantiles


@dataclass
class GlobalQuantileBoostingModel:
    quantiles: tuple[float, ...] = CANONICAL_FORECAST_QUANTILES
    config: dict[str, Any] = field(default_factory=lambda: {
        "n_estimators": 160,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "objective": "reg:quantileerror",
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    })
    models: dict[float, XGBRegressor] = field(default_factory=dict)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GlobalQuantileBoostingModel":
        self.models = {}
        for quantile in self.quantiles:
            model_config = dict(self.config)
            model_config["quantile_alpha"] = float(quantile)
            model = XGBRegressor(**model_config)
            model.fit(X, y)
            self.models[float(quantile)] = model
        return self

    def predict_quantiles(self, X: np.ndarray) -> dict[float, np.ndarray]:
        if not self.models:
            raise ValueError("GlobalQuantileBoostingModel must be fit before predict_quantiles().")
        predictions = {
            quantile: np.expm1(model.predict(X))
            for quantile, model in self.models.items()
        }
        return monotone_quantiles(predictions)

    def metadata(self) -> dict[str, Any]:
        return {
            "model_family": "global_quantile_boosting",
            "quantiles": [float(value) for value in self.quantiles],
        }
