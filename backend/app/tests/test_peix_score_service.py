from app.core.time import utc_now
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, MLForecast
from app.services.media.peix_score_service import DEFAULT_WEIGHTS, PeixEpiScoreService


def _stub_peix_service(
    *,
    weights: dict[str, float] | None = None,
) -> PeixEpiScoreService:
    service = PeixEpiScoreService.__new__(PeixEpiScoreService)
    service.db = MagicMock()
    service._weights = dict(weights or DEFAULT_WEIGHTS)
    service._wastewater_by_region = lambda _virus: {"BE": 0.9}
    service._are_by_region = lambda: {"BE": 0.8}
    service._weather_by_region = lambda: {"BE": 0.6}
    service._notaufnahme_signal = lambda _virus: 0.4
    service._survstat_by_region = lambda _virus: {"BE": 0.5}
    service._search_signal = lambda: 0.3
    service._shortage_signal = lambda: 0.2
    service._forecast_signal = lambda _virus: 0.7
    service._baseline_adjustment = lambda _virus: 0.1
    service._is_school_start = lambda: False
    return service


class PeixScoreServiceTests(unittest.TestCase):
    def test_search_signal_delegates_to_signals_module(self) -> None:
        service = PeixEpiScoreService.__new__(PeixEpiScoreService)

        with patch(
            "app.services.media.peix_score_signals._search_signal",
            return_value=0.42,
        ) as mocked:
            result = service._search_signal()

        mocked.assert_called_once_with(service)
        self.assertEqual(result, 0.42)

    def test_forecast_signal_delegates_to_signals_module(self) -> None:
        service = PeixEpiScoreService.__new__(PeixEpiScoreService)

        with patch(
            "app.services.media.peix_score_signals._forecast_signal",
            return_value=0.61,
        ) as mocked:
            result = service._forecast_signal("Influenza A")

        mocked.assert_called_once_with(service, "Influenza A")
        self.assertEqual(result, 0.61)

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
            now = utc_now().replace(microsecond=0)
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

    def test_baseline_adjustment_still_uses_service_override_for_positivity_rate(self) -> None:
        class OverrideService(PeixEpiScoreService):
            def _get_positivity_rate(self, virus_typ: str) -> float:
                return 0.9

        historical_rows = []
        base_date = utc_now().replace(microsecond=0)
        for index, value in enumerate([0.1, 0.2, 0.3, 0.4] * 20):
            historical_rows.append(
                type(
                    "LabRow",
                    (),
                    {
                        "datum": base_date - timedelta(weeks=52 * (index // 4)),
                        "anzahl_tests": 100,
                        "positive_ergebnisse": int(value * 100),
                    },
                )()
            )

        service = OverrideService.__new__(OverrideService)
        service.db = MagicMock()
        service.db.query.return_value.filter.return_value.all.return_value = historical_rows

        score = service._baseline_adjustment("Influenza A")

        self.assertGreater(score, 0.9)

    def test_build_marks_peix_as_ranking_signal_and_deprecates_probability_alias(self) -> None:
        payload = _stub_peix_service().build("Influenza A")

        self.assertEqual(payload["score_semantics"], "ranking_signal")
        self.assertEqual(payload["impact_probability_semantics"], "ranking_signal")
        self.assertTrue(payload["impact_probability_deprecated"])
        self.assertEqual(payload["regions"]["BE"]["score_semantics"], "ranking_signal")
        self.assertEqual(payload["regions"]["BE"]["impact_probability_semantics"], "ranking_signal")
        self.assertTrue(payload["regions"]["BE"]["impact_probability_deprecated"])
        self.assertIn("national_impact_probability", payload)
        self.assertIn("impact_probability", payload["regions"]["BE"])

    def test_build_uses_honest_weight_source_labels_for_policy_weights(self) -> None:
        default_payload = _stub_peix_service().build("Influenza A")
        translated_payload = _stub_peix_service(weights={
            "bio": 0.40,
            "forecast": 0.20,
            "weather": 0.10,
            "shortage": 0.15,
            "search": 0.10,
            "baseline": 0.05,
        }).build("Influenza A")

        self.assertEqual(default_payload["weights_source"], "manual_policy_default")
        self.assertEqual(translated_payload["weights_source"], "translated_lab_policy")
