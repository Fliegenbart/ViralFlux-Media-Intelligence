"""PeixEpiScore Service.

Öffentliche Projektion eines proprietären Scores:
- numerischer Score (0-100)
- Banding
- Impact-Wahrscheinlichkeit
- Top-Treiber (aggregiert, ohne Formel/Parameter-Offenlegung)
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    NotaufnahmeSyndromData,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.data_ingest.weather_service import CITY_STATE_MAP


REGION_CODE_TO_NAME = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
REGION_NAME_TO_CODE = {name.lower(): code for code, name in REGION_CODE_TO_NAME.items()}

_NOTAUFNAHME_BY_VIRUS = {
    "Influenza A": "ILI",
    "Influenza B": "ILI",
    "SARS-CoV-2": "COVID",
    "RSV A": "ARI",
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class PeixEpiScoreService:
    """Berechnet eine sichere, nicht-offenlegende Score-Projektion."""

    def __init__(self, db: Session):
        self.db = db

    def build(self, virus_typ: str = "Influenza A") -> dict[str, Any]:
        wastewater = self._wastewater_by_region(virus_typ)
        are_signal = self._are_by_region()
        survstat_signal = self._survstat_by_region()
        weather_signal = self._weather_by_region()
        notaufnahme = self._notaufnahme_signal(virus_typ)
        trends = self._google_trends_signal()
        bfarm = self._bfarm_signal()

        regions: dict[str, dict[str, Any]] = {}
        for code, region_name in REGION_CODE_TO_NAME.items():
            w = wastewater.get(code, 0.0)
            a = are_signal.get(code, 0.0)
            s = survstat_signal.get(code, 0.0)
            c = weather_signal.get(code, 0.0)

            bio = _clamp(0.55 * w + 0.25 * a + 0.20 * s)
            market = _clamp(0.75 * bfarm + 0.25 * s)
            psycho = _clamp(trends)
            context = _clamp(0.70 * c + 0.30 * notaufnahme)

            weighted = {
                "Bio": bio * 0.46,
                "Market": market * 0.22,
                "Psycho": psycho * 0.12,
                "Context": context * 0.20,
            }
            score = round(sum(weighted.values()) * 100.0, 1)
            impact_probability = round(self._score_to_probability(score), 1)
            risk_band = self._score_to_band(score)
            top_drivers = self._top_drivers(
                wastewater=w,
                are=a,
                survstat=s,
                weather=c,
                notaufnahme=notaufnahme,
                bfarm=bfarm,
                trends=trends,
            )

            regions[code] = {
                "region_code": code,
                "region_name": region_name,
                "score_0_100": score,
                "risk_band": risk_band,
                "impact_probability": impact_probability,
                "top_drivers": top_drivers,
                "layer_contributions": self._normalized_contributions(weighted),
                # Keine Formel / Rohgewichte / Delay-Regeln nach außen geben.
            }

        national_score = round(sum(item["score_0_100"] for item in regions.values()) / max(len(regions), 1), 1)
        national_drivers = self._top_drivers(
            wastewater=sum(wastewater.values()) / max(len(wastewater), 1),
            are=sum(are_signal.values()) / max(len(are_signal), 1),
            survstat=sum(survstat_signal.values()) / max(len(survstat_signal), 1),
            weather=sum(weather_signal.values()) / max(len(weather_signal), 1),
            notaufnahme=notaufnahme,
            bfarm=bfarm,
            trends=trends,
        )

        return {
            "national_score": national_score,
            "national_band": self._score_to_band(national_score),
            "national_impact_probability": round(self._score_to_probability(national_score), 1),
            "top_drivers": national_drivers,
            "regions": regions,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _score_to_probability(self, score: float) -> float:
        # Sigmoid-Projection als sichere Probability-Approximation.
        return _clamp(1.0 / (1.0 + math.exp(-(score - 50.0) / 11.0)), 0.0, 1.0) * 100.0

    @staticmethod
    def _score_to_band(score: float) -> str:
        if score >= 75:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 35:
            return "elevated"
        return "low"

    @staticmethod
    def _normalized_contributions(weighted_layers: dict[str, float]) -> dict[str, float]:
        total = sum(weighted_layers.values()) or 1.0
        return {name: round((value / total) * 100.0, 1) for name, value in weighted_layers.items()}

    @staticmethod
    def _top_drivers(
        *,
        wastewater: float,
        are: float,
        survstat: float,
        weather: float,
        notaufnahme: float,
        bfarm: float,
        trends: float,
    ) -> list[dict[str, Any]]:
        drivers = [
            ("Abwasser", wastewater),
            ("ARE", are),
            ("SURVSTAT", survstat),
            ("Wetter", weather),
            ("Notaufnahme", notaufnahme),
            ("BfArM", bfarm),
            ("Google Trends", trends),
        ]
        ranked = sorted(drivers, key=lambda item: item[1], reverse=True)[:3]
        return [{"label": name, "strength_pct": round(_clamp(value) * 100.0, 1)} for name, value in ranked]

    def _wastewater_by_region(self, virus_typ: str) -> dict[str, float]:
        latest = self.db.query(func.max(WastewaterData.datum)).filter(
            WastewaterData.virus_typ == virus_typ
        ).scalar()
        if not latest:
            return {}

        rows = self.db.query(
            WastewaterData.bundesland,
            func.avg(WastewaterData.viruslast).label("avg_viruslast"),
        ).filter(
            WastewaterData.virus_typ == virus_typ,
            WastewaterData.datum == latest,
        ).group_by(WastewaterData.bundesland).all()

        max_val = max((float(row.avg_viruslast or 0.0) for row in rows), default=1.0) or 1.0
        out: dict[str, float] = {}
        for row in rows:
            code = str(row.bundesland or "").strip().upper()
            if code not in REGION_CODE_TO_NAME:
                continue
            out[code] = _clamp(float(row.avg_viruslast or 0.0) / max_val)
        return out

    def _are_by_region(self) -> dict[str, float]:
        latest = self.db.query(func.max(AREKonsultation.datum)).filter(
            AREKonsultation.altersgruppe == "00+",
        ).scalar()
        if not latest:
            return {}

        rows = self.db.query(AREKonsultation).filter(
            AREKonsultation.datum == latest,
            AREKonsultation.altersgruppe == "00+",
        ).all()
        max_val = max((float(row.konsultationsinzidenz or 0.0) for row in rows), default=1.0) or 1.0

        out: dict[str, float] = {}
        for row in rows:
            name = str(row.bundesland or "").strip().lower()
            code = REGION_NAME_TO_CODE.get(name)
            if not code:
                continue
            out[code] = _clamp(float(row.konsultationsinzidenz or 0.0) / max_val)
        return out

    def _survstat_by_region(self) -> dict[str, float]:
        latest = self.db.query(func.max(SurvstatWeeklyData.week_start)).filter(
            SurvstatWeeklyData.disease == "All",
        ).scalar()
        if not latest:
            return {}

        rows = self.db.query(SurvstatWeeklyData).filter(
            SurvstatWeeklyData.week_start == latest,
            SurvstatWeeklyData.disease == "All",
        ).all()
        max_val = max((float(row.incidence or 0.0) for row in rows), default=1.0) or 1.0

        out: dict[str, float] = {}
        for row in rows:
            if row.bundesland == "Gesamt":
                continue
            code = REGION_NAME_TO_CODE.get(str(row.bundesland or "").strip().lower())
            if not code:
                continue
            out[code] = _clamp(float(row.incidence or 0.0) / max_val)
        return out

    def _weather_by_region(self) -> dict[str, float]:
        cutoff = datetime.utcnow() - timedelta(days=2)
        rows = self.db.query(WeatherData).filter(
            WeatherData.datum >= cutoff,
        ).all()
        if not rows:
            return {}

        per_region: dict[str, list[float]] = {}
        for row in rows:
            state_name = CITY_STATE_MAP.get(row.city)
            if not state_name:
                continue
            code = REGION_NAME_TO_CODE.get(state_name.lower())
            if not code:
                continue
            temp = float(row.temperatur) if row.temperatur is not None else 7.0
            uv = float(row.uv_index) if row.uv_index is not None else 2.5
            humidity = float(row.luftfeuchtigkeit) if row.luftfeuchtigkeit is not None else 70.0
            temp_factor = _clamp((15.0 - temp) / 20.0)
            uv_factor = _clamp((5.0 - uv) / 5.0)
            humidity_factor = _clamp(humidity / 100.0)
            risk = _clamp(temp_factor * 0.45 + uv_factor * 0.35 + humidity_factor * 0.20)
            per_region.setdefault(code, []).append(risk)

        return {
            code: round(sum(values) / max(len(values), 1), 4)
            for code, values in per_region.items()
        }

    def _notaufnahme_signal(self, virus_typ: str) -> float:
        syndrome = _NOTAUFNAHME_BY_VIRUS.get(virus_typ, "ARI")
        latest = self.db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
        ).order_by(NotaufnahmeSyndromData.datum.desc()).first()
        if not latest:
            return 0.0
        value = latest.relative_cases_7day_ma if latest.relative_cases_7day_ma is not None else latest.relative_cases
        return _clamp(float(value or 0.0) / 20.0)

    def _google_trends_signal(self) -> float:
        cutoff = datetime.utcnow() - timedelta(days=14)
        value = self.db.query(func.avg(GoogleTrendsData.interest_score)).filter(
            GoogleTrendsData.datum >= cutoff
        ).scalar()
        if value is None:
            return 0.0
        return _clamp(float(value) / 100.0)

    def _bfarm_signal(self) -> float:
        signals = get_cached_signals() or {}
        score = float(signals.get("current_risk_score", 0.0) or 0.0)
        return _clamp(score / 100.0)
