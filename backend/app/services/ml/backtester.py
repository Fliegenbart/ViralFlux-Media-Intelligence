"""BacktestService — Modell-Kalibrierung via historischem Backtesting.

Simuliert den historischen Score-/Forecast-Stack für jeden Tag in der
Kundenhistorie, optimiert Gewichte via Ridge Regression und generiert
begleitende Insights.
"""

from __future__ import annotations
from app.core.time import utc_now

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
import math
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor
import logging

from app.models.database import (
    WastewaterAggregated,
    GanzimmunData,
    GoogleTrendsData,
    WeatherData,
    SchoolHolidays,
    AREKonsultation,
    SurvstatWeeklyData,
    GrippeWebData,
    NotaufnahmeSyndromData,
    LabConfiguration,
    BacktestRun,
    BacktestPoint,
)
from app.services.ml.forecast_contracts import (
    DEFAULT_DECISION_BASELINE_WINDOW_DAYS,
    DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
    DEFAULT_DECISION_HORIZON_DAYS,
    HEURISTIC_EVENT_SCORE_SOURCE,
    heuristic_event_score_from_forecast,
)
from app.services.ml import backtester_metrics

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
    DEFAULT_MARKET_HORIZON_DAYS = DEFAULT_DECISION_HORIZON_DAYS
    DEFAULT_MIN_TRAIN_POINTS = 20
    DECISION_EVENT_THRESHOLD_PCT = DEFAULT_DECISION_EVENT_THRESHOLD_PCT
    DECISION_BASELINE_WINDOW_DAYS = DEFAULT_DECISION_BASELINE_WINDOW_DAYS
    QUALITY_GATE_TTD_TARGET_DAYS = 10
    QUALITY_GATE_HIT_RATE_TARGET_PCT = 70.0
    QUALITY_GATE_P90_ERROR_REL_TARGET_PCT = 35.0
    QUALITY_GATE_LEAD_TARGET_DAYS = 7
    DECISION_EVENT_PROBA_THRESHOLD = 0.55
    SURVSTAT_TARGET_ALIASES = {
        "SURVSTAT": "Influenza, saisonal",
        "ALL": "Influenza, saisonal",
        "MYCOPLASMA": "mycoplasma",
        "KEUCHHUSTEN": "keuchhusten",
        "PNEUMOKOKKEN": "pneumokokken",
        "H_INFLUENZAE": "Parainfluenza",
    }

    # Cross-disease pairs: epidemiologisch sinnvolle Korrelationen
    CROSS_DISEASE_MAP: dict[str, list[str]] = {
        "Influenza A": ["RSV A", "SARS-CoV-2"],
        "Influenza B": ["Influenza A", "SARS-CoV-2"],
        "SARS-CoV-2": ["Influenza A", "Influenza B"],
        "RSV A": ["Influenza A", "Influenza B"],
    }

    # SURVSTAT-Krankheiten die Abwasser-Monitoring haben → VIRAL Features nutzen
    SURVSTAT_VIRAL_DISEASES: set[str] = {
        "Influenza, saisonal",
        "COVID-19",
        "RSV (Meldepflicht gemäß IfSG)",
        "RSV (Meldepflicht gemäß Landesmeldeverordnung)",
    }

    # SurvStat Cross-Disease: verwandte Krankheiten als Features
    SURVSTAT_CROSS_DISEASE_MAP: dict[str, list[str]] = {
        "Influenza, saisonal": ["RSV (Meldepflicht gemäß IfSG)", "Mycoplasma", "Parainfluenza"],
        "Mycoplasma": ["Keuchhusten (Meldepflicht gemäß IfSG)", "Influenza, saisonal", "Parainfluenza"],
        "Keuchhusten (Meldepflicht gemäß IfSG)": ["Mycoplasma", "Influenza, saisonal"],
        "Keuchhusten (Meldepflicht gemäß Landesmeldeverordnung)": ["Mycoplasma", "Influenza, saisonal"],
        "Pneumokokken (Meldepflicht gemäß IfSG)": ["Influenza, saisonal", "RSV (Meldepflicht gemäß IfSG)"],
        "Parainfluenza": ["Influenza, saisonal", "RSV (Meldepflicht gemäß IfSG)", "Mycoplasma"],
        "RSV (Meldepflicht gemäß IfSG)": ["Influenza, saisonal", "Parainfluenza"],
        "RSV (Meldepflicht gemäß Landesmeldeverordnung)": ["Influenza, saisonal", "Parainfluenza"],
        "COVID-19": ["Influenza, saisonal", "RSV (Meldepflicht gemäß IfSG)"],
    }

    # Basis-Features (krankheitsunabhängig)
    # Distributed-Lag + Residual-Modellierung.
    # - target_level/lag entfernt (90% Importance = Nachlauf)
    # - Abwasser als 4 Lag-Punkte + Slope + Max (Lead nutzen)
    # - Modell trainiert auf RESIDUAL (y - seasonal_baseline)
    BASE_FEATURE_COLS: list[str] = [
        "seasonal_baseline",
        "target_level",
        "target_roc",
        "week_sin",
        "week_cos",
        "school_start_float",
        "weather_temp",
        "weather_humidity",
        "trends_raw",
        "grippeweb_are",
        "notaufnahme_ari",
    ]

    # Kompakte Features für kleine Datasets (< 35 Trainingspunkte)
    COMPACT_BASE_COLS: list[str] = [
        "seasonal_baseline",
        "target_level",
        "target_roc",
        "week_sin",
        "week_cos",
        "weather_temp",
        "grippeweb_are",
        "notaufnahme_ari",
    ]

    COMPACT_VIRAL_COLS: list[str] = COMPACT_BASE_COLS + [
        "ww_lag0w",
        "ww_lag2w",
    ]

    COMPACT_SURVSTAT_COLS: list[str] = COMPACT_BASE_COLS + [
        "survstat_xdisease_1",
    ]

    # Virale Targets: Distributed-Lag Abwasser
    VIRAL_FEATURE_COLS: list[str] = BASE_FEATURE_COLS + [
        "ww_lag0w",
        "ww_lag1w",
        "ww_lag2w",
        "ww_lag3w",
        "ww_max_3w",
        "ww_slope_2w",
        "positivity_raw",
        "xdisease_load",
    ]

    # SURVSTAT-Targets: Cross-Disease statt Abwasser
    SURVSTAT_FEATURE_COLS: list[str] = BASE_FEATURE_COLS + [
        "survstat_xdisease_1",
        "survstat_xdisease_2",
    ]

    # Legacy-Kompatibilität
    ENHANCED_FEATURE_COLS: list[str] = VIRAL_FEATURE_COLS

    # XGBoost auf SURVSTAT: rein autoregressive Features (kein bio/psycho/context)
    XGBOOST_SURVSTAT_FEATURES: list[str] = [
        "y_lag1", "y_lag2", "y_lag4", "y_lag8", "y_lag52",
        "y_roll4_mean", "y_roll4_std", "y_roll8_mean",
        "y_roc1", "y_roc4",
        "week_sin", "week_cos",
        "y_level",
    ]

    # Gelo-relevante Atemwegsinfekte (ohne COVID-19, da zu dominant)
    GELO_ATEMWEG_DISEASES: list[str] = [
        "Influenza, saisonal",
        "RSV (Meldepflicht gemäß IfSG)",
        "RSV (Meldepflicht gemäß Landesmeldeverordnung)",
        "Keuchhusten (Meldepflicht gemäß IfSG)",
        "Mycoplasma",
        "Parainfluenza",
    ]

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

    def _amelag_raw_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> Optional[float]:
        """Rohe AMELAG-Viruslast an target_date (nicht normalisiert)."""
        effective = available_cutoff or target
        current = self.db.query(WastewaterAggregated).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum <= effective,
            self._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
        ).order_by(WastewaterAggregated.datum.desc()).first()

        if not current or not current.viruslast:
            return None
        return float(current.viruslast)

    def _wastewater_lags_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        """Distributed-Lag Abwasser: Werte bei 0/1/2/3 Wochen zurück + Ableitungen."""
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

        vals: list[float] = []
        result: dict[str, float] = {}
        for lag_w in range(4):  # 0, 1, 2, 3 Wochen
            cutoff = effective - timedelta(weeks=lag_w)
            row = self.db.query(WastewaterAggregated).filter(
                WastewaterAggregated.virus_typ == virus_typ,
                WastewaterAggregated.datum <= cutoff,
                self._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, cutoff),
            ).order_by(WastewaterAggregated.datum.desc()).first()
            v = min(row.viruslast / max_load, 1.0) if row and row.viruslast else 0.0
            result[f"ww_lag{lag_w}w"] = round(v, 4)
            vals.append(v)

        result["ww_max_3w"] = round(max(vals), 4)
        result["ww_slope_2w"] = round(vals[0] - vals[2], 4) if len(vals) > 2 else 0.0
        return result

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
            slope = float((recent - previous) / previous)
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
        components = self._weather_risk_components_at_date(target, available_cutoff)
        return components["composite"]

    def _weather_risk_components_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        """Wetter-Risiko-Einzelkomponenten an target_date."""
        effective = available_cutoff or target
        latest = self.db.query(WeatherData).filter(
            WeatherData.datum <= effective,
            self._asof_filter(WeatherData, WeatherData.datum, effective),
        ).order_by(WeatherData.datum.desc()).limit(5).all()

        if not latest:
            return {"temp_factor": 0.3, "uv_factor": 0.3, "humidity_factor": 0.6, "composite": 0.3}

        temps = [w.temperatur for w in latest if w.temperatur is not None]
        avg_temp = sum(temps) / len(temps) if temps else 5.0
        avg_uv = sum(w.uv_index or 0 for w in latest) / len(latest)
        avg_humidity = sum(w.luftfeuchtigkeit or 60 for w in latest) / len(latest)

        temp_factor = max(0, min(1, (20 - avg_temp) / 25))
        uv_factor = max(0, min(1, (8 - avg_uv) / 8))
        humidity_factor = max(0, min(1, avg_humidity / 100))
        composite = temp_factor * 0.4 + uv_factor * 0.35 + humidity_factor * 0.25

        return {
            "temp_factor": round(temp_factor, 4),
            "uv_factor": round(uv_factor, 4),
            "humidity_factor": round(humidity_factor, 4),
            "composite": round(composite, 4),
        }

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

    def _cross_disease_load_at_date(
        self,
        target: datetime,
        xdisease_viruses: list[str],
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        """Durchschnittliche normalisierte Viruslast der Korrelations-Viren (7-Tage-Fenster)."""
        if not xdisease_viruses:
            return 0.0
        effective = available_cutoff or target
        week_ago = effective - timedelta(days=7)

        from sqlalchemy import func as sa_func
        avg_load = self.db.query(
            sa_func.avg(WastewaterAggregated.viruslast_normalisiert)
        ).filter(
            WastewaterAggregated.virus_typ.in_(xdisease_viruses),
            WastewaterAggregated.datum >= week_ago,
            WastewaterAggregated.datum <= effective,
            self._asof_filter(WastewaterAggregated, WastewaterAggregated.datum, effective),
        ).scalar()

        return round(float(avg_load or 0.0), 4)

    def _grippeweb_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        """GrippeWeb ARE-Inzidenz (syndromisch, krankheitsunabhängig)."""
        effective = available_cutoff or target
        row = self.db.query(GrippeWebData).filter(
            GrippeWebData.erkrankung_typ == "ARE",
            GrippeWebData.altersgruppe == "Gesamt",
            GrippeWebData.datum <= effective,
        ).order_by(GrippeWebData.datum.desc()).first()
        # Normalisierung: ARE-Inzidenz typisch 500-5000 pro 100k → /10000 auf [0, 0.5]
        are_val = float(row.inzidenz / 10000.0) if row and row.inzidenz else 0.0
        return {"grippeweb_are": round(min(are_val, 1.0), 4)}

    def _notaufnahme_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        """Notaufnahme ARI 7-Tage-MA (tagesaktuell, krankheitsunabhängig)."""
        effective = available_cutoff or target
        row = self.db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.syndrome == "ARI",
            NotaufnahmeSyndromData.age_group == "00+",
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.datum <= effective,
        ).order_by(NotaufnahmeSyndromData.datum.desc()).first()
        ari_val = float(row.relative_cases_7day_ma) if row and row.relative_cases_7day_ma else 0.0
        return {"notaufnahme_ari": round(ari_val, 4)}

    def _survstat_cross_disease_at_date(
        self,
        target: datetime,
        target_disease: str,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        """SurvStat-Inzidenz verwandter Krankheiten (für SURVSTAT-Targets)."""
        related = self.SURVSTAT_CROSS_DISEASE_MAP.get(target_disease, [])
        effective = available_cutoff or target
        result = {"survstat_xdisease_1": 0.0, "survstat_xdisease_2": 0.0}

        for i, disease in enumerate(related[:2]):
            row = self.db.query(SurvstatWeeklyData).filter(
                SurvstatWeeklyData.disease == disease,
                SurvstatWeeklyData.bundesland == "Gesamt",
                SurvstatWeeklyData.week_start <= effective,
                SurvstatWeeklyData.available_time <= effective,
            ).order_by(SurvstatWeeklyData.week_start.desc()).first()
            if row and row.incidence is not None:
                # Normalisierung: Inzidenz /1000, gekappt auf 1.0
                result[f"survstat_xdisease_{i + 1}"] = round(
                    min(float(row.incidence) / 1000.0, 1.0), 4
                )

        return result

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

    def _market_proxy_at_date(
        self,
        target: datetime,
        bio: float,
        wastewater: float,
        positivity: float,
    ) -> float:
        """Market disruption proxy from epidemiological signals.

        Without customer-specific order data, we approximate market demand
        using a composite of:
        - Bio activity (weighted 0.4): high infection load → pharmacy demand
        - Wastewater trend (weighted 0.3): leading indicator for OTC demand
        - Positivity rate (weighted 0.3): confirmed infections → treatment demand

        The non-linear transform (power 0.7) emphasizes moderate-to-high
        signal levels where market disruption becomes meaningful.
        """
        raw = bio * 0.4 + wastewater * 0.3 + min(positivity * 5.0, 1.0) * 0.3
        # Non-linear emphasis on higher signal ranges
        return min(raw ** 0.7, 1.0)

    def _compute_sub_scores_at_date(
        self,
        target: datetime,
        virus_typ: str,
        delay_rules: Optional[dict[str, int]] = None,
        target_disease: Optional[str] = None,
    ) -> dict[str, float]:
        """Berechnet Dimensions-Scores + Rohsignale an einem historischen Datum."""
        # Cache: Same date + virus_typ + target_disease → same result
        if not hasattr(self, "_scores_cache"):
            self._scores_cache: dict[str, dict[str, float]] = {}
        cache_key = f"{target.isoformat()}|{virus_typ}|{target_disease}"
        if cache_key in self._scores_cache:
            return self._scores_cache[cache_key]

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
        ww_lags = self._wastewater_lags_at_date(target, virus_typ, available_cutoff=wastewater_cutoff)
        positivity = self._positivity_rate_at_date(target, virus_typ, available_cutoff=positivity_cutoff)
        are_consultation = self._are_consultation_at_date(target, available_cutoff=are_cutoff)
        trends = self._trends_at_date(target, available_cutoff=trends_cutoff)
        weather_components = self._weather_risk_components_at_date(target, available_cutoff=weather_cutoff)
        weather = weather_components["composite"]
        school_start = self._school_start_at_date(target, available_cutoff=holidays_cutoff)

        # Cross-disease signal (wastewater-basiert)
        xdisease_viruses = self.CROSS_DISEASE_MAP.get(virus_typ, [])
        xdisease_load = self._cross_disease_load_at_date(target, xdisease_viruses, available_cutoff=wastewater_cutoff)

        # GrippeWeb + Notaufnahme (syndromisch, krankheitsunabhängig)
        grippeweb = self._grippeweb_at_date(target, available_cutoff=are_cutoff)
        notaufnahme = self._notaufnahme_at_date(target, available_cutoff=are_cutoff)

        # SurvStat Cross-Disease (für SURVSTAT-Targets)
        if target_disease:
            survstat_xd = self._survstat_cross_disease_at_date(
                target, target_disease, available_cutoff=are_cutoff
            )
        else:
            survstat_xd = {"survstat_xdisease_1": 0.0, "survstat_xdisease_2": 0.0}

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

        # MARKET = BfArM shortage disruption proxy
        market = self._market_proxy_at_date(target, bio, wastewater, positivity)

        # PSYCHO = Google Trends
        psycho = trends

        # CONTEXT = weather (+ school_start boost)
        context = weather
        if school_start:
            context = min(context * 1.3, 1.0)

        result = {
            # Legacy composite scores (for backward compatibility)
            "bio": round(bio, 4),
            "market": round(market, 4),
            "psycho": round(psycho, 4),
            "context": round(context, 4),
            "school_start": school_start,
            # Individual raw signals (for enhanced backtest)
            "wastewater_raw": round(wastewater, 4),
            "positivity_raw": round(min(positivity * 5.0, 1.0), 4),
            "are_consultation_raw": round(are_consultation, 4),
            "trends_raw": round(trends, 4),
            "weather_temp": weather_components["temp_factor"],
            "weather_uv": weather_components["uv_factor"],
            "weather_humidity": weather_components["humidity_factor"],
            "weather_raw": weather,
            "school_start_float": 1.0 if school_start else 0.0,
            "xdisease_load": xdisease_load,
            # Distributed-Lag Abwasser
            "ww_lag0w": ww_lags.get("ww_lag0w", 0.0),
            "ww_lag1w": ww_lags.get("ww_lag1w", 0.0),
            "ww_lag2w": ww_lags.get("ww_lag2w", 0.0),
            "ww_lag3w": ww_lags.get("ww_lag3w", 0.0),
            "ww_max_3w": ww_lags.get("ww_max_3w", 0.0),
            "ww_slope_2w": ww_lags.get("ww_slope_2w", 0.0),
            # Neue syndromische Signale
            "grippeweb_are": grippeweb["grippeweb_are"],
            "notaufnahme_ari": notaufnahme["notaufnahme_ari"],
            # SurvStat Cross-Disease
            "survstat_xdisease_1": survstat_xd["survstat_xdisease_1"],
            "survstat_xdisease_2": survstat_xd["survstat_xdisease_2"],
        }
        self._scores_cache[cache_key] = result
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # XGBoost-Features: rein autoregressive SURVSTAT-Zeitreihe
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_survstat_ar_row(
        series: pd.Series,
        idx: int,
        target_date: datetime,
    ) -> dict[str, float]:
        """Baut einen einzelnen Feature-Vektor aus der SURVSTAT-Zeitreihe.

        Args:
            series: Sortierte Zeitreihe der menge-Werte (Index 0 = ältester)
            idx: Position in der Zeitreihe
            target_date: Datum für saisonale Features
        """
        n = len(series)
        val = float(series.iloc[idx]) if idx < n else 0.0

        def _lag(k: int) -> float:
            i = idx - k
            return float(series.iloc[i]) if 0 <= i < n else 0.0

        y_lag1 = _lag(1)
        y_lag2 = _lag(2)
        y_lag4 = _lag(4)
        y_lag8 = _lag(8)
        y_lag52 = _lag(52)

        # Rolling statistics (über die letzten k Punkte VOR idx)
        window4 = [float(series.iloc[idx - j]) for j in range(1, 5) if 0 <= idx - j < n]
        window8 = [float(series.iloc[idx - j]) for j in range(1, 9) if 0 <= idx - j < n]
        y_roll4_mean = float(np.mean(window4)) if window4 else 0.0
        y_roll4_std = float(np.std(window4)) if len(window4) >= 2 else 0.0
        y_roll8_mean = float(np.mean(window8)) if window8 else 0.0

        # Rate of change
        y_roc1 = (y_lag1 - _lag(2)) / max(_lag(2), 1e-6) if _lag(2) > 0 else 0.0
        y_roc4 = (y_lag1 - _lag(5)) / max(_lag(5), 1e-6) if _lag(5) > 0 else 0.0

        # Seasonal encoding
        iso_week = target_date.isocalendar()[1]
        week_sin = round(math.sin(2 * math.pi * iso_week / 52), 4)
        week_cos = round(math.cos(2 * math.pi * iso_week / 52), 4)

        # Level: aktueller Wert / langfristiger Median
        all_vals = [float(series.iloc[j]) for j in range(max(0, idx - 52), idx) if j < n]
        median_val = float(np.median(all_vals)) if all_vals else 1.0
        y_level = y_lag1 / max(median_val, 1e-6)

        return {
            "y_lag1": y_lag1, "y_lag2": y_lag2, "y_lag4": y_lag4,
            "y_lag8": y_lag8, "y_lag52": y_lag52,
            "y_roll4_mean": y_roll4_mean, "y_roll4_std": y_roll4_std,
            "y_roll8_mean": y_roll8_mean,
            "y_roc1": y_roc1, "y_roc4": y_roc4,
            "week_sin": week_sin, "week_cos": week_cos,
            "y_level": y_level,
        }

    def _build_survstat_ar_training_data(
        self,
        train_df: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Baut X/y aus SURVSTAT train_df für XGBoost.

        train_df muss Spalten 'datum' und 'menge' haben, sortiert nach datum.
        Gibt (X, y) zurück wobei X die autoregressive Feature-Matrix ist.
        Skipt die ersten 52 Zeilen (brauchen lag52).
        """
        series = train_df["menge"].reset_index(drop=True)
        dates = train_df["datum"].reset_index(drop=True)
        n = len(series)
        min_idx = min(52, n - 1)  # brauchen mindestens lag52

        rows = []
        targets = []
        for i in range(max(min_idx, 1), n):
            feat = self._build_survstat_ar_row(series, i, dates.iloc[i])
            rows.append([feat[c] for c in self.XGBOOST_SURVSTAT_FEATURES])
            targets.append(float(series.iloc[i]))

        if not rows:
            return np.empty((0, len(self.XGBOOST_SURVSTAT_FEATURES))), np.empty(0)

        X = np.array(rows, dtype=float)
        y = np.array(targets, dtype=float)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        return X, y

    # ─────────────────────────────────────────────────────────────────────────
    # Haupt-Kalibrierung
    # ─────────────────────────────────────────────────────────────────────────

    def _simulate_rows_from_target(
        self,
        target_df: pd.DataFrame,
        virus_typ: str,
        horizon_days: int = 0,
        delay_rules: Optional[dict[str, int]] = None,
        enhanced: bool = False,
        target_disease: Optional[str] = None,
    ) -> list[dict]:
        """Berechne Sub-Scores je Ziel-Datenpunkt ohne Future-Leak.

        Args:
            enhanced: If True, include raw signals + temporal features
                      for the improved GradientBoosting pipeline.
            target_disease: SurvStat disease name for cross-disease features.
        """
        if target_df.empty:
            return []

        df = target_df.copy()
        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
        df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)

        menge_values = df["menge"].tolist()

        # Seasonal baselines per ISO-Woche (für Residual-Modellierung)
        df["_iso_week"] = df["datum"].apply(lambda d: d.isocalendar()[1])
        seasonal_baselines: dict[int, float] = {}
        for wk in range(1, 54):
            vals = df[df["_iso_week"] == wk]["menge"].tolist()
            seasonal_baselines[wk] = float(np.median(vals)) if vals else 0.0

        simulation_rows = []
        for idx, row in df.iterrows():
            target_date = row["datum"]
            sim_date = target_date - timedelta(days=max(0, int(horizon_days)))
            real_qty = float(row["menge"])
            baseline = seasonal_baselines.get(int(row["_iso_week"]), 0.0)

            try:
                scores = self._compute_sub_scores_at_date(
                    sim_date,
                    virus_typ,
                    delay_rules=delay_rules,
                    target_disease=target_disease,
                )
                row_dict = {
                    "date": target_date.strftime("%Y-%m-%d"),
                    "feature_date": sim_date.strftime("%Y-%m-%d"),
                    "real_qty": real_qty,
                    "bio": scores["bio"],
                    "market": scores["market"],
                    "psycho": scores["psycho"],
                    "context": scores["context"],
                    "school_start": scores["school_start"],
                }

                if enhanced:
                    # Raw signals
                    row_dict["wastewater_raw"] = scores["wastewater_raw"]
                    row_dict["positivity_raw"] = scores["positivity_raw"]
                    row_dict["are_consultation_raw"] = scores.get("are_consultation_raw", 0.0)
                    row_dict["trends_raw"] = scores["trends_raw"]
                    row_dict["weather_temp"] = scores["weather_temp"]
                    row_dict["weather_humidity"] = scores["weather_humidity"]
                    row_dict["school_start_float"] = scores["school_start_float"]
                    row_dict["xdisease_load"] = scores["xdisease_load"]

                    # Distributed-Lag Abwasser
                    row_dict["ww_lag0w"] = scores["ww_lag0w"]
                    row_dict["ww_lag1w"] = scores["ww_lag1w"]
                    row_dict["ww_lag2w"] = scores["ww_lag2w"]
                    row_dict["ww_lag3w"] = scores["ww_lag3w"]
                    row_dict["ww_max_3w"] = scores["ww_max_3w"]
                    row_dict["ww_slope_2w"] = scores["ww_slope_2w"]

                    # Syndromische Signale
                    row_dict["grippeweb_are"] = scores["grippeweb_are"]
                    row_dict["notaufnahme_ari"] = scores["notaufnahme_ari"]

                    # SurvStat Cross-Disease
                    row_dict["survstat_xdisease_1"] = scores["survstat_xdisease_1"]
                    row_dict["survstat_xdisease_2"] = scores["survstat_xdisease_2"]

                    # Target rate of change — row-level vintage
                    i = int(idx)
                    if "available_time" in df.columns:
                        vintage_mask = df["available_time"] <= sim_date
                        vintage_vals = df.loc[vintage_mask, "menge"].tolist()
                    else:
                        vintage_vals = menge_values[:i]
                    if len(vintage_vals) >= 2:
                        row_dict["target_roc"] = (vintage_vals[-1] - vintage_vals[-2]) / vintage_vals[-2] if vintage_vals[-2] > 0 else 0.0
                    else:
                        row_dict["target_roc"] = 0.0

                    # Niveauanker: seasonal_baseline + target_level
                    row_dict["seasonal_baseline"] = baseline
                    if vintage_vals:
                        seasonal_med = max(float(np.median(vintage_vals)), 1.0)
                        row_dict["target_level"] = round(float(vintage_vals[-1]) / seasonal_med, 4)
                    else:
                        row_dict["target_level"] = 0.0

                    # Saisonalität am TARGET_DATE (deterministisch bekannt)
                    iso_week = target_date.isocalendar()[1]
                    row_dict["week_sin"] = round(math.sin(2 * math.pi * iso_week / 52), 4)
                    row_dict["week_cos"] = round(math.cos(2 * math.pi * iso_week / 52), 4)

                simulation_rows.append(row_dict)
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

        # Exakter Match zuerst
        exact = self.db.query(SurvstatWeeklyData.disease).filter(
            SurvstatWeeklyData.disease == token
        ).first()
        if exact:
            return exact[0]

        # Fuzzy-Match per LIKE
        pattern = f"%{token.lower()}%"
        row = self.db.query(SurvstatWeeklyData.disease).filter(
            func.lower(SurvstatWeeklyData.disease).like(pattern)
        ).order_by(SurvstatWeeklyData.disease.asc()).first()

        return row[0] if row else None

    def _load_market_target(
        self,
        target_source: str = "RKI_ARE",
        days_back: int = 730,
        bundesland: str = "",
    ) -> Tuple[pd.DataFrame, dict]:
        """Lädt externe Markt-Proxy-Wahrheit für Twin-Mode Market-Check."""
        token = (target_source or "RKI_ARE").strip()
        token_upper = token.upper()
        start_date = datetime.now() - timedelta(days=days_back)
        bl_filter = bundesland.strip() if bundesland else "Gesamt"

        # --- ATEMWEGSINDEX: Aggregat aller respiratorischen Erreger ---
        if token_upper == "ATEMWEGSINDEX":
            surv_rows = self.db.query(
                SurvstatWeeklyData.week_start,
                SurvstatWeeklyData.week_label,
                func.sum(SurvstatWeeklyData.incidence).label("total_incidence"),
                func.min(SurvstatWeeklyData.available_time).label("available_time"),
            ).filter(
                SurvstatWeeklyData.disease.in_(self.GELO_ATEMWEG_DISEASES),
                SurvstatWeeklyData.bundesland == bl_filter,
                or_(SurvstatWeeklyData.age_group == "Gesamt", SurvstatWeeklyData.age_group.is_(None)),
                SurvstatWeeklyData.week_start >= start_date,
            ).group_by(
                SurvstatWeeklyData.week_start,
                SurvstatWeeklyData.week_label,
            ).order_by(SurvstatWeeklyData.week_start.asc()).all()

            df = pd.DataFrame([{
                "datum": row.week_start,
                "menge": float(row.total_incidence or 0),
                "available_time": row.available_time or row.week_start,
            } for row in surv_rows])

            bl_label = bl_filter if bl_filter != "Gesamt" else "Bundesweit"
            return df, {
                "target_source": "ATEMWEGSINDEX",
                "target_label": f"Atemwegsindex ({bl_label})",
                "target_key": "ATEMWEGSINDEX",
                "disease": None,
                "bundesland": bl_filter,
            }

        # --- RKI_ARE ---
        if token_upper == "RKI_ARE":
            bl_are = "Bundesweit" if bl_filter == "Gesamt" else bl_filter
            are_rows = self.db.query(AREKonsultation).filter(
                AREKonsultation.altersgruppe == "00+",
                AREKonsultation.bundesland == bl_are,
                AREKonsultation.datum >= start_date,
            ).order_by(AREKonsultation.datum.asc()).all()

            df = pd.DataFrame([{
                "datum": row.datum,
                "menge": row.konsultationsinzidenz,
                "available_time": row.available_time or row.datum,
            } for row in are_rows if row.konsultationsinzidenz is not None])

            return df, {
                "target_source": "RKI_ARE",
                "target_label": f"RKI ARE ({bl_are}, 00+)",
                "target_key": "RKI_ARE",
                "bundesland": bl_filter,
            }

        # --- SURVSTAT Einzelerreger ---
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
            SurvstatWeeklyData.bundesland == bl_filter,
            SurvstatWeeklyData.week_start >= start_date,
        ).order_by(SurvstatWeeklyData.week_start.asc()).all()

        df = pd.DataFrame([{
            "datum": row.week_start,
            "menge": row.incidence,
            "available_time": row.available_time or row.week_start,
        } for row in surv_rows if row.incidence is not None])

        bl_label = bl_filter if bl_filter != "Gesamt" else "Bundesweit"
        return df, {
            "target_source": "SURVSTAT",
            "target_label": f"SURVSTAT {disease} ({bl_label})",
            "target_key": token_upper,
            "disease": disease,
            "bundesland": bl_filter,
        }

    @staticmethod
    def _estimate_step_days(df_sim: pd.DataFrame) -> int:
        return backtester_metrics.estimate_step_days(df_sim)

    def _build_planning_curve(
        self,
        target_df: pd.DataFrame,
        virus_typ: str = "Influenza A",
        days_back: int = 2500,
    ) -> dict:
        """Planungskurve: Abwasser um empirischen Lead shiften + skalieren.

        Statt ML-Forecast nutzt dies die empirische Cross-Korrelation
        zwischen Abwasser und Target. Robuster als Modell-Prognose.
        """
        from sklearn.linear_model import LinearRegression

        start_date = datetime.now() - timedelta(days=days_back)

        # 1. Abwasser wöchentlich aggregieren
        ww_weekly = self.db.query(
            func.date_trunc("week", WastewaterAggregated.datum).label("week"),
            func.avg(WastewaterAggregated.viruslast).label("avg_vl"),
        ).filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= start_date,
        ).group_by(
            func.date_trunc("week", WastewaterAggregated.datum)
        ).order_by("week").all()

        if len(ww_weekly) < 10:
            return {"lead_days": 0, "correlation": 0, "curve": []}

        ww_df = pd.DataFrame([
            {"week": r.week, "viruslast": float(r.avg_vl or 0)}
            for r in ww_weekly
        ]).set_index("week")

        # 2. Target wöchentlich
        tgt_df = target_df.copy()
        tgt_df["datum"] = pd.to_datetime(tgt_df["datum"])
        tgt_df = tgt_df.set_index("datum")[["menge"]].dropna()

        # 3. Align + Cross-Korrelation
        merged = ww_df.join(tgt_df, how="inner").dropna()
        if len(merged) < 15:
            return {"lead_days": 0, "correlation": 0, "curve": []}

        vl = merged["viruslast"].values
        inc = merged["menge"].values
        vl_n = (vl - vl.mean()) / (vl.std() + 1e-9)
        inc_n = (inc - inc.mean()) / (inc.std() + 1e-9)

        best_lag = 0
        best_corr = 0.0
        for lag in range(0, 5):  # 0-4 Wochen, nur positiv (Abwasser führt)
            if lag > 0:
                x, y = vl_n[:-lag], inc_n[lag:]
            else:
                x, y = vl_n, inc_n
            if len(x) < 10:
                continue
            corr = float(np.corrcoef(x, y)[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_lag = lag

        lead_days = best_lag * 7

        # 4. Lineare Regression: incidence[t+lag] = a * viruslast[t] + b
        if best_lag > 0:
            X_reg = vl[:-best_lag].reshape(-1, 1)
            y_reg = inc[best_lag:]
        else:
            X_reg = vl.reshape(-1, 1)
            y_reg = inc

        reg = LinearRegression().fit(X_reg, y_reg)

        # 5. Planungskurve: Jeder Abwasser-Punkt → Prognose für +lead_days
        curve = []
        for _, row_data in ww_df.iterrows():
            ww_date = row_data.name
            target_date = ww_date + timedelta(days=lead_days)
            predicted = max(0, float(reg.predict([[row_data["viruslast"]]])[0]))
            curve.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "based_on": ww_date.strftime("%Y-%m-%d"),
                "issue_date": ww_date.strftime("%Y-%m-%d"),
                "target_date": target_date.strftime("%Y-%m-%d"),
                "planning_qty": round(predicted, 2),
            })

        return {
            "lead_days": lead_days,
            "lead_weeks": best_lag,
            "correlation": round(best_corr, 3),
            "regression_coef": round(float(reg.coef_[0]), 6),
            "regression_intercept": round(float(reg.intercept_), 2),
            "curve": sorted(curve, key=lambda r: r["date"]),
        }

    def _best_bio_lead_lag(self, df_sim: pd.DataFrame, max_lag_points: int = 6) -> dict:
        return backtester_metrics.best_bio_lead_lag(
            df_sim,
            max_lag_points=max_lag_points,
        )

    @staticmethod
    def _augment_lead_lag_with_horizon(lead_lag: dict, horizon_days: int) -> dict:
        return backtester_metrics.augment_lead_lag_with_horizon(
            lead_lag,
            horizon_days,
        )

    @staticmethod
    def _compute_forecast_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
        return backtester_metrics.compute_forecast_metrics(y_true, y_pred)

    @staticmethod
    def _compute_vintage_metrics(
        forecast_records: list[dict],
        configured_horizon_days: int,
    ) -> dict:
        return backtester_metrics.compute_vintage_metrics(
            forecast_records,
            configured_horizon_days,
        )

    @staticmethod
    def _compute_interval_coverage_metrics(chart_data: list[dict]) -> dict:
        return backtester_metrics.compute_interval_coverage_metrics(chart_data)

    @staticmethod
    def _compute_event_calibration_metrics(
        forecast_records: list[dict],
        threshold_pct: float = 25.0,
    ) -> dict:
        return backtester_metrics.compute_event_calibration_metrics(
            forecast_records,
            threshold_pct=threshold_pct,
            decision_baseline_window_days=BacktestService.DECISION_BASELINE_WINDOW_DAYS,
            heuristic_event_score_source=HEURISTIC_EVENT_SCORE_SOURCE,
        )

    @staticmethod
    def _build_lead_feature_set(feature_cols: list[str]) -> list[str]:
        return backtester_metrics.build_lead_feature_set(feature_cols)

    @staticmethod
    def _compute_timing_metrics(
        forecast_records: list[dict],
        horizon_days: int,
        y_hat_key: str = "y_hat",
        max_lag_points: int = 8,
    ) -> dict:
        return backtester_metrics.compute_timing_metrics(
            forecast_records,
            horizon_days,
            y_hat_key=y_hat_key,
            max_lag_points=max_lag_points,
            quality_gate_lead_target_days=BacktestService.QUALITY_GATE_LEAD_TARGET_DAYS,
        )

    @staticmethod
    def _compute_decision_metrics(
        forecast_records: list[dict],
        threshold_pct: float = 25.0,
        vintage_metrics: Optional[dict] = None,
    ) -> dict:
        return backtester_metrics.compute_decision_metrics(
            forecast_records,
            threshold_pct=threshold_pct,
            vintage_metrics=vintage_metrics,
            decision_baseline_window_days=BacktestService.DECISION_BASELINE_WINDOW_DAYS,
            quality_gate_ttd_target_days=BacktestService.QUALITY_GATE_TTD_TARGET_DAYS,
            quality_gate_hit_rate_target_pct=BacktestService.QUALITY_GATE_HIT_RATE_TARGET_PCT,
            quality_gate_p90_error_rel_target_pct=BacktestService.QUALITY_GATE_P90_ERROR_REL_TARGET_PCT,
        )

    @staticmethod
    def _build_quality_gate(
        decision_metrics: dict,
        timing_metrics: Optional[dict] = None,
        *,
        improvement_vs_baselines: Optional[dict] = None,
        interval_coverage: Optional[dict] = None,
        event_calibration: Optional[dict] = None,
    ) -> dict:
        return backtester_metrics.build_quality_gate(
            decision_metrics,
            timing_metrics,
            improvement_vs_baselines=improvement_vs_baselines,
            interval_coverage=interval_coverage,
            event_calibration=event_calibration,
            quality_gate_ttd_target_days=BacktestService.QUALITY_GATE_TTD_TARGET_DAYS,
            quality_gate_hit_rate_target_pct=BacktestService.QUALITY_GATE_HIT_RATE_TARGET_PCT,
            quality_gate_p90_error_rel_target_pct=BacktestService.QUALITY_GATE_P90_ERROR_REL_TARGET_PCT,
            quality_gate_lead_target_days=BacktestService.QUALITY_GATE_LEAD_TARGET_DAYS,
        )

    @staticmethod
    def _sanitize_for_json(value):
        return backtester_metrics.sanitize_for_json(value)

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
            run_id = f"bt_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
            chart_data = result.get("chart_data", []) or []
            metrics_payload = dict(result.get("metrics", {}) or {})
            if result.get("decision_metrics") is not None:
                metrics_payload["decision_metrics"] = result.get("decision_metrics")
            if result.get("interval_coverage") is not None:
                metrics_payload["interval_coverage"] = result.get("interval_coverage")
            if result.get("event_calibration") is not None:
                metrics_payload["event_calibration"] = result.get("event_calibration")
            if result.get("quality_gate") is not None:
                metrics_payload["quality_gate"] = result.get("quality_gate")
            if result.get("timing_metrics") is not None:
                metrics_payload["timing_metrics"] = result.get("timing_metrics")

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
                metrics=metrics_payload,
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

    def get_backtest_run(self, run_id: str) -> dict | None:
        """Liefert einen persistierten Backtest-Lauf inkl. Chart-Punkten."""
        row = (
            self.db.query(BacktestRun)
            .filter(BacktestRun.run_id == run_id)
            .first()
        )
        if not row:
            return None

        metrics = row.metrics or {}
        points = (
            self.db.query(BacktestPoint)
            .filter(BacktestPoint.run_id == run_id)
            .order_by(BacktestPoint.date.asc(), BacktestPoint.id.asc())
            .all()
        )

        chart_data = [
            {
                "date": point.date.date().isoformat() if point.date else None,
                "region": point.region,
                "real_qty": point.real_qty,
                "predicted_qty": point.predicted_qty,
                "baseline_persistence": point.baseline_persistence,
                "baseline_seasonal": point.baseline_seasonal,
                "bio": point.bio,
                "psycho": point.psycho,
                "context": point.context,
            }
            for point in points
            if point.date is not None
        ]

        return {
            "run_id": row.run_id,
            "mode": row.mode,
            "status": row.status,
            "virus_typ": row.virus_typ,
            "target_source": row.target_source,
            "target_key": row.target_key,
            "target_label": row.target_label,
            "metrics": metrics,
            "decision_metrics": metrics.get("decision_metrics"),
            "quality_gate": metrics.get("quality_gate"),
            "timing_metrics": metrics.get("timing_metrics"),
            "lead_lag": row.lead_lag or {},
            "proof_text": row.proof_text,
            "llm_insight": row.llm_insight,
            "chart_data": chart_data,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "walk_forward": {
                "horizon_days": row.horizon_days,
                "min_train_points": row.min_train_points,
                "strict_vintage_mode": row.strict_vintage_mode,
            },
        }

    @staticmethod
    def _seasonal_naive_baseline(train_df: pd.DataFrame, target_week: int, target_month: int) -> float:
        """Seasonal Baseline: Median der gleichen ISO-Woche (konsistent mit Residual-Training)."""
        same_week = train_df[train_df["iso_week"] == target_week]
        if not same_week.empty:
            return float(same_week["menge"].median())

        same_month = train_df[train_df["month"] == target_month]
        if not same_month.empty:
            return float(same_month["menge"].median())

        return float(train_df["menge"].median())

    def _run_walk_forward_market_backtest(
        self,
        target_df: pd.DataFrame,
        virus_typ: str,
        horizon_days: int,
        min_train_points: int,
        delay_rules: Optional[dict[str, int]] = None,
        exclude_are: bool = False,
        target_disease: Optional[str] = None,
    ) -> dict:
        """Walk-forward Backtest mit XGBoost auf autoregressive SURVSTAT-Features.

        Trainiert rein auf historischen SURVSTAT-Zeitreihendaten (Lags, Rolling,
        Saisonalität). AMELAG-Viruslast wird als Zusatzinfo in chart_data ausgegeben.
        """
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

        # XGBoost auf autoregressive SURVSTAT-Features
        feature_cols = list(self.XGBOOST_SURVSTAT_FEATURES)

        folds: list[dict] = []
        importance_accumulator: list[np.ndarray] = []
        xgb_fold_count = 0

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

            # XGBoost: Autoregressive Features rein aus SURVSTAT-Zeitreihe
            train_sorted = train_target_df[["datum", "menge"]].sort_values("datum").reset_index(drop=True)
            X_train, y_train = self._build_survstat_ar_training_data(train_sorted)
            if len(X_train) < 10:
                continue

            # XGBoost Regressor (keine bio/psycho/context Mischung)
            n_train = len(X_train)
            xgb_fold_count += 1
            model = XGBRegressor(
                n_estimators=min(200, max(50, n_train * 2)),
                max_depth=4 if n_train >= 60 else 3,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=3,
                random_state=42,
                verbosity=0,
            )
            model.fit(X_train, y_train)
            importance_accumulator.append(model.feature_importances_)

            # Test-Features für den Vorhersagepunkt
            series = train_sorted["menge"].reset_index(drop=True)
            test_feat = self._build_survstat_ar_row(
                series, len(series), target_time,
            )
            X_test = np.array([[test_feat.get(c, 0.0) for c in self.XGBOOST_SURVSTAT_FEATURES]])
            X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

            y_hat = max(0.0, float(model.predict(X_test)[0]))
            y_max = float(y_train.max())
            y_hat = min(y_hat, y_max * 2.5)

            # Baselines für Vergleich
            baseline_persistence = float(train_target_df.iloc[-1]["menge"])
            seasonal_bl = self._seasonal_naive_baseline(
                train_target_df, target_week=target_week, target_month=target_month,
            )
            decision_window = train_target_df[
                train_target_df["datum"] >= (forecast_time - timedelta(days=self.DECISION_BASELINE_WINDOW_DAYS))
            ]
            if decision_window.empty:
                decision_window = train_target_df
            decision_baseline = float(decision_window["menge"].median()) if not decision_window.empty else seasonal_bl
            heuristic_event_score = heuristic_event_score_from_forecast(
                prediction=y_hat,
                baseline=decision_baseline if decision_baseline > 0 else max(seasonal_bl, 1.0),
                lower_bound=max(0.0, y_hat - 1.28 * max(float(np.std(y_train)), 1.0)),
                upper_bound=y_hat + 1.28 * max(float(np.std(y_train)), 1.0),
                threshold_pct=float(self.DECISION_EVENT_THRESHOLD_PCT),
            )

            # AMELAG Rohdaten für Chart-Anzeige
            amelag_val = self._amelag_raw_at_date(target_time, virus_typ)

            folds.append({
                "forecast_time": forecast_time,
                "target_time": target_time,
                "real_qty": target_value,
                "predicted_qty": y_hat,
                "predicted_qty_level": y_hat,
                "predicted_qty_lead": y_hat,
                "predicted_qty_decision": y_hat,
                "p_event": None,
                "event_probability": None,
                "heuristic_event_score": heuristic_event_score,
                "probability_source": HEURISTIC_EVENT_SCORE_SOURCE,
                "selected_variant": "xgboost",
                "baseline_persistence": baseline_persistence,
                "baseline_seasonal": seasonal_bl,
                "decision_baseline": round(decision_baseline, 4),
                "amelag_viruslast": amelag_val,
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

        # Feature importance: XGBoost (letzter Fold = größtes Training)
        imp_cols = feature_cols
        if importance_accumulator:
            last_imp = importance_accumulator[-1]
            total = float(last_imp.sum())
            if total > 0:
                optimized_weights = {
                    col: round(float(last_imp[i] / total), 3)
                    for i, col in enumerate(imp_cols[:len(last_imp)])
                }
            else:
                optimized_weights = dict(self.DEFAULT_WEIGHTS)
        else:
            optimized_weights = dict(self.DEFAULT_WEIGHTS)

        # --- Future Forecast Extension (6 weeks ahead) mit XGBoost ---
        forecast_weeks = 6
        residuals = y_true - y_hat
        residual_std = (
            float(np.std(residuals)) if len(residuals) > 2
            else float(np.std(y_true) * 0.3)
        )
        last_target_time = pred_df["target_time"].max()
        # Extend the series with actual values for autoregressive features
        rolling_series = list(df.loc[df["datum"] <= last_target_time, "menge"].values)
        forecast_chart: list[dict] = []

        try:
            for w in range(1, forecast_weeks + 1):
                future_target = last_target_time + timedelta(weeks=w)
                future_forecast = future_target - timedelta(
                    days=max(0, int(horizon_days))
                )

                # Build AR features from extended series
                fc_series = pd.Series(rolling_series, dtype=float)
                fc_feat = self._build_survstat_ar_row(
                    fc_series, len(fc_series), future_target,
                )
                X_fc = np.array([[fc_feat.get(c, 0.0) for c in self.XGBOOST_SURVSTAT_FEATURES]])
                X_fc = np.nan_to_num(X_fc, nan=0.0, posinf=0.0, neginf=0.0)
                y_fc = max(0.0, float(model.predict(X_fc)[0]))

                hf = math.sqrt(w)
                ci_80 = 1.28 * residual_std * hf
                ci_95 = 1.96 * residual_std * hf

                forecast_chart.append({
                    "date": future_target.strftime("%Y-%m-%d"),
                    "issue_date": future_forecast.strftime("%Y-%m-%d"),
                    "target_date": future_target.strftime("%Y-%m-%d"),
                    "forecast_qty": round(y_fc, 3),
                    "ci_80_lower": round(max(0, y_fc - ci_80), 3),
                    "ci_80_upper": round(y_fc + ci_80, 3),
                    "ci_95_lower": round(max(0, y_fc - ci_95), 3),
                    "ci_95_upper": round(y_fc + ci_95, 3),
                    "is_forecast": True,
                })
                rolling_series.append(y_fc)
        except Exception:
            pass  # forecast is best-effort; backtest results always returned

        # Sauberes Datenmodell: forecast_records + chart_data für beide Ansichten
        # forecast_records: Jeder Fold als Record mit issue_date + target_date
        forecast_records = [
            {
                "issue_date": row["forecast_time"].strftime("%Y-%m-%d"),
                "target_date": row["target_time"].strftime("%Y-%m-%d"),
                "y_hat": round(float(row["predicted_qty"]), 3),
                "y_true": float(row["real_qty"]),
                "baseline_persistence": float(row["baseline_persistence"]),
                "baseline_seasonal": float(row["baseline_seasonal"]),
                "decision_baseline": float(row.get("decision_baseline") or 0.0),
                "horizon_days": int(horizon_days),
                "lead_days": int((row["target_time"] - row["forecast_time"]).days),
            }
            for _, row in pred_df.iterrows()
        ]
        decision_forecast_records = [
            {
                "issue_date": row["forecast_time"].strftime("%Y-%m-%d"),
                "target_date": row["target_time"].strftime("%Y-%m-%d"),
                "y_hat": round(float(row.get("predicted_qty_decision", row["predicted_qty"])), 3),
                "y_hat_level": round(float(row.get("predicted_qty_level", row["predicted_qty"])), 3),
                "y_hat_lead": round(float(row.get("predicted_qty_lead", row["predicted_qty"])), 3),
                "p_event": (
                    round(float(row["event_probability"]), 4)
                    if row.get("event_probability") is not None
                    else None
                ),
                "event_probability": (
                    round(float(row["event_probability"]), 4)
                    if row.get("event_probability") is not None
                    else None
                ),
                "heuristic_event_score": (
                    round(float(row["heuristic_event_score"]), 4)
                    if row.get("heuristic_event_score") is not None
                    else None
                ),
                "probability_source": str(row.get("probability_source") or HEURISTIC_EVENT_SCORE_SOURCE),
                "selected_variant": str(row.get("selected_variant") or "level"),
                "y_true": float(row["real_qty"]),
                "baseline_persistence": float(row["baseline_persistence"]),
                "baseline_seasonal": float(row["baseline_seasonal"]),
                "decision_baseline": float(row.get("decision_baseline") or 0.0),
                "horizon_days": int(horizon_days),
                "lead_days": int((row["target_time"] - row["forecast_time"]).days),
            }
            for _, row in pred_df.iterrows()
        ]

        # chart_data: Validierungsansicht (beide am target_date, Standard)
        # OOS-Konfidenzintervalle basierend auf residual_std (konstant, kein Horizont-Faktor)
        ci_80_half = 1.28 * residual_std
        ci_95_half = 1.96 * residual_std
        historical_chart = [
            {
                "date": row["target_time"].strftime("%Y-%m-%d"),
                "issue_date": row["forecast_time"].strftime("%Y-%m-%d"),
                "target_date": row["target_time"].strftime("%Y-%m-%d"),
                "real_qty": float(row["real_qty"]),
                "predicted_qty": round(float(row["predicted_qty"]), 3),
                "ci_80_lower": round(max(0.0, float(row["predicted_qty"]) - ci_80_half), 3),
                "ci_80_upper": round(float(row["predicted_qty"]) + ci_80_half, 3),
                "ci_95_lower": round(max(0.0, float(row["predicted_qty"]) - ci_95_half), 3),
                "ci_95_upper": round(float(row["predicted_qty"]) + ci_95_half, 3),
                "amelag_viruslast": round(float(row["amelag_viruslast"]), 3) if row.get("amelag_viruslast") is not None else None,
                "is_forecast": False,
            }
            for _, row in pred_df.iterrows()
        ]

        # Bridge: last historical point starts the forecast line
        if historical_chart and forecast_chart:
            historical_chart[-1]["forecast_qty"] = historical_chart[-1]["predicted_qty"]

        chart_data = historical_chart + forecast_chart
        vintage_records = decision_forecast_records or forecast_records
        vintage_metrics = self._compute_vintage_metrics(
            forecast_records=vintage_records,
            configured_horizon_days=int(horizon_days),
        )
        decision_metrics = self._compute_decision_metrics(
            forecast_records=vintage_records,
            threshold_pct=float(self.DECISION_EVENT_THRESHOLD_PCT),
            vintage_metrics=vintage_metrics,
        )
        interval_coverage = self._compute_interval_coverage_metrics(historical_chart)
        event_calibration = self._compute_event_calibration_metrics(
            decision_forecast_records,
            threshold_pct=float(self.DECISION_EVENT_THRESHOLD_PCT),
        )
        timing_metrics = self._compute_timing_metrics(
            forecast_records=vintage_records,
            horizon_days=int(horizon_days),
        )
        quality_gate = self._build_quality_gate(
            decision_metrics,
            timing_metrics,
            improvement_vs_baselines={
                "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
                "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
            },
            interval_coverage=interval_coverage,
            event_calibration=None if event_calibration.get("calibration_skipped") else event_calibration,
        )

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
            "model_type": "XGBoost",
            "xgb_folds": xgb_fold_count,
            "feature_count": len(imp_cols) if importance_accumulator else len(feature_cols),
            "feature_names": imp_cols if importance_accumulator else feature_cols,
            "chart_data": chart_data,
            "forecast_records": forecast_records,
            "decision_forecast_records": decision_forecast_records,
            "vintage_metrics": vintage_metrics,
            "decision_metrics": decision_metrics,
            "interval_coverage": interval_coverage,
            "event_calibration": event_calibration,
            "timing_metrics": timing_metrics,
            "quality_gate": quality_gate,
            "forecast_weeks": len(forecast_chart),
            "residual_std": round(residual_std, 4),
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
        bundesland: str = "",
    ) -> dict:
        """Mode A: Markt-Check ohne Kundendaten gegen externe RKI-Proxy-Targets."""
        self._scores_cache = {}  # Clear cache for each new simulation run
        self.strict_vintage_mode = bool(strict_vintage_mode)
        logger.info(
            "Starte Markt-Simulation: virus=%s, target_source=%s, days_back=%s, bundesland=%s",
            virus_typ, target_source, days_back, bundesland or "Gesamt"
        )

        try:
            target_df, target_meta = self._load_market_target(
                target_source=target_source,
                days_back=days_back,
                bundesland=bundesland,
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

        # Auto-detect optimal min_train_points based on available data
        n_available = len(target_df)
        if min_train_points <= 0:
            # Auto mode: use ~60% of data for initial training, min 20, max 150
            min_train_points = max(20, min(150, int(n_available * 0.6)))
            logger.info(
                "Auto min_train_points=%d (data: %d points)",
                min_train_points, n_available,
            )
        elif min_train_points >= n_available:
            # Prevent zero-fold scenario: cap at 70% of data
            min_train_points = max(20, int(n_available * 0.7))
            logger.info(
                "Capped min_train_points=%d (data: %d points)",
                min_train_points, n_available,
            )

        # Exclude ARE from features when target=RKI_ARE (circular dependency)
        exclude_are = (target_source or "").strip().upper() == "RKI_ARE"

        result = self._run_walk_forward_market_backtest(
            target_df=target_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            delay_rules=delay_rules,
            exclude_are=exclude_are,
            target_disease=target_meta.get("disease"),
        )
        if "error" in result:
            return result

        # Lead-Lag: XGBoost-Prognose vs. Ist-Wert (nicht mehr Bio-Signal)
        df_sim = pd.DataFrame([{
            "date": row["date"],
            "bio": row.get("predicted_qty", 0.0),
            "real_qty": row.get("real_qty", 0.0),
        } for row in result.get("chart_data", []) if not row.get("is_forecast")])
        lead_lag = self._augment_lead_lag_with_horizon(
            self._best_bio_lead_lag(df_sim),
            horizon_days=horizon_days,
        )
        relative_lag_days = int(lead_lag.get("relative_lag_days", 0))
        effective_lead_days = int(lead_lag.get("effective_lead_days", 0))
        lag_corr = float(lead_lag.get("lag_correlation", 0.0))
        baseline_delta = result.get("improvement_vs_baselines", {})
        delta_pers = baseline_delta.get("mae_vs_persistence_pct", 0.0)
        delta_seas = baseline_delta.get("mae_vs_seasonal_pct", 0.0)
        decision_records = result.get("decision_forecast_records") or result.get("forecast_records") or []
        decision_metrics = result.get("decision_metrics") or self._compute_decision_metrics(
            forecast_records=decision_records,
            threshold_pct=float(self.DECISION_EVENT_THRESHOLD_PCT),
            vintage_metrics=result.get("vintage_metrics"),
        )
        timing_metrics = result.get("timing_metrics") or self._compute_timing_metrics(
            forecast_records=decision_records,
            horizon_days=int(horizon_days),
        )
        quality_gate = result.get("quality_gate") or self._build_quality_gate(
            decision_metrics,
            timing_metrics,
            improvement_vs_baselines=result.get("improvement_vs_baselines"),
            interval_coverage=result.get("interval_coverage"),
            event_calibration=result.get("event_calibration"),
        )
        result["decision_metrics"] = decision_metrics
        result["timing_metrics"] = timing_metrics
        result["quality_gate"] = quality_gate

        lag_strength = "stark" if abs(lag_corr) >= 0.5 else "moderat" if abs(lag_corr) >= 0.25 else "schwach"

        if lag_corr <= 0:
            proof_text = (
                f"Kein stabiler positiver Lead erkennbar. "
                f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
            )
        elif lead_lag.get("bio_leads_target_effective"):
            proof_text = (
                f"XGBoost-Prognose läuft dem Ist-Wert um ca. {effective_lead_days} Tage voraus "
                f"(Forecast-Horizont {horizon_days}T + Relativ-Lag {relative_lag_days}T). "
                f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
            )
        elif lead_lag.get("target_leads_bio_effective"):
            proof_text = (
                f"Ist-Wert läuft der XGBoost-Prognose um ca. {abs(effective_lead_days)} Tage voraus "
                f"(Forecast-Horizont {horizon_days}T + Relativ-Lag {relative_lag_days}T). "
                f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
            )
        else:
            proof_text = (
                f"Prognose und Ist-Wert sind effektiv gleichzeitig (0T Lead). "
                f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
            )

        result["mode"] = "MARKET_CHECK"
        result["virus_typ"] = virus_typ
        # Planungskurve: Abwasser-Signal → skaliert + um Lead geshiftet
        try:
            planning = self._build_planning_curve(
                target_df=target_df,
                virus_typ=virus_typ,
                days_back=days_back,
            )
            result["planning_curve"] = planning
        except Exception as e:
            logger.warning("Planungskurve fehlgeschlagen: %s", e)
            result["planning_curve"] = {"lead_days": 0, "correlation": 0, "curve": []}

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
        def _safe_metric(value: object, default: float = 0.0) -> float:
            try:
                return float(value) if value is not None else float(default)
            except (TypeError, ValueError):
                return float(default)

        timing_best_corr = _safe_metric(timing_metrics.get("corr_at_best_lag"))
        decision_hit_rate = _safe_metric(decision_metrics.get("hit_rate_pct"))
        decision_false_alarm_rate = _safe_metric(decision_metrics.get("false_alarm_rate_pct"))
        interval_80_coverage = _safe_metric((result.get("interval_coverage") or {}).get("coverage_80_pct"))
        event_brier_score = _safe_metric((result.get("event_calibration") or {}).get("brier_score"))
        result["proof_text"] = (
            f"{proof_text} "
            f"Walk-forward Backtest: MAE vs. Persistence {delta_pers:+.2f}%, "
            f"vs. Seasonal-Naive {delta_seas:+.2f}% (historisch; zukuenftige Performance kann abweichen). "
            f"Timing: best_lag={timing_metrics.get('best_lag_days', 0)} Tage, "
            f"corr@best={timing_best_corr}. "
            f"Decision-Layer: TTD median {decision_metrics.get('median_ttd_days', 0)} Tage, "
            f"Hit-Rate {decision_hit_rate:.1f}%, "
            f"False-Alarms {decision_false_alarm_rate:.1f}%, "
            f"Interval 80% {interval_80_coverage:.1f}%, "
            f"Brier {event_brier_score:.3f}, "
            f"Readiness {'GO' if quality_gate.get('overall_passed') else 'WATCH'}."
        )
        result["llm_insight"] = (
            f"{result['proof_text']} "
            f"Walk-forward Modellguete: R²={result['metrics']['r2_score']}, "
            f"Korrelationsstärke={result['metrics']['correlation_pct']}%, "
            f"sMAPE={result['metrics'].get('smape', 0)}. "
            f"Hinweis: Alle Metriken basieren auf historischen Mustern."
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
        combined_historical: list[dict] = []
        combined_forecast_records: list[dict] = []
        combined_decision_forecast_records: list[dict] = []

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
                "bio": row.get("bio", 0.0),
                "real_qty": row.get("real_qty", 0.0),
            } for row in region_result.get("chart_data", []) if not row.get("is_forecast")])
            region_lead_lag = self._augment_lead_lag_with_horizon(
                self._best_bio_lead_lag(sim_df),
                horizon_days=horizon_days,
            )
            region_result["lead_lag"] = region_lead_lag

            for row in region_result.get("chart_data", []):
                row_copy = dict(row)
                row_copy["region"] = region_name
                combined_chart.append(row_copy)
                if not row_copy.get("is_forecast"):
                    combined_historical.append(row_copy)

            for row in region_result.get("forecast_records", []):
                rec_copy = dict(row)
                rec_copy["region"] = region_name
                combined_forecast_records.append(rec_copy)
            for row in region_result.get("decision_forecast_records", []) or []:
                rec_copy = dict(row)
                rec_copy["region"] = region_name
                combined_decision_forecast_records.append(rec_copy)

            region_results[region_name] = {
                "metrics": region_result.get("metrics", {}),
                "lead_lag": region_lead_lag,
                "chart_points": len(region_result.get("chart_data", [])),
            }

        if not combined_chart or not combined_historical:
            return {
                "error": "Keine validen Backtest-Folds aus Kundendaten erzeugt. Bitte mehr Historie hochladen.",
            }

        combined_df = pd.DataFrame(combined_chart).sort_values("date").reset_index(drop=True)
        metrics_df = pd.DataFrame(combined_historical).sort_values("date").reset_index(drop=True)
        forecast_df = pd.DataFrame(combined_forecast_records).copy()
        if forecast_df.empty:
            return {
                "error": "Keine Forecast-Records für OOS-Metriken verfügbar.",
            }

        y_true = pd.to_numeric(forecast_df["y_true"], errors="coerce").to_numpy(dtype=float)
        y_hat = pd.to_numeric(forecast_df["y_hat"], errors="coerce").to_numpy(dtype=float)

        if "baseline_persistence" in forecast_df.columns:
            y_persistence = pd.to_numeric(
                forecast_df["baseline_persistence"], errors="coerce"
            ).to_numpy(dtype=float)
        else:
            y_persistence = y_hat.copy()

        if "baseline_seasonal" in forecast_df.columns:
            y_seasonal = pd.to_numeric(
                forecast_df["baseline_seasonal"], errors="coerce"
            ).to_numpy(dtype=float)
        else:
            y_seasonal = y_hat.copy()

        model_metrics = self._compute_forecast_metrics(y_true, y_hat)
        persistence_metrics = self._compute_forecast_metrics(y_true, y_persistence)
        seasonal_metrics = self._compute_forecast_metrics(y_true, y_seasonal)

        model_mae = max(model_metrics["mae"], 1e-9)
        pers_mae = max(persistence_metrics["mae"], 1e-9)
        seas_mae = max(seasonal_metrics["mae"], 1e-9)

        if "bio" in metrics_df.columns:
            lag_input = metrics_df[["date", "bio", "real_qty"]].copy()
            lag_input["bio"] = pd.to_numeric(lag_input["bio"], errors="coerce").fillna(0.0)
            lag_input["real_qty"] = pd.to_numeric(lag_input["real_qty"], errors="coerce").fillna(0.0)
            lead_lag_base = self._best_bio_lead_lag(lag_input)
        else:
            lead_lag_base = {
                "best_lag_points": 0,
                "best_lag_days": 0,
                "lag_step_days": int(max(1, int(horizon_days) or 7)),
                "lag_correlation": 0.0,
                "bio_leads_target": False,
            }

        lead_lag_global = self._augment_lead_lag_with_horizon(
            lead_lag_base,
            horizon_days=horizon_days,
        )
        decision_records = combined_decision_forecast_records or combined_forecast_records
        vintage_metrics = self._compute_vintage_metrics(
            forecast_records=decision_records,
            configured_horizon_days=int(horizon_days),
        )
        decision_metrics = self._compute_decision_metrics(
            forecast_records=decision_records,
            threshold_pct=float(self.DECISION_EVENT_THRESHOLD_PCT),
            vintage_metrics=vintage_metrics,
        )
        interval_coverage = self._compute_interval_coverage_metrics(combined_historical)
        event_calibration = self._compute_event_calibration_metrics(
            decision_records,
            threshold_pct=float(self.DECISION_EVENT_THRESHOLD_PCT),
        )
        timing_metrics = self._compute_timing_metrics(
            forecast_records=decision_records,
            horizon_days=int(horizon_days),
        )
        quality_gate = self._build_quality_gate(
            decision_metrics,
            timing_metrics,
            improvement_vs_baselines={
                "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
                "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
            },
            interval_coverage=interval_coverage,
            event_calibration=event_calibration,
        )
        proof_text = (
            f"Kundendaten-Check über {model_metrics['data_points']} Punkte: "
            f"R²={model_metrics['r2_score']}, Korrelationsstärke={model_metrics['correlation_pct']}%, "
            f"Lead/Lag (effektiv)={lead_lag_global['effective_lead_days']} Tage. "
            f"Forecast-Vintage medianer Vorlauf={vintage_metrics['median_lead_days']} Tage. "
            f"Timing best_lag={timing_metrics.get('best_lag_days', 0)} Tage. "
            f"Decision-Layer: TTD median {decision_metrics.get('median_ttd_days', 0)} Tage, "
            f"Hit-Rate {decision_metrics.get('hit_rate_pct', 0):.1f}%, "
            f"False-Alarms {decision_metrics.get('false_alarm_rate_pct', 0):.1f}%, "
            f"Interval 80% {interval_coverage.get('coverage_80_pct', 0.0):.1f}%, "
            f"Brier {float(event_calibration.get('brier_score') or 0.0):.3f}."
        )
        clean_chart_df = combined_df.replace([np.inf, -np.inf], np.nan).astype(object)
        clean_chart_df = clean_chart_df.where(pd.notna(clean_chart_df), None)
        chart_records = clean_chart_df.to_dict(orient="records")

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
            "chart_data": chart_records,
            "forecast_records": combined_forecast_records,
            "decision_forecast_records": decision_records,
            "vintage_metrics": vintage_metrics,
            "decision_metrics": decision_metrics,
            "interval_coverage": interval_coverage,
            "event_calibration": event_calibration,
            "timing_metrics": timing_metrics,
            "quality_gate": quality_gate,
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
        result = self._sanitize_for_json(result)

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
        horizon_days: int = 7,
        min_train_points: int = DEFAULT_MIN_TRAIN_POINTS,
        strict_vintage_mode: bool = True,
    ) -> dict:
        """Out-of-sample Kalibrierung via Walk-forward Backtest.

        customer_df: Spalten 'datum' und 'menge' (Bestellmenge).
        Returns: Metriken, optimierte Gewichte, Chart-Daten, LLM-Insight.
        """
        logger.info(
            "Starte OOS-Kalibrierung: rows=%s, virus=%s, horizon_days=%s, min_train_points=%s",
            len(customer_df),
            virus_typ,
            horizon_days,
            min_train_points,
        )
        self.strict_vintage_mode = bool(strict_vintage_mode)

        df = customer_df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "datum" not in df.columns or "menge" not in df.columns:
            return {
                "error": "Fehlende Pflichtspalten. Erwartet: datum, menge",
                "found_columns": list(df.columns),
            }

        df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
        df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
        df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)

        if len(df) < 8:
            return {
                "error": (
                    f"Zu wenig Datenpunkte für OOS-Kalibrierung ({len(df)}). "
                    "Mindestens 8 erforderlich."
                )
            }

        target_df = df[["datum", "menge"]].copy()
        target_df["available_time"] = target_df["datum"]

        step_days = self._estimate_step_days(
            pd.DataFrame({"date": target_df["datum"].dt.strftime("%Y-%m-%d")})
        )
        primary_horizon = max(1, int(horizon_days))
        primary_min_train = max(5, min(int(min_train_points), max(5, len(target_df) - 1)))

        candidate_cfgs: list[tuple[int, int]] = [
            (primary_horizon, primary_min_train),
            (step_days, primary_min_train),
            (step_days, max(5, min(primary_min_train, len(target_df) // 2))),
            (step_days, 5),
        ]

        seen: set[tuple[int, int]] = set()
        unique_cfgs: list[tuple[int, int]] = []
        for cfg in candidate_cfgs:
            if cfg in seen:
                continue
            seen.add(cfg)
            unique_cfgs.append(cfg)

        result: dict | None = None
        used_horizon = primary_horizon
        used_min_train = primary_min_train
        last_error: str | None = None

        for cfg_horizon, cfg_min_train in unique_cfgs:
            candidate = self._run_walk_forward_market_backtest(
                target_df=target_df,
                virus_typ=virus_typ,
                horizon_days=cfg_horizon,
                min_train_points=cfg_min_train,
                delay_rules=None,
            )
            if "error" in candidate:
                last_error = str(candidate.get("error"))
                continue
            result = candidate
            used_horizon = cfg_horizon
            used_min_train = cfg_min_train
            break

        if not result:
            return {
                "error": (
                    "Walk-forward OOS-Kalibrierung konnte keine validen Folds erzeugen. "
                    f"Letzter Fehler: {last_error or 'unbekannt'}"
                ),
                "attempted_configs": [
                    {"horizon_days": h, "min_train_points": m}
                    for h, m in unique_cfgs
                ],
            }

        df_sim = pd.DataFrame([{
            "date": row["date"],
            "bio": row.get("bio", 0.0),
            "real_qty": row.get("real_qty", 0.0),
        } for row in result.get("chart_data", []) if not row.get("is_forecast")])
        lead_lag = self._augment_lead_lag_with_horizon(
            self._best_bio_lead_lag(df_sim),
            horizon_days=used_horizon,
        )

        metrics = result.get("metrics", {})
        optimized_weights = result.get("optimized_weights", dict(self.DEFAULT_WEIGHTS))
        correlation_signed = float(metrics.get("correlation", 0.0) or 0.0)
        llm_insight = self._generate_llm_insight(
            weights=optimized_weights,
            r2=float(metrics.get("r2_score", 0.0) or 0.0),
            correlation=correlation_signed,
            mae=float(metrics.get("mae", 0.0) or 0.0),
            n_samples=int(metrics.get("data_points", 0) or 0),
            virus_typ=virus_typ,
        )

        proof_text = (
            f"OOS Walk-forward über {metrics.get('data_points', 0)} Folds "
            f"(Horizont {used_horizon}T, min_train_points={used_min_train}). "
            f"R²={metrics.get('r2_score')}, |Korrelation|={metrics.get('correlation_pct')}%, "
            f"sMAPE={metrics.get('smape')}, Lead/Lag (effektiv)="
            f"{lead_lag.get('effective_lead_days', 0)} Tage."
        )

        result["mode"] = "CALIBRATION_OOS"
        result["proof_text"] = proof_text
        result["llm_insight"] = llm_insight
        result["lead_lag"] = lead_lag
        result["walk_forward"] = {
            **(result.get("walk_forward") or {}),
            "enabled": True,
            "horizon_days": int(used_horizon),
            "min_train_points": int(used_min_train),
            "strict_vintage_mode": bool(self.strict_vintage_mode),
            "calibration_mode": "WALK_FORWARD_OOS",
        }

        logger.info(
            "OOS-Kalibrierung abgeschlossen: R²=%s, corr=%s, folds=%s, horizon=%s, min_train=%s, weights=%s",
            result.get("metrics", {}).get("r2_score"),
            result.get("metrics", {}).get("correlation"),
            result.get("walk_forward", {}).get("folds"),
            used_horizon,
            used_min_train,
            result.get("optimized_weights"),
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
        weights_canonical = self._canonicalize_factor_weights(weights)
        dominant = max(weights_canonical, key=weights_canonical.get)
        weakest = min(weights_canonical, key=weights_canonical.get)

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
- {factor_names['bio']}: {weights_canonical['bio']*100:.0f}% Wichtigkeit
- {factor_names['market']}: {weights_canonical['market']*100:.0f}% Wichtigkeit
- {factor_names['psycho']}: {weights_canonical['psycho']*100:.0f}% Wichtigkeit
- {factor_names['context']}: {weights_canonical['context']*100:.0f}% Wichtigkeit

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
            return text
        except Exception as e:
            logger.warning(f"LLM Insight fehlgeschlagen: {e}")
            return (
                f"Die Analyse von {n_samples} Datenpunkten zeigt eine "
                f"{abs(correlation)*100:.0f}%ige Korrelation zwischen ViralFlux-Signalen "
                f"und Ihren tatsächlichen Bestellungen. Der stärkste Einflussfaktor "
                f"ist \"{factor_names[dominant]}\" ({weights_canonical[dominant]*100:.0f}%). "
                f"Wir empfehlen, das Modell mit diesen optimierten Gewichten zu kalibrieren."
            )

    def _map_feature_to_factor(self, feature_name: str) -> str:
        """Mappt beliebige Feature-Namen auf die vier Business-Faktoren."""
        key = str(feature_name or "").strip().lower()
        if not key:
            return "market"

        if (
            key.startswith("bio")
            or key.startswith("ww_")
            or "positivity" in key
            or key.startswith("xdisease")
            or key.startswith("survstat_xdisease")
        ):
            return "bio"

        if key.startswith("psycho") or "trend" in key:
            return "psycho"

        if (
            key.startswith("context")
            or key.startswith("weather")
            or key.startswith("school")
            or key.startswith("week_")
            or key.startswith("seasonal")
        ):
            return "context"

        if (
            key.startswith("market")
            or key.startswith("are_")
            or key.startswith("target_")
            or key.startswith("grippeweb")
            or key.startswith("notaufnahme")
        ):
            return "market"

        return "market"

    def _canonicalize_factor_weights(self, weights: Optional[dict]) -> dict[str, float]:
        """Normiert Gewichte auf bio/market/psycho/context für UI/LLM-Kompatibilität."""
        grouped = {k: 0.0 for k in self.DEFAULT_WEIGHTS.keys()}
        if not isinstance(weights, dict) or not weights:
            return dict(self.DEFAULT_WEIGHTS)

        for raw_key, raw_value in weights.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(value):
                continue
            value = abs(value)
            factor = raw_key if raw_key in grouped else self._map_feature_to_factor(raw_key)
            grouped[factor] += value

        total = float(sum(grouped.values()))
        if total <= 0:
            return dict(self.DEFAULT_WEIGHTS)

        return {
            key: round(grouped[key] / total, 3)
            for key in grouped.keys()
        }

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
        canonical_weights = self._canonicalize_factor_weights(new_weights)
        metrics = result["metrics"]

        # 4. Speichern als Global Default
        self._save_global_defaults(
            canonical_weights, metrics["r2_score"], len(df)
        )

        message = (
            f"Analyse über {len(df)} Datenpunkte "
            f"({len(df) / 365 * 7:.1f} Wochen) abgeschlossen. "
            f"Basis: {target_source}. "
            f"Neue Gewichtung: Bio {canonical_weights['bio'] * 100:.0f}%, "
            f"Markt {canonical_weights['market'] * 100:.0f}%, "
            f"Psycho {canonical_weights['psycho'] * 100:.0f}%, "
            f"Kontext {canonical_weights['context'] * 100:.0f}%."
        )

        return {
            "status": "success",
            "calibration_source": target_source,
            "period_days": days_back,
            "data_points": len(df),
            "new_weights": new_weights,
            "new_weights_canonical": canonical_weights,
            "metrics": metrics,
            "message": message,
        }

    def _save_global_defaults(
        self, weights: dict, score: float, days_count: int
    ):
        """Speichere optimierte Gewichte als Global Default."""
        weights = self._canonicalize_factor_weights(weights)
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
        config.last_calibration_date = utc_now()
        config.calibration_source = "GLOBAL_AUTO_3Y"

        self.db.commit()
        logger.info(f"Globale System-Defaults aktualisiert (R²={score:.2f})")

    # ─────────────────────────────────────────────────────────────────────────
    # Business Pitch Report: ML Detection Advantage vs RKI Reporting
    # ─────────────────────────────────────────────────────────────────────────

    def generate_business_pitch_report(
        self,
        disease: str | list[str] = "Norovirus-Gastroenteritis",
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
            disease: RKI disease name(s) for SurvstatKreisData ground truth.
                     Pass ``"GELO_ATEMWEG"`` to use the preset list of
                     Gelo-relevant respiratory diseases (Influenza, RSV,
                     Keuchhusten, Mycoplasma, Parainfluenza — excl. COVID).
                     A list of disease names is also accepted and will be
                     aggregated into a single time series.
            virus_typ: Virus type for wastewater/signal computation.
            season_start: Start of evaluation window (ISO date).
            season_end: End of evaluation window (ISO date).
            output_path: CSV output path. Defaults to data/processed/backtest_business_report.csv.

        Returns:
            Dict with summary metrics and path to exported CSV.
        """
        from pathlib import Path
        from app.models.database import SurvstatKreisData

        # ── Resolve disease list ──
        if isinstance(disease, str) and disease.upper() == "GELO_ATEMWEG":
            disease_list = self.GELO_ATEMWEG_DISEASES
            disease_label = "Gelo Atemwegsinfekte (Influenza+RSV+Keuchhusten+Mycoplasma+Parainfluenza)"
        elif isinstance(disease, list):
            disease_list = disease
            disease_label = " + ".join(disease_list)
        else:
            disease_list = [disease]
            disease_label = disease

        start_dt = datetime.strptime(season_start, "%Y-%m-%d")
        end_dt = datetime.strptime(season_end, "%Y-%m-%d")

        # Load 8 extra weeks before the evaluation window for bio_score baseline
        lookback_dt = start_dt - timedelta(weeks=8)

        logger.info(
            "Business Pitch Report: diseases=%s, virus=%s, period=%s to %s",
            disease_label, virus_typ, season_start, season_end,
        )

        # ── 1. Load ground truth: weekly national case counts from SurvstatKreisData ──
        kreis_rows = self.db.query(
            SurvstatKreisData.year,
            SurvstatKreisData.week,
            SurvstatKreisData.week_label,
            func.sum(SurvstatKreisData.fallzahl).label("total_cases"),
        ).filter(
            SurvstatKreisData.disease.in_(disease_list),
        ).group_by(
            SurvstatKreisData.year,
            SurvstatKreisData.week,
            SurvstatKreisData.week_label,
        ).order_by(
            SurvstatKreisData.year,
            SurvstatKreisData.week,
        ).all()

        if not kreis_rows:
            return {"error": f"No SurvstatKreisData found for diseases: {disease_list}"}

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
                "disease": disease_label,
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
            "disease": disease_label,
            "disease_list": disease_list,
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
                f"ViralFlux-Signal zeigte {ttd_days} Tage vor dem RKI-Peak "
                f"({rki_peak_date.strftime('%Y-%m-%d')}, {rki_peak_cases:,} Faelle) ein Frühsignal. "
                f"Erste Warnung: {ml_first_alert_date.strftime('%Y-%m-%d') if ml_first_alert_date else 'k.A.'}. "
                f"(Retrospektive Analyse — kein garantierter Vorhersagevorteil.)"
            ) if ml_first_alert_date else (
                f"Kein ML-Frühsignal im Evaluationszeitraum ausgelöst. "
                f"RKI-Peak: {rki_peak_date.strftime('%Y-%m-%d')} ({rki_peak_cases:,} Faelle)."
            ),
        }

        logger.info("Business proof: TTD=%d days, peak=%s", ttd_days, rki_peak_date.strftime("%Y-%m-%d"))
        return summary
