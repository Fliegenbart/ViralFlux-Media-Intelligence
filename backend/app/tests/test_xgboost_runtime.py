from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.services.ml.regional_trainer_modeling import fit_classifier, fit_regressor
from app.services.ml.xgboost_runtime import resolve_xgboost_runtime_config


class _FakeModel:
    def __init__(self, **kwargs) -> None:
        self.kwargs = dict(kwargs)
        self.fit_calls: list[tuple[object, object, dict[str, object]]] = []

    def fit(self, X, y, **kwargs) -> None:
        self.fit_calls.append((X, y, dict(kwargs)))


class XGBoostRuntimeTests(unittest.TestCase):
    def test_resolve_runtime_defaults_to_cpu(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            resolved = resolve_xgboost_runtime_config({"n_estimators": 120})

        self.assertEqual(resolved["n_estimators"], 120)
        self.assertNotIn("device", resolved)
        self.assertNotIn("tree_method", resolved)

    def test_resolve_runtime_enables_cuda_when_requested(self) -> None:
        with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
            resolved = resolve_xgboost_runtime_config({"n_estimators": 120})

        self.assertEqual(resolved["n_estimators"], 120)
        self.assertEqual(resolved["device"], "cuda")
        self.assertEqual(resolved["tree_method"], "hist")

    def test_fit_classifier_applies_runtime_config(self) -> None:
        with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
            model = fit_classifier(
                X=[[1.0], [2.0], [3.0], [4.0]],
                y=[0, 1, 0, 1],
                classifier_cls=_FakeModel,
                classifier_config={"n_estimators": 80},
            )

        self.assertEqual(model.kwargs["n_estimators"], 80)
        self.assertEqual(model.kwargs["device"], "cuda")
        self.assertEqual(model.kwargs["tree_method"], "hist")
        self.assertEqual(model.kwargs["scale_pos_weight"], 1.0)

    def test_fit_regressor_applies_runtime_config(self) -> None:
        with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
            model = fit_regressor(
                X=[[1.0], [2.0], [3.0], [4.0]],
                y=[1.0, 2.0, 3.0, 4.0],
                config={"n_estimators": 60},
                regressor_cls=_FakeModel,
            )

        self.assertEqual(model.kwargs["n_estimators"], 60)
        self.assertEqual(model.kwargs["device"], "cuda")
        self.assertEqual(model.kwargs["tree_method"], "hist")


if __name__ == "__main__":
    unittest.main()
