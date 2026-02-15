"""Fusion Engine — Ganz Immun Outbreak Risk Score.

Kombiniert Abwasser-Surveillance, Lieferengpässe, Prophet-Prognosen,
Suchtrends, Wetter/Ferien-Daten und interne Labordaten zu einem
einzigen 0-100 Risiko-Score.

Architektur:
  Phase A (Bootstrap): Gewichtete Heuristik wenn < 90 Tage Daten
  Phase B (KI-gesteuert): XGBoost Meta-Learner bei ausreichend Daten
"""

import numpy as np
import pandas as pd
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

# ─── Signal-Gewichte (Phase A: Heuristik) ──────────────────────────────────
WEIGHT_WASTEWATER = 0.35
WEIGHT_DRUG_SHORTAGE = 0.25
WEIGHT_PROPHET_TREND = 0.20
WEIGHT_SEARCH_TRENDS = 0.10
WEIGHT_ENVIRONMENT = 0.10

# ─── Phase-Schwellenwert ───────────────────────────────────────────────────
MIN_DAYS_FOR_META_LEARNER = 90
META_LEARNER_PATH = '/app/data/processed/meta_learner.pkl'


class RiskEngine:
    """Zentrale Fusion Engine — kombiniert alle Signale zum Outbreak Score."""

    def __init__(self, db: Session):
        self.db = db
        self._meta_learner = None
        self._load_meta_learner()

    # ═══════════════════════════════════════════════════════════════════════
    #  NORMALISIERUNG (0.0 → 1.0)
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

    def _normalize_shortage(self, shortage_signals: dict | None) -> float:
        """Lieferengpass-Signal normalisieren.

        >= 5 High-Demand Medikamente → 1.0
        >= 2 High-Demand Medikamente → 0.5
        sonst → 0.0
        """
        if not shortage_signals:
            return 0.0

        count = shortage_signals.get('high_demand_shortages', 0)
        if count >= 5:
            return 1.0
        elif count >= 2:
            return 0.5
        return 0.0

    def _normalize_prophet_from_db(self, virus_typ: str) -> float:
        """Prophet-Signal aus gespeicherten MLForecast-Daten.

        Positiver Trend → 1.0 (Welle kommt)
        Flach → 0.5
        Fallend → 0.0
        """
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

    def _normalize_trends(self) -> float:
        """Google Trends Signal (Steigung des Suchinteresses, nicht Absolutwert)."""
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

    def _normalize_environment(self) -> float:
        """Wetter + Ferien Signal.

        Kalt + trocken (Innenräume) + Ferien → höheres Risiko.
        """
        latest_weather = self.db.query(WeatherData).order_by(
            WeatherData.datum.desc()
        ).limit(5).all()

        if latest_weather:
            avg_temp = sum(w.temperatur for w in latest_weather) / len(latest_weather)
            avg_hum = sum(w.luftfeuchtigkeit for w in latest_weather) / len(latest_weather)
        else:
            avg_temp = 10.0
            avg_hum = 60.0

        # Temperatur: kälter = höheres Risiko (25°C→0, -5°C→1)
        temp_factor = max(0, min(1, (25 - avg_temp) / 30))
        # Luftfeuchtigkeit: trockener = höheres Risiko
        hum_factor = max(0, min(1, (100 - avg_hum) / 60))

        # Ferien-Faktor
        now = datetime.now()
        is_holiday = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= now,
            SchoolHolidays.end_datum >= now,
        ).count() > 0
        holiday_factor = 0.7 if is_holiday else 0.3

        return temp_factor * 0.4 + hum_factor * 0.3 + holiday_factor * 0.3

    # ═══════════════════════════════════════════════════════════════════════
    #  SEASONAL BASELINE CORRECTION (History Delta)
    # ═══════════════════════════════════════════════════════════════════════

    def _get_baseline_correction(self, raw_score: float) -> tuple[float, str]:
        """Saisonale Baseline-Korrektur aus internen Labordaten.

        Wenn externe Signale hoch, aber Historie für diese KW niedrig:
        → Score reduzieren (False Alarm Suppression).
        Nur bei extremen Abweichungen (>2σ) wird Alarm ausgelöst (Black Swan).
        """
        current_week = datetime.now().isocalendar()[1]

        historical = self.db.query(GanzimmunData).filter(
            GanzimmunData.anzahl_tests > 0,
        ).all()

        if len(historical) < 52:
            return raw_score, "Keine historische Baseline (zu wenig Daten)"

        # Saisonprofil aufbauen
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
            # Black Swan: extreme Abweichung → Signal vertrauen
            return raw_score, f"Black-Swan-Event: {explanation}"
        elif z_score < -1.0:
            # False Alarm Suppression
            suppression = min(0.3, abs(z_score) * 0.15)
            corrected = raw_score * (1 - suppression)
            return corrected, f"Skepsis-Korrektur ({suppression:.0%}): {explanation}"

        return raw_score, f"Normal: {explanation}"

    # ═══════════════════════════════════════════════════════════════════════
    #  ORDER VELOCITY FALLBACK
    # ═══════════════════════════════════════════════════════════════════════

    def _get_order_signal(self) -> tuple[float, str]:
        """Bestellgeschwindigkeit als Proxy für Infektionsgeschehen.

        CASE 1: Labordaten vorhanden → nutze Labdaten (data_source_mode=LAB_RESULTS)
        CASE 2: Keine Labdaten → Fallback auf Bestelldaten (ESTIMATED_FROM_ORDERS)
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
            # Bulk-Filter: > 5x Median ignorieren (Stockpiling)
            if order.datum >= one_week_ago:
                current_week_qty += qty
            else:
                prev_week_qty += qty

        if prev_week_qty > 0:
            velocity = (current_week_qty - prev_week_qty) / prev_week_qty
        else:
            velocity = 0.0

        # Velocity → Signal 0-1
        if velocity > 0.5:
            signal = 1.0   # Roter Alarm
        elif velocity > 0.2:
            signal = 0.7   # Gelber Alarm
        elif velocity > 0:
            signal = 0.3
        else:
            signal = 0.0

        return signal, "ESTIMATED_FROM_ORDERS"

    # ═══════════════════════════════════════════════════════════════════════
    #  CONFIDENCE (Uncertainty Quantification)
    # ═══════════════════════════════════════════════════════════════════════

    def _calculate_confidence(self, signals: list[float]) -> tuple[float, str]:
        """Konfidenz basierend auf Signal-Übereinstimmung.

        Hohe Übereinstimmung (niedrige Varianz) → hohe Konfidenz.
        Widersprüchliche Signale → niedrige Konfidenz.

        Formel: 1.0 - (StdDev(signals) * penalty_factor)
        """
        if not signals or len(signals) < 2:
            return 0.5, "Niedrig"

        std = float(np.std(signals))
        penalty_factor = 2.5
        confidence = max(0.0, min(1.0, 1.0 - std * penalty_factor))

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
    #  FEATURE ENGINEERING (für Meta-Learner)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_feature_vector(self, date: datetime, virus_typ: str) -> dict:
        """Feature-Vektor X_t für ein Datum erstellen."""
        day_of_year = date.timetuple().tm_yday

        return {
            'wastewater_signal': self._normalize_wastewater(virus_typ),
            'prophet_forecast': self._normalize_prophet_from_db(virus_typ),
            'shortage_count': 0.0,
            'google_trend_slope': self._normalize_trends(),
            'season_sin': math.sin(2 * math.pi * day_of_year / 365.25),
            'season_cos': math.cos(2 * math.pi * day_of_year / 365.25),
            'environment': self._normalize_environment(),
        }

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

    def train_meta_learner(self, virus_typ: str = 'Influenza A') -> dict:
        """XGBoost Meta-Learner auf historischen Daten trainieren.

        Zielvariable y: tatsächliche Inzidenz (um 14 Tage verschoben).
        Features: Abwasser, Trends, Wetter, Saisonalität.
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
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
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

    def _predict_meta_learner(self, virus_typ: str) -> float | None:
        """Meta-Learner-Vorhersage generieren."""
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

    # ═══════════════════════════════════════════════════════════════════════
    #  HAUPT-SCORE-BERECHNUNG
    # ═══════════════════════════════════════════════════════════════════════

    def compute_outbreak_score(
        self,
        virus_typ: str = 'Influenza A',
        shortage_signals: dict | None = None,
        prophet_result: dict | None = None,
    ) -> dict:
        """Ganz Immun Outbreak Score (0-100) berechnen.

        Kombiniert alle Signale mit Phase A (Heuristik) oder Phase B (Meta-Learner).
        """
        now = datetime.now()

        # 1. Alle Signale normalisieren
        sig_wastewater = self._normalize_wastewater(virus_typ)
        sig_shortage = self._normalize_shortage(shortage_signals)

        # Prophet: extern übergeben oder aus DB lesen
        if prophet_result:
            sig_prophet = self._normalize_prophet(prophet_result)
        else:
            sig_prophet = self._normalize_prophet_from_db(virus_typ)

        sig_trends = self._normalize_trends()
        sig_environment = self._normalize_environment()

        signals = [sig_wastewater, sig_shortage, sig_prophet, sig_trends, sig_environment]

        # 2. Order-Velocity Fallback
        order_signal, data_source_mode = self._get_order_signal()

        if data_source_mode == "ESTIMATED_FROM_ORDERS":
            raw_score = (
                0.15 * sig_wastewater +
                0.40 * order_signal +
                0.20 * sig_shortage +
                0.10 * sig_prophet +
                0.10 * sig_trends +
                0.05 * sig_environment
            ) * 100
            signals.append(order_signal)
        else:
            data_source_mode = "FULL"
            raw_score = (
                WEIGHT_WASTEWATER * sig_wastewater +
                WEIGHT_DRUG_SHORTAGE * sig_shortage +
                WEIGHT_PROPHET_TREND * sig_prophet +
                WEIGHT_SEARCH_TRENDS * sig_trends +
                WEIGHT_ENVIRONMENT * sig_environment
            ) * 100

        # 3. Phase bestimmen & Meta-Learner anwenden
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
            raw_score = 0.7 * meta_score + 0.3 * raw_score

        # 4. Baseline-Korrektur (historische Anomalie-Erkennung)
        corrected_score, baseline_explanation = self._get_baseline_correction(raw_score)

        # 5. Konfidenz
        confidence_numeric, confidence_label = self._calculate_confidence(signals)

        # 6. Risikostufe
        final_score = round(max(0, min(100, corrected_score)), 1)
        if final_score >= 65:
            risk_level = "RED"
        elif final_score >= 30:
            risk_level = "YELLOW"
        else:
            risk_level = "GREEN"

        # 7. Leading Indicator
        contributions = {
            'Abwasserlast': sig_wastewater * WEIGHT_WASTEWATER,
            'Lieferengpässe': sig_shortage * WEIGHT_DRUG_SHORTAGE,
            'Prophet-Prognose': sig_prophet * WEIGHT_PROPHET_TREND,
            'Suchtrends': sig_trends * WEIGHT_SEARCH_TRENDS,
            'Umweltfaktoren': sig_environment * WEIGHT_ENVIRONMENT,
        }
        if data_source_mode == "ESTIMATED_FROM_ORDERS":
            contributions['Bestellgeschwindigkeit'] = order_signal * 0.40

        leading = max(contributions, key=contributions.get)

        result = {
            "final_risk_score": final_score,
            "risk_level": risk_level,
            "leading_indicator": leading,
            "confidence_numeric": confidence_numeric,
            "confidence_level": confidence_label,
            "phase": phase,
            "data_source_mode": data_source_mode,
            "virus_typ": virus_typ,
            "baseline_correction": baseline_explanation,
            "component_scores": {
                "wastewater": round(sig_wastewater, 3),
                "drug_shortage": round(sig_shortage, 3),
                "prophet_trend": round(sig_prophet, 3),
                "search_trends": round(sig_trends, 3),
                "environment": round(sig_environment, 3),
                "order_velocity": round(order_signal, 3) if data_source_mode == "ESTIMATED_FROM_ORDERS" else None,
            },
            "contributions": {k: round(v * 100, 1) for k, v in contributions.items()},
            "timestamp": now.isoformat(),
        }

        # 8. Score persistieren
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
    #  AGGREGATION
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
                scores[virus] = {
                    "final_risk_score": 0,
                    "risk_level": "GREEN",
                    "error": str(e),
                }

        all_scores = [s['final_risk_score'] for s in scores.values() if 'final_risk_score' in s]
        overall = max(all_scores) if all_scores else 0

        return {
            "overall_score": round(overall, 1),
            "overall_risk_level": "RED" if overall >= 65 else "YELLOW" if overall >= 30 else "GREEN",
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
