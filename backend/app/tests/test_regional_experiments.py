import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.services.ml.regional_experiments import (
    ExperimentSpec,
    RegionalExperimentTrainer,
    RegionalExperimentRunner,
)


class RegionalExperimentRunnerTests(unittest.TestCase):
    def test_fit_final_models_uses_isotonic_calibration(self) -> None:
        trainer = object.__new__(RegionalExperimentTrainer)
        trainer.regressor_config = {
            "median": {"name": "median"},
            "lower": {"name": "lower"},
            "upper": {"name": "upper"},
        }
        trainer._fit_classifier_from_frame = lambda frame, feature_columns: "classifier"
        trainer._fit_regressor_from_frame = lambda frame, feature_columns, config: config["name"]

        observed: dict[str, list[float]] = {}

        def _fit_isotonic(raw_probabilities, labels):
            observed["raw_probabilities"] = list(raw_probabilities)
            observed["labels"] = list(labels)
            return "calibration"

        trainer._fit_isotonic = _fit_isotonic

        panel = pd.DataFrame({"feature": [1.0, 2.0], "y_next_log": [0.1, 0.2]})
        oof_frame = pd.DataFrame(
            {
                "event_probability_raw": [0.2, 0.8],
                "event_label": [0, 1],
            }
        )

        artifacts = trainer._fit_final_models(
            panel=panel,
            feature_columns=["feature"],
            oof_frame=oof_frame,
        )

        self.assertEqual(observed["raw_probabilities"], [0.2, 0.8])
        self.assertEqual(observed["labels"], [0, 1])
        self.assertEqual(artifacts["classifier"], "classifier")
        self.assertEqual(artifacts["calibration"], "calibration")
        self.assertEqual(artifacts["regressor_median"], "median")
        self.assertEqual(artifacts["regressor_lower"], "lower")
        self.assertEqual(artifacts["regressor_upper"], "upper")

    def test_metric_delta_computes_expected_signed_differences(self) -> None:
        delta = RegionalExperimentRunner._metric_delta(
            {
                "precision_at_top3": 0.25,
                "pr_auc": 0.62,
                "ece": 0.08,
            },
            {
                "precision_at_top3": 0.20,
                "pr_auc": 0.60,
                "ece": 0.10,
            },
        )
        self.assertEqual(delta["precision_at_top3"], 0.05)
        self.assertEqual(delta["pr_auc"], 0.02)
        self.assertEqual(delta["ece"], -0.02)

    def test_run_sorts_best_experiment_by_precision_then_pr_auc_then_ece(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "baseline"
            exp_dir = Path(tmpdir) / "experiments"
            virus_dir = base_dir / "influenza_a"
            virus_dir.mkdir(parents=True)
            (virus_dir / "metadata.json").write_text(json.dumps({
                "aggregate_metrics": {
                    "precision_at_top3": 0.19,
                    "precision_at_top5": 0.18,
                    "pr_auc": 0.63,
                    "brier_score": 0.09,
                    "ece": 0.06,
                    "activation_false_positive_rate": 0.21,
                }
            }))

            class _FakeRunner(RegionalExperimentRunner):
                def _build_result(self, spec_name: str):
                    results = {
                        "baseline": {
                            "aggregate_metrics": {
                                "precision_at_top3": 0.19,
                                "precision_at_top5": 0.18,
                                "pr_auc": 0.63,
                                "brier_score": 0.09,
                                "ece": 0.06,
                                "activation_false_positive_rate": 0.21,
                            },
                            "quality_gate": {"forecast_readiness": "WATCH"},
                        },
                        "candidate_a": {
                            "aggregate_metrics": {
                                "precision_at_top3": 0.21,
                                "precision_at_top5": 0.19,
                                "pr_auc": 0.61,
                                "brier_score": 0.10,
                                "ece": 0.07,
                                "activation_false_positive_rate": 0.20,
                            },
                            "quality_gate": {"forecast_readiness": "WATCH"},
                        },
                        "candidate_b": {
                            "aggregate_metrics": {
                                "precision_at_top3": 0.21,
                                "precision_at_top5": 0.20,
                                "pr_auc": 0.66,
                                "brier_score": 0.11,
                                "ece": 0.05,
                                "activation_false_positive_rate": 0.18,
                            },
                            "quality_gate": {"forecast_readiness": "WATCH"},
                        },
                    }
                    return results[spec_name]

                def run(self, *, virus_typ: str = "Influenza A", specs=None):
                    specs = specs or []
                    baseline_trainer = type("Baseline", (), {
                        "load_artifacts": lambda self, virus_typ: json.loads((base_dir / "influenza_a" / "metadata.json").read_text())
                    })()
                    baseline_metrics = ((baseline_trainer.load_artifacts(virus_typ).get("aggregate_metrics")) or {})
                    runs = []
                    for spec in specs:
                        result = self._build_result(spec.name)
                        runs.append({
                            "name": spec.name,
                            "aggregate_metrics": result["aggregate_metrics"],
                            "quality_gate": result["quality_gate"],
                            "delta_vs_baseline": self._metric_delta(result["aggregate_metrics"], baseline_metrics),
                            "model_dir": str(exp_dir / spec.name),
                        })
                    ranking = sorted(
                        runs,
                        key=lambda item: (
                            float((item.get("aggregate_metrics") or {}).get("precision_at_top3") or 0.0),
                            float((item.get("aggregate_metrics") or {}).get("pr_auc") or 0.0),
                            -float((item.get("aggregate_metrics") or {}).get("ece") or 1.0),
                            -float((item.get("aggregate_metrics") or {}).get("activation_false_positive_rate") or 1.0),
                        ),
                        reverse=True,
                    )
                    summary = {
                        "virus_typ": virus_typ,
                        "baseline_metrics": baseline_metrics,
                        "experiment_count": len(ranking),
                        "best_experiment": ranking[0]["name"] if ranking else None,
                        "runs": ranking,
                    }
                    return summary

            runner = _FakeRunner(db=None, baseline_models_dir=base_dir, experiments_dir=exp_dir)
            summary = runner.run(
                virus_typ="Influenza A",
                specs=[
                    ExperimentSpec(name="baseline"),
                    ExperimentSpec(name="candidate_a"),
                    ExperimentSpec(name="candidate_b"),
                ],
            )

            self.assertEqual(summary["best_experiment"], "candidate_b")
            self.assertEqual(summary["runs"][0]["name"], "candidate_b")
            self.assertEqual(summary["runs"][1]["name"], "candidate_a")


if __name__ == "__main__":
    unittest.main()
