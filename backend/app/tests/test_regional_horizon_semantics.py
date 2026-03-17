import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.regional_trainer import RegionalModelTrainer


class _LoadableModel:
    def __init__(self) -> None:
        self.loaded_path: str | None = None

    def load_model(self, path: str) -> None:
        self.loaded_path = path


class RegionalHorizonSemanticsTests(unittest.TestCase):
    def test_prepare_horizon_panel_uses_future_current_incidence_as_target(self) -> None:
        panel = pd.DataFrame(
            {
                "bundesland": ["BY", "BY", "BY"],
                "as_of_date": [
                    pd.Timestamp("2026-03-01"),
                    pd.Timestamp("2026-03-04"),
                    pd.Timestamp("2026-03-07"),
                ],
                "target_date": [
                    pd.Timestamp("2026-03-04"),
                    pd.Timestamp("2026-03-07"),
                    pd.Timestamp("2026-03-10"),
                ],
                "target_window_days": [[3, 3], [3, 3], [3, 3]],
                "current_known_incidence": [10.0, 16.0, 22.0],
                "truth_source": ["survstat_kreis", "survstat_kreis", "survstat_kreis"],
                "f1": [1.0, 2.0, 3.0],
            }
        )

        prepared = RegionalModelTrainer._prepare_horizon_panel(panel, horizon_days=3)

        self.assertEqual(len(prepared), 2)
        self.assertEqual(prepared.iloc[0]["next_week_incidence"], 16.0)
        self.assertEqual(prepared.iloc[1]["next_week_incidence"], 22.0)
        self.assertEqual(prepared.iloc[0]["target_window_days"], [3, 3])
        self.assertEqual(prepared.iloc[0]["horizon_days"], 3.0)

    def test_trainer_load_artifacts_reads_horizon_specific_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            model_dir = base / "influenza_a" / "horizon_5"
            model_dir.mkdir(parents=True)
            (model_dir / "metadata.json").write_text(json.dumps({"trained_at": "2026-03-15T12:00:00", "horizon_days": 5}))
            (model_dir / "backtest.json").write_text(json.dumps({"total_regions": 16, "horizon_days": 5}))
            (model_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 100, "horizon_days": 5}))

            trainer = RegionalModelTrainer(db=None, models_dir=base)
            payload = trainer.load_artifacts("Influenza A", horizon_days=5)

            self.assertEqual(payload["metadata"]["horizon_days"], 5)
            self.assertEqual(payload["metadata"]["target_window_days"], [5, 5])
            self.assertEqual(payload["backtest"]["horizon_days"], 5)

    @patch("app.services.ml.regional_forecast.pickle.load", return_value="calibration")
    @patch("app.services.ml.regional_forecast.XGBRegressor", side_effect=lambda: _LoadableModel())
    @patch("app.services.ml.regional_forecast.XGBClassifier", side_effect=lambda: _LoadableModel())
    def test_forecast_loader_requires_horizon_metadata_for_scoped_artifacts(
        self,
        _classifier_cls,
        _regressor_cls,
        _pickle_load,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            model_dir = base / "influenza_a" / "horizon_5"
            model_dir.mkdir(parents=True)
            for name in [
                "classifier.json",
                "regressor_median.json",
                "regressor_lower.json",
                "regressor_upper.json",
                "calibration.pkl",
            ]:
                (model_dir / name).write_text("{}")
            (model_dir / "metadata.json").write_text(json.dumps({"feature_columns": ["f1"]}))
            (model_dir / "dataset_manifest.json").write_text(json.dumps({"rows": 10}))
            (model_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 10}))

            service = RegionalForecastService(db=None, models_dir=base)
            payload = service._load_artifacts("Influenza A", horizon_days=5)

            self.assertIn("load_error", payload)
            self.assertIn("horizon_days", payload["load_error"])

    @patch("app.services.ml.regional_forecast.pickle.load", return_value="calibration")
    @patch("app.services.ml.regional_forecast.XGBRegressor", side_effect=lambda: _LoadableModel())
    @patch("app.services.ml.regional_forecast.XGBClassifier", side_effect=lambda: _LoadableModel())
    def test_forecast_loader_uses_explicit_legacy_transition_for_h7_fallback(
        self,
        _classifier_cls,
        _regressor_cls,
        _pickle_load,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            legacy_dir = base / "influenza_a"
            legacy_dir.mkdir(parents=True)
            for name in [
                "classifier.json",
                "regressor_median.json",
                "regressor_lower.json",
                "regressor_upper.json",
                "calibration.pkl",
            ]:
                (legacy_dir / name).write_text("{}")
            (legacy_dir / "metadata.json").write_text(json.dumps({"feature_columns": ["f1"]}))
            (legacy_dir / "dataset_manifest.json").write_text(json.dumps({"rows": 10}))
            (legacy_dir / "point_in_time_snapshot.json").write_text(json.dumps({"rows": 10}))

            service = RegionalForecastService(db=None, models_dir=base)
            payload = service._load_artifacts("Influenza A", horizon_days=7)

            self.assertEqual(payload["artifact_transition_mode"], "legacy_default_window_fallback")
            self.assertEqual(payload["metadata"]["horizon_days"], 7)
            self.assertEqual(payload["metadata"]["requested_horizon_days"], 7)


if __name__ == "__main__":
    unittest.main()
