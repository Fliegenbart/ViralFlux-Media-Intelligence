import unittest
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, KreisEinwohner, SurvstatKreisData
from app.services.data_ingest.survstat_api_service import SurvstatApiService
from app.services.ml.regional_features import RegionalFeatureBuilder


class SurvstatPopulationSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = SurvstatApiService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_extract_destatis_modern_records_aggregates_municipalities_to_counties(self) -> None:
        frame = [
            [None] * 10 for _ in range(6)
        ]
        frame.extend([
            [40, 41, "01", "0", "01", None, None, "Flensburg, Stadt", None, None],
            [60, 61, "01", "0", "01", "0000", "000", "Flensburg, Stadt", None, 96326],
            [40, 43, "01", "0", "51", None, None, "Dithmarschen", None, None],
            [60, 63, "01", "0", "51", "0011", "011", "Brunsbüttel, Stadt", None, 12381],
            [60, 64, "01", "0", "51", "0044", "044", "Heide, Stadt", None, 21844],
            [60, 64, "01", "0", "51", "0100", "100", "Musterort", None, 1000],
        ])

        records = self.service._extract_destatis_modern_records(pd.DataFrame(frame))

        self.assertEqual(len(records), 2)
        by_ags = {row["ags"]: row for row in records}
        self.assertEqual(by_ags["01001"]["einwohner"], 96326)
        self.assertEqual(by_ags["01051"]["einwohner"], 35225)
        self.assertEqual(by_ags["01051"]["bundesland"], "Schleswig-Holstein")

    def test_extract_destatis_legacy_records_reads_direct_county_rows(self) -> None:
        frame = [
            [None] * 14 for _ in range(8)
        ]
        frame.extend([
            ["01", None, 40, 41, None, "01001", None, "Flensburg, Stadt", None, None, None, None, None, 91113],
            ["01", None, 40, 43, None, "01051", None, "Dithmarschen", None, None, None, None, None, 133969],
            ["01", None, 60, 61, None, "010010000000", "01001000", "Flensburg, Stadt", None, None, None, None, None, 91113],
        ])

        records = self.service._extract_destatis_legacy_records(pd.DataFrame(frame))

        self.assertEqual(len(records), 2)
        by_ags = {row["ags"]: row for row in records}
        self.assertEqual(by_ags["01001"]["einwohner"], 91113)
        self.assertEqual(by_ags["01051"]["kreis_name"], "Dithmarschen")

    def test_apply_kreis_population_records_updates_existing_rows_and_inserts_berlin_total(self) -> None:
        self.db.add_all([
            KreisEinwohner(
                kreis_name="LK Ahrweiler",
                ags="07131",
                bundesland="Rheinland-Pfalz",
                einwohner=0,
            ),
            KreisEinwohner(
                kreis_name="SK Berlin Mitte",
                ags="11001",
                bundesland="Berlin",
                einwohner=0,
            ),
        ])
        self.db.commit()

        result = self.service._apply_kreis_population_records(
            records=[
                {
                    "ags": "07131",
                    "kreis_name": "Ahrweiler",
                    "bundesland": "Rheinland-Pfalz",
                    "einwohner": 132170,
                },
                {
                    "ags": "11000",
                    "kreis_name": "Berlin, Stadt",
                    "bundesland": "Berlin",
                    "einwohner": 3677472,
                },
            ],
            source_meta={"label": "test", "url": "memory://destatis"},
        )

        self.assertEqual(result["updated_existing"], 1)
        self.assertEqual(result["inserted_missing"], 1)
        self.assertEqual(
            self.db.query(KreisEinwohner).filter(KreisEinwohner.ags == "07131").one().einwohner,
            132170,
        )
        self.assertEqual(
            self.db.query(KreisEinwohner).filter(KreisEinwohner.ags == "11000").one().einwohner,
            3677472,
        )


class RegionalKreisTruthAggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_load_truth_from_kreis_uses_state_population_even_for_berlin_bezirke(self) -> None:
        self.db.add_all([
            KreisEinwohner(
                kreis_name="SK Berlin Mitte",
                ags="11001",
                bundesland="Berlin",
                einwohner=0,
            ),
            KreisEinwohner(
                kreis_name="SK Berlin Pankow",
                ags="11003",
                bundesland="Berlin",
                einwohner=0,
            ),
            KreisEinwohner(
                kreis_name="Berlin, Stadt",
                ags="11000",
                bundesland="Berlin",
                einwohner=3677472,
            ),
            KreisEinwohner(
                kreis_name="LK Ahrweiler",
                ags="07131",
                bundesland="Rheinland-Pfalz",
                einwohner=132170,
            ),
            SurvstatKreisData(
                year=2026,
                week=10,
                week_label="2026_10",
                kreis="SK Berlin Mitte",
                disease="influenza, saisonal",
                fallzahl=100,
                inzidenz=None,
                created_at=datetime.utcnow(),
            ),
            SurvstatKreisData(
                year=2026,
                week=10,
                week_label="2026_10",
                kreis="SK Berlin Pankow",
                disease="influenza, saisonal",
                fallzahl=200,
                inzidenz=None,
                created_at=datetime.utcnow(),
            ),
            SurvstatKreisData(
                year=2026,
                week=10,
                week_label="2026_10",
                kreis="LK Ahrweiler",
                disease="influenza, saisonal",
                fallzahl=132,
                inzidenz=None,
                created_at=datetime.utcnow(),
            ),
        ])
        self.db.commit()

        builder = RegionalFeatureBuilder(self.db)
        truth = builder._load_truth_from_kreis("Influenza A", pd.Timestamp("2026-01-01"))

        self.assertEqual(sorted(truth["bundesland"].tolist()), ["BE", "RP"])
        berlin = truth.loc[truth["bundesland"] == "BE"].iloc[0]
        self.assertAlmostEqual(
            berlin["incidence"],
            (300.0 / 3677472.0) * 100_000.0,
            places=6,
        )
        rheinland_pfalz = truth.loc[truth["bundesland"] == "RP"].iloc[0]
        self.assertAlmostEqual(
            rheinland_pfalz["incidence"],
            (132.0 / 132170.0) * 100_000.0,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
