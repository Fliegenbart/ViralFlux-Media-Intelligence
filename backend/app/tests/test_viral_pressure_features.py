import unittest

from app.services.ml.research.viral_pressure_features import (
    build_viral_pressure_features,
)


class ViralPressureFeaturesTests(unittest.TestCase):
    def test_lightweight_formulas_include_divergence_pressure_spatial_and_saturation(self) -> None:
        features = build_viral_pressure_features(
            {
                "ww_slope7d": 0.45,
                "survstat_momentum_2w": 0.10,
                "grippeweb_are_momentum_1w": 0.20,
                "ifsg_influenza_momentum_1w": 0.15,
                "neighbor_ww_slope7d": 0.30,
                "national_ww_slope7d": 0.25,
                "survstat_baseline_zscore": 0.50,
                "survstat_current_incidence": 22.0,
                "survstat_seasonal_baseline": 16.0,
            },
            surge_probability=0.74,
            expected_growth_score=0.61,
            confidence=0.71,
            market_weight=0.82,
            timing_fit=1.0,
            data_quality_factor=0.90,
        )

        self.assertGreater(features["wastewater_case_divergence"], 0.0)
        self.assertGreater(features["viral_pressure_score"], 0.0)
        self.assertAlmostEqual(features["spatial_import_pressure"], 0.275, places=3)
        self.assertGreaterEqual(features["saturation_factor"], 0.0)
        self.assertLessEqual(features["saturation_factor"], 1.0)
        self.assertGreater(features["budget_opportunity_score"], 0.0)
        self.assertEqual(
            features["formula_versions"],
            {
                "wastewater_case_divergence": "research_v1_causal_z_proxy",
                "viral_pressure_score": "research_v1_weighted_proxy",
                "spatial_import_pressure": "research_v1_neighbor_national_mean",
                "recent_saturation_score": "research_v1_baseline_zscore",
                "budget_opportunity_score": "media_spending_truth_v1",
            },
        )

    def test_target_week_truth_is_not_used_as_a_feature(self) -> None:
        base_row = {
            "ww_slope7d": 0.20,
            "survstat_momentum_2w": 0.05,
            "neighbor_ww_slope7d": 0.10,
            "survstat_baseline_zscore": 0.25,
        }
        with_future_truth = {
            **base_row,
            "next_week_incidence": 9999.0,
            "target_week_start": "2099-01-05",
            "event_label": 1,
        }

        expected = build_viral_pressure_features(
            base_row,
            surge_probability=0.40,
            expected_growth_score=0.30,
            confidence=0.60,
            market_weight=0.50,
        )
        actual = build_viral_pressure_features(
            with_future_truth,
            surge_probability=0.40,
            expected_growth_score=0.30,
            confidence=0.60,
            market_weight=0.50,
        )

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
