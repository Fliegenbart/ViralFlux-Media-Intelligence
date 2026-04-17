"""Unit tests for Weighted Interval Score vs Bracher et al. 2021.

These tests pin the normalisation fix from ~/peix-math-deepdive.md finding #1.
Before the fix, WIS was inflated by ~4× because the implementation divided
by the sum of nominal interval weights (≈0.875) instead of ``K + 0.5`` as
prescribed by Bracher, Ray, Gneiting & Reich (PLOS Computational Biology,
2021, https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008618).

We validate against three analytical cases:

1. Median-only payload: WIS should collapse to the mean absolute error
   divided by the 0.5 normalisation (so WIS = MAE).
2. Perfect forecast (observation equals median, intervals wrap): WIS is
   the mean interval width weighted and normalised — no penalty terms.
3. Single-interval payload, observation outside the interval: reproduce
   the canonical Interval-Score formula by hand and check WIS equals
   the expected value after normalisation.

If any of these three break, the normalisation has drifted again.
"""
from __future__ import annotations

import unittest

import numpy as np

from app.services.ml.benchmarking.metrics import weighted_interval_score


class WeightedIntervalScoreBracherTests(unittest.TestCase):
    def test_median_only_reduces_to_mae_over_half(self) -> None:
        # K = 0 (no intervals), so WIS = (1 / 0.5) * 0.5 * |y - m|  =  |y - m|
        y_true = [100.0, 105.0, 95.0]
        payload = {0.5: [100.0, 100.0, 100.0]}
        expected = float(np.mean(np.abs(np.array(y_true) - 100.0)))
        got = weighted_interval_score(y_true, payload)
        self.assertAlmostEqual(got, expected, places=6)

    def test_perfect_point_inside_all_intervals(self) -> None:
        # y == median, and y is inside every interval → interval_score equals
        # the interval width alone (no penalty terms). WIS is a weighted mean
        # of widths divided by K + 0.5.
        y_true = [100.0, 100.0]
        payload = {
            0.025: [80.0, 80.0],
            0.1:   [85.0, 85.0],
            0.25:  [90.0, 90.0],
            0.5:   [100.0, 100.0],
            0.75:  [110.0, 110.0],
            0.9:   [115.0, 115.0],
            0.975: [120.0, 120.0],
        }
        # Three intervals (K=3). Median contribution: 0.5 * |y - m| = 0.
        # Interval contributions:
        #   α = 0.05 → width 40, weight 0.025 → 1.0
        #   α = 0.2  → width 30, weight 0.1   → 3.0
        #   α = 0.5  → width 20, weight 0.25  → 5.0
        # Σ = 9.0, divide by K + 0.5 = 3.5 → 2.5714…
        expected = 9.0 / 3.5
        got = weighted_interval_score(y_true, payload)
        self.assertAlmostEqual(got, expected, places=6)

    def test_single_interval_observation_outside(self) -> None:
        # One central 90 % interval only. Observation well above the upper
        # bound → penalty term dominates.
        # K = 1, normalisation = 1.5.
        # α = 0.2, weight = 0.1.
        # IS_0.2(F, y) = (upper - lower) + (2/α) * (y - upper) when y > upper
        #             = (120 - 80) + (2/0.2) * (150 - 120)
        #             = 40 + 10 * 30 = 340
        # Median contribution: 0.5 * |y - m| = 0.5 * |150 - 100| = 25
        # Total score per point: 25 + 0.1 * 340 = 25 + 34 = 59
        # WIS = 59 / 1.5 ≈ 39.3333
        y_true = [150.0]
        payload = {
            0.1: [80.0],
            0.5: [100.0],
            0.9: [120.0],
        }
        expected = 59.0 / 1.5
        got = weighted_interval_score(y_true, payload)
        self.assertAlmostEqual(got, expected, places=6)

    def test_sparse_grid_ignores_missing_pairs(self) -> None:
        # Only the 0.1/0.9 pair is supplied — 0.025/0.975 and 0.25/0.75 are
        # dropped silently. K must be 1, not 3, and WIS normalises by 1.5.
        y_true = [100.0]
        payload = {
            0.1: [90.0],
            0.5: [100.0],
            0.9: [110.0],
        }
        # Observation on median, inside interval.
        # IS_0.2 = (110 - 90) = 20. weight 0.1 → 2.0.
        # Median contribution: 0 (exact match).
        # WIS = 2.0 / 1.5 ≈ 1.3333
        expected = 2.0 / 1.5
        got = weighted_interval_score(y_true, payload)
        self.assertAlmostEqual(got, expected, places=6)


if __name__ == "__main__":
    unittest.main()
