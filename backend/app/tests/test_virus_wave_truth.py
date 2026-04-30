from datetime import date, timedelta
import unittest

from app.services.media.cockpit.virus_wave_truth import (
    AMELAG_VIRUS_BY_SCOPE,
    SURVSTAT_DISEASES_BY_VIRUS,
    align_wave_points,
    build_wave_evidence,
    compute_wave_features_from_points,
    select_amelag_signal_basis,
)


def _weekly_points(start: date, values: list[float]) -> list[dict]:
    return [
        {
            "date": start + timedelta(days=7 * idx),
            "value": value,
        }
        for idx, value in enumerate(values)
    ]


class VirusWaveTruthTests(unittest.TestCase):
    def test_canonical_source_mappings_include_combined_influenza_and_rsv(self) -> None:
        self.assertEqual(SURVSTAT_DISEASES_BY_VIRUS["Influenza A+B"], ("influenza, saisonal",))
        self.assertEqual(AMELAG_VIRUS_BY_SCOPE["Influenza A+B"], "Influenza A+B")
        self.assertIn("rsv (meldepflicht gemäß ifsg)", SURVSTAT_DISEASES_BY_VIRUS["RSV"])
        self.assertEqual(AMELAG_VIRUS_BY_SCOPE["RSV"], "RSV A+B")

    def test_wave_features_identify_growth_phase_and_onset(self) -> None:
        points = _weekly_points(
            date(2026, 1, 5),
            [1.0, 1.2, 1.1, 1.3, 2.4, 4.5, 8.8, 13.0],
        )

        features = compute_wave_features_from_points(
            points,
            source="survstat",
            virus_typ="Influenza A",
            region="DE",
        )

        self.assertEqual(features["phase"], "early_growth")
        self.assertEqual(features["onset_date"], "2026-02-02")
        self.assertEqual(features["peak_date"], "2026-02-23")
        self.assertGreater(features["wave_strength"], 0.5)
        self.assertGreater(features["confidence"], 0.5)

    def test_alignment_reports_negative_lag_when_amelag_leads_survstat(self) -> None:
        amelag_points = _weekly_points(
            date(2026, 1, 5),
            [1, 2, 4, 8, 16, 12, 8, 4],
        )
        survstat_points = _weekly_points(
            date(2026, 1, 12),
            [1, 2, 4, 8, 16, 12, 8, 4],
        )
        survstat_features = compute_wave_features_from_points(
            survstat_points,
            source="survstat",
            virus_typ="Influenza A",
            region="DE",
        )
        amelag_features = compute_wave_features_from_points(
            amelag_points,
            source="amelag",
            virus_typ="Influenza A",
            region="DE",
        )

        alignment = align_wave_points(
            survstat_points=survstat_points,
            amelag_points=amelag_points,
            survstat_features=survstat_features,
            amelag_features=amelag_features,
        )

        self.assertEqual(alignment["lead_lag_days"], -7)
        self.assertGreaterEqual(alignment["correlation"], 0.99)
        self.assertEqual(alignment["status"], "amelag_leads_survstat")

    def test_evidence_weights_make_good_amelag_primary_for_early_warning(self) -> None:
        survstat_features = {
            "source": "survstat",
            "phase": "decline",
            "status": "ok",
            "confidence": 0.72,
            "data_points": 20,
        }
        amelag_features = {
            "source": "amelag",
            "phase": "post_wave",
            "status": "ok",
            "confidence": 0.80,
            "data_points": 20,
        }
        alignment = {
            "status": "amelag_leads_survstat",
            "lead_lag_days": -7,
            "alignment_score": 0.84,
        }
        amelag_points = [
            {
                "date": date(2026, 4, 20),
                "available_time": date(2026, 4, 21),
                "value": 12.0,
                "vorhersage": 12.0,
                "viruslast_normalisiert": 10.0,
                "viruslast": 9.0,
                "obere_schranke": 14.0,
                "untere_schranke": 10.0,
                "n_standorte": 45,
                "anteil_bev": 0.28,
                "unter_bg": False,
            }
        ]

        evidence = build_wave_evidence(
            survstat_features=survstat_features,
            amelag_features=amelag_features,
            alignment=alignment,
            amelag_points=amelag_points,
            reference_date=date(2026, 4, 30),
        )

        early_warning = evidence["weight_profiles"]["early_warning"]
        self.assertEqual(evidence["mode"], "diagnostic_only")
        self.assertEqual(evidence["source_roles"]["amelag"], "early_warning_trend_signal")
        self.assertEqual(evidence["source_availability"]["syndromic"], "planned_unavailable")
        self.assertEqual(evidence["early_warning_signal"]["primary_source"], "amelag")
        self.assertEqual(evidence["early_warning_signal"]["confidence_method"], "heuristic_v1")
        self.assertGreater(early_warning["effective_weights"]["amelag"], early_warning["effective_weights"]["survstat"])
        self.assertFalse(evidence["budget_impact"]["can_change_budget"])
        self.assertEqual(evidence["amelag_quality"]["signal_basis"], "vorhersage")
        self.assertFalse(evidence["amelag_quality"]["backtest_safe"])

    def test_evidence_reduces_poor_amelag_quality_without_treating_missing_sources_as_burden(self) -> None:
        survstat_features = {
            "source": "survstat",
            "phase": "early_growth",
            "status": "ok",
            "confidence": 0.75,
            "data_points": 20,
        }
        amelag_features = {
            "source": "amelag",
            "phase": "early_growth",
            "status": "ok",
            "confidence": 0.80,
            "data_points": 20,
        }
        alignment = {
            "status": "synchronized",
            "lead_lag_days": 0,
            "alignment_score": 0.60,
        }
        good_amelag_points = [
            {
                "date": date(2026, 4, 20),
                "available_time": date(2026, 4, 21),
                "value": 12.0,
                "vorhersage": 12.0,
                "obere_schranke": 14.0,
                "untere_schranke": 10.0,
                "n_standorte": 45,
                "anteil_bev": 0.28,
                "unter_bg": False,
            }
        ]
        poor_amelag_points = [
            {
                "date": date(2026, 1, 1),
                "available_time": date(2026, 1, 2),
                "value": 0.2,
                "viruslast": 0.2,
                "obere_schranke": 5.0,
                "untere_schranke": 0.0,
                "n_standorte": 2,
                "anteil_bev": 0.01,
                "unter_bg": True,
            }
        ]

        good = build_wave_evidence(
            survstat_features=survstat_features,
            amelag_features=amelag_features,
            alignment=alignment,
            amelag_points=good_amelag_points,
            reference_date=date(2026, 4, 30),
        )
        poor = build_wave_evidence(
            survstat_features=survstat_features,
            amelag_features=amelag_features,
            alignment=alignment,
            amelag_points=poor_amelag_points,
            reference_date=date(2026, 4, 30),
        )

        self.assertLess(
            poor["weight_profiles"]["early_warning"]["effective_weights"]["amelag"],
            good["weight_profiles"]["early_warning"]["effective_weights"]["amelag"],
        )
        self.assertLess(
            poor["early_warning_signal"]["confidence"],
            good["early_warning_signal"]["confidence"],
        )
        self.assertIn("amelag_stale", poor["amelag_quality"]["quality_flags"])
        self.assertIn("amelag_low_population_coverage", poor["amelag_quality"]["quality_flags"])
        self.assertEqual(poor["source_availability"]["severity"], "planned_unavailable")
        self.assertIn("syndromic", poor["weight_profiles"]["early_warning"]["missing_sources"])

    def test_amelag_signal_basis_falls_back_in_order(self) -> None:
        self.assertEqual(
            select_amelag_signal_basis({"vorhersage": 3.0, "viruslast_normalisiert": 2.0, "viruslast": 1.0})[1],
            "vorhersage",
        )
        self.assertEqual(
            select_amelag_signal_basis({"vorhersage": None, "viruslast_normalisiert": 2.0, "viruslast": 1.0})[1],
            "viruslast_normalisiert",
        )
        self.assertEqual(
            select_amelag_signal_basis({"vorhersage": None, "viruslast_normalisiert": None, "viruslast": 1.0})[1],
            "viruslast",
        )


if __name__ == "__main__":
    unittest.main()
