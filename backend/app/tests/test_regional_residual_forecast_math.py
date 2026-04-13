import unittest

import numpy as np
import pandas as pd

from app.services.ml.regional_residual_forecast import (
    _quantile_for_mixture,
    baseline_component_logs,
    mixture_cdf_value,
    mixture_quantiles_via_cdf,
    optimize_baseline_weights,
    optimize_persistence_mix_weight,
    quantile_cdf,
)


class RegionalResidualForecastMathTests(unittest.TestCase):
    def test_baseline_component_logs_build_leave_one_region_out_signal(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(
                    [
                        "2026-01-01",
                        "2026-01-01",
                        "2026-01-01",
                        "2026-01-08",
                        "2026-01-08",
                        "2026-01-08",
                    ]
                ),
                "bundesland": ["BY", "BE", "NW", "BY", "BE", "NW"],
                "current_known_incidence": [10.0, 20.0, 40.0, 12.0, 24.0, 48.0],
                "seasonal_baseline": [8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
            }
        )

        components = baseline_component_logs(frame)
        pooled = np.expm1(components["pooled_log"])

        np.testing.assert_allclose(
            pooled,
            np.array([30.0, 25.0, 15.0, 36.0, 30.0, 18.0], dtype=float),
            rtol=1e-6,
            atol=1e-6,
        )

    def test_optimize_baseline_weights_prefers_current_level_when_target_is_persistent(self) -> None:
        dates = pd.date_range("2026-01-01", periods=12, freq="7D")
        frame = pd.DataFrame(
            {
                "as_of_date": list(dates) * 2,
                "bundesland": ["BY"] * len(dates) + ["BE"] * len(dates),
                "current_known_incidence": np.concatenate(
                    [
                        np.linspace(10.0, 21.0, len(dates)),
                        np.linspace(18.0, 29.0, len(dates)),
                    ]
                ),
                "seasonal_baseline": np.full(len(dates) * 2, 6.0, dtype=float),
            }
        )
        frame["next_week_incidence"] = frame["current_known_incidence"].astype(float)

        result = optimize_baseline_weights(frame, candidate_step=0.5)

        self.assertGreaterEqual(result["weights"]["current_log"], result["weights"]["seasonal_log"])
        self.assertGreaterEqual(result["weights"]["current_log"], result["weights"]["pooled_log"])
        self.assertGreater(result["diagnostics"]["evaluated_candidates"], 1)

    def test_mixture_quantiles_via_cdf_invert_the_mixed_distribution(self) -> None:
        model_quantiles = {
            0.1: np.array([10.0], dtype=float),
            0.5: np.array([20.0], dtype=float),
            0.9: np.array([120.0], dtype=float),
        }
        baseline_quantiles = {
            0.1: np.array([5.0], dtype=float),
            0.5: np.array([15.0], dtype=float),
            0.9: np.array([25.0], dtype=float),
        }

        mixed = mixture_quantiles_via_cdf(
            model_quantiles=model_quantiles,
            baseline_quantiles=baseline_quantiles,
            mixture_weight=0.5,
            output_quantiles=(0.1, 0.5, 0.9),
        )
        mixed_q90 = float(mixed[0.9][0])
        mixed_cdf = mixture_cdf_value(
            mixed_q90,
            model_quantiles={quantile: float(values[0]) for quantile, values in model_quantiles.items()},
            baseline_quantiles={quantile: float(values[0]) for quantile, values in baseline_quantiles.items()},
            mixture_weight=0.5,
        )

        self.assertAlmostEqual(mixed_cdf, 0.9, delta=0.02)
        self.assertNotAlmostEqual(mixed_q90, 72.5, delta=1.0)

    def test_mixture_quantiles_via_cdf_matches_scalar_inversion_samplewise(self) -> None:
        model_quantiles = {
            0.025: np.array([4.0, 6.0], dtype=float),
            0.1: np.array([7.0, 9.0], dtype=float),
            0.25: np.array([10.0, 12.0], dtype=float),
            0.5: np.array([14.0, 18.0], dtype=float),
            0.75: np.array([22.0, 28.0], dtype=float),
            0.9: np.array([40.0, 55.0], dtype=float),
            0.975: np.array([65.0, 80.0], dtype=float),
        }
        baseline_quantiles = {
            0.025: np.array([2.0, 3.0], dtype=float),
            0.1: np.array([4.0, 5.0], dtype=float),
            0.25: np.array([6.0, 8.0], dtype=float),
            0.5: np.array([9.0, 11.0], dtype=float),
            0.75: np.array([13.0, 16.0], dtype=float),
            0.9: np.array([18.0, 22.0], dtype=float),
            0.975: np.array([24.0, 30.0], dtype=float),
        }
        output_quantiles = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)

        mixed = mixture_quantiles_via_cdf(
            model_quantiles=model_quantiles,
            baseline_quantiles=baseline_quantiles,
            mixture_weight=0.35,
            output_quantiles=output_quantiles,
        )

        for sample_idx in range(2):
            scalar_model = {
                quantile: float(values[sample_idx])
                for quantile, values in model_quantiles.items()
            }
            scalar_baseline = {
                quantile: float(values[sample_idx])
                for quantile, values in baseline_quantiles.items()
            }
            expected = np.asarray(
                [
                    _quantile_for_mixture(
                        quantile,
                        model_quantiles=scalar_model,
                        baseline_quantiles=scalar_baseline,
                        mixture_weight=0.35,
                    )
                    for quantile in output_quantiles
                ],
                dtype=float,
            )
            actual = np.asarray(
                [mixed[quantile][sample_idx] for quantile in output_quantiles],
                dtype=float,
            )
            np.testing.assert_allclose(actual, expected, atol=1e-5, rtol=1e-5)

    def test_quantile_cdf_extrapolates_tail_above_upper_quantile(self) -> None:
        quantiles = {
            0.025: 10.0,
            0.1: 12.0,
            0.25: 15.0,
            0.5: 20.0,
            0.75: 30.0,
            0.9: 40.0,
            0.975: 50.0,
        }

        cdf_value = quantile_cdf(80.0, quantiles)

        self.assertGreater(cdf_value, 0.975)
        self.assertLess(cdf_value, 1.0)
        self.assertGreater(1.0 - cdf_value, 0.0)
        self.assertLess(1.0 - cdf_value, 0.025)

    def test_optimize_persistence_mix_weight_prefers_the_better_distribution(self) -> None:
        y_true = np.array([20.0, 22.0, 24.0], dtype=float)
        model_quantiles = {
            0.1: np.array([18.0, 20.0, 22.0], dtype=float),
            0.5: np.array([20.0, 22.0, 24.0], dtype=float),
            0.9: np.array([22.0, 24.0, 26.0], dtype=float),
        }
        persistence_quantiles = {
            0.1: np.array([8.0, 8.0, 8.0], dtype=float),
            0.5: np.array([10.0, 10.0, 10.0], dtype=float),
            0.9: np.array([12.0, 12.0, 12.0], dtype=float),
        }

        result = optimize_persistence_mix_weight(
            y_true=y_true,
            model_quantiles=model_quantiles,
            persistence_quantiles=persistence_quantiles,
            weight_grid=(0.0, 0.25, 0.5, 0.75, 1.0),
        )

        self.assertEqual(result["weight"], 1.0)
        self.assertGreaterEqual(result["evaluated_weights"], 2)


if __name__ == "__main__":
    unittest.main()
