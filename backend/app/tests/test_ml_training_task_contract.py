import unittest
from contextlib import nullcontext
from unittest.mock import patch

from app.core.celery_app import celery_app
from app.services.ml.tasks import (
    refresh_regional_operational_snapshots_task,
    train_regional_models_task,
    train_xgboost_model_task,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES


class MLTrainingTaskContractTests(unittest.TestCase):
    def test_market_backtest_refresh_task_runs_all_supported_viruses(self) -> None:
        from app.services.ml.tasks import refresh_market_backtests_task

        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.backtester.BacktestService",
        ) as backtest_service_cls, patch.object(
            refresh_market_backtests_task,
            "update_state",
        ):
            backtest_service_cls.return_value.run_market_simulation.return_value = {
                "status": "success",
                "persisted_run_id": "bt-123",
            }

            result = refresh_market_backtests_task.run()

        self.assertEqual(result["virus_types"], list(SUPPORTED_VIRUS_TYPES))
        self.assertEqual(result["target_source"], "RKI_ARE")
        self.assertEqual(result["selection_mode"], "all")
        self.assertEqual(
            backtest_service_cls.return_value.run_market_simulation.call_count,
            len(SUPPORTED_VIRUS_TYPES),
        )
        self.assertEqual(
            [
                call.kwargs
                for call in backtest_service_cls.return_value.run_market_simulation.call_args_list
            ],
            [
                {
                    "virus_typ": virus,
                    "target_source": "RKI_ARE",
                    "strict_vintage_mode": True,
                }
                for virus in SUPPORTED_VIRUS_TYPES
            ],
        )

    def test_celery_schedule_refreshes_market_backtests_and_uses_valid_training_kwargs(self) -> None:
        schedule = celery_app.conf.beat_schedule

        refresh_entry = schedule["daily-market-backtest-refresh"]
        self.assertEqual(refresh_entry["task"], "refresh_market_backtests_task")
        self.assertEqual(refresh_entry["schedule"]._orig_hour, 6)
        self.assertEqual(refresh_entry["schedule"]._orig_minute, 10)
        self.assertEqual(refresh_entry["kwargs"], {})

        training_entry = schedule["daily-xgboost-training"]
        self.assertEqual(training_entry["kwargs"], {"virus_typ": None})

        snapshot_entry = schedule["daily-regional-operational-snapshot-refresh"]
        self.assertEqual(
            snapshot_entry["task"],
            "refresh_regional_operational_snapshots_task",
        )
        self.assertEqual(snapshot_entry["schedule"]._orig_hour, 7)
        self.assertEqual(snapshot_entry["schedule"]._orig_minute, 20)
        self.assertEqual(snapshot_entry["kwargs"], {})

    def test_snapshot_refresh_task_runs_all_supported_viruses(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ops.regional_operational_snapshot_refresh.RegionalOperationalSnapshotRefreshService",
        ) as refresh_service_cls, patch.object(
            refresh_regional_operational_snapshots_task,
            "update_state",
        ) as update_state:
            refresh_service_cls.return_value.refresh_supported_scopes.return_value = {
                "status": "success",
                "records_written": 8,
                "scope_count": 8,
            }

            result = refresh_regional_operational_snapshots_task.run()

        refresh_service_cls.return_value.refresh_supported_scopes.assert_called_once_with(
            virus_types=list(SUPPORTED_VIRUS_TYPES),
            horizon_days_list=None,
            weekly_budget_eur=50000.0,
            top_n=12,
        )
        self.assertEqual(result["virus_types"], list(SUPPORTED_VIRUS_TYPES))
        self.assertEqual(result["selection_mode"], "all")
        self.assertIsNone(result["virus_typ"])
        self.assertEqual(
            update_state.call_args_list[1].kwargs["meta"]["step"],
            "Refreshing regional operational snapshots...",
        )

    def test_run_without_selection_trains_all_supported_viruses(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.model_trainer.XGBoostTrainer",
        ) as trainer_cls, patch.object(
            train_xgboost_model_task,
            "update_state",
        ) as update_state:
            trainer_cls.return_value.train_all.return_value = {"ok": True}

            result = train_xgboost_model_task.run()

        trainer_cls.return_value.train_all.assert_called_once_with(
            virus_types=list(SUPPORTED_VIRUS_TYPES),
            include_internal_history=True,
            research_mode=False,
        )
        self.assertEqual(result["virus_types"], list(SUPPORTED_VIRUS_TYPES))
        self.assertEqual(result["selection_mode"], "all")
        self.assertIsNone(result["virus_typ"])
        self.assertEqual(update_state.call_args_list[1].kwargs["meta"]["step"], "Training all virus types...")

    def test_run_with_single_virus_uses_single_trainer_path(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.model_trainer.XGBoostTrainer",
        ) as trainer_cls, patch.object(
            train_xgboost_model_task,
            "update_state",
        ):
            trainer_cls.return_value.train.return_value = {"ok": True}

            result = train_xgboost_model_task.run(
                virus_typ="influenza a",
                include_internal_history=False,
                research_mode=True,
            )

        trainer_cls.return_value.train.assert_called_once_with(
            virus_typ="Influenza A",
            include_internal_history=False,
            research_mode=True,
        )
        trainer_cls.return_value.train_all.assert_not_called()
        self.assertEqual(result["virus_types"], ["Influenza A"])
        self.assertEqual(result["selection_mode"], "single")
        self.assertEqual(result["virus_typ"], "Influenza A")

    def test_run_with_subset_keeps_reported_selection_in_sync(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.model_trainer.XGBoostTrainer",
        ) as trainer_cls, patch.object(
            train_xgboost_model_task,
            "update_state",
        ) as update_state:
            trainer_cls.return_value.train_all.return_value = {"ok": True}

            result = train_xgboost_model_task.run(
                virus_types=["RSV A", "Influenza A"],
            )

        trainer_cls.return_value.train_all.assert_called_once_with(
            virus_types=["Influenza A", "RSV A"],
            include_internal_history=True,
            research_mode=False,
        )
        self.assertEqual(result["virus_types"], ["Influenza A", "RSV A"])
        self.assertEqual(result["selection_mode"], "subset")
        self.assertEqual(
            update_state.call_args_list[1].kwargs["meta"]["step"],
            "Training selected virus types...",
        )

    def test_conflicting_selectors_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            train_xgboost_model_task.run(
                virus_typ="Influenza A",
                virus_types=["Influenza B"],
            )

    def test_empty_selector_list_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            train_xgboost_model_task.run(virus_types=[])

    def test_regional_task_without_selection_trains_all_supported_viruses(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.regional_trainer.RegionalModelTrainer",
        ) as trainer_cls, patch.object(
            train_regional_models_task,
            "update_state",
        ) as update_state:
            trainer_cls.return_value.train_selected_viruses_all_regions.return_value = {
                virus: {"trained": 16, "failed": 0}
                for virus in SUPPORTED_VIRUS_TYPES
            }

            result = train_regional_models_task.run()

        trainer_cls.return_value.train_selected_viruses_all_regions.assert_called_once_with(
            virus_types=list(SUPPORTED_VIRUS_TYPES),
        )
        self.assertEqual(result["virus_types"], list(SUPPORTED_VIRUS_TYPES))
        self.assertEqual(result["selection_mode"], "all")
        self.assertIsNone(result["virus_typ"])
        self.assertEqual(
            update_state.call_args.kwargs["meta"]["step"],
            "Training regional models for all supported viruses...",
        )

    def test_regional_task_with_single_virus_uses_single_trainer_path(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.regional_trainer.RegionalModelTrainer",
        ) as trainer_cls, patch.object(
            train_regional_models_task,
            "update_state",
        ):
            trainer_cls.return_value.train_all_regions.return_value = {
                "status": "success",
                "trained": 16,
                "failed": 0,
                "aggregate_metrics": {"precision_at_top3": 0.2},
                "quality_gate": {"forecast_readiness": "WATCH"},
            }

            result = train_regional_models_task.run(virus_typ="influenza a")

        trainer_cls.return_value.train_all_regions.assert_called_once_with(virus_typ="Influenza A")
        trainer_cls.return_value.train_selected_viruses_all_regions.assert_not_called()
        self.assertEqual(result["virus_types"], ["Influenza A"])
        self.assertEqual(result["selection_mode"], "single")
        self.assertEqual(result["virus_typ"], "Influenza A")

    def test_regional_task_with_subset_keeps_reported_selection_in_sync(self) -> None:
        with patch(
            "app.services.ml.tasks.get_db_context",
            return_value=nullcontext(object()),
        ), patch(
            "app.services.ml.regional_trainer.RegionalModelTrainer",
        ) as trainer_cls, patch.object(
            train_regional_models_task,
            "update_state",
        ) as update_state:
            trainer_cls.return_value.train_selected_viruses_all_regions.return_value = {
                "Influenza A": {"trained": 16, "failed": 0, "quality_gate": {"forecast_readiness": "WATCH"}},
                "RSV A": {"trained": 16, "failed": 0, "quality_gate": {"forecast_readiness": "WATCH"}},
            }

            result = train_regional_models_task.run(virus_types=["RSV A", "Influenza A"])

        trainer_cls.return_value.train_selected_viruses_all_regions.assert_called_once_with(
            virus_types=["Influenza A", "RSV A"],
        )
        self.assertEqual(result["virus_types"], ["Influenza A", "RSV A"])
        self.assertEqual(result["selection_mode"], "subset")
        self.assertEqual(
            update_state.call_args.kwargs["meta"]["step"],
            "Training regional models for selected viruses...",
        )


if __name__ == "__main__":
    unittest.main()
