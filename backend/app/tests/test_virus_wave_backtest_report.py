from datetime import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    Base,
    VirusWaveBacktestEvent,
    VirusWaveBacktestResult,
    VirusWaveBacktestRun,
)
from app.services.media.cockpit.virus_wave_backtest_report import (
    build_virus_wave_backtest_evaluation_report,
    render_virus_wave_backtest_markdown,
)


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            VirusWaveBacktestRun.__table__,
            VirusWaveBacktestResult.__table__,
            VirusWaveBacktestEvent.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _add_run(
    db,
    *,
    pathogen: str,
    canonical_pathogen: str | None = None,
    pathogen_variant: str | None = None,
    season: str = "2025_2026",
    evidence_onset_gain: float = 7.0,
    evidence_peak_gain: float = 5.0,
    evidence_phase_accuracy: float = 0.95,
    evidence_false_warning: float = 0.0,
    evidence_missed_wave: float = 0.0,
    evidence_status: str = "ok",
    method_flags: dict | None = None,
    scope_mode: str | None = None,
):
    run = VirusWaveBacktestRun(
        run_key=f"test:{pathogen}:{season}",
        algorithm_version="virus-wave-evidence-runtime-v1.1",
        backtest_version="virus-wave-backtest-v1.3",
        mode="historical_cutoff",
        status="success",
        started_at=datetime(2026, 4, 30, 9, 0),
        finished_at=datetime(2026, 4, 30, 9, 1),
        pathogens=[pathogen],
        regions=["DE"],
        seasons=[season],
        baseline_models=["survstat_only"],
        candidate_models=["evidence_v1_1_quality_weighted"],
        parameters_json={"backtest_safe": True, "method_flags": method_flags or {}, "scope_mode": scope_mode},
        summary_json={"budget_impact": {"can_change_budget": False}},
    )
    db.add(run)
    db.flush()
    canonical = canonical_pathogen or pathogen
    common = {
        "run_id": run.id,
        "pathogen": pathogen,
        "canonical_pathogen": canonical,
        "pathogen_variant": pathogen_variant,
        "region_code": "DE",
        "season": season,
    }
    db.add(
        VirusWaveBacktestResult(
            **common,
            model_name="survstat_only",
            status="ok",
            onset_detection_gain_days=0.0,
            peak_detection_gain_days=0.0,
            phase_accuracy=1.0,
            false_early_warning_rate=0.0,
            missed_wave_rate=0.0,
            false_post_peak_rate=0.0,
            summary_json={"budget_can_change": False},
        )
    )
    db.add(
        VirusWaveBacktestResult(
            **common,
            model_name="evidence_v1_1_quality_weighted",
            status=evidence_status,
            onset_detection_gain_days=evidence_onset_gain,
            peak_detection_gain_days=evidence_peak_gain,
            phase_accuracy=evidence_phase_accuracy,
            false_early_warning_rate=evidence_false_warning,
            missed_wave_rate=evidence_missed_wave,
            false_post_peak_rate=0.0,
            summary_json={"budget_can_change": False},
        )
    )
    db.commit()


class VirusWaveBacktestReportTests(unittest.TestCase):
    def test_report_classifies_go_review_and_no_go_without_budget_impact(self) -> None:
        db = _db_session()
        try:
            _add_run(db, pathogen="Influenza A", evidence_onset_gain=10.0, evidence_phase_accuracy=0.98)
            _add_run(
                db,
                pathogen="Influenza B",
                evidence_onset_gain=-21.0,
                evidence_phase_accuracy=0.72,
                evidence_false_warning=0.4,
            )
            _add_run(
                db,
                pathogen="RSV A",
                canonical_pathogen="RSV",
                pathogen_variant="RSV A",
                evidence_onset_gain=0.0,
                evidence_phase_accuracy=1.0,
            )

            report = build_virus_wave_backtest_evaluation_report(db, mode="historical_cutoff")
            by_pathogen = {row["pathogen"]: row for row in report["pathogen_reports"]}

            self.assertEqual(report["mode"], "historical_cutoff")
            self.assertTrue(report["backtest_safe"])
            self.assertFalse(report["budget_impact"]["can_change_budget"])
            self.assertEqual(by_pathogen["Influenza A"]["recommendation"], "go_for_simulation")
            self.assertEqual(by_pathogen["Influenza B"]["recommendation"], "no_go")
            self.assertEqual(by_pathogen["RSV A"]["recommendation"], "review")
            self.assertIn("rsv_variant_scope_requires_review", by_pathogen["RSV A"]["warnings"])
            self.assertEqual(report["summary"]["go_count"], 1)
            self.assertEqual(report["summary"]["no_go_count"], 1)
            self.assertEqual(report["summary"]["review_count"], 1)
        finally:
            db.close()

    def test_markdown_report_is_human_readable_and_states_diagnostic_only(self) -> None:
        db = _db_session()
        try:
            _add_run(db, pathogen="SARS-CoV-2", evidence_onset_gain=5.0, evidence_peak_gain=30.0)
            report = build_virus_wave_backtest_evaluation_report(db, mode="historical_cutoff")

            markdown = render_virus_wave_backtest_markdown(report)

            self.assertIn("Virus Wave Backtest Evaluation v1.7", markdown)
            self.assertIn("diagnostic_only", markdown)
            self.assertIn("SARS-CoV-2", markdown)
            self.assertIn("budget_can_change: false", markdown)
        finally:
            db.close()

    def test_report_handles_missing_backtest_data_explicitly(self) -> None:
        db = _db_session()
        try:
            report = build_virus_wave_backtest_evaluation_report(db, mode="historical_cutoff")

            self.assertEqual(report["status"], "no_data")
            self.assertEqual(report["pathogen_reports"], [])
            self.assertFalse(report["budget_impact"]["can_change_budget"])
        finally:
            db.close()

    def test_report_keeps_latest_runs_per_pathogen_region_and_season(self) -> None:
        db = _db_session()
        try:
            _add_run(db, pathogen="SARS-CoV-2", season="2023_2024", evidence_peak_gain=20.0)
            _add_run(db, pathogen="SARS-CoV-2", season="2025_2026", evidence_peak_gain=-5.0)

            report = build_virus_wave_backtest_evaluation_report(db, mode="historical_cutoff")
            seasons = sorted(row["season"] for row in report["pathogen_reports"])

            self.assertEqual(seasons, ["2023_2024", "2025_2026"])

        finally:
            db.close()

    def test_report_surfaces_backtest_method_flags_as_warnings(self) -> None:
        db = _db_session()
        try:
            _add_run(
                db,
                pathogen="Influenza B",
                method_flags={
                    "warnings": ["subtype_specific_amelag_vs_combined_clinical_anchor"],
                    "requires_anchor_review": True,
                },
            )

            report = build_virus_wave_backtest_evaluation_report(db, mode="historical_cutoff")
            row = report["pathogen_reports"][0]

            self.assertIn("subtype_specific_amelag_vs_combined_clinical_anchor", row["warnings"])
            self.assertEqual(row["recommendation"], "review")
            self.assertIn("clinical_anchor_must_be_confirmed_before_promotion", row["recommendation_reasons"])
        finally:
            db.close()

    def test_report_can_filter_to_canonical_scope_mode(self) -> None:
        db = _db_session()
        try:
            _add_run(db, pathogen="Influenza A", scope_mode="legacy")
            _add_run(db, pathogen="Influenza A+B", scope_mode="canonical")
            _add_run(db, pathogen="RSV", canonical_pathogen="RSV", scope_mode="canonical")

            report = build_virus_wave_backtest_evaluation_report(
                db,
                mode="historical_cutoff",
                scope_mode="canonical",
            )
            pathogens = sorted(row["pathogen"] for row in report["pathogen_reports"])

            self.assertEqual(pathogens, ["Influenza A+B", "RSV"])
            self.assertEqual(report["scope_mode"], "canonical")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
