import json
import tempfile
import unittest
from pathlib import Path

from app.services.ml.benchmarking.artifacts import write_benchmark_artifacts
from app.services.ml.benchmarking.contracts import BenchmarkArtifactSummary
from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.services.ml.benchmarking.registry import (
    DEFAULT_METRIC_SEMANTICS_VERSION,
    ForecastRegistry,
    LEGACY_REGIONAL_EVENT_DEFINITION_VERSION,
    LEGACY_REGIONAL_METRIC_SEMANTICS_VERSION,
    LEGACY_REGIONAL_QUANTILE_GRID_VERSION,
    LEGACY_REGIONAL_SCIENCE_CONTRACT_VERSION,
)
from app.services.ml.forecast_orchestrator import ForecastOrchestrator


class ForecastBenchmarkingTests(unittest.TestCase):
    def test_summarize_probabilistic_metrics_returns_wis_coverage_and_event_metrics(self) -> None:
        metrics = summarize_probabilistic_metrics(
            y_true=[10.0, 12.0, 14.0],
            quantile_predictions={
                0.025: [7.0, 9.0, 11.0],
                0.1: [8.0, 10.0, 12.0],
                0.25: [9.0, 11.0, 13.0],
                0.5: [10.0, 12.0, 14.0],
                0.75: [11.0, 13.0, 15.0],
                0.9: [12.0, 14.0, 16.0],
                0.975: [13.0, 15.0, 17.0],
            },
            baseline_quantiles={
                0.1: [7.0, 9.0, 11.0],
                0.5: [9.0, 11.0, 13.0],
                0.9: [11.0, 13.0, 15.0],
            },
            event_labels=[0, 1, 1],
            event_probabilities=[0.2, 0.7, 0.8],
            action_threshold=0.6,
        )

        self.assertIn("wis", metrics)
        self.assertIn("relative_wis", metrics)
        self.assertIn("crps", metrics)
        self.assertIn("coverage_95", metrics)
        self.assertIn("winkler_80", metrics)
        self.assertIn("winkler_95", metrics)
        self.assertIn("pinball_loss", metrics)
        self.assertIn("brier_score", metrics)
        self.assertIn("decision_utility", metrics)

    def test_summarize_probabilistic_metrics_rewards_sharper_well_centered_forecasts(self) -> None:
        sharper = summarize_probabilistic_metrics(
            y_true=[10.0, 12.0, 14.0],
            quantile_predictions={
                0.025: [9.2, 11.2, 13.2],
                0.1: [9.5, 11.5, 13.5],
                0.25: [9.8, 11.8, 13.8],
                0.5: [10.0, 12.0, 14.0],
                0.75: [10.2, 12.2, 14.2],
                0.9: [10.5, 12.5, 14.5],
                0.975: [10.8, 12.8, 14.8],
            },
        )
        wider = summarize_probabilistic_metrics(
            y_true=[10.0, 12.0, 14.0],
            quantile_predictions={
                0.025: [4.0, 6.0, 8.0],
                0.1: [6.0, 8.0, 10.0],
                0.25: [8.0, 10.0, 12.0],
                0.5: [10.0, 12.0, 14.0],
                0.75: [12.0, 14.0, 16.0],
                0.9: [14.0, 16.0, 18.0],
                0.975: [16.0, 18.0, 20.0],
            },
        )

        self.assertLess(sharper["crps"], wider["crps"])
        self.assertLess(sharper["wis"], wider["wis"])
        self.assertLess(sharper["winkler_95"], wider["winkler_95"])

    def test_registry_promotes_better_relative_wis_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ForecastRegistry(registry_root=Path(tmpdir))
            scope = registry.record_evaluation(
                virus_typ="Influenza A",
                horizon_days=7,
                model_family="regional_pooled_panel",
                metrics={"relative_wis": 0.98, "crps": 1.4, "coverage_95": 0.95, "brier_score": 0.09, "ece": 0.05},
                metadata={"model_version": "baseline"},
                promote=True,
            )
            self.assertEqual(scope["champion"]["model_family"], "regional_pooled_panel")

            promoted = registry.should_promote(
                candidate_metrics={"relative_wis": 0.94, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
                champion_metrics=scope["champion"]["metrics"],
            )
            self.assertTrue(promoted)

    def test_registry_defaults_to_app_ml_models_directory(self) -> None:
        registry = ForecastRegistry()

        self.assertTrue(str(registry.registry_root).endswith("/backend/app/ml_models/forecast_registry"))

    def test_registry_load_scope_backfills_legacy_regional_champion_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_root = Path(tmpdir)
            scope_dir = registry_root / "influenza_a" / "horizon_7"
            scope_dir.mkdir(parents=True, exist_ok=True)
            scope_dir.joinpath("registry.json").write_text(
                json.dumps(
                    {
                        "virus_typ": "Influenza A",
                        "horizon_days": 7,
                        "champion": {
                            "model_family": "regional_pooled_panel",
                            "status": "champion",
                            "metrics": {"relative_wis": 0.91},
                            "metadata": {
                                "model_version": "regional_pooled_panel:h7:2026-03-23T19:26:51.984764",
                                "calibration_version": "raw_passthrough:h7:2026-03-23T19:26:51.984764",
                                "rollout_mode": "gated",
                            },
                        },
                        "history": [],
                    }
                )
            )

            scope = ForecastRegistry(registry_root=registry_root).load_scope(
                virus_typ="Influenza A",
                horizon_days=7,
            )

            champion_metadata = scope["champion"]["metadata"]
            self.assertEqual(champion_metadata["registry_status"], "champion")
            self.assertEqual(champion_metadata["metric_semantics_version"], LEGACY_REGIONAL_METRIC_SEMANTICS_VERSION)
            self.assertEqual(
                champion_metadata["event_definition_version"],
                LEGACY_REGIONAL_EVENT_DEFINITION_VERSION,
            )
            self.assertEqual(
                champion_metadata["quantile_grid_version"],
                LEGACY_REGIONAL_QUANTILE_GRID_VERSION,
            )
            self.assertEqual(
                champion_metadata["science_contract_version"],
                LEGACY_REGIONAL_SCIENCE_CONTRACT_VERSION,
            )
            self.assertEqual(champion_metadata["calibration_mode"], "raw_passthrough")
            self.assertTrue(champion_metadata["champion_scope_active"])
            self.assertTrue(champion_metadata["legacy_metadata_backfill"])

    def test_registry_record_evaluation_persists_full_science_contract_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ForecastRegistry(registry_root=Path(tmpdir))
            payload = registry.record_evaluation(
                virus_typ="Influenza A",
                horizon_days=7,
                model_family="regional_pooled_panel",
                metrics={"relative_wis": 0.91},
                metadata={
                    "model_version": "regional_pooled_panel:h7:2026-04-12T12:21:06.673194",
                    "calibration_version": "raw_passthrough:h7:2026-04-12T12:21:06.673194",
                    "rollout_mode": "gated",
                    "registry_status": "challenger",
                    "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                    "event_definition_version": "regional_survstat_v2",
                    "quantile_grid_version": "canonical_quantile_grid_v1",
                    "science_contract_version": "regional_h7_science_contract_v1",
                    "calibration_mode": "raw_passthrough",
                    "calibration_evidence_mode": "oof_predictions_only",
                    "champion_scope_active": True,
                    "champion_scope_reason": "Active h7 champion scope in the first product phase.",
                    "oof_calibration_only": True,
                    "weather_vintage_discipline_passed": True,
                    "quantile_monotonicity_passed": True,
                    "sample_count": 873,
                    "quality_gate_overall_passed": False,
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "WATCH"},
                },
                promote=False,
            )

            latest_metadata = payload["history"][-1]["metadata"]
            self.assertEqual(latest_metadata["registry_status"], "challenger")
            self.assertEqual(latest_metadata["science_contract_version"], "regional_h7_science_contract_v1")
            self.assertEqual(latest_metadata["calibration_evidence_mode"], "oof_predictions_only")
            self.assertEqual(latest_metadata["quality_gate"]["forecast_readiness"], "WATCH")
            self.assertTrue(latest_metadata["weather_vintage_discipline_passed"])

    def test_registry_rejects_candidate_when_crps_gets_worse(self) -> None:
        registry = ForecastRegistry()

        promoted = registry.should_promote(
            candidate_metrics={"relative_wis": 0.94, "crps": 1.6, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            champion_metrics={"relative_wis": 0.98, "crps": 1.4, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
        )

        self.assertFalse(promoted)

    def test_registry_blocks_strict_promotion_when_quality_gate_fails(self) -> None:
        registry = ForecastRegistry()

        evidence = registry.evaluate_promotion(
            candidate_metrics={"relative_wis": 0.94, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            champion_metrics={"relative_wis": 0.98, "crps": 1.4, "coverage_95": 0.95, "brier_score": 0.09, "ece": 0.05},
            candidate_metadata={
                "quality_gate_overall_passed": False,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
                "virus_typ": "Influenza A",
                "horizon_days": 7,
                "champion_scope_active": True,
                "weather_vintage_discipline_passed": True,
                "oof_calibration_only": True,
                "quantile_monotonicity_passed": True,
            },
            champion_metadata={
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
            },
        )

        self.assertFalse(evidence["promotion_allowed"])
        self.assertIn("quality_gate_not_passed", evidence["promotion_blockers"])

    def test_registry_blocks_strict_promotion_when_metric_semantics_are_incompatible(self) -> None:
        registry = ForecastRegistry()

        evidence = registry.evaluate_promotion(
            candidate_metrics={"relative_wis": 0.94, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            champion_metrics={"relative_wis": 0.98, "crps": 1.4, "coverage_95": 0.95, "brier_score": 0.09, "ece": 0.05},
            candidate_metadata={
                "quality_gate_overall_passed": True,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
                "virus_typ": "Influenza A",
                "horizon_days": 7,
                "champion_scope_active": True,
                "weather_vintage_discipline_passed": True,
                "oof_calibration_only": True,
                "quantile_monotonicity_passed": True,
            },
            champion_metadata={
                "metric_semantics_version": "regional_probabilistic_metrics_v0",
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
            },
        )

        self.assertFalse(evidence["promotion_allowed"])
        self.assertIn("metric_semantics_incompatible", evidence["promotion_blockers"])

    def test_registry_blocks_strict_promotion_when_sample_count_is_below_minimum(self) -> None:
        registry = ForecastRegistry()

        evidence = registry.evaluate_promotion(
            candidate_metrics={"relative_wis": 0.94, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            champion_metrics={"relative_wis": 0.98, "crps": 1.4, "coverage_95": 0.95, "brier_score": 0.09, "ece": 0.05},
            candidate_metadata={
                "quality_gate_overall_passed": True,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 6,
                "virus_typ": "Influenza A",
                "horizon_days": 7,
                "champion_scope_active": True,
                "weather_vintage_discipline_passed": True,
                "oof_calibration_only": True,
                "quantile_monotonicity_passed": True,
            },
            champion_metadata={
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
            },
        )

        self.assertFalse(evidence["promotion_allowed"])
        self.assertIn("minimum_sample_count_not_met", evidence["promotion_blockers"])

    def test_registry_allows_strict_promotion_when_evidence_is_complete(self) -> None:
        registry = ForecastRegistry()

        evidence = registry.evaluate_promotion(
            candidate_metrics={"relative_wis": 0.94, "crps": 1.2, "coverage_95": 0.95, "brier_score": 0.08, "ece": 0.04},
            champion_metrics={"relative_wis": 0.98, "crps": 1.4, "coverage_95": 0.94, "brier_score": 0.09, "ece": 0.05},
            candidate_metadata={
                "quality_gate_overall_passed": True,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
                "virus_typ": "Influenza A",
                "horizon_days": 7,
                "champion_scope_active": True,
                "weather_vintage_discipline_passed": True,
                "oof_calibration_only": True,
                "quantile_monotonicity_passed": True,
            },
            champion_metadata={
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
            },
        )

        self.assertTrue(evidence["promotion_allowed"])
        self.assertEqual(evidence["promotion_blockers"], [])
        self.assertEqual(
            [item["name"] for item in evidence["promotion_gate_sequence"]],
            [
                "champion_scope",
                "leakage_and_vintage",
                "wis",
                "coverage",
                "event_calibration",
                "operational_utility",
            ],
        )

    def test_registry_blocks_promotion_for_non_active_h7_scope_even_when_metrics_are_good(self) -> None:
        registry = ForecastRegistry()

        evidence = registry.evaluate_promotion(
            candidate_metrics={"relative_wis": 0.91, "crps": 1.1, "coverage_95": 0.95, "brier_score": 0.07, "ece": 0.03},
            champion_metrics=None,
            candidate_metadata={
                "quality_gate_overall_passed": True,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
                "virus_typ": "SARS-CoV-2",
                "horizon_days": 7,
                "champion_scope_active": False,
                "weather_vintage_discipline_passed": True,
                "oof_calibration_only": True,
                "quantile_monotonicity_passed": True,
            },
        )

        self.assertFalse(evidence["promotion_allowed"])
        self.assertIn("champion_scope_not_active", evidence["promotion_blockers"])

    def test_registry_blocks_promotion_when_vintage_or_calibration_contract_is_broken(self) -> None:
        registry = ForecastRegistry()

        evidence = registry.evaluate_promotion(
            candidate_metrics={"relative_wis": 0.91, "crps": 1.1, "coverage_95": 0.95, "brier_score": 0.07, "ece": 0.03},
            champion_metrics=None,
            candidate_metadata={
                "quality_gate_overall_passed": True,
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "event_definition_version": "regional_survstat_v2",
                "quantile_grid_version": "canonical_quantile_grid_v1",
                "sample_count": 24,
                "virus_typ": "Influenza A",
                "horizon_days": 7,
                "champion_scope_active": True,
                "weather_vintage_discipline_passed": False,
                "oof_calibration_only": False,
                "quantile_monotonicity_passed": False,
            },
        )

        self.assertFalse(evidence["promotion_allowed"])
        self.assertIn("vintage_discipline_not_passed", evidence["promotion_blockers"])
        self.assertIn("oof_calibration_not_passed", evidence["promotion_blockers"])
        self.assertIn("quantile_monotonicity_not_passed", evidence["promotion_blockers"])

    def test_orchestrator_resolves_revision_policy_from_metadata(self) -> None:
        orchestrator = ForecastOrchestrator()

        self.assertEqual(
            orchestrator.resolve_revision_policy(
                metadata={"revision_policy_metadata": {"default_policy": "adaptive"}}
            ),
            "adaptive",
        )
        self.assertEqual(
            orchestrator.resolve_revision_policy(
                metadata={"revision_policy_metadata": {"default_policy": "raw"}},
                requested_policy="adjusted",
            ),
            "adjusted",
        )

    def test_artifact_writer_persists_summary_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            summary = BenchmarkArtifactSummary(
                virus_typ="Influenza A",
                horizon_days=7,
                issue_dates=["2026-03-01"],
                primary_metric="relative_wis",
                champion_name="regional_pooled_panel",
                metrics={"relative_wis": 0.94, "crps": 1.12},
                leaderboard=[{"candidate": "regional_pooled_panel", "relative_wis": 0.94, "crps": 1.12, "winkler_95": 4.8, "coverage_95": 0.95, "brier_score": 0.08, "decision_utility": 0.71, "samples": 12}],
            )
            paths = write_benchmark_artifacts(
                output_dir=output_dir,
                summary=summary,
                diagnostics=[{"fold": 1, "candidate": "regional_pooled_panel"}],
            )

            self.assertTrue(Path(paths["summary"]).exists())
            self.assertTrue(Path(paths["report"]).exists())
            payload = json.loads(Path(paths["summary"]).read_text())
            self.assertEqual(payload["champion_name"], "regional_pooled_panel")
            report_text = Path(paths["report"]).read_text()
            self.assertIn("CRPS", report_text)
