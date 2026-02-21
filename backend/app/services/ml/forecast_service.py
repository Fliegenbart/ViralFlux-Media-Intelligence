"""ML Stacking Forecast Service.

Architecture: XGBoost Meta-Learner stacking three base estimators
(Holt-Winters, Ridge Regression, Prophet) with AMELAG lagged features
and asymmetric loss (quantile regression at 80th percentile).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sqlalchemy.orm import Session
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.core.config import get_settings
from app.models.database import (
    GoogleTrendsData,
    MLForecast,
    SchoolHolidays,
    WastewaterAggregated,
    WeatherData,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Features used by the XGBoost meta-learner
META_FEATURES: list[str] = [
    "hw_pred",
    "ridge_pred",
    "prophet_pred",
    "amelag_lag4",
    "amelag_lag7",
    "trend_momentum_7d",
    "schulferien",
    "trends_score",
]


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


class ForecastService:
    """ML Stacking Forecast: HW + Ridge + Prophet → XGBoost Meta-Learner."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.forecast_days: int = settings.FORECAST_DAYS
        self.confidence_level: float = settings.CONFIDENCE_LEVEL

    # ═══════════════════════════════════════════════════════════════════
    #  DATA PREPARATION
    # ═══════════════════════════════════════════════════════════════════

    def prepare_training_data(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
    ) -> pd.DataFrame:
        """Build feature DataFrame from wastewater, trends, holidays, AMELAG."""
        logger.info(f"Preparing training data for {virus_typ}")
        start_date = datetime.now() - timedelta(days=lookback_days)

        # 1. Wastewater viral load (target) + AMELAG vorhersage
        wastewater = (
            self.db.query(WastewaterAggregated)
            .filter(
                WastewaterAggregated.virus_typ == virus_typ,
                WastewaterAggregated.datum >= start_date,
            )
            .order_by(WastewaterAggregated.datum.asc())
            .all()
        )

        if not wastewater:
            logger.warning(f"No wastewater data found for {virus_typ}")
            return pd.DataFrame()

        df = pd.DataFrame(
            [
                {
                    "ds": w.datum,
                    "y": w.viruslast,
                    "viruslast_normalized": w.viruslast_normalisiert,
                    "amelag_pred": w.vorhersage,
                }
                for w in wastewater
            ]
        )

        df = df.sort_values("ds").reset_index(drop=True)
        df["ds"] = pd.to_datetime(df["ds"])

        # 2. Google Trends
        trends_keywords = ["Grippe", "Erkältung", "Fieber"]
        trends = (
            self.db.query(GoogleTrendsData)
            .filter(
                GoogleTrendsData.keyword.in_(trends_keywords),
                GoogleTrendsData.datum >= start_date,
            )
            .all()
        )

        if trends:
            trends_df = pd.DataFrame(
                [{"ds": pd.to_datetime(t.datum), "interest_score": t.interest_score} for t in trends]
            )
            trends_avg = trends_df.groupby("ds")["interest_score"].mean().reset_index()
            trends_avg.columns = ["ds", "trends_score"]
            df = df.merge(trends_avg, on="ds", how="left")
        else:
            df["trends_score"] = 0.0

        # 3. School holidays
        df["schulferien"] = df["ds"].apply(lambda d: 1.0 if self._is_holiday(d) else 0.0)

        # 4. Lag features
        df["lag1"] = df["y"].shift(1)
        df["lag2"] = df["y"].shift(2)
        df["lag3"] = df["y"].shift(3)

        # 5. Moving averages
        df["ma3"] = df["y"].rolling(window=3, min_periods=1).mean()
        df["ma5"] = df["y"].rolling(window=5, min_periods=1).mean()

        # 6. Rate of change
        df["roc"] = df["y"].pct_change()

        # 7. Trend momentum (7-day slope as 1st derivative)
        y_shifted = df["y"].shift(7).replace(0, np.nan)
        df["trend_momentum_7d"] = df["y"].diff(periods=7) / y_shifted

        # 8. AMELAG vorhersage time-lagged features (wastewater leads demand by 4-7 days)
        df["amelag_lag4"] = df["amelag_pred"].shift(4)
        df["amelag_lag7"] = df["amelag_pred"].shift(7)

        # Fill NaN
        df = df.bfill().ffill()
        # Replace remaining inf/nan
        df = df.replace([np.inf, -np.inf], 0.0).fillna(0.0)

        logger.info(f"Training data prepared: {len(df)} rows, {len(df.columns)} features")
        return df

    def _is_holiday(self, datum: datetime) -> bool:
        """Check if date falls in school holidays."""
        return (
            self.db.query(SchoolHolidays)
            .filter(
                SchoolHolidays.start_datum <= datum,
                SchoolHolidays.end_datum >= datum,
            )
            .first()
            is not None
        )

    # ═══════════════════════════════════════════════════════════════════
    #  BASE ESTIMATORS
    # ═══════════════════════════════════════════════════════════════════

    def _fit_holt_winters(self, y: np.ndarray, n_steps: int) -> np.ndarray:
        """Base estimator 1: Holt-Winters Exponential Smoothing."""
        n = len(y)
        try:
            seasonal_periods = min(52, n // 2) if n >= 8 else None
            if seasonal_periods and seasonal_periods >= 2:
                hw_model = ExponentialSmoothing(
                    y,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=seasonal_periods,
                    initialization_method="estimated",
                )
            else:
                hw_model = ExponentialSmoothing(
                    y,
                    trend="add",
                    initialization_method="estimated",
                )
            hw_fit = hw_model.fit(optimized=True)
            return hw_fit.forecast(n_steps)
        except Exception as e:
            logger.warning(f"Holt-Winters failed, using simple trend: {e}")
            recent = y[-min(5, n) :]
            slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
            return np.array([y[-1] + slope * (i + 1) for i in range(n_steps)])

    def _fit_ridge(
        self,
        df: pd.DataFrame,
        y: np.ndarray,
        n_steps: int,
    ) -> tuple[np.ndarray, dict[str, float]]:
        """Base estimator 2: Ridge Regression on lag/trend features."""
        feature_cols = ["lag1", "lag2", "lag3", "ma3", "ma5", "trends_score", "schulferien", "roc"]
        available = [c for c in feature_cols if c in df.columns]

        if len(available) < 2:
            return np.full(n_steps, y[-1]), {}

        try:
            X = df[available].values
            ridge = Ridge(alpha=1.0)
            ridge.fit(X, y)

            forecast: list[float] = []
            last_row = df[available].iloc[-1].values.copy()
            last_vals = list(y[-5:])

            for _ in range(n_steps):
                pred = float(ridge.predict(last_row.reshape(1, -1))[0])
                forecast.append(pred)
                last_vals.append(pred)
                if "lag1" in available:
                    last_row[available.index("lag1")] = pred
                if "lag2" in available:
                    last_row[available.index("lag2")] = last_vals[-2] if len(last_vals) >= 2 else pred
                if "lag3" in available:
                    last_row[available.index("lag3")] = last_vals[-3] if len(last_vals) >= 3 else pred
                if "ma3" in available:
                    last_row[available.index("ma3")] = np.mean(last_vals[-3:])
                if "ma5" in available:
                    last_row[available.index("ma5")] = np.mean(last_vals[-5:])
                if "roc" in available:
                    prev = last_vals[-2] if len(last_vals) >= 2 else 1.0
                    last_row[available.index("roc")] = (pred - prev) / prev if prev != 0 else 0.0

            importance: dict[str, float] = {}
            total_abs = float(np.sum(np.abs(ridge.coef_))) + 1e-9
            for fname, coef in zip(available, ridge.coef_):
                importance[fname] = round(abs(float(coef)) / total_abs, 3)

            return np.array(forecast), importance
        except Exception as e:
            logger.warning(f"Ridge regression failed: {e}")
            return np.full(n_steps, y[-1]), {}

    def _fit_prophet(
        self,
        virus_typ: str,
        n_steps: int,
    ) -> np.ndarray | None:
        """Base estimator 3: Facebook Prophet with regressors."""
        try:
            from app.services.fusion_engine.prophet_predictor import ProphetPredictor

            predictor = ProphetPredictor(self.db)
            result = predictor.fit_and_predict(
                virus_typ=virus_typ,
                forecast_days=n_steps,
            )

            if result and "forecast" in result and result["forecast"]:
                preds = [max(0.0, item["yhat"]) for item in result["forecast"]]
                return np.array(preds[:n_steps])
        except Exception as e:
            logger.warning(f"Prophet failed for {virus_typ}: {e}")

        return None

    # ═══════════════════════════════════════════════════════════════════
    #  XGBOOST META-LEARNER
    # ═══════════════════════════════════════════════════════════════════

    def _generate_oof_predictions(
        self,
        df: pd.DataFrame,
        n_splits: int = 5,
    ) -> pd.DataFrame:
        """Generate out-of-fold predictions from base estimators using TimeSeriesSplit.

        For each fold, HW and Ridge are trained on the train split and
        predicted on the validation split. Prophet predictions are estimated
        from the last known training values (simplified — Prophet is expensive).
        """
        y = df["y"].values
        n = len(y)
        tscv = TimeSeriesSplit(n_splits=n_splits)

        oof = pd.DataFrame(index=df.index, columns=["hw_pred", "ridge_pred"], dtype=float)
        oof[:] = np.nan

        for train_idx, val_idx in tscv.split(df):
            if len(train_idx) < 10 or len(val_idx) < 1:
                continue

            y_train = y[train_idx]
            n_val = len(val_idx)

            # HW
            hw_preds = self._fit_holt_winters(y_train, n_val)
            oof.loc[val_idx, "hw_pred"] = hw_preds[:n_val]

            # Ridge
            df_train = df.iloc[train_idx]
            ridge_preds, _ = self._fit_ridge(df_train, y_train, n_val)
            oof.loc[val_idx, "ridge_pred"] = ridge_preds[:n_val]

        # Fill any remaining NaN with simple persistence (last known value)
        oof["hw_pred"] = oof["hw_pred"].ffill().bfill().fillna(y[-1])
        oof["ridge_pred"] = oof["ridge_pred"].ffill().bfill().fillna(y[-1])

        return oof

    def _fit_xgboost_meta(
        self,
        df: pd.DataFrame,
        oof: pd.DataFrame,
    ) -> tuple[Any, Any, Any, dict[str, float]]:
        """Train XGBoost meta-learner with quantile regression (asymmetric loss).

        Returns (model_median, model_lower, model_upper, feature_importance).
        """
        from xgboost import XGBRegressor

        # Merge OOF predictions into feature DataFrame
        df_meta = df.copy()
        df_meta["hw_pred"] = oof["hw_pred"].values
        df_meta["ridge_pred"] = oof["ridge_pred"].values
        # Prophet OOF: approximate with rolling mean (Prophet is too expensive per fold)
        df_meta["prophet_pred"] = df_meta["ma5"]  # reasonable proxy for OOF

        # Build feature matrix
        available_meta = [f for f in META_FEATURES if f in df_meta.columns]
        X = df_meta[available_meta].values
        y = df_meta["y"].values

        # Replace any remaining NaN/inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # ── Median model (main prediction, biased high via quantile_alpha=0.8) ──
        model_median = XGBRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            objective="reg:quantileerror",
            quantile_alpha=0.8,
            random_state=42,
            verbosity=0,
        )
        model_median.fit(X, y)

        # ── Lower bound (10th percentile) ──
        model_lower = XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            objective="reg:quantileerror",
            quantile_alpha=0.1,
            random_state=42,
            verbosity=0,
        )
        model_lower.fit(X, y)

        # ── Upper bound (90th percentile) ──
        model_upper = XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            objective="reg:quantileerror",
            quantile_alpha=0.9,
            random_state=42,
            verbosity=0,
        )
        model_upper.fit(X, y)

        # Feature importance from median model
        importance_raw = model_median.feature_importances_
        total = float(np.sum(importance_raw)) + 1e-9
        feature_importance = {
            fname: round(float(imp) / total, 3)
            for fname, imp in zip(available_meta, importance_raw)
        }

        logger.info(f"XGBoost meta-learner trained on {len(y)} samples, {len(available_meta)} features")
        return model_median, model_lower, model_upper, feature_importance

    def _compute_outbreak_risk(
        self,
        prediction: float,
        y_history: np.ndarray,
        window: int = 30,
    ) -> float:
        """Compute outbreak risk score (0.0 – 1.0) via z-score sigmoid."""
        recent = y_history[-min(window, len(y_history)) :]
        mean_val = float(np.mean(recent))
        std_val = float(np.std(recent))
        if std_val < 1e-9:
            return 0.5
        z = (prediction - mean_val) / std_val
        return round(_sigmoid(z), 3)

    # ═══════════════════════════════════════════════════════════════════
    #  MAIN FORECAST PIPELINE
    # ═══════════════════════════════════════════════════════════════════

    def train_and_forecast(self, virus_typ: str = "Influenza A") -> dict[str, Any]:
        """Train stacking model and generate 14-day forecast.

        Pipeline:
        1. Prepare features (wastewater, trends, holidays, AMELAG lags, momentum)
        2. Generate out-of-fold predictions from HW + Ridge via TimeSeriesSplit
        3. Train XGBoost meta-learner on OOF predictions + auxiliary features
        4. Generate final forecast with confidence intervals
        """
        logger.info(f"=== Stacking forecast for {virus_typ} ===")

        df = self.prepare_training_data(virus_typ=virus_typ)

        if df.empty or len(df) < 10:
            logger.error(f"Insufficient data for training ({len(df) if not df.empty else 0} rows)")
            return {"error": "Insufficient training data"}

        y = df["y"].values
        n = len(y)

        # Detect data frequency
        date_diffs = df["ds"].diff().dt.days.dropna()
        data_freq_days = int(date_diffs.median()) if len(date_diffs) > 0 else 7
        data_freq_days = max(1, min(data_freq_days, 14))
        n_steps = max(2, self.forecast_days // data_freq_days + 1)

        logger.info(f"Data: {n} rows, freq={data_freq_days}d, n_steps={n_steps}")

        # ── Step 1: Base estimator forecasts (for the actual forecast horizon) ──
        hw_forecast = self._fit_holt_winters(y, n_steps)
        ridge_forecast, ridge_importance = self._fit_ridge(df, y, n_steps)
        prophet_forecast = self._fit_prophet(virus_typ, n_steps)

        if prophet_forecast is None:
            # Fallback: use average of HW and Ridge as Prophet proxy
            prophet_forecast = (hw_forecast + ridge_forecast) / 2.0
            logger.info("Prophet unavailable, using HW/Ridge average as proxy")

        # Ensure all forecast arrays have the same length
        min_len = min(len(hw_forecast), len(ridge_forecast), len(prophet_forecast))
        hw_forecast = hw_forecast[:min_len]
        ridge_forecast = ridge_forecast[:min_len]
        prophet_forecast = prophet_forecast[:min_len]
        n_steps = min_len

        # ── Step 2: Out-of-fold predictions for meta-learner training ──
        oof = self._generate_oof_predictions(df, n_splits=5)

        # ── Step 3: Train XGBoost meta-learner ──
        try:
            model_med, model_lo, model_hi, feature_importance = self._fit_xgboost_meta(df, oof)
            used_xgb = True
        except Exception as e:
            logger.warning(f"XGBoost meta-learner failed, falling back to weighted ensemble: {e}")
            used_xgb = False
            feature_importance = ridge_importance

        # ── Step 4: Generate forecast ──
        if used_xgb:
            # Build feature rows for each forecast step
            last_row = df.iloc[-1].copy()
            available_meta = [f for f in META_FEATURES if f in df.columns or f in ["hw_pred", "ridge_pred", "prophet_pred"]]

            ensemble = np.zeros(n_steps)
            lower = np.zeros(n_steps)
            upper = np.zeros(n_steps)

            for i in range(n_steps):
                feat = {}
                feat["hw_pred"] = float(hw_forecast[i])
                feat["ridge_pred"] = float(ridge_forecast[i])
                feat["prophet_pred"] = float(prophet_forecast[i])
                feat["amelag_lag4"] = float(last_row.get("amelag_lag4", 0.0))
                feat["amelag_lag7"] = float(last_row.get("amelag_lag7", 0.0))
                feat["trend_momentum_7d"] = float(last_row.get("trend_momentum_7d", 0.0))
                feat["schulferien"] = float(last_row.get("schulferien", 0.0))
                feat["trends_score"] = float(last_row.get("trends_score", 0.0))

                X_row = np.array([[feat.get(f, 0.0) for f in available_meta]])
                X_row = np.nan_to_num(X_row, nan=0.0, posinf=0.0, neginf=0.0)

                ensemble[i] = max(0.0, float(model_med.predict(X_row)[0]))
                lower[i] = max(0.0, float(model_lo.predict(X_row)[0]))
                upper[i] = max(0.0, float(model_hi.predict(X_row)[0]))
        else:
            # Fallback: weighted ensemble (legacy behavior)
            ensemble = 0.5 * hw_forecast + 0.3 * ridge_forecast + 0.2 * prophet_forecast
            ensemble = np.maximum(ensemble, 0)

            if n >= 5:
                residuals = np.diff(y[-min(20, n) :])
                std = float(np.std(residuals)) if len(residuals) > 1 else float(np.std(y)) * 0.1
            else:
                std = float(np.std(y)) * 0.1

            z = 1.96
            lower = ensemble - z * std * np.sqrt(np.arange(1, n_steps + 1))
            upper = ensemble + z * std * np.sqrt(np.arange(1, n_steps + 1))
            lower = np.maximum(lower, 0)

        # ── Step 5: Interpolate to daily resolution ──
        last_date = df["ds"].max()
        native_dates = [last_date + timedelta(days=data_freq_days * (i + 1)) for i in range(n_steps)]
        daily_dates = [last_date + timedelta(days=i + 1) for i in range(self.forecast_days)]

        native_days = np.array([(d - last_date).days for d in native_dates])
        daily_days = np.array([(d - last_date).days for d in daily_dates])

        interp_x = np.concatenate([[0], native_days])
        interp_y = np.concatenate([[y[-1]], ensemble])
        interp_lo = np.concatenate([[y[-1]], lower])
        interp_hi = np.concatenate([[y[-1]], upper])

        daily_ensemble = np.maximum(np.interp(daily_days, interp_x, interp_y), 0)
        daily_lower = np.maximum(np.interp(daily_days, interp_x, interp_lo), 0)
        daily_upper = np.maximum(np.interp(daily_days, interp_x, interp_hi), 0)

        # ── Step 6: Compute per-day outbreak risk + trend momentum ──
        last_momentum = float(df["trend_momentum_7d"].iloc[-1]) if "trend_momentum_7d" in df.columns else 0.0

        forecast_records: list[dict[str, Any]] = []
        for i in range(self.forecast_days):
            pred = float(daily_ensemble[i])
            risk = self._compute_outbreak_risk(pred, y)
            forecast_records.append(
                {
                    "ds": daily_dates[i],
                    "yhat": pred,
                    "yhat_lower": float(daily_lower[i]),
                    "yhat_upper": float(daily_upper[i]),
                    "trend_momentum_7d": last_momentum,
                    "outbreak_risk_score": risk,
                }
            )

        model_version = "xgb_stack_v1" if used_xgb else "hw_ridge_prophet_v2"

        result: dict[str, Any] = {
            "virus_typ": virus_typ,
            "training_samples": n,
            "forecast_days": self.forecast_days,
            "data_frequency_days": data_freq_days,
            "forecast": forecast_records,
            "feature_importance": feature_importance,
            "model_version": model_version,
            "confidence": float(self.confidence_level),
            "timestamp": datetime.utcnow(),
        }

        logger.info(
            f"Forecast completed for {virus_typ}: {self.forecast_days} daily points, "
            f"model={model_version}, features={len(feature_importance)}"
        )
        return result

    # ═══════════════════════════════════════════════════════════════════
    #  PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════

    def save_forecast(self, forecast_data: dict[str, Any]) -> int:
        """Save forecast to database including new stacking fields."""
        logger.info("Saving forecast to database...")
        count = 0

        for item in forecast_data["forecast"]:
            existing = (
                self.db.query(MLForecast)
                .filter(
                    MLForecast.forecast_date == item["ds"],
                    MLForecast.virus_typ == forecast_data["virus_typ"],
                )
                .first()
            )

            kwargs = {
                "predicted_value": item["yhat"],
                "lower_bound": item["yhat_lower"],
                "upper_bound": item["yhat_upper"],
                "confidence": forecast_data.get("confidence", 0.95),
                "model_version": forecast_data["model_version"],
                "features_used": forecast_data.get("feature_importance", {}),
                "trend_momentum_7d": item.get("trend_momentum_7d"),
                "outbreak_risk_score": item.get("outbreak_risk_score"),
            }

            if existing:
                for key, val in kwargs.items():
                    setattr(existing, key, val)
            else:
                forecast_record = MLForecast(
                    forecast_date=item["ds"],
                    virus_typ=forecast_data["virus_typ"],
                    **kwargs,
                )
                self.db.add(forecast_record)
                count += 1

        self.db.commit()
        logger.info(f"Saved {count} new forecast records")
        return count

    def run_forecasts_for_all_viruses(self) -> dict[str, Any]:
        """Run stacking forecasts for all relevant virus types."""
        virus_types = ["Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"]

        results: dict[str, Any] = {}
        for virus in virus_types:
            logger.info(f"Processing forecast for {virus}...")
            try:
                forecast = self.train_and_forecast(virus_typ=virus)
                if "error" not in forecast:
                    self.save_forecast(forecast)
                results[virus] = forecast
            except Exception as e:
                logger.error(f"Forecast failed for {virus}: {e}")
                results[virus] = {"error": str(e)}

        return results
