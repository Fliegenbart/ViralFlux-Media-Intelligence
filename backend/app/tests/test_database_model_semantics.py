import unittest
from datetime import datetime

from app.models.database import (
    OutbreakScore,
    WastewaterData,
    VirusWaveAlignment,
    VirusWaveBacktestEvent,
    VirusWaveBacktestResult,
    VirusWaveBacktestRun,
    VirusWaveEvidence,
    VirusWaveFeature,
    VirusWaveFeatureRun,
)
from app.schemas.outbreak_score import OutbreakScoreResponse


class DatabaseModelSemanticsTests(unittest.TestCase):
    def test_outbreak_score_model_uses_decision_priority_index_on_python_side(self) -> None:
        row = OutbreakScore(
            decision_priority_index=72.5,
            signal_level="HIGH",
            signal_source="forecast_decision_service",
            reliability_label="Hoch",
            reliability_score=0.81,
        )

        self.assertEqual(row.decision_priority_index, 72.5)
        self.assertEqual(row.signal_level, "HIGH")
        self.assertEqual(row.signal_source, "forecast_decision_service")
        self.assertEqual(row.reliability_label, "Hoch")
        self.assertEqual(row.reliability_score, 0.81)
        self.assertFalse(hasattr(row, "decision_signal_index"))
        self.assertFalse(hasattr(row, "final_risk_score"))
        self.assertFalse(hasattr(row, "risk_level"))
        self.assertFalse(hasattr(row, "leading_indicator"))
        self.assertFalse(hasattr(row, "confidence_level"))
        self.assertFalse(hasattr(row, "confidence_numeric"))

    def test_outbreak_score_response_serializes_new_field_name(self) -> None:
        row = OutbreakScore(
            id=1,
            datum=datetime(2026, 4, 11, 12, 0, 0),
            virus_typ="Influenza A",
            decision_priority_index=72.5,
            signal_level="HIGH",
            signal_source="forecast_decision_service",
            reliability_label="Hoch",
            reliability_score=0.81,
        )
        row.created_at = datetime(2026, 4, 11, 12, 5, 0)

        payload = OutbreakScoreResponse.model_validate(row).model_dump()

        self.assertEqual(payload["decision_priority_index"], 72.5)
        self.assertNotIn("decision_signal_index", payload)

    def test_virus_wave_materialization_models_expose_audit_fields(self) -> None:
        run = VirusWaveFeatureRun(
            run_key="Influenza A:DE:runtime-v1.1",
            algorithm_version="virus-wave-evidence-runtime-v1.1",
            mode="materialized",
            status="success",
            pathogen="Influenza A",
            region_code="DE",
            parameters_json={"lookback_weeks": 156},
            snapshot_json={"schema": "virus_wave_truth_v1"},
        )
        feature = VirusWaveFeature(
            source="amelag",
            source_role="early_warning_trend_signal",
            pathogen="Influenza A",
            region_code="DE",
            season="2025_2026",
            phase="post_wave",
            signal_basis="vorhersage",
            confidence_score=0.82,
            algorithm_version="virus-wave-evidence-runtime-v1.1",
        )
        alignment = VirusWaveAlignment(
            pathogen="Influenza A",
            region_code="DE",
            season="2025_2026",
            early_source="amelag",
            confirmed_source="survstat",
            raw_lead_lag_days=-7,
            early_source_lead_days=7,
            alignment_status="amelag_leads_survstat",
            alignment_score=0.82,
            algorithm_version="virus-wave-evidence-runtime-v1.1",
        )
        evidence = VirusWaveEvidence(
            pathogen="Influenza A",
            region_code="DE",
            season="2025_2026",
            profile_name="early_warning",
            primary_source="amelag",
            base_weights_json={"amelag": 0.65},
            quality_multipliers_json={"amelag": 0.9},
            effective_weights_json={"amelag": 0.8},
            source_availability_json={"amelag": "available"},
            evidence_coverage=0.72,
            evidence_mode="diagnostic_only",
            budget_can_change=False,
            confidence_score=0.82,
            confidence_method="heuristic_v1",
            algorithm_version="virus-wave-evidence-runtime-v1.1",
        )

        self.assertEqual(run.__tablename__, "virus_wave_feature_runs")
        self.assertEqual(feature.signal_basis, "vorhersage")
        self.assertEqual(alignment.early_source_lead_days, 7)
        self.assertFalse(evidence.budget_can_change)
        self.assertEqual(evidence.effective_weights_json["amelag"], 0.8)

    def test_virus_wave_backtest_models_are_research_only(self) -> None:
        run = VirusWaveBacktestRun(
            run_key="wave-backtest:Influenza A:DE:historical_cutoff:v1.3",
            algorithm_version="virus-wave-evidence-runtime-v1.1",
            backtest_version="virus-wave-backtest-v1.3",
            mode="historical_cutoff",
            status="success",
            pathogens=["Influenza A"],
            regions=["DE"],
            seasons=["2025_2026"],
            baseline_models=["survstat_only"],
            candidate_models=["evidence_v1_1_quality_weighted"],
            parameters_json={"backtest_safe": True},
            summary_json={"budget_impact": {"can_change_budget": False}},
        )
        result = VirusWaveBacktestResult(
            pathogen="Influenza A",
            canonical_pathogen="Influenza A",
            region_code="DE",
            season="2025_2026",
            model_name="evidence_v1_1_quality_weighted",
            onset_detection_gain_days=7.0,
            phase_accuracy=0.8,
            false_early_warning_rate=0.0,
            missed_wave_rate=0.0,
            summary_json={"mode": "diagnostic_only"},
        )
        event = VirusWaveBacktestEvent(
            pathogen="Influenza A",
            canonical_pathogen="Influenza A",
            region_code="DE",
            season="2025_2026",
            event_type="onset",
            event_date=datetime(2026, 1, 5),
            model_name="evidence_v1_1_quality_weighted",
            predicted_phase="early_growth",
            observed_phase="early_growth",
            confidence_score=0.8,
        )

        self.assertEqual(run.mode, "historical_cutoff")
        self.assertFalse(run.summary_json["budget_impact"]["can_change_budget"])
        self.assertEqual(result.model_name, "evidence_v1_1_quality_weighted")
        self.assertEqual(event.event_type, "onset")

    def test_wastewater_data_exposes_laborwechsel_quality_flag(self) -> None:
        row = WastewaterData(
            standort="Aachen",
            bundesland="NW",
            datum=datetime(2026, 1, 7),
            virus_typ="SARS-CoV-2",
            viruslast=220.0,
            laborwechsel=True,
        )

        self.assertTrue(row.laborwechsel)


if __name__ == "__main__":
    unittest.main()
