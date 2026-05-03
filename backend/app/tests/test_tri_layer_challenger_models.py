from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.services.research.tri_layer.challenger_models import (
    fit_tri_layer_challenger_models,
    resolve_tri_layer_challenger_xgboost_params,
)


class _TrackingModel:
    instances: list["_TrackingModel"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.fit_kwargs: dict = {}
        _TrackingModel.instances.append(self)

    def fit(self, X, y, **kwargs):
        self.X = X
        self.y = y
        self.fit_kwargs = kwargs
        return self

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


def _cutoff_results() -> list[dict]:
    return [
        {
            "cutoff_date": "2024-10-01",
            "region_code": "HH",
            "early_warning_score": 82.0,
            "wave_phase": "early_growth",
            "observed_onset": True,
            "observed_phase": "early_growth",
            "model_predictions": {
                "clinical_only": {"onset_probability": 0.72},
                "wastewater_only": {"onset_probability": 0.84},
                "wastewater_plus_clinical": {"onset_probability": 0.86},
                "forecast_proxy_only": {"onset_probability": 0.70},
                "tri_layer_epi_no_sales": {"onset_probability": 0.88},
            },
        },
        {
            "cutoff_date": "2024-10-01",
            "region_code": "BE",
            "early_warning_score": 18.0,
            "wave_phase": "baseline",
            "observed_onset": False,
            "observed_phase": "baseline",
            "model_predictions": {
                "clinical_only": {"onset_probability": 0.18},
                "wastewater_only": {"onset_probability": 0.12},
                "wastewater_plus_clinical": {"onset_probability": 0.15},
                "forecast_proxy_only": {"onset_probability": 0.20},
                "tri_layer_epi_no_sales": {"onset_probability": 0.16},
            },
        },
        {
            "cutoff_date": "2024-10-08",
            "region_code": "HH",
            "early_warning_score": 76.0,
            "wave_phase": "peak",
            "observed_onset": True,
            "observed_phase": "peak",
            "model_predictions": {
                "clinical_only": {"onset_probability": 0.70},
                "wastewater_only": {"onset_probability": 0.79},
                "wastewater_plus_clinical": {"onset_probability": 0.81},
                "forecast_proxy_only": {"onset_probability": 0.66},
                "tri_layer_epi_no_sales": {"onset_probability": 0.83},
            },
        },
        {
            "cutoff_date": "2024-10-08",
            "region_code": "BE",
            "early_warning_score": 12.0,
            "wave_phase": "baseline",
            "observed_onset": False,
            "observed_phase": "baseline",
            "model_predictions": {
                "clinical_only": {"onset_probability": 0.16},
                "wastewater_only": {"onset_probability": 0.10},
                "wastewater_plus_clinical": {"onset_probability": 0.12},
                "forecast_proxy_only": {"onset_probability": 0.19},
                "tri_layer_epi_no_sales": {"onset_probability": 0.14},
            },
        },
    ]


def test_tri_layer_challenger_cpu_config_trains_without_device() -> None:
    _TrackingModel.reset()

    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cpu"}, clear=False):
        result = fit_tri_layer_challenger_models(
            _cutoff_results(),
            classifier_cls=_TrackingModel,
            ranker_cls=_TrackingModel,
            min_samples=4,
        )

    assert result["status"] == "trained"
    assert result["runtime"]["device"] == "cpu"
    assert "onset_classifier" in result["models"]
    assert "phase_classifier" in result["models"]
    assert "regional_ranker" in result["models"]
    assert "source_ablation_classifiers" in result["models"]
    assert _TrackingModel.instances
    assert all("device" not in model.kwargs for model in _TrackingModel.instances)
    assert all("tree_method" not in model.kwargs for model in _TrackingModel.instances)


def test_tri_layer_challenger_cuda_config_creates_xgboost_params() -> None:
    _TrackingModel.reset()

    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
        params = resolve_tri_layer_challenger_xgboost_params({"n_estimators": 12})
        result = fit_tri_layer_challenger_models(
            _cutoff_results(),
            classifier_cls=_TrackingModel,
            ranker_cls=_TrackingModel,
            min_samples=4,
        )

    assert params["device"] == "cuda"
    assert params["tree_method"] == "hist"
    assert result["runtime"]["device"] == "cuda"
    assert _TrackingModel.instances
    assert all(model.kwargs["device"] == "cuda" for model in _TrackingModel.instances)
    assert all(model.kwargs["tree_method"] == "hist" for model in _TrackingModel.instances)


def test_tri_layer_challenger_invalid_device_raises_clear_error() -> None:
    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda-fast"}, clear=False):
        with pytest.raises(ValueError, match="REGIONAL_XGBOOST_DEVICE"):
            resolve_tri_layer_challenger_xgboost_params({"n_estimators": 12})
