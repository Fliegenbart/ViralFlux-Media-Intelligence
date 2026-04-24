import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, patch

import numpy as np
import pandas as pd

from app.services.ml.forecast_service import (
    BACKTEST_RELIABILITY_PROXY_SOURCE,
    DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
    BurdenForecast,
    BurdenForecastPoint,
    EventForecast,
    ForecastService,
    ForecastQuality,
    _is_model_feature_compatibility_error,
    _load_cached_models,
    _resolve_loaded_model_feature_names,
    _sigmoid,
    confidence_label,
    ensure_supported_horizon,
    invalidate_model_cache,
    normalize_forecast_region,
    reliability_score_from_metrics,
    utc_now,
)
from app.services.ml import forecast_service_pipeline


class ForecastServiceGuardTests(unittest.TestCase):
    def test_inline_train_and_forecast_extends_stale_live_frame_to_today(self) -> None:
        class _Model:
            def __init__(self, value: float) -> None:
                self.value = value

            def predict(self, X):
                return np.array([self.value], dtype=float)

        class _EventModel:
            feature_names = ["current_y"]

            def predict_proba(self, X):
                return np.array([0.42], dtype=float)

        class _Service:
            live_feature_max_ds: str | None = None

            def prepare_training_data(self, **kwargs):
                dates = pd.date_range("2026-04-01", "2026-04-15", freq="D")
                return pd.DataFrame(
                    {
                        "ds": dates,
                        "y": np.linspace(10.0, 24.0, len(dates)),
                        "amelag_pred": np.linspace(9.0, 23.0, len(dates)),
                        "trends_score": 1.0,
                        "xd_load": 0.0,
                        "survstat_incidence": 0.0,
                        "lab_positivity_rate": 0.0,
                        "lab_signal_available": 0.0,
                        "lab_baseline_mean": 0.0,
                        "lab_baseline_zscore": 0.0,
                        "schulferien": 0.0,
                        "lag1": 0.0,
                        "lag2": 0.0,
                        "lag3": 0.0,
                        "ma3": 0.0,
                        "ma5": 0.0,
                        "roc": 0.0,
                        "trend_momentum_7d": 0.0,
                        "amelag_lag4": 0.0,
                        "amelag_lag7": 0.0,
                        "xdisease_lag7": 0.0,
                        "xdisease_lag14": 0.0,
                        "survstat_lag7": 0.0,
                        "survstat_lag14": 0.0,
                        "lab_positivity_lag7": 0.0,
                        "region": "BY",
                    }
                )

            def _build_direct_training_panel_from_frame(self, df, **kwargs):
                return pd.DataFrame({"feature": np.linspace(1.0, 30.0, 30)})

            def _fit_xgboost_meta_from_panel(self, panel, target_column):
                return (
                    _Model(30.0),
                    _Model(20.0),
                    _Model(40.0),
                    ["current_y", "horizon_days"],
                    {"current_y": 1.0},
                )

            def _build_live_direct_feature_row(self, df, **kwargs):
                self.live_feature_max_ds = pd.Timestamp(df["ds"].max()).date().isoformat()
                return {"current_y": float(df["y"].iloc[-1]), "horizon_days": float(kwargs["horizon_days"])}

            def _build_event_probability_model_from_panel(self, panel):
                return {
                    "model": _EventModel(),
                    "calibrated_metrics": {},
                    "probability_source": "test",
                    "model_family": "test",
                    "calibration_mode": "raw_probability",
                    "fallback_reason": None,
                    "reliability_metrics": {},
                    "reliability_source": "test",
                    "reliability_score": 0.75,
                }

            def _build_live_event_feature_row(self, **kwargs):
                return {"current_y": kwargs["live_feature_row"]["current_y"]}

            def evaluate_training_candidate(self, **kwargs):
                return {}

            def _compute_outbreak_risk(self, prediction, y):
                return 0.5

            def _quality_meta_from_backtest(self, **kwargs):
                return {"forecast_ready": kwargs["forecast_ready"]}

            def _build_contracts(self, **kwargs):
                return {
                    "event_forecast": {"reliability_score": 0.75},
                    "forecast_quality": {},
                }

            def _is_holiday(self, day, region="DE"):
                return False

        service = _Service()

        result = forecast_service_pipeline.train_and_forecast(
            service,
            virus_typ="Influenza A",
            region="BY",
            horizon_days=5,
            include_internal_history=True,
            normalize_forecast_region_fn=lambda region: str(region).upper(),
            ensure_supported_horizon_fn=lambda horizon: int(horizon),
            min_direct_train_points=2,
            utc_now_fn=lambda: datetime(2026, 4, 24, 12, 0, 0),
            timedelta_cls=timedelta,
            np_module=np,
            pd_module=pd,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None),
        )

        self.assertEqual(service.live_feature_max_ds, "2026-04-24")
        self.assertEqual(
            [pd.Timestamp(item["ds"]).date().isoformat() for item in result["forecast"]],
            [
                "2026-04-25",
                "2026-04-26",
                "2026-04-27",
                "2026-04-28",
                "2026-04-29",
            ],
        )
        self.assertEqual(result["feature_freshness"]["feature_as_of"], "2026-04-15")
        self.assertEqual(result["feature_freshness"]["days_forward_filled"], 9)
        self.assertTrue(result["feature_freshness"]["extension_applied"])

    def test_forecast_service_does_not_keep_dead_confidence_level_state(self) -> None:
        service = ForecastService(db=None)

        self.assertFalse(hasattr(service, "confidence_level"))

    @patch("app.services.ml.forecast_service_model_cache.load_cached_models")
    def test_load_cached_models_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ("med", "lo", "hi", {"version": "v1"}, None)

        result = _load_cached_models("Influenza A", region="BY", horizon_days=14)

        self.assertEqual(result, ("med", "lo", "hi", {"version": "v1"}, None))
        delegated.assert_called_once_with(
            "Influenza A",
            region="BY",
            horizon_days=14,
            ml_models_dir=ANY,
            event_model_artifact_name=ANY,
            default_forecast_region=ANY,
            default_decision_horizon_days=ANY,
            learned_probability_model_cls=ANY,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            model_artifact_dir_fn=ANY,
            json_module=ANY,
            pickle_module=ANY,
            cache=ANY,
            cache_lock=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_model_cache.invalidate_model_cache")
    def test_invalidate_model_cache_wrapper_delegates_to_module(self, delegated) -> None:
        invalidate_model_cache("Influenza A")

        delegated.assert_called_once_with(
            "Influenza A",
            virus_slug_fn=ANY,
            cache=ANY,
            cache_lock=ANY,
        )

    @patch("app.services.ml.forecast_service_model_cache.is_model_feature_compatibility_error")
    def test_is_model_feature_compatibility_error_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = True

        result = _is_model_feature_compatibility_error(ValueError("Feature shape mismatch"))

        self.assertTrue(result)
        delegated.assert_called_once()

    @patch("app.services.ml.forecast_service_model_cache.resolve_loaded_model_feature_names")
    def test_resolve_loaded_model_feature_names_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["hw_pred", "horizon_days"]

        result = _resolve_loaded_model_feature_names(
            metadata={},
            live_feature_row={"horizon_days": 7.0},
            model=None,
        )

        self.assertEqual(result, ["hw_pred", "horizon_days"])
        delegated.assert_called_once_with(
            metadata={},
            live_feature_row={"horizon_days": 7.0},
            model=None,
            meta_features=ANY,
        )

    @patch("app.services.ml.forecast_service_sources.region_variants")
    def test_region_variants_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["BY", "Bayern"]

        result = ForecastService._region_variants("BY")

        self.assertEqual(result, ["BY", "Bayern"])
        delegated.assert_called_once_with("BY", normalize_forecast_region_fn=ANY, default_forecast_region=ANY, bundesland_names=ANY)

    @patch("app.services.ml.forecast_service_sources.survstat_region_values")
    def test_survstat_region_values_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["BY", "Bayern", "Gesamt"]

        result = ForecastService._survstat_region_values("BY")

        self.assertEqual(result, ["BY", "Bayern", "Gesamt"])
        delegated.assert_called_once_with("BY", region_variants_fn=ANY, normalize_forecast_region_fn=ANY, default_forecast_region=ANY)

    @patch("app.services.ml.forecast_service_sources.load_wastewater_training_frame")
    def test_load_wastewater_training_frame_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = pd.DataFrame({"ds": [pd.Timestamp("2026-01-01")], "y": [1.0]})
        service = ForecastService(db=None)

        result = service._load_wastewater_training_frame(
            virus_typ="Influenza A",
            start_date=pd.Timestamp("2025-01-01").to_pydatetime(),
            region="BY",
        )

        self.assertEqual(result["y"].tolist(), [1.0])
        delegated.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            start_date=pd.Timestamp("2025-01-01").to_pydatetime(),
            region="BY",
            normalize_forecast_region_fn=ANY,
            default_forecast_region=ANY,
            region_variants_fn=ANY,
            wastewater_aggregated_model=ANY,
            wastewater_data_model=ANY,
            func_module=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_sources.load_google_trends_rows")
    def test_load_google_trends_rows_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["trend-row"]
        service = ForecastService(db=None)

        result = service._load_google_trends_rows(
            keywords=["Grippe"],
            start_date=pd.Timestamp("2025-01-01").to_pydatetime(),
            region="BY",
        )

        self.assertEqual(result, ["trend-row"])
        delegated.assert_called_once_with(
            service,
            keywords=["Grippe"],
            start_date=pd.Timestamp("2025-01-01").to_pydatetime(),
            region="BY",
            normalize_forecast_region_fn=ANY,
            default_forecast_region=ANY,
            region_variants_fn=ANY,
            google_trends_data_model=ANY,
        )

    @patch("app.services.ml.forecast_service_sources.is_holiday")
    def test_is_holiday_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = True
        service = ForecastService(db=None)
        day = pd.Timestamp("2026-01-03").to_pydatetime()

        result = service._is_holiday(day, region="BY")

        self.assertTrue(result)
        delegated.assert_called_once_with(
            service,
            day,
            region="BY",
            normalize_forecast_region_fn=ANY,
            default_forecast_region=ANY,
            region_variants_fn=ANY,
            school_holidays_model=ANY,
        )

    @patch("app.services.ml.forecast_service_preparation.prepare_training_data")
    def test_prepare_training_data_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = pd.DataFrame({"region": ["DE"], "y": [1.0]})
        service = ForecastService(db=None)

        result = service.prepare_training_data(
            virus_typ="Influenza A",
            lookback_days=120,
            include_internal_history=False,
            region="BY",
        )

        self.assertEqual(result["region"].tolist(), ["DE"])
        delegated.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            lookback_days=120,
            include_internal_history=False,
            region="BY",
            normalize_forecast_region_fn=ANY,
            default_forecast_region=ANY,
            cross_disease_map=ANY,
            survstat_virus_map=ANY,
            wastewater_aggregated_model=ANY,
            survstat_weekly_data_model=ANY,
            func_module=ANY,
            pd_module=ANY,
            np_module=ANY,
            datetime_cls=ANY,
            timedelta_cls=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_direct_training.build_direct_training_panel_from_frame")
    def test_build_direct_training_panel_from_frame_wrapper_delegates_to_module(self, panel_mock) -> None:
        panel_mock.return_value = pd.DataFrame({"hw_pred": [1.0]})
        service = ForecastService(db=None)
        raw = pd.DataFrame({"ds": pd.to_datetime(["2026-01-01"]), "y": [1.0]})

        result = service._build_direct_training_panel_from_frame(
            raw,
            horizon_days=7,
            n_splits=3,
        )

        self.assertEqual(result["hw_pred"].tolist(), [1.0])
        panel_mock.assert_called_once_with(
            service,
            raw,
            horizon_days=7,
            n_splits=3,
            ensure_supported_horizon_fn=ANY,
            build_direct_target_frame_fn=ANY,
            min_direct_train_points=ANY,
            ridge_cls=ANY,
            time_series_split_cls=ANY,
            np_module=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_estimators.fit_holt_winters")
    def test_fit_holt_winters_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = np.array([1.0, 2.0], dtype=float)
        service = ForecastService(db=None)
        history = np.array([3.0, 4.0, 5.0], dtype=float)

        result = service._fit_holt_winters(history, 2)

        self.assertEqual(result.tolist(), [1.0, 2.0])
        delegated.assert_called_once_with(
            history,
            2,
            np_module=ANY,
            exponential_smoothing_cls=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_estimators.fit_ridge")
    def test_fit_ridge_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = (np.array([7.0], dtype=float), {"lag1": 1.0})
        service = ForecastService(db=None)
        frame = pd.DataFrame({"lag1": [1.0], "lag2": [2.0]})
        target = np.array([3.0], dtype=float)

        result = service._fit_ridge(frame, target, 1)

        self.assertEqual(result[0].tolist(), [7.0])
        self.assertEqual(result[1], {"lag1": 1.0})
        delegated.assert_called_once_with(
            frame,
            target,
            1,
            np_module=ANY,
            ridge_cls=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_estimators.fit_prophet")
    def test_fit_prophet_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = np.array([9.0, 10.0], dtype=float)
        service = ForecastService(db=None)

        result = service._fit_prophet("Influenza A", 2)

        self.assertEqual(result.tolist(), [9.0, 10.0])
        delegated.assert_called_once_with(
            service,
            "Influenza A",
            2,
            np_module=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_direct_training.build_live_direct_feature_row")
    def test_build_live_direct_feature_row_wrapper_delegates_to_module(self, row_mock) -> None:
        row_mock.return_value = {"hw_pred": 1.0, "ridge_pred": 2.0}
        service = ForecastService(db=None)
        raw = pd.DataFrame({"ds": pd.to_datetime(["2026-01-01"]), "y": [1.0]})

        result = service._build_live_direct_feature_row(
            raw,
            virus_typ="Influenza A",
            horizon_days=7,
            region="DE",
        )

        self.assertEqual(result, {"hw_pred": 1.0, "ridge_pred": 2.0})
        row_mock.assert_called_once_with(
            service,
            raw,
            virus_typ="Influenza A",
            horizon_days=7,
            region="DE",
            ensure_supported_horizon_fn=ANY,
            default_forecast_region=ANY,
            normalize_forecast_region_fn=ANY,
            build_direct_target_frame_fn=ANY,
            min_direct_train_points=ANY,
            ridge_cls=ANY,
            np_module=ANY,
        )

    @patch("app.services.ml.forecast_service_direct_training.fit_xgboost_meta_from_panel")
    def test_fit_xgboost_meta_from_panel_wrapper_delegates_to_module(self, fit_mock) -> None:
        fit_mock.return_value = ("median", "lower", "upper", ["hw_pred"], {"hw_pred": 1.0})
        service = ForecastService(db=None)
        panel = pd.DataFrame({"hw_pred": [1.0], "y_target": [2.0]})

        result = service._fit_xgboost_meta_from_panel(
            panel,
            target_column="y_target",
            model_config={"median": {"n_estimators": 10}},
        )

        self.assertEqual(result, ("median", "lower", "upper", ["hw_pred"], {"hw_pred": 1.0}))
        fit_mock.assert_called_once_with(
            service,
            panel,
            target_column="y_target",
            model_config={"median": {"n_estimators": 10}},
            meta_features=ANY,
            np_module=ANY,
        )

    @patch("app.services.ml.forecast_service_direct_training.generate_oof_predictions")
    def test_generate_oof_predictions_wrapper_delegates_to_module(self, oof_mock) -> None:
        oof_mock.return_value = pd.DataFrame({"hw_pred": [0.0], "ridge_pred": [0.0]})
        service = ForecastService(db=None)
        frame = pd.DataFrame({"y": [1.0]})

        result = service._generate_oof_predictions(frame, n_splits=2)

        self.assertEqual(result["hw_pred"].tolist(), [0.0])
        oof_mock.assert_called_once_with(
            service,
            frame,
            n_splits=2,
            time_series_split_cls=ANY,
            np_module=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_direct_training.fit_xgboost_meta")
    def test_fit_xgboost_meta_wrapper_delegates_to_module(self, fit_mock) -> None:
        fit_mock.return_value = ("median", "lower", "upper", {"hw_pred": 0.5})
        service = ForecastService(db=None)
        df = pd.DataFrame({"y": [1.0]})
        oof = pd.DataFrame({"hw_pred": [0.0], "ridge_pred": [0.0]})

        result = service._fit_xgboost_meta(df, oof, model_config=None)

        self.assertEqual(result, ("median", "lower", "upper", {"hw_pred": 0.5}))
        fit_mock.assert_called_once_with(
            service,
            df,
            oof,
            model_config=None,
            meta_features=ANY,
            np_module=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_backtest.evaluate_training_candidate")
    def test_evaluate_training_candidate_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"window_count": 3, "region": "DE"}
        service = ForecastService(db=None)

        result = service.evaluate_training_candidate(
            "Influenza A",
            include_internal_history=False,
            model_config={"median": {"n_estimators": 10}},
            n_windows=4,
            walk_forward_stride=2,
            max_splits=3,
            region="BY",
            horizon_days=14,
        )

        self.assertEqual(result, {"window_count": 3, "region": "DE"})
        delegated.assert_called_once_with(
            service,
            "Influenza A",
            include_internal_history=False,
            model_config={"median": {"n_estimators": 10}},
            n_windows=4,
            walk_forward_stride=2,
            max_splits=3,
            region="BY",
            horizon_days=14,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            default_forecast_region=ANY,
            default_decision_horizon_days=ANY,
            default_walk_forward_stride=ANY,
            min_direct_train_points=ANY,
            build_walk_forward_splits_fn=ANY,
            compute_regression_metrics_fn=ANY,
            compute_classification_metrics_fn=ANY,
            summarize_probabilistic_metrics_fn=ANY,
            np_module=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_pipeline.train_and_forecast")
    def test_train_and_forecast_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"status": "success", "virus_typ": "Influenza A"}
        service = ForecastService(db=None)

        result = service.train_and_forecast(
            virus_typ="Influenza A",
            region="BY",
            horizon_days=14,
            include_internal_history=False,
        )

        self.assertEqual(result, {"status": "success", "virus_typ": "Influenza A"})
        delegated.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            region="BY",
            horizon_days=14,
            include_internal_history=False,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            min_direct_train_points=ANY,
            utc_now_fn=ANY,
            timedelta_cls=ANY,
            np_module=ANY,
            pd_module=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_pipeline.save_forecast")
    def test_save_forecast_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = 2
        service = ForecastService(db=None)
        forecast_data = {
            "virus_typ": "Influenza A",
            "region": "DE",
            "horizon_days": 7,
            "forecast": [{"ds": pd.Timestamp("2026-01-10"), "yhat": 1.0}],
            "model_version": "v1",
        }

        result = service.save_forecast(forecast_data)

        self.assertEqual(result, 2)
        delegated.assert_called_once_with(
            service,
            forecast_data,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            normalize_event_forecast_payload_fn=ANY,
            default_decision_horizon_days=ANY,
            ml_forecast_cls=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_pipeline.run_forecasts_for_all_viruses")
    def test_run_forecasts_for_all_viruses_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"Influenza A": {"status": "success"}}
        service = ForecastService(db=None)

        result = service.run_forecasts_for_all_viruses(
            region="BY",
            horizon_days=14,
            include_internal_history=False,
        )

        self.assertEqual(result, {"Influenza A": {"status": "success"}})
        delegated.assert_called_once_with(
            service,
            region="BY",
            horizon_days=14,
            include_internal_history=False,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            default_forecast_region=ANY,
            default_decision_horizon_days=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_quality_contracts.compute_regression_metrics")
    def test_compute_regression_metrics_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"mae": 1.2}

        result = ForecastService._compute_regression_metrics([1.0], [2.0])

        self.assertEqual(result, {"mae": 1.2})
        delegated.assert_called_once_with([1.0], [2.0], np_module=ANY)

    @patch("app.services.ml.forecast_service_quality_contracts.backtest_quality_score")
    def test_backtest_quality_score_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = 0.77

        result = ForecastService._backtest_quality_score({"mape": 23.0})

        self.assertEqual(result, 0.77)
        delegated.assert_called_once_with({"mape": 23.0})

    @patch("app.services.ml.forecast_service_quality_contracts.calibration_passed")
    def test_calibration_passed_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = True

        result = ForecastService._calibration_passed({"brier_score": 0.1})

        self.assertTrue(result)
        delegated.assert_called_once_with({"brier_score": 0.1})

    @patch("app.services.ml.forecast_service_quality_contracts.quality_meta_from_backtest")
    def test_quality_meta_from_backtest_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"confidence": 0.81}
        service = ForecastService(db=None)

        result = service._quality_meta_from_backtest(
            backtest_metrics={"mape": 12.0},
            event_probability=0.63,
            probability_source="learned",
            calibration_mode="platt",
            fallback_reason=None,
            learned_model_version="v1",
            forecast_ready=True,
            drift_status="ok",
            baseline_deltas={"delta": 1.0},
            timing_metrics={"lag": 2.0},
            interval_coverage={"p50": 0.7},
            promotion_gate={"status": "go"},
        )

        self.assertEqual(result, {"confidence": 0.81})
        delegated.assert_called_once_with(
            service,
            backtest_metrics={"mape": 12.0},
            event_probability=0.63,
            probability_source="learned",
            calibration_mode="platt",
            fallback_reason=None,
            learned_model_version="v1",
            forecast_ready=True,
            drift_status="ok",
            baseline_deltas={"delta": 1.0},
            timing_metrics={"lag": 2.0},
            interval_coverage={"p50": 0.7},
            promotion_gate={"status": "go"},
            reliability_score_from_metrics_fn=reliability_score_from_metrics,
            backtest_reliability_proxy_source=BACKTEST_RELIABILITY_PROXY_SOURCE,
        )

    @patch("app.services.ml.forecast_service_quality_contracts.compute_outbreak_risk")
    def test_compute_outbreak_risk_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = 0.55
        service = ForecastService(db=None)
        history = np.array([1.0, 2.0], dtype=float)

        result = service._compute_outbreak_risk(42.0, history, window=21)

        self.assertEqual(result, 0.55)
        delegated.assert_called_once_with(42.0, history, window=21, np_module=ANY, sigmoid_fn=_sigmoid)

    @patch("app.services.ml.forecast_service_quality_contracts.build_contracts")
    def test_build_contracts_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"event_forecast": {"confidence": 0.7}}
        service = ForecastService(db=None)
        history = np.array([10.0, 11.0], dtype=float)
        forecast_records = [{"ds": pd.Timestamp("2026-01-10"), "yhat": 12.0}]
        issue_date = pd.Timestamp("2026-01-03").to_pydatetime()

        result = service._build_contracts(
            virus_typ="Influenza A",
            region="DE",
            horizon_days=7,
            forecast_records=forecast_records,
            model_version="v1",
            y_history=history,
            issue_date=issue_date,
            quality_meta={"event_probability": 0.6},
        )

        self.assertEqual(result, {"event_forecast": {"confidence": 0.7}})
        delegated.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            region="DE",
            horizon_days=7,
            forecast_records=forecast_records,
            model_version="v1",
            y_history=history,
            issue_date=issue_date,
            quality_meta={"event_probability": 0.6},
            normalize_forecast_region_fn=normalize_forecast_region,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            burden_forecast_cls=BurdenForecast,
            burden_forecast_point_cls=BurdenForecastPoint,
            event_forecast_cls=EventForecast,
            forecast_quality_cls=ForecastQuality,
            confidence_label_fn=confidence_label,
            backtest_reliability_proxy_source=BACKTEST_RELIABILITY_PROXY_SOURCE,
            default_decision_event_threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            utc_now_fn=utc_now,
            np_module=ANY,
        )

    @patch("app.services.ml.forecast_service_inference.predict")
    def test_predict_wrapper_delegates_to_module(self, predict_mock) -> None:
        predict_mock.return_value = {"status": "success", "virus_typ": "Influenza A"}
        service = ForecastService(db=None)

        result = service.predict(
            virus_typ="Influenza A",
            region="BY",
            horizon_days=14,
            include_internal_history=False,
        )

        self.assertEqual(result, {"status": "success", "virus_typ": "Influenza A"})
        predict_mock.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            region="BY",
            horizon_days=14,
            include_internal_history=False,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            load_cached_models_fn=ANY,
            is_model_feature_compatibility_error_fn=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_inference.inference_from_loaded_models")
    def test_inference_from_loaded_models_wrapper_delegates_to_module(self, inference_mock) -> None:
        inference_mock.return_value = {"model_version": "xgb_stack_v1_loaded"}
        service = ForecastService(db=None)

        result = service._inference_from_loaded_models(
            virus_typ="Influenza A",
            model_med="median-model",
            model_lo="lower-model",
            model_hi="upper-model",
            metadata={"version": "xgb_stack_v1_loaded"},
            event_model=None,
            region="DE",
            horizon_days=7,
            include_internal_history=True,
        )

        self.assertEqual(result, {"model_version": "xgb_stack_v1_loaded"})
        inference_mock.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            model_med="median-model",
            model_lo="lower-model",
            model_hi="upper-model",
            metadata={"version": "xgb_stack_v1_loaded"},
            event_model=None,
            region="DE",
            horizon_days=7,
            include_internal_history=True,
            normalize_forecast_region_fn=ANY,
            ensure_supported_horizon_fn=ANY,
            min_direct_train_points=ANY,
            np_module=ANY,
            pd_module=ANY,
            timedelta_cls=ANY,
            utc_now_fn=ANY,
            logger=ANY,
        )

    @patch("app.services.ml.forecast_service_event_probability.fit_event_classifier_model")
    def test_fit_event_classifier_model_wrapper_delegates_to_module(self, fit_mock) -> None:
        fit_mock.return_value = "event-model"
        train_df = pd.DataFrame({"event_target": [0, 1], "current_y": [1.0, 2.0]})

        result = ForecastService._fit_event_classifier_model(
            train_df,
            feature_names=["current_y"],
            model_family="logistic_regression",
        )

        self.assertEqual(result, "event-model")
        fit_mock.assert_called_once_with(
            train_df,
            feature_names=["current_y"],
            model_family="logistic_regression",
            np_module=ANY,
            empirical_event_classifier_cls=ANY,
            default_event_classifier_config=ANY,
            pipeline_cls=ANY,
            standard_scaler_cls=ANY,
            logistic_regression_cls=ANY,
        )

    @patch("app.services.ml.forecast_service_event_probability.build_event_oof_predictions")
    def test_build_event_oof_predictions_wrapper_delegates_to_module(self, oof_mock) -> None:
        oof_mock.return_value = pd.DataFrame({"fold": [1], "event_probability_raw": [0.7]})
        service = ForecastService(db=None)
        panel = pd.DataFrame({"event_target": [0, 1]})

        result = service._build_event_oof_predictions(
            panel,
            feature_names=["current_y"],
            model_family="logistic_regression",
            walk_forward_stride=4,
            max_splits=3,
            min_train_points=20,
        )

        self.assertEqual(result["event_probability_raw"].tolist(), [0.7])
        oof_mock.assert_called_once_with(
            service,
            panel,
            feature_names=["current_y"],
            model_family="logistic_regression",
            walk_forward_stride=4,
            max_splits=3,
            min_train_points=20,
            default_walk_forward_stride=ANY,
            min_direct_train_points=ANY,
            build_walk_forward_splits_fn=ANY,
            np_module=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_event_probability.select_best_event_candidate")
    def test_select_best_event_candidate_wrapper_delegates_to_module(self, select_mock) -> None:
        select_mock.return_value = {"model_family": "logistic_regression"}
        candidates = [{"model_family": "xgb_classifier", "oof_frame": pd.DataFrame({"x": [1]})}]

        result = ForecastService._select_best_event_candidate(candidates)

        self.assertEqual(result, {"model_family": "logistic_regression"})
        select_mock.assert_called_once_with(
            candidates,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_event_probability.build_event_probability_model_from_panel")
    def test_build_event_probability_model_from_panel_wrapper_delegates_to_module(self, build_mock) -> None:
        build_mock.return_value = {"model_family": "empirical_prevalence"}
        service = ForecastService(db=None)
        panel = pd.DataFrame({"event_target": [0, 1]})

        result = service._build_event_probability_model_from_panel(
            panel,
            walk_forward_stride=5,
            max_splits=2,
        )

        self.assertEqual(result, {"model_family": "empirical_prevalence"})
        build_mock.assert_called_once_with(
            service,
            panel,
            walk_forward_stride=5,
            max_splits=2,
            default_walk_forward_stride=ANY,
            min_direct_train_points=ANY,
            learned_probability_model_cls=ANY,
            empirical_event_classifier_cls=ANY,
            compute_classification_metrics_fn=ANY,
            select_probability_calibration_fn=ANY,
            apply_probability_calibration_fn=ANY,
            reliability_score_from_metrics_fn=ANY,
            np_module=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_internal_history.augment_with_internal_history")
    def test_augment_with_internal_history_wrapper_delegates_to_module(self, augment_mock) -> None:
        augment_mock.return_value = pd.DataFrame({"y": [1.0], "lab_positivity_rate": [0.2]})
        service = ForecastService(db=None)
        df = pd.DataFrame({"ds": pd.to_datetime(["2026-01-01"]), "y": [1.0]})

        result = service._augment_with_internal_history(
            df=df,
            virus_typ="Influenza A",
            start_date=pd.Timestamp("2025-01-01"),
            region="DE",
        )

        self.assertEqual(result["lab_positivity_rate"].tolist(), [0.2])
        augment_mock.assert_called_once_with(
            service,
            df=df,
            virus_typ="Influenza A",
            start_date=pd.Timestamp("2025-01-01"),
            region="DE",
        )

    @patch("app.services.ml.forecast_service_internal_history.load_internal_history_frame")
    def test_load_internal_history_frame_wrapper_delegates_to_module(self, load_mock) -> None:
        load_mock.return_value = pd.DataFrame({"anzahl_tests": [100]})
        service = ForecastService(db=None)

        result = service._load_internal_history_frame(
            virus_typ="Influenza A",
            start_date=pd.Timestamp("2025-01-01"),
            region="BY",
        )

        self.assertEqual(result["anzahl_tests"].tolist(), [100])
        load_mock.assert_called_once_with(
            service,
            virus_typ="Influenza A",
            start_date=pd.Timestamp("2025-01-01"),
            region="BY",
            internal_history_test_map=ANY,
            ganzimmun_model=ANY,
            normalize_forecast_region_fn=ANY,
            default_forecast_region=ANY,
            func_module=ANY,
            timedelta_cls=ANY,
            pd_module=ANY,
        )

    @patch("app.services.ml.forecast_service_internal_history.build_internal_history_feature_frame")
    def test_build_internal_history_feature_frame_wrapper_delegates_to_module(self, build_mock) -> None:
        build_mock.return_value = pd.DataFrame({"lab_signal_available": [1.0]})
        ds = pd.Series(pd.to_datetime(["2026-01-10"]))
        history = pd.DataFrame({"datum": pd.to_datetime(["2026-01-05"])})

        result = ForecastService._build_internal_history_feature_frame(ds, history)

        self.assertEqual(result["lab_signal_available"].tolist(), [1.0])
        build_mock.assert_called_once_with(
            ds,
            history,
            pd_module=ANY,
            timedelta_cls=ANY,
        )

    def test_resolve_loaded_model_feature_names_respects_explicit_metadata_schema(self) -> None:
        names = _resolve_loaded_model_feature_names(
            metadata={"feature_names": ["hw_pred", "ridge_pred"]},
            live_feature_row={"hw_pred": 1.0, "ridge_pred": 2.0, "horizon_days": 7.0},
            model=None,
        )

        self.assertEqual(names, ["hw_pred", "ridge_pred"])

    def test_resolve_loaded_model_feature_names_can_append_horizon_for_legacy_models_without_metadata(self) -> None:
        class _Booster:
            @staticmethod
            def num_features() -> int:
                return 19

        class _Model:
            @staticmethod
            def get_booster() -> _Booster:
                return _Booster()

        names = _resolve_loaded_model_feature_names(
            metadata={},
            live_feature_row={"horizon_days": 7.0},
            model=_Model(),
        )

        self.assertIn("horizon_days", names)

    def test_predict_falls_back_to_in_memory_forecast_when_cached_model_features_do_not_match(self) -> None:
        service = ForecastService(db=None)

        with patch(
            "app.services.ml.forecast_service._load_cached_models",
            return_value=(object(), object(), object(), {"version": "legacy-rsv-model"}, None),
        ), patch.object(
            service,
            "_inference_from_loaded_models",
            side_effect=ValueError("Feature shape mismatch, expected: 18, got 19"),
        ), patch.object(
            service,
            "train_and_forecast",
            return_value={"status": "success", "virus_typ": "RSV A"},
        ) as fallback:
            result = service.predict(virus_typ="RSV A")

        fallback.assert_called_once_with(
            virus_typ="RSV A",
            region="DE",
            horizon_days=7,
            include_internal_history=True,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["virus_typ"], "RSV A")

    @patch("app.services.ml.forecast_service_features.finalize_training_frame")
    def test_finalize_training_frame_wrapper_delegates_to_module(self, delegated) -> None:
        raw = pd.DataFrame({"ds": pd.to_datetime(["2026-01-01"]), "y": [1.0]})
        delegated.return_value = raw.copy()

        result = ForecastService._finalize_training_frame(raw)

        self.assertEqual(result["y"].tolist(), [1.0])
        delegated.assert_called_once_with(
            raw,
            leakage_safe_warmup_rows=ANY,
            np_module=ANY,
        )

    @patch("app.services.ml.forecast_service_features.build_meta_feature_row")
    def test_build_meta_feature_row_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"hw_pred": 1.0}
        row = pd.Series({"trends_score": 2.0})

        result = ForecastService._build_meta_feature_row(
            row,
            hw_pred=1.0,
            ridge_pred=2.0,
            prophet_pred=3.0,
        )

        self.assertEqual(result, {"hw_pred": 1.0})
        delegated.assert_called_once_with(
            row,
            hw_pred=1.0,
            ridge_pred=2.0,
            prophet_pred=3.0,
        )

    @patch("app.services.ml.forecast_service_features.direct_ridge_feature_columns")
    def test_direct_ridge_feature_columns_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["lag1"]
        frame = pd.DataFrame({"lag1": [1.0]})

        result = ForecastService._direct_ridge_feature_columns(frame)

        self.assertEqual(result, ["lag1"])
        delegated.assert_called_once_with(frame, ridge_direct_features=ANY)

    @patch("app.services.ml.forecast_service_features.event_feature_columns")
    def test_event_feature_columns_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["current_y", "hw_pred"]
        frame = pd.DataFrame({"current_y": [1.0], "hw_pred": [2.0]})

        result = ForecastService._event_feature_columns(frame)

        self.assertEqual(result, ["current_y", "hw_pred"])
        delegated.assert_called_once_with(frame, meta_features=ANY)

    @patch("app.services.ml.forecast_service_features.build_live_event_feature_row")
    def test_build_live_event_feature_row_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = {"current_y": 5.0, "horizon_days": 7.0}
        raw = pd.DataFrame({"y": [5.0]})

        result = ForecastService._build_live_event_feature_row(
            raw=raw,
            live_feature_row={"hw_pred": 1.0},
            horizon_days=7,
        )

        self.assertEqual(result, {"current_y": 5.0, "horizon_days": 7.0})
        delegated.assert_called_once_with(raw=raw, live_feature_row={"hw_pred": 1.0}, horizon_days=7)

    @patch("app.services.ml.forecast_service_features.event_model_candidates")
    def test_event_model_candidates_wrapper_delegates_to_module(self, delegated) -> None:
        delegated.return_value = ["logistic_regression", "xgb_classifier"]

        result = ForecastService._event_model_candidates()

        self.assertEqual(result, ["logistic_regression", "xgb_classifier"])
        delegated.assert_called_once_with()

    def test_finalize_training_frame_drops_warmup_rows_without_backfill(self) -> None:
        base = pd.Series(np.arange(20, dtype=float))
        raw = pd.DataFrame(
            {
                "ds": pd.date_range("2024-01-01", periods=20, freq="D"),
                "y": base,
                "trends_score": [np.nan] + [10.0] * 19,
                "schulferien": [0.0] * 20,
                "amelag_pred": base + 100.0,
                "xd_load": base / 10.0,
                "survstat_incidence": base / 20.0,
                "lag1": base.shift(1),
                "lag2": base.shift(2),
                "lag3": base.shift(3),
                "ma3": base.rolling(window=3, min_periods=1).mean().shift(1),
                "ma5": base.rolling(window=5, min_periods=1).mean().shift(1),
                "roc": base.pct_change().shift(1),
                "trend_momentum_7d": base.diff(periods=7) / base.shift(7).replace(0, np.nan),
                "amelag_lag4": (base + 100.0).shift(4),
                "amelag_lag7": (base + 100.0).shift(7),
                "xdisease_lag7": (base / 10.0).shift(7),
                "xdisease_lag14": (base / 10.0).shift(14),
                "survstat_lag7": (base / 20.0).shift(7),
                "survstat_lag14": (base / 20.0).shift(14),
            }
        )

        clean = ForecastService._finalize_training_frame(raw)

        self.assertEqual(len(clean), 6)
        self.assertEqual(clean.iloc[0]["ds"], raw.iloc[14]["ds"])
        self.assertEqual(clean.iloc[0]["lag1"], raw.iloc[14]["lag1"])
        self.assertFalse(clean.isna().any().any())

    def test_build_meta_feature_row_keeps_cross_disease_lags(self) -> None:
        row = pd.Series(
            {
                "amelag_lag4": 1.4,
                "amelag_lag7": 1.7,
                "trend_momentum_7d": 0.2,
                "schulferien": 1.0,
                "trends_score": 24.0,
                "xdisease_lag7": 0.7,
                "xdisease_lag14": 0.4,
                "survstat_incidence": 0.9,
                "survstat_lag7": 0.8,
                "survstat_lag14": 0.6,
                "lab_positivity_rate": 0.18,
                "lab_signal_available": 1.0,
                "lab_baseline_mean": 0.12,
                "lab_baseline_zscore": 1.5,
                "lab_positivity_lag7": 0.15,
            }
        )

        features = ForecastService._build_meta_feature_row(
            row,
            hw_pred=10.0,
            ridge_pred=11.0,
            prophet_pred=12.0,
        )

        self.assertEqual(features["xdisease_lag7"], 0.7)
        self.assertEqual(features["xdisease_lag14"], 0.4)
        self.assertEqual(features["lab_positivity_rate"], 0.18)
        self.assertEqual(features["lab_baseline_zscore"], 1.5)
        self.assertEqual(features["hw_pred"], 10.0)
        self.assertEqual(features["prophet_pred"], 12.0)

    def test_build_internal_history_feature_frame_respects_available_time(self) -> None:
        ds = pd.Series(pd.to_datetime(["2024-01-10", "2024-01-20"]))
        history = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2024-01-05", "2024-01-12", "2023-01-18", "2023-01-19"]),
                "available_time": pd.to_datetime(["2024-01-06", "2024-01-15", "2023-01-18", "2023-01-19"]),
                "anzahl_tests": [100, 200, 100, 120],
                "positive_ergebnisse": [20, 100, 10, 12],
            }
        )

        features = ForecastService._build_internal_history_feature_frame(ds, history)

        self.assertAlmostEqual(features.iloc[0]["lab_positivity_rate"], 0.2)
        self.assertAlmostEqual(features.iloc[1]["lab_positivity_rate"], 0.5)
        self.assertGreater(features.iloc[1]["lab_baseline_mean"], 0.0)
        self.assertNotEqual(features.iloc[1]["lab_baseline_zscore"], 0.0)

    def test_build_internal_history_feature_frame_falls_back_to_zero_without_history(self) -> None:
        ds = pd.Series(pd.to_datetime(["2024-01-10", "2024-01-20"]))

        features = ForecastService._build_internal_history_feature_frame(ds, pd.DataFrame())

        self.assertTrue((features == 0.0).all().all())

    def test_build_direct_training_panel_does_not_backfill_future_oof_predictions(self) -> None:
        raw = pd.DataFrame(
            {
                "ds": pd.date_range("2026-01-01", periods=100, freq="D"),
                "y": np.linspace(10.0, 109.0, 100),
            }
        )

        def _build_with_hw_value(hw_value: float) -> pd.DataFrame:
            service = ForecastService(db=None)
            service._fit_holt_winters = lambda history, horizon: np.full(horizon, hw_value, dtype=float)  # type: ignore[method-assign]
            return service._build_direct_training_panel_from_frame(
                raw,
                horizon_days=7,
                n_splits=2,
            )

        panel_a = _build_with_hw_value(111.0)
        panel_b = _build_with_hw_value(777.0)

        early_slice_a = panel_a.loc[:61, ["hw_pred", "ridge_pred", "prophet_pred"]].copy()
        early_slice_b = panel_b.loc[:61, ["hw_pred", "ridge_pred", "prophet_pred"]].copy()
        self.assertTrue(early_slice_a.equals(early_slice_b))
        self.assertNotEqual(panel_a.iloc[-1]["hw_pred"], panel_b.iloc[-1]["hw_pred"])

    def test_generate_oof_predictions_uses_causal_history_fallback_instead_of_series_end(self) -> None:
        service = ForecastService(db=None)
        frame = pd.DataFrame(
            {
                "y": np.arange(10.0, 30.0, dtype=float),
            }
        )
        service._fit_holt_winters = lambda history, n_val: np.full(n_val, 91.0, dtype=float)  # type: ignore[method-assign]
        service._fit_ridge = lambda df_train, y_train, n_val: (np.full(n_val, 82.0, dtype=float), {})  # type: ignore[method-assign]

        oof = service._generate_oof_predictions(frame, n_splits=2)

        self.assertEqual(oof.iloc[0]["hw_pred"], 0.0)
        self.assertEqual(oof.iloc[0]["ridge_pred"], 0.0)
        self.assertEqual(oof.iloc[1]["hw_pred"], frame.iloc[0]["y"])
        self.assertEqual(oof.iloc[1]["ridge_pred"], frame.iloc[0]["y"])
        self.assertNotEqual(oof.iloc[0]["hw_pred"], frame.iloc[-1]["y"])
        self.assertNotEqual(oof.iloc[0]["ridge_pred"], frame.iloc[-1]["y"])


if __name__ == "__main__":
    unittest.main()
