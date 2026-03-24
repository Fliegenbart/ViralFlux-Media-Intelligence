from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.benchmarking.metrics import monotone_quantiles


_PROVIDER_IMPORT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "timesfm": ("timesfm",),
    "chronos": ("chronos", "chronos_forecasting"),
}


@dataclass
class TSFMAdapter:
    provider: str = "disabled"
    enabled: bool = False
    available: bool = False
    reason: str = "feature_flag_disabled"
    module_name: str | None = None
    probabilistic: bool = True

    @classmethod
    def from_settings(cls, *, enabled: bool = False, provider: str = "timesfm") -> "TSFMAdapter":
        provider_name = str(provider or "timesfm").strip().lower()
        if not enabled:
            return cls(provider=provider_name, enabled=False, available=False, reason="feature_flag_disabled")

        for module_name in _PROVIDER_IMPORT_CANDIDATES.get(provider_name, (provider_name,)):
            try:
                importlib.import_module(module_name)
                return cls(
                    provider=provider_name,
                    enabled=True,
                    available=True,
                    reason="import_ok",
                    module_name=module_name,
                    probabilistic=True,
                )
            except Exception:
                continue

        return cls(
            provider=provider_name,
            enabled=True,
            available=False,
            reason="import_failed",
            module_name=None,
            probabilistic=True,
        )

    def _load_module(self):
        if not self.available or not self.module_name:
            raise RuntimeError(f"TSFM provider {self.provider} is unavailable: {self.reason}")
        return importlib.import_module(self.module_name)

    def predict_quantiles(
        self,
        *,
        history: np.ndarray | list[float],
        horizon: int,
        quantiles: tuple[float, ...] = CANONICAL_FORECAST_QUANTILES,
    ) -> dict[float, np.ndarray]:
        if horizon <= 0:
            raise ValueError("horizon must be positive for TSFM forecasting.")

        series = np.asarray(history, dtype=float).reshape(-1)
        if series.size == 0:
            raise ValueError("history must contain at least one value for TSFM forecasting.")

        module = self._load_module()
        provider = self.provider.lower()
        if provider == "timesfm":
            return self._predict_timesfm(module=module, history=series, horizon=horizon, quantiles=quantiles)
        if provider == "chronos":
            return self._predict_chronos(module=module, history=series, horizon=horizon, quantiles=quantiles)
        raise RuntimeError(f"Unsupported TSFM provider: {self.provider}")

    def _predict_timesfm(
        self,
        *,
        module: Any,
        history: np.ndarray,
        horizon: int,
        quantiles: tuple[float, ...],
    ) -> dict[float, np.ndarray]:
        client_cls = getattr(module, "TimesFm", None) or getattr(module, "TimesFM", None)
        if client_cls is None:
            raise RuntimeError("timesfm package is installed but exposes no supported TimesFm client.")

        errors: list[str] = []
        client = None
        for kwargs in (
            {"context_len": int(max(len(history), horizon)), "horizon_len": int(horizon)},
            {"horizon_len": int(horizon)},
            {},
        ):
            try:
                client = client_cls(**kwargs)
                break
            except Exception as exc:
                errors.append(exc.__class__.__name__)
        if client is None:
            raise RuntimeError(f"Could not initialize TimesFM client: {', '.join(errors) or 'unknown_error'}")

        if hasattr(client, "forecast_quantiles"):
            forecast = client.forecast_quantiles(
                inputs=[history.astype(float).tolist()],
                horizon=int(horizon),
                quantiles=[float(value) for value in quantiles],
            )
        elif hasattr(client, "forecast"):
            forecast = client.forecast(
                inputs=[history.astype(float).tolist()],
                horizon=int(horizon),
                quantiles=[float(value) for value in quantiles],
            )
        else:
            raise RuntimeError("TimesFM client exposes no supported forecast method.")
        return self._normalize_provider_forecast(forecast, quantiles=quantiles, horizon=horizon)

    def _predict_chronos(
        self,
        *,
        module: Any,
        history: np.ndarray,
        horizon: int,
        quantiles: tuple[float, ...],
    ) -> dict[float, np.ndarray]:
        pipeline_cls = getattr(module, "ChronosPipeline", None) or getattr(module, "Pipeline", None)
        if pipeline_cls is None:
            raise RuntimeError("chronos package is installed but exposes no supported pipeline class.")

        if hasattr(pipeline_cls, "from_pretrained"):
            pipeline = pipeline_cls.from_pretrained("amazon/chronos-t5-small")
        else:
            pipeline = pipeline_cls()

        if hasattr(pipeline, "predict_quantiles"):
            forecast = pipeline.predict_quantiles(
                context=history.astype(float),
                prediction_length=int(horizon),
                quantile_levels=[float(value) for value in quantiles],
            )
        elif hasattr(pipeline, "predict"):
            forecast = pipeline.predict(
                context=history.astype(float),
                prediction_length=int(horizon),
                quantile_levels=[float(value) for value in quantiles],
            )
        else:
            raise RuntimeError("Chronos pipeline exposes no supported prediction method.")
        return self._normalize_provider_forecast(forecast, quantiles=quantiles, horizon=horizon)

    @staticmethod
    def _normalize_provider_forecast(
        forecast: Any,
        *,
        quantiles: tuple[float, ...],
        horizon: int,
    ) -> dict[float, np.ndarray]:
        if isinstance(forecast, dict):
            quantile_map: dict[float, np.ndarray] = {}
            for quantile in quantiles:
                value = None
                for key in (quantile, str(quantile), f"q_{quantile:g}", f"quantile_{quantile:g}"):
                    if key in forecast:
                        value = forecast[key]
                        break
                if value is None:
                    continue
                arr = np.asarray(value, dtype=float).reshape(-1)
                quantile_map[float(quantile)] = arr[:horizon]
            if quantile_map:
                return monotone_quantiles(quantile_map)

        array = np.asarray(forecast, dtype=float)
        if array.ndim == 3 and array.shape[0] == 1:
            array = array[0]
        if array.ndim != 2:
            raise RuntimeError("TSFM forecast output could not be normalized into quantile trajectories.")
        if array.shape[0] == len(quantiles):
            quantile_map = {
                float(quantile): np.asarray(array[idx], dtype=float).reshape(-1)[:horizon]
                for idx, quantile in enumerate(quantiles)
            }
            return monotone_quantiles(quantile_map)
        if array.shape[1] == len(quantiles):
            quantile_map = {
                float(quantile): np.asarray(array[:, idx], dtype=float).reshape(-1)[:horizon]
                for idx, quantile in enumerate(quantiles)
            }
            return monotone_quantiles(quantile_map)
        raise RuntimeError("TSFM forecast output has an unsupported shape.")

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "available": self.available,
            "reason": self.reason,
            "module_name": self.module_name,
            "probabilistic": self.probabilistic,
            "challenger_mode": "zero_shot_quantile",
        }
