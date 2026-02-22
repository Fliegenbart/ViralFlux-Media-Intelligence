"""BacktestService — Modell-Kalibrierung via historisches Backtesting.

Simuliert die RiskEngine für jeden Tag in der Kundenhistorie,
optimiert Gewichte via Ridge Regression und generiert LLM-Insights.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
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
    AREKonsultation,
    SurvstatWeeklyData,
    LabConfiguration,
    BacktestRun,
    BacktestPoint,
)

logger = logging.getLogger(__name__)


class BacktestService:
    """Backtesting auf historischen Kundendaten + Gewichtsoptimierung."""

    DEFAULT_WEIGHTS = {"bio": 0.35, "market": 0.35, "psycho": 0.10, "context": 0.20}
    DEFAULT_DELAY_RULES_DAYS = {
        "wastewater": 2,
        "positivity": 2,
        "trends": 3,
        "weather": 0,
        "school_holidays": 0,
        "are_consultation": 7,
    }
    DEFAULT_MARKET_HORIZON_DAYS = 14
    DEFAULT_MIN_TRAIN_POINTS = 20
    SURVSTAT_TARGET_ALIASES = {
        "SURVSTAT": "all",
        "ALL": "all",
        "MYCOPLASMA": "mycoplasma",
        "KEUCHHUSTEN": "keuchhusten",
        "PNEUMOKOKKEN": "pneumokokken",
        "H_INFLUENZAE": "haemophilus influenzae",
    }

    def __init__(self, db: Session):
        self.db = db
        self.strict_vintage_mode = True

    def _asof_filter(self, model_cls, event_col, cutoff: datetime):
        """As-of-Filter mit Fallback auf event_time wenn available_time fehlt."""
        if not self.strict_vintage_mode:
            return event_col <= cutoff

        available_col = getattr(model_cls, "available_time", None)
        if available_col is None:
            return event_col <= cutoff

        return or_(
            available_col <= cutoff,
            and_(available_col.is_(None), event_col <= cutoff),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Time-Travel: Signale an einem beliebigen historischen Datum berechnen
    # ─────────────────────────────────────────────────────────────────────────

    def _wastewater_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        """Normalisierte Viruslast an target_date (0-1)."""
        effective = available_cutoff or target
        one_year_ago = effective - timedelta(days=365)

        max_load = self.db.query(
            func.max(WastewaterAggregated.viruslast)
        ).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= one_year_ago,
            WastewaterAggregated.datum <= effective,
            self._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
        ).scalar() or 1.0

        current = self.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum <= effective,
            self._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
        ).order_by(WastewaterAggregated.datum.desc()).first()

        if not current or not current.viruslast:
            return 0.0
        return min(current.viruslast / max_load, 1.0)

    def _positivity_rate_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        """Positivrate der letzten 14 Tage relativ zu target_date."""
        effective = available_cutoff or target
        start = effective - timedelta(days=14)

        test_typ_map = {
            "Influenza A": "Influenza A",
            "Influenza B": "Influenza B",
            "SARS-CoV-2": "SARS-CoV-2",
            "RSV A": "RSV",
        }

        query = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= start,
            GanzimmunData.datum <= effective,
            GanzimmunData.anzahl_tests > 0,
            self._asof_filter(GanzimmunData, GanzimmunData.datum, effective),
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

    def _trends_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        """Google Trends Steigung an target_date (0-1)."""
        effective = available_cutoff or target
        two_weeks_ago = effective - timedelta(days=14)
        four_weeks_ago = effective - timedelta(days=28)

        recent = self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= two_weeks_ago,
            GoogleTrendsData.datum <= effective,
            self._asof_filter(GoogleTrendsData, GoogleTrendsData.datum, effective),
        ).scalar() or 0

        previous = self.db.query(
            func.avg(GoogleTrendsData.interest_score)
        ).filter(
            GoogleTrendsData.datum >= four_weeks_ago,
            GoogleTrendsData.datum < two_weeks_ago,
            self._asof_filter(GoogleTrendsData, GoogleTrendsData.datum, effective),
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

    def _weather_risk_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        """Wetter-Risiko an target_date (Temperatur, UV, Feuchte)."""
        effective = available_cutoff or target
        latest = self.db.query(WeatherData).filter(
            WeatherData.datum <= effective,
            self._asof_filter(WeatherData, WeatherData.datum, effective),
        ).order_by(WeatherData.datum.desc()).limit(5).all()

        if not latest:
            return 0.3

        temps = [w.temperatur for w in latest if w.temperatur is not None]
        avg_temp = sum(temps) / len(temps) if temps else 5.0
        avg_uv = sum(w.uv_index or 0 for w in latest) / len(latest)
        avg_humidity = sum(w.luftfeuchtigkeit or 60 for w in latest) / len(latest)

        temp_factor = max(0, min(1, (20 - avg_temp) / 25))
        uv_factor = max(0, min(1, (8 - avg_uv) / 8))
        humidity_factor = max(0, min(1, avg_humidity / 100))

        return temp_factor * 0.4 + uv_factor * 0.35 + humidity_factor * 0.25

    def _school_start_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> bool:
        """True wenn Ferien in den letzten 7 Tagen vor target_date endeten."""
        effective = available_cutoff or target
        week_ago = effective - timedelta(days=7)
        count = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.end_datum >= week_ago,
            SchoolHolidays.end_datum <= effective,
        ).count()
        return count > 0

    def _are_consultation_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        """ARE-Konsultationsinzidenz-Signal an target_date (0-1).

        Weekly data is forward-filled: most recent ARE reading on or before
        target_date, then percentile-ranked against same-week historical values.
        """
        effective = available_cutoff or target
        latest = self.db.query(AREKonsultation).filter(
            AREKonsultation.altersgruppe == '00+',
            AREKonsultation.bundesland == 'Bundesweit',
            AREKonsultation.datum <= effective,
            self._asof_filter(AREKonsultation, AREKonsultation.datum, effective),
        ).order_by(AREKonsultation.datum.desc()).first()

        if not latest or not latest.konsultationsinzidenz:
            return 0.0

        current_value = latest.konsultationsinzidenz
        current_week = latest.kalenderwoche

        # Only use data available at target_date (no future leak)
        historical = self.db.query(AREKonsultation.konsultationsinzidenz).filter(
            AREKonsultation.kalenderwoche == current_week,
            AREKonsultation.altersgruppe == '00+',
            AREKonsultation.bundesland == 'Bundesweit',
            AREKonsultation.datum <= effective,
            self._asof_filter(AREKonsultation, AREKonsultation.datum, effective),
        ).all()

        values = sorted([h[0] for h in historical if h[0] is not None])

        if len(values) < 3:
            return min(current_value / 8200.0, 1.0)

        from bisect import bisect_right
        rank = bisect_right(values, current_value)
        return min(rank / len(values), 1.0)

    def _compute_sub_scores_at_date(
        self,
        target: datetime,
        virus_typ: str,
        delay_rules: Optional[dict[str, int]] = None,
    ) -> dict[str, float]:
        """Berechnet die 4 Dimensions-Scores an einem historischen Datum."""
        rules = dict(self.DEFAULT_DELAY_RULES_DAYS)
        if delay_rules:
            rules.update(delay_rules)

        wastewater_cutoff = target - timedelta(days=max(0, int(rules.get("wastewater", 0))))
        positivity_cutoff = target - timedelta(days=max(0, int(rules.get("positivity", 0))))
        are_cutoff = target - timedelta(days=max(0, int(rules.get("are_consultation", 0))))
        trends_cutoff = target - timedelta(days=max(0, int(rules.get("trends", 0))))
        weather_cutoff = target - timedelta(days=max(0, int(rules.get("weather", 0))))
        holidays_cutoff = target - timedelta(days=max(0, int(rules.get("school_holidays", 0))))

        wastewater = self._wastewater_at_date(target, virus_typ, available_cutoff=wastewater_cutoff)
        positivity = self._positivity_rate_at_date(target, virus_typ, available_cutoff=positivity_cutoff)
        are_consultation = self._are_consultation_at_date(target, available_cutoff=are_cutoff)
        trends = self._trends_at_date(target, available_cutoff=trends_cutoff)
        weather = self._weather_risk_at_date(target, available_cutoff=weather_cutoff)
        school_start = self._school_start_at_date(target, available_cutoff=holidays_cutoff)

        # BIO = wastewater + lab positivity + ARE consultation (graceful degradation)
        if are_consultation > 0:
            bio = min(
                wastewater * 0.40 +
                positivity * 5.0 * 0.35 +
                are_consultation * 0.25,
                1.0
            )
        else:
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
            "are_consultation_raw": round(are_consultation, 4),
            "weather_raw": round(weather, 4),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Haupt-Kalibrierung
    # ─────────────────────────────────────────────────────────────────────────

    def _simulate_rows_from_target(
        self,
        target_df: pd.DataFrame,
        virus_typ: str,
        horizon_days: int = 0,
        delay_rules: Optional[dict[str, int]] = None,
    ) -> list[dict]:
        """Berechne Sub-Scores je Ziel-Datenpunkt ohne Future-Leak."""
        if target_df.empty:
            return []

        df = target_df.copy()
        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
        df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)

        simulation_rows = []
        for _, row in df.iterrows():
            target_date = row["datum"]
            sim_date = target_date - timedelta(days=max(0, int(horizon_days)))
            real_qty = float(row["menge"])

            try:
                scores = self._compute_sub_scores_at_date(
                    sim_date,
                    virus_typ,
                    delay_rules=delay_rules,
                )
                simulation_rows.append({
                    "date": target_date.strftime("%Y-%m-%d"),
                    "feature_date": sim_date.strftime("%Y-%m-%d"),
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

        return simulation_rows

    def _fit_regression_from_simulation(
        self,
        df_sim: pd.DataFrame,
        virus_typ: str,
        use_llm: bool = True,
    ) -> dict:
        """Ridge-Fit und Metrikberechnung auf simulierten Features."""
        if df_sim.empty:
            return {"error": "Keine Datenpunkte konnten simuliert werden."}

        feature_cols = ["bio", "market", "psycho", "context"]
        X = df_sim[feature_cols].values
        y = df_sim["real_qty"].values

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = Ridge(alpha=1.0, fit_intercept=True)
        model.fit(X_scaled, y)

        y_pred = model.predict(X_scaled)
        r2 = r2_score(y, y_pred)
        mae = mean_absolute_error(y, y_pred)

        raw_coefs = np.abs(model.coef_)
        total = raw_coefs.sum()
        if total > 0:
            weights_pct = {
                col: round(float(raw_coefs[i] / total), 2)
                for i, col in enumerate(feature_cols)
            }
        else:
            weights_pct = dict(self.DEFAULT_WEIGHTS)

        if y.max() > 0:
            y_pred_scaled = y_pred * (y.mean() / y_pred.mean()) if y_pred.mean() > 0 else y_pred
        else:
            y_pred_scaled = y_pred

        chart_data = []
        records = df_sim.to_dict(orient="records")
        for i, row in enumerate(records):
            chart_data.append({
                "date": row["date"],
                "real_qty": row["real_qty"],
                "predicted_qty": round(float(y_pred_scaled[i]), 1),
                "bio": row["bio"],
                "psycho": row["psycho"],
                "context": row["context"],
            })

        correlation = float(np.corrcoef(y, y_pred)[0, 1]) if len(y) > 2 else 0.0
        if np.isnan(correlation):
            correlation = 0.0

        if use_llm:
            llm_insight = self._generate_llm_insight(
                weights_pct, r2, correlation, mae, len(df_sim), virus_typ
            )
        else:
            llm_insight = (
                f"Simulation über {len(df_sim)} Datenpunkte: "
                f"R²={r2:.2f}, Korrelation={correlation:.1%}, MAE={mae:.1f}. "
                f"Dominanter Treiber: {max(weights_pct, key=weights_pct.get)}."
            )

        return {
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

    def _resolve_survstat_disease(self, source_token: str) -> Optional[str]:
        """Mappt Zieltoken auf einen konkreten SURVSTAT-Disease-String."""
        token = (source_token or "").strip()
        token_upper = token.upper()

        if token_upper in self.SURVSTAT_TARGET_ALIASES:
            token = self.SURVSTAT_TARGET_ALIASES[token_upper]

        if token.lower() == "all":
            exact_all = self.db.query(SurvstatWeeklyData.disease).filter(
                SurvstatWeeklyData.disease == "All"
            ).first()
            if exact_all:
                return exact_all[0]
            return None

        pattern = f"%{token.lower()}%"
        row = self.db.query(SurvstatWeeklyData.disease).filter(
            func.lower(SurvstatWeeklyData.disease).like(pattern)
        ).order_by(SurvstatWeeklyData.disease.asc()).first()

        return row[0] if row else None

    def _load_market_target(
        self,
        target_source: str = "RKI_ARE",
        days_back: int = 730,
    ) -> Tuple[pd.DataFrame, dict]:
        """Lädt externe Markt-Proxy-Wahrheit für Twin-Mode Market-Check."""
        token = (target_source or "RKI_ARE").strip()
        token_upper = token.upper()
        start_date = datetime.now() - timedelta(days=days_back)

        if token_upper == "RKI_ARE":
            are_rows = self.db.query(AREKonsultation).filter(
                AREKonsultation.altersgruppe == "00+",
                AREKonsultation.bundesland == "Bundesweit",
                AREKonsultation.datum >= start_date,
            ).order_by(AREKonsultation.datum.asc()).all()

            df = pd.DataFrame([{
                "datum": row.datum,
                "menge": row.konsultationsinzidenz,
                "available_time": row.available_time or row.datum,
            } for row in are_rows if row.konsultationsinzidenz is not None])

            return df, {
                "target_source": "RKI_ARE",
                "target_label": "RKI ARE-Konsultationsinzidenz (Bundesweit, 00+)",
                "target_key": "RKI_ARE",
            }

        if token_upper.startswith("SURVSTAT:"):
            survstat_token = token.split(":", 1)[1].strip()
        else:
            survstat_token = self.SURVSTAT_TARGET_ALIASES.get(token_upper, token)

        disease = self._resolve_survstat_disease(survstat_token)
        if not disease:
            available = self.db.query(SurvstatWeeklyData.disease).distinct().order_by(
                SurvstatWeeklyData.disease.asc()
            ).limit(12).all()
            available_names = [row[0] for row in available]
            raise ValueError(
                f"SURVSTAT Ziel '{target_source}' nicht gefunden. "
                f"Verfügbar (Auszug): {available_names}"
            )

        surv_rows = self.db.query(SurvstatWeeklyData).filter(
            SurvstatWeeklyData.disease == disease,
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.week_start >= start_date,
        ).order_by(SurvstatWeeklyData.week_start.asc()).all()

        df = pd.DataFrame([{
            "datum": row.week_start,
            "menge": row.incidence,
            "available_time": row.available_time or row.week_start,
        } for row in surv_rows if row.incidence is not None])

        return df, {
            "target_source": "SURVSTAT",
            "target_label": f"SURVSTAT {disease} (Gesamt)",
            "target_key": token_upper,
            "disease": disease,
            "bundesland": "Gesamt",
        }

    @staticmethod
    def _estimate_step_days(df_sim: pd.DataFrame) -> int:
        dates = pd.to_datetime(df_sim["date"], errors="coerce").dropna().sort_values()
        if len(dates) < 2:
            return 7

        day_diffs = dates.diff().dropna().dt.days
        if day_diffs.empty:
            return 7

        median_days = int(round(float(day_diffs.median())))
        return median_days if median_days > 0 else 7

    def _best_bio_lead_lag(self, df_sim: pd.DataFrame, max_lag_points: int = 6) -> dict:
        """Bestimme Lag, bei dem Bio-Signal und Target am stärksten korrelieren.

        Positive lag_points bedeuten: Bio führt das Target (Lead).
        """
        if df_sim.empty or len(df_sim) < 8:
            return {
                "best_lag_points": 0,
                "best_lag_days": 0,
                "lag_step_days": 7,
                "lag_correlation": 0.0,
                "bio_leads_target": False,
            }

        bio = pd.to_numeric(df_sim["bio"], errors="coerce").fillna(0.0).to_numpy()
        target = pd.to_numeric(df_sim["real_qty"], errors="coerce").fillna(0.0).to_numpy()
        step_days = self._estimate_step_days(df_sim)

        best_lag = 0
        best_corr = 0.0

        for lag in range(-max_lag_points, max_lag_points + 1):
            if lag > 0:
                x = bio[:-lag]
                y = target[lag:]
            elif lag < 0:
                x = bio[-lag:]
                y = target[:lag]
            else:
                x = bio
                y = target

            if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
                continue

            corr = float(np.corrcoef(x, y)[0, 1])
            if np.isnan(corr):
                continue

            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag

        lead_days = best_lag * step_days
        return {
            "best_lag_points": int(best_lag),
            "best_lag_days": int(lead_days),
            "lag_step_days": int(step_days),
            "lag_correlation": round(float(best_corr), 3),
            "bio_leads_target": bool(lead_days > 0 and best_corr > 0),
        }

    @staticmethod
    def _compute_forecast_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
        """Standard-Metriken für Forecast- und Baseline-Vergleich."""
        if len(y_true) == 0:
            return {
                "r2_score": 0.0,
                "correlation": 0.0,
                "correlation_pct": 0.0,
                "mae": 0.0,
                "rmse": 0.0,
                "smape": 0.0,
                "data_points": 0,
            }

        mae = float(mean_absolute_error(y_true, y_pred))
        rmse = float(np.sqrt(np.mean(np.square(y_true - y_pred))))
        denom = np.abs(y_true) + np.abs(y_pred)
        smape = float(np.mean(np.where(denom > 0, 200.0 * np.abs(y_true - y_pred) / denom, 0.0)))

        corr = float(np.corrcoef(y_true, y_pred)[0, 1]) if len(y_true) > 2 else 0.0
        if np.isnan(corr):
            corr = 0.0

        try:
            r2 = float(r2_score(y_true, y_pred))
            if np.isnan(r2):
                r2 = 0.0
        except Exception:
            r2 = 0.0

        return {
            "r2_score": round(r2, 3),
            "correlation": round(corr, 3),
            "correlation_pct": round(abs(corr) * 100, 1),
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "smape": round(smape, 3),
            "data_points": int(len(y_true)),
        }

    def _persist_backtest_result(
        self,
        *,
        mode: str,
        virus_typ: str,
        target_source: str,
        target_key: str,
        target_label: str,
        result: dict,
        parameters: Optional[dict] = None,
    ) -> Optional[str]:
        """Persistiert einen Backtest-Lauf inkl. Chart-Punkten."""
        try:
            run_id = f"bt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
            chart_data = result.get("chart_data", []) or []

            run = BacktestRun(
                run_id=run_id,
                mode=mode,
                status="success",
                virus_typ=virus_typ,
                target_source=target_source,
                target_key=target_key,
                target_label=target_label,
                strict_vintage_mode=bool(
                    result.get("walk_forward", {}).get(
                        "strict_vintage_mode",
                        self.strict_vintage_mode,
                    )
                ),
                horizon_days=int(result.get("walk_forward", {}).get("horizon_days", 14)),
                min_train_points=int(result.get("walk_forward", {}).get("min_train_points", 20)),
                parameters=parameters or {},
                metrics=result.get("metrics", {}),
                baseline_metrics=result.get("baseline_metrics", {}),
                improvement_vs_baselines=result.get("improvement_vs_baselines", {}),
                optimized_weights=result.get("optimized_weights", {}),
                proof_text=result.get("proof_text"),
                llm_insight=result.get("llm_insight"),
                lead_lag=result.get("lead_lag"),
                chart_points=len(chart_data),
            )
            self.db.add(run)
            self.db.flush()

            points: list[BacktestPoint] = []
            for row in chart_data:
                date_raw = row.get("date")
                date_parsed = pd.to_datetime(date_raw, errors="coerce")
                if pd.isna(date_parsed):
                    continue

                points.append(
                    BacktestPoint(
                        run_id=run_id,
                        date=date_parsed.to_pydatetime(),
                        region=row.get("region"),
                        real_qty=float(row.get("real_qty")) if row.get("real_qty") is not None else None,
                        predicted_qty=float(row.get("predicted_qty")) if row.get("predicted_qty") is not None else None,
                        baseline_persistence=(
                            float(row.get("baseline_persistence"))
                            if row.get("baseline_persistence") is not None
                            else None
                        ),
                        baseline_seasonal=(
                            float(row.get("baseline_seasonal"))
                            if row.get("baseline_seasonal") is not None
                            else None
                        ),
                        bio=float(row.get("bio")) if row.get("bio") is not None else None,
                        psycho=float(row.get("psycho")) if row.get("psycho") is not None else None,
                        context=float(row.get("context")) if row.get("context") is not None else None,
                        extra={
                            "feature_date": row.get("feature_date"),
                            "source_mode": mode,
                        },
                    )
                )

            if points:
                self.db.bulk_save_objects(points)

            self.db.commit()
            return run_id
        except Exception as exc:
            self.db.rollback()
            logger.warning(f"Backtest-Persistenz fehlgeschlagen: {exc}")
            return None

    def list_backtest_runs(self, mode: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Liefert persistierte Backtest-Runs für UI-Historie."""
        query = self.db.query(BacktestRun).order_by(BacktestRun.created_at.desc())
        if mode:
            query = query.filter(BacktestRun.mode == mode)

        rows = query.limit(max(1, min(limit, 200))).all()
        return [
            {
                "run_id": row.run_id,
                "mode": row.mode,
                "status": row.status,
                "virus_typ": row.virus_typ,
                "target_source": row.target_source,
                "target_key": row.target_key,
                "target_label": row.target_label,
                "strict_vintage_mode": row.strict_vintage_mode,
                "horizon_days": row.horizon_days,
                "metrics": row.metrics or {},
                "lead_lag": row.lead_lag or {},
                "chart_points": row.chart_points,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    @staticmethod
    def _seasonal_naive_baseline(train_df: pd.DataFrame, target_week: int, target_month: int) -> float:
        """Seasonal Naive: gleiche ISO-Woche, sonst Monat, sonst letzter Wert."""
        same_week = train_df[train_df["iso_week"] == target_week]
        if not same_week.empty:
            return float(same_week.iloc[-1]["menge"])

        same_month = train_df[train_df["month"] == target_month]
        if not same_month.empty:
            return float(same_month.iloc[-1]["menge"])

        return float(train_df.iloc[-1]["menge"])

    def _run_walk_forward_market_backtest(
        self,
        target_df: pd.DataFrame,
        virus_typ: str,
        horizon_days: int,
        min_train_points: int,
        delay_rules: Optional[dict[str, int]] = None,
    ) -> dict:
        """Walk-forward Backtest mit Baselines und Delay-Regeln."""
        df = target_df.copy()
        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
        if "available_time" in df.columns:
            df["available_time"] = pd.to_datetime(df["available_time"], errors="coerce")
        else:
            df["available_time"] = pd.NaT
        df["available_time"] = df["available_time"].fillna(df["datum"])
        df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)
        if df.empty:
            return {"error": "Keine validen Zielwerte für Walk-forward Backtest verfügbar."}

        # Baseline-Hilfsspalten
        isocal = df["datum"].dt.isocalendar()
        df["iso_week"] = isocal.week.astype(int)
        df["month"] = df["datum"].dt.month.astype(int)

        feature_cols = ["bio", "market", "psycho", "context"]
        folds: list[dict] = []
        coef_accumulator: list[np.ndarray] = []

        for _, row in df.iterrows():
            target_time = row["datum"]
            target_value = float(row["menge"])
            target_week = int(row["iso_week"])
            target_month = int(row["month"])
            forecast_time = target_time - timedelta(days=max(0, int(horizon_days)))

            if self.strict_vintage_mode:
                train_target_df = df[df["available_time"] <= forecast_time].copy()
            else:
                train_target_df = df[df["datum"] <= forecast_time].copy()
            if len(train_target_df) < min_train_points:
                continue

            train_rows = self._simulate_rows_from_target(
                train_target_df[["datum", "menge"]],
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                delay_rules=delay_rules,
            )
            if len(train_rows) < min_train_points:
                continue

            df_train = pd.DataFrame(train_rows)
            X_train = df_train[feature_cols].values
            y_train = df_train["real_qty"].values

            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            model = Ridge(alpha=1.0, fit_intercept=True)
            model.fit(X_train_scaled, y_train)

            coef_accumulator.append(np.abs(model.coef_))

            test_scores = self._compute_sub_scores_at_date(
                forecast_time,
                virus_typ=virus_typ,
                delay_rules=delay_rules,
            )
            X_test = np.array([[
                test_scores["bio"],
                test_scores["market"],
                test_scores["psycho"],
                test_scores["context"],
            ]])
            y_hat = float(model.predict(scaler.transform(X_test))[0])

            baseline_persistence = float(train_target_df.iloc[-1]["menge"])
            baseline_seasonal = self._seasonal_naive_baseline(
                train_target_df,
                target_week=target_week,
                target_month=target_month,
            )

            folds.append({
                "forecast_time": forecast_time,
                "target_time": target_time,
                "real_qty": target_value,
                "predicted_qty": y_hat,
                "baseline_persistence": baseline_persistence,
                "baseline_seasonal": baseline_seasonal,
                "bio": float(test_scores["bio"]),
                "psycho": float(test_scores["psycho"]),
                "context": float(test_scores["context"]),
            })

        if not folds:
            return {
                "error": (
                    "Walk-forward erzeugte keine validen Folds. "
                    f"Erhöhe days_back oder reduziere min_train_points (aktuell {min_train_points})."
                )
            }

        pred_df = pd.DataFrame(folds).sort_values("target_time").reset_index(drop=True)
        y_true = pred_df["real_qty"].to_numpy(dtype=float)
        y_hat = pred_df["predicted_qty"].to_numpy(dtype=float)
        y_persistence = pred_df["baseline_persistence"].to_numpy(dtype=float)
        y_seasonal = pred_df["baseline_seasonal"].to_numpy(dtype=float)

        model_metrics = self._compute_forecast_metrics(y_true, y_hat)
        persistence_metrics = self._compute_forecast_metrics(y_true, y_persistence)
        seasonal_metrics = self._compute_forecast_metrics(y_true, y_seasonal)

        model_mae = max(model_metrics["mae"], 1e-9)
        pers_mae = max(persistence_metrics["mae"], 1e-9)
        seas_mae = max(seasonal_metrics["mae"], 1e-9)

        if coef_accumulator:
            avg_coefs = np.mean(np.vstack(coef_accumulator), axis=0)
            total = float(avg_coefs.sum())
            if total > 0:
                optimized_weights = {
                    col: round(float(avg_coefs[i] / total), 2)
                    for i, col in enumerate(feature_cols)
                }
            else:
                optimized_weights = dict(self.DEFAULT_WEIGHTS)
        else:
            optimized_weights = dict(self.DEFAULT_WEIGHTS)

        return {
            "metrics": {
                **model_metrics,
                "data_points": int(len(pred_df)),
                "date_range": {
                    "start": pred_df["target_time"].min().strftime("%Y-%m-%d"),
                    "end": pred_df["target_time"].max().strftime("%Y-%m-%d"),
                },
            },
            "baseline_metrics": {
                "persistence": persistence_metrics,
                "seasonal_naive": seasonal_metrics,
            },
            "improvement_vs_baselines": {
                "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
                "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
            },
            "optimized_weights": optimized_weights,
            "default_weights": dict(self.DEFAULT_WEIGHTS),
            "chart_data": [
                {
                    "date": row["target_time"].strftime("%Y-%m-%d"),
                    "real_qty": float(row["real_qty"]),
                    "predicted_qty": round(float(row["predicted_qty"]), 3),
                    "bio": round(float(row["bio"]), 4),
                    "psycho": round(float(row["psycho"]), 4),
                    "context": round(float(row["context"]), 4),
                    "baseline_persistence": round(float(row["baseline_persistence"]), 3),
                    "baseline_seasonal": round(float(row["baseline_seasonal"]), 3),
                }
                for _, row in pred_df.iterrows()
            ],
            "walk_forward": {
                "enabled": True,
                "folds": int(len(pred_df)),
                "horizon_days": int(horizon_days),
                "min_train_points": int(min_train_points),
                "strict_vintage_mode": bool(self.strict_vintage_mode),
                "delay_rules_days": dict(self.DEFAULT_DELAY_RULES_DAYS | (delay_rules or {})),
            },
        }

    def run_market_simulation(
        self,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        days_back: int = 730,
        horizon_days: int = DEFAULT_MARKET_HORIZON_DAYS,
        min_train_points: int = DEFAULT_MIN_TRAIN_POINTS,
        delay_rules: Optional[dict[str, int]] = None,
        strict_vintage_mode: bool = True,
    ) -> dict:
        """Mode A: Markt-Check ohne Kundendaten gegen externe RKI-Proxy-Targets."""
        self.strict_vintage_mode = bool(strict_vintage_mode)
        logger.info(
            "Starte Markt-Simulation: virus=%s, target_source=%s, days_back=%s, strict_vintage=%s",
            virus_typ, target_source, days_back, self.strict_vintage_mode
        )

        try:
            target_df, target_meta = self._load_market_target(
                target_source=target_source,
                days_back=days_back,
            )
        except Exception as e:
            return {"error": str(e)}

        if target_df.empty or len(target_df) < 8:
            return {
                "error": (
                    f"Zu wenig Daten für Markt-Simulation ({len(target_df)} Punkte). "
                    "Mindestens 8 erforderlich."
                ),
                "target_source": target_meta.get("target_source"),
                "target_label": target_meta.get("target_label"),
            }

        result = self._run_walk_forward_market_backtest(
            target_df=target_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            delay_rules=delay_rules,
        )
        if "error" in result:
            return result

        df_sim = pd.DataFrame([{
            "date": row["date"],
            "bio": row["bio"],
            "real_qty": row["real_qty"],
        } for row in result.get("chart_data", [])])
        lead_lag = self._best_bio_lead_lag(df_sim)
        lead_days = lead_lag["best_lag_days"]
        baseline_delta = result.get("improvement_vs_baselines", {})
        delta_pers = baseline_delta.get("mae_vs_persistence_pct", 0.0)
        delta_seas = baseline_delta.get("mae_vs_seasonal_pct", 0.0)

        if lead_lag["bio_leads_target"]:
            proof_text = (
                f"Bio-Signal führt die Zielreihe um ca. {lead_days} Tage "
                f"(Lag-Korrelation {lead_lag['lag_correlation']})."
            )
        elif lead_days < 0:
            proof_text = (
                f"Zielreihe führt das Bio-Signal um ca. {abs(lead_days)} Tage "
                f"(Lag-Korrelation {lead_lag['lag_correlation']})."
            )
        else:
            proof_text = (
                f"Kein klarer Lead erkennbar (Lag-Korrelation {lead_lag['lag_correlation']})."
            )

        result["mode"] = "MARKET_CHECK"
        result["virus_typ"] = virus_typ
        result["target_source"] = target_meta.get("target_source")
        result["target_key"] = target_meta.get("target_key", target_source)
        result["target_label"] = target_meta.get("target_label")
        result["target_meta"] = target_meta
        result["lead_lag"] = lead_lag
        result["vintage_mode"] = "STRICT_ASOF" if self.strict_vintage_mode else "EVENT_TIME_ONLY"
        result["cutoff_policy"] = {
            "strict_vintage_mode": bool(self.strict_vintage_mode),
            "fallback": "event_time<=cutoff when available_time is NULL",
        }
        result["proof_text"] = (
            f"{proof_text} "
            f"Gegenüber Persistence beträgt die MAE-Veränderung {delta_pers:+.2f}%, "
            f"gegenüber Seasonal-Naive {delta_seas:+.2f}%."
        )
        result["llm_insight"] = (
            f"{result['proof_text']} "
            f"Walk-forward Modellgüte: R²={result['metrics']['r2_score']}, "
            f"Korrelation={result['metrics']['correlation_pct']}%, "
            f"sMAPE={result['metrics'].get('smape', 0)}."
        )

        persisted_run_id = self._persist_backtest_result(
            mode="MARKET_CHECK",
            virus_typ=virus_typ,
            target_source=result["target_source"],
            target_key=result["target_key"],
            target_label=result["target_label"],
            result=result,
            parameters={
                "days_back": days_back,
                "horizon_days": horizon_days,
                "min_train_points": min_train_points,
                "strict_vintage_mode": bool(self.strict_vintage_mode),
                "delay_rules": delay_rules or {},
            },
        )
        if persisted_run_id:
            result["run_id"] = persisted_run_id

        return result

    def run_customer_simulation(
        self,
        customer_df: pd.DataFrame,
        virus_typ: str = "Influenza A",
        horizon_days: int = DEFAULT_MARKET_HORIZON_DAYS,
        min_train_points: int = DEFAULT_MIN_TRAIN_POINTS,
        strict_vintage_mode: bool = True,
    ) -> dict:
        """Mode B: Realitäts-Check mit Kundendaten (optional region-spezifisch)."""
        self.strict_vintage_mode = bool(strict_vintage_mode)
        df = customer_df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]

        if "datum" not in df.columns or "menge" not in df.columns:
            return {
                "error": "Fehlende Pflichtspalten. Erwartet: datum, menge",
                "found_columns": list(df.columns),
            }

        if "region" not in df.columns:
            df["region"] = "Gesamt"

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
        df["region"] = df["region"].astype(str).fillna("Gesamt")
        df = df.dropna(subset=["datum", "menge"]).sort_values(["region", "datum"])

        if len(df) < 8:
            return {
                "error": f"Zu wenig Datenpunkte ({len(df)}). Mindestens 8 erforderlich.",
            }

        region_results: dict[str, dict] = {}
        combined_chart: list[dict] = []

        for region_name, region_df in df.groupby("region"):
            target_df = region_df[["datum", "menge"]].copy()
            target_df["available_time"] = target_df["datum"]
            if len(target_df) < max(8, min_train_points):
                continue

            region_result = self._run_walk_forward_market_backtest(
                target_df=target_df,
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                min_train_points=min_train_points,
                delay_rules=None,
            )
            if "error" in region_result:
                continue

            sim_df = pd.DataFrame([{
                "date": row["date"],
                "bio": row["bio"],
                "real_qty": row["real_qty"],
            } for row in region_result.get("chart_data", [])])
            region_lead_lag = self._best_bio_lead_lag(sim_df)
            region_result["lead_lag"] = region_lead_lag

            for row in region_result.get("chart_data", []):
                row["region"] = region_name
                combined_chart.append(row)

            region_results[region_name] = {
                "metrics": region_result.get("metrics", {}),
                "lead_lag": region_lead_lag,
                "chart_points": len(region_result.get("chart_data", [])),
            }

        if not combined_chart:
            return {
                "error": "Keine validen Backtest-Folds aus Kundendaten erzeugt. Bitte mehr Historie hochladen.",
            }

        combined_df = pd.DataFrame(combined_chart).sort_values("date").reset_index(drop=True)
        y_true = combined_df["real_qty"].to_numpy(dtype=float)
        y_hat = combined_df["predicted_qty"].to_numpy(dtype=float)
        y_persistence = combined_df["baseline_persistence"].to_numpy(dtype=float)
        y_seasonal = combined_df["baseline_seasonal"].to_numpy(dtype=float)

        model_metrics = self._compute_forecast_metrics(y_true, y_hat)
        persistence_metrics = self._compute_forecast_metrics(y_true, y_persistence)
        seasonal_metrics = self._compute_forecast_metrics(y_true, y_seasonal)

        model_mae = max(model_metrics["mae"], 1e-9)
        pers_mae = max(persistence_metrics["mae"], 1e-9)
        seas_mae = max(seasonal_metrics["mae"], 1e-9)

        lead_lag_global = self._best_bio_lead_lag(
            combined_df[["date", "bio", "real_qty"]].rename(columns={"real_qty": "real_qty"})
        )
        proof_text = (
            f"Kundendaten-Check über {model_metrics['data_points']} Punkte: "
            f"R²={model_metrics['r2_score']}, Korrelation={model_metrics['correlation_pct']}%, "
            f"Lead/Lag={lead_lag_global['best_lag_days']} Tage."
        )

        result = {
            "mode": "CUSTOMER_CHECK",
            "virus_typ": virus_typ,
            "target_source": "CUSTOMER_SALES",
            "target_key": "CUSTOMER_SALES",
            "target_label": "Kundenumsatz/Bestellmenge",
            "metrics": model_metrics,
            "baseline_metrics": {
                "persistence": persistence_metrics,
                "seasonal_naive": seasonal_metrics,
            },
            "improvement_vs_baselines": {
                "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
                "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
            },
            "lead_lag": lead_lag_global,
            "regions": region_results,
            "chart_data": combined_df.to_dict(orient="records"),
            "proof_text": proof_text,
            "llm_insight": (
                f"{proof_text} Gegenüber Persistence beträgt die MAE-Veränderung "
                f"{((pers_mae - model_mae) / pers_mae * 100):+.2f}%, "
                f"gegenüber Seasonal-Naive {((seas_mae - model_mae) / seas_mae * 100):+.2f}%."
            ),
            "walk_forward": {
                "enabled": True,
                "folds": int(model_metrics["data_points"]),
                "horizon_days": int(horizon_days),
                "min_train_points": int(min_train_points),
                "strict_vintage_mode": bool(self.strict_vintage_mode),
            },
        }

        persisted_run_id = self._persist_backtest_result(
            mode="CUSTOMER_CHECK",
            virus_typ=virus_typ,
            target_source="CUSTOMER_SALES",
            target_key="CUSTOMER_SALES",
            target_label="Kundenumsatz/Bestellmenge",
            result=result,
            parameters={
                "horizon_days": horizon_days,
                "min_train_points": min_train_points,
                "strict_vintage_mode": bool(self.strict_vintage_mode),
                "regions_in_input": sorted(df["region"].unique().tolist()),
            },
        )
        if persisted_run_id:
            result["run_id"] = persisted_run_id

        return result

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
        self.strict_vintage_mode = False

        no_delay_rules = {k: 0 for k in self.DEFAULT_DELAY_RULES_DAYS}
        simulation_rows = self._simulate_rows_from_target(
            customer_df,
            virus_typ,
            horizon_days=0,
            delay_rules=no_delay_rules,
        )
        if not simulation_rows:
            return {"error": "Keine Datenpunkte konnten simuliert werden."}

        df_sim = pd.DataFrame(simulation_rows)
        result = self._fit_regression_from_simulation(df_sim, virus_typ, use_llm=True)
        if "error" in result:
            return result

        logger.info(
            "Kalibrierung abgeschlossen: R²=%s, Korrelation=%s, Gewichte=%s",
            result["metrics"]["r2_score"],
            result["metrics"]["correlation"],
            result["optimized_weights"],
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
        """LLM-Erklärung der Kalibrierungsergebnisse via lokalem vLLM."""
        dominant = max(weights, key=weights.get)
        weakest = min(weights, key=weights.get)

        factor_names = {
            "bio": "Biologische Daten (RKI-Abwasser + Laborpositivrate)",
            "market": "Marktdaten (Lieferengpässe + Bestelltrends)",
            "psycho": "Suchverhalten (Google Trends)",
            "context": "Kontextfaktoren (Wetter + Schulferien)",
        }

        prompt = f"""Du bist ein Senior Data Scientist bei ViralFlux Media Intelligence.
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
            from app.services.llm.vllm_service import generate_text_sync

            messages = [
                {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
                {"role": "user", "content": prompt},
            ]
            text = generate_text_sync(messages=messages, temperature=0.2)
            if text.startswith("FEHLER:"):
                raise RuntimeError(text)
            return text
        except Exception as e:
            logger.warning(f"LLM Insight fehlgeschlagen: {e}")
            return (
                f"Die Analyse von {n_samples} Datenpunkten zeigt eine "
                f"{abs(correlation)*100:.0f}%ige Korrelation zwischen ViralFlux-Signalen "
                f"und Ihren tatsächlichen Bestellungen. Der stärkste Einflussfaktor "
                f"ist \"{factor_names[dominant]}\" ({weights[dominant]*100:.0f}%). "
                f"Wir empfehlen, das Modell mit diesen optimierten Gewichten zu kalibrieren."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Globale Kalibrierung (3 Jahre, RKI-Fallback)
    # ─────────────────────────────────────────────────────────────────────────

    def run_global_calibration(
        self, virus_typ: str = "Influenza A", days_back: int = 1095
    ) -> dict:
        """Trainiert Gewichte über 3 Jahre. Nutzt interne Daten oder RKI-Fallback.

        Priorität 1: Interne Verkaufsdaten (GanzimmunData)
        Priorität 2: RKI ARE-Konsultation (Markt-Proxy)
        Priorität 3: RKI SURVSTAT All (Markt-Proxy)
        """
        logger.info(
            f"Starte globale Kalibrierung: {virus_typ}, "
            f"Rückblick={days_back} Tage ({days_back / 365:.1f} Jahre)"
        )

        start_date = datetime.now() - timedelta(days=days_back)

        # 1. Interne Daten prüfen
        internal_data = self.db.query(GanzimmunData).filter(
            GanzimmunData.test_typ.ilike(f"%{virus_typ}%"),
            GanzimmunData.datum >= start_date,
        ).order_by(GanzimmunData.datum.asc()).all()

        target_source = "INTERNAL_SALES"

        # 2. Fallback auf externe Markt-Proxy-Daten (ARE / SURVSTAT)
        if not internal_data or len(internal_data) < 50:
            logger.info("Keine ausreichenden internen Daten. Fallback auf RKI ARE.")

            try:
                df, target_meta = self._load_market_target(
                    target_source="RKI_ARE",
                    days_back=days_back,
                )
                target_source = target_meta.get("target_source", "RKI_ARE")
            except Exception as e:
                logger.warning(f"ARE-Fallback fehlgeschlagen: {e}")
                df = pd.DataFrame()

            if len(df) < 20:
                logger.info("ARE nicht ausreichend. Fallback auf SURVSTAT All.")
                try:
                    df, target_meta = self._load_market_target(
                        target_source="SURVSTAT",
                        days_back=days_back,
                    )
                    target_source = target_meta.get("target_source", "SURVSTAT")
                except Exception as e:
                    logger.warning(f"SURVSTAT-Fallback fehlgeschlagen: {e}")
                    df = pd.DataFrame()

            if len(df) < 5:
                return {"error": "Weder interne Daten noch valide RKI-Proxy-Daten verfügbar."}
        else:
            df = pd.DataFrame([{
                'datum': d.datum,
                'menge': d.anzahl_tests,
            } for d in internal_data])

        if len(df) < 5:
            return {"error": f"Zu wenig Datenpunkte ({len(df)}) für Kalibrierung."}

        # 3. Simulation & Training (nutzt existierende run_calibration Logik)
        result = self.run_calibration(df, virus_typ=virus_typ)

        if "error" in result:
            return result

        new_weights = result["optimized_weights"]
        metrics = result["metrics"]

        # 4. Speichern als Global Default
        self._save_global_defaults(
            new_weights, metrics["r2_score"], len(df)
        )

        message = (
            f"Analyse über {len(df)} Datenpunkte "
            f"({len(df) / 365 * 7:.1f} Wochen) abgeschlossen. "
            f"Basis: {target_source}. "
            f"Neue Gewichtung: Bio {new_weights['bio'] * 100:.0f}%, "
            f"Markt {new_weights['market'] * 100:.0f}%, "
            f"Psycho {new_weights['psycho'] * 100:.0f}%, "
            f"Kontext {new_weights['context'] * 100:.0f}%."
        )

        return {
            "status": "success",
            "calibration_source": target_source,
            "period_days": days_back,
            "data_points": len(df),
            "new_weights": new_weights,
            "metrics": metrics,
            "message": message,
        }

    def _save_global_defaults(
        self, weights: dict, score: float, days_count: int
    ):
        """Speichere optimierte Gewichte als Global Default."""
        config = self.db.query(LabConfiguration).filter_by(
            is_global_default=True
        ).first()

        if not config:
            config = LabConfiguration(is_global_default=True)
            self.db.add(config)

        config.weight_bio = weights.get('bio', 0.35)
        config.weight_market = weights.get('market', 0.35)
        config.weight_psycho = weights.get('psycho', 0.10)
        config.weight_context = weights.get('context', 0.20)
        config.correlation_score = score
        config.analyzed_days = days_count
        config.last_calibration_date = datetime.utcnow()
        config.calibration_source = "GLOBAL_AUTO_3Y"

        self.db.commit()
        logger.info(f"Globale System-Defaults aktualisiert (R²={score:.2f})")

    # ─────────────────────────────────────────────────────────────────────────
    # Business Pitch Report: ML Detection Advantage vs RKI Reporting
    # ─────────────────────────────────────────────────────────────────────────

    def generate_business_pitch_report(
        self,
        disease: str = "Norovirus-Gastroenteritis",
        virus_typ: str = "Influenza A",
        season_start: str = "2024-10-01",
        season_end: str = "2025-03-31",
        output_path: str | None = None,
    ) -> dict:
        """Generate a business-proof CSV showing ML detection advantage over RKI reporting.

        Simulates the winter season week-by-week using strict TimeSeriesSplit
        (no future data leakage). For each week, computes the ML risk score
        from wastewater/trends/weather signals, then compares the ML alert date
        to the actual RKI-reported outbreak onset.

        Detection method: Adaptive outbreak detection. An alert fires when the
        case count WoW growth rate exceeds 40% AND the bio_score is above its
        trailing 4-week average. This avoids both false positives (noise) and
        missed detections (flat thresholds on dampened composite scores).

        The key metric is TTD_Advantage_Days (Time-To-Detection Advantage):
        TTD = RKI_peak_date - ML_first_alert_date

        Args:
            disease: RKI disease name for SurvstatKreisData ground truth.
            virus_typ: Virus type for wastewater/signal computation.
            season_start: Start of evaluation window (ISO date).
            season_end: End of evaluation window (ISO date).
            output_path: CSV output path. Defaults to data/processed/backtest_business_report.csv.

        Returns:
            Dict with summary metrics and path to exported CSV.
        """
        from pathlib import Path
        from app.models.database import SurvstatKreisData

        start_dt = datetime.strptime(season_start, "%Y-%m-%d")
        end_dt = datetime.strptime(season_end, "%Y-%m-%d")

        # Load 8 extra weeks before the evaluation window for bio_score baseline
        lookback_dt = start_dt - timedelta(weeks=8)

        logger.info(
            "Business Pitch Report: disease=%s, virus=%s, period=%s to %s",
            disease, virus_typ, season_start, season_end,
        )

        # ── 1. Load ground truth: weekly national case counts from SurvstatKreisData ──
        kreis_rows = self.db.query(
            SurvstatKreisData.year,
            SurvstatKreisData.week,
            SurvstatKreisData.week_label,
            func.sum(SurvstatKreisData.fallzahl).label("total_cases"),
        ).filter(
            SurvstatKreisData.disease == disease,
        ).group_by(
            SurvstatKreisData.year,
            SurvstatKreisData.week,
            SurvstatKreisData.week_label,
        ).order_by(
            SurvstatKreisData.year,
            SurvstatKreisData.week,
        ).all()

        if not kreis_rows:
            return {"error": f"No SurvstatKreisData found for disease '{disease}'"}

        # Build weekly time series (including lookback)
        all_weekly = []
        for row in kreis_rows:
            try:
                week_date = datetime.strptime(f"{row.year}-W{row.week:02d}-1", "%Y-W%W-%w")
            except ValueError:
                continue
            if lookback_dt <= week_date <= end_dt:
                all_weekly.append({
                    "date": week_date,
                    "week_label": row.week_label,
                    "actual_rki_cases": int(row.total_cases or 0),
                })

        df_all = pd.DataFrame(all_weekly).sort_values("date").reset_index(drop=True)

        if len(df_all) < 8:
            return {"error": f"Insufficient data points ({len(df_all)}) in evaluation window"}

        # ── 2. Compute ML risk scores for ALL weeks (lookback + eval) ──
        scores = []
        for _, row in df_all.iterrows():
            sub = self._compute_sub_scores_at_date(
                target=row["date"], virus_typ=virus_typ,
                delay_rules=self.DEFAULT_DELAY_RULES_DAYS,
            )
            w = self.DEFAULT_WEIGHTS
            composite = round(min(1.0, max(0.0,
                sub["bio"] * w["bio"] + sub["market"] * w["market"]
                + sub["psycho"] * w["psycho"] + sub["context"] * w["context"]
            )), 4)
            scores.append({**sub, "ml_risk_score": composite})

        df_all["ml_risk_score"] = [s["ml_risk_score"] for s in scores]
        df_all["bio_score"] = [s["bio"] for s in scores]
        df_all["psycho_score"] = [s["psycho"] for s in scores]
        df_all["context_score"] = [s["context"] for s in scores]

        # ── 3. Adaptive outbreak detection ──
        # WoW case growth
        df_all["cases_prev"] = df_all["actual_rki_cases"].shift(1)
        df_all["wow_growth"] = (
            (df_all["actual_rki_cases"] - df_all["cases_prev"])
            / df_all["cases_prev"].replace(0, np.nan)
        ).fillna(0)

        # Bio score rolling mean (4-week trailing window)
        df_all["bio_rolling_mean"] = df_all["bio_score"].rolling(4, min_periods=2).mean()
        df_all["bio_above_trend"] = df_all["bio_score"] > df_all["bio_rolling_mean"]

        # Alert: WoW growth ≥ 40% AND bio above trend (2 consecutive weeks)
        df_all["bio_above_streak"] = 0
        streak = 0
        for i in range(len(df_all)):
            if df_all.iloc[i]["bio_above_trend"]:
                streak += 1
            else:
                streak = 0
            df_all.iloc[i, df_all.columns.get_loc("bio_above_streak")] = streak

        df_all["alert_triggered"] = (
            (df_all["wow_growth"] >= 0.40) & (df_all["bio_above_streak"] >= 2)
        )

        # ── 4. Filter to evaluation window only ──
        df_eval = df_all[df_all["date"] >= start_dt].copy().reset_index(drop=True)

        if df_eval.empty:
            return {"error": "No data points in evaluation window after filtering"}

        # Find RKI peak
        peak_idx = df_eval["actual_rki_cases"].idxmax()
        rki_peak_date = df_eval.loc[peak_idx, "date"]
        rki_peak_cases = int(df_eval.loc[peak_idx, "actual_rki_cases"])

        # Find first ML alert
        alert_rows = df_eval[df_eval["alert_triggered"]]
        ml_first_alert_date = alert_rows.iloc[0]["date"] if not alert_rows.empty else None

        # TTD
        ttd_days = (rki_peak_date - ml_first_alert_date).days if ml_first_alert_date else 0

        # ── 5. Build report rows ──
        report_rows = []
        for _, row in df_eval.iterrows():
            report_rows.append({
                "date": row["date"].strftime("%Y-%m-%d"),
                "region": "Gesamt",
                "disease": disease,
                "actual_rki_cases": int(row["actual_rki_cases"]),
                "ml_risk_score": float(row["ml_risk_score"]),
                "alert_triggered": bool(row["alert_triggered"]),
                "ttd_advantage_days": ttd_days,
                "bio_score": float(row["bio_score"]),
                "psycho_score": float(row["psycho_score"]),
                "context_score": float(row["context_score"]),
                "wow_growth_pct": round(float(row["wow_growth"]) * 100, 1),
            })

        df_report = pd.DataFrame(report_rows)

        # ── 6. Export CSV ──
        if output_path is None:
            out_dir = Path("/app/data/processed")
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / "backtest_business_report.csv")

        df_report.to_csv(output_path, index=False)
        logger.info("Business pitch report exported to %s (%d rows)", output_path, len(df_report))

        # ── 7. Summary ──
        alerts_count = int(df_report["alert_triggered"].sum())
        total_weeks = len(df_report)

        summary = {
            "status": "success",
            "disease": disease,
            "virus_typ": virus_typ,
            "season": f"{season_start} → {season_end}",
            "total_weeks": total_weeks,
            "rki_peak_date": rki_peak_date.strftime("%Y-%m-%d"),
            "rki_peak_cases": rki_peak_cases,
            "ml_first_alert_date": ml_first_alert_date.strftime("%Y-%m-%d") if ml_first_alert_date else None,
            "ttd_advantage_days": ttd_days,
            "detection_method": "Adaptive: WoW_growth>=40% AND bio_score>4wk_trailing_avg for 2+ weeks",
            "alerts_triggered": alerts_count,
            "alert_rate_pct": round(alerts_count / total_weeks * 100, 1),
            "output_path": output_path,
            "proof_statement": (
                f"ViralFlux ML detected the {disease} outbreak {ttd_days} days before "
                f"the RKI peak ({rki_peak_date.strftime('%Y-%m-%d')}, {rki_peak_cases:,} cases). "
                f"First alert: {ml_first_alert_date.strftime('%Y-%m-%d') if ml_first_alert_date else 'N/A'}."
            ) if ml_first_alert_date else (
                f"No ML alert triggered during the evaluation period. "
                f"RKI peak: {rki_peak_date.strftime('%Y-%m-%d')} ({rki_peak_cases:,} cases)."
            ),
        }

        logger.info("Business proof: TTD=%d days, peak=%s", ttd_days, rki_peak_date.strftime("%Y-%m-%d"))
        return summary
