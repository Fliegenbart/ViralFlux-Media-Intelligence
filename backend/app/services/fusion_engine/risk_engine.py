"""Fusion Engine — GanzImmun Risk Engine v3.0

Kern-Logik: 4-Dimensionen Score-Berechnung mit Genius-Multipliers.

Architektur:
  Layer 1: Signal Collection — DB → DailyInputData
  Layer 2: Sub-Scores — BIO (35%), MARKET (35%), PSYCHO (10%), CONTEXT (20%)
  Layer 3: Genius Multipliers — School-Turbo, Allergy-Dampener, Supply-Shock
  Layer 4: Confidence — Signalübereinstimmung

  Phase A: Gewichtete Heuristik (Standard)
  Phase B: XGBoost Meta-Learner Overlay (wenn trainiert + >= 90 Tage Daten)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging
import math
import pickle
import os

from app.models.database import (
    WastewaterAggregated, GoogleTrendsData, WeatherData,
    SchoolHolidays, GanzimmunData, MLForecast,
    OutbreakScore as OutbreakScoreModel,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Phase B Schwellenwert ────────────────────────────────────────────────
MIN_DAYS_FOR_META_LEARNER = 90
META_LEARNER_PATH = '/app/data/processed/meta_learner.pkl'


# ═══════════════════════════════════════════════════════════════════════════
#  1. DATA STRUCTURES (The Input Layer)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DailyInputData:
    """Container für alle normierten Daten eines Tages (Werte 0.0 bis 1.0).

    Alle Zeitreihen müssen bereits auf t+14 (Vorhersage) geshiftet sein.
    """
    date: datetime

    # --- BIO LAYER (Die biologische Wahrheit) ---
    wastewater_load: float          # RKI/AMELAG (normiert auf Max-Last des Jahres)
    internal_positivity_rate: float # Ganz Immun Labordaten (z.B. 0.15 für 15%)
    internal_baseline_delta: float  # Abweichung zur historischen Baseline (z-Score)

    # --- MARKET LAYER (Die Versorgungs-Realität) ---
    bfarm_shortage_count: int       # Anzahl relevanter Engpässe (Antibiotika/Saft)
    order_velocity_index: float     # Order Trend (0.0 - 1.0)

    # --- PSYCHO LAYER (Das Verhalten) ---
    google_search_volume: float     # Trends "Grippe" etc. (0.0 - 1.0)

    # --- CONTEXT LAYER (Die Umgebung) ---
    weather_risk_score: float       # Kombi aus Temp < 5°C & UV < 2 (0.0 - 1.0)
    pollen_load: float              # DWD Pollenindex (0.0 - 1.0)
    is_school_start: bool           # True wenn Ferienende innerhalb letzter 7 Tage


@dataclass
class RiskPrediction:
    """Der Output der Engine."""
    date: datetime
    final_risk_score: float         # 0.0 bis 100.0
    confidence_score: float         # 0.0 bis 100.0
    risk_level: str                 # GREEN, YELLOW, RED, BLACK
    primary_driver: str             # z.B. "Market (Engpässe + Orders)"
    anomalies_detected: List[str]   # z.B. ["School-Start Turbo (x1.4)"]


# ═══════════════════════════════════════════════════════════════════════════
#  2. THE CORE ENGINE (The Coca-Cola Recipe)
# ═══════════════════════════════════════════════════════════════════════════

class RiskEngine:
    """GanzImmun Fusion Engine — 4-Dimensionen Risk Scoring.

    Gewichte (The "Static" Logic):
      BIO:     35% — Abwasser + interne Labordaten
      MARKET:  35% — Lieferengpässe + Bestellgeschwindigkeit
      PSYCHO:  10% — Google-Suchverhalten
      CONTEXT: 20% — Wetter + Umgebung
    """

    def __init__(self, db: Session):
        self.db = db
        self._meta_learner = None
        self._load_meta_learner()

        # ─── The Recipe ─────────────────────────────────────────
        self.WEIGHT_BIO = 0.35
        self.WEIGHT_MARKET = 0.35
        self.WEIGHT_PSYCHO = 0.10
        self.WEIGHT_CONTEXT = 0.20

        self.PANIC_THRESHOLD = 80.0
        self.SHORTAGE_CRITICAL_LIMIT = 5

    # ═══════════════════════════════════════════════════════════════════════
    #  LAYER 1: SIGNAL COLLECTION (DB → DailyInputData)
    # ═══════════════════════════════════════════════════════════════════════

    def _normalize_wastewater(self, virus_typ: str) -> float:
        """Aktuelle Viruslast / Jahresmaximum (capped bei 1.0)."""
        one_year_ago = datetime.now() - timedelta(days=365)

        max_load = self.db.query(
            func.max(WastewaterAggregated.viruslast)
        ).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= one_year_ago,
        ).scalar() or 1.0

        current = self.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
        ).order_by(WastewaterAggregated.datum.desc()).first()

        if not current or not current.viruslast:
            return 0.0

        return min(current.viruslast / max_load, 1.0)

    def _get_internal_positivity_rate(self, virus_typ: str = None) -> float:
        """Aktuelle Positivrate aus internen Labordaten (letzte 14 Tage)."""
        two_weeks_ago = datetime.now() - timedelta(days=14)

        query = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= two_weeks_ago,
            GanzimmunData.anzahl_tests > 0,
        )

        if virus_typ:
            test_typ_map = {
                'Influenza A': 'Influenza A',
                'Influenza B': 'Influenza B',
                'SARS-CoV-2': 'SARS-CoV-2',
                'RSV A': 'RSV',
            }
            mapped = test_typ_map.get(virus_typ)
            if mapped:
                query = query.filter(GanzimmunData.test_typ == mapped)

        recent = query.all()
        if not recent:
            return 0.0

        total_tests = sum(d.anzahl_tests for d in recent)
        total_positive = sum(d.positive_ergebnisse or 0 for d in recent)

        if total_tests == 0:
            return 0.0

        return total_positive / total_tests

    def _get_baseline_delta(self, virus_typ: str = None) -> float:
        """z-Score der aktuellen Positivrate vs. historische Baseline."""
        current_week = datetime.now().isocalendar()[1]

        historical = self.db.query(GanzimmunData).filter(
            GanzimmunData.anzahl_tests > 0,
        ).all()

        if len(historical) < 52:
            return 0.0

        weekly_rates: dict[int, list[float]] = {}
        for d in historical:
            week = d.datum.isocalendar()[1]
            rate = (d.positive_ergebnisse or 0) / d.anzahl_tests
            weekly_rates.setdefault(week, []).append(rate)

        if current_week not in weekly_rates or len(weekly_rates[current_week]) < 2:
            return 0.0

        hist_mean = float(np.mean(weekly_rates[current_week]))
        hist_std = float(np.std(weekly_rates[current_week])) or 0.01

        current_rate = self._get_internal_positivity_rate(virus_typ)
        z_score = (current_rate - hist_mean) / hist_std

        return z_score

    def _get_shortage_count(self, shortage_signals: dict | None) -> int:
        """Anzahl kritischer Medikamenten-Engpässe."""
        if not shortage_signals:
            return 0
        return shortage_signals.get('high_demand_shortages', 0)

    def _get_order_velocity(self) -> tuple[float, str]:
        """Bestellgeschwindigkeit als Proxy-Signal.

        Returns: (velocity_signal_0_to_1, data_source_mode)
        """
        one_week_ago = datetime.now() - timedelta(days=7)
        recent_lab = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= one_week_ago,
            GanzimmunData.anzahl_tests > 0,
            GanzimmunData.positive_ergebnisse.isnot(None),
        ).count()

        if recent_lab > 0:
            return 0.0, "LAB_RESULTS"

        # Fallback: Bestelldaten aus extra_data
        two_weeks_ago = datetime.now() - timedelta(days=14)
        recent_orders = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= two_weeks_ago,
            GanzimmunData.extra_data.isnot(None),
        ).all()

        if not recent_orders:
            return 0.0, "NO_DATA"

        current_week_qty = 0
        prev_week_qty = 0

        for order in recent_orders:
            extra = order.extra_data or {}
            qty = extra.get('order_quantity', extra.get('quantity', 0)) or 0
            if order.datum >= one_week_ago:
                current_week_qty += qty
            else:
                prev_week_qty += qty

        if prev_week_qty > 0:
            velocity = (current_week_qty - prev_week_qty) / prev_week_qty
        else:
            velocity = 0.0

        signal = max(0.0, min(velocity, 1.0))
        return signal, "ESTIMATED_FROM_ORDERS"

    def _normalize_trends(self) -> float:
        """Google Trends Signal (Steigung des Suchinteresses, 0.0-1.0)."""
        now = datetime.now()
        two_weeks_ago = now - timedelta(days=14)
        four_weeks_ago = now - timedelta(days=28)

        recent = self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= two_weeks_ago,
        ).scalar() or 0

        previous = self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= four_weeks_ago,
            GoogleTrendsData.datum < two_weeks_ago,
        ).scalar() or 0

        if previous > 0:
            slope = (recent - previous) / previous
        else:
            slope = 0.0

        if slope > 0.2:
            return min(1.0, 0.5 + slope)
        elif slope < -0.2:
            return max(0.0, 0.5 + slope)
        return 0.5

    def _calculate_weather_risk(self) -> float:
        """Wetter-Risiko: Kalt (<5°C) + Niedrige UV (<2) + Hohe Luftfeuchtigkeit.

        Returns: 0.0-1.0 (1.0 = maximales Risiko).
        """
        latest = self.db.query(WeatherData).filter(
            WeatherData.data_type == 'CURRENT',
        ).order_by(WeatherData.datum.desc()).limit(5).all()

        if not latest:
            latest = self.db.query(WeatherData).order_by(
                WeatherData.datum.desc()
            ).limit(5).all()

        if not latest:
            return 0.3

        avg_temp = sum(w.temperatur for w in latest) / len(latest)
        avg_uv = sum(w.uv_index or 0 for w in latest) / len(latest)
        avg_humidity = sum(w.luftfeuchtigkeit or 60 for w in latest) / len(latest)

        # Temperatur: kälter = höheres Risiko (20°C→0, -5°C→1)
        temp_factor = max(0, min(1, (20 - avg_temp) / 25))
        # UV: niedriger = höheres Risiko (8→0, 0→1)
        uv_factor = max(0, min(1, (8 - avg_uv) / 8))
        # Humidity: höher = mehr Atemwegsrisiko
        humidity_factor = max(0, min(1, avg_humidity / 100))

        return temp_factor * 0.4 + uv_factor * 0.35 + humidity_factor * 0.25

    def _get_pollen_load(self) -> float:
        """DWD Pollenindex (0.0-1.0).

        TODO: Anbindung an DWD Pollenflug-Gefahrenindex API.
        Derzeit keine Datenquelle — gibt 0.0 zurück.
        Allergy-Dampener wird erst aktiv wenn pollen_load > 0.7.
        """
        return 0.0

    def _check_school_start(self) -> bool:
        """True wenn Ferienende innerhalb der letzten 7 Tage."""
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        count = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.end_datum >= week_ago,
            SchoolHolidays.end_datum <= now,
        ).count()

        return count > 0

    def _normalize_prophet_from_db(self, virus_typ: str) -> float:
        """Prophet-Baseline aus gespeicherten MLForecast-Daten (0.0-1.0)."""
        latest = self.db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ,
        ).order_by(MLForecast.created_at.desc()).first()

        if not latest:
            return 0.5

        forecasts = self.db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.created_at >= latest.created_at - timedelta(seconds=10),
        ).order_by(MLForecast.forecast_date.asc()).all()

        if len(forecasts) < 2:
            return 0.5

        slope = (forecasts[-1].predicted_value - forecasts[0].predicted_value) / len(forecasts)
        first_val = forecasts[0].predicted_value or 1
        trend_pct = slope / first_val if first_val > 0 else 0

        if trend_pct > 0.01:
            return min(1.0, 0.5 + trend_pct * 10)
        elif trend_pct < -0.01:
            return max(0.0, 0.5 + trend_pct * 10)
        return 0.5

    def _normalize_prophet(self, prophet_result: dict | None) -> float:
        """Prophet-Ergebnis normalisieren (wenn extern übergeben)."""
        if not prophet_result:
            return 0.5
        slope = prophet_result.get('trend_slope', 0)
        if slope > 0.01:
            return min(1.0, 0.5 + slope * 10)
        elif slope < -0.01:
            return max(0.0, 0.5 + slope * 10)
        return 0.5

    def _collect_daily_input(
        self, virus_typ: str, shortage_signals: dict | None
    ) -> tuple[DailyInputData, float, str]:
        """Alle DB-Signale sammeln → DailyInputData.

        Returns: (input_data, order_velocity, data_source_mode)
        """
        order_velocity, data_source_mode = self._get_order_velocity()

        input_data = DailyInputData(
            date=datetime.now(),
            wastewater_load=self._normalize_wastewater(virus_typ),
            internal_positivity_rate=self._get_internal_positivity_rate(virus_typ),
            internal_baseline_delta=self._get_baseline_delta(virus_typ),
            bfarm_shortage_count=self._get_shortage_count(shortage_signals),
            order_velocity_index=order_velocity,
            google_search_volume=self._normalize_trends(),
            weather_risk_score=self._calculate_weather_risk(),
            pollen_load=self._get_pollen_load(),
            is_school_start=self._check_school_start(),
        )

        return input_data, order_velocity, data_source_mode

    # ═══════════════════════════════════════════════════════════════════════
    #  LAYER 2: SUB-SCORES (The 4 Dimensions)
    # ═══════════════════════════════════════════════════════════════════════

    def _calculate_sub_scores(self, data: DailyInputData) -> Dict[str, float]:
        """Berechnet die 4 Dimensionen (jeweils 0.0-1.0)."""

        # 1. BIO SCORE (RKI Abwasser + interne Labordaten)
        # internal_positivity_rate * 5.0 skaliert: 20% Positivrate → ~1.0
        bio_score = (
            data.wastewater_load * 0.5 +
            data.internal_positivity_rate * 5.0 * 0.5
        )

        # 2. MARKET SCORE (Engpässe + Bestellgeschwindigkeit)
        # Engpässe linear bis 5, darüber gedeckelt
        shortage_impact = min(data.bfarm_shortage_count / 5.0, 1.0)
        market_score = (
            data.order_velocity_index * 0.6 +
            shortage_impact * 0.4
        )

        # 3. PSYCHO SCORE (Google-Suchverhalten)
        psycho_score = data.google_search_volume

        # 4. CONTEXT SCORE (Wetter + Umgebung)
        context_score = data.weather_risk_score

        return {
            "bio": min(bio_score, 1.0),
            "market": min(market_score, 1.0),
            "psycho": min(psycho_score, 1.0),
            "context": min(context_score, 1.0),
        }

    # ═══════════════════════════════════════════════════════════════════════
    #  LAYER 3: GENIUS MULTIPLIERS (The "Conditional Magic")
    # ═══════════════════════════════════════════════════════════════════════

    def _apply_genius_multipliers(
        self, base_score: float, scores: Dict[str, float], data: DailyInputData
    ) -> tuple[float, List[str]]:
        """Conditional Logic — Turbo-Booster und False-Alarm-Filter."""
        final_score = base_score
        anomalies = []

        # --- A. The "School-Start Turbo" ---
        # Ferienende + Kaltes Wetter = explosionsartiger Anstieg
        if data.is_school_start and data.weather_risk_score > 0.6:
            multiplier = 1.4
            final_score *= multiplier
            anomalies.append(f"School-Start Turbo (x{multiplier})")

        # --- B. The "Allergy-Dampener" (False Alarm Filter) ---
        # Google schreit "Schnupfen" (Psycho hoch), aber Pollen hoch & Viren niedrig
        if (data.pollen_load > 0.7 and
                scores['psycho'] > 0.6 and
                scores['bio'] < 0.3):
            multiplier = 0.4
            final_score *= multiplier
            anomalies.append("Allergy-Dampener: Pollen hoch / Virus niedrig")

        # --- C. The "Supply-Shock" Override ---
        # Wenn Medikamente fehlen, ist die Lage ernst — egal was der Rest sagt
        if data.bfarm_shortage_count >= self.SHORTAGE_CRITICAL_LIMIT:
            if final_score < 0.8:
                final_score = 0.90
                anomalies.append("CRITICAL SUPPLY SHOCK OVERRIDE")

        return min(final_score, 1.0), anomalies

    # ═══════════════════════════════════════════════════════════════════════
    #  LAYER 4: CONFIDENCE (Signal Agreement)
    # ═══════════════════════════════════════════════════════════════════════

    def _calculate_confidence(self, scores: Dict[str, float]) -> tuple[float, str]:
        """Konfidenz basierend auf Übereinstimmung der 4 Dimensionen.

        Alle Signale einig (std_dev ≈ 0) → Konfidenz 100%.
        Widersprüchliche Signale (std_dev hoch) → Konfidenz niedrig.
        """
        values = list(scores.values())
        if len(values) < 2:
            return 0.5, "Niedrig"

        std_dev = float(np.std(values))
        penalty_factor = 2.0
        confidence = max(0.0, min(1.0, 1.0 - std_dev * penalty_factor))

        if confidence >= 0.8:
            label = "Sehr Hoch"
        elif confidence >= 0.6:
            label = "Hoch"
        elif confidence >= 0.4:
            label = "Mittel"
        else:
            label = "Niedrig"

        return round(confidence, 3), label

    # ═══════════════════════════════════════════════════════════════════════
    #  BASELINE CORRECTION (Historische Anomalie-Erkennung)
    # ═══════════════════════════════════════════════════════════════════════

    def _get_baseline_correction(self, raw_score: float) -> tuple[float, str]:
        """Saisonale Baseline-Korrektur aus internen Labordaten.

        Externe Signale hoch, aber Historie für diese KW niedrig?
        → Score reduzieren (False Alarm Suppression).
        Extreme Abweichungen (>2σ) = Black Swan → Signal vertrauen.
        """
        current_week = datetime.now().isocalendar()[1]

        historical = self.db.query(GanzimmunData).filter(
            GanzimmunData.anzahl_tests > 0,
        ).all()

        if len(historical) < 52:
            return raw_score, "Keine historische Baseline (zu wenig Daten)"

        weekly_rates: dict[int, list[float]] = {}
        for d in historical:
            week = d.datum.isocalendar()[1]
            rate = (d.positive_ergebnisse or 0) / d.anzahl_tests
            weekly_rates.setdefault(week, []).append(rate)

        if current_week not in weekly_rates or len(weekly_rates[current_week]) < 2:
            return raw_score, f"Keine Baseline für KW{current_week}"

        hist_mean = float(np.mean(weekly_rates[current_week]))
        hist_std = float(np.std(weekly_rates[current_week])) or 0.01

        current_signal = raw_score / 100
        z_score = (current_signal - hist_mean) / hist_std

        explanation = f"KW{current_week}: Baseline {hist_mean:.3f} \u00b1 {hist_std:.3f}, z={z_score:.1f}"

        if z_score > 2.0:
            return raw_score, f"Black-Swan-Event: {explanation}"
        elif z_score < -1.0:
            suppression = min(0.3, abs(z_score) * 0.15)
            corrected = raw_score * (1 - suppression)
            return corrected, f"Skepsis-Korrektur ({suppression:.0%}): {explanation}"

        return raw_score, f"Normal: {explanation}"

    # ═══════════════════════════════════════════════════════════════════════
    #  PHASE B: META-LEARNER (XGBoost)
    # ═══════════════════════════════════════════════════════════════════════

    def _load_meta_learner(self):
        """Trainiertes XGBoost-Modell laden (wenn vorhanden)."""
        if os.path.exists(META_LEARNER_PATH):
            try:
                with open(META_LEARNER_PATH, 'rb') as f:
                    self._meta_learner = pickle.load(f)
                logger.info("Meta-Learner erfolgreich geladen")
            except Exception as e:
                logger.warning(f"Meta-Learner laden fehlgeschlagen: {e}")
                self._meta_learner = None

    def _build_feature_vector(self, date: datetime, virus_typ: str) -> dict:
        """Feature-Vektor X_t für Meta-Learner."""
        day_of_year = date.timetuple().tm_yday
        return {
            'wastewater_signal': self._normalize_wastewater(virus_typ),
            'prophet_forecast': self._normalize_prophet_from_db(virus_typ),
            'shortage_count': 0.0,
            'google_trend_slope': self._normalize_trends(),
            'season_sin': math.sin(2 * math.pi * day_of_year / 365.25),
            'season_cos': math.cos(2 * math.pi * day_of_year / 365.25),
            'environment': self._calculate_weather_risk(),
        }

    def _predict_meta_learner(self, virus_typ: str) -> float | None:
        """Meta-Learner-Vorhersage generieren (Phase B)."""
        if self._meta_learner is None:
            return None

        features = self._build_feature_vector(datetime.now(), virus_typ)
        X = pd.DataFrame([{
            'wastewater_norm': features['wastewater_signal'],
            'season_sin': features['season_sin'],
            'season_cos': features['season_cos'],
        }])

        try:
            pred = self._meta_learner.predict(X)[0]
            return float(pred)
        except Exception as e:
            logger.warning(f"Meta-Learner Vorhersage fehlgeschlagen: {e}")
            return None

    def train_meta_learner(self, virus_typ: str = 'Influenza A') -> dict:
        """XGBoost Meta-Learner auf historischen Daten trainieren.

        Zielvariable y: tatsächliche Inzidenz (um 14 Tage verschoben).
        Features: Abwasser, Saisonalität.
        """
        try:
            from xgboost import XGBRegressor
        except ImportError:
            return {"success": False, "error": "xgboost nicht installiert"}

        lookback = datetime.now() - timedelta(days=365)
        ww_data = self.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= lookback,
        ).order_by(WastewaterAggregated.datum.asc()).all()

        if len(ww_data) < MIN_DAYS_FOR_META_LEARNER:
            return {
                "success": False,
                "error": f"Zu wenig Daten ({len(ww_data)} < {MIN_DAYS_FOR_META_LEARNER})",
                "phase": "A",
            }

        max_load = max((d.viruslast for d in ww_data if d.viruslast), default=1.0)

        rows = []
        for i, d in enumerate(ww_data):
            if i + 14 >= len(ww_data):
                break
            day_of_year = d.datum.timetuple().tm_yday
            rows.append({
                'wastewater_norm': (d.viruslast or 0) / max_load,
                'season_sin': math.sin(2 * math.pi * day_of_year / 365.25),
                'season_cos': math.cos(2 * math.pi * day_of_year / 365.25),
                'target': ww_data[i + 14].viruslast or 0,
            })

        df = pd.DataFrame(rows)
        feature_cols = ['wastewater_norm', 'season_sin', 'season_cos']
        X = df[feature_cols]
        y = df['target']

        model = XGBRegressor(
            n_estimators=100, max_depth=4,
            learning_rate=0.1, random_state=42,
        )
        model.fit(X, y)

        os.makedirs(os.path.dirname(META_LEARNER_PATH), exist_ok=True)
        with open(META_LEARNER_PATH, 'wb') as f:
            pickle.dump(model, f)

        self._meta_learner = model
        logger.info(f"Meta-Learner trainiert: {len(df)} Samples, Features: {feature_cols}")

        return {
            "success": True,
            "training_samples": len(df),
            "phase": "B",
            "features": feature_cols,
        }

    # ═══════════════════════════════════════════════════════════════════════
    #  HAUPT-SCORE-BERECHNUNG
    # ═══════════════════════════════════════════════════════════════════════

    def compute_outbreak_score(
        self,
        virus_typ: str = 'Influenza A',
        shortage_signals: dict | None = None,
        prophet_result: dict | None = None,
    ) -> dict:
        """Outbreak Score (0-100) berechnen.

        4-Dimensionen Fusion + Genius Multipliers + Phase B Overlay.
        """
        now = datetime.now()

        # 1. Signale sammeln (Layer 1)
        input_data, order_velocity, data_source_mode = self._collect_daily_input(
            virus_typ, shortage_signals
        )

        # Prophet-Baseline (Saisonale Prognose)
        if prophet_result:
            prophet_baseline = self._normalize_prophet(prophet_result)
        else:
            prophet_baseline = self._normalize_prophet_from_db(virus_typ)

        # 2. Sub-Scores berechnen (Layer 2)
        scores = self._calculate_sub_scores(input_data)

        # 3. Weighted Fusion — Prophet ist die Basis, Live-Daten modifizieren sie
        raw_score = (
            prophet_baseline * 0.15 +
            scores['bio'] * self.WEIGHT_BIO +
            scores['market'] * self.WEIGHT_MARKET +
            scores['psycho'] * self.WEIGHT_PSYCHO +
            scores['context'] * self.WEIGHT_CONTEXT
        )

        # 4. Genius Multipliers anwenden (Layer 3)
        final_score_val, anomalies = self._apply_genius_multipliers(
            raw_score, scores, input_data
        )
        final_score_100 = final_score_val * 100.0

        # 5. Phase B: Meta-Learner Overlay (wenn verfügbar)
        phase = "A"
        meta_prediction = self._predict_meta_learner(virus_typ)

        if meta_prediction is not None:
            phase = "B"
            one_year_max = self.db.query(
                func.max(WastewaterAggregated.viruslast)
            ).filter(
                WastewaterAggregated.virus_typ == virus_typ,
                WastewaterAggregated.datum >= now - timedelta(days=365),
            ).scalar() or 1.0

            meta_score = min(100, (meta_prediction / one_year_max) * 100)
            final_score_100 = 0.7 * meta_score + 0.3 * final_score_100

        # 6. Baseline-Korrektur (historische Anomalie-Erkennung)
        corrected_score, baseline_explanation = self._get_baseline_correction(final_score_100)

        # 7. Konfidenz (Layer 4)
        confidence_numeric, confidence_label = self._calculate_confidence(scores)

        # 8. Risikostufe bestimmen
        final_score = round(max(0, min(100, corrected_score)), 1)

        if final_score >= 90:
            risk_level = "BLACK"
        elif final_score >= 65:
            risk_level = "RED"
        elif final_score >= 30:
            risk_level = "YELLOW"
        else:
            risk_level = "GREEN"

        # 9. Primary Driver (wer hat den höchsten Sub-Score?)
        driver_labels = {
            'bio': 'Bio (Abwasser + Labor)',
            'market': 'Market (Engpässe + Orders)',
            'psycho': 'Psycho (Suchtrends)',
            'context': 'Context (Wetter + Umgebung)',
        }
        max_driver = max(scores, key=scores.get)
        leading = driver_labels.get(max_driver, max_driver.upper())

        shortage_norm = min(input_data.bfarm_shortage_count / 5.0, 1.0)

        result = {
            "final_risk_score": final_score,
            "risk_level": risk_level,
            "leading_indicator": leading,
            "confidence_numeric": confidence_numeric,
            "confidence_level": confidence_label,
            "phase": phase,
            "data_source_mode": data_source_mode if data_source_mode != "LAB_RESULTS" else "FULL",
            "virus_typ": virus_typ,
            "baseline_correction": baseline_explanation,
            "anomalies_detected": anomalies,
            "component_scores": {
                # 4-Layer Dimensionen (neu)
                "bio": round(scores['bio'], 3),
                "market": round(scores['market'], 3),
                "psycho": round(scores['psycho'], 3),
                "context": round(scores['context'], 3),
                # Einzelsignale (backward compat)
                "wastewater": round(input_data.wastewater_load, 3),
                "drug_shortage": round(shortage_norm, 3),
                "prophet_trend": round(prophet_baseline, 3),
                "search_trends": round(input_data.google_search_volume, 3),
                "environment": round(input_data.weather_risk_score, 3),
                "order_velocity": round(order_velocity, 3),
            },
            "contributions": {
                "Bio": round(scores['bio'] * self.WEIGHT_BIO * 100, 1),
                "Market": round(scores['market'] * self.WEIGHT_MARKET * 100, 1),
                "Psycho": round(scores['psycho'] * self.WEIGHT_PSYCHO * 100, 1),
                "Context": round(scores['context'] * self.WEIGHT_CONTEXT * 100, 1),
                "Prophet": round(prophet_baseline * 0.15 * 100, 1),
            },
            "timestamp": now.isoformat(),
        }

        # 10. Score persistieren
        self._save_score(result)

        return result

    def _save_score(self, result: dict):
        """Outbreak Score in Datenbank speichern."""
        try:
            score = OutbreakScoreModel(
                datum=datetime.now(),
                virus_typ=result['virus_typ'],
                final_risk_score=result['final_risk_score'],
                risk_level=result['risk_level'],
                leading_indicator=result['leading_indicator'],
                confidence_level=result['confidence_level'],
                confidence_numeric=result['confidence_numeric'],
                component_scores=result['component_scores'],
                data_source_mode=result['data_source_mode'],
                phase=result['phase'],
            )
            self.db.add(score)
            self.db.commit()
        except Exception as e:
            logger.warning(f"Outbreak Score speichern fehlgeschlagen: {e}")
            self.db.rollback()

    # ═══════════════════════════════════════════════════════════════════════
    #  AGGREGATION & HISTORY
    # ═══════════════════════════════════════════════════════════════════════

    def compute_all_viruses(
        self,
        shortage_signals: dict | None = None,
        prophet_results: dict | None = None,
    ) -> dict:
        """Outbreak Scores für alle Virus-Typen berechnen."""
        viruses = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']
        scores = {}

        for virus in viruses:
            prophet = prophet_results.get(virus) if prophet_results else None
            try:
                scores[virus] = self.compute_outbreak_score(
                    virus_typ=virus,
                    shortage_signals=shortage_signals,
                    prophet_result=prophet,
                )
            except Exception as e:
                logger.error(f"Score-Berechnung fehlgeschlagen für {virus}: {e}")
                self.db.rollback()
                scores[virus] = {
                    "final_risk_score": 0,
                    "risk_level": "GREEN",
                    "error": str(e),
                }

        all_scores = [s['final_risk_score'] for s in scores.values() if 'final_risk_score' in s]
        overall = max(all_scores) if all_scores else 0

        return {
            "overall_score": round(overall, 1),
            "overall_risk_level": (
                "BLACK" if overall >= 90 else
                "RED" if overall >= 65 else
                "YELLOW" if overall >= 30 else
                "GREEN"
            ),
            "per_virus": scores,
            "timestamp": datetime.now().isoformat(),
        }

    def get_score_history(self, virus_typ: str = None, days: int = 90) -> list:
        """Historische Outbreak Scores abrufen."""
        start = datetime.now() - timedelta(days=days)
        query = self.db.query(OutbreakScoreModel).filter(
            OutbreakScoreModel.datum >= start,
        )
        if virus_typ:
            query = query.filter(OutbreakScoreModel.virus_typ == virus_typ)

        scores = query.order_by(OutbreakScoreModel.datum.asc()).all()

        return [
            {
                "date": s.datum.isoformat(),
                "virus_typ": s.virus_typ,
                "score": s.final_risk_score,
                "risk_level": s.risk_level,
                "confidence": s.confidence_level,
                "phase": s.phase,
                "leading_indicator": s.leading_indicator,
            }
            for s in scores
        ]
