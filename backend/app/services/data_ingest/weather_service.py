import requests
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.core.config import get_settings
from app.models.database import WeatherData

logger = logging.getLogger(__name__)
settings = get_settings()


class WeatherService:
    """Service zum Abrufen von Wetterdaten via OpenWeather API."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"

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

    def fetch_current_weather(self, city: dict) -> dict:
        """Hole aktuelle Wetterdaten für eine Stadt."""
        url = f"{self.BASE_URL}/weather"
        params = {
            'lat': city['lat'],
            'lon': city['lon'],
            'appid': self.api_key,
            'units': 'metric',
            'lang': 'de'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        return {
            'city': city['name'],
            'temperatur': data['main']['temp'],
            'gefuehlte_temperatur': data['main']['feels_like'],
            'luftfeuchtigkeit': data['main']['humidity'],
            'luftdruck': data['main']['pressure'],
            'wetter_beschreibung': data['weather'][0]['description'],
            'wind_geschwindigkeit': data['wind']['speed'],
            'datum': datetime.utcnow()
        }

    def fetch_forecast(self, city: dict, days: int = 8) -> list:
        """Hole Wettervorhersage (5-Tage/3h-Intervalle, Free API)."""
        url = f"{self.BASE_URL}/forecast"
        params = {
            'lat': city['lat'],
            'lon': city['lon'],
            'appid': self.api_key,
            'units': 'metric',
            'lang': 'de',
            'cnt': min(days, 5) * 8  # 8 Datenpunkte pro Tag (3h), max 5 Tage bei Free API
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        forecasts = []
        for item in data['list']:
            forecasts.append({
                'city': city['name'],
                'datum': datetime.fromtimestamp(item['dt']),
                'temperatur': item['main']['temp'],
                'gefuehlte_temperatur': item['main']['feels_like'],
                'luftfeuchtigkeit': item['main']['humidity'],
                'luftdruck': item['main']['pressure'],
                'wetter_beschreibung': item['weather'][0]['description'],
                'wind_geschwindigkeit': item['wind']['speed']
            })

        logger.info(f"Fetched {len(forecasts)} forecast points for {city['name']}")
        return forecasts

    def import_weather_data(self, weather_data: dict):
        """Importiere einen Wetterdatensatz in die Datenbank."""
        data = WeatherData(**weather_data)
        self.db.add(data)

    def run_full_import(self, include_forecast: bool = True):
        """Führe Import für alle Städte durch inkl. 8-Tage-Forecast."""
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
                # Aktuelles Wetter
                current = self.fetch_current_weather(city)
                self.import_weather_data(current)
                imported += 1

                # 8-Tage Forecast
                if include_forecast:
                    forecasts = self.fetch_forecast(city, days=8)
                    for fc in forecasts:
                        self.import_weather_data(fc)
                        imported += 1

                logger.info(f"Weather: {city['name']} = {current['temperatur']}°C")
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
