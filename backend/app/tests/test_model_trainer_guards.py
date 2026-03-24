import unittest

from app.services.ml.model_trainer import XGBoostTrainer


class ModelTrainerGuardTests(unittest.TestCase):
    def test_should_promote_when_no_existing_metrics(self) -> None:
        self.assertTrue(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics=None,
                candidate_metrics={"relative_wis": 0.92, "crps": 1.1, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            )
        )

    def test_should_not_promote_worse_candidate(self) -> None:
        self.assertFalse(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics={"relative_wis": 0.95, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
                candidate_metrics={"relative_wis": 0.97, "crps": 1.3, "coverage_95": 0.92, "brier_score": 0.09, "ece": 0.05},
            )
        )

    def test_select_best_candidate_prefers_lower_relative_wis_then_crps_then_coverage(self) -> None:
        best = XGBoostTrainer._select_best_candidate(
            [
                {
                    "name": "baseline",
                    "backtest_metrics": {"relative_wis": 0.98, "crps": 1.4, "pinball_loss": 1.8, "ece": 0.06, "coverage_95": 0.95},
                },
                {
                    "name": "history",
                    "backtest_metrics": {"relative_wis": 0.95, "crps": 1.2, "pinball_loss": 1.9, "ece": 0.05, "coverage_95": 0.94},
                },
                {
                    "name": "history_b",
                    "backtest_metrics": {"relative_wis": 0.95, "crps": 1.1, "pinball_loss": 1.7, "ece": 0.07, "coverage_95": 0.93},
                },
                {
                    "name": "invalid",
                    "backtest_metrics": {"error": "boom"},
                },
            ]
        )

        self.assertIsNotNone(best)
        self.assertEqual(best["name"], "history_b")

    def test_should_not_promote_when_crps_is_materially_worse(self) -> None:
        self.assertFalse(
            XGBoostTrainer._should_promote_candidate(
                existing_metrics={"relative_wis": 1.0, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04, "decision_utility": 0.7},
                candidate_metrics={"relative_wis": 0.97, "crps": 1.3, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04, "decision_utility": 0.7},
            )
        )


if __name__ == "__main__":
    unittest.main()
