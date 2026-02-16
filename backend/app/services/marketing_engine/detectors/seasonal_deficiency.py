"""SeasonalDeficiencyDetector — UV-/Wetterdaten → Vitamin-D und saisonale Opportunities.

Prüft: Niedriger UV-Index über längere Zeit → Vitamin-D-Mangel-Screening empfehlen.
Fallback: Wenn kein UV-Index → Winter-Monate + niedrige Temperatur als Proxy.
"""

from datetime import datetime, timedelta
from sqlalchemy import func, and_
import logging

from .base_detector import OpportunityDetector
from app.models.database import WeatherData
from app.services.data_ingest.weather_service import CITY_STATE_MAP

logger = logging.getLogger(__name__)

UV_LOW_THRESHOLD = 3.0
UV_MIN_CONSECUTIVE_DAYS = 14


class SeasonalDeficiencyDetector(OpportunityDetector):
    """Erkennt saisonale Mangelzustände aus Wetterdaten."""

    OPPORTUNITY_TYPE = "SEASONAL_DEFICIENCY"

    def detect(self) -> list[dict]:
        """Prüft UV-Index und Temperatur für Vitamin-D-Mangel-Opportunities."""
        opportunities = []

        # Strategie 1: UV-Index aus WeatherData
        uv_opp = self._detect_low_uv()
        if uv_opp:
            opportunities.append(uv_opp)

        # Strategie 2: Fallback — Winter + Kälte
        if not uv_opp:
            cold_opp = self._detect_winter_cold()
            if cold_opp:
                opportunities.append(cold_opp)

        return opportunities

    def _detect_low_uv(self) -> dict | None:
        """Prüft auf anhaltend niedrigen UV-Index."""
        thirty_days_ago = datetime.now() - timedelta(days=30)

        # Durchschnitts-UV pro Tag (über alle Städte)
        daily_uv = (
            self.db.query(
                func.date(WeatherData.datum).label("day"),
                func.avg(WeatherData.uv_index).label("avg_uv"),
            )
            .filter(
                WeatherData.datum >= thirty_days_ago,
                WeatherData.uv_index.isnot(None),
            )
            .group_by(func.date(WeatherData.datum))
            .order_by(func.date(WeatherData.datum))
            .all()
        )

        if len(daily_uv) < 7:
            return None

        # Zähle aufeinanderfolgende Tage mit UV < Schwelle
        consecutive = 0
        max_consecutive = 0
        for row in daily_uv:
            if row.avg_uv < UV_LOW_THRESHOLD:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

        if max_consecutive < UV_MIN_CONSECUTIVE_DAYS:
            return None

        urgency = self.calculate_urgency({"consecutive_days": max_consecutive})

        # Finde Städte mit niedrigstem UV → Regionen
        city_uv = (
            self.db.query(
                WeatherData.city,
                func.avg(WeatherData.uv_index).label("avg_uv"),
            )
            .filter(
                WeatherData.datum >= thirty_days_ago,
                WeatherData.uv_index.isnot(None),
            )
            .group_by(WeatherData.city)
            .all()
        )
        low_uv_states = [
            CITY_STATE_MAP.get(row.city, row.city)
            for row in city_uv
            if row.avg_uv and row.avg_uv < UV_LOW_THRESHOLD
        ]

        return {
            "id": self._generate_id(f"VITD-{max_consecutive}D"),
            "type": self.OPPORTUNITY_TYPE,
            "status": "NEW",
            "urgency_score": urgency,
            "region_target": {
                "country": "DE",
                "states": low_uv_states or list(CITY_STATE_MAP.values()),
                "plz_cluster": "ALL",
            },
            "trigger_context": {
                "source": "OpenWeather_UV",
                "event": "LOW_UV_EXTENDED",
                "details": (
                    f"UV-Index < {UV_LOW_THRESHOLD} für {max_consecutive} "
                    f"aufeinanderfolgende Tage. Vitamin-D-Synthese physiologisch unmöglich."
                ),
                "detected_at": datetime.now().strftime("%Y-%m-%d"),
            },
            "target_audience": ["Allgemeinmediziner", "Internisten", "Orthopäden"],
            "_condition": "low_uv",
            "_consecutive_days": max_consecutive,
        }

    def _detect_winter_cold(self) -> dict | None:
        """Fallback: Winter-Monate + niedrige Temperatur = Vitamin-D-Proxy."""
        now = datetime.now()
        month = now.month

        # Nur Oktober–März
        if month not in (10, 11, 12, 1, 2, 3):
            return None

        seven_days_ago = now - timedelta(days=7)
        avg_temp = (
            self.db.query(func.avg(WeatherData.temperatur))
            .filter(WeatherData.datum >= seven_days_ago)
            .scalar()
        )

        if avg_temp is None:
            return None

        # Nur wenn kalt genug (< 5°C im Schnitt)
        if avg_temp > 5.0:
            return None

        # Wie tief im Winter? Urgency steigt von Okt→Jan
        month_urgency = {10: 40, 11: 55, 12: 70, 1: 75, 2: 65, 3: 45}
        urgency = month_urgency.get(month, 50)

        return {
            "id": self._generate_id(f"VITD-COLD-M{month}"),
            "type": self.OPPORTUNITY_TYPE,
            "status": "NEW",
            "urgency_score": float(urgency),
            "region_target": {
                "country": "DE",
                "states": list(CITY_STATE_MAP.values()),
                "plz_cluster": "ALL",
            },
            "trigger_context": {
                "source": "OpenWeather_Temperature",
                "event": "WINTER_COLD_STREAK",
                "details": (
                    f"Durchschnittstemperatur {avg_temp:.1f}°C in den letzten 7 Tagen. "
                    f"Wintermonat {now.strftime('%B')} — erhöhtes Vitamin-D-Mangel-Risiko."
                ),
                "detected_at": now.strftime("%Y-%m-%d"),
            },
            "target_audience": ["Allgemeinmediziner", "Internisten", "Orthopäden"],
            "_condition": "low_uv",
            "_avg_temperature": round(avg_temp, 1),
        }

    def calculate_urgency(self, context: dict) -> float:
        """Urgency basiert auf Anzahl aufeinanderfolgender Low-UV-Tage."""
        days = context.get("consecutive_days", 0)
        return min(100.0, days * 3.25)
