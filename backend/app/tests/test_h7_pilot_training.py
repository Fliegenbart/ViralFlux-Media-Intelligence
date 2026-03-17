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

    def test_influenza_default_spec_map_keeps_rsv_on_baseline_only(self) -> None:
        spec_map = default_h7_influenza_calibration_specs_by_virus(
            ["Influenza A", "Influenza B", "RSV A"]
        )

        self.assertGreater(len(spec_map["Influenza A"]), 1)
        self.assertGreater(len(spec_map["Influenza B"]), 1)
        self.assertEqual(spec_map["RSV A"], (BASELINE_GUARD_SPEC,))

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
        self.assertEqual(virus_summary["runs"][0]["selected_calibration_mode"], "logit_temp_guarded_t1p25")
        self.assertEqual(virus_summary["runs"][0]["delta_vs_baseline"]["ece"], -0.01)
        self.assertEqual(virus_summary["comparison_table"][1]["name"], "logit_temperature_grid")


if __name__ == "__main__":
    unittest.main()
