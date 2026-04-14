import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.services.ml.h7_pilot_training import (
    BASELINE_GUARD_SPEC,
    CalibrationExperimentSpec,
    H7PilotExperimentRunner,
    PilotExperimentSpec,
    PilotH7ExperimentTrainer,
    default_h7_influenza_calibration_specs_by_virus,
    default_h7_rsv_ranking_specs_by_virus,
    RSV_SIGNAL_CORE_SELECTION,
)


class H7PilotTrainingTests(unittest.TestCase):
    def test_pilot_trainer_prefers_extra_candidate_when_guard_improves_ece(self) -> None:
        trainer = PilotH7ExperimentTrainer(
            db=None,
            calibration_experiments=(
                CalibrationExperimentSpec(
                    strategy="logit_temperature",
                    temperatures=(1.25,),
                ),
            ),
        )
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        labels = np.array([0, 1] * 10, dtype=int)
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": np.where(labels == 1, 0.58, 0.42),
            }
        )

        isotonic = object()
        candidate = object()
        trainer._fit_isotonic = lambda *_args, **_kwargs: isotonic
        trainer._extra_guarded_calibration_candidates = lambda **_kwargs: [
            ("temp_candidate", candidate),
        ]

        def _apply(calibration, raw_probabilities):
            raw = np.asarray(raw_probabilities, dtype=float)
            if calibration is None:
                return np.clip(raw, 0.001, 0.999)
            if calibration is isotonic:
                return np.where(raw >= 0.5, 0.65, 0.55)
            if calibration is candidate:
                return np.where(raw >= 0.5, 0.60, 0.40)
            raise AssertionError("unexpected calibration")

        trainer._apply_calibration = _apply

        calibration, mode = trainer._select_guarded_calibration(
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
        )

        self.assertIs(calibration, candidate)
        self.assertEqual(mode, "temp_candidate")

    def test_pilot_trainer_keeps_raw_when_no_extra_candidate_improves_ece(self) -> None:
        trainer = PilotH7ExperimentTrainer(
            db=None,
            calibration_experiments=(
                CalibrationExperimentSpec(
                    strategy="shrinkage_blend",
                    alphas=(0.15,),
                ),
            ),
        )
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        labels = np.array([0, 1] * 10, dtype=int)
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": np.where(labels == 1, 0.58, 0.42),
            }
        )

        candidate = object()
        trainer._fit_isotonic = lambda *_args, **_kwargs: None
        trainer._extra_guarded_calibration_candidates = lambda **_kwargs: [
            ("bad_candidate", candidate),
        ]

        def _apply(calibration, raw_probabilities):
            raw = np.asarray(raw_probabilities, dtype=float)
            if calibration is None:
                return np.clip(raw, 0.001, 0.999)
            if calibration is candidate:
                return np.where(raw >= 0.5, 0.55, 0.45)
            raise AssertionError("unexpected calibration")

        trainer._apply_calibration = _apply

        calibration, mode = trainer._select_guarded_calibration(
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
        )

        self.assertIsNone(calibration)
        self.assertEqual(mode, "raw_passthrough")

    def test_baseline_guard_does_not_promote_platt_when_no_extra_experiments_are_configured(self) -> None:
        trainer = PilotH7ExperimentTrainer(db=None)
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        labels = np.array([0, 1] * 10, dtype=int)
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": np.where(labels == 1, 0.58, 0.42),
            }
        )

        platt = object()
        trainer._fit_isotonic = lambda *_args, **_kwargs: None
        trainer._fit_platt = lambda *_args, **_kwargs: platt

        def _apply(calibration, raw_probabilities):
            raw = np.asarray(raw_probabilities, dtype=float)
            if calibration is None:
                return np.clip(raw, 0.001, 0.999)
            if calibration is platt:
                return np.where(raw >= 0.5, 0.60, 0.40)
            raise AssertionError("unexpected calibration")

        trainer._apply_calibration = _apply

        with patch(
            "app.services.ml.regional_trainer_calibration._extra_guarded_calibration_candidates",
            return_value=[],
        ):
            calibration, mode = trainer._select_guarded_calibration(
                calibration_frame=calibration_frame,
                raw_probability_col="event_probability_raw",
                action_threshold=0.6,
            )

        self.assertIsNone(calibration)
        self.assertEqual(mode, "raw_passthrough")

    def test_baseline_guard_does_not_use_default_extra_candidates(self) -> None:
        trainer = PilotH7ExperimentTrainer(db=None)
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        labels = np.array([0, 1] * 10, dtype=int)
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": dates,
                "event_label": labels,
                "event_probability_raw": np.where(labels == 1, 0.58, 0.42),
            }
        )

        extra_candidate = object()
        trainer._fit_isotonic = lambda *_args, **_kwargs: None
        trainer._fit_platt = lambda *_args, **_kwargs: None

        def _apply(calibration, raw_probabilities):
            raw = np.asarray(raw_probabilities, dtype=float)
            if calibration is None:
                return np.clip(raw, 0.001, 0.999)
            if calibration is extra_candidate:
                return np.where(raw >= 0.5, 0.60, 0.40)
            raise AssertionError("unexpected calibration")

        trainer._apply_calibration = _apply

        with patch(
            "app.services.ml.regional_trainer_calibration._extra_guarded_calibration_candidates",
            return_value=[("extra_candidate", extra_candidate)],
        ):
            calibration, mode = trainer._select_guarded_calibration(
                calibration_frame=calibration_frame,
                raw_probability_col="event_probability_raw",
                action_threshold=0.6,
            )

        self.assertIsNone(calibration)
        self.assertEqual(mode, "raw_passthrough")

    def test_influenza_default_spec_map_keeps_rsv_on_baseline_only(self) -> None:
        spec_map = default_h7_influenza_calibration_specs_by_virus(
            ["Influenza A", "Influenza B", "RSV A"]
        )

        self.assertGreater(len(spec_map["Influenza A"]), 1)
        self.assertGreater(len(spec_map["Influenza B"]), 1)
        self.assertEqual(spec_map["RSV A"], (BASELINE_GUARD_SPEC,))

    def test_rsv_ranking_default_spec_map_uses_signal_subset_and_weighted_variants(self) -> None:
        spec_map = default_h7_rsv_ranking_specs_by_virus(["RSV A", "Influenza A"])

        self.assertGreater(len(spec_map["RSV A"]), 1)
        self.assertIsNotNone(spec_map["RSV A"][1].feature_selection)
        self.assertEqual(spec_map["Influenza A"], (BASELINE_GUARD_SPEC,))

    def test_rsv_trainer_applies_feature_subset_and_signal_weights(self) -> None:
        trainer = PilotH7ExperimentTrainer(
            db=None,
            feature_selection=RSV_SIGNAL_CORE_SELECTION,
            recency_weight_half_life_days=180.0,
            signal_agreement_weight=0.35,
        )
        panel = pd.DataFrame(
            {
                "ifsg_rsv_level": [1.5, -0.4],
                "survstat_baseline_zscore": [1.2, -0.2],
                "ww_slope7d": [0.8, -0.6],
                "weather_forecast_temp_3_7": [8.0, 10.0],
                "state_BY": [1.0, 0.0],
                "state_population_millions": [13.1, 13.1],
                "ww_sites_per_million": [2.2, 1.9],
                "target_week_iso": [6.0, 6.0],
                "target_holiday_share": [0.0, 0.0],
                "target_holiday_any": [0.0, 0.0],
                "as_of_date": pd.to_datetime(["2026-06-01", "2026-06-01"]),
                "event_label": [1, 0],
                "y_next_log": [0.2, 0.1],
            }
        )

        filtered_columns = trainer._feature_columns(panel)
        weights = trainer._sample_weights(panel)

        self.assertIn("ifsg_rsv_level", filtered_columns)
        self.assertIn("survstat_baseline_zscore", filtered_columns)
        self.assertNotIn("weather_forecast_temp_3_7", filtered_columns)
        self.assertNotIn("state_BY", filtered_columns)
        self.assertIsNotNone(weights)
        self.assertGreater(float(weights[0]), float(weights[1]))

    def test_runner_emits_comparison_rows_with_calibration_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "baseline"
            exp_dir = Path(tmp_dir) / "experiments"

            class _BaselineTrainer:
                def __init__(self, db, models_dir=None):
                    self.models_dir = models_dir

                def load_artifacts(self, virus_typ: str, horizon_days: int = 7):
                    return {
                        "metadata": {
                            "aggregate_metrics": {
                                "precision_at_top3": 0.70,
                                "activation_false_positive_rate": 0.05,
                                "pr_auc": 0.60,
                                "brier_score": 0.09,
                                "ece": 0.08,
                            },
                            "quality_gate": {
                                "overall_passed": False,
                                "forecast_readiness": "WATCH",
                                "failed_checks": ["ece_passed"],
                                "profile": "pilot_v1",
                            },
                            "calibration_version": "raw_passthrough:h7:baseline",
                        }
                    }

            class _ExperimentTrainer:
                def __init__(self, db, **kwargs):
                    self.kwargs = kwargs

                def train_all_regions(self, **kwargs):
                    return {
                        "status": "success",
                        "aggregate_metrics": {
                            "precision_at_top3": 0.72,
                            "activation_false_positive_rate": 0.04,
                            "pr_auc": 0.62,
                            "brier_score": 0.085,
                            "ece": 0.07,
                        },
                        "quality_gate": {
                            "overall_passed": False,
                            "forecast_readiness": "WATCH",
                            "failed_checks": ["ece_passed"],
                            "profile": "pilot_v1",
                        },
                        "calibration_version": "logit_temp_guarded_t1p25:h7:experiment",
                        "selected_calibration_mode": "logit_temp_guarded_t1p25",
                        "model_dir": str(exp_dir / "influenza_a" / "logit_temperature_grid"),
                    }

            with patch("app.services.ml.h7_pilot_training.RegionalModelTrainer", _BaselineTrainer), patch(
                "app.services.ml.h7_pilot_training.PilotH7ExperimentTrainer",
                _ExperimentTrainer,
            ):
                runner = H7PilotExperimentRunner(
                    db=None,
                    baseline_models_dir=base_dir,
                    experiment_models_dir=exp_dir,
                )
                summary = runner.run(
                    virus_types=["Influenza A"],
                    specs_by_virus={
                        "Influenza A": (
                            PilotExperimentSpec(
                                name="logit_temperature_grid",
                                description="test experiment",
                            ),
                        )
                    },
                )

        virus_summary = summary["viruses"]["Influenza A"]
        self.assertEqual(virus_summary["baseline"]["selected_calibration_mode"], "raw_passthrough")
        self.assertEqual(virus_summary["baseline"]["ece"], 0.08)
        self.assertEqual(virus_summary["runs"][0]["selected_calibration_mode"], "logit_temp_guarded_t1p25")
        self.assertEqual(virus_summary["runs"][0]["precision_at_top3"], 0.72)
        self.assertEqual(virus_summary["runs"][0]["delta_vs_baseline"]["ece"], -0.01)
        self.assertEqual(virus_summary["runs"][0]["gate_outcome"], "WATCH")
        self.assertTrue(virus_summary["runs"][0]["retained"])
        self.assertEqual(virus_summary["best_retained_experiment"], "logit_temperature_grid")
        self.assertEqual(virus_summary["comparison_table"][1]["name"], "logit_temperature_grid")
        self.assertEqual(virus_summary["comparison_table"][1]["brier_score"], 0.085)

    def test_runner_writes_split_summary_files_per_virus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "baseline"
            exp_dir = Path(tmp_dir) / "experiments"
            summary_output = Path(tmp_dir) / "influenza_calibration_summary.json"

            class _BaselineTrainer:
                def __init__(self, db, models_dir=None):
                    self.models_dir = models_dir

                def load_artifacts(self, virus_typ: str, horizon_days: int = 7):
                    return {
                        "metadata": {
                            "aggregate_metrics": {
                                "precision_at_top3": 0.70,
                                "activation_false_positive_rate": 0.05,
                                "pr_auc": 0.60,
                                "brier_score": 0.09,
                                "ece": 0.08,
                            },
                            "quality_gate": {
                                "overall_passed": False,
                                "forecast_readiness": "WATCH",
                                "failed_checks": ["ece_passed"],
                                "profile": "pilot_v1",
                            },
                            "calibration_version": "raw_passthrough:h7:baseline",
                        }
                    }

            class _ExperimentTrainer:
                def __init__(self, db, **kwargs):
                    self.kwargs = kwargs

                def train_all_regions(self, **kwargs):
                    virus_slug = str(kwargs["virus_typ"]).lower().replace(" ", "_")
                    return {
                        "status": "success",
                        "aggregate_metrics": {
                            "precision_at_top3": 0.72,
                            "activation_false_positive_rate": 0.04,
                            "pr_auc": 0.62,
                            "brier_score": 0.085,
                            "ece": 0.07,
                        },
                        "quality_gate": {
                            "overall_passed": False,
                            "forecast_readiness": "WATCH",
                            "failed_checks": ["ece_passed"],
                            "profile": "pilot_v1",
                        },
                        "calibration_version": "logit_temp_guarded_t1p25:h7:experiment",
                        "selected_calibration_mode": "logit_temp_guarded_t1p25",
                        "model_dir": str(exp_dir / virus_slug / "logit_temperature_grid"),
                    }

            with patch("app.services.ml.h7_pilot_training.RegionalModelTrainer", _BaselineTrainer), patch(
                "app.services.ml.h7_pilot_training.PilotH7ExperimentTrainer",
                _ExperimentTrainer,
            ):
                runner = H7PilotExperimentRunner(
                    db=None,
                    baseline_models_dir=base_dir,
                    experiment_models_dir=exp_dir,
                )
                runner.run(
                    virus_types=["Influenza A", "Influenza B"],
                    specs_by_virus={
                        "Influenza A": (
                            PilotExperimentSpec(
                                name="logit_temperature_grid",
                                description="test experiment",
                            ),
                        ),
                        "Influenza B": (
                            PilotExperimentSpec(
                                name="logit_temperature_grid",
                                description="test experiment",
                            ),
                        ),
                    },
                    summary_output=summary_output,
                )

            self.assertTrue(summary_output.exists())
            influenza_a_output = summary_output.with_name("influenza_calibration_summary.influenza_a.json")
            influenza_b_output = summary_output.with_name("influenza_calibration_summary.influenza_b.json")
            self.assertTrue(influenza_a_output.exists())
            self.assertTrue(influenza_b_output.exists())

            influenza_a_summary = json.loads(influenza_a_output.read_text())
            influenza_b_summary = json.loads(influenza_b_output.read_text())

            self.assertEqual(influenza_a_summary["pilot_viruses"], ["Influenza A"])
            self.assertEqual(sorted(influenza_a_summary["viruses"]), ["Influenza A"])
            self.assertEqual(influenza_b_summary["pilot_viruses"], ["Influenza B"])
            self.assertEqual(sorted(influenza_b_summary["viruses"]), ["Influenza B"])


if __name__ == "__main__":
    unittest.main()
