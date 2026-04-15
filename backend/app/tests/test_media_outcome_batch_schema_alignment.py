import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db.schema_contracts import get_required_schema_contract_gaps
from app.models.database import Base


class MediaOutcomeBatchSchemaAlignmentTests(unittest.TestCase):
    def test_detects_missing_ingestion_columns_on_legacy_batch_schema(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE media_outcome_import_batches (
                            id INTEGER PRIMARY KEY,
                            batch_id VARCHAR NOT NULL,
                            brand VARCHAR NOT NULL,
                            source_label VARCHAR NOT NULL,
                            status VARCHAR NOT NULL,
                            uploaded_at DATETIME,
                            file_name VARCHAR
                        )
                        """
                    )
                )

            gaps = get_required_schema_contract_gaps(engine)

            self.assertIn(
                "media_outcome_import_batches.source_system",
                gaps["missing_columns"],
            )
            self.assertIn(
                "media_outcome_import_batches.external_batch_id",
                gaps["missing_columns"],
            )
            self.assertIn(
                "media_outcome_import_batches.ingestion_mode",
                gaps["missing_columns"],
            )
        finally:
            engine.dispose()

    def test_accepts_current_batch_schema_from_repo_metadata(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            Base.metadata.create_all(bind=engine)

            gaps = get_required_schema_contract_gaps(engine)

            self.assertNotIn("media_outcome_import_batches", gaps["missing_tables"])
            self.assertNotIn(
                "media_outcome_import_batches.source_system",
                gaps["missing_columns"],
            )
            self.assertNotIn(
                "media_outcome_import_batches.external_batch_id",
                gaps["missing_columns"],
            )
            self.assertNotIn(
                "media_outcome_import_batches.ingestion_mode",
                gaps["missing_columns"],
            )
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
