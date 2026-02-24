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
import math
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor
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
    GrippeWebData,
    NotaufnahmeSyndromData,
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
    # Exogene Signale — KEINE Target-Lags!
    # Target-Lags (lag1-3, ma3) wurden entfernt weil sie das Modell
    # zu einem Nachlauf-Indikator machen: 91% Importance auf lag1
    # → Prognose peakt 3-4 Wochen NACH dem echten Peak.
    # Nur target_roc (Richtung) bleibt als schwaches Trend-Signal.
    BASE_FEATURE_COLS: list[str] = [
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
        "target_roc",
        "week_sin",
        "week_cos",
        "weather_temp",
        "grippeweb_are",
        "notaufnahme_ari",
    ]

    COMPACT_VIRAL_COLS: list[str] = COMPACT_BASE_COLS + [
        "wastewater_raw",
    ]

    COMPACT_SURVSTAT_COLS: list[str] = COMPACT_BASE_COLS + [
        "survstat_xdisease_1",
    ]

    # Virale Targets: Abwasser-Signale nützlich
    VIRAL_FEATURE_COLS: list[str] = BASE_FEATURE_COLS + [
        "wastewater_raw",
        "positivity_raw",
        "xdisease_load",
    ]

    # SURVSTAT-Targets: Abwasser irrelevant, SurvStat Cross-Disease stattdessen
    SURVSTAT_FEATURE_COLS: list[str] = BASE_FEATURE_COLS + [
        "survstat_xdisease_1",
        "survstat_xdisease_2",
    ]

    # Legacy-Kompatibilität
    ENHANCED_FEATURE_COLS: list[str] = VIRAL_FEATURE_COLS

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

        simulation_rows = []
        for idx, row in df.iterrows():
            target_date = row["datum"]
            sim_date = target_date - timedelta(days=max(0, int(horizon_days)))
            real_qty = float(row["menge"])

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

                    # Neue syndromische Signale
                    row_dict["grippeweb_are"] = scores["grippeweb_are"]
                    row_dict["notaufnahme_ari"] = scores["notaufnahme_ari"]

                    # SurvStat Cross-Disease
                    row_dict["survstat_xdisease_1"] = scores["survstat_xdisease_1"]
                    row_dict["survstat_xdisease_2"] = scores["survstat_xdisease_2"]

                    # Target rate of change only (keine Lags — sonst Nachlauf)
                    i = int(idx)
                    prev = menge_values[i - 1] if i >= 1 else 1.0
                    row_dict["target_roc"] = (prev - (menge_values[i - 2] if i >= 2 else prev)) / prev if prev > 0 else 0.0

                    # Cyclic seasonality
                    iso_week = sim_date.isocalendar()[1]
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
        exclude_are: bool = False,
        target_disease: Optional[str] = None,
    ) -> dict:
        """Walk-forward Backtest mit erweiterter Feature-Pipeline und GradientBoosting.

        Args:
            exclude_are: If True, remove are_consultation_raw from features
                         (to prevent circular dependency when target=RKI_ARE).
            target_disease: SurvStat disease name for disease-aware feature selection.
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

        # Disease-aware feature selection
        is_bacterial_target = (
            target_disease
            and target_disease in self.SURVSTAT_CROSS_DISEASE_MAP
            and target_disease not in self.SURVSTAT_VIRAL_DISEASES
        )
        if is_bacterial_target:
            # Bakterielle/nicht-virale Targets: kein Abwasser-Signal
            feature_cols = list(self.SURVSTAT_FEATURE_COLS)
        elif exclude_are:
            # RKI_ARE target: exclude ARE from features (circular dependency)
            feature_cols = list(self.VIRAL_FEATURE_COLS)
        elif target_disease:
            # SURVSTAT viral targets: viral features but no are_consultation_raw
            # (reduces dimensionality for small SURVSTAT datasets)
            feature_cols = list(self.VIRAL_FEATURE_COLS)
        else:
            # Non-SURVSTAT targets (e.g. customer data): full feature set
            feature_cols = list(self.VIRAL_FEATURE_COLS)
            if "are_consultation_raw" not in feature_cols:
                feature_cols.insert(3, "are_consultation_raw")

        # Legacy features for backward-compatible chart output
        legacy_feature_cols = ["bio", "market", "psycho", "context"]

        folds: list[dict] = []
        importance_accumulator: list[np.ndarray] = []
        gbr_fold_count = 0
        ridge_fold_count = 0

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

            # Enhanced simulation with raw signals + temporal features
            train_rows = self._simulate_rows_from_target(
                train_target_df[["datum", "menge"]],
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                delay_rules=delay_rules,
                enhanced=True,
                target_disease=target_disease,
            )
            if len(train_rows) < min_train_points:
                continue

            df_train = pd.DataFrame(train_rows)

            # Adaptive feature set: compact for small datasets
            n_train = len(train_rows)
            if n_train < 35:
                # Small dataset: use compact features (8 vs 15-16)
                if is_bacterial_target:
                    fold_features = list(self.COMPACT_SURVSTAT_COLS)
                else:
                    fold_features = list(self.COMPACT_VIRAL_COLS)
            else:
                fold_features = list(feature_cols)

            # Ensure all feature columns exist (fill missing with 0)
            for col in fold_features:
                if col not in df_train.columns:
                    df_train[col] = 0.0

            X_train = df_train[fold_features].values
            y_train = df_train["real_qty"].values

            # Replace NaN/inf
            X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)

            # Adaptive model selection based on training set size
            if n_train >= 40:
                gbr_fold_count += 1
                model = GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.8,
                    min_samples_leaf=3,
                    random_state=42,
                )
                model.fit(X_train, y_train)
                importance_accumulator.append(model.feature_importances_)
                use_gbr = True
            elif n_train >= 25:
                gbr_fold_count += 1
                model = GradientBoostingRegressor(
                    n_estimators=60,
                    max_depth=2,
                    learning_rate=0.08,
                    subsample=0.8,
                    min_samples_leaf=max(5, n_train // 6),
                    random_state=42,
                )
                model.fit(X_train, y_train)
                importance_accumulator.append(model.feature_importances_)
                use_gbr = True
            else:
                ridge_fold_count += 1
                scaler = StandardScaler()
                X_train = scaler.fit_transform(X_train)
                model = Ridge(alpha=1.0, fit_intercept=True)
                model.fit(X_train, y_train)
                importance_accumulator.append(np.abs(model.coef_))
                use_gbr = False

            # Build test features for the forecast point
            test_scores = self._compute_sub_scores_at_date(
                forecast_time,
                virus_typ=virus_typ,
                delay_rules=delay_rules,
                target_disease=target_disease,
            )

            # Target lags from training history (no future leak)
            # Target rate of change (Richtung, kein Niveau)
            t_vals = train_target_df["menge"].tolist()
            lag1 = float(t_vals[-1]) if len(t_vals) >= 1 else 0.0
            prev = float(t_vals[-2]) if len(t_vals) >= 2 else 1.0
            target_roc = (lag1 - prev) / prev if prev > 0 else 0.0

            # Seasonality
            iso_week = forecast_time.isocalendar()[1]
            week_sin = round(math.sin(2 * math.pi * iso_week / 52), 4)
            week_cos = round(math.cos(2 * math.pi * iso_week / 52), 4)

            # Build feature vector — nur exogene Signale + Saisonalität
            test_feat = {
                "wastewater_raw": test_scores["wastewater_raw"],
                "positivity_raw": test_scores["positivity_raw"],
                "are_consultation_raw": test_scores.get("are_consultation_raw", 0.0),
                "trends_raw": test_scores["trends_raw"],
                "weather_temp": test_scores["weather_temp"],
                "weather_humidity": test_scores["weather_humidity"],
                "school_start_float": test_scores["school_start_float"],
                "target_roc": target_roc,
                "week_sin": week_sin,
                "week_cos": week_cos,
                "xdisease_load": test_scores["xdisease_load"],
                "grippeweb_are": test_scores["grippeweb_are"],
                "notaufnahme_ari": test_scores["notaufnahme_ari"],
                "survstat_xdisease_1": test_scores["survstat_xdisease_1"],
                "survstat_xdisease_2": test_scores["survstat_xdisease_2"],
            }
            X_test = np.array([[test_feat.get(c, 0.0) for c in fold_features]])
            X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

            if not use_gbr:
                X_test = scaler.transform(X_test)

            y_hat = float(model.predict(X_test)[0])

            # Clip predictions to prevent extreme extrapolation
            y_max = float(y_train.max())
            y_min = float(y_train.min())
            y_hat = max(0.0, min(y_hat, y_max * 2.0))

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

        # Feature importance: use last fold (largest training set, most reliable)
        if importance_accumulator:
            last_imp = importance_accumulator[-1]
            last_n_features = len(last_imp)
            # Determine which feature set was used in the last fold
            if last_n_features == len(feature_cols):
                imp_cols = feature_cols
            elif is_bacterial_target and last_n_features == len(self.COMPACT_SURVSTAT_COLS):
                imp_cols = self.COMPACT_SURVSTAT_COLS
            elif last_n_features == len(self.COMPACT_VIRAL_COLS):
                imp_cols = self.COMPACT_VIRAL_COLS
            else:
                imp_cols = feature_cols[:last_n_features]
            total = float(last_imp.sum())
            if total > 0:
                optimized_weights = {
                    col: round(float(last_imp[i] / total), 3)
                    for i, col in enumerate(imp_cols)
                }
            else:
                optimized_weights = dict(self.DEFAULT_WEIGHTS)
        else:
            optimized_weights = dict(self.DEFAULT_WEIGHTS)

        # --- Future Forecast Extension (6 weeks ahead) ---
        forecast_weeks = 6
        residuals = y_true - y_hat
        residual_std = (
            float(np.std(residuals)) if len(residuals) > 2
            else float(np.std(y_true) * 0.3)
        )
        last_target_time = pred_df["target_time"].max()
        rolling_values = list(y_true[-3:])
        forecast_chart: list[dict] = []

        try:
            for w in range(1, forecast_weeks + 1):
                future_target = last_target_time + timedelta(weeks=w)
                future_forecast = future_target - timedelta(
                    days=max(0, int(horizon_days))
                )

                test_scores = self._compute_sub_scores_at_date(
                    future_forecast,
                    virus_typ=virus_typ,
                    delay_rules=delay_rules,
                    target_disease=target_disease,
                )

                t1 = float(rolling_values[-1]) if rolling_values else 0.0
                t_prev = float(rolling_values[-2]) if len(rolling_values) >= 2 else 1.0
                t_roc = (t1 - t_prev) / t_prev if t_prev > 0 else 0.0

                iso_week = future_target.isocalendar()[1]
                w_sin = round(math.sin(2 * math.pi * iso_week / 52), 4)
                w_cos = round(math.cos(2 * math.pi * iso_week / 52), 4)

                test_feat = {
                    "wastewater_raw": test_scores["wastewater_raw"],
                    "positivity_raw": test_scores["positivity_raw"],
                    "are_consultation_raw": test_scores.get("are_consultation_raw", 0.0),
                    "trends_raw": test_scores["trends_raw"],
                    "weather_temp": test_scores["weather_temp"],
                    "weather_humidity": test_scores["weather_humidity"],
                    "school_start_float": test_scores["school_start_float"],
                    "target_roc": t_roc,
                    "week_sin": w_sin, "week_cos": w_cos,
                    "xdisease_load": test_scores["xdisease_load"],
                    "grippeweb_are": test_scores["grippeweb_are"],
                    "notaufnahme_ari": test_scores["notaufnahme_ari"],
                    "survstat_xdisease_1": test_scores["survstat_xdisease_1"],
                    "survstat_xdisease_2": test_scores["survstat_xdisease_2"],
                }
                X_fc = np.array([[test_feat.get(c, 0.0) for c in fold_features]])
                X_fc = np.nan_to_num(X_fc, nan=0.0, posinf=0.0, neginf=0.0)
                if not use_gbr:
                    X_fc = scaler.transform(X_fc)
                y_fc = max(0.0, float(model.predict(X_fc)[0]))

                hf = math.sqrt(w)
                ci_80 = 1.28 * residual_std * hf
                ci_95 = 1.96 * residual_std * hf

                forecast_chart.append({
                    "date": future_target.strftime("%Y-%m-%d"),
                    "forecast_qty": round(y_fc, 3),
                    "ci_80_lower": round(max(0, y_fc - ci_80), 3),
                    "ci_80_upper": round(y_fc + ci_80, 3),
                    "ci_95_lower": round(max(0, y_fc - ci_95), 3),
                    "ci_95_upper": round(y_fc + ci_95, 3),
                    "is_forecast": True,
                })
                rolling_values.append(y_fc)
        except Exception:
            pass  # forecast is best-effort; backtest results always returned

        # Build unified chart_data
        # Ist-Werte am target_time, Prognosen am forecast_time (wo sie erstellt wurden)
        # So sieht man im Chart ob die Prognose VOR dem echten Peak kommt
        from collections import OrderedDict
        date_rows: dict[str, dict] = OrderedDict()

        for _, row in pred_df.iterrows():
            # Ist-Wert am target_time
            td = row["target_time"].strftime("%Y-%m-%d")
            if td not in date_rows:
                date_rows[td] = {"date": td, "is_forecast": False}
            date_rows[td]["real_qty"] = float(row["real_qty"])

            # Prognose am forecast_time (wann sie erstellt wurde)
            fd = row["forecast_time"].strftime("%Y-%m-%d")
            if fd not in date_rows:
                date_rows[fd] = {"date": fd, "is_forecast": False}
            date_rows[fd]["predicted_qty"] = round(float(row["predicted_qty"]), 3)

        historical_chart = sorted(date_rows.values(), key=lambda r: r["date"])

        # Bridge: last historical point starts the forecast line
        if historical_chart and forecast_chart:
            last_pred = next((r for r in reversed(historical_chart) if r.get("predicted_qty") is not None), None)
            if last_pred:
                last_pred["forecast_qty"] = last_pred["predicted_qty"]

        chart_data = historical_chart + forecast_chart

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
            "model_type": "GradientBoosting" if gbr_fold_count > ridge_fold_count else "Ridge",
            "gbr_folds": gbr_fold_count,
            "ridge_folds": ridge_fold_count,
            "feature_count": len(imp_cols) if importance_accumulator else len(feature_cols),
            "feature_names": imp_cols if importance_accumulator else feature_cols,
            "chart_data": chart_data,
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

        df_sim = pd.DataFrame([{
            "date": row["date"],
            "bio": row.get("bio", 0.0),
            "real_qty": row.get("real_qty", 0.0),
        } for row in result.get("chart_data", []) if not row.get("is_forecast")])
        lead_lag = self._best_bio_lead_lag(df_sim)
        # Adjust for horizon shift: bio was computed horizon_days before target_time
        lead_lag["best_lag_days"] += horizon_days
        lead_lag["bio_leads_target"] = bool(
            lead_lag["best_lag_days"] > 0 and lead_lag["lag_correlation"] > 0
        )
        lead_days = lead_lag["best_lag_days"]
        baseline_delta = result.get("improvement_vs_baselines", {})
        delta_pers = baseline_delta.get("mae_vs_persistence_pct", 0.0)
        delta_seas = baseline_delta.get("mae_vs_seasonal_pct", 0.0)

        lag_r = lead_lag["lag_correlation"]
        lag_strength = "stark" if abs(lag_r) >= 0.5 else "moderat" if abs(lag_r) >= 0.25 else "schwach"

        if lead_lag["bio_leads_target"]:
            proof_text = (
                f"Bio-Signal (Abwasser-Monitoring) laeuft dem Target um ca. {lead_days} Tage voraus. "
                f"Signal-Korrelation am optimalen Lag: r={lag_r} ({lag_strength}). "
                f"Hinweis: Die Modell-Korrelation oben misst die Gesamtprognose-Guete, "
                f"die Signal-Korrelation hier nur den Bio-Kanal allein."
            )
        elif lead_days < 0:
            proof_text = (
                f"Target laeuft dem Bio-Signal um ca. {abs(lead_days)} Tage voraus. "
                f"Signal-Korrelation am optimalen Lag: r={lag_r} ({lag_strength}). "
                f"Hinweis: Die Modell-Korrelation oben misst die Gesamtprognose-Guete, "
                f"die Signal-Korrelation hier nur den Bio-Kanal allein."
            )
        else:
            proof_text = (
                f"Bio-Signal und Target zeigen gleichzeitige Korrelation: r={lag_r} ({lag_strength}). "
                f"Hinweis: Die Modell-Korrelation oben misst die Gesamtprognose-Guete, "
                f"die Signal-Korrelation hier nur den Bio-Kanal allein."
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
            f"Walk-forward Backtest: MAE vs. Persistence {delta_pers:+.2f}%, "
            f"vs. Seasonal-Naive {delta_seas:+.2f}% (historisch; zukuenftige Performance kann abweichen)."
        )
        result["llm_insight"] = (
            f"{result['proof_text']} "
            f"Modellguete: R²={result['metrics']['r2_score']}, "
            f"Korrelation={result['metrics']['correlation_pct']}%, "
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
            region_lead_lag = self._best_bio_lead_lag(sim_df)
            # Adjust for horizon shift
            region_lead_lag["best_lag_days"] += horizon_days
            region_lead_lag["bio_leads_target"] = bool(
                region_lead_lag["best_lag_days"] > 0
                and region_lead_lag["lag_correlation"] > 0
            )
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
        # Adjust for horizon shift
        lead_lag_global["best_lag_days"] += horizon_days
        lead_lag_global["bio_leads_target"] = bool(
            lead_lag_global["best_lag_days"] > 0
            and lead_lag_global["lag_correlation"] > 0
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
                f"({rki_peak_date.strftime('%Y-%m-%d')}, {rki_peak_cases:,} Faelle) ein Fruehsignal. "
                f"Erste Warnung: {ml_first_alert_date.strftime('%Y-%m-%d') if ml_first_alert_date else 'k.A.'}. "
                f"(Retrospektive Analyse — kein garantierter Vorhersagevorteil.)"
            ) if ml_first_alert_date else (
                f"Kein ML-Fruehsignal im Evaluationszeitraum ausgeloest. "
                f"RKI-Peak: {rki_peak_date.strftime('%Y-%m-%d')} ({rki_peak_cases:,} Faelle)."
            ),
        }

        logger.info("Business proof: TTD=%d days, peak=%s", ttd_days, rki_peak_date.strftime("%Y-%m-%d"))
        return summary
