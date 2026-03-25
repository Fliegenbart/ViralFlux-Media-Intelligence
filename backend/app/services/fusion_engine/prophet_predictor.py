"""Prophet-basierter Predictor für Outbreak-Vorhersage.

Wraps Facebook Prophet mit domänenspezifischen Regressoren
(Schulferien, Temperatur, Luftfeuchtigkeit) für 28-Tage-Vorhersage.
"""

from app.core.time import utc_now
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from app.models.database import (
    WastewaterAggregated, GanzimmunData,
    WeatherData, SchoolHolidays,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ProphetPredictor:
    """Facebook Prophet Wrapper mit externen Regressoren."""

    def __init__(self, db: Session):
        self.db = db
        self.model = None
        self.forecast_days = 28

    def prepare_data(
        self,
        virus_typ: str = 'Influenza A',
        lookback_days: int = 730,
        use_internal_target: bool = False,
        test_typ: str | None = None,
    ) -> pd.DataFrame:
        """Build training DataFrame mit ds, y und Regressor-Spalten.

        Wenn use_internal_target=True und GanzimmunData vorhanden,
        y = Positivrate (geglätteter 7-Tage-Durchschnitt).
        Sonst y = Abwasser-Viruslast.
        """
        start_date = datetime.now() - timedelta(days=lookback_days)

        # --- Target-Variable ---
        used_internal = False
        if use_internal_target and test_typ:
            lab_data = self.db.query(GanzimmunData).filter(
                GanzimmunData.test_typ == test_typ,
                GanzimmunData.datum >= start_date,
                GanzimmunData.anzahl_tests > 0,
            ).order_by(GanzimmunData.datum.asc()).all()

            if len(lab_data) >= 14:
                df = pd.DataFrame([{
                    'ds': d.datum,
                    'y': (d.positive_ergebnisse or 0) / d.anzahl_tests * 100,
                } for d in lab_data])
                # 7-Tage Rolling Average gegen Wochenend-Effekte
                df['y'] = df['y'].rolling(7, min_periods=1).mean()
                used_internal = True
                logger.info(f"Interne Labordaten als Target: {len(df)} Zeilen")

        if not used_internal:
            ww_data = self.db.query(WastewaterAggregated).filter(
                WastewaterAggregated.virus_typ == virus_typ,
                WastewaterAggregated.datum >= start_date,
            ).order_by(WastewaterAggregated.datum.asc()).all()

            if not ww_data:
                raise ValueError(f"Keine Abwasserdaten für {virus_typ}")

            df = pd.DataFrame([{
                'ds': d.datum,
                'y': d.viruslast,
            } for d in ww_data])

        df['ds'] = pd.to_datetime(df['ds'])

        # --- Regressoren ---

        # 1. Schulferien (binär)
        holidays = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum >= start_date - timedelta(days=30),
        ).all()

        def is_holiday(dt):
            for h in holidays:
                if h.start_datum <= dt <= h.end_datum:
                    return 1.0
            return 0.0

        df['school_holiday'] = df['ds'].apply(is_holiday)

        # 2. Temperatur (7-Tage-Durchschnitt) + Luftfeuchtigkeit
        weather = self.db.query(WeatherData).filter(
            WeatherData.datum >= start_date,
        ).order_by(WeatherData.datum.asc()).all()

        if weather:
            weather_df = pd.DataFrame([{
                'ds': pd.Timestamp(w.datum).normalize(),
                'temp': w.temperatur,
                'hum': w.luftfeuchtigkeit,
            } for w in weather])

            weather_daily = weather_df.groupby('ds').agg(
                temp=('temp', 'mean'), hum=('hum', 'mean')
            ).reset_index()
            weather_daily['temperature_7d_avg'] = weather_daily['temp'].rolling(7, min_periods=1).mean()
            weather_daily['humidity'] = weather_daily['hum']

            df = df.merge(
                weather_daily[['ds', 'temperature_7d_avg', 'humidity']],
                on='ds', how='left',
            )

        # Fehlende Regressoren füllen
        for col, default in [('temperature_7d_avg', 5.0), ('humidity', 70.0)]:
            if col not in df.columns:
                df[col] = default
            df[col] = df[col].ffill().bfill().fillna(default)

        df = df.dropna(subset=['y'])

        logger.info(
            f"ProphetPredictor: {len(df)} Zeilen für {virus_typ}, "
            f"Target={'interne_labdaten' if used_internal else 'abwasser'}"
        )
        return df

    def fit_and_predict(
        self,
        virus_typ: str = 'Influenza A',
        forecast_days: int = 28,
        use_internal_target: bool = False,
        test_typ: str | None = None,
    ) -> dict:
        """Prophet trainieren und Vorhersage generieren."""
        try:
            from prophet import Prophet
        except ImportError:
            logger.warning("Prophet nicht installiert, Fallback auf gespeicherte Prognosen")
            return self._fallback_from_stored(virus_typ)

        self.forecast_days = forecast_days

        df = self.prepare_data(
            virus_typ=virus_typ,
            use_internal_target=use_internal_target,
            test_typ=test_typ,
        )

        if len(df) < 14:
            raise ValueError(f"Zu wenig Daten für Prophet ({len(df)} Zeilen)")

        # Prophet konfigurieren
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            changepoint_prior_scale=0.05,
            interval_width=settings.CONFIDENCE_LEVEL,
        )
        m.add_regressor('school_holiday')
        m.add_regressor('temperature_7d_avg')
        m.add_regressor('humidity')

        train_cols = ['ds', 'y', 'school_holiday', 'temperature_7d_avg', 'humidity']
        m.fit(df[train_cols])
        self.model = m

        # Future-Dataframe mit Regressoren
        future = m.make_future_dataframe(periods=forecast_days)
        last_row = df.iloc[-1]

        future = future.merge(
            df[['ds', 'school_holiday', 'temperature_7d_avg', 'humidity']],
            on='ds', how='left',
        )
        future['school_holiday'] = future['school_holiday'].fillna(last_row['school_holiday'])
        future['temperature_7d_avg'] = future['temperature_7d_avg'].fillna(last_row['temperature_7d_avg'])
        future['humidity'] = future['humidity'].fillna(last_row['humidity'])

        forecast = m.predict(future)

        # Nur zukünftige Vorhersagen extrahieren
        future_mask = forecast['ds'] > df['ds'].max()
        future_fc = forecast[future_mask]

        # Trend-Richtung berechnen
        if len(future_fc) >= 2:
            slope = (future_fc['yhat'].iloc[-1] - future_fc['yhat'].iloc[0]) / len(future_fc)
            first_val = future_fc['yhat'].iloc[0]
            trend_pct = slope / first_val if first_val > 0 else 0
        else:
            trend_pct = 0.0

        return {
            'virus_typ': virus_typ,
            'forecast_days': forecast_days,
            'training_samples': len(df),
            'target_type': 'internal_lab' if use_internal_target else 'wastewater',
            'forecast': [
                {
                    'ds': row['ds'],
                    'yhat': max(0, row['yhat']),
                    'yhat_lower': max(0, row['yhat_lower']),
                    'yhat_upper': max(0, row['yhat_upper']),
                }
                for _, row in future_fc.iterrows()
            ],
            'trend_slope': float(trend_pct),
            'trend_direction': (
                'steigend' if trend_pct > 0.01
                else 'fallend' if trend_pct < -0.01
                else 'stabil'
            ),
            'timestamp': utc_now().isoformat(),
        }

    def _fallback_from_stored(self, virus_typ: str) -> dict | None:
        """Gespeicherte MLForecast-Daten als Fallback verwenden."""
        from app.models.database import MLForecast

        latest = self.db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ,
        ).order_by(MLForecast.created_at.desc()).first()

        if not latest:
            return None

        forecasts = self.db.query(MLForecast).filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.created_at >= latest.created_at - timedelta(seconds=10),
        ).order_by(MLForecast.forecast_date.asc()).all()

        if len(forecasts) < 2:
            return None

        slope = (forecasts[-1].predicted_value - forecasts[0].predicted_value) / len(forecasts)
        first_val = forecasts[0].predicted_value or 1
        trend_pct = slope / first_val if first_val > 0 else 0

        return {
            'virus_typ': virus_typ,
            'forecast_days': len(forecasts),
            'training_samples': 0,
            'target_type': 'stored_forecast',
            'forecast': [
                {
                    'ds': f.forecast_date,
                    'yhat': f.predicted_value,
                    'yhat_lower': f.lower_bound or f.predicted_value * 0.8,
                    'yhat_upper': f.upper_bound or f.predicted_value * 1.2,
                }
                for f in forecasts
            ],
            'trend_slope': float(trend_pct),
            'trend_direction': (
                'steigend' if trend_pct > 0.01
                else 'fallend' if trend_pct < -0.01
                else 'stabil'
            ),
            'timestamp': utc_now().isoformat(),
        }
