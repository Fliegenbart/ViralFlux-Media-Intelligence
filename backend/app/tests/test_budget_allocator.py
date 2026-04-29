import unittest

from app.services.media.cockpit.budget_allocator import (
    BudgetAllocatorConfig,
    allocate_budget_deltas,
)


class BudgetAllocatorTests(unittest.TestCase):
    def test_allocator_conserves_total_budget_and_respects_caps(self) -> None:
        result = allocate_budget_deltas(
            [
                {"region_code": "NW", "budget_opportunity_score": 0.80, "base_budget_eur": 12000, "max_delta_pct": 15},
                {"region_code": "BY", "budget_opportunity_score": 0.50, "base_budget_eur": 10000, "max_delta_pct": 15},
                {"region_code": "SN", "budget_opportunity_score": 0.20, "base_budget_eur": 8000, "max_delta_pct": 15},
            ],
            config=BudgetAllocatorConfig(max_weekly_shift_pct=15),
        )

        rows = result["regions"]
        self.assertAlmostEqual(sum(row["recommended_delta_pct"] for row in rows), 0.0, places=6)
        self.assertAlmostEqual(
            sum(row["before_budget_eur"] for row in rows),
            sum(row["after_budget_eur"] for row in rows),
            places=2,
        )
        self.assertLessEqual(max(abs(row["recommended_delta_pct"]) for row in rows), 15.0)
        self.assertGreater(next(row for row in rows if row["region_code"] == "NW")["recommended_delta_pct"], 0.0)
        self.assertLess(next(row for row in rows if row["region_code"] == "SN")["recommended_delta_pct"], 0.0)

    def test_uncertainty_cap_reduces_delta(self) -> None:
        result = allocate_budget_deltas(
            [
                {"region_code": "NW", "budget_opportunity_score": 0.95, "base_budget_eur": 10000, "max_delta_pct": 15, "uncertainty_capped": True},
                {"region_code": "BY", "budget_opportunity_score": 0.05, "base_budget_eur": 10000, "max_delta_pct": 15},
            ],
            config=BudgetAllocatorConfig(max_weekly_shift_pct=15, uncertainty_shift_cap_pct=5),
        )

        nw = next(row for row in result["regions"] if row["region_code"] == "NW")
        self.assertLessEqual(abs(nw["recommended_delta_pct"]), 5.0)


if __name__ == "__main__":
    unittest.main()
