import unittest
from contextlib import nullcontext
from unittest.mock import patch

from app.services.ml.tasks import train_xgboost_model_task
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES


class MLTrainingTaskContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
