"""WeatherService — DWD-Wetterdaten via BrightSky API.

Quelle: https://api.brightsky.dev/ (Open Source, DWD-Daten, kostenlos, kein API Key)
Liefert stündliche Beobachtungen + MOSMIX-Prognosen für ganz Deutschland.
Historische Daten ab ~2015 verfügbar.
"""

from app.core.time import utc_now
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging
from typing import Any

from app.models.database import WeatherData
from app.services.ml.nowcast_revision import capture_nowcast_snapshots

logger = logging.getLogger(__name__)

BRIGHTSKY_BASE = "https://api.brightsky.dev"
WEATHER_FORECAST_RUN_IDENTITY_SOURCE = "persisted_weather_ingest_run_v1"
WEATHER_FORECAST_RUN_IDENTITY_QUALITY = "stable_persisted_batch"

# 16 Landeshauptstädte — flächendeckende Abdeckung für ganz Deutschland
CITIES = [
    # Nord
    {"name": "Kiel", "lat": 54.32, "lon": 10.14},
    {"name": "Hamburg", "lat": 53.55, "lon": 9.99},
    {"name": "Schwerin", "lat": 53.63, "lon": 11.41},
    {"name": "Bremen", "lat": 53.08, "lon": 8.80},
    {"name": "Hannover", "lat": 52.37, "lon": 9.74},
    # Ost
    {"name": "Berlin", "lat": 52.52, "lon": 13.41},
    {"name": "Potsdam", "lat": 52.40, "lon": 13.07},
    {"name": "Magdeburg", "lat": 52.13, "lon": 11.63},
    {"name": "Dresden", "lat": 51.05, "lon": 13.74},
    {"name": "Erfurt", "lat": 50.98, "lon": 11.03},
    # West
    {"name": "Düsseldorf", "lat": 51.23, "lon": 6.78},
    {"name": "Saarbrücken", "lat": 49.23, "lon": 7.00},
    # Mitte
    {"name": "Wiesbaden", "lat": 50.08, "lon": 8.24},
    {"name": "Mainz", "lat": 50.00, "lon": 8.27},
    # Süd
    {"name": "Stuttgart", "lat": 48.78, "lon": 9.18},
    {"name": "München", "lat": 48.14, "lon": 11.58},
]

# Stadt → Bundesland Mapping (global, wird auch von Detektoren importiert)
CITY_STATE_MAP = {
    "Kiel": "Schleswig-Holstein",
    "Hamburg": "Hamburg",
    "Schwerin": "Mecklenburg-Vorpommern",
    "Bremen": "Bremen",
    "Hannover": "Niedersachsen",
    "Berlin": "Berlin",
    "Potsdam": "Brandenburg",
    "Magdeburg": "Sachsen-Anhalt",
    "Dresden": "Sachsen",
    "Erfurt": "Thüringen",
    "Düsseldorf": "Nordrhein-Westfalen",
    "Saarbrücken": "Saarland",
    "Wiesbaden": "Hessen",
    "Mainz": "Rheinland-Pfalz",
    "Stuttgart": "Baden-Württemberg",
    "München": "Bayern",
}


class WeatherService:
    """DWD-Wetterdaten via BrightSky (kostenlos, kein API Key)."""

    def __init__(self, db: Session):
        self.db = db

    # ─── BrightSky API Calls ────────────────────────────────────────────────

    def _fetch_weather(self, city: dict, date_str: str, last_date_str: str) -> list[dict]:
        """Stündliche Beobachtungen für einen Zeitraum abrufen."""
        url = f"{BRIGHTSKY_BASE}/weather"
        params = {
            "lat": city["lat"],
            "lon": city["lon"],
            "date": date_str,
            "last_date": last_date_str,
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("weather", [])
        except requests.RequestException as e:
            logger.warning(f"BrightSky Fehler ({city['name']}, {date_str}): {e}")
            return []

    def _fetch_current(self, city: dict) -> dict | None:
        """Aktuelles Wetter für eine Stadt."""
        url = f"{BRIGHTSKY_BASE}/current_weather"
        params = {"lat": city["lat"], "lon": city["lon"]}
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json().get("weather")
        except requests.RequestException as e:
            logger.warning(f"BrightSky current_weather Fehler ({city['name']}): {e}")
            return None

    # ─── Aggregation: Stundenwerte → Tagesdurchschnitt ──────────────────────

    def _aggregate_day(self, hourly_records: list[dict], city_name: str, day: datetime) -> dict:
        """24 Stundenwerte zu einem Tagesdatensatz aggregieren."""

        def avg(key):
            vals = [r[key] for r in hourly_records if r.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else None

        def total(key):
            vals = [r[key] for r in hourly_records if r.get(key) is not None]
            return round(sum(vals), 1) if vals else None

        # Wind: BrightSky liefert km/h → umrechnen in m/s
        wind_kmh = avg("wind_speed")
        wind_ms = round(wind_kmh / 3.6, 1) if wind_kmh is not None else None

        # UV-Proxy aus Sonnenstunden + Wolkenbedeckung
        sunshine_min = total("sunshine") or 0
        cloud_pct = avg("cloud_cover") or 50
        sunshine_h = sunshine_min / 60.0
        # Max UV im Sommer ~8, Winter ~2; Proxy: sunshine_h skaliert
        month = day.month
        seasonal_max_uv = {1: 1.5, 2: 2.5, 3: 4, 4: 5.5, 5: 7, 6: 8,
                          7: 8, 8: 7, 9: 5, 10: 3, 11: 1.5, 12: 1}
        max_uv = seasonal_max_uv.get(month, 4)
        # Mehr Sonne + weniger Wolken = höherer UV
        uv_proxy = min(max_uv, (sunshine_h / 10.0) * max_uv * (1 - cloud_pct / 200.0))

        # Condition → Beschreibung
        conditions = [r.get("condition", "") for r in hourly_records if r.get("condition")]
        dominant_condition = max(set(conditions), key=conditions.count) if conditions else "unknown"

        # Precipitation: Regen vs. Schnee
        temp = avg("temperature") or 5
        precip_total = total("precipitation") or 0
        regen = precip_total if temp > 1 else 0
        schnee = precip_total if temp <= 1 else 0

        return {
            "city": city_name,
            "datum": day.replace(hour=12, minute=0, second=0),
            "available_time": day.replace(hour=23, minute=59, second=0),
            "temperatur": avg("temperature"),
            "gefuehlte_temperatur": None,  # BrightSky liefert kein feels_like
            "luftfeuchtigkeit": avg("relative_humidity"),
            "luftdruck": avg("pressure_msl"),
            "wetter_beschreibung": dominant_condition,
            "wind_geschwindigkeit": wind_ms,
            "uv_index": round(uv_proxy, 1),
            "wolken": cloud_pct,
            "niederschlag_wahrscheinlichkeit": None,
            "regen_mm": regen,
            "schnee_mm": schnee,
            "taupunkt": avg("dew_point"),
            "data_type": "DAILY_OBSERVATION",
        }

    @staticmethod
    def _chunk_ranges(start_date: datetime, end_date: datetime, chunk_days: int) -> list[tuple[datetime, datetime]]:
        chunk_size = max(int(chunk_days), 1)
        ranges: list[tuple[datetime, datetime]] = []
        current = start_date
        while current <= end_date:
            chunk_end = min(current + timedelta(days=chunk_size - 1), end_date)
            ranges.append((current, chunk_end))
            current = chunk_end + timedelta(days=1)
        return ranges

    def _aggregate_daily_records(
        self,
        hourly_records: list[dict],
        *,
        city_name: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        by_day: dict[str, list[dict]] = {}
        for record in hourly_records:
            timestamp = str(record.get("timestamp") or "")[:10]
            if not timestamp:
                continue
            by_day.setdefault(timestamp, []).append(record)

        daily_records: list[dict] = []
        for day_str, hourly in sorted(by_day.items()):
            if len(hourly) < 6:
                continue
            day = datetime.strptime(day_str, "%Y-%m-%d")
            if day < start_date or day > end_date:
                continue
            daily_records.append(self._aggregate_day(hourly, city_name, day))
        return daily_records

    def _existing_observation_dates(
        self,
        city_name: str,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> set[datetime.date]:
        rows = (
            self.db.query(WeatherData.datum)
            .filter(
                WeatherData.city == city_name,
                WeatherData.datum >= start_date.replace(hour=0, minute=0, second=0, microsecond=0),
                WeatherData.datum <= end_date.replace(hour=23, minute=59, second=59, microsecond=999999),
                WeatherData.data_type == "DAILY_OBSERVATION",
            )
            .all()
        )
        return {
            row[0].date()
            for row in rows
            if row and row[0] is not None
        }

    def _backfill_city_history(
        self,
        city: dict,
        *,
        start_date: datetime,
        end_date: datetime,
        chunk_days: int,
    ) -> dict:
        city_name = city["name"]
        imported = 0
        skipped = 0
        errors: list[str] = []

        for chunk_start, chunk_end in self._chunk_ranges(start_date, end_date, chunk_days):
            expected_dates = {
                (chunk_start + timedelta(days=offset)).date()
                for offset in range((chunk_end - chunk_start).days + 1)
            }
            existing_dates = self._existing_observation_dates(
                city_name,
                start_date=chunk_start,
                end_date=chunk_end,
            )
            if expected_dates and expected_dates.issubset(existing_dates):
                skipped += len(expected_dates)
                continue

            try:
                records = self._fetch_weather(
                    city,
                    chunk_start.strftime("%Y-%m-%d"),
                    (chunk_end + timedelta(days=1)).strftime("%Y-%m-%d"),
                )
                daily_records = self._aggregate_daily_records(
                    records,
                    city_name=city_name,
                    start_date=chunk_start,
                    end_date=chunk_end,
                )
                aggregated_dates = set()
                for record in daily_records:
                    day_key = record["datum"].date()
                    aggregated_dates.add(day_key)
                    if day_key in existing_dates:
                        skipped += 1
                        continue
                    self._upsert_weather(record)
                    imported += 1
                missing_dates = sorted(expected_dates - existing_dates - aggregated_dates)
                if missing_dates:
                    errors.append(
                        f"{city_name} {chunk_start.date()}-{chunk_end.date()}: "
                        f"missing {len(missing_dates)} daily aggregates"
                    )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                errors.append(f"{city_name} {chunk_start.date()}-{chunk_end.date()}: {e}")

        return {
            "city": city_name,
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
        }

    # ─── Import-Methoden ────────────────────────────────────────────────────

    def _upsert_weather(self, record: dict):
        """Wetterdatensatz einfügen oder aktualisieren."""
        query = self.db.query(WeatherData).filter(
            WeatherData.city == record["city"],
            WeatherData.datum == record["datum"],
            WeatherData.data_type == record["data_type"],
        )

        forecast_run_id = record.get("forecast_run_id")
        forecast_run_timestamp = record.get("forecast_run_timestamp")
        is_forecast_record = str(record.get("data_type") or "").upper().endswith("FORECAST")
        if is_forecast_record and forecast_run_id:
            query = query.filter(WeatherData.forecast_run_id == forecast_run_id)
        elif is_forecast_record and forecast_run_timestamp is not None:
            query = query.filter(WeatherData.forecast_run_timestamp == forecast_run_timestamp)
        elif is_forecast_record:
            query = query.filter(
                WeatherData.forecast_run_id.is_(None),
                WeatherData.forecast_run_timestamp.is_(None),
            )

        existing = query.first()

        if existing:
            incoming_available = record.get("available_time")
            if incoming_available is not None:
                if existing.available_time is None or incoming_available < existing.available_time:
                    existing.available_time = incoming_available
            for key, val in record.items():
                if key not in ("city", "datum", "data_type", "available_time") and val is not None:
                    setattr(existing, key, val)
        else:
            if record.get("available_time") is None:
                record["available_time"] = utc_now()
            self.db.add(WeatherData(**record))

    @staticmethod
    def _build_forecast_run_identity(run_started_at: datetime | None = None) -> dict[str, Any]:
        """Erzeuge eine stabile Persistenz-Identitaet fuer genau einen Forecast-Importlauf."""
        timestamp = (run_started_at or utc_now()).replace(second=0, microsecond=0)
        return {
            "forecast_run_timestamp": timestamp,
            "forecast_run_id": f"weather_forecast_run:{timestamp.isoformat()}",
            "forecast_run_identity_source": WEATHER_FORECAST_RUN_IDENTITY_SOURCE,
            "forecast_run_identity_quality": WEATHER_FORECAST_RUN_IDENTITY_QUALITY,
            "available_time": timestamp,
        }

    def import_day(self, city: dict, day: datetime) -> bool:
        """Einen Tag für eine Stadt importieren (24h Aggregat)."""
        date_str = day.strftime("%Y-%m-%d")
        next_day = (day + timedelta(days=1)).strftime("%Y-%m-%d")

        records = self._fetch_weather(city, date_str, next_day)
        if not records:
            return False

        daily = self._aggregate_day(records, city["name"], day)
        self._upsert_weather(daily)
        return True

    def import_current(self) -> int:
        """Aktuelles Wetter für alle Städte importieren."""
        count = 0
        for city in CITIES:
            current = self._fetch_current(city)
            if not current:
                continue

            wind_kmh = current.get("wind_speed_60") or current.get("wind_speed_30") or 0
            humidity = current.get("relative_humidity")
            cloud = current.get("cloud_cover")

            record = {
                "city": city["name"],
                "datum": utc_now().replace(minute=0, second=0, microsecond=0),
                "available_time": utc_now(),
                "temperatur": current.get("temperature"),
                "gefuehlte_temperatur": None,
                "luftfeuchtigkeit": humidity,
                "luftdruck": current.get("pressure_msl"),
                "wetter_beschreibung": current.get("condition", ""),
                "wind_geschwindigkeit": round(wind_kmh / 3.6, 1) if wind_kmh else None,
                "uv_index": None,  # Wird beim nächsten Tagesaggregat gesetzt
                "wolken": cloud,
                "niederschlag_wahrscheinlichkeit": None,
                "regen_mm": current.get("precipitation_60"),
                "schnee_mm": None,
                "taupunkt": current.get("dew_point"),
                "data_type": "CURRENT",
            }
            self._upsert_weather(record)
            count += 1
            logger.info(f"Weather: {city['name']} = {current.get('temperature')}°C, {current.get('condition')}")

        self.db.commit()
        return count

    def import_forecast(self) -> int:
        """8-Tage-Prognose (MOSMIX) für alle Städte importieren.

        BrightSky liefert MOSMIX-Forecast-Daten wenn das Datum in der Zukunft liegt.
        Wir holen morgen bis +8 Tage, aggregieren pro Tag und speichern als DAILY_FORECAST.
        """
        count = 0
        tomorrow = (utc_now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = tomorrow + timedelta(days=8)
        forecast_run_identity = self._build_forecast_run_identity()

        for city in CITIES:
            date_str = tomorrow.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d")

            records = self._fetch_weather(city, date_str, end_str)
            if not records:
                logger.warning(f"Forecast: Keine MOSMIX-Daten für {city['name']}")
                continue

            # Gruppiere nach Tag
            by_day: dict[str, list] = {}
            for r in records:
                ts = r.get("timestamp", "")[:10]
                if ts not in by_day:
                    by_day[ts] = []
                by_day[ts].append(r)

            for day_str, hourly in by_day.items():
                if len(hourly) < 6:
                    continue  # Zu wenige Stundenwerte für sinnvolles Aggregat
                day = datetime.strptime(day_str, "%Y-%m-%d")
                daily = self._aggregate_day(hourly, city["name"], day)
                daily["data_type"] = "DAILY_FORECAST"
                daily.update(forecast_run_identity)

                # Precipitation probability aus MOSMIX (falls verfügbar)
                pop_vals = [r.get("precipitation_probability") for r in hourly
                            if r.get("precipitation_probability") is not None]
                if pop_vals:
                    daily["niederschlag_wahrscheinlichkeit"] = round(sum(pop_vals) / len(pop_vals), 1)

                self._upsert_weather(daily)
                count += 1

            logger.debug(f"Forecast {city['name']}: {len(by_day)} Tage")

        self.db.commit()
        logger.info(f"Forecast Import: {count} Tages-Prognosen für {len(CITIES)} Städte")
        return count

    def backfill_history(self, start_date: datetime, end_date: datetime, *, chunk_days: int = 90) -> dict:
        """Historische Tageswerte für alle Städte nachladen.

        BrightSky liefert DWD-Beobachtungsdaten ab ~2015.
        Empfohlen: start_date=2024-01-01 für Backtesting-Relevanz.
        """
        logger.info(
            "Weather Backfill: %s bis %s für %s Städte (chunk_days=%s)",
            start_date.date(),
            end_date.date(),
            len(CITIES),
            chunk_days,
        )

        total_imported = 0
        total_skipped = 0
        errors = []

        for city in CITIES:
            city_result = self._backfill_city_history(
                city,
                start_date=start_date,
                end_date=end_date,
                chunk_days=chunk_days,
            )
            total_imported += int(city_result["imported"])
            total_skipped += int(city_result["skipped"])
            errors.extend(city_result["errors"])
            logger.info(
                "Backfill %s: %s Tage importiert, %s übersprungen",
                city["name"],
                city_result["imported"],
                city_result["skipped"],
            )

        result = {
            "success": total_imported > 0 or total_skipped > 0,
            "imported": total_imported,
            "skipped": total_skipped,
            "chunk_days": int(chunk_days),
            "errors": errors[:10] if errors else None,
            "cities": len(CITIES),
            "date_range": f"{start_date.date()} bis {end_date.date()}",
            "timestamp": utc_now().isoformat(),
        }

        total_in_db = self.db.query(WeatherData).count()
        result["total_in_db"] = total_in_db

        logger.info(f"Weather Backfill fertig: {total_imported} neu, {total_skipped} übersprungen, {total_in_db} gesamt")
        return result

    def run_full_import(self, include_forecast: bool = True) -> dict:
        """Täglicher Import: aktuelles Wetter + letzte 7 Tage Backfill.

        Ersetzt den alten OpenWeather-Import. Kein API Key nötig.
        """
        logger.info("Starting BrightSky weather import...")
        results = {}

        # 1. Aktuelles Wetter
        try:
            current_count = self.import_current()
            results["current"] = {"imported": current_count}
        except Exception as e:
            logger.error(f"Current weather import failed: {e}")
            results["current"] = {"error": str(e)}

        # 2. Letzte 7 Tage nachladen (falls Lücken)
        try:
            end = datetime.now()
            start = end - timedelta(days=7)
            backfill = self.backfill_history(start, end)
            results["backfill_7d"] = backfill
        except Exception as e:
            logger.error(f"7-day backfill failed: {e}")
            results["backfill_7d"] = {"error": str(e)}

        # 3. 8-Tage-Forecast (MOSMIX)
        if include_forecast:
            try:
                forecast_count = self.import_forecast()
                results["forecast"] = {"imported": forecast_count}
            except Exception as e:
                logger.error(f"Forecast import failed: {e}")
                results["forecast"] = {"error": str(e)}

        total_in_db = self.db.query(WeatherData).count()
        snapshot_rows = capture_nowcast_snapshots(self.db, ["weather"]).get("weather", 0)
        return {
            "success": True,
            "source": "BrightSky (DWD)",
            "total_in_db": total_in_db,
            "snapshot_rows": snapshot_rows,
            "details": results,
            "timestamp": utc_now().isoformat(),
        }
