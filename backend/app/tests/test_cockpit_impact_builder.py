"""Tests for app.services.media.cockpit.impact_builder.

The impact tab MUST NOT fabricate numbers. These tests verify:
  - liveRanking is derived strictly from the snapshot's regions,
  - truthHistory pulls BL-level SURVSTAT rows and excludes the "Gesamt" bucket,
  - outcomePipeline reports real counts and flips connected=True only when data is there,
  - notes are populated with clear "data pending" messages when inputs are empty.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    Base,
    MediaOutcomeImportBatch,
    MediaOutcomeRecord,
    OutcomeObservation,
    SurvstatWeeklyData,
)
from app.services.media.cockpit import impact_builder


class ImpactBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # ---------- liveRanking ----------

    def test_live_ranking_from_snapshot_sorts_by_pRising_desc(self) -> None:
        snapshot = {
            "regions": [
                {"code": "NW", "name": "Nordrhein-Westfalen", "pRising": 0.28, "delta7d": -0.08, "decisionLabel": "Watch"},
                {"code": "BY", "name": "Bayern", "pRising": 0.78, "delta7d": 0.26, "decisionLabel": "Activate"},
                {"code": "BE", "name": "Berlin", "pRising": 0.82, "delta7d": 0.34, "decisionLabel": "Activate"},
            ]
        }
        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=snapshot
        )
        self.assertEqual([r["code"] for r in payload["liveRanking"]], ["BE", "BY", "NW"])
        self.assertEqual(payload["liveRanking"][0]["decisionLabel"], "Activate")

    def test_live_ranking_skips_regions_without_signal(self) -> None:
        snapshot = {
            "regions": [
                {"code": "NW", "name": "NRW", "pRising": None, "delta7d": None},
                {"code": "BY", "name": "Bayern", "pRising": 0.78, "delta7d": 0.26},
            ]
        }
        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=snapshot
        )
        self.assertEqual([r["code"] for r in payload["liveRanking"]], ["BY"])

    def test_live_ranking_is_empty_when_snapshot_missing(self) -> None:
        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=None
        )
        self.assertEqual(payload["liveRanking"], [])
        self.assertTrue(any("Kein Live-Ranking" in n for n in payload["notes"]))

    # ---------- truthHistory ----------

    def test_truth_history_returns_bl_rows_excluding_gesamt(self) -> None:
        base = datetime(2026, 2, 2)
        rows = [
            ("BY", "Bayern", base, 35.1),
            ("NW", "Nordrhein-Westfalen", base, 20.2),
            ("BE", "Berlin", base, 47.8),
            ("Gesamt", "Gesamt", base, 28.0),  # MUST be excluded
        ]
        for _, name, week_start, incidence in rows:
            self.db.add(
                SurvstatWeeklyData(
                    week_label=f"W{week_start.isocalendar().week:02d}/{week_start.year}",
                    week_start=week_start,
                    year=week_start.year,
                    week=week_start.isocalendar().week,
                    bundesland=name,
                    disease="Influenza, saisonal",
                    incidence=incidence,
                )
            )
        self.db.commit()

        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=None, weeks_back=4
        )
        tl = payload["truthHistory"]["timeline"]
        self.assertEqual(len(tl), 1)
        codes = [r["code"] for r in tl[0]["regions"]]
        self.assertNotIn("Gesamt", codes)
        self.assertEqual(tl[0]["top3"], ["BE", "BY", "NW"])

    def test_truth_history_is_empty_when_no_survstat_bl_rows(self) -> None:
        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=None
        )
        self.assertEqual(payload["truthHistory"]["timeline"], [])
        self.assertTrue(any("SURVSTAT" in n for n in payload["notes"]))

    # ---------- outcomePipeline ----------

    def test_outcome_pipeline_reports_zero_when_tables_empty(self) -> None:
        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=None
        )
        op = payload["outcomePipeline"]
        self.assertFalse(op["connected"])
        self.assertEqual(op["mediaOutcomeRecords"], 0)
        self.assertEqual(op["importBatches"], 0)
        self.assertEqual(op["outcomeObservations"], 0)
        self.assertEqual(op["holdoutGroupsDefined"], 0)
        self.assertIsNone(op["lastImportBatchAt"])
        self.assertIn("Noch keine Outcome-Daten", op["note"])

    def test_outcome_pipeline_flips_connected_when_records_present(self) -> None:
        self.db.add(
            MediaOutcomeImportBatch(
                batch_id="batch-1",
                brand="gelo",
                source_label="gelo_csv",
                file_name="gelo_2026_w06.csv",
                rows_total=5,
                rows_valid=5,
                rows_imported=5,
                created_at=datetime.utcnow(),
            )
        )
        self.db.add(
            MediaOutcomeRecord(
                week_start=datetime.utcnow() - timedelta(days=7),
                brand="GELO",
                product="GeloMyrtol",
                region_code="BY",
                media_spend_eur=12000.0,
                sales_units=2840,
                revenue_eur=24500.0,
                source_label="gelo_csv",
                import_batch_id="batch-1",
                updated_at=datetime.utcnow(),
            )
        )
        self.db.add(
            OutcomeObservation(
                brand="GELO",
                product="GeloMyrtol",
                region_code="BY",
                window_start=datetime.utcnow() - timedelta(days=7),
                window_end=datetime.utcnow(),
                metric_name="sales_units",
                metric_value=2840.0,
                metric_unit="units",
                source_label="gelo_csv",
                holdout_group="treatment",
            )
        )
        self.db.commit()

        payload = impact_builder.build_impact_payload(
            self.db, virus_typ="Influenza A", snapshot=None
        )
        op = payload["outcomePipeline"]
        self.assertTrue(op["connected"])
        self.assertEqual(op["mediaOutcomeRecords"], 1)
        self.assertEqual(op["importBatches"], 1)
        self.assertEqual(op["outcomeObservations"], 1)
        self.assertEqual(op["holdoutGroupsDefined"], 1)
        self.assertIsNotNone(op["lastImportBatchAt"])
        self.assertIn("Feedback-Loop ist aktiv", op["note"])


if __name__ == "__main__":
    unittest.main()
