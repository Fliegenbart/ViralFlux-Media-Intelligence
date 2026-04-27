import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_holdout_snapshot.py"
SPEC = importlib.util.spec_from_file_location("run_holdout_snapshot", SCRIPT_PATH)
holdout = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = holdout
SPEC.loader.exec_module(holdout)


class _FakeResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _FakeDb:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql = str(sql)
        self.params = dict(params)
        return _FakeResult()


class HoldoutSnapshotHelperTests(unittest.TestCase):
    def test_safe_mean_ignores_nan_and_infinite_values(self):
        self.assertEqual(holdout._safe_mean([1.0, float("nan"), 3.0, float("inf")]), 2.0)

    def test_safe_mean_returns_none_for_no_clean_values(self):
        self.assertIsNone(holdout._safe_mean([float("nan"), float("-inf")]))

    def test_pearson_reports_perfect_positive_correlation(self):
        self.assertAlmostEqual(holdout._pearson([1, 2, 3], [2, 4, 6]), 1.0)

    def test_pearson_returns_none_for_constant_vector(self):
        self.assertIsNone(holdout._pearson([1, 1, 1], [2, 3, 4]))

    def test_precision_at_k_returns_overlap_and_rankings(self):
        score, actual_top, forecast_top = holdout._precision_at_k(
            {"Bayern": 10, "Berlin": 8, "Hamburg": 7},
            {"Berlin": 9, "Sachsen": 6, "Bayern": 5},
            k=3,
        )

        self.assertAlmostEqual(score, 2 / 3)
        self.assertEqual(actual_top, ["Bayern", "Berlin", "Hamburg"])
        self.assertEqual(forecast_top, ["Berlin", "Sachsen", "Bayern"])

    def test_round_or_none_preserves_none(self):
        self.assertIsNone(holdout._round_or_none(None))
        self.assertEqual(holdout._round_or_none(1.23456, 2), 1.23)

    def test_normalise_region_maps_iso_codes(self):
        self.assertEqual(holdout._normalise_region("DE-BY"), "Bayern")
        self.assertEqual(holdout._normalise_region(" Hessen "), "Hessen")

    def test_fetch_forecasts_defaults_to_pre_week_holdout_cutoff(self):
        db = _FakeDb()

        holdout._fetch_forecasts(
            db,
            virus="Influenza A",
            horizon_days=7,
            week_start="2026-01-12",
        )

        self.assertIn(
            "created_at::date < (:week_start::date - (:horizon_days || ' days')::interval)",
            db.sql,
        )
        self.assertEqual(db.params["horizon_days"], 7)


if __name__ == "__main__":
    unittest.main()
