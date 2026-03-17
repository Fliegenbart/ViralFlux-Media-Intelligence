import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.services.media.truth_layer_contracts import OutcomeObservationInput
from app.services.media.truth_layer_service import TruthLayerService
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ml.regional_trainer import RegionalModelTrainer
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES


class _DummyClassifier:
    def __init__(self, probabilities):
        self._probabilities = np.asarray(probabilities, dtype=float)

    def predict_proba(self, X):
        probs = self._probabilities[: len(X)]
        return np.column_stack([1.0 - probs, probs])


class _DummyRegressor:
    def __init__(self, outputs):
        self._outputs = np.asarray(outputs, dtype=float)

    def predict(self, X):
        return self._outputs[: len(X)]


class _FakeFeatureBuilder:
    def __init__(self, frame: pd.DataFrame, as_of_date: str):
        self._frame = frame
        self._as_of_date = pd.Timestamp(as_of_date)
        self.last_horizon_days: int | None = None

    def latest_available_as_of_date(self, virus_typ: str = "Influenza A") -> pd.Timestamp:
        return self._as_of_date

    def build_inference_panel(
        self,
        virus_typ: str = "Influenza A",
        as_of_date=None,
        lookback_days: int = 180,
        horizon_days: int = 7,
        include_nowcast: bool = False,
        use_revision_adjusted: bool = False,
    ) -> pd.DataFrame:
        del virus_typ, as_of_date, lookback_days, include_nowcast, use_revision_adjusted
        self.last_horizon_days = horizon_days
        return self._frame.copy()


class RegionalForecastServiceTests(unittest.TestCase):
    def _make_service(
        self,
        *,
        quality_gate_passed: bool = True,
        virus_typ: str = "Influenza A",
        rollout_mode: str = "gated",
        activation_policy: str = "quality_gate",
        signal_bundle_version: str = "core_panel_v1",
        validated_for_budget_activation: bool = True,
        inference_panel: pd.DataFrame | None = None,
        probabilities: list[float] | None = None,
        median_values: list[float] | None = None,
        lower_values: list[float] | None = None,
        upper_values: list[float] | None = None,
        aggregate_metrics: dict | None = None,
    ) -> RegionalForecastService:
        if inference_panel is None:
            inference_panel = pd.DataFrame(
                {
                    "bundesland": ["BY", "BE"],
                    "bundesland_name": ["Bayern", "Berlin"],
                    "as_of_date": [pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-14")],
                    "target_week_start": [pd.Timestamp("2026-03-16"), pd.Timestamp("2026-03-16")],
                    "current_known_incidence": [10.0, 14.0],
                    "seasonal_baseline": [8.0, 9.0],
                    "seasonal_mad": [2.0, 2.5],
                    "pollen_context_score": [1.5, 0.5],
                    "f1": [1.0, 0.2],
                    "f2": [0.1, 0.8],
                }
            )

        quality_gate = {
            "overall_passed": quality_gate_passed,
            "forecast_readiness": "GO" if quality_gate_passed else "WATCH",
        }
        metadata = {
            "feature_columns": ["f1", "f2"],
            "action_threshold": 0.6,
            "event_definition_version": "regional_survstat_v1",
            "quality_gate": quality_gate,
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "signal_bundle_version": signal_bundle_version,
            "aggregate_metrics": aggregate_metrics or {},
        }
        probabilities = probabilities or [0.82, 0.41]
        median_values = median_values or [28.0, 12.0]
        lower_values = lower_values or [24.0, 10.0]
        upper_values = upper_values or [32.0, 15.0]

        service = RegionalForecastService(db=None)
        service.feature_builder = _FakeFeatureBuilder(inference_panel, as_of_date="2026-03-14")
        service._load_artifacts = lambda virus_typ, horizon_days=7: {
            "classifier": _DummyClassifier(probabilities),
            "regressor_median": _DummyRegressor(np.log1p(median_values)),
            "regressor_lower": _DummyRegressor(np.log1p(lower_values)),
            "regressor_upper": _DummyRegressor(np.log1p(upper_values)),
            "calibration": None,
            "metadata": {
                **metadata,
                "horizon_days": horizon_days,
                "target_window_days": [horizon_days, horizon_days],
                "supported_horizon_days": [3, 5, 7],
            },
        }
        service._business_gate = lambda quality_gate, truth_readiness=None, brand="gelo": {
            "truth_readiness": "belastbar" if validated_for_budget_activation else "im_aufbau",
            "truth_ready": validated_for_budget_activation,
            "coverage_weeks": 52 if validated_for_budget_activation else 12,
            "expected_units_lift_enabled": validated_for_budget_activation,
            "expected_revenue_lift_enabled": validated_for_budget_activation,
            "action_class": "customer_lift_ready" if validated_for_budget_activation else "market_watch",
            "validation_status": "passed_holdout_validation" if validated_for_budget_activation else "pending_holdout_validation",
            "decision_scope": "validated_budget_activation" if validated_for_budget_activation else "decision_support_only",
            "validated_for_budget_activation": validated_for_budget_activation,
        }
        service._test_virus_typ = virus_typ
        return service

    @staticmethod
    def _decision_ready_panel() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "bundesland": ["BY"],
                "bundesland_name": ["Bayern"],
                "as_of_date": [pd.Timestamp("2026-03-14")],
                "target_week_start": [pd.Timestamp("2026-03-16")],
                "current_known_incidence": [10.0],
                "seasonal_baseline": [8.0],
                "seasonal_mad": [2.0],
                "pollen_context_score": [1.5],
                "f1": [1.0],
                "f2": [0.1],
                "ww_acceleration7d": [0.45],
                "national_ww_acceleration7d": [0.30],
                "survstat_momentum_2w": [0.24],
                "grippeweb_are_momentum_1w": [0.28],
                "grippeweb_ili_momentum_1w": [0.22],
                "ifsg_influenza_momentum_1w": [0.30],
                "ww_level_freshness_days": [0.0],
                "ww_level_revision_risk": [0.05],
                "ww_level_usable_confidence": [0.98],
                "ww_level_coverage_ratio": [1.0],
                "survstat_current_incidence_freshness_days": [0.0],
                "survstat_current_incidence_revision_risk": [0.10],
                "survstat_current_incidence_usable_confidence": [0.95],
                "survstat_current_incidence_coverage_ratio": [1.0],
                "grippeweb_are_freshness_days": [1.0],
                "grippeweb_are_revision_risk": [0.10],
                "grippeweb_are_usable_confidence": [0.92],
                "grippeweb_are_coverage_ratio": [0.9],
                "grippeweb_ili_freshness_days": [1.0],
                "grippeweb_ili_revision_risk": [0.10],
                "grippeweb_ili_usable_confidence": [0.91],
                "grippeweb_ili_coverage_ratio": [0.9],
                "ifsg_influenza_freshness_days": [1.0],
                "ifsg_influenza_revision_risk": [0.08],
                "ifsg_influenza_usable_confidence": [0.93],
                "ifsg_influenza_coverage_ratio": [0.95],
            }
        )

    @staticmethod
    def _sparse_decision_panel() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "bundesland": ["BB"],
                "bundesland_name": ["Brandenburg"],
                "as_of_date": [pd.Timestamp("2026-03-14")],
                "target_week_start": [pd.Timestamp("2026-03-16")],
                "current_known_incidence": [6.0],
                "seasonal_baseline": [6.0],
                "seasonal_mad": [1.5],
                "pollen_context_score": [0.2],
                "f1": [0.3],
                "f2": [0.4],
                "ww_acceleration7d": [0.0],
                "national_ww_acceleration7d": [0.0],
                "survstat_momentum_2w": [0.0],
            }
        )

    def test_predict_all_regions_returns_calibrated_panel_payload(self) -> None:
        service = self._make_service(quality_gate_passed=True)

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

        self.assertEqual(result["virus_typ"], "Influenza A")
        self.assertEqual(result["horizon_days"], 7)
        self.assertEqual(result["target_window_days"], [7, 7])
        self.assertEqual(result["quality_gate"]["forecast_readiness"], "GO")
        self.assertEqual(result["total_regions"], 2)
        self.assertEqual(result["top_5"][0]["bundesland"], "BY")
        self.assertEqual(service.feature_builder.last_horizon_days, 7)

        top = result["predictions"][0]
        self.assertEqual(top["event_definition_version"], "regional_survstat_v1")
        self.assertEqual(top["horizon_days"], 7)
        self.assertEqual(top["target_window_days"], [7, 7])
        self.assertIn("target_date", top)
        self.assertIn("event_probability_calibrated", top)
        self.assertIn("expected_next_week_incidence", top)
        self.assertEqual(top["expected_target_incidence"], top["expected_next_week_incidence"])
        self.assertEqual(top["prediction_interval"], {"lower": 24.0, "upper": 32.0})
        self.assertTrue(top["activation_candidate"])
        self.assertEqual(top["rank"], 1)
        self.assertEqual(top["rollout_mode"], "gated")
        self.assertEqual(top["activation_policy"], "quality_gate")
        self.assertEqual(top["signal_bundle_version"], "core_panel_v1")
        self.assertTrue(top["business_gate"]["validated_for_budget_activation"])
        self.assertIn("model_version", top)
        self.assertIn("calibration_version", top)
        self.assertIn("point_in_time_snapshot", top)
        self.assertIn("source_coverage", top)
        self.assertIn("decision", top)
        self.assertIn("decision_label", top)
        self.assertIn("priority_score", top)
        self.assertIn("reason_trace", top)
        self.assertIn("uncertainty_summary", top)

    def test_predict_all_regions_passes_horizon_five_through_to_inference_and_contract(self) -> None:
        service = self._make_service(quality_gate_passed=True)

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=5)

        self.assertEqual(result["horizon_days"], 5)
        self.assertEqual(result["target_window_days"], [5, 5])
        self.assertEqual(service.feature_builder.last_horizon_days, 5)
        top = result["predictions"][0]
        self.assertEqual(top["horizon_days"], 5)
        self.assertEqual(top["target_window_days"], [5, 5])
        self.assertEqual(top["expected_target_incidence"], top["expected_next_week_incidence"])

    def test_predict_all_regions_rejects_unsupported_horizon(self) -> None:
        service = self._make_service(quality_gate_passed=True)

        with self.assertRaises(ValueError):
            service.predict_all_regions(virus_typ="Influenza A", horizon_days=4)

    def test_predict_all_regions_assigns_activate_when_signals_are_strong(self) -> None:
        service = self._make_service(
            inference_panel=self._decision_ready_panel(),
            probabilities=[0.82],
            median_values=[28.0],
            lower_values=[24.0],
            upper_values=[32.0],
            aggregate_metrics={
                "pr_auc": 0.71,
                "ece": 0.05,
                "brier_score": 0.09,
            },
        )

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

        top = result["predictions"][0]
        self.assertEqual(top["decision_label"], "Activate")
        self.assertGreater(top["priority_score"], 0.72)
        self.assertEqual(top["decision"]["stage"], "activate")
        self.assertGreaterEqual(top["decision_rank"], 1)
        self.assertTrue(top["reason_trace"]["why"])

    def test_predict_all_regions_assigns_prepare_for_mid_strength_case(self) -> None:
        service = self._make_service(
            inference_panel=self._decision_ready_panel(),
            probabilities=[0.57],
            median_values=[21.0],
            lower_values=[18.0],
            upper_values=[24.0],
            aggregate_metrics={
                "pr_auc": 0.64,
                "ece": 0.06,
                "brier_score": 0.11,
            },
        )

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

        top = result["predictions"][0]
        self.assertEqual(top["decision_label"], "Prepare")
        self.assertEqual(top["decision"]["stage"], "prepare")
        self.assertGreater(top["priority_score"], 0.54)

    def test_predict_all_regions_marks_sparse_region_as_watch_with_uncertainty(self) -> None:
        service = self._make_service(
            inference_panel=self._sparse_decision_panel(),
            probabilities=[0.61],
            median_values=[8.0],
            lower_values=[6.0],
            upper_values=[12.0],
        )

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

        top = result["predictions"][0]
        self.assertEqual(top["decision_label"], "Watch")
        self.assertEqual(top["decision"]["stage"], "watch")
        self.assertTrue(top["reason_trace"]["uncertainty"])
        self.assertIn("Remaining uncertainty", top["uncertainty_summary"])

    def test_media_activation_downgrades_to_watch_when_quality_gate_fails(self) -> None:
        service = self._make_service(quality_gate_passed=False)

        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        self.assertEqual(result["summary"]["quality_gate"]["forecast_readiness"], "WATCH")
        self.assertEqual(result["summary"]["total_budget_allocated"], 0.0)
        self.assertTrue(all(item["action"] == "watch" for item in result["recommendations"]))
        self.assertTrue(all(item["budget_eur"] == 0.0 for item in result["recommendations"]))

    def test_media_activation_exposes_allocation_fields_and_normalized_budget(self) -> None:
        service = self._make_service(
            quality_gate_passed=True,
            inference_panel=self._decision_ready_panel(),
            probabilities=[0.82],
            median_values=[28.0],
            lower_values=[24.0],
            upper_values=[32.0],
            aggregate_metrics={
                "pr_auc": 0.71,
                "ece": 0.05,
                "brier_score": 0.09,
            },
        )

        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        first = result["recommendations"][0]
        self.assertIn("recommended_activation_level", first)
        self.assertIn("suggested_budget_share", first)
        self.assertIn("suggested_budget_eur", first)
        self.assertIn("confidence", first)
        self.assertIn("allocation_score", first)
        self.assertIn("reason_trace", first)
        self.assertIn("allocation_reason_trace", first)
        self.assertEqual(first["allocation_reason_trace"], first["reason_trace"])
        self.assertIn("suggested_budget_amount", first)
        self.assertEqual(first["suggested_budget_amount"], first["suggested_budget_eur"])
        self.assertAlmostEqual(result["summary"]["budget_share_total"], 1.0, places=6)

    def test_media_activation_returns_stable_empty_payload_for_no_data(self) -> None:
        service = self._make_service(
            inference_panel=pd.DataFrame(),
        )

        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["recommendations"], [])
        self.assertIn("summary", result)
        self.assertIn("allocation_config", result)
        self.assertEqual(result["summary"]["total_budget_allocated"], 0.0)
        self.assertFalse(result["summary"]["spend_enabled"])

    def test_media_activation_returns_stable_empty_payload_for_no_model(self) -> None:
        service = self._make_service()
        service._load_artifacts = lambda virus_typ, horizon_days=7: {}

        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        self.assertEqual(result["status"], "no_model")
        self.assertEqual(result["recommendations"], [])
        self.assertIn("Horizon 7", result["message"])
        self.assertEqual(result["summary"]["allocation_policy_version"], "regional_media_allocation_v1")
        self.assertEqual(result["summary"]["total_budget_allocated"], 0.0)

    def test_predict_all_regions_returns_explicit_no_model_for_missing_horizon(self) -> None:
        service = self._make_service()
        service._load_artifacts = lambda virus_typ, horizon_days=7: {}

        result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=3)

        self.assertEqual(result["status"], "no_model")
        self.assertEqual(result["horizon_days"], 3)
        self.assertEqual(result["target_window_days"], [3, 3])
        self.assertIn("Horizon 3", result["message"])

    def test_media_activation_stays_watch_until_business_gate_is_validated(self) -> None:
        service = self._make_service(
            quality_gate_passed=True,
            validated_for_budget_activation=False,
        )

        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        self.assertEqual(result["summary"]["quality_gate"]["forecast_readiness"], "GO")
        self.assertFalse(result["summary"]["business_gate"]["validated_for_budget_activation"])
        self.assertEqual(result["summary"]["total_budget_allocated"], 0.0)
        self.assertTrue(all(item["action"] == "watch" for item in result["recommendations"]))
        self.assertTrue(
            all("Business-Gate" in item["timeline"] for item in result["recommendations"])
        )

    def test_sars_forecast_and_media_activation_respect_shadow_watch_policy(self) -> None:
        service = self._make_service(
            quality_gate_passed=True,
            virus_typ="SARS-CoV-2",
            rollout_mode="shadow",
            activation_policy="watch_only",
            signal_bundle_version="sars_hybrid_v1",
        )

        forecast = service.predict_all_regions(virus_typ="SARS-CoV-2", horizon_days=7)
        top = forecast["predictions"][0]
        self.assertEqual(top["rollout_mode"], "shadow")
        self.assertEqual(top["activation_policy"], "watch_only")
        self.assertEqual(top["signal_bundle_version"], "sars_hybrid_v1")
        self.assertFalse(top["activation_candidate"])

        media = service.generate_media_activation(
            virus_typ="SARS-CoV-2",
            weekly_budget_eur=50000,
            horizon_days=7,
        )
        self.assertEqual(media["summary"]["rollout_mode"], "shadow")
        self.assertEqual(media["summary"]["activation_policy"], "watch_only")
        self.assertEqual(media["summary"]["total_budget_allocated"], 0.0)
        self.assertTrue(all(item["action"] == "watch" for item in media["recommendations"]))

    def test_benchmark_supported_viruses_ranks_by_quality_and_metrics(self) -> None:
        service = RegionalForecastService(db=None)

        artifact_payloads = {
            "Influenza A": {
                "metadata": {
                    "trained_at": "2026-03-14T17:00:00",
                    "dataset_manifest": {"states": 16, "rows": 2083, "truth_source": "survstat_kreis"},
                    "aggregate_metrics": {
                        "precision_at_top3": 0.18,
                        "precision_at_top5": 0.17,
                        "pr_auc": 0.51,
                        "brier_score": 0.10,
                        "ece": 0.06,
                        "activation_false_positive_rate": 0.20,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "label_selection": {"tau": 0.15},
                }
            },
            "Influenza B": {
                "metadata": {
                    "trained_at": "2026-03-14T17:00:00",
                    "dataset_manifest": {"states": 16, "rows": 2081, "truth_source": "survstat_kreis"},
                    "aggregate_metrics": {
                        "precision_at_top3": 0.17,
                        "precision_at_top5": 0.16,
                        "pr_auc": 0.49,
                        "brier_score": 0.10,
                        "ece": 0.05,
                        "activation_false_positive_rate": 0.19,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "label_selection": {"tau": 0.10},
                }
            },
            "SARS-CoV-2": {
                "metadata": {
                    "trained_at": "2026-03-14T17:00:00",
                    "dataset_manifest": {"states": 16, "rows": 4042, "truth_source": "survstat_kreis"},
                    "aggregate_metrics": {
                        "precision_at_top3": 0.0,
                        "precision_at_top5": 0.0,
                        "pr_auc": 0.0,
                        "brier_score": 0.01,
                        "ece": 0.004,
                        "activation_false_positive_rate": 1.0,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "rollout_mode": "shadow",
                    "activation_policy": "watch_only",
                    "signal_bundle_version": "sars_hybrid_v1",
                    "label_selection": {"tau": 0.10},
                }
            },
        }
        service._load_artifacts = lambda virus_typ, horizon_days=7: artifact_payloads.get(virus_typ, {})

        result = service.benchmark_supported_viruses(reference_virus="Influenza A")

        self.assertEqual(result["reference_virus"], "Influenza A")
        self.assertEqual(result["trained_viruses"], 3)
        self.assertEqual(result["benchmark"][0]["virus_typ"], "Influenza A")
        self.assertEqual(result["benchmark"][1]["virus_typ"], "Influenza B")
        self.assertEqual(result["benchmark"][-1]["virus_typ"], "RSV A")
        self.assertIn("business_gate", result)
        influenza_b = next(item for item in result["benchmark"] if item["virus_typ"] == "Influenza B")
        self.assertAlmostEqual(influenza_b["delta_vs_reference"]["precision_at_top3"], -0.01, places=6)
        sars = next(item for item in result["benchmark"] if item["virus_typ"] == "SARS-CoV-2")
        self.assertEqual(sars["rollout_mode"], "shadow")
        self.assertEqual(sars["activation_policy"], "watch_only")
        self.assertIn("business_gate", sars)

    def test_get_validation_summary_exposes_business_evidence_contract(self) -> None:
        service = RegionalForecastService(db=None)
        service._load_artifacts = lambda virus_typ, horizon_days=7: {
            "metadata": {
                "model_family": "regional_pooled_panel",
                "trained_at": "2026-03-14T17:00:00",
                "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                "signal_bundle_version": "core_panel_v1",
                "rollout_mode": "gated",
                "activation_policy": "quality_gate",
            },
            "dataset_manifest": {
                "source_coverage": {
                    "wastewater": {"coverage_ratio": 0.92},
                }
            },
            "point_in_time_snapshot": {
                "snapshot_type": "regional_panel_as_of_training",
                "unique_as_of_dates": 180,
            },
        }
        service._business_gate = lambda quality_gate, truth_readiness=None, brand="gelo": {
            "brand": brand,
            "operator_context": {"operator": "peix", "truth_partner": brand},
            "validation_status": "pending_holdout_validation",
            "decision_scope": "decision_support_only",
            "validated_for_budget_activation": False,
            "evidence_tier": "holdout_ready",
        }

        result = service.get_validation_summary(virus_typ="Influenza A", brand="gelo")

        self.assertEqual(result["brand"], "gelo")
        self.assertEqual(result["business_gate"]["operator_context"]["operator"], "peix")
        self.assertEqual(result["evidence_tier"], "holdout_ready")
        self.assertEqual(result["source_coverage"]["wastewater"]["coverage_ratio"], 0.92)
        self.assertEqual(result["point_in_time_snapshot"]["snapshot_type"], "regional_panel_as_of_training")

    def test_build_portfolio_view_prioritizes_cross_virus_opportunities(self) -> None:
        service = RegionalForecastService(db=None)

        artifact_payloads = {
            "Influenza A": {
                "metadata": {
                    "aggregate_metrics": {
                        "precision_at_top3": 0.18,
                        "precision_at_top5": 0.17,
                        "pr_auc": 0.51,
                        "brier_score": 0.10,
                        "ece": 0.06,
                        "activation_false_positive_rate": 0.20,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                }
            },
            "Influenza B": {
                "metadata": {
                    "aggregate_metrics": {
                        "precision_at_top3": 0.17,
                        "precision_at_top5": 0.16,
                        "pr_auc": 0.49,
                        "brier_score": 0.10,
                        "ece": 0.05,
                        "activation_false_positive_rate": 0.19,
                    },
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                }
            },
            "SARS-CoV-2": {
                "metadata": {
                    "aggregate_metrics": {
                        "precision_at_top3": 0.20,
                        "precision_at_top5": 0.18,
                        "pr_auc": 0.52,
                        "brier_score": 0.09,
                        "ece": 0.07,
                        "activation_false_positive_rate": 0.18,
                    },
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "rollout_mode": "shadow",
                    "activation_policy": "watch_only",
                    "signal_bundle_version": "sars_hybrid_v1",
                }
            },
        }
        service._load_artifacts = lambda virus_typ, horizon_days=7: artifact_payloads.get(virus_typ, {})
        service.predict_all_regions = lambda virus_typ, horizon_days=7: {
            "virus_typ": virus_typ,
            "as_of_date": "2026-03-06 00:00:00",
            "predictions": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "rank": 1,
                    "event_probability_calibrated": 0.62 if virus_typ == "Influenza A" else 0.67,
                    "expected_next_week_incidence": 28.0,
                    "prediction_interval": {"lower": 24.0, "upper": 32.0},
                    "current_known_incidence": 10.0,
                    "change_pct": 35.0 if virus_typ == "Influenza B" else 22.0,
                    "trend": "steigend",
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "rollout_mode": "shadow" if virus_typ == "SARS-CoV-2" else "gated",
                    "activation_policy": "watch_only" if virus_typ == "SARS-CoV-2" else "quality_gate",
                    "signal_bundle_version": "sars_hybrid_v1" if virus_typ == "SARS-CoV-2" else "core_panel_v1",
                    "action_threshold": 0.6,
                    "as_of_date": "2026-03-06 00:00:00",
                    "target_week_start": "2026-03-09 00:00:00",
                },
                {
                    "bundesland": "BE",
                    "bundesland_name": "Berlin",
                    "rank": 2,
                    "event_probability_calibrated": 0.45,
                    "expected_next_week_incidence": 15.0,
                    "prediction_interval": {"lower": 12.0, "upper": 18.0},
                    "current_known_incidence": 11.0,
                    "change_pct": 9.0,
                    "trend": "stabil",
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                    "rollout_mode": "shadow" if virus_typ == "SARS-CoV-2" else "gated",
                    "activation_policy": "watch_only" if virus_typ == "SARS-CoV-2" else "quality_gate",
                    "signal_bundle_version": "sars_hybrid_v1" if virus_typ == "SARS-CoV-2" else "core_panel_v1",
                    "action_threshold": 0.6,
                    "as_of_date": "2026-03-06 00:00:00",
                    "target_week_start": "2026-03-09 00:00:00",
                },
            ],
        }

        result = service.build_portfolio_view(top_n=6, reference_virus="Influenza A")

        self.assertEqual(result["summary"]["trained_viruses"], 3)
        self.assertIn("business_gate", result)
        self.assertEqual(len(result["benchmark"]), len(SUPPORTED_VIRUS_TYPES))
        influenza_b_opportunity = next(item for item in result["top_opportunities"] if item["virus_typ"] == "Influenza B")
        self.assertEqual(influenza_b_opportunity["bundesland"], "BY")
        self.assertEqual(influenza_b_opportunity["portfolio_action"], "prioritize")
        self.assertIn("GeloMyrtol forte", influenza_b_opportunity["products"])
        sars_opportunity = next(item for item in result["top_opportunities"] if item["virus_typ"] == "SARS-CoV-2")
        self.assertEqual(sars_opportunity["activation_policy"], "watch_only")
        self.assertIn(sars_opportunity["portfolio_action"], {"watch", "prioritize"})
        self.assertNotIn(sars_opportunity["portfolio_action"], {"activate", "prepare"})


class RegionalTrainerRolloutTests(unittest.TestCase):
    def test_sars_rollout_metadata_compares_candidate_against_previous_and_persistence(self) -> None:
        trainer = RegionalModelTrainer(db=None)

        rollout = trainer._rollout_metadata(
            virus_typ="SARS-CoV-2",
            aggregate_metrics={
                "precision_at_top3": 0.22,
                "pr_auc": 0.18,
                "activation_false_positive_rate": 0.40,
            },
            baseline_metrics={
                "persistence": {
                    "precision_at_top3": 0.20,
                    "pr_auc": 0.10,
                }
            },
            previous_artifact={
                "metadata": {
                    "aggregate_metrics": {
                        "precision_at_top3": 0.15,
                        "pr_auc": 0.12,
                        "activation_false_positive_rate": 0.52,
                    }
                }
            },
        )

        self.assertEqual(rollout["rollout_mode"], "shadow")
        self.assertEqual(rollout["activation_policy"], "watch_only")
        self.assertEqual(rollout["signal_bundle_version"], "sars_hybrid_v1")
        self.assertTrue(rollout["shadow_evaluation"]["overall_passed"])

    def test_non_sars_rollout_metadata_stays_standard(self) -> None:
        trainer = RegionalModelTrainer(db=None)

        rollout = trainer._rollout_metadata(
            virus_typ="Influenza A",
            aggregate_metrics={"precision_at_top3": 0.2},
            baseline_metrics={},
            previous_artifact={},
        )

        self.assertEqual(rollout["rollout_mode"], "gated")
        self.assertEqual(rollout["activation_policy"], "quality_gate")
        self.assertEqual(rollout["signal_bundle_version"], "core_panel_v1")
        self.assertNotIn("shadow_evaluation", rollout)


class RegionalTruthLayerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.truth_service = TruthLayerService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    @staticmethod
    def _allocation_forecast(
        *,
        business_gate: dict | None = None,
        quality_gate: dict | None = None,
    ) -> dict:
        return {
            "virus_typ": "Influenza A",
            "as_of_date": "2026-03-16T00:00:00",
            "quality_gate": quality_gate or {"overall_passed": True, "forecast_readiness": "GO"},
            "business_gate": business_gate or {
                "validated_for_budget_activation": True,
                "evidence_tier": "commercially_validated",
            },
            "action_threshold": 0.6,
            "rollout_mode": "gated",
            "activation_policy": "quality_gate",
            "predictions": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "rank": 1,
                    "decision_rank": 1,
                    "event_probability_calibrated": 0.82,
                    "decision_label": "Activate",
                    "priority_score": 0.84,
                    "decision": {
                        "stage": "activate",
                        "forecast_confidence": 0.78,
                    },
                    "reason_trace": {
                        "why": ["Strong epidemiological signal."],
                        "contributing_signals": [],
                        "uncertainty": [],
                        "policy_overrides": [],
                    },
                    "uncertainty_summary": "Residual uncertainty is currently limited.",
                    "change_pct": 35.0,
                    "trend": "steigend",
                    "current_known_incidence": 10.0,
                    "expected_next_week_incidence": 28.0,
                    "prediction_interval": {"lower": 24.0, "upper": 32.0},
                    "as_of_date": "2026-03-16T00:00:00",
                    "target_week_start": "2026-03-23T00:00:00",
                    "quality_gate": quality_gate or {"overall_passed": True, "forecast_readiness": "GO"},
                    "business_gate": business_gate or {
                        "validated_for_budget_activation": True,
                        "evidence_tier": "commercially_validated",
                    },
                    "rollout_mode": "gated",
                    "activation_policy": "quality_gate",
                }
            ],
        }

    @staticmethod
    def _allocation_payload() -> dict:
        return {
            "headline": "Influenza A: Budget auf BY fokussieren",
            "allocation_policy_version": "regional_media_allocation_v1",
            "config": {"version": "regional_media_allocation_v1"},
            "summary": {
                "budget_share_total": 1.0,
                "total_budget_allocated": 50000.0,
            },
            "recommendations": [
                {
                    "bundesland": "BY",
                    "recommended_activation_level": "Activate",
                    "priority_rank": 1,
                    "suggested_budget_share": 1.0,
                    "suggested_budget_eur": 50000.0,
                    "suggested_budget_amount": 50000.0,
                    "allocation_score": 0.91,
                    "confidence": 0.82,
                    "reason_trace": {
                        "why": ["Activate gets the strongest score."],
                        "budget_drivers": ["High-confidence activate region."],
                        "uncertainty": [],
                        "blockers": [],
                    },
                    "spend_readiness": "ready",
                    "product_clusters": [],
                    "keyword_clusters": [],
                }
            ],
        }

    @staticmethod
    def _benchmark_payload() -> dict:
        return {
            "trained_viruses": 1,
            "go_viruses": 1,
            "business_gate": {
                "validated_for_budget_activation": True,
                "evidence_tier": "truth_backed",
            },
            "evidence_tier": "truth_backed",
            "benchmark": [
                {
                    "virus_typ": "Influenza A",
                    "status": "trained",
                    "rank": 1,
                    "benchmark_score": 63.0,
                    "quality_gate": {"overall_passed": True, "forecast_readiness": "GO"},
                    "business_gate": {
                        "validated_for_budget_activation": True,
                        "evidence_tier": "truth_backed",
                    },
                    "rollout_mode": "gated",
                    "activation_policy": "quality_gate",
                    "aggregate_metrics": {"precision_at_top3": 0.18},
                }
            ],
        }

    @staticmethod
    def _observation(
        *,
        week_start: datetime,
        metric_name: str,
        metric_value: float,
        product: str = "GeloMyrtol forte",
        region_code: str = "BY",
        holdout_group: str | None = None,
        metadata: dict | None = None,
    ) -> OutcomeObservationInput:
        return OutcomeObservationInput(
            brand="gelo",
            product=product,
            region_code=region_code,
            metric_name=metric_name,
            metric_value=metric_value,
            window_start=week_start,
            window_end=week_start + timedelta(days=6),
            source_label="manual",
            holdout_group=holdout_group,
            metadata=metadata or {},
        )

    def _seed_commercially_validated_truth(self, *, region_code: str = "BY", product: str = "GeloMyrtol forte") -> None:
        start = datetime(2025, 8, 4)
        observations: list[OutcomeObservationInput] = []
        for offset in range(34):
            week = start + timedelta(days=7 * offset)
            group = "test" if offset % 2 == 0 else "control"
            metadata = {"holdout_lift_pct": 8.0} if offset >= 20 else {}
            observations.extend(
                [
                    self._observation(
                        week_start=week,
                        metric_name="media_spend",
                        metric_value=1600 + offset * 25,
                        product=product,
                        region_code=region_code,
                        holdout_group=group,
                        metadata=metadata,
                    ),
                    self._observation(
                        week_start=week,
                        metric_name="revenue",
                        metric_value=5400 + offset * 90,
                        product=product,
                        region_code=region_code,
                        holdout_group=group,
                        metadata=metadata,
                    ),
                ]
            )
        self.truth_service.upsert_observations(observations)

    def test_generate_media_allocation_adds_truth_validation_and_release_guidance(self) -> None:
        self._seed_commercially_validated_truth()
        service = RegionalForecastService(db=self.db)
        service.predict_all_regions = lambda virus_typ, horizon_days=7: self._allocation_forecast()
        service.media_allocation_engine.allocate = lambda **kwargs: self._allocation_payload()

        result = service.generate_media_allocation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        first = result["recommendations"][0]
        self.assertTrue(first["truth_layer_enabled"])
        self.assertEqual(first["outcome_readiness"]["status"], "ready")
        self.assertEqual(first["evidence_status"], "commercially_validated")
        self.assertEqual(first["spend_gate_status"], "released")
        self.assertEqual(first["budget_release_recommendation"], "release")
        self.assertTrue(first["signal_outcome_agreement"]["historical_response_observed"])
        self.assertEqual(first["truth_assessments"][0]["product"], "GeloMyrtol forte")
        self.assertEqual(result["truth_layer"]["evidence_status_counts"]["commercially_validated"], 1)
        self.assertEqual(
            result["truth_layer"]["budget_release_recommendation_counts"]["release"],
            1,
        )

    def test_generate_media_allocation_stays_stable_when_truth_scope_has_no_data(self) -> None:
        service = RegionalForecastService(db=self.db)
        service.predict_all_regions = lambda virus_typ, horizon_days=7: self._allocation_forecast(
            business_gate={
                "validated_for_budget_activation": True,
                "evidence_tier": "commercially_validated",
            },
            quality_gate={"overall_passed": True, "forecast_readiness": "GO"},
        )
        service.media_allocation_engine.allocate = lambda **kwargs: self._allocation_payload()

        result = service.generate_media_allocation(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
        )

        first = result["recommendations"][0]
        self.assertEqual(first["evidence_status"], "no_truth")
        self.assertEqual(first["spend_gate_status"], "manual_review_required")
        self.assertEqual(first["budget_release_recommendation"], "manual_review")
        self.assertEqual(first["suggested_budget_eur"], 50000.0)
        self.assertTrue(first["truth_assessments"])

    def test_build_portfolio_view_exposes_truth_overlay_without_changing_epidemiological_action(self) -> None:
        self._seed_commercially_validated_truth()
        service = RegionalForecastService(db=self.db)
        service.benchmark_supported_viruses = lambda reference_virus="Influenza A", horizon_days=7: self._benchmark_payload()
        service.predict_all_regions = lambda virus_typ, horizon_days=7: self._allocation_forecast()

        result = service.build_portfolio_view(
            top_n=3,
            reference_virus="Influenza A",
            horizon_days=7,
        )

        first = result["top_opportunities"][0]
        self.assertEqual(first["portfolio_action"], "activate")
        self.assertEqual(first["evidence_status"], "commercially_validated")
        self.assertEqual(first["spend_gate_status"], "released")
        self.assertEqual(first["budget_release_recommendation"], "release")
        self.assertEqual(first["truth_assessments"][0]["product"], "GeloMyrtol forte")
        self.assertEqual(result["truth_layer"]["spend_gate_status_counts"]["released"], 1)


class RegionalCampaignRecommendationIntegrationTests(unittest.TestCase):
    def test_generate_campaign_recommendations_consumes_allocation_output(self) -> None:
        service = RegionalForecastService(db=None)
        service.generate_media_allocation = lambda virus_typ="Influenza A", weekly_budget_eur=50000, horizon_days=7: {
            "virus_typ": virus_typ,
            "horizon_days": horizon_days,
            "target_window_days": [horizon_days, horizon_days],
            "summary": {
                "total_budget_allocated": 12000.0,
                "budget_share_total": 1.0,
            },
            "truth_layer": {
                "enabled": False,
                "scopes_evaluated": 1,
            },
            "recommendations": [
                {
                    "bundesland": "BY",
                    "bundesland_name": "Bayern",
                    "recommended_activation_level": "Activate",
                    "priority_rank": 1,
                    "suggested_budget_share": 0.24,
                    "suggested_budget_eur": 12000.0,
                    "suggested_budget_amount": 12000.0,
                    "confidence": 0.78,
                    "products": ["GeloMyrtol forte", "GeloRevoice"],
                    "channels": ["Banner (programmatic)", "Meta (regional)"],
                    "timeline": "Sofort aktivieren",
                    "allocation_score": 0.88,
                    "spend_gate_status": "released",
                    "budget_release_recommendation": "release",
                    "evidence_status": "truth_backed",
                    "truth_layer_enabled": False,
                    "signal_outcome_agreement": {
                        "status": "no_outcome_support",
                        "signal_present": True,
                        "historical_response_observed": False,
                    },
                    "product_clusters": [
                        {
                            "cluster_key": "gelo_core_respiratory",
                            "label": "Influenza A core demand cluster",
                            "priority_rank": 1,
                            "fit_score": 0.82,
                            "products": ["GeloMyrtol forte", "GeloRevoice"],
                        }
                    ],
                }
            ],
        }

        result = service.generate_campaign_recommendations(
            virus_typ="Influenza A",
            weekly_budget_eur=50000,
            horizon_days=7,
            top_n=6,
        )

        self.assertEqual(result["horizon_days"], 7)
        self.assertEqual(result["target_window_days"], [7, 7])
        self.assertEqual(result["summary"]["total_recommendations"], 1)
        first = result["recommendations"][0]
        self.assertEqual(first["region"], "BY")
        self.assertEqual(first["recommended_product_cluster"]["cluster_key"], "gelo_core_respiratory")
        self.assertIn("recommended_keyword_cluster", first)
        self.assertIn("recommendation_rationale", first)


if __name__ == "__main__":
    unittest.main()
