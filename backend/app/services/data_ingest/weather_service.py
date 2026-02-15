import requests
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.core.config import get_settings
from app.models.database import WeatherData

logger = logging.getLogger(__name__)
settings = get_settings()


class WeatherService:
    """Service zum Abrufen von Wetterdaten via OpenWeather OneCall 3.0 API."""

    ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"

    CITIES = [
        {"name": "Berlin", "lat": 52.52, "lon": 13.41},
        {"name": "Hamburg", "lat": 53.55, "lon": 9.99},
        {"name": "München", "lat": 48.14, "lon": 11.58},
        {"name": "Köln", "lat": 50.94, "lon": 6.96},
        {"name": "Frankfurt", "lat": 50.11, "lon": 8.68},
    ]

    def __init__(self, db: Session):
        self.db = db
        self.api_key = settings.OPENWEATHER_API_KEY

    def _has_valid_key(self) -> bool:
        return self.api_key and self.api_key not in ('placeholder', 'your-openweather-api-key-here', '')

    def fetch_onecall(self, city: dict) -> dict:
        """Fetch current + 8-day forecast via OneCall 3.0 API."""
        params = {
            'lat': city['lat'],
            'lon': city['lon'],
            'appid': self.api_key,
            'units': 'metric',
            'lang': 'de',
            'exclude': 'minutely,alerts'
        }

        response = requests.get(self.ONECALL_URL, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def import_weather_data(self, weather_data: dict):
        """Import a single weather record into the database."""
        data = WeatherData(**weather_data)
        self.db.add(data)

    def run_full_import(self, include_forecast: bool = True):
        """Import current weather + 8-day daily forecast for all cities."""
        if not self._has_valid_key():
            logger.warning("No valid OpenWeather API key configured, skipping weather import")
            return {
                "success": False,
                "error": "No valid OPENWEATHER_API_KEY configured",
                "timestamp": datetime.utcnow().isoformat()
            }

        logger.info(f"Starting weather import for {len(self.CITIES)} cities (forecast={include_forecast})...")
        imported = 0
        errors = []

        for city in self.CITIES:
            try:
                data = self.fetch_onecall(city)

                # Current weather
                current = data.get('current', {})
                self.import_weather_data({
                    'city': city['name'],
                    'datum': datetime.utcnow(),
                    'temperatur': current.get('temp'),
                    'gefuehlte_temperatur': current.get('feels_like'),
                    'luftfeuchtigkeit': current.get('humidity'),
                    'luftdruck': current.get('pressure'),
                    'wetter_beschreibung': current.get('weather', [{}])[0].get('description', ''),
                    'wind_geschwindigkeit': current.get('wind_speed'),
                    'uv_index': current.get('uvi'),
                })
                imported += 1

                # 8-day daily forecast
                if include_forecast:
                    for day in data.get('daily', []):
                        self.import_weather_data({
                            'city': city['name'],
                            'datum': datetime.fromtimestamp(day['dt']),
                            'temperatur': day['temp']['day'],
                            'gefuehlte_temperatur': day['feels_like']['day'],
                            'luftfeuchtigkeit': day.get('humidity'),
                            'luftdruck': day.get('pressure'),
                            'wetter_beschreibung': day.get('weather', [{}])[0].get('description', ''),
                            'wind_geschwindigkeit': day.get('wind_speed'),
                            'uv_index': day.get('uvi'),
                        })
                        imported += 1

                # Hourly forecast (next 48h) - take every 3h
                for i, hour in enumerate(data.get('hourly', [])):
                    if i % 3 != 0:
                        continue
                    self.import_weather_data({
                        'city': city['name'],
                        'datum': datetime.fromtimestamp(hour['dt']),
                        'temperatur': hour.get('temp'),
                        'gefuehlte_temperatur': hour.get('feels_like'),
                        'luftfeuchtigkeit': hour.get('humidity'),
                        'luftdruck': hour.get('pressure'),
                        'wetter_beschreibung': hour.get('weather', [{}])[0].get('description', ''),
                        'wind_geschwindigkeit': hour.get('wind_speed'),
                        'uv_index': hour.get('uvi'),
                    })
                    imported += 1

                logger.info(f"Weather: {city['name']} = {current.get('temp')}°C, {current.get('weather', [{}])[0].get('description', '')}")
            except Exception as e:
                logger.error(f"Weather fetch failed for {city['name']}: {e}")
                errors.append(f"{city['name']}: {e}")

        self.db.commit()

        return {
            "success": imported > 0,
            "records_imported": imported,
            "errors": errors if errors else None,
            "timestamp": datetime.utcnow().isoformat()
        }
