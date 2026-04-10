"""PeixEpiScore v2.0 — Unified Score Service.

Einziger, finaler Score für das ViralFlux-Dashboard.
Integriert alle 4 Virus-Typen als gewichteten Durchschnitt.

Formel:
  PeixEpiScore = (bio_aggregate × 0.50 + forecast × 0.15 + weather × 0.10
                  + shortage × 0.15 + search × 0.05 + baseline × 0.05) × 100

  bio_aggregate = Σ(virus_weight_i × epi_score_i)  über alle 4 Viren

Kein legacy Override. BfArM max. 10 Punkte Einfluss.
"""

from __future__ import annotations
from app.core.time import utc_now

import logging
import math
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.services.media import peix_score_signals
from app.models.database import (
    LabConfiguration,
)
from app.services.media.semantic_contracts import ranking_signal_contract

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

VIRUS_WEIGHTS = {
    "Influenza A": 0.35,
    "Influenza B": 0.15,
    "SARS-CoV-2": 0.25,
    "RSV A": 0.25,
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
    # Schulstart-Multiplikator: Erhöhte Kontaktrate nach Ferien.
    # Empirisch geschätzt, nicht validiert. 1.0 = deaktiviert.
    "school_start_multiplier": 1.15,
    "school_start_weather_min": 0.6,
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
        self._load_translated_lab_policy_weights()

    def _load_translated_lab_policy_weights(self) -> None:
        """Leite heuristische Policy-Gewichte aus der 4D-LabConfiguration ab."""
        config = self.db.query(LabConfiguration).filter_by(
            is_global_default=True
        ).first()

        if not config:
            return

        # 4D (LabConfiguration) → 6D (PeixEpiScore) Mapping.
        #
        # Die LabConfiguration liefert 4 Gewichte: bio, market, psycho, context.
        # PeixEpiScore benötigt 6 Dimensionen. Das folgende Mapping ist eine
        # explizite Policy-Übersetzung und keine direkte statistische Kalibrierung.
        #
        # Mapping:
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
            f"PeixEpiScore: Abgeleitete Policy-Gewichte aus LabConfiguration geladen "
            f"(Basis: {config.analyzed_days} Tage, R²={config.correlation_score})"
        )

    @staticmethod
    def _weights_source_label(weights: dict[str, float]) -> str:
        return "manual_policy_default" if weights == DEFAULT_WEIGHTS else "translated_lab_policy"

    @staticmethod
    def _ranking_signal_metadata(*, score_field: str, legacy_field: str, label: str) -> dict[str, Any]:
        return {
            "score_semantics": "ranking_signal",
            "impact_probability_semantics": "ranking_signal",
            "impact_probability_deprecated": True,
            "field_contracts": {
                score_field: ranking_signal_contract(source="PeixEpiScore", label=label),
                legacy_field: ranking_signal_contract(
                    source="PeixEpiScore",
                    label="Legacy Signal-Alias",
                ),
            },
        }

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
                **self._ranking_signal_metadata(
                    score_field="score_0_100",
                    legacy_field="impact_probability",
                    label="Signalwert",
                ),
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
            "weights_source": self._weights_source_label(self._weights),
            "top_drivers": national_drivers,
            "regions": regions,
            "generated_at": utc_now().isoformat(),
            **self._ranking_signal_metadata(
                score_field="national_score",
                legacy_field="national_impact_probability",
                label="Nationaler Signalwert",
            ),
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
        return peix_score_signals._wastewater_by_region(self, virus_typ)

    def _are_by_region(self) -> dict[str, float]:
        return peix_score_signals._are_by_region(self)

    def _survstat_by_region(self, virus_typ: str) -> dict[str, float]:
        return peix_score_signals._survstat_by_region(self, virus_typ)

    def _weather_by_region(self) -> dict[str, float]:
        return peix_score_signals._weather_by_region(self)

    def _notaufnahme_signal(self, virus_typ: str) -> float:
        return peix_score_signals._notaufnahme_signal(self, virus_typ)

    def _search_signal(self) -> float:
        return peix_score_signals._search_signal(self)

    def _shortage_signal(self) -> float:
        return peix_score_signals._shortage_signal(self)

    def _forecast_signal(self, virus_typ: str) -> float:
        return peix_score_signals._forecast_signal(self, virus_typ)

    def _baseline_adjustment(self, virus_typ: str) -> float:
        return peix_score_signals._baseline_adjustment(self, virus_typ)

    def _get_positivity_rate(self, virus_typ: str) -> float:
        return peix_score_signals._get_positivity_rate(self, virus_typ)

    def _is_school_start(self) -> bool:
        return peix_score_signals._is_school_start(self)

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
