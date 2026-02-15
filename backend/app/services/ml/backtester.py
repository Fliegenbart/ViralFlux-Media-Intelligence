"""BacktestService — Modell-Kalibrierung via historisches Backtesting.

Simuliert die RiskEngine für jeden Tag in der Kundenhistorie,
optimiert Gewichte via Ridge Regression und generiert LLM-Insights.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.preprocessing import StandardScaler
import logging

from app.models.database import (
    WastewaterAggregated,
    GanzimmunData,
    GoogleTrendsData,
    WeatherData,
    SchoolHolidays,
)

logger = logging.getLogger(__name__)


class BacktestService:
    """Backtesting auf historischen Kundendaten + Gewichtsoptimierung."""

    DEFAULT_WEIGHTS = {"bio": 0.35, "market": 0.35, "psycho": 0.10, "context": 0.20}

    def __init__(self, db: Session):
        self.db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Time-Travel: Signale an einem beliebigen historischen Datum berechnen
    # ─────────────────────────────────────────────────────────────────────────

    def _wastewater_at_date(self, target: datetime, virus_typ: str) -> float:
        """Normalisierte Viruslast an target_date (0-1)."""
        one_year_ago = target - timedelta(days=365)

        max_load = self.db.query(
            func.max(WastewaterAggregated.viruslast)
        ).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= one_year_ago,
            WastewaterAggregated.datum <= target,
        ).scalar() or 1.0

        current = self.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum <= target,
        ).order_by(WastewaterAggregated.datum.desc()).first()

        if not current or not current.viruslast:
            return 0.0
        return min(current.viruslast / max_load, 1.0)

    def _positivity_rate_at_date(self, target: datetime, virus_typ: str) -> float:
        """Positivrate der letzten 14 Tage relativ zu target_date."""
        start = target - timedelta(days=14)

        test_typ_map = {
            "Influenza A": "Influenza A",
            "Influenza B": "Influenza B",
            "SARS-CoV-2": "SARS-CoV-2",
            "RSV A": "RSV",
        }

        query = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= start,
            GanzimmunData.datum <= target,
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

    def _trends_at_date(self, target: datetime) -> float:
        """Google Trends Steigung an target_date (0-1)."""
        two_weeks_ago = target - timedelta(days=14)
        four_weeks_ago = target - timedelta(days=28)

        recent = self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= two_weeks_ago,
            GoogleTrendsData.datum <= target,
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

    def _weather_risk_at_date(self, target: datetime) -> float:
        """Wetter-Risiko an target_date (Temperatur, UV, Feuchte)."""
        latest = self.db.query(WeatherData).filter(
            WeatherData.datum <= target,
        ).order_by(WeatherData.datum.desc()).limit(5).all()

        if not latest:
            return 0.3

        avg_temp = sum(w.temperatur for w in latest) / len(latest)
        avg_uv = sum(w.uv_index or 0 for w in latest) / len(latest)
        avg_humidity = sum(w.luftfeuchtigkeit or 60 for w in latest) / len(latest)

        temp_factor = max(0, min(1, (20 - avg_temp) / 25))
        uv_factor = max(0, min(1, (8 - avg_uv) / 8))
        humidity_factor = max(0, min(1, avg_humidity / 100))

        return temp_factor * 0.4 + uv_factor * 0.35 + humidity_factor * 0.25

    def _school_start_at_date(self, target: datetime) -> bool:
        """True wenn Ferien in den letzten 7 Tagen vor target_date endeten."""
        week_ago = target - timedelta(days=7)
        count = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.end_datum >= week_ago,
            SchoolHolidays.end_datum <= target,
        ).count()
        return count > 0

    def _compute_sub_scores_at_date(
        self, target: datetime, virus_typ: str
    ) -> dict[str, float]:
        """Berechnet die 4 Dimensions-Scores an einem historischen Datum."""
        wastewater = self._wastewater_at_date(target, virus_typ)
        positivity = self._positivity_rate_at_date(target, virus_typ)
        trends = self._trends_at_date(target)
        weather = self._weather_risk_at_date(target)
        school_start = self._school_start_at_date(target)

        # BIO = wastewater + lab positivity
        bio = min(wastewater * 0.5 + positivity * 5.0 * 0.5, 1.0)

        # MARKET = placeholder (order velocity needs customer-specific data)
        market = 0.0

        # PSYCHO = Google Trends
        psycho = trends

        # CONTEXT = weather (+ school_start boost)
        context = weather
        if school_start:
            context = min(context * 1.3, 1.0)

        return {
            "bio": round(bio, 4),
            "market": round(market, 4),
            "psycho": round(psycho, 4),
            "context": round(context, 4),
            "school_start": school_start,
            "wastewater_raw": round(wastewater, 4),
            "weather_raw": round(weather, 4),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Haupt-Kalibrierung
    # ─────────────────────────────────────────────────────────────────────────

    def run_calibration(
        self,
        customer_df: pd.DataFrame,
        virus_typ: str = "Influenza A",
    ) -> dict:
        """Backtesting + Ridge Regression Gewichtsoptimierung.

        customer_df: Spalten 'datum' und 'menge' (Bestellmenge).
        Returns: Metrics, optimierte Gewichte, Chart-Daten, LLM-Insight.
        """
        logger.info(f"Starte Kalibrierung: {len(customer_df)} Zeilen, Virus={virus_typ}")

        customer_df["datum"] = pd.to_datetime(customer_df["datum"])
        customer_df = customer_df.sort_values("datum").reset_index(drop=True)

        simulation_rows = []

        for _, row in customer_df.iterrows():
            sim_date = row["datum"]
            real_qty = float(row["menge"])

            try:
                scores = self._compute_sub_scores_at_date(sim_date, virus_typ)
                simulation_rows.append({
                    "date": sim_date.strftime("%Y-%m-%d"),
                    "real_qty": real_qty,
                    "bio": scores["bio"],
                    "market": scores["market"],
                    "psycho": scores["psycho"],
                    "context": scores["context"],
                    "school_start": scores["school_start"],
                })
            except Exception as e:
                logger.warning(f"Simulation für {sim_date} fehlgeschlagen: {e}")
                continue

        if not simulation_rows:
            return {"error": "Keine Datenpunkte konnten simuliert werden."}

        df_sim = pd.DataFrame(simulation_rows)

        # ── Ridge Regression: Gewichtsoptimierung ───────────────────────────
        feature_cols = ["bio", "market", "psycho", "context"]
        X = df_sim[feature_cols].values
        y = df_sim["real_qty"].values

        # Standardisierung für bessere Regression
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = Ridge(alpha=1.0, fit_intercept=True)
        model.fit(X_scaled, y)

        y_pred = model.predict(X_scaled)
        r2 = r2_score(y, y_pred)
        mae = mean_absolute_error(y, y_pred)

        # Koeffizienten auf Original-Skala zurückrechnen + normalisieren
        raw_coefs = np.abs(model.coef_)
        total = raw_coefs.sum()
        if total > 0:
            weights_pct = {
                col: round(float(raw_coefs[i] / total), 2)
                for i, col in enumerate(feature_cols)
            }
        else:
            weights_pct = dict(self.DEFAULT_WEIGHTS)

        # ── Predicted-Kurve für Chart normalisieren ─────────────────────────
        # Skaliere y_pred auf gleichen Bereich wie y für Vergleichbarkeit
        if y.max() > 0:
            y_pred_scaled = y_pred * (y.mean() / y_pred.mean()) if y_pred.mean() > 0 else y_pred
        else:
            y_pred_scaled = y_pred

        chart_data = []
        for i, row_dict in enumerate(simulation_rows):
            chart_data.append({
                "date": row_dict["date"],
                "real_qty": row_dict["real_qty"],
                "predicted_qty": round(float(y_pred_scaled[i]), 1),
                "bio": row_dict["bio"],
                "psycho": row_dict["psycho"],
                "context": row_dict["context"],
            })

        # ── Korrelation (Pearson) ───────────────────────────────────────────
        correlation = float(np.corrcoef(y, y_pred)[0, 1]) if len(y) > 2 else 0.0

        # ── LLM Insight ─────────────────────────────────────────────────────
        llm_insight = self._generate_llm_insight(
            weights_pct, r2, correlation, mae, len(df_sim), virus_typ
        )

        result = {
            "metrics": {
                "r2_score": round(r2, 3),
                "correlation": round(correlation, 3),
                "correlation_pct": round(abs(correlation) * 100, 1),
                "mae": round(mae, 1),
                "data_points": len(df_sim),
                "date_range": {
                    "start": df_sim["date"].min(),
                    "end": df_sim["date"].max(),
                },
            },
            "default_weights": dict(self.DEFAULT_WEIGHTS),
            "optimized_weights": weights_pct,
            "llm_insight": llm_insight,
            "chart_data": chart_data,
        }

        logger.info(
            f"Kalibrierung abgeschlossen: R²={r2:.3f}, "
            f"Korrelation={correlation:.3f}, Gewichte={weights_pct}"
        )
        return result

    def _generate_llm_insight(
        self,
        weights: dict,
        r2: float,
        correlation: float,
        mae: float,
        n_samples: int,
        virus_typ: str,
    ) -> str:
        """LLM-Erklärung der Kalibrierungsergebnisse via Ollama."""
        dominant = max(weights, key=weights.get)
        weakest = min(weights, key=weights.get)

        factor_names = {
            "bio": "Biologische Daten (RKI-Abwasser + Laborpositivrate)",
            "market": "Marktdaten (Lieferengpässe + Bestelltrends)",
            "psycho": "Suchverhalten (Google Trends)",
            "context": "Kontextfaktoren (Wetter + Schulferien)",
        }

        prompt = f"""Du bist ein Senior Data Scientist bei LabPulse Pro.
Du hast eine Regressionsanalyse der historischen Bestellungen eines Labors durchgeführt.

Harte Fakten:
- Analysierter Erreger: {virus_typ}
- Anzahl analysierter Datenpunkte: {n_samples}
- Modell-Qualität (R²): {r2:.2f} (1.0 = perfekt, 0.0 = kein Zusammenhang)
- Korrelation zwischen Vorhersage und Realität: {correlation:.1%}
- Durchschnittliche Abweichung (MAE): {mae:.0f} Einheiten

Ermittelte Einflussfaktoren auf die Bestellungen dieses Labors:
- {factor_names['bio']}: {weights['bio']*100:.0f}% Wichtigkeit
- {factor_names['market']}: {weights['market']*100:.0f}% Wichtigkeit
- {factor_names['psycho']}: {weights['psycho']*100:.0f}% Wichtigkeit
- {factor_names['context']}: {weights['context']*100:.0f}% Wichtigkeit

Stärkster Faktor: {factor_names[dominant]}
Schwächster Faktor: {factor_names[weakest]}

Schreibe eine professionelle Zusammenfassung (3-4 Sätze, auf Deutsch) für den Laborleiter.
Erkläre, worauf seine Bestellungen am stärksten reagiert haben und was weniger relevant war.
Schlage vor, das Modell mit diesen neuen Gewichten zu kalibrieren.
Verwende einen sachlichen, vertrauenswürdigen Ton."""

        try:
            from app.services.llm.ollama_service import OllamaRecommendationService
            llm = OllamaRecommendationService(self.db)
            return llm._call_ollama(prompt)
        except Exception as e:
            logger.warning(f"LLM Insight fehlgeschlagen: {e}")
            return (
                f"Die Analyse von {n_samples} Datenpunkten zeigt eine "
                f"{abs(correlation)*100:.0f}%ige Korrelation zwischen LabPulse-Signalen "
                f"und Ihren tatsächlichen Bestellungen. Der stärkste Einflussfaktor "
                f"ist \"{factor_names[dominant]}\" ({weights[dominant]*100:.0f}%). "
                f"Wir empfehlen, das Modell mit diesen optimierten Gewichten zu kalibrieren."
            )
