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
    backtester_autoregressive,
    backtester_explanations,
    backtester_metrics,
    backtester_persistence,
    backtester_reporting,
    backtester_simulation,
    backtester_signals,
    backtester_targets,
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
        return backtester_signals.asof_filter(
            self,
            model_cls,
            event_col,
            cutoff,
            and_fn=and_,
            or_fn=or_,
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
        return backtester_signals.wastewater_at_date(
            self,
            target,
            virus_typ,
            available_cutoff=available_cutoff,
            timedelta_cls=timedelta,
        )

    def _amelag_raw_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> Optional[float]:
        return backtester_signals.amelag_raw_at_date(
            self,
            target,
            virus_typ,
            available_cutoff=available_cutoff,
        )

    def _wastewater_lags_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        return backtester_signals.wastewater_lags_at_date(
            self,
            target,
            virus_typ,
            available_cutoff=available_cutoff,
            timedelta_cls=timedelta,
        )

    def _positivity_rate_at_date(
        self,
        target: datetime,
        virus_typ: str,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        return backtester_signals.positivity_rate_at_date(
            self,
            target,
            virus_typ,
            available_cutoff=available_cutoff,
            timedelta_cls=timedelta,
        )

    def _trends_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        return backtester_signals.trends_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
            timedelta_cls=timedelta,
        )

    def _weather_risk_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        return backtester_signals.weather_risk_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
        )

    def _weather_risk_components_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        return backtester_signals.weather_risk_components_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
        )

    def _school_start_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> bool:
        return backtester_signals.school_start_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
            timedelta_cls=timedelta,
        )

    def _cross_disease_load_at_date(
        self,
        target: datetime,
        xdisease_viruses: list[str],
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        return backtester_signals.cross_disease_load_at_date(
            self,
            target,
            xdisease_viruses,
            available_cutoff=available_cutoff,
            timedelta_cls=timedelta,
        )

    def _grippeweb_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        return backtester_signals.grippeweb_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
        )

    def _notaufnahme_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        return backtester_signals.notaufnahme_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
        )

    def _survstat_cross_disease_at_date(
        self,
        target: datetime,
        target_disease: str,
        available_cutoff: Optional[datetime] = None,
    ) -> dict[str, float]:
        return backtester_signals.survstat_cross_disease_at_date(
            self,
            target,
            target_disease,
            available_cutoff=available_cutoff,
        )

    def _are_consultation_at_date(
        self,
        target: datetime,
        available_cutoff: Optional[datetime] = None,
    ) -> float:
        return backtester_signals.are_consultation_at_date(
            self,
            target,
            available_cutoff=available_cutoff,
        )

    def _market_proxy_at_date(
        self,
        target: datetime,
        bio: float,
        wastewater: float,
        positivity: float,
    ) -> float:
        return backtester_signals.market_proxy_at_date(
            target,
            bio=bio,
            wastewater=wastewater,
            positivity=positivity,
        )

    def _compute_sub_scores_at_date(
        self,
        target: datetime,
        virus_typ: str,
        delay_rules: Optional[dict[str, int]] = None,
        target_disease: Optional[str] = None,
    ) -> dict[str, float]:
        return backtester_signals.compute_sub_scores_at_date(
            self,
            target,
            virus_typ,
            delay_rules=delay_rules,
            target_disease=target_disease,
            timedelta_cls=timedelta,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # XGBoost-Features: rein autoregressive SURVSTAT-Zeitreihe
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_survstat_ar_row(
        series: pd.Series,
        idx: int,
        target_date: datetime,
    ) -> dict[str, float]:
        return backtester_autoregressive.build_survstat_ar_row(
            series=series,
            idx=idx,
            target_date=target_date,
            xgboost_survstat_features=BacktestService.XGBOOST_SURVSTAT_FEATURES,
        )

    def _build_survstat_ar_training_data(
        self,
        train_df: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        return backtester_autoregressive.build_survstat_ar_training_data(
            train_df,
            xgboost_survstat_features=self.XGBOOST_SURVSTAT_FEATURES,
            build_survstat_ar_row_fn=self._build_survstat_ar_row,
        )

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
        return backtester_targets.resolve_survstat_disease(self, source_token)

    def _load_market_target(
        self,
        target_source: str = "RKI_ARE",
        days_back: int = 730,
        bundesland: str = "",
    ) -> Tuple[pd.DataFrame, dict]:
        return backtester_targets.load_market_target(
            self,
            target_source=target_source,
            days_back=days_back,
            bundesland=bundesland,
        )

    @staticmethod
    def _estimate_step_days(df_sim: pd.DataFrame) -> int:
        return backtester_metrics.estimate_step_days(df_sim)

    def _build_planning_curve(
        self,
        target_df: pd.DataFrame,
        virus_typ: str = "Influenza A",
        days_back: int = 2500,
    ) -> dict:
        return backtester_targets.build_planning_curve(
            self,
            target_df=target_df,
            virus_typ=virus_typ,
            days_back=days_back,
        )

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
        """Delegiert die Persistenz an das ausgelagerte Hilfsmodul."""
        return backtester_persistence.persist_backtest_result(
            self,
            mode=mode,
            virus_typ=virus_typ,
            target_source=target_source,
            target_key=target_key,
            target_label=target_label,
            result=result,
            parameters=parameters,
            pd_module=pd,
            uuid4_fn=uuid4,
            logger_obj=logger,
        )

    def list_backtest_runs(self, mode: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Delegiert die UI-Historie an das ausgelagerte Hilfsmodul."""
        return backtester_persistence.list_backtest_runs(
            self,
            mode=mode,
            limit=limit,
        )

    def get_backtest_run(self, run_id: str) -> dict | None:
        """Delegiert das Laden eines Backtest-Laufs an das ausgelagerte Hilfsmodul."""
        return backtester_persistence.get_backtest_run(self, run_id)

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
        """Delegiert die Erklär-Generierung an das ausgelagerte Hilfsmodul."""
        return backtester_explanations.generate_llm_insight(
            self,
            weights=weights,
            r2=r2,
            correlation=correlation,
            mae=mae,
            n_samples=n_samples,
            virus_typ=virus_typ,
            logger_obj=logger,
        )

    def _map_feature_to_factor(self, feature_name: str) -> str:
        """Delegiert die Faktor-Zuordnung an das ausgelagerte Hilfsmodul."""
        return backtester_explanations.map_feature_to_factor(feature_name)

    def _canonicalize_factor_weights(self, weights: Optional[dict]) -> dict[str, float]:
        """Delegiert die Gewichts-Normierung an das ausgelagerte Hilfsmodul."""
        return backtester_explanations.canonicalize_factor_weights(
            self,
            weights,
            np_module=np,
            map_feature_to_factor_fn=self._map_feature_to_factor,
        )

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
