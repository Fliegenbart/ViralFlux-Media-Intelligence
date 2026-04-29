import unittest

from app.services.media.cockpit.spending_decision_backtest import (
    evaluate_spending_decision_backtest,
)


def _artifact() -> dict:
    return {
        "details": {
            "NW": {
                "timeline": [
                    {
                        "as_of_date": "2026-01-01",
                        "target_week_start": "2026-01-08",
                        "event_probability_calibrated": 0.90,
                        "current_known_incidence": 12.0,
                        "expected_target_incidence": 24.0,
                        "next_week_incidence": 30.0,
                        "state_population_millions": 18.0,
                    },
                    {
                        "as_of_date": "2026-01-08",
                        "target_week_start": "2026-01-15",
                        "event_probability_calibrated": 0.85,
                        "current_known_incidence": 14.0,
                        "expected_target_incidence": 28.0,
                        "next_week_incidence": 32.0,
                        "state_population_millions": 18.0,
                    },
                ]
            },
            "BY": {
                "timeline": [
                    {
                        "as_of_date": "2026-01-01",
                        "target_week_start": "2026-01-08",
                        "event_probability_calibrated": 0.20,
                        "current_known_incidence": 28.0,
                        "expected_target_incidence": 20.0,
                        "next_week_incidence": 14.0,
                        "state_population_millions": 13.0,
                    },
                    {
                        "as_of_date": "2026-01-08",
                        "target_week_start": "2026-01-15",
                        "event_probability_calibrated": 0.15,
                        "current_known_incidence": 24.0,
                        "expected_target_incidence": 18.0,
                        "next_week_incidence": 12.0,
                        "state_population_millions": 13.0,
                    },
                ]
            },
        }
    }


class SpendingDecisionBacktestTests(unittest.TestCase):
    def test_decision_backtest_reports_capture_regret_and_baseline_rank(self) -> None:
        payload = evaluate_spending_decision_backtest(_artifact(), min_regret_reduction=0.01)

        self.assertTrue(payload["decision_backtest_passed"])
        self.assertGreater(payload["budget_weighted_event_capture"], 0.0)
        self.assertLess(payload["allocation_regret_vs_oracle"], payload["baselines"]["static_allocation"]["allocation_regret_vs_oracle"])
        self.assertGreater(payload["regret_reduction_vs_static"], 0.0)
        self.assertEqual(payload["model_rank_among_strategies"], 1)
        self.assertIn("highest_current_incidence_allocation", payload["baselines"])


if __name__ == "__main__":
    unittest.main()
