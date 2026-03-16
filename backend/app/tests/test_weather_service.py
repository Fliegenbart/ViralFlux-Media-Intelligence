from __future__ import annotations

from datetime import datetime, timedelta
import unittest

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


if __name__ == "__main__":
    unittest.main()
