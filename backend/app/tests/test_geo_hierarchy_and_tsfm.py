import unittest

import numpy as np
import pandas as pd

from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.models.tsfm_adapter import TSFMAdapter
from app.services.ml.regional_trainer import RegionalModelTrainer


class _StaticRegressor:
    def __init__(self, values) -> None:
        self._values = np.asarray(values, dtype=float)

    def predict(self, X):
        return self._values[: len(X)]


class GeoHierarchyAndTSFMTests(unittest.TestCase):
    def test_blend_quantiles_falls_back_to_baseline_for_zero_weight(self) -> None:
        blended = GeoHierarchyHelper.blend_quantiles(
            model_quantiles={0.5: np.asarray([10.0, 20.0], dtype=float)},
            baseline_quantiles={0.5: np.asarray([4.0, 6.0], dtype=float)},
            blend_weight=0.0,
        )

        np.testing.assert_allclose(blended[0.5], np.asarray([4.0, 6.0], dtype=float))

    def test_aggregate_feature_frame_builds_independent_cluster_rows(self) -> None:
        panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BW", "BE"],
                "as_of_date": pd.to_datetime(["2026-03-10"] * 3),
                "state_population_millions": [13.0, 11.0, 4.0],
                "current_known_incidence": [8.0, 14.0, 30.0],
                "f1": [10.0, 20.0, 30.0],
                "f2": [1.0, 3.0, 5.0],
            }
        )

        cluster_frame = GeoHierarchyHelper.aggregate_feature_frame(
            panel,
            feature_columns=["f1", "f2"],
            cluster_assignments={"BY": "south", "BW": "south", "BE": "east"},
            level="cluster",
        )

        self.assertEqual(set(cluster_frame["hierarchy_group"]), {"south", "east"})
        south_row = cluster_frame.loc[cluster_frame["hierarchy_group"] == "south"].iloc[0]
        self.assertAlmostEqual(float(south_row["f1"]), (10.0 * 13.0 + 20.0 * 11.0) / 24.0, places=6)
        self.assertAlmostEqual(float(south_row["f2"]), (1.0 * 13.0 + 3.0 * 11.0) / 24.0, places=6)
        south_incidence = np.asarray([8.0, 14.0], dtype=float)
        south_weights = np.asarray([13.0, 11.0], dtype=float)
        south_mean = float(np.average(south_incidence, weights=south_weights))
        south_std = float(np.sqrt(np.average((south_incidence - south_mean) ** 2, weights=south_weights)))
        national_current = float(np.average(np.asarray([8.0, 14.0, 30.0], dtype=float), weights=np.asarray([13.0, 11.0, 4.0], dtype=float)))
        self.assertEqual(float(south_row["hierarchy_member_count"]), 2.0)
        self.assertAlmostEqual(float(south_row["hierarchy_total_weight"]), 24.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_incidence_std"]), south_std, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_incidence_range"]), 6.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_incidence_max"]), 14.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_incidence_min"]), 8.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_hot_state_population_share"]), 11.0 / 24.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_hot_state_excess"]), 14.0 - south_mean, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_vs_national_current_gap"]), south_mean - national_current, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_vs_rest_current_gap"]), south_mean - 30.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_current_rank_pct"]), 0.5, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_gap_to_hottest_cluster"]), south_mean - 30.0, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_gap_to_coolest_cluster"]), 0.0, places=6)

    def test_reconcile_quantiles_returns_coherent_cluster_and_national_sums(self) -> None:
        state_quantiles = {
            0.1: np.asarray([9.0, 11.0, 5.0], dtype=float),
            0.5: np.asarray([10.0, 12.0, 6.0], dtype=float),
            0.9: np.asarray([11.0, 13.0, 7.0], dtype=float),
        }
        cluster_assignments = {"BY": "south", "BW": "south", "BE": "east"}
        cluster_quantiles = {
            0.1: np.asarray([18.5, 4.0], dtype=float),
            0.5: np.asarray([23.0, 4.5], dtype=float),
            0.9: np.asarray([25.0, 5.0], dtype=float),
        }
        national_quantiles = {
            0.1: np.asarray([23.0], dtype=float),
            0.5: np.asarray([29.0], dtype=float),
            0.9: np.asarray([31.0], dtype=float),
        }
        residual_history = np.asarray(
            [
                [0.5, -0.2, 0.1, 0.4, -0.1, 0.2],
                [0.4, -0.1, 0.2, 0.3, -0.2, 0.1],
                [0.6, -0.3, 0.0, 0.5, 0.1, 0.3],
            ],
            dtype=float,
        )

        reconciled, metadata = GeoHierarchyHelper.reconcile_quantiles(
            state_quantiles,
            cluster_assignments=cluster_assignments,
            state_order=["BY", "BW", "BE"],
            cluster_quantiles=cluster_quantiles,
            national_quantiles=national_quantiles,
            residual_history=residual_history,
        )

        self.assertEqual(metadata["reconciliation_method"], "mint_projection_residual_covariance")
        self.assertEqual(metadata["hierarchy_consistency_status"], "coherent")
        self.assertLessEqual(metadata["max_coherence_gap"], 1e-6)
        cluster_q50 = metadata["cluster_quantiles"][0.5]
        national_q50 = metadata["national_quantiles"][0.5]
        self.assertAlmostEqual(float(cluster_q50[0]), float(reconciled[0.5][0] + reconciled[0.5][1]), places=6)
        self.assertAlmostEqual(float(cluster_q50[1]), float(reconciled[0.5][2]), places=6)
        self.assertAlmostEqual(float(national_q50[0]), float(np.sum(reconciled[0.5])), places=6)
        self.assertLessEqual(float(reconciled[0.1][0]), float(reconciled[0.5][0]))
        self.assertLessEqual(float(reconciled[0.5][0]), float(reconciled[0.9][0]))

    def test_reconcile_quantiles_supports_population_weighted_aggregates(self) -> None:
        state_quantiles = {
            0.5: np.asarray([10.0, 20.0], dtype=float),
        }
        reconciled, metadata = GeoHierarchyHelper.reconcile_quantiles(
            state_quantiles,
            cluster_assignments={"BY": "south", "BE": "east"},
            state_order=["BY", "BE"],
            state_weights={"BY": 10.0, "BE": 30.0},
        )

        self.assertAlmostEqual(float(metadata["national_quantiles"][0.5][0]), 17.5, places=6)
        self.assertAlmostEqual(float(metadata["cluster_quantiles"][0.5][0]), 10.0, places=6)
        self.assertAlmostEqual(float(metadata["cluster_quantiles"][0.5][1]), 20.0, places=6)

    def test_cluster_homogeneity_diagnostics_detects_stable_correlated_clusters(self) -> None:
        dates = pd.date_range("2026-01-01", periods=12, freq="D")
        panel = pd.DataFrame(
            {
                "bundesland": (["BY"] * 12) + (["BW"] * 12) + (["BE"] * 12) + (["BB"] * 12),
                "as_of_date": list(dates) * 4,
                "current_known_incidence": (
                    [10 + idx for idx in range(12)]
                    + [10.2 + idx for idx in range(12)]
                    + [30 - idx for idx in range(12)]
                    + [29.8 - idx for idx in range(12)]
                ),
                "state_population_millions": ([13.0] * 12) + ([11.0] * 12) + ([4.0] * 12) + ([2.5] * 12),
            }
        )

        diagnostics = GeoHierarchyHelper.cluster_homogeneity_diagnostics(
            panel,
            trailing_days=10,
            n_clusters=2,
        )

        self.assertEqual(diagnostics["status"], "ok")
        self.assertGreater(int(diagnostics["evaluation_dates"]), 0)
        self.assertEqual(diagnostics["homogeneity_rating"], "good")
        self.assertGreater(float(diagnostics["within_cluster_corr_mean"]), float(diagnostics["between_cluster_corr_mean"]))
        self.assertLess(float(diagnostics["state_reassignment_rate"]), 0.05)
        self.assertEqual(len(diagnostics["latest_clusters"]), 2)

    def test_aggregate_feature_frame_adds_neighbor_cluster_context(self) -> None:
        panel = pd.DataFrame(
            {
                "bundesland": ["BY", "SN", "BB", "BE"],
                "as_of_date": pd.to_datetime(["2026-03-10"] * 4),
                "state_population_millions": [13.0, 4.0, 2.5, 4.0],
                "current_known_incidence": [12.0, 18.0, 28.0, 24.0],
                "f1": [1.0, 2.0, 3.0, 4.0],
            }
        )

        cluster_frame = GeoHierarchyHelper.aggregate_feature_frame(
            panel,
            feature_columns=["f1"],
            cluster_assignments={"BY": "south", "SN": "south", "BB": "east", "BE": "east"},
            level="cluster",
        )

        south_row = cluster_frame.loc[cluster_frame["hierarchy_group"] == "south"].iloc[0]
        south_mean = float(np.average(np.asarray([12.0, 18.0], dtype=float), weights=np.asarray([13.0, 4.0], dtype=float)))
        east_mean = float(np.average(np.asarray([28.0, 24.0], dtype=float), weights=np.asarray([2.5, 4.0], dtype=float)))
        self.assertEqual(float(south_row["hierarchy_neighbor_cluster_count"]), 1.0)
        self.assertAlmostEqual(float(south_row["hierarchy_neighbor_current_gap"]), south_mean - east_mean, places=6)
        self.assertAlmostEqual(float(south_row["hierarchy_neighbor_current_ratio"]), south_mean / east_mean, places=6)

    def test_tsfm_adapter_is_stable_when_disabled_or_missing(self) -> None:
        disabled = TSFMAdapter.from_settings(enabled=False, provider="timesfm")
        missing = TSFMAdapter.from_settings(enabled=True, provider="definitely_missing_provider")

        self.assertFalse(disabled.available)
        self.assertEqual(disabled.reason, "feature_flag_disabled")
        self.assertFalse(missing.available)
        self.assertEqual(missing.reason, "import_failed")
        self.assertEqual(missing.metadata()["challenger_mode"], "zero_shot_quantile")

    def test_resolve_blend_weight_policy_prefers_matching_regime(self) -> None:
        policy = {
            "version": "fold_probabilistic_wis_crps_v1",
            "horizon_days": 7,
            "fallback": {"weight": 0.2, "scope": "all_history", "samples": 18, "wis": 2.4, "crps": 1.0},
            "by_regime": {
                "respiratory_peak": {"weight": 0.6, "scope": "same_regime", "samples": 8, "wis": 1.8, "crps": 0.7},
            },
        }

        peak = GeoHierarchyHelper.resolve_blend_weight_policy(
            policy,
            as_of_date="2026-01-15",
            horizon_days=7,
            fallback=0.0,
        )
        summer = GeoHierarchyHelper.resolve_blend_weight_policy(
            policy,
            as_of_date="2026-07-15",
            horizon_days=7,
            fallback=0.0,
        )

        self.assertEqual(peak["regime"], "respiratory_peak")
        self.assertAlmostEqual(float(peak["weight"]), 0.6, places=6)
        self.assertEqual(peak["scope"], "same_regime")
        self.assertEqual(summer["regime"], "off_season")
        self.assertAlmostEqual(float(summer["weight"]), 0.2, places=6)
        self.assertEqual(summer["scope"], "all_history")

    def test_trainer_builds_hierarchy_metadata_with_residual_history(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BE", "BW"],
                "as_of_date": pd.to_datetime(["2026-03-10", "2026-03-10", "2026-03-10"]),
                "current_known_incidence": [12.0, 8.0, 10.0],
            }
        )
        oof_frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(["2026-03-08", "2026-03-08", "2026-03-08", "2026-03-09", "2026-03-09", "2026-03-09"]),
                "bundesland": ["BY", "BE", "BW", "BY", "BE", "BW"],
                "residual": [0.5, -0.1, 0.2, 0.4, -0.2, 0.1],
                "prediction_interval_lower": [10.0, 6.0, 8.0, 11.0, 7.0, 9.0],
                "expected_target_incidence": [12.0, 8.0, 10.0, 13.0, 8.5, 10.5],
                "prediction_interval_upper": [14.0, 10.0, 12.0, 15.0, 10.0, 12.0],
            }
        )

        metadata = trainer._build_hierarchy_metadata(panel=panel, oof_frame=oof_frame)

        self.assertTrue(metadata["enabled"])
        self.assertEqual(metadata["reconciliation_method"], "mint_projection_residual_covariance")
        self.assertEqual(metadata["hierarchy_consistency_status"], "coherent")
        self.assertEqual(set(metadata["state_order"]), {"BY", "BE", "BW"})
        self.assertTrue(metadata["state_residual_history"])
        self.assertIn("state_weights", metadata)

    def test_hierarchy_component_diagnostics_prefer_baseline_when_model_is_worse(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        oof_frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(["2026-03-08", "2026-03-08", "2026-03-09", "2026-03-09"] * 4),
                "bundesland": ["BY", "BE", "BY", "BE"] * 4,
                "next_week_incidence": [10.0, 5.0, 11.0, 4.0] * 4,
                "expected_target_incidence": [9.5, 5.5, 10.5, 4.5] * 4,
                "cluster_id": ["cluster_0", "cluster_1", "cluster_0", "cluster_1"] * 4,
                "cluster_expected_target_incidence": [20.0, 12.0, 21.0, 11.0] * 4,
                "national_expected_target_incidence": [40.0, 40.0, 41.0, 41.0] * 4,
            }
        )

        diagnostics = trainer._hierarchy_component_diagnostics(oof_frame=oof_frame)

        self.assertEqual(diagnostics["cluster"]["recommended_blend_weight"], 0.0)
        self.assertEqual(diagnostics["national"]["recommended_blend_weight"], 0.0)

    def test_estimate_hierarchy_blend_choice_is_regime_sensitive(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        history_rows = []
        for day in range(6):
            history_rows.append(
                {
                    "as_of_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day),
                    "horizon_days": 7,
                    "regime": "respiratory_peak",
                    "truth": 10.0,
                    "baseline_q_0.1": 6.0,
                    "baseline_q_0.5": 12.0,
                    "baseline_q_0.9": 18.0,
                    "model_q_0.1": 9.0,
                    "model_q_0.5": 10.0,
                    "model_q_0.9": 11.0,
                }
            )
        for day in range(6):
            history_rows.append(
                {
                    "as_of_date": pd.Timestamp("2026-07-01") + pd.Timedelta(days=day),
                    "horizon_days": 7,
                    "regime": "off_season",
                    "truth": 10.0,
                    "baseline_q_0.1": 9.0,
                    "baseline_q_0.5": 10.0,
                    "baseline_q_0.9": 11.0,
                    "model_q_0.1": 4.0,
                    "model_q_0.5": 15.0,
                    "model_q_0.9": 21.0,
                }
            )

        peak_choice = trainer._estimate_hierarchy_blend_choice(
            history_rows,
            target_regime="respiratory_peak",
            target_horizon_days=7,
        )
        summer_choice = trainer._estimate_hierarchy_blend_choice(
            history_rows,
            target_regime="off_season",
            target_horizon_days=7,
        )

        self.assertGreater(float(peak_choice["weight"]), 0.0)
        self.assertEqual(peak_choice["scope"], "same_regime")
        self.assertEqual(float(summer_choice["weight"]), 0.0)

    def test_trainer_predicts_independent_cluster_and_national_inputs(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        frame = pd.DataFrame(
            {
                "bundesland": ["BY", "BW", "BE"],
                "as_of_date": pd.to_datetime(["2026-03-10"] * 3),
                "current_known_incidence": [12.0, 10.0, 8.0],
                "state_population_millions": [13.0, 11.0, 4.0],
                "f1": [1.0, 2.0, 3.0],
                "f2": [0.1, 0.2, 0.3],
            }
        )

        predictions = trainer._predict_hierarchy_aggregate_quantiles(
            frame=frame,
            source_panel=frame,
            feature_columns=["f1", "f2"],
            reg_lower=_StaticRegressor(np.log1p([18.0, 9.0, 25.0])),
            reg_median=_StaticRegressor(np.log1p([20.0, 10.0, 30.0])),
            reg_upper=_StaticRegressor(np.log1p([22.0, 11.0, 35.0])),
            hierarchy_models={
                "cluster": {
                    "lower": _StaticRegressor(np.log1p([18.0, 9.0, 25.0])),
                    "median": _StaticRegressor(np.log1p([20.0, 10.0, 30.0])),
                    "upper": _StaticRegressor(np.log1p([22.0, 11.0, 35.0])),
                },
                "national": {
                    "lower": _StaticRegressor(np.log1p([18.0])),
                    "median": _StaticRegressor(np.log1p([20.0])),
                    "upper": _StaticRegressor(np.log1p([22.0])),
                },
            },
        )

        self.assertEqual(len(predictions["national_median"]), 3)
        self.assertTrue(all(value == 20.0 for value in predictions["national_median"]))
        self.assertTrue(any(value is not None for value in predictions["cluster_ids"]))
        self.assertTrue(any(np.isfinite(value) for value in predictions["cluster_median"]))

    def test_trainer_builds_reconciled_benchmark_candidate_frame(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        source_panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BW", "BE", "BY", "BW", "BE"],
                "as_of_date": pd.to_datetime(["2026-03-08"] * 3 + ["2026-03-09"] * 3),
                "current_known_incidence": [12.0, 10.0, 8.0, 13.0, 11.0, 9.0],
            }
        )
        oof_frame = pd.DataFrame(
            {
                "fold": [0, 0, 0, 1, 1, 1],
                "virus_typ": ["Influenza A"] * 6,
                "bundesland": ["BY", "BW", "BE", "BY", "BW", "BE"],
                "bundesland_name": ["Bayern", "Baden-Württemberg", "Berlin", "Bayern", "Baden-Württemberg", "Berlin"],
                "as_of_date": pd.to_datetime(["2026-03-08"] * 3 + ["2026-03-09"] * 3),
                "target_week_start": pd.to_datetime(["2026-03-10"] * 6),
                "horizon_days": [7] * 6,
                "event_label": [1, 1, 0, 1, 1, 0],
                "event_probability_calibrated": [0.7, 0.62, 0.3, 0.75, 0.64, 0.28],
                "next_week_incidence": [14.0, 12.0, 7.5, 15.0, 13.0, 8.5],
                "expected_target_incidence": [13.0, 11.0, 8.0, 14.5, 12.0, 9.0],
                "prediction_interval_lower": [11.0, 9.5, 6.0, 12.0, 10.0, 7.0],
                "prediction_interval_upper": [15.0, 13.0, 10.0, 16.0, 14.0, 11.0],
                "cluster_id": ["cluster_0", "cluster_1", "cluster_2", "cluster_0", "cluster_1", "cluster_2"],
                "cluster_prediction_interval_lower": [16.0, 13.0, 7.0, 18.0, 14.0, 8.0],
                "cluster_expected_target_incidence": [20.0, 17.0, 9.0, 22.0, 18.0, 10.0],
                "cluster_prediction_interval_upper": [24.0, 21.0, 11.0, 26.0, 22.0, 12.0],
                "national_prediction_interval_lower": [40.0] * 6,
                "national_expected_target_incidence": [48.0] * 6,
                "national_prediction_interval_upper": [56.0] * 6,
            }
        )

        reconciled = trainer._hierarchy_reconciled_benchmark_frame(
            oof_frame=oof_frame,
            source_panel=source_panel,
        )

        self.assertFalse(reconciled.empty)
        self.assertEqual(set(reconciled["candidate"]), {"regional_pooled_panel_mint"})
        self.assertIn("reconciliation_method", reconciled.columns)
        self.assertIn("hierarchy_consistency_status", reconciled.columns)
        self.assertIn(reconciled["reconciliation_method"].iloc[0], {"mint_projection_residual_covariance", "state_sum_passthrough"})


if __name__ == "__main__":
    unittest.main()
