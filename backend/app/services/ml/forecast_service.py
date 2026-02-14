import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.linear_model import Ridge
import logging
from typing import Dict, List

from app.models.database import (
    WastewaterAggregated,
    GoogleTrendsData,
    WeatherData,
    SchoolHolidays,
    GrippeWebData,
    MLForecast
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ForecastService:
    """ML-basierter Prognosedienst mit Holt-Winters + Ridge Regression."""

    def __init__(self, db: Session):
        self.db = db
        self.forecast_days = settings.FORECAST_DAYS
        self.confidence_level = settings.CONFIDENCE_LEVEL

    def prepare_training_data(
        self,
        virus_typ: str = 'Influenza A',
        lookback_days: int = 900
    ) -> pd.DataFrame:
        """Prepare training data with all features."""
        logger.info(f"Preparing training data for {virus_typ}")
        start_date = datetime.now() - timedelta(days=lookback_days)

        # 1. Wastewater viral load (target)
        wastewater = self.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= start_date
        ).all()

        df = pd.DataFrame([{
            'ds': w.datum,
            'y': w.viruslast,
            'viruslast_normalized': w.viruslast_normalisiert
        } for w in wastewater])

        if df.empty:
            logger.warning(f"No wastewater data found for {virus_typ}")
            return pd.DataFrame()

        df = df.sort_values('ds').reset_index(drop=True)
        df['ds'] = pd.to_datetime(df['ds'])

        # 2. Google Trends
        trends_keywords = ['Grippe', 'Erkältung', 'Fieber']
        trends = self.db.query(GoogleTrendsData).filter(
            GoogleTrendsData.keyword.in_(trends_keywords),
            GoogleTrendsData.datum >= start_date
        ).all()

        trends_df = pd.DataFrame([{
            'ds': pd.to_datetime(t.datum),
            'interest_score': t.interest_score
        } for t in trends])

        if not trends_df.empty:
            trends_avg = trends_df.groupby('ds')['interest_score'].mean().reset_index()
            trends_avg.columns = ['ds', 'trends_score']
            df = df.merge(trends_avg, on='ds', how='left')
        else:
            df['trends_score'] = 0

        # 3. School holidays
        df['schulferien'] = df['ds'].apply(lambda d: 1 if self._is_holiday(d) else 0)

        # 4. Lag features
        df['lag1'] = df['y'].shift(1)
        df['lag2'] = df['y'].shift(2)
        df['lag3'] = df['y'].shift(3)

        # 5. Moving averages
        df['ma3'] = df['y'].rolling(window=3, min_periods=1).mean()
        df['ma5'] = df['y'].rolling(window=5, min_periods=1).mean()

        # 6. Rate of change
        df['roc'] = df['y'].pct_change()

        # Fill NaN
        df = df.bfill().ffill()

        logger.info(f"Training data prepared: {len(df)} rows, {len(df.columns)} features")
        return df

    def _is_holiday(self, datum) -> bool:
        """Check if date falls in school holidays."""
        return self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= datum,
            SchoolHolidays.end_datum >= datum
        ).first() is not None

    def train_and_forecast(self, virus_typ: str = 'Influenza A') -> Dict:
        """Train model and generate 14-day forecast using Holt-Winters + Ridge."""
        logger.info(f"Training forecast model for {virus_typ}")

        df = self.prepare_training_data(virus_typ=virus_typ)

        if df.empty or len(df) < 10:
            logger.error(f"Insufficient data for training ({len(df) if not df.empty else 0} rows)")
            return {"error": "Insufficient training data"}

        y = df['y'].values
        n = len(y)

        # Detect data frequency (median days between data points)
        date_diffs = df['ds'].diff().dt.days.dropna()
        data_freq_days = int(date_diffs.median()) if len(date_diffs) > 0 else 7
        data_freq_days = max(1, min(data_freq_days, 14))  # Clamp to 1-14
        logger.info(f"Detected data frequency: {data_freq_days} days")

        # Number of forecast steps at native frequency to cover forecast_days
        n_steps = max(2, self.forecast_days // data_freq_days + 1)

        # ── Method 1: Holt-Winters Exponential Smoothing ──
        try:
            seasonal_periods = min(52, n // 2) if n >= 8 else None
            if seasonal_periods and seasonal_periods >= 2:
                hw_model = ExponentialSmoothing(
                    y,
                    trend='add',
                    seasonal='add',
                    seasonal_periods=seasonal_periods,
                    initialization_method='estimated'
                )
            else:
                hw_model = ExponentialSmoothing(
                    y,
                    trend='add',
                    initialization_method='estimated'
                )
            hw_fit = hw_model.fit(optimized=True)
            hw_forecast = hw_fit.forecast(n_steps)
        except Exception as e:
            logger.warning(f"Holt-Winters failed, using simple trend: {e}")
            recent = y[-min(5, n):]
            slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
            hw_forecast = np.array([y[-1] + slope * (i + 1) for i in range(n_steps)])

        # ── Method 2: Ridge regression on features ──
        try:
            feature_cols = ['lag1', 'lag2', 'lag3', 'ma3', 'ma5', 'trends_score', 'schulferien', 'roc']
            available_features = [c for c in feature_cols if c in df.columns]

            if len(available_features) >= 2:
                X = df[available_features].values
                ridge = Ridge(alpha=1.0)
                ridge.fit(X, y)

                ridge_forecast = []
                last_row = df[available_features].iloc[-1].values.copy()
                last_vals = list(y[-5:])

                for i in range(n_steps):
                    pred = ridge.predict(last_row.reshape(1, -1))[0]
                    ridge_forecast.append(pred)
                    last_vals.append(pred)
                    if 'lag1' in available_features:
                        last_row[available_features.index('lag1')] = pred
                    if 'lag2' in available_features:
                        last_row[available_features.index('lag2')] = last_vals[-2] if len(last_vals) >= 2 else pred
                    if 'lag3' in available_features:
                        last_row[available_features.index('lag3')] = last_vals[-3] if len(last_vals) >= 3 else pred
                    if 'ma3' in available_features:
                        last_row[available_features.index('ma3')] = np.mean(last_vals[-3:])
                    if 'ma5' in available_features:
                        last_row[available_features.index('ma5')] = np.mean(last_vals[-5:])
                    if 'roc' in available_features:
                        prev = last_vals[-2] if len(last_vals) >= 2 else 1
                        last_row[available_features.index('roc')] = (pred - prev) / prev if prev != 0 else 0

                ridge_forecast = np.array(ridge_forecast)

                feature_importance = {}
                for fname, coef in zip(available_features, ridge.coef_):
                    feature_importance[fname] = round(abs(float(coef)) / (np.sum(np.abs(ridge.coef_)) + 1e-9), 3)
            else:
                ridge_forecast = hw_forecast.copy()
                feature_importance = {}
        except Exception as e:
            logger.warning(f"Ridge regression failed: {e}")
            ridge_forecast = hw_forecast.copy()
            feature_importance = {}

        # ── Ensemble: 60% Holt-Winters + 40% Ridge ──
        ensemble = 0.6 * hw_forecast + 0.4 * ridge_forecast
        ensemble = np.maximum(ensemble, 0)

        # Confidence intervals
        if n >= 5:
            residuals = np.diff(y[-min(20, n):])
            std = np.std(residuals) if len(residuals) > 1 else np.std(y) * 0.1
        else:
            std = np.std(y) * 0.1

        z = 1.96
        lower = ensemble - z * std * np.sqrt(np.arange(1, n_steps + 1))
        upper = ensemble + z * std * np.sqrt(np.arange(1, n_steps + 1))
        lower = np.maximum(lower, 0)

        # Interpolate native-frequency forecasts to daily for 14 days
        last_date = df['ds'].max()
        native_dates = [last_date + timedelta(days=data_freq_days * (i + 1)) for i in range(n_steps)]

        # Build daily dates for the full forecast period
        daily_dates = [last_date + timedelta(days=i + 1) for i in range(self.forecast_days)]

        # Interpolate ensemble values to daily
        native_days = np.array([(d - last_date).days for d in native_dates])
        daily_days = np.array([(d - last_date).days for d in daily_dates])

        # Add the last known point for smooth interpolation
        interp_x = np.concatenate([[0], native_days])
        interp_y = np.concatenate([[y[-1]], ensemble])
        interp_lower = np.concatenate([[y[-1]], lower])
        interp_upper = np.concatenate([[y[-1]], upper])

        daily_ensemble = np.interp(daily_days, interp_x, interp_y)
        daily_lower = np.interp(daily_days, interp_x, interp_lower)
        daily_upper = np.interp(daily_days, interp_x, interp_upper)

        daily_ensemble = np.maximum(daily_ensemble, 0)
        daily_lower = np.maximum(daily_lower, 0)

        forecast_records = []
        for i in range(self.forecast_days):
            forecast_records.append({
                'ds': daily_dates[i],
                'yhat': float(daily_ensemble[i]),
                'yhat_lower': float(daily_lower[i]),
                'yhat_upper': float(daily_upper[i])
            })

        result = {
            "virus_typ": virus_typ,
            "training_samples": n,
            "forecast_days": self.forecast_days,
            "data_frequency_days": data_freq_days,
            "forecast": forecast_records,
            "feature_importance": feature_importance,
            "model_version": "hw_ridge_v1",
            "confidence": float(self.confidence_level),
            "timestamp": datetime.utcnow()
        }

        logger.info(f"Forecast completed for {virus_typ}: {self.forecast_days} daily points from {n_steps} native-freq steps ({data_freq_days}d)")
        return result

    def save_forecast(self, forecast_data: Dict):
        """Save forecast to database."""
        logger.info("Saving forecast to database...")
        count = 0

        for item in forecast_data['forecast']:
            existing = self.db.query(MLForecast).filter(
                MLForecast.forecast_date == item['ds'],
                MLForecast.virus_typ == forecast_data['virus_typ']
            ).first()

            if existing:
                existing.predicted_value = item['yhat']
                existing.lower_bound = item['yhat_lower']
                existing.upper_bound = item['yhat_upper']
                existing.confidence = forecast_data.get('confidence', 0.95)
                existing.model_version = forecast_data['model_version']
                existing.features_used = forecast_data.get('feature_importance', {})
            else:
                forecast_record = MLForecast(
                    forecast_date=item['ds'],
                    virus_typ=forecast_data['virus_typ'],
                    predicted_value=item['yhat'],
                    lower_bound=item['yhat_lower'],
                    upper_bound=item['yhat_upper'],
                    confidence=forecast_data.get('confidence', 0.95),
                    model_version=forecast_data['model_version'],
                    features_used=forecast_data.get('feature_importance', {})
                )
                self.db.add(forecast_record)
                count += 1

        self.db.commit()
        logger.info(f"Saved {count} new forecast records")
        return count

    def run_forecasts_for_all_viruses(self):
        """Run forecasts for all relevant virus types."""
        virus_types = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A']

        results = {}
        for virus in virus_types:
            logger.info(f"Processing forecast for {virus}...")
            try:
                forecast = self.train_and_forecast(virus_typ=virus)
                if 'error' not in forecast:
                    self.save_forecast(forecast)
                results[virus] = forecast
            except Exception as e:
                logger.error(f"Forecast failed for {virus}: {e}")
                results[virus] = {"error": str(e)}

        return results
