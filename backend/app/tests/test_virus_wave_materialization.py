from datetime import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    Base,
    VirusWaveAlignment,
    VirusWaveEvidence,
    VirusWaveFeature,
    VirusWaveFeatureRun,
)
from app.services.media.cockpit.virus_wave_materialization import (
    materialize_virus_wave_truth_payload,
    read_latest_materialized_virus_wave_truth,
)


def _sample_payload() -> dict:
    return {
        "schema": "virus_wave_truth_v1",
        "engine_version": "virus_wave_truth_runtime_v1_1",
        "algorithm_version": "virus-wave-evidence-runtime-v1.1",
        "scope": {"virus": "Influenza A", "region": "DE", "lookback_weeks": 156},
        "sourceStatus": {"computation_mode": "runtime_from_existing_timeseries"},
        "survstat_phase": "decline",
        "amelag_phase": "post_wave",
        "lead_lag_days": -7,
        "amelag_lead_days": 7,
        "alignment_status": "amelag_leads_survstat",
        "alignment_score": 0.82,
        "survstat": {
            "source": "survstat",
            "virus": "Influenza A",
            "region": "DE",
            "status": "ok",
            "data_points": 155,
            "latest_date": "2026-04-20",
            "phase": "decline",
            "onset_date": "2025-10-06",
            "peak_date": "2026-01-26",
            "peak_intensity": 22.0,
            "wave_strength": 0.52,
            "growth_rate_1w": -0.10,
            "growth_rate_2w": -0.20,
            "confidence": 0.71,
        },
        "amelag": {
            "source": "amelag",
            "virus": "Influenza A",
            "region": "DE",
            "status": "ok",
            "data_points": 125,
            "latest_date": "2026-04-23",
            "phase": "post_wave",
            "onset_date": "2025-10-01",
            "peak_date": "2026-01-19",
            "peak_intensity": 18.0,
            "wave_strength": 0.48,
            "growth_rate_1w": -0.04,
            "growth_rate_2w": -0.12,
            "confidence": 0.80,
        },
        "alignment": {
            "status": "amelag_leads_survstat",
            "lead_lag_days": -7,
            "correlation": 0.86,
            "alignment_score": 0.82,
            "divergence_score": 0.18,
            "onset_lag_days": -5,
            "peak_lag_days": -7,
        },
        "evidence": {
            "mode": "diagnostic_only",
            "algorithm_version": "virus-wave-evidence-runtime-v1.1",
            "source_roles": {
                "amelag": "early_warning_trend_signal",
                "survstat": "confirmed_reporting_signal",
                "syndromic": "planned_population_symptom_signal",
                "severity": "planned_healthcare_burden_signal",
            },
            "source_availability": {
                "amelag": "available",
                "survstat": "available",
                "syndromic": "planned_unavailable",
                "severity": "planned_unavailable",
            },
            "early_warning_signal": {
                "primary_source": "amelag",
                "phase": "post_wave",
                "confidence": 0.82,
                "confidence_method": "heuristic_v1",
            },
            "confirmed_reporting_signal": {
                "primary_source": "survstat",
                "phase": "decline",
                "confidence": 0.71,
                "confidence_method": "heuristic_v1",
            },
            "weight_profiles": {
                "early_warning": {
                    "base_weights": {"amelag": 0.65, "survstat": 0.20, "syndromic": 0.15, "severity": 0.0},
                    "quality_multipliers": {"amelag": 0.90, "survstat": 0.72, "syndromic": 0.0, "severity": 0.0},
                    "effective_weights": {"amelag": 0.80, "survstat": 0.20, "syndromic": 0.0, "severity": 0.0},
                    "evidence_coverage": 0.72,
                    "missing_sources": ["syndromic", "severity"],
                },
                "phase_detection": {
                    "base_weights": {"amelag": 0.50, "survstat": 0.35, "syndromic": 0.15, "severity": 0.0},
                    "quality_multipliers": {"amelag": 0.90, "survstat": 0.72, "syndromic": 0.0, "severity": 0.0},
                    "effective_weights": {"amelag": 0.64, "survstat": 0.36, "syndromic": 0.0, "severity": 0.0},
                    "evidence_coverage": 0.70,
                    "missing_sources": ["syndromic", "severity"],
                },
                "confirmed_burden": {
                    "base_weights": {"amelag": 0.15, "survstat": 0.45, "syndromic": 0.25, "severity": 0.15},
                    "quality_multipliers": {"amelag": 0.90, "survstat": 0.72, "syndromic": 0.0, "severity": 0.0},
                    "effective_weights": {"amelag": 0.29, "survstat": 0.71, "syndromic": 0.0, "severity": 0.0},
                    "evidence_coverage": 0.46,
                    "missing_sources": ["syndromic", "severity"],
                },
                "severity_pressure": {
                    "base_weights": {"amelag": 0.05, "survstat": 0.15, "syndromic": 0.20, "severity": 0.60},
                    "quality_multipliers": {"amelag": 0.90, "survstat": 0.72, "syndromic": 0.0, "severity": 0.0},
                    "effective_weights": {"amelag": 0.29, "survstat": 0.71, "syndromic": 0.0, "severity": 0.0},
                    "evidence_coverage": 0.15,
                    "missing_sources": ["syndromic", "severity"],
                },
            },
            "amelag_quality": {
                "signal_basis": "vorhersage",
                "data_freshness_days": 5,
                "quality_flags": [],
            },
            "budget_impact": {
                "mode": "diagnostic_only",
                "can_change_budget": False,
                "reason": "awaiting_backtest_validation",
            },
        },
    }


class VirusWaveMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            bind=self.engine,
            tables=[
                VirusWaveFeatureRun.__table__,
                VirusWaveFeature.__table__,
                VirusWaveAlignment.__table__,
                VirusWaveEvidence.__table__,
            ],
        )
        self.Session = sessionmaker(bind=self.engine)

    def test_materialization_persists_normalized_evidence_and_is_idempotent(self) -> None:
        db = self.Session()
        try:
            first = materialize_virus_wave_truth_payload(db, _sample_payload())
            db.commit()
            second = materialize_virus_wave_truth_payload(db, _sample_payload())
            db.commit()

            self.assertEqual(first["run_key"], second["run_key"])
            self.assertEqual(db.query(VirusWaveFeatureRun).count(), 1)
            self.assertEqual(db.query(VirusWaveFeature).count(), 2)
            self.assertEqual(db.query(VirusWaveAlignment).count(), 1)
            self.assertEqual(db.query(VirusWaveEvidence).count(), 4)

            early = (
                db.query(VirusWaveEvidence)
                .filter(VirusWaveEvidence.profile_name == "early_warning")
                .one()
            )
            self.assertEqual(early.primary_source, "amelag")
            self.assertEqual(early.evidence_mode, "diagnostic_only")
            self.assertFalse(early.budget_can_change)
            self.assertEqual(early.base_weights_json["amelag"], 0.65)
            self.assertEqual(early.effective_weights_json["amelag"], 0.80)
        finally:
            db.close()

    def test_latest_materialized_read_returns_snapshot_with_materialization_metadata(self) -> None:
        db = self.Session()
        try:
            materialize_virus_wave_truth_payload(db, _sample_payload(), computed_at=datetime(2026, 4, 30, 8, 0, 0))
            db.commit()

            payload = read_latest_materialized_virus_wave_truth(
                db,
                virus_typ="Influenza A",
                region="DE",
            )

            self.assertIsNotNone(payload)
            assert payload is not None
            self.assertEqual(payload["evidence"]["weight_profiles"]["early_warning"]["effective_weights"]["amelag"], 0.80)
            self.assertFalse(payload["evidence"]["budget_impact"]["can_change_budget"])
            self.assertEqual(payload["materialization"]["mode"], "materialized")
            self.assertEqual(payload["materialization"]["status"], "success")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
