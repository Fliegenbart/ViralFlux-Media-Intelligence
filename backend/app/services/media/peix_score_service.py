"""PeixEpiScore v2.0 — Unified Score Service.

Einziger, finaler Score für das ViralFlux-Dashboard.
Integriert alle 4 Virus-Typen als gewichteten Durchschnitt.

Formel:
  PeixEpiScore = (bio_aggregate × 0.50 + forecast × 0.15 + weather × 0.10
                  + shortage × 0.10 + search × 0.10 + baseline × 0.05) × 100

  bio_aggregate = Σ(virus_weight_i × epi_score_i)  über alle 4 Viren

Kein legacy Override. BfArM max. 10 Punkte Einfluss.
"""

from __future__ import annotations
from app.core.time import utc_now

import logging
import math
from bisect import bisect_right
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.schema_contracts import ensure_ml_forecast_schema_aligned
from app.models.database import (
    AREKonsultation,
    GanzimmunData,
    GoogleTrendsData,
    LabConfiguration,
    MLForecast,
    NotaufnahmeSyndromData,
    SchoolHolidays,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.data_ingest.bfarm_service import get_cached_signals
from app.services.data_ingest.weather_service import CITY_STATE_MAP
from app.services.ml.forecast_contracts import DEFAULT_DECISION_HORIZON_DAYS
from app.services.ml.forecast_horizon_utils import DEFAULT_FORECAST_REGION

logger = logging.getLogger(__name__)

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

VIRUS_WEIGHTS = {
    "Influenza A": 0.35,
    "Influenza B": 0.15,
    "SARS-CoV-2": 0.25,
    "RSV A": 0.25,
}

_NOTAUFNAHME_BY_VIRUS = {
    "Influenza A": "ILI",
    "Influenza B": "ILI",
    "SARS-CoV-2": "COVID",
    "RSV A": "ARI",
}

# SurvStat-Krankheiten pro Virus (RKI-Meldedaten → PeixEpiScore-Virus)
_SURVSTAT_BY_VIRUS: dict[str, list[str]] = {
    "Influenza A": ["influenza, saisonal"],
    "Influenza B": ["influenza, saisonal"],
    "SARS-CoV-2": ["covid-19"],
    "RSV A": ["rsv (meldepflicht gemäß ifsg)"],
}

# Dimension weights (sum = 1.00)
DEFAULT_WEIGHTS = {
    "bio": 0.50,
    "forecast": 0.15,
    "shortage": 0.15,
    "weather": 0.10,
    "search": 0.05,
    "baseline": 0.05,
}

# ── Konfigurierbare Schwellwerte ──────────────────────────────────────
# Alle Magic Numbers an einer Stelle. Begründungen wo vorhanden.
PEIX_CONFIG = {
    # Wetter: Temperatur-Risiko steigt linear unter 20°C (RKI-Grippesaison beginnt ~15°C,
    # 20°C als obere Schwelle konservativ). Normierung /25 → 0°C ergibt 0.8, -5°C ergibt 1.0.
    "weather_temp_threshold": 20.0,
    "weather_temp_divisor": 25.0,
    # Wetter: UV < 8 erhöht Risiko (UV 8 = "sehr hoch" lt. DWD-Skala).
    "weather_uv_threshold": 8.0,
    # Wetter: Gewichtung der 3 Wetter-Faktoren (Summe = 1.0)
    "weather_temp_weight": 0.40,
    "weather_uv_weight": 0.35,
    "weather_humidity_weight": 0.25,
    # Schulstart-Multiplikator: Erhöhte Kontaktrate nach Ferien.
    # Empirisch geschätzt, nicht validiert. 1.0 = deaktiviert.
    "school_start_multiplier": 1.15,
    "school_start_weather_min": 0.6,
    # Engpass-Signal: Normierung auf max. 20 "High-Demand" Meldungen.
    # 20 = oberes Ende des typischen Bereichs lt. BfArM-Daten 2023-2025.
    "shortage_norm_divisor": 20.0,
    "shortage_fieber_weight": 0.5,
    # Notaufnahme Fallback: Wenn <14 historische Werte, normiere auf /20.
    "notaufnahme_fallback_divisor": 20.0,
    # Epi-Score Komponentengewichte (4-Signale vorhanden)
    "epi_weights_4": {"wastewater": 0.35, "are": 0.25, "notaufnahme": 0.20, "survstat": 0.20},
    # Risk-Band Schwellwerte (Score 0-100)
    "risk_band_high": 75,
    "risk_band_elevated": 55,
    "risk_band_moderate": 35,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class PeixEpiScoreService:
    """PeixEpiScore v2.0 — Unified Score auf Basis bestehender Modelle."""

    def __init__(self, db: Session):
        self.db = db
        self._weights = dict(DEFAULT_WEIGHTS)
        self._load_calibrated_weights()

    def _load_calibrated_weights(self) -> None:
        """Lade Ridge-optimierte Gewichte aus LabConfiguration (Backtester)."""
        config = self.db.query(LabConfiguration).filter_by(
            is_global_default=True
        ).first()

        if not config:
            return

        # 4D (Backtester Ridge) → 6D (PeixEpiScore) Mapping.
        #
        # Der Backtester kalibriert 4 Gewichte: bio, market, psycho, context.
        # PeixEpiScore benötigt 6 Dimensionen. Mapping:
        #   bio    → bio      (1:1, direkt)
        #   market → shortage (1:1, direkt)
        #   psycho → search   (1:1, direkt)
        #   context → forecast (50%) + weather (30%) + baseline (20%)
        #
        # Der Context-Split (50/30/20) spiegelt die relative Erklaerungskraft
        # wider: Forecasts enthalten aggregierte ML-Signale, Wetter liefert
        # kurzfristigen Kontext, Baseline dient als Regularisierung.
        total_4d = (
            config.weight_bio + config.weight_market
            + config.weight_psycho + config.weight_context
        )
        if total_4d <= 0:
            return

        bio_frac = config.weight_bio / total_4d
        market_frac = config.weight_market / total_4d
        psycho_frac = config.weight_psycho / total_4d
        context_frac = config.weight_context / total_4d

        self._weights = {
            "bio": round(bio_frac, 4),
            "forecast": round(context_frac * 0.50, 4),
            "weather": round(context_frac * 0.30, 4),
            "shortage": round(market_frac, 4),
            "search": round(psycho_frac, 4),
            "baseline": round(context_frac * 0.20, 4),
        }
        # Renormalisierung: Summe = 1.0 (nötig wegen Rundung)
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: round(v / total, 4) for k, v in self._weights.items()}

        logger.info(
            f"PeixEpiScore: Kalibrierte Gewichte geladen "
            f"(Basis: {config.analyzed_days} Tage, R²={config.correlation_score})"
        )

    def build(self, virus_typ: str = "Influenza A") -> dict[str, Any]:
        """Berechne den PeixEpiScore für alle Regionen."""

        # --- Regionale Signale sammeln ---
        wastewater_per_virus = {}
        for v in VIRUS_WEIGHTS:
            wastewater_per_virus[v] = self._wastewater_by_region(v)

        are_signal = self._are_by_region()
        weather_signal = self._weather_by_region()

        notaufnahme_per_virus = {}
        for v in VIRUS_WEIGHTS:
            notaufnahme_per_virus[v] = self._notaufnahme_signal(v)

        survstat_per_virus = {}
        for v in VIRUS_WEIGHTS:
            survstat_per_virus[v] = self._survstat_by_region(v)

        # Nationale Signale
        search = self._search_signal()
        shortage = self._shortage_signal()
        forecast_per_virus = {}
        for v in VIRUS_WEIGHTS:
            forecast_per_virus[v] = self._forecast_signal(v)
        baseline = self._baseline_adjustment(virus_typ)

        # Gewichteter Forecast über alle Viren
        forecast = sum(
            forecast_per_virus[v] * w for v, w in VIRUS_WEIGHTS.items()
        )

        # School-Start Multiplier check
        school_start = self._is_school_start()

        # --- Per-Virus Epi-Scores (national) ---
        virus_scores: dict[str, dict[str, Any]] = {}
        for v, v_weight in VIRUS_WEIGHTS.items():
            ww_vals = wastewater_per_virus[v]
            ww_national = sum(ww_vals.values()) / max(len(ww_vals), 1) if ww_vals else 0.0
            are_national = sum(are_signal.values()) / max(len(are_signal), 1) if are_signal else 0.0
            not_val = notaufnahme_per_virus[v]
            surv_vals = survstat_per_virus[v]
            surv_national = sum(surv_vals.values()) / max(len(surv_vals), 1) if surv_vals else 0.0

            epi = self._compute_epi_score(
                wastewater=ww_national,
                are=are_national,
                notaufnahme=not_val,
                survstat=surv_national,
            )
            virus_scores[v] = {
                "epi_score": round(epi, 2),
                "weight": v_weight,
                "contribution": round(epi * v_weight * self._weights["bio"] * 100, 1),
            }

        bio_aggregate = sum(
            virus_scores[v]["epi_score"] * VIRUS_WEIGHTS[v]
            for v in VIRUS_WEIGHTS
        )

        # --- Regionale Berechnung ---
        regions: dict[str, dict[str, Any]] = {}
        for code, region_name in REGION_CODE_TO_NAME.items():
            # Per-Virus regional epi scores
            region_virus_epis = []
            for v, v_weight in VIRUS_WEIGHTS.items():
                ww = wastewater_per_virus[v].get(code, 0.0)
                a = are_signal.get(code, 0.0)
                n = notaufnahme_per_virus[v]
                s = survstat_per_virus[v].get(code, 0.0)
                epi = self._compute_epi_score(wastewater=ww, are=a, notaufnahme=n, survstat=s)
                region_virus_epis.append(epi * v_weight)

            region_bio = sum(region_virus_epis)
            region_weather = weather_signal.get(code, 0.0)

            # 6D-Fusion
            raw_score = (
                region_bio * self._weights["bio"]
                + forecast * self._weights["forecast"]
                + region_weather * self._weights["weather"]
                + shortage * self._weights["shortage"]
                + search * self._weights["search"]
                + baseline * self._weights["baseline"]
            )

            # Konservativer Schulstart-Multiplikator als Zusatzsignal.
            multiplier = 1.0
            if school_start and region_weather > PEIX_CONFIG["school_start_weather_min"]:
                multiplier = PEIX_CONFIG["school_start_multiplier"]

            score = round(_clamp(raw_score * multiplier) * 100.0, 1)
            risk_band = self._score_to_band(score)
            impact_probability = round(self._score_to_probability(score), 1)

            layer_contributions = {
                "Bio": round(region_bio * self._weights["bio"] * 100, 1),
                "Forecast": round(forecast * self._weights["forecast"] * 100, 1),
                "Weather": round(region_weather * self._weights["weather"] * 100, 1),
                "Shortage": round(shortage * self._weights["shortage"] * 100, 1),
                "Search": round(search * self._weights["search"] * 100, 1),
                "Baseline": round(baseline * self._weights["baseline"] * 100, 1),
            }

            top_drivers = self._top_drivers(
                bio=region_bio,
                forecast=forecast,
                weather=region_weather,
                shortage=shortage,
                search=search,
                baseline=baseline,
            )

            regions[code] = {
                "region_code": code,
                "region_name": region_name,
                "score_0_100": score,
                "risk_band": risk_band,
                "impact_probability": impact_probability,
                "top_drivers": top_drivers,
                "layer_contributions": self._normalized_contributions(layer_contributions),
            }

        # --- National ---
        national_score = round(
            sum(r["score_0_100"] for r in regions.values()) / max(len(regions), 1), 1
        )

        # Konfidenz über alle Dimensionen
        dimension_values = [bio_aggregate, forecast, weather_signal_avg(weather_signal),
                           shortage, search, baseline]
        confidence, confidence_label = self._calculate_confidence(dimension_values)

        context_signals = {
            "forecast": {
                "value": round(forecast, 2),
                "weight": self._weights["forecast"],
                "contribution": round(forecast * self._weights["forecast"] * 100, 1),
            },
            "weather": {
                "value": round(weather_signal_avg(weather_signal), 2),
                "weight": self._weights["weather"],
                "contribution": round(weather_signal_avg(weather_signal) * self._weights["weather"] * 100, 1),
            },
            "shortage": {
                "value": round(shortage, 2),
                "weight": self._weights["shortage"],
                "contribution": round(shortage * self._weights["shortage"] * 100, 1),
            },
            "search": {
                "value": round(search, 2),
                "weight": self._weights["search"],
                "contribution": round(search * self._weights["search"] * 100, 1),
            },
            "baseline": {
                "value": round(baseline, 2),
                "weight": self._weights["baseline"],
                "contribution": round(baseline * self._weights["baseline"] * 100, 1),
            },
        }

        national_drivers = self._top_drivers(
            bio=bio_aggregate,
            forecast=forecast,
            weather=weather_signal_avg(weather_signal),
            shortage=shortage,
            search=search,
            baseline=baseline,
        )

        return {
            "national_score": national_score,
            "national_band": self._score_to_band(national_score),
            "national_impact_probability": round(self._score_to_probability(national_score), 1),
            "virus_scores": virus_scores,
            "context_signals": context_signals,
            "confidence": confidence,
            "confidence_label": confidence_label,
            "weights_source": "calibrated" if self._weights != DEFAULT_WEIGHTS else "default",
            "top_drivers": national_drivers,
            "regions": regions,
            "generated_at": utc_now().isoformat(),
        }

    # ─── Epi-Score Berechnung (per Virus, adaptiv) ────────────────────────

    @staticmethod
    def _compute_epi_score(
        *,
        wastewater: float,
        are: float,
        notaufnahme: float,
        survstat: float = 0.0,
    ) -> float:
        """Gewichteter Epi-Score mit adaptiver Gewichtung.

        4-Komponenten-Modell (wenn alle Daten vorhanden):
          Wastewater 35% + ARE 25% + Notaufnahme 20% + SurvStat 20%
        Fallback auf 3/2/1-Komponenten wenn Daten fehlen.
        """
        has_are = are > 0
        has_not = notaufnahme > 0
        has_surv = survstat > 0

        if has_are and has_not and has_surv:
            w = PEIX_CONFIG["epi_weights_4"]
            score = wastewater * w["wastewater"] + are * w["are"] + notaufnahme * w["notaufnahme"] + survstat * w["survstat"]
        elif has_are and has_surv:
            score = wastewater * 0.40 + are * 0.30 + survstat * 0.30
        elif has_not and has_surv:
            score = wastewater * 0.40 + notaufnahme * 0.30 + survstat * 0.30
        elif has_surv:
            score = wastewater * 0.55 + survstat * 0.45
        elif has_are and has_not:
            score = wastewater * 0.45 + are * 0.30 + notaufnahme * 0.25
        elif has_are:
            score = wastewater * 0.55 + are * 0.45
        elif has_not:
            score = wastewater * 0.55 + notaufnahme * 0.45
        else:
            score = wastewater
        return _clamp(score)

    # ─── Signal-Funktionen ────────────────────────────────────────────────

    def _wastewater_by_region(self, virus_typ: str) -> dict[str, float]:
        """Wastewater per Region, normalisiert auf 0-1 (current/max)."""
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
        """ARE-Konsultationsinzidenz per Region, Perzentil-Rang-normalisiert."""
        latest = self.db.query(func.max(AREKonsultation.datum)).filter(
            AREKonsultation.altersgruppe == "00+",
        ).scalar()
        if not latest:
            return {}

        latest_row = self.db.query(AREKonsultation).filter(
            AREKonsultation.datum == latest,
            AREKonsultation.altersgruppe == "00+",
        ).first()
        current_week = latest_row.kalenderwoche if latest_row else None

        rows = self.db.query(AREKonsultation).filter(
            AREKonsultation.datum == latest,
            AREKonsultation.altersgruppe == "00+",
        ).all()

        out: dict[str, float] = {}
        for row in rows:
            name = str(row.bundesland or "").strip().lower()
            code = REGION_NAME_TO_CODE.get(name)
            if not code:
                continue
            current_value = float(row.konsultationsinzidenz or 0.0)

            if current_week is not None:
                historical = self.db.query(AREKonsultation.konsultationsinzidenz).filter(
                    AREKonsultation.kalenderwoche == current_week,
                    AREKonsultation.altersgruppe == "00+",
                    AREKonsultation.bundesland == row.bundesland,
                ).all()
                values = sorted([h[0] for h in historical if h[0] is not None])
                if len(values) >= 3:
                    rank = bisect_right(values, current_value)
                    out[code] = _clamp(rank / len(values))
                    continue

            # Fallback: simple max-normalization
            max_val = max((float(r.konsultationsinzidenz or 0.0) for r in rows), default=1.0) or 1.0
            out[code] = _clamp(current_value / max_val)
        return out

    def _survstat_by_region(self, virus_typ: str) -> dict[str, float]:
        """SurvStat-Meldeinzidenz per Region, Perzentil-Rang-normalisiert.

        Nutzt laborbestätigte RKI-Fallzahlen als epidemiologischen
        Gold-Standard-Indikator. Normalisierung erfolgt via Perzentil-Rang
        gegenüber derselben ISO-Woche der Vorjahre (mind. 3 Werte).
        """
        diseases = _SURVSTAT_BY_VIRUS.get(virus_typ)
        if not diseases:
            return {}

        latest_week = (
            self.db.query(func.max(SurvstatWeeklyData.week_start))
            .filter(
                func.lower(SurvstatWeeklyData.disease).in_(diseases),
                SurvstatWeeklyData.bundesland != "Gesamt",
                SurvstatWeeklyData.week > 0,
            )
            .scalar()
        )
        if not latest_week:
            return {}

        rows = (
            self.db.query(SurvstatWeeklyData)
            .filter(
                func.lower(SurvstatWeeklyData.disease).in_(diseases),
                SurvstatWeeklyData.week_start == latest_week,
                SurvstatWeeklyData.bundesland != "Gesamt",
            )
            .all()
        )
        if not rows:
            return {}

        current_week_nr = rows[0].week

        per_bl: dict[str, float] = {}
        for row in rows:
            bl = str(row.bundesland or "").strip()
            per_bl[bl] = per_bl.get(bl, 0.0) + float(row.incidence or 0.0)

        out: dict[str, float] = {}
        for bl, current_incidence in per_bl.items():
            code = REGION_NAME_TO_CODE.get(bl.lower())
            if not code:
                continue

            if current_week_nr and current_week_nr > 0:
                historical = (
                    self.db.query(func.sum(SurvstatWeeklyData.incidence))
                    .filter(
                        func.lower(SurvstatWeeklyData.disease).in_(diseases),
                        SurvstatWeeklyData.week == current_week_nr,
                        SurvstatWeeklyData.bundesland == bl,
                        SurvstatWeeklyData.week_start < latest_week,
                    )
                    .group_by(SurvstatWeeklyData.year)
                    .all()
                )
                values = sorted([float(h[0]) for h in historical if h[0] is not None])
                if len(values) >= 3:
                    rank = bisect_right(values, current_incidence)
                    out[code] = _clamp(rank / len(values))
                    continue

            max_val = max(per_bl.values(), default=1.0) or 1.0
            out[code] = _clamp(current_incidence / max_val)

        return out

    def _weather_by_region(self) -> dict[str, float]:
        """Wetter-Risiko per Region (temp×0.4 + uv×0.35 + humidity×0.25)."""
        cutoff = utc_now() - timedelta(days=2)
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
            temp_factor = _clamp((PEIX_CONFIG["weather_temp_threshold"] - temp) / PEIX_CONFIG["weather_temp_divisor"])
            uv_factor = _clamp((PEIX_CONFIG["weather_uv_threshold"] - uv) / PEIX_CONFIG["weather_uv_threshold"])
            humidity_factor = _clamp(humidity / 100.0)
            risk = (temp_factor * PEIX_CONFIG["weather_temp_weight"]
                    + uv_factor * PEIX_CONFIG["weather_uv_weight"]
                    + humidity_factor * PEIX_CONFIG["weather_humidity_weight"])
            per_region.setdefault(code, []).append(_clamp(risk))

        return {
            code: round(sum(values) / max(len(values), 1), 4)
            for code, values in per_region.items()
        }

    def _notaufnahme_signal(self, virus_typ: str) -> float:
        """Notaufnahme-Signal per Virus, Perzentil-Rang über 3J-Historie."""
        syndrome = _NOTAUFNAHME_BY_VIRUS.get(virus_typ, "ARI")
        latest = self.db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
        ).order_by(NotaufnahmeSyndromData.datum.desc()).first()
        if not latest:
            return 0.0

        current_value = (
            latest.relative_cases_7day_ma
            if latest.relative_cases_7day_ma is not None
            else latest.relative_cases
        )
        if current_value is None:
            return 0.0

        three_years_ago = utc_now() - timedelta(days=365 * 3)
        historical = self.db.query(
            NotaufnahmeSyndromData.relative_cases_7day_ma,
            NotaufnahmeSyndromData.relative_cases,
        ).filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.age_group == "00+",
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.datum >= three_years_ago,
        ).all()

        values = []
        for rel_ma, rel in historical:
            value = rel_ma if rel_ma is not None else rel
            if value is not None:
                values.append(value)
        values = sorted(values)

        if len(values) < 14:
            return _clamp(float(current_value) / PEIX_CONFIG["notaufnahme_fallback_divisor"])

        rank = bisect_right(values, current_value)
        return _clamp(rank / len(values))

    def _search_signal(self) -> float:
        """Google Trends Steigung (2W vs 4W), nicht nur Mittelwert."""
        now = utc_now()
        two_weeks_ago = now - timedelta(days=14)
        four_weeks_ago = now - timedelta(days=28)

        recent = float(self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= two_weeks_ago,
        ).scalar() or 0)

        previous = float(self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= four_weeks_ago,
            GoogleTrendsData.datum < two_weeks_ago,
        ).scalar() or 0)

        if previous > 0:
            slope = (recent - previous) / previous
        else:
            slope = 0.0

        if slope > 0.2:
            return _clamp(0.5 + slope)
        elif slope < -0.2:
            return _clamp(0.5 + slope)
        return 0.5

    def _shortage_signal(self) -> float:
        """BfArM-Engpass-Signal, nur GELO-relevante Kategorien (Atemwege + Fieber/Schmerz)."""
        signals = get_cached_signals() or {}
        by_cat = signals.get("by_category", {})
        atemwege = float((by_cat.get("Atemwege") or {}).get("high_demand", 0) or 0)
        fieber = float((by_cat.get("Fieber_Schmerz") or {}).get("high_demand", 0) or 0)
        # Atemwege voll gewichtet, Fieber/Schmerz halb (indirekt GELO-relevant)
        count = atemwege + fieber * PEIX_CONFIG["shortage_fieber_weight"]
        return _clamp(count / PEIX_CONFIG["shortage_norm_divisor"])

    def _forecast_signal(self, virus_typ: str) -> float:
        """Prophet/HW-Trend aus MLForecast-Tabelle (bestehende Logik)."""
        ensure_ml_forecast_schema_aligned(self.db)
        latest = self.db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.region == DEFAULT_FORECAST_REGION,
            MLForecast.horizon_days == DEFAULT_DECISION_HORIZON_DAYS,
        ).order_by(MLForecast.created_at.desc()).first()

        if not latest:
            return 0.5

        forecasts = self.db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.region == DEFAULT_FORECAST_REGION,
            MLForecast.horizon_days == DEFAULT_DECISION_HORIZON_DAYS,
            MLForecast.created_at >= latest.created_at - timedelta(seconds=10),
        ).order_by(MLForecast.forecast_date.asc()).all()

        if len(forecasts) < 2:
            return 0.5

        slope = (forecasts[-1].predicted_value - forecasts[0].predicted_value) / len(forecasts)
        first_val = forecasts[0].predicted_value or 1
        trend_pct = slope / first_val if first_val > 0 else 0

        if trend_pct > 0.01:
            return _clamp(0.5 + trend_pct * 10)
        elif trend_pct < -0.01:
            return _clamp(0.5 + trend_pct * 10)
        return 0.5

    def _baseline_adjustment(self, virus_typ: str) -> float:
        """Saisonale Baseline-Korrektur als 0-1 Signal (z-Score → Sigmoid)."""
        current_week = utc_now().isocalendar()[1]

        historical = self.db.query(GanzimmunData).filter(
            GanzimmunData.anzahl_tests > 0,
        ).all()

        if len(historical) < 52:
            return 0.5

        weekly_rates: dict[int, list[float]] = {}
        for d in historical:
            week = d.datum.isocalendar()[1]
            rate = (d.positive_ergebnisse or 0) / d.anzahl_tests
            weekly_rates.setdefault(week, []).append(rate)

        if current_week not in weekly_rates or len(weekly_rates[current_week]) < 2:
            return 0.5

        hist_mean = float(np.mean(weekly_rates[current_week]))
        hist_std = float(np.std(weekly_rates[current_week])) or 0.01

        current_rate = self._get_positivity_rate(virus_typ)
        z_score = (current_rate - hist_mean) / hist_std

        # Sigmoid mapping: z-Score → 0-1
        return _clamp(1.0 / (1.0 + math.exp(-z_score)))

    def _get_positivity_rate(self, virus_typ: str) -> float:
        """Aktuelle Positivrate (14d-Fenster)."""
        two_weeks_ago = utc_now() - timedelta(days=14)

        test_typ_map = {
            "Influenza A": "Influenza A",
            "Influenza B": "Influenza B",
            "SARS-CoV-2": "SARS-CoV-2",
            "RSV A": "RSV",
        }

        query = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= two_weeks_ago,
            GanzimmunData.anzahl_tests > 0,
        )
        mapped = test_typ_map.get(virus_typ)
        if mapped:
            query = query.filter(GanzimmunData.test_typ == mapped)

        recent = query.all()
        if not recent:
            return 0.0

        total = sum(d.anzahl_tests for d in recent)
        positive = sum(d.positive_ergebnisse or 0 for d in recent)
        return positive / total if total > 0 else 0.0

    def _is_school_start(self) -> bool:
        """True wenn Ferienende innerhalb der letzten 7 Tage."""
        now = utc_now()
        week_ago = now - timedelta(days=7)
        count = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.end_datum >= week_ago,
            SchoolHolidays.end_datum <= now,
        ).count()
        return count > 0

    # ─── Scoring Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _score_to_probability(score: float) -> float:
        return _clamp(1.0 / (1.0 + math.exp(-(score - 50.0) / 11.0)), 0.0, 1.0) * 100.0

    @staticmethod
    def _score_to_band(score: float) -> str:
        if score >= PEIX_CONFIG["risk_band_high"]:
            return "critical"
        if score >= PEIX_CONFIG["risk_band_elevated"]:
            return "high"
        if score >= PEIX_CONFIG["risk_band_moderate"]:
            return "elevated"
        return "low"

    @staticmethod
    def _normalized_contributions(layers: dict[str, float]) -> dict[str, float]:
        total = sum(layers.values()) or 1.0
        return {name: round((v / total) * 100.0, 1) for name, v in layers.items()}

    @staticmethod
    def _top_drivers(
        *,
        bio: float,
        forecast: float,
        weather: float,
        shortage: float,
        search: float,
        baseline: float,
    ) -> list[dict[str, Any]]:
        drivers = [
            ("Epidemiologie", bio),
            ("ML-Prognose", forecast),
            ("Wetter", weather),
            ("Versorgungslage", shortage),
            ("Suchverhalten", search),
            ("Saisonale Baseline", baseline),
        ]
        ranked = sorted(drivers, key=lambda item: item[1], reverse=True)[:3]
        return [
            {"label": name, "strength_pct": round(_clamp(value) * 100.0, 1)}
            for name, value in ranked
        ]

    @staticmethod
    def _calculate_confidence(values: list[float]) -> tuple[float, str]:
        if len(values) < 2:
            return 0.5, "Niedrig"
        std_dev = float(np.std(values))
        confidence = _clamp(1.0 - std_dev * 2.0)
        if confidence >= 0.8:
            label = "Sehr Hoch"
        elif confidence >= 0.6:
            label = "Hoch"
        elif confidence >= 0.4:
            label = "Mittel"
        else:
            label = "Niedrig"
        return round(confidence, 2), label


def weather_signal_avg(weather_by_region: dict[str, float]) -> float:
    """National average of regional weather signals."""
    if not weather_by_region:
        return 0.3
    return sum(weather_by_region.values()) / len(weather_by_region)
