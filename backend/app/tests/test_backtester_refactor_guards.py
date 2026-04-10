from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.ml.backtester import BacktestService
from app.services.ml.forecast_contracts import HEURISTIC_EVENT_SCORE_SOURCE


class BacktesterRefactorGuardTests(unittest.TestCase):
    @patch("app.services.ml.backtester_metrics.compute_decision_metrics")
    def test_compute_decision_metrics_wrapper_delegates_with_quality_targets(
        self,
        compute_mock,
    ) -> None:
        compute_mock.return_value = {"alerts": 2}

        result = BacktestService._compute_decision_metrics(
            [{"issue_date": "2024-01-01", "target_date": "2024-01-08", "y_hat": 10.0, "y_true": 12.0}],
            threshold_pct=30.0,
            vintage_metrics={"p90_abs_error": 4.2},
        )

        self.assertEqual(result, {"alerts": 2})
        compute_mock.assert_called_once_with(
            [{"issue_date": "2024-01-01", "target_date": "2024-01-08", "y_hat": 10.0, "y_true": 12.0}],
            threshold_pct=30.0,
            vintage_metrics={"p90_abs_error": 4.2},
            decision_baseline_window_days=BacktestService.DECISION_BASELINE_WINDOW_DAYS,
            quality_gate_ttd_target_days=BacktestService.QUALITY_GATE_TTD_TARGET_DAYS,
            quality_gate_hit_rate_target_pct=BacktestService.QUALITY_GATE_HIT_RATE_TARGET_PCT,
            quality_gate_p90_error_rel_target_pct=BacktestService.QUALITY_GATE_P90_ERROR_REL_TARGET_PCT,
        )

    @patch("app.services.ml.backtester_metrics.compute_event_calibration_metrics")
    def test_event_calibration_wrapper_delegates_with_contract_inputs(
        self,
        calibration_mock,
    ) -> None:
        calibration_mock.return_value = {"samples": 4}

        result = BacktestService._compute_event_calibration_metrics(
            [{"issue_date": "2024-01-01", "target_date": "2024-01-08", "y_true": 12.0, "p_event": 0.7}],
            threshold_pct=25.0,
        )

        self.assertEqual(result, {"samples": 4})
        calibration_mock.assert_called_once_with(
            [{"issue_date": "2024-01-01", "target_date": "2024-01-08", "y_true": 12.0, "p_event": 0.7}],
            threshold_pct=25.0,
            decision_baseline_window_days=BacktestService.DECISION_BASELINE_WINDOW_DAYS,
            heuristic_event_score_source=HEURISTIC_EVENT_SCORE_SOURCE,
        )

    @patch("app.services.ml.backtester_metrics.build_quality_gate")
    def test_build_quality_gate_wrapper_delegates_with_targets(self, gate_mock) -> None:
        gate_mock.return_value = {"forecast_readiness": "GO"}

        result = BacktestService._build_quality_gate(
            {"median_ttd_days": 14},
            timing_metrics={"best_lag_days": 14},
            improvement_vs_baselines={"mae_vs_persistence_pct": 1.0, "mae_vs_seasonal_pct": 1.0},
        )

        self.assertEqual(result, {"forecast_readiness": "GO"})
        gate_mock.assert_called_once_with(
            {"median_ttd_days": 14},
            {"best_lag_days": 14},
            improvement_vs_baselines={"mae_vs_persistence_pct": 1.0, "mae_vs_seasonal_pct": 1.0},
            interval_coverage=None,
            event_calibration=None,
            quality_gate_ttd_target_days=BacktestService.QUALITY_GATE_TTD_TARGET_DAYS,
            quality_gate_hit_rate_target_pct=BacktestService.QUALITY_GATE_HIT_RATE_TARGET_PCT,
            quality_gate_p90_error_rel_target_pct=BacktestService.QUALITY_GATE_P90_ERROR_REL_TARGET_PCT,
            quality_gate_lead_target_days=BacktestService.QUALITY_GATE_LEAD_TARGET_DAYS,
        )

    @patch("app.services.ml.backtester_metrics.sanitize_for_json")
    def test_sanitize_for_json_wrapper_delegates(self, sanitize_mock) -> None:
        sanitize_mock.return_value = {"ok": True}

        result = BacktestService._sanitize_for_json({"value": float("inf")})

        self.assertEqual(result, {"ok": True})
        sanitize_mock.assert_called_once_with({"value": float("inf")})
