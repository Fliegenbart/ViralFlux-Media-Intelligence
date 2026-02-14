import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from prophet import Prophet
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
    """ML-basierter Prognosedienst mit Prophet."""
    
    def __init__(self, db: Session):
        self.db = db
        self.forecast_days = settings.FORECAST_DAYS
        self.confidence_level = settings.CONFIDENCE_LEVEL
    
    def prepare_training_data(
        self, 
        virus_typ: str = 'Influenza A',
        lookback_days: int = 180
    ) -> pd.DataFrame:
        """
        Bereite Trainingsdaten vor mit allen Features.
        
        Features:
        - Viruslast (Abwasser) - Hauptziel
        - Google Trends Score
        - ARE/ILI Inzidenzen
        - Temperatur, Luftfeuchtigkeit
        - Schulferien (Binär)
        - Lag Features (7, 14 Tage)
        
        Args:
            virus_typ: Virustyp für Prognose
            lookback_days: Anzahl Tage zurück für Training
        
        Returns:
            DataFrame mit allen Features
        """
        logger.info(f"Preparing training data for {virus_typ}")
        
        start_date = datetime.now() - timedelta(days=lookback_days)
        
        # 1. Abwasser-Viruslast (Ziel-Variable)
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
        
        # 2. Google Trends - Durchschnitt über relevante Keywords
        trends_keywords = ['Grippe', 'Erkältung', 'Fieber']
        trends = self.db.query(GoogleTrendsData).filter(
            GoogleTrendsData.keyword.in_(trends_keywords),
            GoogleTrendsData.datum >= start_date
        ).all()
        
        trends_df = pd.DataFrame([{
            'ds': t.datum,
            'keyword': t.keyword,
            'interest_score': t.interest_score
        } for t in trends])
        
        if not trends_df.empty:
            # Durchschnitt über alle Keywords pro Tag
            trends_avg = trends_df.groupby('ds')['interest_score'].mean().reset_index()
            trends_avg.columns = ['ds', 'trends_score']
            df = df.merge(trends_avg, on='ds', how='left')
        else:
            df['trends_score'] = 0
        
        # 3. GrippeWeb ARE Inzidenzen
        grippeweb = self.db.query(GrippeWebData).filter(
            GrippeWebData.erkrankung_typ == 'ARE',
            GrippeWebData.datum >= start_date,
            GrippeWebData.bundesland.is_(None)  # Bundesweit
        ).all()
        
        grippeweb_df = pd.DataFrame([{
            'ds': g.datum,
            'are_inzidenz': g.inzidenz
        } for g in grippeweb])
        
        if not grippeweb_df.empty:
            df = df.merge(grippeweb_df, on='ds', how='left')
        else:
            df['are_inzidenz'] = 0
        
        # 4. Wetterdaten - Durchschnitt über Städte
        weather = self.db.query(WeatherData).filter(
            WeatherData.datum >= start_date
        ).all()
        
        weather_df = pd.DataFrame([{
            'ds': w.datum.date(),
            'temperatur': w.temperatur,
            'luftfeuchtigkeit': w.luftfeuchtigkeit
        } for w in weather])
        
        if not weather_df.empty:
            weather_avg = weather_df.groupby('ds').agg({
                'temperatur': 'mean',
                'luftfeuchtigkeit': 'mean'
            }).reset_index()
            weather_avg['ds'] = pd.to_datetime(weather_avg['ds'])
            df = df.merge(weather_avg, on='ds', how='left')
        else:
            df['temperatur'] = 15  # Default
            df['luftfeuchtigkeit'] = 70  # Default
        
        # 5. Schulferien (Binär)
        df['schulferien'] = df['ds'].apply(
            lambda d: 1 if self._is_holiday(d) else 0
        )
        
        # 6. Lag Features (Viruslast vor 7 und 14 Tagen)
        df['viruslast_lag7'] = df['y'].shift(7)
        df['viruslast_lag14'] = df['y'].shift(14)
        
        # 7. Moving Averages
        df['viruslast_ma7'] = df['y'].rolling(window=7, min_periods=1).mean()
        df['trends_ma7'] = df['trends_score'].rolling(window=7, min_periods=1).mean()
        
        # NaN entfernen
        df = df.fillna(method='bfill').fillna(method='ffill')
        
        logger.info(f"Training data prepared: {len(df)} rows, {len(df.columns)} features")
        return df
    
    def _is_holiday(self, datum: datetime) -> bool:
        """Prüfe ob Datum in Schulferien liegt."""
        return self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= datum,
            SchoolHolidays.end_datum >= datum
        ).first() is not None
    
    def train_and_forecast(
        self, 
        virus_typ: str = 'Influenza A'
    ) -> Dict:
        """
        Trainiere Prophet-Modell und erstelle Prognose.
        
        Args:
            virus_typ: Virustyp für Prognose
        
        Returns:
            Dict mit Prognose-Daten
        """
        logger.info(f"Training Prophet model for {virus_typ}")
        
        # Trainingsdaten vorbereiten
        df = self.prepare_training_data(virus_typ=virus_typ)
        
        if df.empty or len(df) < 30:
            logger.error(f"Insufficient data for training ({len(df)} rows)")
            return {"error": "Insufficient training data"}
        
        # Prophet-Modell initialisieren
        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=True,
            changepoint_prior_scale=0.05,  # Flexibilität für Trend-Änderungen
            interval_width=self.confidence_level
        )
        
        # Regressoren hinzufügen
        regressors = [
            'trends_score',
            'are_inzidenz',
            'temperatur',
            'luftfeuchtigkeit',
            'schulferien',
            'viruslast_lag7',
            'viruslast_lag14',
            'trends_ma7'
        ]
        
        for regressor in regressors:
            if regressor in df.columns:
                model.add_regressor(regressor)
        
        # Modell trainieren
        logger.info("Fitting Prophet model...")
        model.fit(df[['ds', 'y'] + [r for r in regressors if r in df.columns]])
        
        # Zukünftige Daten vorbereiten
        future = model.make_future_dataframe(
            periods=self.forecast_days,
            freq='D'
        )
        
        # Regressoren für Zukunft vorbereiten
        # (Vereinfachung: Letzte bekannte Werte verwenden)
        for regressor in regressors:
            if regressor in df.columns:
                last_value = df[regressor].iloc[-1]
                future[regressor] = last_value
        
        # Prognose erstellen
        logger.info("Generating forecast...")
        forecast = model.predict(future)
        
        # Nur zukünftige Werte
        forecast_future = forecast[forecast['ds'] > df['ds'].max()]
        
        # Feature Importance (approximiert)
        feature_importance = {}
        for regressor in regressors:
            if regressor in df.columns:
                # Korrelation mit Ziel-Variable
                corr = df[['y', regressor]].corr().iloc[0, 1]
                feature_importance[regressor] = abs(corr)
        
        result = {
            "virus_typ": virus_typ,
            "training_samples": len(df),
            "forecast_days": self.forecast_days,
            "forecast": forecast_future[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict('records'),
            "feature_importance": feature_importance,
            "model_version": "prophet_v1",
            "timestamp": datetime.utcnow()
        }
        
        logger.info(f"Forecast completed for {virus_typ}: {len(forecast_future)} days")
        return result
    
    def save_forecast(self, forecast_data: Dict):
        """Speichere Prognose in Datenbank."""
        logger.info("Saving forecast to database...")
        
        count = 0
        for item in forecast_data['forecast']:
            # Prüfe ob bereits existiert
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
        """Erstelle Prognosen für alle relevanten Viren."""
        virus_types = ['Influenza A', 'Influenza B', 'SARS-CoV-2', 'RSV A', 'RSV B']
        
        results = {}
        for virus in virus_types:
            logger.info(f"Processing forecast for {virus}...")
            forecast = self.train_and_forecast(virus_typ=virus)
            
            if 'error' not in forecast:
                self.save_forecast(forecast)
                results[virus] = forecast
            else:
                results[virus] = forecast
        
        return results
