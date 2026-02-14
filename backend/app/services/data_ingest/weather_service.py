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
    
    # Wichtige deutsche Städte für repräsentative Wetterdaten
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
    
    def fetch_current_weather(self, city: dict) -> dict:
        """
        Hole aktuelle Wetterdaten für eine Stadt.
        
        Args:
            city: Dict mit 'name', 'lat', 'lon'
        
        Returns:
            Wetterdaten als Dictionary
        """
        logger.info(f"Fetching weather for {city['name']}")
        
        try:
            url = f"{self.BASE_URL}/weather"
            params = {
                'lat': city['lat'],
                'lon': city['lon'],
                'appid': self.api_key,
                'units': 'metric',  # Celsius
                'lang': 'de'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            weather_info = {
                'city': city['name'],
                'temperatur': data['main']['temp'],
                'gefuehlte_temperatur': data['main']['feels_like'],
                'luftfeuchtigkeit': data['main']['humidity'],
                'luftdruck': data['main']['pressure'],
                'wetter_beschreibung': data['weather'][0]['description'],
                'wind_geschwindigkeit': data['wind']['speed'],
                'datum': datetime.utcnow()
            }
            
            logger.info(f"Weather fetched for {city['name']}: {weather_info['temperatur']}°C")
            return weather_info
            
        except Exception as e:
            logger.error(f"Error fetching weather for {city['name']}: {e}")
            raise
    
    def fetch_forecast(self, city: dict, days: int = 5) -> list:
        """
        Hole Wettervorhersage (5 Tage, 3h Intervalle).
        
        Args:
            city: Dict mit 'name', 'lat', 'lon'
            days: Anzahl Tage (max 5 für Free API)
        
        Returns:
            Liste von Vorhersage-Daten
        """
        logger.info(f"Fetching {days}-day forecast for {city['name']}")
        
        try:
            url = f"{self.BASE_URL}/forecast"
            params = {
                'lat': city['lat'],
                'lon': city['lon'],
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'de',
                'cnt': days * 8  # 8 Datenpunkte pro Tag (3h Intervalle)
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            forecasts = []
            for item in data['list']:
                forecast = {
                    'city': city['name'],
                    'datum': datetime.fromtimestamp(item['dt']),
                    'temperatur': item['main']['temp'],
                    'gefuehlte_temperatur': item['main']['feels_like'],
                    'luftfeuchtigkeit': item['main']['humidity'],
                    'luftdruck': item['main']['pressure'],
                    'wetter_beschreibung': item['weather'][0]['description'],
                    'wind_geschwindigkeit': item['wind']['speed']
                }
                forecasts.append(forecast)
            
            logger.info(f"Fetched {len(forecasts)} forecast points for {city['name']}")
            return forecasts
            
        except Exception as e:
            logger.error(f"Error fetching forecast for {city['name']}: {e}")
            raise
    
    def import_weather_data(self, weather_data: dict):
        """Importiere Wetterdaten in die Datenbank."""
        # Check if already exists
        existing = self.db.query(WeatherData).filter(
            WeatherData.city == weather_data['city'],
            WeatherData.datum == weather_data['datum']
        ).first()
        
        if existing:
            # Update existing record
            for key, value in weather_data.items():
                if key != 'city' and key != 'datum':
                    setattr(existing, key, value)
        else:
            # Insert new record
            data = WeatherData(**weather_data)
            self.db.add(data)
        
        self.db.commit()
    
    def run_full_import(self, include_forecast: bool = True):
        """
        Führe kompletten Import für alle Städte durch.
        
        Args:
            include_forecast: Auch Vorhersage-Daten importieren
        """
        logger.info(f"Starting weather data import for {len(self.CITIES)} cities...")
        
        total_imported = 0
        
        try:
            for city in self.CITIES:
                # Aktuelle Wetterdaten
                current = self.fetch_current_weather(city)
                self.import_weather_data(current)
                total_imported += 1
                
                # Vorhersage-Daten
                if include_forecast:
                    forecasts = self.fetch_forecast(city, days=5)
                    for forecast in forecasts:
                        self.import_weather_data(forecast)
                        total_imported += 1
            
            result = {
                "success": True,
                "cities_processed": len(self.CITIES),
                "records_imported": total_imported,
                "timestamp": datetime.utcnow()
            }
            
            logger.info(f"Weather import completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Weather import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow()
            }
