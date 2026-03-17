import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db.schema_contracts import (
    MLForecastSchemaMismatchError,
    ensure_ml_forecast_schema_aligned,
    get_ml_forecast_schema_gaps,
)
from app.models.database import Base


class MLForecastSchemaAlignmentTests(unittest.TestCase):
    def test_detects_missing_region_and_horizon_columns_on_legacy_schema(self) -> None:
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
                        CREATE TABLE ml_forecasts (
                            id INTEGER PRIMARY KEY,
                            created_at DATETIME,
                            forecast_date DATETIME NOT NULL,
                            virus_typ VARCHAR NOT NULL,
                            predicted_value FLOAT NOT NULL,
                            lower_bound FLOAT,
                            upper_bound FLOAT,
                            confidence FLOAT,
                            model_version VARCHAR,
                            features_used JSON,
                            trend_momentum_7d FLOAT,
                            outbreak_risk_score FLOAT
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX idx_forecast_date_virus ON ml_forecasts (forecast_date, virus_typ)"
                    )
                )

            gaps = get_ml_forecast_schema_gaps(engine)

            self.assertIn("ml_forecasts.region", gaps["missing_columns"])
            self.assertIn("ml_forecasts.horizon_days", gaps["missing_columns"])
            self.assertIn("ml_forecasts.idx_forecast_scope_date", gaps["missing_indexes"])
            with self.assertRaises(MLForecastSchemaMismatchError):
                ensure_ml_forecast_schema_aligned(engine)
        finally:
            engine.dispose()

    def test_accepts_current_repo_schema_contract(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            Base.metadata.create_all(bind=engine)

            ensure_ml_forecast_schema_aligned(engine)
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
