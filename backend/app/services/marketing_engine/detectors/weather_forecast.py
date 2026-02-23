"""WeatherForecastDetector — 8-Tage-Wetterprognose → proaktive Gelo-OTC Aktivierungs-Chancen.

Analysiert die nächsten 8 Tage Wettervorhersage um:
1. LOW_SUNSHINE_FORECAST: Wenig Sonne (konservativ) → Immun-Support Positionierung
2. NASSKALT_FORECAST: Kalt (2-10°C) + feucht → Erkältungs-Trigger
3. EXTREME_COLD_FORECAST: Temperatur < -5°C → Akut-Trigger (Erkältung im Anflug)
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import logging

from .base_detector import OpportunityDetector
from app.models.database import WeatherData
from app.services.data_ingest.weather_service import CITY_STATE_MAP

logger = logging.getLogger(__name__)

# Schwellwerte
UV_LOW_THRESHOLD = 3.0
UV_LOW_MIN_DAYS = 5            # Von 8 Tagen mindestens 5 mit UV < 3
NASSKALT_TEMP_MIN = 2.0        # °C
NASSKALT_TEMP_MAX = 10.0       # °C
NASSKALT_HUMIDITY_THRESHOLD = 80.0  # %
NASSKALT_POP_THRESHOLD = 0.6   # 60% Niederschlagswahrscheinlichkeit
NASSKALT_MIN_DAYS = 4          # Von 8 Tagen mindestens 4 nasskalt
EXTREME_COLD_THRESHOLD = -5.0  # °C
EXTREME_COLD_MIN_DAYS = 3


class WeatherForecastDetector(OpportunityDetector):
    """Erkennt proaktive Vertriebschancen aus 8-Tage-Wetterprognose."""

    OPPORTUNITY_TYPE = "WEATHER_FORECAST"

    def detect(self) -> list[dict]:
        """Analysiert Forecast-Daten für alle Städte."""
        opportunities = []

        forecast_data = self._load_forecast_data()
        if not forecast_data:
            logger.info("Keine Forecast-Wetterdaten — WeatherForecastDetector übersprungen")
            return []

        # Pattern 1: Wenig Sonne (UV)
        low_sun = self._detect_low_sunshine(forecast_data)
        if low_sun:
            opportunities.append(low_sun)

        # Pattern 2: Nasskalt (kalt + feucht)
        nasskalt = self._detect_nasskalt(forecast_data)
        if nasskalt:
            opportunities.append(nasskalt)

        # Pattern 3: Extremkälte
        extreme = self._detect_extreme_cold(forecast_data)
        if extreme:
            opportunities.append(extreme)

        return opportunities

    def _load_forecast_data(self) -> list:
        """Lade Daily-Forecast-Wetterdaten für die nächsten 8 Tage."""
        now = datetime.utcnow()
        eight_days_out = now + timedelta(days=8)

        rows = (
            self.db.query(WeatherData)
            .filter(
                WeatherData.data_type == "DAILY_FORECAST",
                WeatherData.datum >= now,
                WeatherData.datum <= eight_days_out,
            )
            .order_by(WeatherData.datum.asc())
            .all()
        )
        return rows

    def _detect_low_sunshine(self, forecast_data: list) -> dict | None:
        """Wenig Sonne (UV < 3 an vielen Tagen) → konservative Immun-Support Opportunity.

        Hard rule: no supplement/therapy instructions (Vitamin-D etc.).
        """
        daily_uv = defaultdict(list)
        for row in forecast_data:
            if row.uv_index is not None:
                daily_uv[row.datum.date()].append(row.uv_index)

        if len(daily_uv) < 3:
            return None

        low_days = 0
        total_days = len(daily_uv)
        uv_sum = 0
        for day_key, uv_values in daily_uv.items():
            avg = sum(uv_values) / len(uv_values)
            uv_sum += avg
            if avg < UV_LOW_THRESHOLD:
                low_days += 1

        avg_uv_overall = uv_sum / total_days if total_days > 0 else 0

        if low_days < UV_LOW_MIN_DAYS:
            return None

        urgency = self.calculate_urgency({
            "pattern": "low_sunshine",
            "low_days": low_days,
            "total_days": total_days,
        })

        # Betroffene Regionen ermitteln
        city_uv = defaultdict(list)
        for row in forecast_data:
            if row.uv_index is not None:
                city_uv[row.city].append(row.uv_index)

        low_uv_states = [
            CITY_STATE_MAP.get(city, city)
            for city, values in city_uv.items()
            if (sum(values) / len(values)) < UV_LOW_THRESHOLD
        ]

        return {
            "id": self._generate_id(f"LOWSUN-{low_days}D"),
            "type": self.OPPORTUNITY_TYPE,
            "status": "NEW",
            "urgency_score": urgency,
            "region_target": {
                "country": "DE",
                "states": low_uv_states or list(CITY_STATE_MAP.values()),
                "plz_cluster": self._derive_plz_from_states(low_uv_states or list(CITY_STATE_MAP.values())),
                "kreis_detail": self._hotspot_kreise("RESPIRATORY", low_uv_states),
            },
            "trigger_context": {
                "source": "OpenWeather_Forecast",
                "event": "LOW_SUNSHINE_FORECAST",
                "details": (
                    f"Wetterprognose: {low_days} von {total_days} Tagen mit sehr niedriger UV-Intensitaet "
                    f"(Durchschnitt: {avg_uv_overall:.1f}). Konservatives Signal fuer saisonale Belastung "
                    f"und praeventive Kommunikation (z. B. 'Immunsystem im Alltag unterstuetzen')."
                ),
                "detected_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "target_audience": ["Erwachsene", "Familien", "Praeventionsaffine Zielgruppen"],
            "_condition": "immun_support",
            "_low_days": low_days,
            "_total_days": total_days,
            "_avg_uv": round(avg_uv_overall, 1),
        }

    def _detect_nasskalt(self, forecast_data: list) -> dict | None:
        """Kalt (2-10°C) + feucht → Erkältungsrisiko."""
        daily = defaultdict(lambda: {"temps": [], "humidities": [], "pops": []})

        for row in forecast_data:
            day_key = row.datum.date()
            if row.temperatur is not None:
                daily[day_key]["temps"].append(row.temperatur)
            if row.luftfeuchtigkeit is not None:
                daily[day_key]["humidities"].append(row.luftfeuchtigkeit)
            if row.niederschlag_wahrscheinlichkeit is not None:
                daily[day_key]["pops"].append(row.niederschlag_wahrscheinlichkeit)

        nasskalt_days = 0
        total_days = len(daily)
        for day_key, conds in daily.items():
            avg_temp = sum(conds["temps"]) / len(conds["temps"]) if conds["temps"] else None
            avg_hum = sum(conds["humidities"]) / len(conds["humidities"]) if conds["humidities"] else None
            avg_pop = sum(conds["pops"]) / len(conds["pops"]) if conds["pops"] else None

            if avg_temp is None:
                continue

            is_cold = NASSKALT_TEMP_MIN <= avg_temp <= NASSKALT_TEMP_MAX
            is_wet = (
                (avg_hum is not None and avg_hum > NASSKALT_HUMIDITY_THRESHOLD)
                or (avg_pop is not None and avg_pop > NASSKALT_POP_THRESHOLD)
            )

            if is_cold and is_wet:
                nasskalt_days += 1

        if nasskalt_days < NASSKALT_MIN_DAYS:
            return None

        urgency = self.calculate_urgency({
            "pattern": "nasskalt",
            "nasskalt_days": nasskalt_days,
            "total_days": total_days,
        })

        return {
            "id": self._generate_id(f"NASSKALT-{nasskalt_days}D"),
            "type": self.OPPORTUNITY_TYPE,
            "status": "NEW",
            "urgency_score": urgency,
            "region_target": {
                "country": "DE",
                "states": list(CITY_STATE_MAP.values()),
                "plz_cluster": self._derive_plz_from_states(list(CITY_STATE_MAP.values())),
                "kreis_detail": self._hotspot_kreise("RESPIRATORY"),
            },
            "trigger_context": {
                "source": "OpenWeather_Forecast",
                "event": "NASSKALT_FORECAST",
                "details": (
                    f"Wetterprognose: {nasskalt_days} von {total_days} Tagen mit nasskalten "
                    f"Bedingungen (2-10°C + hohe Feuchtigkeit/Niederschlag). "
                    f"Erhoehtes Erkaeltungs-Risiko — Timing fuer symptomnahe OTC-Kommunikation."
                ),
                "detected_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "target_audience": ["Erwachsene", "Familien", "Pendler"],
            "_condition": "erkaltung_akut",
            "_nasskalt_days": nasskalt_days,
            "_total_days": total_days,
        }

    def _detect_extreme_cold(self, forecast_data: list) -> dict | None:
        """Extremkälte < -5°C → allgemeines Infektionsrisiko."""
        daily_temps = defaultdict(list)
        for row in forecast_data:
            if row.temperatur is not None:
                daily_temps[row.datum.date()].append(row.temperatur)

        extreme_days = 0
        min_temp = 100.0
        for day_key, temps in daily_temps.items():
            avg = sum(temps) / len(temps)
            min_temp = min(min_temp, avg)
            if avg < EXTREME_COLD_THRESHOLD:
                extreme_days += 1

        if extreme_days < EXTREME_COLD_MIN_DAYS:
            return None

        urgency = self.calculate_urgency({
            "pattern": "extreme_cold",
            "extreme_days": extreme_days,
            "min_temp": min_temp,
        })

        return {
            "id": self._generate_id(f"EXTCOLD-{extreme_days}D"),
            "type": self.OPPORTUNITY_TYPE,
            "status": "URGENT" if extreme_days >= 5 else "NEW",
            "urgency_score": urgency,
            "region_target": {
                "country": "DE",
                "states": list(CITY_STATE_MAP.values()),
                "plz_cluster": self._derive_plz_from_states(list(CITY_STATE_MAP.values())),
                "kreis_detail": self._hotspot_kreise("RESPIRATORY"),
            },
            "trigger_context": {
                "source": "OpenWeather_Forecast",
                "event": "EXTREME_COLD_FORECAST",
                "details": (
                    f"Wetterprognose: {extreme_days} Tage mit Extremkälte "
                    f"(Tiefsttemperatur {min_temp:.1f}°C). "
                    f"Stark erhoehtes Belastungs-/Erkaeltungs-Risiko (konservatives Signal) — Aktivierungsfenster."
                ),
                "detected_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "target_audience": ["Erwachsene", "Familien"],
            "_condition": "erkaltung_akut",
            "_extreme_days": extreme_days,
            "_min_temp": round(min_temp, 1),
        }

    def calculate_urgency(self, context: dict) -> float:
        """Urgency Score 0-100 basierend auf Muster-Schwere."""
        pattern = context.get("pattern", "")

        if pattern == "low_sunshine":
            low_days = context.get("low_days", 0)
            total = context.get("total_days", 8)
            ratio = low_days / max(total, 1)
            return min(100.0, ratio * 80 + 15)  # 5/8=65, 8/8=95

        elif pattern == "nasskalt":
            days = context.get("nasskalt_days", 0)
            total = context.get("total_days", 8)
            ratio = days / max(total, 1)
            return min(100.0, ratio * 90 + 10)  # 4/8=55, 8/8=100

        elif pattern == "extreme_cold":
            days = context.get("extreme_days", 0)
            min_temp = context.get("min_temp", 0)
            base = days * 15
            cold_bonus = max(0, (-min_temp - 5) * 5)
            return min(100.0, base + cold_bonus + 20)

        return 50.0
