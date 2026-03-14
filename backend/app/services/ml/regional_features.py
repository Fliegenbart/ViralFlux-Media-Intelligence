"""Regional feature engineering for per-Bundesland ML forecasting.

This module adds regional data aggregation to the national ML pipeline.
Instead of averaging all 27 AMELAG sites into 1 national signal,
it builds per-Bundesland feature sets including:
- Regional wastewater viral load (from individual AMELAG sites)
- Regional SurvStat incidence (from weekly reporting data)
- Regional weather features (temperature, humidity)
- Regional pollen severity (DWD index)
- Regional school holidays (binary per-Bundesland)

Usage:
    from app.services.ml.regional_features import RegionalFeatureBuilder
    builder = RegionalFeatureBuilder(db)
    df = builder.build_regional_training_data(
        virus_typ="Influenza A",
        bundesland="BY",
        lookback_days=900,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    PollenData,
    SchoolHolidays,
    SurvstatWeeklyData,
    WastewaterData,
    WeatherData,
)
from app.services.ml.forecast_service import SURVSTAT_VIRUS_MAP

logger = logging.getLogger(__name__)

# Map cities to Bundesland codes (BrightSky/OpenWeather cities)
CITY_TO_BUNDESLAND: dict[str, str] = {
    "Berlin": "BE",
    "Hamburg": "HH",
    "Munich": "BY", "München": "BY",
    "Cologne": "NW", "Köln": "NW",
    "Frankfurt": "HE", "Frankfurt am Main": "HE",
    "Stuttgart": "BW",
    "Düsseldorf": "NW",
    "Leipzig": "SN",
    "Dortmund": "NW",
    "Essen": "NW",
    "Bremen": "HB",
    "Dresden": "SN",
    "Hannover": "NI",
    "Nuremberg": "BY", "Nürnberg": "BY",
    "Duisburg": "NW",
    "Bochum": "NW",
    "Wuppertal": "NW",
    "Bielefeld": "NW",
    "Bonn": "NW",
    "Mannheim": "BW",
    "Karlsruhe": "BW",
    "Augsburg": "BY",
    "Wiesbaden": "HE",
    "Mainz": "RP",
    "Kiel": "SH",
    "Magdeburg": "ST",
    "Erfurt": "TH",
    "Schwerin": "MV",
    "Potsdam": "BB",
    "Saarbrücken": "SL",
}

ALL_BUNDESLAENDER = [
    "BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV",
    "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH",
]

BUNDESLAND_NAMES: dict[str, str] = {
    "BW": "Baden-Württemberg", "BY": "Bayern", "BE": "Berlin",
    "BB": "Brandenburg", "HB": "Bremen", "HH": "Hamburg",
    "HE": "Hessen", "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen", "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz", "SL": "Saarland",
    "SN": "Sachsen", "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein", "TH": "Thüringen",
}


class RegionalFeatureBuilder:
    """Build per-Bundesland training features from all available data sources."""

    def __init__(self, db: Session):
        self.db = db

    def build_regional_training_data(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        lookback_days: int = 900,
    ) -> pd.DataFrame:
        """Build feature DataFrame for a specific Bundesland.

        Returns a DataFrame with columns:
        - ds: date
        - y: regional viral load (target)
        - amelag_regional_lag4/7: regional wastewater lags
        - survstat_regional: regional SurvStat incidence
        - temperature_avg_7d: 7-day rolling mean temperature
        - humidity_avg_7d: 7-day rolling mean humidity
        - pollen_severity_max: max pollen index across types
        - schulferien_regional: binary, specific to Bundesland
        - trend_momentum_7d: 7-day momentum
        """
        logger.info("Building regional features: %s / %s", virus_typ, bundesland)
        start_date = datetime.now() - timedelta(days=lookback_days)
        bl_name = BUNDESLAND_NAMES.get(bundesland, bundesland)

        # 1. Regional wastewater (individual AMELAG sites in this Bundesland)
        df = self._get_regional_wastewater(virus_typ, bundesland, bl_name, start_date)
        if df.empty:
            logger.warning("No wastewater data for %s / %s — falling back to national", virus_typ, bundesland)
            return pd.DataFrame()

        # 2. Regional SurvStat incidence
        df = self._add_regional_survstat(df, virus_typ, bl_name, start_date)

        # 3. Regional weather
        df = self._add_regional_weather(df, bundesland, start_date)

        # 4. Regional pollen
        df = self._add_regional_pollen(df, bundesland, start_date)

        # 5. Regional school holidays
        df = self._add_regional_holidays(df, bl_name)

        # 6. Lag features
        df["amelag_regional_lag4"] = df["y"].shift(4)
        df["amelag_regional_lag7"] = df["y"].shift(7)
        df["trend_momentum_7d"] = df["y"].diff(7) / df["y"].shift(7).replace(0, np.nan)
        df["survstat_regional_lag7"] = df["survstat_regional"].shift(7)
        df["survstat_regional_lag14"] = df["survstat_regional"].shift(14)

        # 7. Finalize: drop warmup rows, fill NaN
        df = df.iloc[14:].copy()  # Drop first 14 rows for lag warmup
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(0.0)
        df = df.reset_index(drop=True)

        logger.info(
            "Regional features ready: %s / %s — %d rows, %d features",
            virus_typ, bundesland, len(df), len(df.columns),
        )
        return df

    def _get_regional_wastewater(
        self, virus_typ: str, bl_code: str, bl_name: str, start_date: datetime,
    ) -> pd.DataFrame:
        """Aggregate AMELAG wastewater data for a specific Bundesland."""
        rows = (
            self.db.query(
                WastewaterData.datum,
                func.avg(WastewaterData.viruslast).label("viral_load_avg"),
                func.count(WastewaterData.id).label("n_sites"),
            )
            .filter(
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.bundesland.in_([bl_code, bl_name]),
                WastewaterData.datum >= start_date,
                WastewaterData.viruslast.isnot(None),
            )
            .group_by(WastewaterData.datum)
            .order_by(WastewaterData.datum.asc())
            .all()
        )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([
            {"ds": pd.to_datetime(r.datum), "y": float(r.viral_load_avg or 0), "n_sites": int(r.n_sites)}
            for r in rows
        ])
        return df.sort_values("ds").reset_index(drop=True)

    def _add_regional_survstat(
        self, df: pd.DataFrame, virus_typ: str, bl_name: str, start_date: datetime,
    ) -> pd.DataFrame:
        """Add regional SurvStat incidence as a feature."""
        diseases = SURVSTAT_VIRUS_MAP.get(virus_typ, [])
        if not diseases:
            df["survstat_regional"] = 0.0
            return df

        rows = (
            self.db.query(
                SurvstatWeeklyData.week_start,
                func.sum(SurvstatWeeklyData.incidence).label("total_incidence"),
            )
            .filter(
                func.lower(SurvstatWeeklyData.disease).in_(diseases),
                SurvstatWeeklyData.bundesland == bl_name,
                SurvstatWeeklyData.week > 0,
                SurvstatWeeklyData.week_start >= start_date,
            )
            .group_by(SurvstatWeeklyData.week_start)
            .order_by(SurvstatWeeklyData.week_start.asc())
            .all()
        )

        if rows:
            surv_df = pd.DataFrame([
                {"ds": pd.to_datetime(r.week_start), "survstat_regional": float(r.total_incidence or 0)}
                for r in rows
            ])
            # Normalize to [0, 1]
            max_val = surv_df["survstat_regional"].max() or 1.0
            surv_df["survstat_regional"] = surv_df["survstat_regional"] / max_val
            df = df.merge(surv_df, on="ds", how="left")
            df["survstat_regional"] = df["survstat_regional"].ffill().fillna(0.0)
        else:
            df["survstat_regional"] = 0.0

        return df

    def _add_regional_weather(
        self, df: pd.DataFrame, bl_code: str, start_date: datetime,
    ) -> pd.DataFrame:
        """Add regional weather features (temperature, humidity)."""
        # Find cities in this Bundesland
        cities = [city for city, code in CITY_TO_BUNDESLAND.items() if code == bl_code]
        if not cities:
            df["temperature_avg_7d"] = 0.0
            df["humidity_avg_7d"] = 0.0
            return df

        rows = (
            self.db.query(
                WeatherData.datum,
                func.avg(WeatherData.temperatur).label("temp"),
                func.avg(WeatherData.luftfeuchtigkeit).label("humidity"),
            )
            .filter(
                WeatherData.city.in_(cities),
                WeatherData.datum >= start_date,
                WeatherData.data_type == "CURRENT",
            )
            .group_by(WeatherData.datum)
            .order_by(WeatherData.datum.asc())
            .all()
        )

        if rows:
            weather_df = pd.DataFrame([
                {"ds": pd.to_datetime(r.datum), "temp": float(r.temp or 0), "humidity": float(r.humidity or 0)}
                for r in rows
            ])
            df = df.merge(weather_df, on="ds", how="left")
            df["temp"] = df["temp"].ffill().fillna(0.0)
            df["humidity"] = df["humidity"].ffill().fillna(0.0)
        else:
            df["temp"] = 0.0
            df["humidity"] = 0.0

        # 7-day rolling averages
        df["temperature_avg_7d"] = df["temp"].rolling(7, min_periods=1).mean()
        df["humidity_avg_7d"] = df["humidity"].rolling(7, min_periods=1).mean()
        df = df.drop(columns=["temp", "humidity"], errors="ignore")

        return df

    def _add_regional_pollen(
        self, df: pd.DataFrame, bl_code: str, start_date: datetime,
    ) -> pd.DataFrame:
        """Add regional pollen severity (max across all pollen types)."""
        rows = (
            self.db.query(
                PollenData.datum,
                func.max(PollenData.pollen_index).label("max_index"),
            )
            .filter(
                PollenData.region_code == bl_code,
                PollenData.datum >= start_date,
            )
            .group_by(PollenData.datum)
            .order_by(PollenData.datum.asc())
            .all()
        )

        if rows:
            pollen_df = pd.DataFrame([
                {"ds": pd.to_datetime(r.datum), "pollen_severity_max": float(r.max_index or 0)}
                for r in rows
            ])
            df = df.merge(pollen_df, on="ds", how="left")
            df["pollen_severity_max"] = df["pollen_severity_max"].ffill().fillna(0.0)
        else:
            df["pollen_severity_max"] = 0.0

        return df

    def _add_regional_holidays(self, df: pd.DataFrame, bl_name: str) -> pd.DataFrame:
        """Add regional school holiday indicator (binary)."""
        holidays = (
            self.db.query(SchoolHolidays)
            .filter(SchoolHolidays.bundesland == bl_name)
            .all()
        )

        holiday_ranges = [(h.start_datum, h.end_datum) for h in holidays]

        def is_holiday(d: datetime) -> float:
            for start, end in holiday_ranges:
                if start <= d <= end:
                    return 1.0
            return 0.0

        df["schulferien_regional"] = df["ds"].apply(is_holiday)
        return df

    def get_available_bundeslaender(self, virus_typ: str = "Influenza A") -> list[str]:
        """Return list of Bundesland codes that have wastewater data for this virus."""
        rows = (
            self.db.query(WastewaterData.bundesland)
            .filter(
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.viruslast.isnot(None),
            )
            .distinct()
            .all()
        )

        available = set()
        for (bl,) in rows:
            # Map full name to code if needed
            if bl in BUNDESLAND_NAMES:
                available.add(bl)
            else:
                for code, name in BUNDESLAND_NAMES.items():
                    if name == bl:
                        available.add(code)
                        break

        return sorted(available)

    def build_all_regions(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
    ) -> dict[str, pd.DataFrame]:
        """Build training data for all available Bundesländer.

        Returns dict mapping Bundesland code → feature DataFrame.
        """
        available = self.get_available_bundeslaender(virus_typ)
        logger.info("Building regional features for %d Bundesländer: %s", len(available), available)

        results = {}
        for bl_code in available:
            df = self.build_regional_training_data(
                virus_typ=virus_typ,
                bundesland=bl_code,
                lookback_days=lookback_days,
            )
            if not df.empty and len(df) >= 30:  # Need at least 30 data points
                results[bl_code] = df
            else:
                logger.warning("Skipping %s: insufficient data (%d rows)", bl_code, len(df))

        logger.info(
            "Regional features complete: %d/%d Bundesländer with sufficient data",
            len(results), len(available),
        )
        return results
