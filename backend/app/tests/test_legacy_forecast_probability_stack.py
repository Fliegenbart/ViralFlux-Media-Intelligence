import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from app.services.ml.forecast_contracts import (
    BACKTEST_RELIABILITY_PROXY_SOURCE,
    EventForecast,
    HEURISTIC_EVENT_SCORE_SOURCE,
)
from app.services.ml.forecast_horizon_utils import (
    build_direct_target_frame,
    build_walk_forward_splits,
    select_probability_calibration,
)
from app.services.ml.forecast_service import ForecastService


class _DummyEventModel:
    def __init__(self, probability: float = 0.6) -> None:
        self.probability = float(probability)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        probs = np.full(len(X), self.probability, dtype=float)
        return np.column_stack([1.0 - probs, probs])


class _IdentityProbabilityCalibrator:
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        probs = np.clip(np.asarray(X, dtype=float).reshape(-1), 0.001, 0.999)
        return np.column_stack([1.0 - probs, probs])


class _ConstantProbabilityCalibrator:
    def __init__(self, probability: float) -> None:
        self.probability = float(probability)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        probs = np.full(len(np.asarray(X)), self.probability, dtype=float)
        return np.column_stack([1.0 - probs, probs])


class LegacyForecastProbabilityStackTests(unittest.TestCase):
    @staticmethod
    def _guard_calibration_frame(periods: int = 80) -> pd.DataFrame:
        dates = pd.date_range("2026-01-01", periods=periods, freq="D")
        labels = np.array([idx % 2 for idx in range(periods)], dtype=int)
        raw_probs = np.where(labels == 1, 0.9, 0.1)
        return pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": raw_probs,
            }
        )

    @staticmethod
    def _flat_isotonic_calibrator() -> IsotonicRegression:
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(np.array([0.1, 0.9], dtype=float), np.array([0.5, 0.5], dtype=float))
        return calibrator

    def test_build_direct_target_frame_aligns_event_target_with_requested_horizon(self) -> None:
        frame = pd.DataFrame(
            {
                "ds": pd.date_range("2026-01-01", periods=6, freq="D"),
                "y": [100.0, 110.0, 90.0, 130.0, 100.0, 150.0],
            }
        )

        direct = build_direct_target_frame(frame, horizon_days=3)

        self.assertEqual(len(direct), 3)
        self.assertEqual(direct.iloc[0]["y_target"], 130.0)
        self.assertEqual(direct.iloc[0]["event_target"], 1.0)
        self.assertEqual(direct.iloc[1]["y_target"], 100.0)
        self.assertEqual(direct.iloc[1]["event_target"], 0.0)
        self.assertEqual(direct.iloc[2]["target_date"], pd.Timestamp("2026-01-06"))

    def test_build_walk_forward_splits_uses_dense_recent_origins_with_stride_and_cap(self) -> None:
        splits = build_walk_forward_splits(
            10,
            min_train_points=3,
            stride=2,
            max_splits=2,
        )

        self.assertEqual([(split.train_end_idx, split.test_idx) for split in splits], [(7, 7), (9, 9)])
        self.assertTrue(all(split.train_end_idx <= split.test_idx for split in splits))

    def test_select_probability_calibration_prefers_isotonic_when_support_is_sufficient(self) -> None:
        dates = pd.date_range("2026-01-01", periods=80, freq="D")
        labels = np.array([idx % 2 for idx in range(80)], dtype=int)
        raw_probs = np.where(labels == 1, 0.72, 0.28)
        frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": raw_probs,
            }
        )

        result = select_probability_calibration(frame)

        self.assertEqual(result["calibration_mode"], "isotonic")
        self.assertIsNone(result["fallback_reason"])
        self.assertGreater(result["reliability_metrics"]["sample_count"], 0.0)

    def test_select_probability_calibration_falls_back_to_platt_then_raw(self) -> None:
        platt_frame = self._guard_calibration_frame()
        with patch(
            "app.services.ml.forecast_horizon_utils.fit_isotonic_calibrator",
            return_value=None,
        ), patch(
            "app.services.ml.forecast_horizon_utils.fit_platt_calibrator",
            return_value=_IdentityProbabilityCalibrator(),
        ):
            platt_result = select_probability_calibration(platt_frame)
        self.assertEqual(platt_result["calibration_mode"], "platt")

        raw_dates = pd.date_range("2026-02-01", periods=24, freq="D")
        raw_labels = np.zeros(24, dtype=int)
        raw_labels[0] = 1
        raw_frame = pd.DataFrame(
            {
                "as_of_date": raw_dates,
                "event_label": raw_labels,
                "event_probability_raw": np.full(24, 0.08, dtype=float),
            }
        )

        raw_result = select_probability_calibration(raw_frame)
        self.assertEqual(raw_result["calibration_mode"], "raw_probability")
        self.assertTrue(raw_result["fallback_reason"])

    def test_select_probability_calibration_rejects_isotonic_when_guard_metrics_worsen(self) -> None:
        frame = self._guard_calibration_frame()

        with patch(
            "app.services.ml.forecast_horizon_utils.fit_isotonic_calibrator",
            return_value=self._flat_isotonic_calibrator(),
        ), patch(
            "app.services.ml.forecast_horizon_utils.fit_platt_calibrator",
            return_value=None,
        ):
            result = select_probability_calibration(frame)

        self.assertEqual(result["calibration_mode"], "raw_probability")
        self.assertEqual(result["reliability_source"], "temporal_guard")
        self.assertIn("guard_metrics_worsened", str(result["fallback_reason"]))
        self.assertIn("isotonic", str(result["fallback_reason"]))

    def test_select_probability_calibration_accepts_platt_when_guard_does_not_worsen(self) -> None:
        frame = self._guard_calibration_frame()

        with patch(
            "app.services.ml.forecast_horizon_utils.fit_isotonic_calibrator",
            return_value=self._flat_isotonic_calibrator(),
        ), patch(
            "app.services.ml.forecast_horizon_utils.fit_platt_calibrator",
            return_value=_IdentityProbabilityCalibrator(),
        ):
            result = select_probability_calibration(frame)

        self.assertEqual(result["calibration_mode"], "platt")
        self.assertIsNone(result["fallback_reason"])
        self.assertEqual(result["reliability_source"], "temporal_guard")

    def test_select_probability_calibration_uses_raw_when_all_candidates_fail_guard(self) -> None:
        frame = self._guard_calibration_frame()

        with patch(
            "app.services.ml.forecast_horizon_utils.fit_isotonic_calibrator",
            return_value=self._flat_isotonic_calibrator(),
        ), patch(
            "app.services.ml.forecast_horizon_utils.fit_platt_calibrator",
            return_value=_ConstantProbabilityCalibrator(0.5),
        ):
            result = select_probability_calibration(frame)

        self.assertEqual(result["calibration_mode"], "raw_probability")
        self.assertEqual(result["reliability_source"], "temporal_guard")
        self.assertIn("guard_metrics_worsened", str(result["fallback_reason"]))
        self.assertIn("isotonic", str(result["fallback_reason"]))
        self.assertIn("platt", str(result["fallback_reason"]))

    def test_event_oof_predictions_never_train_on_future_issue_dates(self) -> None:
        service = ForecastService(db=None)
        issue_dates = pd.date_range("2026-01-01", periods=40, freq="D")
        panel = pd.DataFrame(
            {
                "issue_date": issue_dates,
                "target_date": issue_dates + pd.Timedelta(days=7),
                "event_target": [idx % 2 for idx in range(40)],
                "current_y": np.linspace(10.0, 50.0, 40),
                "hw_pred": np.linspace(10.0, 50.0, 40),
                "ridge_pred": np.linspace(11.0, 51.0, 40),
                "prophet_pred": np.linspace(12.0, 52.0, 40),
                "horizon_days": np.full(40, 7.0),
            }
        )
        captured_train_end_dates: list[pd.Timestamp] = []

        def _fit(train_df, *, feature_names, model_family):
            captured_train_end_dates.append(pd.Timestamp(train_df["issue_date"].max()))
            return _DummyEventModel(probability=0.61)

        service._fit_event_classifier_model = _fit  # type: ignore[method-assign]

        oof = service._build_event_oof_predictions(
            panel,
            feature_names=["current_y", "hw_pred", "ridge_pred", "prophet_pred", "horizon_days"],
            model_family="logistic_regression",
            walk_forward_stride=5,
            max_splits=3,
            min_train_points=20,
        )

        self.assertEqual(len(oof), len(captured_train_end_dates))
        for train_end, (_, row) in zip(captured_train_end_dates, oof.iterrows()):
            self.assertLess(train_end, pd.Timestamp(row["issue_date"]))

    def test_build_contracts_keeps_existing_fields_and_adds_probability_metadata(self) -> None:
        service = ForecastService(db=None)

        contracts = service._build_contracts(
            virus_typ="Influenza A",
            region="DE",
            horizon_days=7,
            forecast_records=[
                {
                    "ds": pd.Timestamp("2026-03-21"),
                    "yhat": 123.0,
                    "yhat_lower": 110.0,
                    "yhat_upper": 140.0,
                }
            ],
            model_version="xgb_stack_direct_h7_inline",
            y_history=np.array([80.0, 90.0, 100.0, 110.0], dtype=float),
            issue_date=pd.Timestamp("2026-03-14").to_pydatetime(),
            quality_meta={
                "event_probability": 0.63,
                "forecast_ready": True,
                "drift_status": "ok",
                "confidence": 0.12,
                "reliability_score": 0.74,
                "backtest_quality_score": 0.81,
                "brier_score": 0.11,
                "ece": 0.04,
                "calibration_passed": True,
                "probability_source": "learned_exceedance_logistic_regression",
                "calibration_mode": "platt",
                "uncertainty_source": "backtest_interval_coverage",
                "fallback_reason": None,
                "fallback_used": False,
                "learned_model_version": "xgb_stack_direct_h7_inline",
            },
        )

        event = contracts["event_forecast"]
        self.assertIn("event_probability", event)
        self.assertIn("confidence", event)
        self.assertIn("reliability_score", event)
        self.assertIn("reliability_label", event)
        self.assertIn("backtest_quality_score", event)
        self.assertIn("event_signal_score", event)
        self.assertIn("signal_source", event)
        self.assertIn("probability_source", event)
        self.assertIn("calibration_mode", event)
        self.assertIn("uncertainty_source", event)
        self.assertIn("fallback_reason", event)
        self.assertEqual(event["event_probability"], 0.63)
        self.assertEqual(event["event_signal_score"], 0.63)
        self.assertEqual(event["confidence"], 0.74)
        self.assertEqual(event["reliability_score"], 0.74)
        self.assertEqual(event["reliability_label"], "Hoch")
        self.assertEqual(event["backtest_quality_score"], 0.81)
        self.assertEqual(event["signal_source"], "learned_exceedance_logistic_regression")
        self.assertEqual(event["probability_source"], "learned_exceedance_logistic_regression")
        self.assertEqual(event["calibration_mode"], "platt")
        self.assertEqual(event["uncertainty_source"], BACKTEST_RELIABILITY_PROXY_SOURCE)
        self.assertNotIn("confidence_semantics", event)

    def test_build_contracts_uses_heuristic_signal_when_probability_is_missing(self) -> None:
        service = ForecastService(db=None)

        contracts = service._build_contracts(
            virus_typ="Influenza A",
            region="DE",
            horizon_days=7,
            forecast_records=[
                {
                    "ds": pd.Timestamp("2026-03-21"),
                    "yhat": 130.0,
                    "yhat_lower": 120.0,
                    "yhat_upper": 140.0,
                }
            ],
            model_version="xgb_stack_direct_h7_inline",
            y_history=np.array([80.0, 90.0, 100.0, 110.0], dtype=float),
            issue_date=pd.Timestamp("2026-03-14").to_pydatetime(),
            quality_meta={
                "event_probability": None,
                "forecast_ready": False,
                "drift_status": "warning",
                "reliability_score": 0.52,
                "backtest_quality_score": 0.48,
                "probability_source": HEURISTIC_EVENT_SCORE_SOURCE,
                "calibration_mode": "raw_probability",
                "uncertainty_source": "backtest_interval_coverage",
                "fallback_reason": "no_learned_model",
                "fallback_used": True,
                "learned_model_version": None,
            },
        )

        event = contracts["event_forecast"]
        self.assertIsNone(event["event_probability"])
        self.assertIsNotNone(event["heuristic_event_score"])
        self.assertEqual(event["event_signal_score"], event["heuristic_event_score"])
        self.assertEqual(event["signal_source"], HEURISTIC_EVENT_SCORE_SOURCE)
        self.assertIsNone(event["probability_source"])
        self.assertEqual(event["reliability_label"], "Mittel")
        self.assertNotIn("confidence_semantics", event)

    def test_event_forecast_contract_keeps_existing_fields_and_adds_heuristic_score(self) -> None:
        event = EventForecast(
            event_key="influenza_a_growth_h7",
            horizon_days=7,
            event_probability=None,
            threshold_pct=25.0,
            baseline_value=100.0,
            threshold_value=125.0,
            calibration_method=HEURISTIC_EVENT_SCORE_SOURCE,
            heuristic_event_score=0.68,
            probability_source=HEURISTIC_EVENT_SCORE_SOURCE,
            fallback_used=None,
        ).to_dict()

        self.assertIn("event_probability", event)
        self.assertIn("heuristic_event_score", event)
        self.assertIn("probability_source", event)
        self.assertIn("signal_source", event)
        self.assertIsNone(event["event_probability"])
        self.assertEqual(event["heuristic_event_score"], 0.68)
        self.assertIsNone(event["probability_source"])
        self.assertEqual(event["event_signal_score"], 0.68)
        self.assertEqual(event["signal_source"], HEURISTIC_EVENT_SCORE_SOURCE)
        self.assertTrue(event["fallback_used"])

    def test_event_forecast_contract_uses_confidence_as_reliability_alias(self) -> None:
        event = EventForecast(
            event_key="influenza_a_growth_h7",
            horizon_days=7,
            event_probability=0.61,
            threshold_pct=25.0,
            baseline_value=100.0,
            threshold_value=125.0,
            calibration_method="learned_exceedance_logistic_regression:platt",
            confidence=0.12,
            reliability_score=0.73,
            uncertainty_source="backtest_interval_coverage",
        ).to_dict()

        self.assertEqual(event["event_signal_score"], 0.61)
        self.assertEqual(event["confidence"], 0.73)
        self.assertEqual(event["reliability_score"], 0.73)
        self.assertEqual(event["reliability_label"], "Hoch")
        self.assertNotIn("confidence_semantics", event)
        self.assertEqual(event["uncertainty_source"], BACKTEST_RELIABILITY_PROXY_SOURCE)


if __name__ == "__main__":
    unittest.main()
