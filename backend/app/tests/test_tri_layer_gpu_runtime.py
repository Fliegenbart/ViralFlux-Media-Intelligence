from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.services.research.tri_layer.gpu_runtime import resolve_tri_layer_xgboost_config


def test_tri_layer_cpu_default_does_not_set_device() -> None:
    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cpu"}, clear=False):
        resolved = resolve_tri_layer_xgboost_config({"n_estimators": 25})

    assert resolved["n_estimators"] == 25
    assert "device" not in resolved
    assert "tree_method" not in resolved


def test_tri_layer_cuda_sets_device_and_hist_tree_method() -> None:
    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
        resolved = resolve_tri_layer_xgboost_config({"n_estimators": 25})

    assert resolved["device"] == "cuda"
    assert resolved["tree_method"] == "hist"


def test_tri_layer_cuda_index_is_accepted() -> None:
    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda:1"}, clear=False):
        resolved = resolve_tri_layer_xgboost_config({"n_estimators": 25})

    assert resolved["device"] == "cuda:1"
    assert resolved["tree_method"] == "hist"


def test_tri_layer_invalid_device_fails_with_clear_value_error() -> None:
    with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda-fast"}, clear=False):
        with pytest.raises(ValueError, match="REGIONAL_XGBOOST_DEVICE"):
            resolve_tri_layer_xgboost_config({"n_estimators": 25})
