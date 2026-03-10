import unittest

from app.services.ml.model_trainer import XGBoostTrainer


class ModelTrainerGuardTests(unittest.TestCase):
    def test_should_promote_when_no_existing_metrics(self) -> None:
        self.assertTrue(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics=None,
                candidate_metrics={"mape": 18.0, "rmse": 3.1},
            )
        )

    def test_should_not_promote_worse_candidate(self) -> None:
        self.assertFalse(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics={"mape": 12.0, "rmse": 2.4},
                candidate_metrics={"mape": 14.0, "rmse": 2.0},
            )
        )

    def test_select_best_candidate_prefers_lower_mape_then_rmse(self) -> None:
        best = XGBoostTrainer._select_best_candidate(
            [
                {
                    "name": "baseline",
                    "backtest_metrics": {"mape": 14.0, "rmse": 2.5},
                },
                {
                    "name": "history",
                    "backtest_metrics": {"mape": 14.0, "rmse": 2.1},
                },
                {
                    "name": "invalid",
                    "backtest_metrics": {"error": "boom"},
                },
            ]
        )

        self.assertIsNotNone(best)
        self.assertEqual(best["name"], "history")


if __name__ == "__main__":
    unittest.main()
