from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.ml.backtester import BacktestService
from app.services.ml.forecast_contracts import HEURISTIC_EVENT_SCORE_SOURCE


class BacktesterRefactorGuardTests(unittest.TestCase):
    @patch("app.services.ml.backtester_simulation.simulate_rows_from_target")
    def test_simulate_rows_from_target_wrapper_delegates_to_module(
        self,
        simulate_mock,
    ) -> None:
        simulate_mock.return_value = [{"date": "2024-01-08", "real_qty": 10.0}]
        service = BacktestService(db=None)

        result = service._simulate_rows_from_target(
            target_df="target-frame",
            virus_typ="Influenza A",
            horizon_days=7,
            delay_rules={"weather": 2},
            enhanced=True,
            target_disease="mycoplasma",
        )

        self.assertEqual(result, [{"date": "2024-01-08", "real_qty": 10.0}])
        simulate_mock.assert_called_once_with(
            service,
            target_df="target-frame",
            virus_typ="Influenza A",
            horizon_days=7,
            delay_rules={"weather": 2},
            enhanced=True,
            target_disease="mycoplasma",
        )

    @patch("app.services.ml.backtester_simulation.fit_regression_from_simulation")
    def test_fit_regression_from_simulation_wrapper_delegates_to_module(
        self,
        fit_mock,
    ) -> None:
        fit_mock.return_value = {"metrics": {"r2_score": 0.81}}
        service = BacktestService(db=None)

        result = service._fit_regression_from_simulation(
            df_sim="simulation-frame",
            virus_typ="RSV A",
            use_llm=False,
        )

        self.assertEqual(result, {"metrics": {"r2_score": 0.81}})
        fit_mock.assert_called_once_with(
            service,
            df_sim="simulation-frame",
            virus_typ="RSV A",
            use_llm=False,
        )

    @patch("app.services.ml.backtester_walk_forward.run_walk_forward_market_backtest")
    def test_run_walk_forward_market_backtest_wrapper_delegates_to_module(
        self,
        walk_forward_mock,
    ) -> None:
        walk_forward_mock.return_value = {"metrics": {"data_points": 3}}
        service = BacktestService(db=None)

        result = service._run_walk_forward_market_backtest(
            target_df="target-frame",
            virus_typ="Influenza A",
            horizon_days=7,
            min_train_points=12,
            delay_rules={"weather": 2},
            exclude_are=True,
            target_disease="mycoplasma",
        )

        self.assertEqual(result, {"metrics": {"data_points": 3}})
        walk_forward_mock.assert_called_once_with(
            service,
            target_df="target-frame",
            virus_typ="Influenza A",
            horizon_days=7,
            min_train_points=12,
            delay_rules={"weather": 2},
            exclude_are=True,
            target_disease="mycoplasma",
        )

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
