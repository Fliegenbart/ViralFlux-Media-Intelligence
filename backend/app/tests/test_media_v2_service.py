import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.services.media.v2_service import MediaV2Service


class MediaV2ServiceTruthCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MediaV2Service(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_import_outcomes_from_records_updates_truth_coverage(self) -> None:
        result = self.service.import_outcomes(
            source_label="manual_csv",
            brand="gelo",
            records=[
                {
                    "week_start": "2026-01-05T00:00:00",
                    "product": "GeloProsed",
                    "region_code": "SH",
                    "media_spend_eur": 10000,
                    "sales_units": 120,
                },
                {
                    "week_start": "2026-01-12T00:00:00",
                    "product": "GeloRevoice",
                    "region_code": "HH",
                    "media_spend_eur": 9000,
                    "order_count": 44,
                },
            ],
        )

        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["coverage"]["coverage_weeks"], 2)
        self.assertEqual(result["coverage"]["regions_covered"], 2)
        self.assertEqual(result["coverage"]["products_covered"], 2)
        self.assertIn("Media Spend", result["coverage"]["outcome_fields_present"])
        self.assertEqual(result["coverage"]["trust_readiness"], "erste_signale")

    def test_import_outcomes_supports_inline_csv_payload(self) -> None:
        csv_payload = (
            "week_start,product,region_code,media_spend_eur,qualified_visits\n"
            "2026-02-02T00:00:00,GeloProsed,SH,12000,320\n"
            "2026-02-09T00:00:00,GeloProsed,HH,14000,410\n"
        )

        result = self.service.import_outcomes(
            source_label="csv_upload",
            brand="gelo",
            csv_payload=csv_payload,
        )

        self.assertEqual(result["imported"], 2)
        coverage = self.service.get_truth_coverage(brand="gelo")
        self.assertEqual(coverage["coverage_weeks"], 2)
        self.assertIn("Qualifizierte Besuche", coverage["outcome_fields_present"])
        self.assertIn("csv_upload", coverage["source_labels"])


if __name__ == "__main__":
    unittest.main()
