import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.ml.benchmarking.artifacts import write_benchmark_artifacts
from app.services.ml.benchmarking.contracts import BenchmarkArtifactSummary
from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.services.ml.benchmarking.registry import (
    DEFAULT_METRIC_SEMANTICS_VERSION,
    ForecastRegistry,
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
                "sample_count": 24,
            },
            champion_metadata={
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
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
                "sample_count": 24,
            },
            champion_metadata={
                "metric_semantics_version": "regional_probabilistic_metrics_v0",
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
                "sample_count": 6,
            },
            champion_metadata={
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
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
                "sample_count": 24,
            },
            champion_metadata={
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "sample_count": 24,
            },
        )

        self.assertTrue(evidence["promotion_allowed"])
        self.assertEqual(evidence["promotion_blockers"], [])

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
