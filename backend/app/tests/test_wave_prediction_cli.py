import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_wave_v1_backtest.py"


class WavePredictionCliTests(unittest.TestCase):
    def test_cli_smoke_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "wave_eval"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--fixture",
                    "default",
                    "--pathogen",
                    "Influenza A",
                    "--region",
                    "BY",
                    "--horizon",
                    "14",
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            self.assertTrue((output_dir / "panel_summary.json").exists())
            self.assertTrue((output_dir / "leakage_spotcheck.csv").exists())
            self.assertTrue((output_dir / "fold_metrics.json").exists())
            self.assertTrue((output_dir / "predictions.csv").exists())
            self.assertTrue((output_dir / "top_features.json").exists())

            with open(output_dir / "fold_metrics.json", "r", encoding="utf-8") as handle:
                fold_metrics = json.load(handle)
            self.assertEqual(fold_metrics["status"], "ok")
            self.assertIn("baseline_metrics", fold_metrics)
            self.assertIn("confusion_matrix", fold_metrics)

            predictions = pd.read_csv(output_dir / "predictions.csv")
            score_columns = [column for column in ("wave_probability", "wave_score") if column in predictions.columns]
            self.assertEqual(len(score_columns), 1)
            self.assertIn("fold", predictions.columns)

            leakage_spotcheck = pd.read_csv(output_dir / "leakage_spotcheck.csv")
            self.assertFalse(leakage_spotcheck.empty)
            self.assertTrue(
                (
                    pd.to_datetime(leakage_spotcheck["source_truth_available_date"])
                    <= pd.to_datetime(leakage_spotcheck["as_of_date"])
                ).all()
            )

    def test_cli_sparse_fixture_aborts_with_data_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "wave_eval_sparse"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--fixture",
                    "sparse",
                    "--pathogen",
                    "Influenza A",
                    "--region",
                    "BY",
                    "--horizon",
                    "14",
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((output_dir / "panel_summary.json").exists())
            self.assertTrue((output_dir / "fold_metrics.json").exists())
            self.assertFalse((output_dir / "predictions.csv").exists())

            with open(output_dir / "fold_metrics.json", "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Insufficient positive wave_start rows", payload["error"])


if __name__ == "__main__":
    unittest.main()
