from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.services.ml import backtester_walk_forward, forecast_service_direct_training
from app.services.ml.regional_trainer_modeling import fit_classifier, fit_regressor
from app.services.ml.xgboost_runtime import resolve_xgboost_runtime_config


class _FakeModel:
    def __init__(self, **kwargs) -> None:
        self.kwargs = dict(kwargs)
        self.fit_calls: list[tuple[object, object, dict[str, object]]] = []

    def fit(self, X, y, **kwargs) -> None:
        self.fit_calls.append((X, y, dict(kwargs)))


class _TrackingFakeModel(_FakeModel):
    instances: list["_TrackingFakeModel"] = []

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.feature_importances_ = np.array([1.0], dtype=float)
        self.__class__.instances.append(self)

    def predict(self, X):
        return np.ones(len(X), dtype=float)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []


class _ForecastServiceStub:
    @staticmethod
    def _resolve_xgb_quantile_config(model_config):
        return {
            "median": dict((model_config or {}).get("median") or {"n_estimators": 10}),
            "lower": dict((model_config or {}).get("lower") or {"n_estimators": 10}),
            "upper": dict((model_config or {}).get("upper") or {"n_estimators": 10}),
        }


class _BacktestServiceStub:
    strict_vintage_mode = False
    XGBOOST_SURVSTAT_FEATURES = ["signal"]
    DECISION_BASELINE_WINDOW_DAYS = 84
    DECISION_EVENT_THRESHOLD_PCT = 25.0
    DEFAULT_DELAY_RULES_DAYS = {}
    DEFAULT_WEIGHTS = {"signal": 1.0}

    @staticmethod
    def _build_survstat_ar_training_data(train_sorted):
        X = np.arange(12, dtype=float).reshape(-1, 1)
        y = np.linspace(10.0, 21.0, 12)
        return X, y

    @staticmethod
    def _build_survstat_ar_row(series, idx, target_time):
        return {"signal": 1.0}

    @staticmethod
    def _amelag_raw_at_date(target_time, virus_typ):
        return 0.0

    @staticmethod
    def _compute_forecast_metrics(y_true, y_hat):
        return {
            "r2_score": 0.4,
            "correlation_pct": 80.0,
            "mae": 1.0,
            "rmse": 1.0,
            "smape": 5.0,
        }

    @staticmethod
    def _compute_vintage_metrics(forecast_records, configured_horizon_days):
        return {"p90_abs_error": 1.0}

    @staticmethod
    def _compute_decision_metrics(forecast_records, threshold_pct, vintage_metrics):
        return {"median_ttd_days": 12, "hit_rate_pct": 80.0, "error_relative_pct": 10.0}

    @staticmethod
    def _compute_interval_coverage_metrics(chart_data):
        return {"interval_passed": True}

    @staticmethod
    def _compute_event_calibration_metrics(forecast_records, threshold_pct):
        return {"calibration_passed": True, "calibration_skipped": False}

    @staticmethod
    def _compute_timing_metrics(forecast_records, horizon_days):
        return {"best_lag_days": 7, "corr_at_best_lag": 0.6}

    @staticmethod
    def _build_quality_gate(
        decision_metrics,
        timing_metrics,
        *,
        improvement_vs_baselines=None,
        interval_coverage=None,
        event_calibration=None,
    ):
        return {"overall_passed": True, "forecast_readiness": "GO"}


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

    def test_fit_xgboost_meta_from_panel_applies_runtime_config(self) -> None:
        _TrackingFakeModel.reset()
        panel = pd.DataFrame(
            {
                "hw_pred": [1.0, 2.0, 3.0, 4.0],
                "ridge_pred": [1.5, 2.5, 3.5, 4.5],
                "y_target": [2.0, 3.0, 4.0, 5.0],
                "horizon_days": [7, 7, 7, 7],
            }
        )

        with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
            with patch("xgboost.XGBRegressor", _TrackingFakeModel):
                forecast_service_direct_training.fit_xgboost_meta_from_panel(
                    _ForecastServiceStub(),
                    panel,
                    target_column="y_target",
                    model_config={"median": {"n_estimators": 20}},
                    meta_features=["hw_pred"],
                    np_module=np,
                )

        self.assertTrue(_TrackingFakeModel.instances)
        self.assertEqual(_TrackingFakeModel.instances[0].kwargs["device"], "cuda")
        self.assertEqual(_TrackingFakeModel.instances[0].kwargs["tree_method"], "hist")

    def test_walk_forward_market_backtest_applies_runtime_config(self) -> None:
        _TrackingFakeModel.reset()
        target_df = pd.DataFrame(
            {
                "datum": pd.date_range("2025-01-05", periods=16, freq="7D"),
                "menge": np.linspace(10.0, 25.0, 16),
                "available_time": pd.date_range("2025-01-05", periods=16, freq="7D"),
            }
        )

        with patch.dict(os.environ, {"REGIONAL_XGBOOST_DEVICE": "cuda"}, clear=False):
            with patch("app.services.ml.backtester_walk_forward.XGBRegressor", _TrackingFakeModel):
                result = backtester_walk_forward.run_walk_forward_market_backtest(
                    _BacktestServiceStub(),
                    target_df=target_df,
                    virus_typ="Influenza A",
                    horizon_days=7,
                    min_train_points=5,
                    delay_rules=None,
                )

        self.assertNotIn("error", result)
        self.assertTrue(_TrackingFakeModel.instances)
        self.assertEqual(_TrackingFakeModel.instances[0].kwargs["device"], "cuda")
        self.assertEqual(_TrackingFakeModel.instances[0].kwargs["tree_method"], "hist")


if __name__ == "__main__":
    unittest.main()
