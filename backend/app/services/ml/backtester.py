"""BacktestService — Modell-Kalibrierung via historischem Backtesting.

Simuliert den historischen Score-/Forecast-Stack für jeden Tag in der
Kundenhistorie, optimiert Gewichte via Ridge Regression und generiert
begleitende Insights.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
import math
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
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
    BacktestRun,
    BacktestPoint,
)
from app.services.ml.forecast_contracts import (
    DEFAULT_DECISION_BASELINE_WINDOW_DAYS,
    DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
    DEFAULT_DECISION_HORIZON_DAYS,
    HEURISTIC_EVENT_SCORE_SOURCE,
)
from app.services.ml import (
    backtester_metrics,
    backtester_reporting,
    backtester_simulation,
    backtester_walk_forward,
    backtester_workflows,
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
        """Delegiert die Simulationszeilen an das ausgelagerte Hilfsmodul."""
        return backtester_simulation.simulate_rows_from_target(
            self,
            target_df=target_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            delay_rules=delay_rules,
            enhanced=enhanced,
            target_disease=target_disease,
        )

    def _fit_regression_from_simulation(
        self,
        df_sim: pd.DataFrame,
        virus_typ: str,
        use_llm: bool = True,
    ) -> dict:
        """Delegiert Ridge-Fit und Kennzahlen an das ausgelagerte Hilfsmodul."""
        return backtester_simulation.fit_regression_from_simulation(
            self,
            df_sim=df_sim,
            virus_typ=virus_typ,
            use_llm=use_llm,
        )

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
        """Delegiert die saisonale Baseline an das ausgelagerte Hilfsmodul."""
        return backtester_walk_forward.seasonal_naive_baseline(
            train_df,
            target_week=target_week,
            target_month=target_month,
        )

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
        """Delegiert den Walk-forward Backtest an das ausgelagerte Hilfsmodul."""
        return backtester_walk_forward.run_walk_forward_market_backtest(
            self,
            target_df=target_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            delay_rules=delay_rules,
            exclude_are=exclude_are,
            target_disease=target_disease,
        )

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
        """Delegiert den Markt-Workflow an das ausgelagerte Hilfsmodul."""
        return backtester_workflows.run_market_simulation(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            days_back=days_back,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            delay_rules=delay_rules,
            strict_vintage_mode=strict_vintage_mode,
            bundesland=bundesland,
        )

    def run_customer_simulation(
        self,
        customer_df: pd.DataFrame,
        virus_typ: str = "Influenza A",
        horizon_days: int = DEFAULT_MARKET_HORIZON_DAYS,
        min_train_points: int = DEFAULT_MIN_TRAIN_POINTS,
        strict_vintage_mode: bool = True,
    ) -> dict:
        """Delegiert den Kunden-Workflow an das ausgelagerte Hilfsmodul."""
        return backtester_workflows.run_customer_simulation(
            self,
            customer_df=customer_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            strict_vintage_mode=strict_vintage_mode,
        )

    def run_calibration(
        self,
        customer_df: pd.DataFrame,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
        min_train_points: int = DEFAULT_MIN_TRAIN_POINTS,
        strict_vintage_mode: bool = True,
    ) -> dict:
        """Delegiert den OOS-Kalibrierungs-Workflow an das ausgelagerte Hilfsmodul."""
        return backtester_workflows.run_calibration(
            self,
            customer_df=customer_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            strict_vintage_mode=strict_vintage_mode,
        )

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
        """Delegiert die globale Kalibrierung an das ausgelagerte Reporting-Modul."""
        return backtester_reporting.run_global_calibration(
            self,
            virus_typ=virus_typ,
            days_back=days_back,
        )

    def _save_global_defaults(
        self, weights: dict, score: float, days_count: int
    ):
        """Delegiert das Speichern globaler Defaults an das Reporting-Modul."""
        return backtester_reporting.save_global_defaults(
            self,
            weights,
            score,
            days_count,
        )

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
        """Delegiert den Business-Proof-Report an das ausgelagerte Reporting-Modul."""
        return backtester_reporting.generate_business_pitch_report(
            self,
            disease=disease,
            virus_typ=virus_typ,
            season_start=season_start,
            season_end=season_end,
            output_path=output_path,
        )
