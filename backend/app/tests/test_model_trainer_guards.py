import unittest

from app.services.ml.model_trainer import XGBoostTrainer


class ModelTrainerGuardTests(unittest.TestCase):
    def test_should_promote_when_no_existing_metrics(self) -> None:
        self.assertTrue(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics=None,
                candidate_metrics={"relative_wis": 0.92, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            )
        )

    def test_should_not_promote_worse_candidate(self) -> None:
        self.assertFalse(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics={"relative_wis": 0.95, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
                candidate_metrics={"relative_wis": 0.97, "coverage_95": 0.92, "brier_score": 0.09, "ece": 0.05},
            )
        )

    def test_select_best_candidate_prefers_lower_relative_wis_then_pinball_then_ece(self) -> None:
        best = XGBoostTrainer._select_best_candidate(
            [
                {
                    "name": "baseline",
                    "backtest_metrics": {"relative_wis": 0.98, "pinball_loss": 1.8, "ece": 0.06},
                },
                {
                    "name": "history",
                    "backtest_metrics": {"relative_wis": 0.95, "pinball_loss": 1.9, "ece": 0.05},
                },
                {
                    "name": "history_b",
                    "backtest_metrics": {"relative_wis": 0.95, "pinball_loss": 1.7, "ece": 0.07},
                },
                {
                    "name": "invalid",
                    "backtest_metrics": {"error": "boom"},
                },
            ]
        )

        self.assertIsNotNone(best)
        self.assertEqual(best["name"], "history_b")


if __name__ == "__main__":
    unittest.main()
