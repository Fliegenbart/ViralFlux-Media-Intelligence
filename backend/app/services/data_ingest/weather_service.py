"""WeatherService — DWD-Wetterdaten via BrightSky API.

Quelle: https://api.brightsky.dev/ (Open Source, DWD-Daten, kostenlos, kein API Key)
Liefert stündliche Beobachtungen + MOSMIX-Prognosen für ganz Deutschland.
Historische Daten ab ~2015 verfügbar.
"""

import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from app.models.database import WeatherData

logger = logging.getLogger(__name__)

BRIGHTSKY_BASE = "https://api.brightsky.dev"

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

    # ─── Import-Methoden ────────────────────────────────────────────────────

    def _upsert_weather(self, record: dict):
        """Wetterdatensatz einfügen oder aktualisieren."""
        existing = self.db.query(WeatherData).filter(
            WeatherData.city == record["city"],
            WeatherData.datum == record["datum"],
            WeatherData.data_type == record["data_type"],
        ).first()

        if existing:
            for key, val in record.items():
                if key not in ("city", "datum", "data_type") and val is not None:
                    setattr(existing, key, val)
        else:
            self.db.add(WeatherData(**record))

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
                "datum": datetime.utcnow().replace(minute=0, second=0, microsecond=0),
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
        tomorrow = (datetime.utcnow() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = tomorrow + timedelta(days=8)

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

    def backfill_history(self, start_date: datetime, end_date: datetime) -> dict:
        """Historische Tageswerte für alle Städte nachladen.

        BrightSky liefert DWD-Beobachtungsdaten ab ~2015.
        Empfohlen: start_date=2024-01-01 für Backtesting-Relevanz.
        """
        logger.info(f"Weather Backfill: {start_date.date()} bis {end_date.date()} für {len(CITIES)} Städte")

        total_imported = 0
        total_skipped = 0
        errors = []

        for city in CITIES:
            city_count = 0
            current_day = start_date

            while current_day <= end_date:
                # Prüfe ob schon vorhanden
                exists = self.db.query(WeatherData).filter(
                    WeatherData.city == city["name"],
                    WeatherData.datum >= current_day.replace(hour=0),
                    WeatherData.datum <= current_day.replace(hour=23, minute=59),
                    WeatherData.data_type == "DAILY_OBSERVATION",
                ).first()

                if exists:
                    total_skipped += 1
                    current_day += timedelta(days=1)
                    continue

                try:
                    if self.import_day(city, current_day):
                        city_count += 1
                        total_imported += 1
                except Exception as e:
                    errors.append(f"{city['name']} {current_day.date()}: {e}")

                current_day += timedelta(days=1)

                # Commit alle 30 Tage (Speicher schonen)
                if city_count > 0 and city_count % 30 == 0:
                    self.db.commit()

            self.db.commit()
            logger.info(f"Backfill {city['name']}: {city_count} Tage importiert")

        result = {
            "success": total_imported > 0 or total_skipped > 0,
            "imported": total_imported,
            "skipped": total_skipped,
            "errors": errors[:10] if errors else None,
            "cities": len(CITIES),
            "date_range": f"{start_date.date()} bis {end_date.date()}",
            "timestamp": datetime.utcnow().isoformat(),
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
        return {
            "success": True,
            "source": "BrightSky (DWD)",
            "total_in_db": total_in_db,
            "details": results,
            "timestamp": datetime.utcnow().isoformat(),
        }
