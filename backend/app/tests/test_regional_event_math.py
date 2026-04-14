import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.services.ml import regional_trainer_calibration, regional_trainer_events
from app.services.ml.regional_trainer import RegionalModelTrainer


class RegionalEventMathTests(unittest.TestCase):
    def test_event_feature_columns_adds_direct_incidence_anchors(self) -> None:
        panel = pd.DataFrame(
            {
                "current_known_incidence": [8.0],
                "seasonal_baseline": [6.0],
                "seasonal_mad": [2.0],
                "survstat_baseline_gap": [2.0],
                "survstat_baseline_zscore": [1.0],
                "ww_level": [0.4],
            }
        )

        columns = regional_trainer_events.event_feature_columns(
            panel,
            base_feature_columns=["ww_level", "survstat_baseline_gap"],
        )

        self.assertEqual(
            columns[:5],
            [
                "current_known_incidence",
                "seasonal_baseline",
                "seasonal_mad",
                "survstat_baseline_gap",
                "survstat_baseline_zscore",
            ],
        )
        self.assertIn("ww_level", columns)
        self.assertEqual(columns.count("survstat_baseline_gap"), 1)

    def test_select_event_definition_prefers_probability_quality_over_raw_precision(self) -> None:
        config = SimpleNamespace(
            tau_grid=(0.1, 0.2),
            kappa_grid=(0.5,),
            min_recall_for_selection=0.35,
        )
        panel = pd.DataFrame({"row_id": range(20)})

        class _Service:
            @staticmethod
            def _event_labels(_panel, *, virus_typ, tau, kappa, event_config):
                del virus_typ, kappa, event_config
                if np.isclose(tau, 0.1):
                    return np.array([1] * 12 + [0] * 8, dtype=int)
                return np.array([1] * 13 + [0] * 7, dtype=int)

            @staticmethod
            def _oof_classification_predictions(*, panel, labels, virus_typ, feature_columns, min_recall_for_threshold):
                del panel, virus_typ, feature_columns, min_recall_for_threshold
                mean_probability = 0.25 if int(np.sum(labels)) == 12 else 0.65
                return pd.DataFrame(
                    {
                        "event_label": labels,
                        "event_probability_calibrated": np.full(len(labels), mean_probability, dtype=float),
                    }
                )

        def _threshold(probabilities, labels, min_recall):
            del labels, min_recall
            if float(np.mean(probabilities)) < 0.5:
                return 0.6, 0.88, 0.45
            return 0.55, 0.72, 0.62

        def _average_precision(labels, probabilities):
            del labels
            return 0.41 if float(np.mean(probabilities)) < 0.5 else 0.67

        def _brier(labels, probabilities):
            del labels
            return 0.22 if float(np.mean(probabilities)) < 0.5 else 0.11

        def _ece(labels, probabilities):
            del labels
            return 0.18 if float(np.mean(probabilities)) < 0.5 else 0.06

        selection = regional_trainer_events.select_event_definition(
            _Service(),
            virus_typ="Influenza A",
            panel=panel,
            feature_columns=["f1"],
            event_config=config,
            event_definition_config_for_virus_fn=lambda _virus: config,
            choose_action_threshold_fn=_threshold,
            average_precision_safe_fn=_average_precision,
            brier_score_safe_fn=_brier,
            compute_ece_fn=_ece,
        )

        self.assertEqual(selection["tau"], 0.2)
        self.assertEqual(selection["pr_auc"], 0.67)
        self.assertEqual(selection["brier_score"], 0.11)
        self.assertEqual(selection["ece"], 0.06)

    def test_select_guarded_calibration_prefers_best_guarded_candidate(self) -> None:
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-01", periods=20, freq="D"),
                "event_label": np.array([0, 1] * 10, dtype=int),
                "event_probability_raw": np.array([0.42, 0.58] * 10, dtype=float),
            }
        )

        class _Trainer:
            @staticmethod
            def _calibration_guard_split_dates(_dates):
                all_dates = list(pd.date_range("2026-01-01", periods=20, freq="D"))
                return all_dates[:10], all_dates[10:]

            @staticmethod
            def _fit_isotonic(raw_probabilities, labels):
                del raw_probabilities, labels
                return "isotonic"

            @staticmethod
            def _fit_platt(raw_probabilities, labels):
                del raw_probabilities, labels
                return "platt"

            @staticmethod
            def _apply_calibration(calibration, raw_probabilities):
                raw = np.asarray(raw_probabilities, dtype=float)
                if calibration is None:
                    return raw
                if calibration == "isotonic":
                    return np.where(raw >= 0.5, 0.64, 0.46)
                if calibration == "platt":
                    return np.where(raw >= 0.5, 0.72, 0.28)
                return calibration.predict(raw)

            @staticmethod
            def _calibration_guard_metrics(*, as_of_dates, labels, probabilities, action_threshold):
                del as_of_dates, labels, action_threshold
                positive_probability = float(np.max(probabilities))
                if positive_probability >= 0.7:
                    return {
                        "brier_score": 0.09,
                        "ece": 0.05,
                        "precision_at_top3": 0.60,
                        "activation_false_positive_rate": 0.10,
                    }
                if positive_probability >= 0.6:
                    return {
                        "brier_score": 0.11,
                        "ece": 0.08,
                        "precision_at_top3": 0.60,
                        "activation_false_positive_rate": 0.10,
                    }
                return {
                    "brier_score": 0.12,
                    "ece": 0.10,
                    "precision_at_top3": 0.60,
                    "activation_false_positive_rate": 0.10,
                }

        calibration, mode = regional_trainer_calibration.select_guarded_calibration(
            _Trainer(),
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
            calibration_guard_epsilon=1e-6,
            choose_action_threshold_fn=lambda probabilities, labels, min_recall: (0.6, 0.0, 0.0),
        )

        self.assertEqual(calibration, "platt")
        self.assertEqual(mode, "platt_guarded")

    def test_select_guarded_calibration_can_choose_logit_temperature_candidate(self) -> None:
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-02-01", periods=20, freq="D"),
                "event_label": np.array([0, 1] * 10, dtype=int),
                "event_probability_raw": np.array([0.44, 0.56] * 10, dtype=float),
            }
        )

        class _Trainer:
            @staticmethod
            def _calibration_guard_split_dates(_dates):
                all_dates = list(pd.date_range("2026-02-01", periods=20, freq="D"))
                return all_dates[:10], all_dates[10:]

            @staticmethod
            def _fit_isotonic(raw_probabilities, labels):
                del raw_probabilities, labels
                return "isotonic"

            @staticmethod
            def _fit_platt(raw_probabilities, labels):
                del raw_probabilities, labels
                return "platt"

            @staticmethod
            def _apply_calibration(calibration, raw_probabilities):
                raw = np.asarray(raw_probabilities, dtype=float)
                if calibration is None:
                    return raw
                if calibration == "isotonic":
                    return np.where(raw >= 0.5, 0.60, 0.40)
                if calibration == "platt":
                    return np.where(raw >= 0.5, 0.64, 0.36)
                return calibration.predict(raw)

            @staticmethod
            def _calibration_guard_metrics(*, as_of_dates, labels, probabilities, action_threshold):
                del as_of_dates, labels, action_threshold
                positive_probability = float(np.max(probabilities))
                negative_probability = float(np.min(probabilities))
                if 0.52 <= positive_probability <= 0.58 and 0.42 <= negative_probability <= 0.48:
                    return {
                        "brier_score": 0.085,
                        "ece": 0.035,
                        "precision_at_top3": 0.60,
                        "activation_false_positive_rate": 0.10,
                    }
                if positive_probability >= 0.64 and negative_probability <= 0.36:
                    return {
                        "brier_score": 0.095,
                        "ece": 0.055,
                        "precision_at_top3": 0.60,
                        "activation_false_positive_rate": 0.10,
                    }
                return {
                    "brier_score": 0.11,
                    "ece": 0.08,
                    "precision_at_top3": 0.60,
                    "activation_false_positive_rate": 0.10,
                }

        calibration, mode = regional_trainer_calibration.select_guarded_calibration(
            _Trainer(),
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
            calibration_guard_epsilon=1e-6,
            choose_action_threshold_fn=lambda probabilities, labels, min_recall: (0.6, 0.0, 0.0),
        )

        self.assertTrue(hasattr(calibration, "predict"))
        self.assertTrue(str(mode).startswith("logit_temp_guarded_t"))

    def test_select_guarded_calibration_can_choose_quantile_smoothing_candidate(self) -> None:
        calibration_frame = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-03-01", periods=40, freq="D"),
                "event_label": np.array([0, 0, 0, 1, 1] * 8, dtype=int),
                "event_probability_raw": np.array([0.18, 0.24, 0.31, 0.72, 0.84] * 8, dtype=float),
            }
        )

        class _Trainer:
            @staticmethod
            def _calibration_guard_split_dates(_dates):
                all_dates = list(pd.date_range("2026-03-01", periods=40, freq="D"))
                return all_dates[:20], all_dates[20:]

            @staticmethod
            def _fit_isotonic(raw_probabilities, labels):
                del raw_probabilities, labels
                return "isotonic"

            @staticmethod
            def _fit_platt(raw_probabilities, labels):
                del raw_probabilities, labels
                return "platt"

            @staticmethod
            def _apply_calibration(calibration, raw_probabilities):
                raw = np.asarray(raw_probabilities, dtype=float)
                if calibration is None:
                    return raw
                if calibration == "isotonic":
                    return np.where(raw >= 0.5, 0.70, 0.30)
                if calibration == "platt":
                    return np.where(raw >= 0.5, 0.76, 0.24)
                return calibration.predict(raw)

            @staticmethod
            def _calibration_guard_metrics(*, as_of_dates, labels, probabilities, action_threshold):
                del as_of_dates, labels, action_threshold
                unique_count = len(np.unique(np.round(probabilities, 3)))
                positive_probability = float(np.max(probabilities))
                negative_probability = float(np.min(probabilities))
                if unique_count == 3 and 0.19 <= negative_probability <= 0.21 and 0.69 <= positive_probability <= 0.71:
                    return {
                        "brier_score": 0.082,
                        "ece": 0.031,
                        "precision_at_top3": 0.60,
                        "activation_false_positive_rate": 0.10,
                    }
                if positive_probability >= 0.75 and negative_probability <= 0.25:
                    return {
                        "brier_score": 0.091,
                        "ece": 0.052,
                        "precision_at_top3": 0.60,
                        "activation_false_positive_rate": 0.10,
                    }
                return {
                    "brier_score": 0.11,
                    "ece": 0.08,
                    "precision_at_top3": 0.60,
                    "activation_false_positive_rate": 0.10,
                }

        calibration, mode = regional_trainer_calibration.select_guarded_calibration(
            _Trainer(),
            calibration_frame=calibration_frame,
            raw_probability_col="event_probability_raw",
            action_threshold=0.6,
            calibration_guard_epsilon=1e-6,
            choose_action_threshold_fn=lambda probabilities, labels, min_recall: (0.6, 0.0, 0.0),
        )

        self.assertTrue(hasattr(calibration, "predict"))
        self.assertTrue(str(mode).startswith("quantile_smooth_guarded_"))

    def test_event_sample_weights_favor_recent_rsv_rows(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(
                    ["2025-10-01", "2026-01-01", "2026-04-01"]
                )
            }
        )

        weights = trainer._event_sample_weights(
            frame,
            virus_typ="RSV A",
        )

        self.assertEqual(len(weights), 3)
        self.assertLess(float(weights[0]), float(weights[1]))
        self.assertLess(float(weights[1]), float(weights[2]))
        self.assertLessEqual(float(weights[2]), 1.0)

    def test_event_sample_weights_boost_rsv_signal_agreement(self) -> None:
        trainer = RegionalModelTrainer(db=None)
        frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(
                    ["2026-04-01", "2026-04-01"]
                ),
                "ifsg_rsv_baseline_zscore": [2.5, -2.5],
                "ifsg_rsv_momentum_1w": [2.0, -2.0],
                "survstat_baseline_zscore": [1.8, -1.8],
                "survstat_momentum_2w": [1.7, -1.7],
                "ww_slope7d": [1.6, -1.6],
                "ww_acceleration7d": [1.4, -1.4],
            }
        )

        weights = trainer._event_sample_weights(
            frame,
            virus_typ="RSV A",
        )

        self.assertEqual(len(weights), 2)
        self.assertGreater(float(weights[0]), float(weights[1]))
        self.assertGreater(float(weights[0]), 1.0)
