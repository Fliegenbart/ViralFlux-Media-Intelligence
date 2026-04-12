import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.media.outcome_ingestion_service import OutcomeIngestionService


class OutcomeIngestionServiceTests(unittest.TestCase):
    def test_ingest_outcomes_rejects_blank_brand(self) -> None:
        with patch("app.services.media.outcome_ingestion_service.MediaV2Service") as media_cls, patch(
            "app.services.media.outcome_ingestion_service.TruthLayerService"
        ):
            service = OutcomeIngestionService(db=object())
            service._existing_batch = lambda **_: SimpleNamespace(rows_imported=0, batch_id="batch-1")
            media_cls.return_value.get_outcome_import_batch_detail.return_value = {
                "batch": {"coverage_after_import": {}},
                "issues": [],
            }

            with self.assertRaises(ValueError):
                service.ingest_outcomes(
                    brand="   ",
                    source_system="sap",
                    external_batch_id="batch-1",
                    observations=[],
                )


if __name__ == "__main__":
    unittest.main()
