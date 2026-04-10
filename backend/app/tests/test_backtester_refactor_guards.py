from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch

import app.services.ml.backtester as backtester
from app.services.ml.backtester import BacktestService
from app.services.ml.forecast_contracts import HEURISTIC_EVENT_SCORE_SOURCE


class BacktesterRefactorGuardTests(unittest.TestCase):
    @patch("app.services.ml.backtester_signals.asof_filter")
    def test_asof_filter_wrapper_delegates_to_module(self, signals_mock) -> None:
        signals_mock.return_value = "filter-clause"
        service = BacktestService(db=None)

        result = service._asof_filter("model", "event_col", datetime(2026, 4, 10, 12, 0, 0))

        self.assertEqual(result, "filter-clause")
        signals_mock.assert_called_once_with(
            service,
            "model",
            "event_col",
            datetime(2026, 4, 10, 12, 0, 0),
            and_fn=backtester.and_,
            or_fn=backtester.or_,
        )

    @patch("app.services.ml.backtester_signals.market_proxy_at_date")
    def test_market_proxy_wrapper_delegates_to_module(self, signals_mock) -> None:
        signals_mock.return_value = 0.77
        service = BacktestService(db=None)

        result = service._market_proxy_at_date(
            datetime(2026, 4, 10),
            bio=0.5,
            wastewater=0.7,
            positivity=0.2,
        )

        self.assertEqual(result, 0.77)
        signals_mock.assert_called_once_with(
            datetime(2026, 4, 10),
            bio=0.5,
            wastewater=0.7,
            positivity=0.2,
        )

    @patch("app.services.ml.backtester_signals.compute_sub_scores_at_date")
    def test_compute_sub_scores_wrapper_delegates_to_module(self, signals_mock) -> None:
        signals_mock.return_value = {"bio": 0.4}
        service = BacktestService(db=None)

        result = service._compute_sub_scores_at_date(
            datetime(2026, 4, 10),
            "Influenza A",
            delay_rules={"weather": 2},
            target_disease="mycoplasma",
        )

        self.assertEqual(result, {"bio": 0.4})
        signals_mock.assert_called_once_with(
            service,
            datetime(2026, 4, 10),
            "Influenza A",
            delay_rules={"weather": 2},
            target_disease="mycoplasma",
            timedelta_cls=backtester.timedelta,
        )

    @patch("app.services.ml.backtester_autoregressive.build_survstat_ar_row")
    def test_build_survstat_ar_row_wrapper_delegates_to_module(
        self,
        autoregressive_mock,
    ) -> None:
        autoregressive_mock.return_value = {"y_lag1": 1.0}

        result = BacktestService._build_survstat_ar_row(
            series="series",
            idx=12,
            target_date="2026-01-01",
        )

        self.assertEqual(result, {"y_lag1": 1.0})
        autoregressive_mock.assert_called_once_with(
            series="series",
            idx=12,
            target_date="2026-01-01",
            xgboost_survstat_features=BacktestService.XGBOOST_SURVSTAT_FEATURES,
        )

    @patch("app.services.ml.backtester_autoregressive.build_survstat_ar_training_data")
    def test_build_survstat_ar_training_data_wrapper_delegates_to_module(
        self,
        autoregressive_mock,
    ) -> None:
        autoregressive_mock.return_value = ("X", "y")
        service = BacktestService(db=None)

        result = service._build_survstat_ar_training_data("train-frame")

        self.assertEqual(result, ("X", "y"))
        autoregressive_mock.assert_called_once_with(
            "train-frame",
            xgboost_survstat_features=BacktestService.XGBOOST_SURVSTAT_FEATURES,
            build_survstat_ar_row_fn=service._build_survstat_ar_row,
        )

    @patch("app.services.ml.backtester_targets.resolve_survstat_disease")
    def test_resolve_survstat_disease_wrapper_delegates_to_module(
        self,
        targets_mock,
    ) -> None:
        targets_mock.return_value = "Influenza, saisonal"
        service = BacktestService(db=None)

        result = service._resolve_survstat_disease("SURVSTAT")

        self.assertEqual(result, "Influenza, saisonal")
        targets_mock.assert_called_once_with(
            service,
            "SURVSTAT",
        )

    @patch("app.services.ml.backtester_targets.load_market_target")
    def test_load_market_target_wrapper_delegates_to_module(
        self,
        targets_mock,
    ) -> None:
        sentinel = ("frame", {"target_key": "RKI_ARE"})
        targets_mock.return_value = sentinel
        service = BacktestService(db=None)

        result = service._load_market_target(
            target_source="RKI_ARE",
            days_back=365,
            bundesland="Berlin",
        )

        self.assertEqual(result, sentinel)
        targets_mock.assert_called_once_with(
            service,
            target_source="RKI_ARE",
            days_back=365,
            bundesland="Berlin",
        )

    @patch("app.services.ml.backtester_targets.build_planning_curve")
    def test_build_planning_curve_wrapper_delegates_to_module(
        self,
        targets_mock,
    ) -> None:
        sentinel = {"lead_days": 14, "curve": []}
        targets_mock.return_value = sentinel
        service = BacktestService(db=None)

        result = service._build_planning_curve(
            target_df="target-frame",
            virus_typ="Influenza A",
            days_back=1200,
        )

        self.assertEqual(result, sentinel)
        targets_mock.assert_called_once_with(
            service,
            target_df="target-frame",
            virus_typ="Influenza A",
            days_back=1200,
        )

    @patch("app.services.ml.backtester_persistence.persist_backtest_result")
    def test_persist_backtest_result_wrapper_delegates_to_module(
        self,
        persistence_mock,
    ) -> None:
        persistence_mock.return_value = "bt_123"
        service = BacktestService(db=None)

        result = service._persist_backtest_result(
            mode="MARKET_CHECK",
            virus_typ="Influenza A",
            target_source="RKI_ARE",
            target_key="RKI_ARE",
            target_label="RKI ARE",
            result={"metrics": {"r2_score": 0.5}},
            parameters={"strict_vintage_mode": True},
        )

        self.assertEqual(result, "bt_123")
        persistence_mock.assert_called_once_with(
            service,
            mode="MARKET_CHECK",
            virus_typ="Influenza A",
            target_source="RKI_ARE",
            target_key="RKI_ARE",
            target_label="RKI ARE",
            result={"metrics": {"r2_score": 0.5}},
            parameters={"strict_vintage_mode": True},
            pd_module=backtester.pd,
            uuid4_fn=backtester.uuid4,
            logger_obj=backtester.logger,
        )

    @patch("app.services.ml.backtester_persistence.list_backtest_runs")
    def test_list_backtest_runs_wrapper_delegates_to_module(
        self,
        persistence_mock,
    ) -> None:
        persistence_mock.return_value = [{"run_id": "bt_123"}]
        service = BacktestService(db=None)

        result = service.list_backtest_runs(mode="MARKET_CHECK", limit=15)

        self.assertEqual(result, [{"run_id": "bt_123"}])
        persistence_mock.assert_called_once_with(
            service,
            mode="MARKET_CHECK",
            limit=15,
        )

    @patch("app.services.ml.backtester_persistence.get_backtest_run")
    def test_get_backtest_run_wrapper_delegates_to_module(
        self,
        persistence_mock,
    ) -> None:
        persistence_mock.return_value = {"run_id": "bt_123"}
        service = BacktestService(db=None)

        result = service.get_backtest_run("bt_123")

        self.assertEqual(result, {"run_id": "bt_123"})
        persistence_mock.assert_called_once_with(
            service,
            "bt_123",
        )

    @patch("app.services.ml.backtester_explanations.generate_llm_insight")
    def test_generate_llm_insight_wrapper_delegates_to_module(
        self,
        explanations_mock,
    ) -> None:
        explanations_mock.return_value = "LLM summary"
        service = BacktestService(db=None)

        result = service._generate_llm_insight(
            weights={"bio": 0.6, "market": 0.4},
            r2=0.71,
            correlation=0.82,
            mae=14.0,
            n_samples=42,
            virus_typ="Influenza A",
        )

        self.assertEqual(result, "LLM summary")
        explanations_mock.assert_called_once_with(
            service,
            weights={"bio": 0.6, "market": 0.4},
            r2=0.71,
            correlation=0.82,
            mae=14.0,
            n_samples=42,
            virus_typ="Influenza A",
            logger_obj=backtester.logger,
        )

    @patch("app.services.ml.backtester_explanations.map_feature_to_factor")
    def test_map_feature_to_factor_wrapper_delegates_to_module(
        self,
        explanations_mock,
    ) -> None:
        explanations_mock.return_value = "bio"
        service = BacktestService(db=None)

        result = service._map_feature_to_factor("ww_lag1w")

        self.assertEqual(result, "bio")
        explanations_mock.assert_called_once_with("ww_lag1w")

    @patch("app.services.ml.backtester_explanations.canonicalize_factor_weights")
    def test_canonicalize_factor_weights_wrapper_delegates_to_module(
        self,
        explanations_mock,
    ) -> None:
        explanations_mock.return_value = {"bio": 0.5, "market": 0.5}
        service = BacktestService(db=None)

        result = service._canonicalize_factor_weights({"ww_lag1w": 0.7, "trend": 0.3})

        self.assertEqual(result, {"bio": 0.5, "market": 0.5})
        explanations_mock.assert_called_once_with(
            service,
            {"ww_lag1w": 0.7, "trend": 0.3},
            np_module=backtester.np,
            map_feature_to_factor_fn=service._map_feature_to_factor,
        )

    @patch("app.services.ml.backtester_reporting.run_global_calibration")
    def test_run_global_calibration_wrapper_delegates_to_module(
        self,
        reporting_mock,
    ) -> None:
        reporting_mock.return_value = {"status": "success", "data_points": 52}
        service = BacktestService(db=None)

        result = service.run_global_calibration(
            virus_typ="RSV A",
            days_back=730,
        )

        self.assertEqual(result, {"status": "success", "data_points": 52})
        reporting_mock.assert_called_once_with(
            service,
            virus_typ="RSV A",
            days_back=730,
        )

    @patch("app.services.ml.backtester_reporting.save_global_defaults")
    def test_save_global_defaults_wrapper_delegates_to_module(
        self,
        reporting_mock,
    ) -> None:
        service = BacktestService(db=None)

        service._save_global_defaults(
            {"bio": 0.4, "market": 0.3, "psycho": 0.1, "context": 0.2},
            0.82,
            300,
        )

        reporting_mock.assert_called_once_with(
            service,
            {"bio": 0.4, "market": 0.3, "psycho": 0.1, "context": 0.2},
            0.82,
            300,
        )

    @patch("app.services.ml.backtester_reporting.generate_business_pitch_report")
    def test_generate_business_pitch_report_wrapper_delegates_to_module(
        self,
        reporting_mock,
    ) -> None:
        reporting_mock.return_value = {"status": "success", "ttd_advantage_days": 9}
        service = BacktestService(db=None)

        result = service.generate_business_pitch_report(
            disease=["Influenza, saisonal", "RSV (Meldepflicht gemäß IfSG)"],
            virus_typ="Influenza A",
            season_start="2024-10-01",
            season_end="2025-03-31",
            output_path="/tmp/report.csv",
        )

        self.assertEqual(result, {"status": "success", "ttd_advantage_days": 9})
        reporting_mock.assert_called_once_with(
            service,
            disease=["Influenza, saisonal", "RSV (Meldepflicht gemäß IfSG)"],
            virus_typ="Influenza A",
            season_start="2024-10-01",
            season_end="2025-03-31",
            output_path="/tmp/report.csv",
        )

    @patch("app.services.ml.backtester_workflows.run_market_simulation")
    def test_run_market_simulation_wrapper_delegates_to_module(
        self,
        workflow_mock,
    ) -> None:
        workflow_mock.return_value = {"mode": "MARKET_CHECK", "metrics": {"data_points": 12}}
        service = BacktestService(db=None)

        result = service.run_market_simulation(
            virus_typ="RSV A",
            target_source="RKI_SURVSTAT",
            days_back=365,
            horizon_days=14,
            min_train_points=24,
            delay_rules={"weather": 2},
            strict_vintage_mode=False,
            bundesland="Berlin",
        )

        self.assertEqual(result, {"mode": "MARKET_CHECK", "metrics": {"data_points": 12}})
        workflow_mock.assert_called_once_with(
            service,
            virus_typ="RSV A",
            target_source="RKI_SURVSTAT",
            days_back=365,
            horizon_days=14,
            min_train_points=24,
            delay_rules={"weather": 2},
            strict_vintage_mode=False,
            bundesland="Berlin",
        )

    @patch("app.services.ml.backtester_workflows.run_customer_simulation")
    def test_run_customer_simulation_wrapper_delegates_to_module(
        self,
        workflow_mock,
    ) -> None:
        workflow_mock.return_value = {"mode": "CUSTOMER_CHECK", "metrics": {"data_points": 18}}
        service = BacktestService(db=None)

        result = service.run_customer_simulation(
            customer_df="customer-frame",
            virus_typ="Influenza A",
            horizon_days=7,
            min_train_points=20,
            strict_vintage_mode=True,
        )

        self.assertEqual(result, {"mode": "CUSTOMER_CHECK", "metrics": {"data_points": 18}})
        workflow_mock.assert_called_once_with(
            service,
            customer_df="customer-frame",
            virus_typ="Influenza A",
            horizon_days=7,
            min_train_points=20,
            strict_vintage_mode=True,
        )

    @patch("app.services.ml.backtester_workflows.run_calibration")
    def test_run_calibration_wrapper_delegates_to_module(
        self,
        workflow_mock,
    ) -> None:
        workflow_mock.return_value = {"mode": "CALIBRATION_OOS", "metrics": {"data_points": 9}}
        service = BacktestService(db=None)

        result = service.run_calibration(
            customer_df="customer-frame",
            virus_typ="Influenza B",
            horizon_days=10,
            min_train_points=22,
            strict_vintage_mode=False,
        )

        self.assertEqual(result, {"mode": "CALIBRATION_OOS", "metrics": {"data_points": 9}})
        workflow_mock.assert_called_once_with(
            service,
            customer_df="customer-frame",
            virus_typ="Influenza B",
            horizon_days=10,
            min_train_points=22,
            strict_vintage_mode=False,
        )

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
