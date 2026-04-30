from datetime import date, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    Base,
    VirusWaveBacktestEvent,
    VirusWaveBacktestResult,
    VirusWaveBacktestRun,
)
from app.services.media.cockpit.virus_wave_backtest import (
    DEFAULT_SCOPES,
    canonicalize_pathogen_scope,
    candidate_epi_seasons_for_backtest,
    filter_points_to_epi_season,
    persist_virus_wave_backtest_report,
    prepare_amelag_points_for_backtest,
    run_wave_backtest_from_points,
)


def _weekly_points(start: date, values: list[float], *, field: str = "value") -> list[dict]:
    return [
        {
            "date": start + timedelta(days=7 * idx),
            field: value,
            "value": value,
        }
        for idx, value in enumerate(values)
    ]


class VirusWaveBacktestTests(unittest.TestCase):
    def test_pathogen_normalization_groups_rsv_variants_without_losing_variant(self) -> None:
        self.assertEqual(
            canonicalize_pathogen_scope("RSV A"),
            {"pathogen": "RSV", "pathogen_variant": "RSV A"},
        )
        self.assertEqual(
            canonicalize_pathogen_scope("Respiratory syncytial virus"),
            {"pathogen": "RSV", "pathogen_variant": None},
        )
        self.assertEqual(
            canonicalize_pathogen_scope("Influenza A"),
            {"pathogen": "Influenza A", "pathogen_variant": None},
        )
        self.assertEqual(
            canonicalize_pathogen_scope("Influenza A+B"),
            {"pathogen": "Influenza A+B", "pathogen_variant": None},
        )
        self.assertEqual(
            canonicalize_pathogen_scope("RSV A+B"),
            {"pathogen": "RSV", "pathogen_variant": None},
        )

    def test_default_scopes_use_canonical_comparison_pairs(self) -> None:
        self.assertEqual(DEFAULT_SCOPES, ["Influenza A+B", "RSV", "SARS-CoV-2"])

    def test_historical_cutoff_amelag_signal_avoids_vorhersage_future_leakage(self) -> None:
        points = [
            {
                "date": date(2026, 1, 1),
                "vorhersage": 100.0,
                "viruslast_normalisiert": 8.0,
                "viruslast": 4.0,
            }
        ]

        safe = prepare_amelag_points_for_backtest(points, mode="historical_cutoff")
        retrospective = prepare_amelag_points_for_backtest(points, mode="retrospective_descriptive")

        self.assertEqual(safe[0]["value"], 8.0)
        self.assertEqual(safe[0]["signal_basis"], "viruslast_normalisiert")
        self.assertTrue(safe[0]["backtest_safe"])
        self.assertEqual(retrospective[0]["value"], 100.0)
        self.assertEqual(retrospective[0]["signal_basis"], "vorhersage")
        self.assertFalse(retrospective[0]["backtest_safe"])

    def test_quality_weighted_combo_detects_synthetic_amelag_lead_before_survstat_only(self) -> None:
        start = date(2026, 1, 5)
        survstat_points = _weekly_points(start, [1, 1, 1, 1, 1, 2, 5, 10, 15, 9, 4, 2])
        amelag_points = _weekly_points(start, [1, 1, 2, 5, 10, 15, 9, 4, 2, 1, 1, 1])

        report = run_wave_backtest_from_points(
            pathogen="Influenza A",
            region="DE",
            survstat_points=survstat_points,
            amelag_points=amelag_points,
            mode="historical_cutoff",
        )

        by_model = {row["model_name"]: row for row in report["results"]}
        self.assertEqual(report["mode"], "historical_cutoff")
        self.assertTrue(report["backtest_safe"])
        self.assertEqual(by_model["survstat_only"]["onset_detection_gain_days"], 0)
        self.assertGreater(by_model["evidence_v1_1_quality_weighted"]["onset_detection_gain_days"], 0)
        self.assertGreaterEqual(by_model["evidence_v1_1_quality_weighted"]["phase_accuracy"], 0.0)
        self.assertFalse(report["budget_impact"]["can_change_budget"])

    def test_missing_amelag_data_keeps_backtest_diagnostic_and_marks_candidate_as_missing(self) -> None:
        start = date(2026, 1, 5)
        survstat_points = _weekly_points(start, [1, 1, 1, 3, 7, 9, 5, 2])

        report = run_wave_backtest_from_points(
            pathogen="Influenza A",
            region="DE",
            survstat_points=survstat_points,
            amelag_points=[],
            mode="historical_cutoff",
        )

        by_model = {row["model_name"]: row for row in report["results"]}
        self.assertEqual(by_model["amelag_only"]["status"], "insufficient_data")
        self.assertEqual(by_model["evidence_v1_1_quality_weighted"]["status"], "insufficient_data")
        self.assertFalse(report["budget_impact"]["can_change_budget"])

    def test_persist_backtest_report_is_idempotent_and_keeps_budget_disabled(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            bind=engine,
            tables=[
                VirusWaveBacktestRun.__table__,
                VirusWaveBacktestResult.__table__,
                VirusWaveBacktestEvent.__table__,
            ],
        )
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            report = run_wave_backtest_from_points(
                pathogen="Influenza A",
                region="DE",
                survstat_points=_weekly_points(date(2026, 1, 5), [1, 1, 1, 3, 7, 9, 5, 2]),
                amelag_points=_weekly_points(date(2026, 1, 5), [1, 2, 5, 8, 7, 3, 1, 1]),
                mode="historical_cutoff",
            )

            first = persist_virus_wave_backtest_report(db, report)
            db.commit()
            second = persist_virus_wave_backtest_report(db, report)
            db.commit()

            self.assertEqual(first["run_key"], second["run_key"])
            self.assertEqual(db.query(VirusWaveBacktestRun).count(), 1)
            self.assertEqual(db.query(VirusWaveBacktestResult).count(), 4)
            self.assertGreaterEqual(db.query(VirusWaveBacktestEvent).count(), 1)
            stored = db.query(VirusWaveBacktestRun).one()
            self.assertFalse(stored.summary_json["budget_impact"]["can_change_budget"])
        finally:
            db.close()

    def test_peak_detection_is_constrained_to_after_onset_in_same_wave_window(self) -> None:
        start = date(2025, 7, 7)
        report = run_wave_backtest_from_points(
            pathogen="RSV A",
            region="DE",
            survstat_points=_weekly_points(start, [20, 2, 1, 1, 1, 3, 6, 12, 18, 11, 5, 2]),
            amelag_points=_weekly_points(start, [1, 1, 1, 2, 5, 9, 14, 21, 15, 8, 3, 1]),
            mode="historical_cutoff",
            season="2025_2026",
        )

        by_model = {row["model_name"]: row for row in report["results"]}
        baseline = by_model["survstat_only"]["summary_json"]

        self.assertEqual(report["season"], "2025_2026")
        self.assertLessEqual(baseline["baseline_onset_date"], baseline["baseline_peak_date"])
        self.assertFalse(report["method_flags"]["peak_before_onset_detected"])

    def test_epi_season_filter_prevents_cross_season_wave_mixing(self) -> None:
        points = _weekly_points(date(2023, 12, 4), [100, 80, 60, 40])
        points += _weekly_points(date(2025, 10, 6), [10, 20, 40, 80])

        filtered = filter_points_to_epi_season(points, "2025_2026")

        self.assertEqual([point["date"].isoformat() for point in filtered], [
            "2025-10-06",
            "2025-10-13",
            "2025-10-20",
            "2025-10-27",
        ])

    def test_candidate_epi_seasons_skip_partial_boundary_windows(self) -> None:
        partial = _weekly_points(date(2023, 5, 8), [1, 2, 3, 4, 5, 6, 7, 8])
        full = _weekly_points(date(2023, 10, 2), [1, 2, 3, 5, 8, 13, 8, 5, 3, 2, 1, 1])

        seasons = candidate_epi_seasons_for_backtest(
            [*partial, *full],
            [*partial, *full],
            min_points_per_source=8,
        )

        self.assertEqual(seasons, ["2023_2024"])

    def test_subtype_specific_amelag_with_combined_survstat_anchor_is_flagged(self) -> None:
        start = date(2026, 1, 5)

        report = run_wave_backtest_from_points(
            pathogen="Influenza B",
            region="DE",
            survstat_points=_weekly_points(start, [1, 1, 2, 5, 9, 5, 2, 1]),
            amelag_points=_weekly_points(start, [1, 2, 4, 8, 10, 7, 3, 1]),
            mode="historical_cutoff",
            clinical_anchor="combined_influenza_survstat",
        )

        self.assertEqual(report["clinical_anchor"], "combined_influenza_survstat")
        self.assertIn("subtype_specific_amelag_vs_combined_clinical_anchor", report["method_flags"]["warnings"])
        self.assertTrue(report["method_flags"]["requires_anchor_review"])

    def test_canonical_rsv_prefers_combined_rsv_amelag_scope_metadata(self) -> None:
        start = date(2026, 1, 5)

        report = run_wave_backtest_from_points(
            pathogen="RSV",
            region="DE",
            survstat_points=_weekly_points(start, [1, 1, 2, 5, 9, 5, 2, 1]),
            amelag_points=_weekly_points(start, [1, 2, 5, 9, 10, 6, 3, 1]),
            mode="historical_cutoff",
            amelag_scope="RSV A+B",
        )

        self.assertEqual(report["canonical_pathogen"], "RSV")
        self.assertEqual(report["pathogen_variant"], None)
        self.assertEqual(report["amelag_scope"], "RSV A+B")
        self.assertNotIn("rsv_variant_scope_requires_review", report["method_flags"]["warnings"])

    def test_canonical_influenza_ab_pair_does_not_require_anchor_review(self) -> None:
        start = date(2026, 1, 5)

        report = run_wave_backtest_from_points(
            pathogen="Influenza A+B",
            region="DE",
            survstat_points=_weekly_points(start, [1, 1, 2, 5, 9, 5, 2, 1]),
            amelag_points=_weekly_points(start, [1, 2, 4, 8, 10, 7, 3, 1]),
            mode="historical_cutoff",
        )

        self.assertEqual(report["clinical_anchor"], "combined_influenza_survstat")
        self.assertEqual(report["amelag_scope"], "Influenza A+B")
        self.assertNotIn("subtype_specific_amelag_vs_combined_clinical_anchor", report["method_flags"]["warnings"])
        self.assertFalse(report["method_flags"]["requires_anchor_review"])

    def test_canonical_rsv_pair_defaults_to_combined_amelag_scope(self) -> None:
        start = date(2026, 1, 5)

        report = run_wave_backtest_from_points(
            pathogen="RSV",
            region="DE",
            survstat_points=_weekly_points(start, [1, 1, 2, 5, 9, 5, 2, 1]),
            amelag_points=_weekly_points(start, [1, 2, 5, 9, 10, 6, 3, 1]),
            mode="historical_cutoff",
        )

        self.assertEqual(report["clinical_anchor"], "rsv_survstat")
        self.assertEqual(report["amelag_scope"], "RSV A+B")
        self.assertEqual(report["canonical_pathogen"], "RSV")
        self.assertEqual(report["pathogen_variant"], None)
        self.assertNotIn("rsv_variant_scope_requires_review", report["method_flags"]["warnings"])


if __name__ == "__main__":
    unittest.main()
