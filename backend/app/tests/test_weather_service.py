from __future__ import annotations

from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, WeatherData
from app.services.data_ingest.weather_service import WeatherService


class _FakeDB:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeWeatherService(WeatherService):
    def __init__(self, existing_dates: set[datetime.date]) -> None:
        super().__init__(db=_FakeDB())
        self._existing_dates = set(existing_dates)
        self.fetch_calls: list[tuple[str, str, str]] = []
        self.upserted_dates: list[datetime.date] = []

    def _fetch_weather(self, city: dict, date_str: str, last_date_str: str) -> list[dict]:
        self.fetch_calls.append((city["name"], date_str, last_date_str))
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = datetime.strptime(last_date_str, "%Y-%m-%d") - timedelta(days=1)
        records: list[dict] = []
        current = start
        while current <= end:
            for hour in range(0, 24, 4):
                records.append(
                    {
                        "timestamp": current.replace(hour=hour).isoformat(),
                        "temperature": 10.0 + hour / 10.0,
                        "relative_humidity": 60.0,
                        "pressure_msl": 1013.0,
                        "wind_speed": 12.0,
                        "sunshine": 120.0,
                        "cloud_cover": 40.0,
                        "condition": "sunny",
                        "precipitation": 0.0,
                        "dew_point": 4.0,
                    }
                )
            current += timedelta(days=1)
        return records

    def _existing_observation_dates(
        self,
        city_name: str,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> set[datetime.date]:
        del city_name
        return {
            day
            for day in self._existing_dates
            if start_date.date() <= day <= end_date.date()
        }

    def _upsert_weather(self, record: dict) -> None:
        self.upserted_dates.append(record["datum"].date())


class WeatherServiceBackfillTests(unittest.TestCase):
    def test_backfill_city_history_fetches_ranges_and_skips_full_chunks(self) -> None:
        service = _FakeWeatherService(
            existing_dates={
                datetime(2026, 1, 2).date(),
                datetime(2026, 1, 5).date(),
            }
        )

        result = service._backfill_city_history(
            {"name": "Teststadt", "lat": 0.0, "lon": 0.0},
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 1, 5),
            chunk_days=2,
        )

        self.assertEqual(
            service.fetch_calls,
            [
                ("Teststadt", "2026-01-01", "2026-01-03"),
                ("Teststadt", "2026-01-03", "2026-01-05"),
            ],
        )
        self.assertEqual(service.upserted_dates, [
            datetime(2026, 1, 1).date(),
            datetime(2026, 1, 3).date(),
            datetime(2026, 1, 4).date(),
        ])
        self.assertEqual(result["imported"], 3)
        self.assertEqual(result["skipped"], 2)
        self.assertEqual(service.db.commit_calls, 2)
        self.assertEqual(service.db.rollback_calls, 0)


class WeatherServiceForecastRunIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = WeatherService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_upsert_weather_keeps_multiple_forecast_runs_for_same_city_and_date(self) -> None:
        first_run = self.service._build_forecast_run_identity(datetime(2026, 3, 20, 6, 0))
        second_run = self.service._build_forecast_run_identity(datetime(2026, 3, 20, 12, 0))
        record = {
            "city": "München",
            "datum": datetime(2026, 3, 24, 12, 0),
            "temperatur": 9.0,
            "luftfeuchtigkeit": 70.0,
            "data_type": "DAILY_FORECAST",
        }

        self.service._upsert_weather({**record, **first_run})
        self.service._upsert_weather({**record, **second_run, "temperatur": 12.0})
        self.db.commit()

        rows = (
            self.db.query(WeatherData)
            .filter(
                WeatherData.city == "München",
                WeatherData.datum == datetime(2026, 3, 24, 12, 0),
                WeatherData.data_type == "DAILY_FORECAST",
            )
            .order_by(WeatherData.forecast_run_timestamp.asc())
            .all()
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].forecast_run_timestamp, datetime(2026, 3, 20, 6, 0))
        self.assertEqual(rows[1].forecast_run_timestamp, datetime(2026, 3, 20, 12, 0))
        self.assertEqual(rows[0].forecast_run_identity_source, "persisted_weather_ingest_run_v1")
        self.assertEqual(rows[0].forecast_run_identity_quality, "stable_persisted_batch")

    def test_import_forecast_persists_shared_run_identity_for_one_ingest_batch(self) -> None:
        def _forecast_hourly_records(day: datetime) -> list[dict]:
            records: list[dict] = []
            for hour in range(0, 24, 4):
                records.append(
                    {
                        "timestamp": day.replace(hour=hour).isoformat(),
                        "temperature": 10.0 + hour / 10.0,
                        "relative_humidity": 55.0,
                        "pressure_msl": 1010.0,
                        "wind_speed": 12.0,
                        "sunshine": 60.0,
                        "cloud_cover": 40.0,
                        "condition": "cloudy",
                        "precipitation": 0.0,
                        "precipitation_probability": 35.0,
                        "dew_point": 4.0,
                    }
                )
            return records

        class _SingleCityForecastService(WeatherService):
            def _fetch_weather(self, city: dict, date_str: str, last_date_str: str) -> list[dict]:
                del city, last_date_str
                day = datetime.strptime(date_str, "%Y-%m-%d")
                return _forecast_hourly_records(day)

        service = _SingleCityForecastService(self.db)
        fixed_now = datetime(2026, 3, 20, 6, 42, 33)
        with patch("app.services.data_ingest.weather_service.CITIES", [{"name": "Berlin", "lat": 0.0, "lon": 0.0}]):
            with patch("app.services.data_ingest.weather_service.utc_now", return_value=fixed_now):
                inserted = service.import_forecast()

        rows = self.db.query(WeatherData).filter(WeatherData.data_type == "DAILY_FORECAST").all()
        self.assertEqual(inserted, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].forecast_run_timestamp, datetime(2026, 3, 20, 6, 42))
        self.assertEqual(
            rows[0].forecast_run_id,
            "weather_forecast_run:2026-03-20T06:42:00",
        )
        self.assertEqual(rows[0].available_time, datetime(2026, 3, 20, 6, 42))
        self.assertEqual(rows[0].forecast_run_identity_source, "persisted_weather_ingest_run_v1")
        self.assertEqual(rows[0].forecast_run_identity_quality, "stable_persisted_batch")


if __name__ == "__main__":
    unittest.main()
