import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.services.ml.regional_experiments import (
    ExperimentSpec,
    RegionalExperimentTrainer,
    RegionalExperimentRunner,
)
from app.services.ml.models.event_classifier import LearnedEventModel
from app.services.ml.regional_trainer import RegionalModelTrainer


class RegionalExperimentRunnerTests(unittest.TestCase):
    def test_learned_event_model_fit_uses_shared_calibration_helper(self) -> None:
        captured: dict[str, object] = {}

        class _FakeClassifier:
            def fit(self, X, y):
                captured["fit_rows"] = len(X)
                return self

            def predict_proba(self, X):
                rows = len(X)
                probs = np.linspace(0.2, 0.8, rows, dtype=float)
                return np.column_stack([1.0 - probs, probs])

        calibration_dates = pd.date_range("2026-01-01", periods=24, freq="D")

        with patch(
            "app.services.ml.models.event_classifier.XGBClassifier",
            return_value=_FakeClassifier(),
        ), patch(
            "app.services.ml.models.event_classifier.select_probability_calibration_from_raw",
            side_effect=lambda raw_probabilities, labels, **kwargs: {
                "calibration": "shared_calibration",
                "calibration_mode": "isotonic",
                "fallback_reason": None,
                "received_rows": len(raw_probabilities),
                "received_labels": list(np.asarray(labels, dtype=int)),
                "received_allowed_modes": kwargs.get("allowed_modes"),
                "received_dates": list(pd.to_datetime(kwargs.get("as_of_dates")).normalize()),
            },
        ) as calibration_mock, patch(
            "app.services.ml.models.event_classifier.choose_action_threshold",
            return_value=(0.42, 0.0, 0.0),
        ):
            model = LearnedEventModel.fit(
                X_train=np.arange(40, dtype=float).reshape(-1, 1),
                y_train=np.array([idx % 2 for idx in range(40)], dtype=int),
                X_calibration=np.arange(24, dtype=float).reshape(-1, 1),
                y_calibration=np.array([idx % 2 for idx in range(24)], dtype=int),
                calibration_dates=calibration_dates,
            )

        self.assertEqual(captured["fit_rows"], 40)
        self.assertEqual(calibration_mock.call_count, 1)
        self.assertEqual(model.calibration, "shared_calibration")
        self.assertEqual(model.calibration_mode, "isotonic")
        helper_kwargs = calibration_mock.call_args.kwargs
        self.assertEqual(helper_kwargs["allowed_modes"], ("isotonic", "raw_probability"))
        self.assertEqual(
            list(pd.to_datetime(helper_kwargs["as_of_dates"]).normalize()),
            list(calibration_dates.normalize()),
        )

    def test_learned_event_model_low_support_falls_back_to_raw_passthrough(self) -> None:
        class _FakeClassifier:
            def fit(self, X, y):
                return self

            def predict_proba(self, X):
                probs = np.clip(0.2 + (np.asarray(X, dtype=float).reshape(-1) * 0.02), 0.2, 0.8)
                return np.column_stack([1.0 - probs, probs])

        calibration_inputs = np.arange(10, dtype=float).reshape(-1, 1)

        with patch(
            "app.services.ml.models.event_classifier.XGBClassifier",
            return_value=_FakeClassifier(),
        ), patch(
            "app.services.ml.models.event_classifier.choose_action_threshold",
            return_value=(0.5, 0.0, 0.0),
        ):
            model = LearnedEventModel.fit(
                X_train=np.arange(40, dtype=float).reshape(-1, 1),
                y_train=np.array([idx % 2 for idx in range(40)], dtype=int),
                X_calibration=calibration_inputs,
                y_calibration=np.array([idx % 2 for idx in range(10)], dtype=int),
                calibration_dates=pd.date_range("2026-02-01", periods=10, freq="D"),
            )

        expected_raw = np.array([0.2, 0.22], dtype=float)
        self.assertIsNone(model.calibration)
        self.assertEqual(model.calibration_mode, "raw_passthrough")
        np.testing.assert_allclose(model.predict_proba(np.array([[0.0], [1.0]], dtype=float)), expected_raw)

    def test_regional_fit_final_models_passes_tail_calibration_dates_to_learned_event_model(self) -> None:
        trainer = object.__new__(RegionalModelTrainer)
        trainer._fit_classifier_from_frame = lambda frame, feature_columns, sample_weight=None: "classifier"
        trainer._select_guarded_calibration = lambda **kwargs: ("regional_calibration", "isotonic_guarded")
        trainer._fit_regressor_from_frame = lambda frame, feature_columns, config: str(config.get("objective") or "regressor")
        trainer._fit_hierarchy_models = lambda **kwargs: ({"cluster": "hier"}, {"cluster": "mode"})

        panel = pd.DataFrame(
            {
                "feature": np.linspace(1.0, 60.0, 60),
                "event_label": np.array([idx % 2 for idx in range(60)], dtype=int),
                "as_of_date": pd.date_range("2026-01-01", periods=60, freq="D"),
                "y_next_log": np.linspace(0.1, 1.0, 60),
            }
        )
        oof_frame = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=30, freq="D"),
                "event_label": np.array([idx % 2 for idx in range(30)], dtype=int),
                "event_probability_raw": np.linspace(0.2, 0.8, 30),
            }
        )

        captured: dict[str, object] = {}

        def _fit_learned_event_model(**kwargs):
            captured.update(kwargs)
            return "learned_model"

        with patch(
            "app.services.ml.regional_trainer.LearnedEventModel.fit",
            side_effect=_fit_learned_event_model,
        ):
            artifacts = trainer._fit_final_models(
                panel=panel,
                feature_columns=["feature"],
                hierarchy_feature_columns=["feature"],
                oof_frame=oof_frame,
                action_threshold=0.55,
            )

        self.assertEqual(artifacts["learned_event_model"], "learned_model")
        self.assertEqual(len(captured["calibration_dates"]), 20)
        self.assertEqual(
            list(pd.to_datetime(captured["calibration_dates"]).normalize()),
            list(panel["as_of_date"].tail(20).dt.normalize()),
        )

    def test_fit_final_models_uses_isotonic_calibration(self) -> None:
        trainer = object.__new__(RegionalExperimentTrainer)
        trainer.regressor_config = {
            "median": {"name": "median"},
            "lower": {"name": "lower"},
            "upper": {"name": "upper"},
        }
        trainer._fit_classifier_from_frame = lambda frame, feature_columns, sample_weight=None: "classifier"
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
