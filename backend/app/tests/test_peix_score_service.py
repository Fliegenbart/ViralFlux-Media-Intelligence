import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, MLForecast
from app.services.media.peix_score_service import PeixEpiScoreService


class PeixScoreServiceTests(unittest.TestCase):
    def test_search_signal_handles_decimal_averages(self) -> None:
        config_query = MagicMock()
        config_query.filter_by.return_value.first.return_value = None

        recent_query = MagicMock()
        recent_query.filter.return_value.scalar.return_value = Decimal("130.0")

        previous_query = MagicMock()
        previous_query.filter.return_value.scalar.return_value = Decimal("100.0")

        db = MagicMock()
        db.query.side_effect = [config_query, recent_query, previous_query]

        score = PeixEpiScoreService(db)._search_signal()

        self.assertIsInstance(score, float)
        self.assertAlmostEqual(score, 0.8)

    def test_forecast_signal_reads_only_national_default_horizon(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()
        try:
            now = datetime.utcnow().replace(microsecond=0)
            db.add_all([
                MLForecast(
                    forecast_date=now + timedelta(days=1),
                    virus_typ="Influenza A",
                    region="DE",
                    horizon_days=7,
                    predicted_value=100.0,
                    created_at=now,
                ),
                MLForecast(
                    forecast_date=now + timedelta(days=2),
                    virus_typ="Influenza A",
                    region="DE",
                    horizon_days=7,
                    predicted_value=140.0,
                    created_at=now,
                ),
                MLForecast(
                    forecast_date=now + timedelta(days=1),
                    virus_typ="Influenza A",
                    region="BY",
                    horizon_days=7,
                    predicted_value=20.0,
                    created_at=now + timedelta(minutes=2),
                ),
                MLForecast(
                    forecast_date=now + timedelta(days=2),
                    virus_typ="Influenza A",
                    region="BY",
                    horizon_days=7,
                    predicted_value=10.0,
                    created_at=now + timedelta(minutes=2),
                ),
                MLForecast(
                    forecast_date=now + timedelta(days=1),
                    virus_typ="Influenza A",
                    region="DE",
                    horizon_days=5,
                    predicted_value=20.0,
                    created_at=now + timedelta(minutes=3),
                ),
                MLForecast(
                    forecast_date=now + timedelta(days=2),
                    virus_typ="Influenza A",
                    region="DE",
                    horizon_days=5,
                    predicted_value=10.0,
                    created_at=now + timedelta(minutes=3),
                ),
            ])
            db.commit()

            score = PeixEpiScoreService(db)._forecast_signal("Influenza A")

            self.assertGreater(score, 0.5)
        finally:
            db.close()
            Base.metadata.drop_all(bind=engine)
            engine.dispose()
