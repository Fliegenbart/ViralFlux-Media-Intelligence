import unittest
from unittest.mock import ANY, patch

import numpy as np
import pandas as pd

from app.services.ml.forecast_service import (
    ForecastService,
    _resolve_loaded_model_feature_names,
)


class ForecastServiceGuardTests(unittest.TestCase):
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
