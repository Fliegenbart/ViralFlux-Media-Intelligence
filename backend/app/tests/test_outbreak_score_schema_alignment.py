import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db.schema_contracts import (
    OutbreakScoreSchemaMismatchError,
    ensure_outbreak_score_schema_aligned,
    get_required_schema_contract_gaps,
)
from app.models.database import Base


class OutbreakScoreSchemaAlignmentTests(unittest.TestCase):
    def test_detects_legacy_outbreak_score_columns_after_semantics_rename(self) -> None:
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
                        CREATE TABLE outbreak_scores (
                            id INTEGER PRIMARY KEY,
                            datum DATETIME NOT NULL,
                            virus_typ VARCHAR NOT NULL,
                            final_risk_score FLOAT NOT NULL,
                            risk_level VARCHAR,
                            leading_indicator VARCHAR,
                            confidence_level VARCHAR,
                            confidence_numeric FLOAT,
                            component_scores JSON,
                            data_source_mode VARCHAR,
                            phase VARCHAR,
                            created_at DATETIME
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX idx_outbreak_date_virus ON outbreak_scores (datum, virus_typ)"
                    )
                )

            gaps = get_required_schema_contract_gaps(engine)

            self.assertIn("outbreak_scores.decision_priority_index", gaps["missing_columns"])
            self.assertIn("outbreak_scores.signal_level", gaps["missing_columns"])
            self.assertIn("outbreak_scores.signal_source", gaps["missing_columns"])
            self.assertIn("outbreak_scores.reliability_label", gaps["missing_columns"])
            self.assertIn("outbreak_scores.reliability_score", gaps["missing_columns"])
            with self.assertRaises(OutbreakScoreSchemaMismatchError):
                ensure_outbreak_score_schema_aligned(engine)
        finally:
            engine.dispose()

    def test_accepts_current_outbreak_score_schema_from_repo_metadata(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            Base.metadata.create_all(bind=engine)

            gaps = get_required_schema_contract_gaps(engine)

            self.assertNotIn("outbreak_scores", gaps["missing_tables"])
            self.assertNotIn("outbreak_scores.decision_priority_index", gaps["missing_columns"])
            self.assertNotIn("outbreak_scores.signal_level", gaps["missing_columns"])
            self.assertNotIn("outbreak_scores.signal_source", gaps["missing_columns"])
            self.assertNotIn("outbreak_scores.reliability_label", gaps["missing_columns"])
            self.assertNotIn("outbreak_scores.reliability_score", gaps["missing_columns"])
            ensure_outbreak_score_schema_aligned(engine)
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
