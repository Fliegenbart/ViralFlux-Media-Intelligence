import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_feature_importance.py"
SPEC = importlib.util.spec_from_file_location("export_feature_importance", SCRIPT_PATH)
feature_importance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = feature_importance
SPEC.loader.exec_module(feature_importance)


class ExportFeatureImportanceTests(unittest.TestCase):
    def test_virus_slug_matches_model_artifact_convention(self):
        self.assertEqual(feature_importance._virus_slug("Influenza A"), "influenza_a")
        self.assertEqual(feature_importance._virus_slug("SARS-CoV-2"), "sars_cov_2")

    def test_resolve_model_dir_accepts_direct_horizon_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            horizon_dir = Path(tmp) / "influenza_a" / "horizon_7"
            horizon_dir.mkdir(parents=True)
            (horizon_dir / "model_median.json").write_text("{}", encoding="utf-8")

            result = feature_importance._resolve_model_dir(
                model_dir=horizon_dir,
                virus_typ="Influenza A",
                horizon_days=7,
            )

        self.assertEqual(result, horizon_dir)

    def test_resolve_model_dir_appends_slug_and_horizon_for_root_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "influenza_a" / "horizon_7"
            expected.mkdir(parents=True)
            (expected / "model_median.json").write_text("{}", encoding="utf-8")

            result = feature_importance._resolve_model_dir(
                model_dir=root,
                virus_typ="Influenza A",
                horizon_days=7,
            )

        self.assertEqual(result, expected)

    def test_resolve_model_dir_uses_retained_summary_artifact_for_nested_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preferred = root / "influenza_a" / "best_spec" / "influenza_a" / "horizon_7"
            preferred.mkdir(parents=True)
            (preferred / "model_median.json").write_text("{}", encoding="utf-8")
            (root / "summary_flu_a.json").write_text(
                json.dumps(
                    {
                        "viruses": {
                            "Influenza A": {
                                "runs": [
                                    {
                                        "name": "best_spec",
                                        "retained": True,
                                        "artifact_dir": str(preferred),
                                    }
                                ]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = feature_importance._resolve_model_dir(
                model_dir=root,
                virus_typ="Influenza A",
                horizon_days=7,
            )

        self.assertEqual(result, preferred)

    def test_choose_model_file_prefers_median_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            (model_dir / "model_upper.json").write_text("{}", encoding="utf-8")
            median = model_dir / "model_median.json"
            median.write_text("{}", encoding="utf-8")

            self.assertEqual(feature_importance._choose_model_file(model_dir), median)

    def test_choose_model_file_uses_classifier_for_regional_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            classifier = model_dir / "classifier.json"
            classifier.write_text("{}", encoding="utf-8")
            (model_dir / "regressor_median.json").write_text("{}", encoding="utf-8")

            self.assertEqual(feature_importance._choose_model_file(model_dir), classifier)

    def test_load_feature_names_prefers_feature_names_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            (model_dir / "feature_names.json").write_text(
                json.dumps(["signal_a", "signal_b"]),
                encoding="utf-8",
            )

            self.assertEqual(
                feature_importance._load_feature_names(model_dir),
                ["signal_a", "signal_b"],
            )

    def test_load_feature_names_uses_event_columns_for_classifier_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            classifier = model_dir / "classifier.json"
            classifier.write_text("{}", encoding="utf-8")
            (model_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "feature_columns": ["regressor_a"],
                        "event_feature_columns": ["classifier_a", "classifier_b"],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                feature_importance._load_feature_names(
                    model_dir,
                    model_file=classifier,
                    model_role="auto",
                ),
                ["classifier_a", "classifier_b"],
            )

    def test_build_feature_rows_maps_f_indices_and_sorts_by_gain(self):
        rows = feature_importance._build_feature_rows(
            feature_names=["temp", "trends"],
            gain={"f1": 3.0, "f0": 5.0},
            weight={"f0": 2.0},
            cover={"f1": 7.0},
        )

        self.assertEqual([row["name"] for row in rows], ["temp", "trends"])
        self.assertEqual(rows[0]["gain_importance"], 5.0)
        self.assertEqual(rows[0]["weight_importance"], 2.0)
        self.assertEqual(rows[1]["cover_importance"], 7.0)


if __name__ == "__main__":
    unittest.main()
