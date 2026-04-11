"""Calibrated regional forecast inference and media activation service."""

from __future__ import annotations
from app.core.time import utc_now

import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from app.core.config import get_settings
from app.models.database import BacktestPoint, BacktestRun, MLForecast
from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.campaign_recommendation_service import CampaignRecommendationService
from app.services.media.truth_layer_service import TruthLayerService
from app.services.ml import regional_forecast_artifacts
from app.services.ml import regional_forecast_media
from app.services.ml import regional_forecast_prediction
from app.services.ml import regional_forecast_truth
from app.services.ml import regional_forecast_views
from app.services.ml import regional_forecast_workflows
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.forecast_orchestrator import ForecastOrchestrator
from app.services.ml.forecast_horizon_utils import (
    SUPPORTED_FORECAST_HORIZONS,
    ensure_supported_horizon,
    regional_horizon_support_status,
    regional_model_artifact_dir,
)
from app.services.ml.regional_decision_engine import RegionalDecisionEngine
from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_media_allocation_engine import RegionalMediaAllocationEngine
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.models.tsfm_adapter import TSFMAdapter
from app.services.ml.regional_panel_utils import (
    EVENT_DEFINITION_VERSION,
    TARGET_WINDOW_DAYS,
    activation_policy_for_virus,
    rollout_mode_for_virus,
    signal_bundle_version_for_virus,
    sars_h7_promotion_status,
)
from app.services.ml.regional_trainer import TRAINING_ONLY_PANEL_COLUMNS, _virus_slug
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore
from app.services.source_coverage_semantics import ARTIFACT_SOURCE_COVERAGE_SCOPE

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"

MEDIA_CHANNELS = {
    "high": ["Banner (programmatic)", "Digi-CLP (regional)", "Meta (regional)", "LinkedIn (Fachkreise)"],
    "medium": ["Banner (programmatic)", "Meta (regional)"],
    "low": ["Meta (national awareness)"],
}

DEFAULT_PORTFOLIO_PRODUCTS = {
    "Influenza A": ["GeloMyrtol forte", "GeloRevoice"],
    "Influenza B": ["GeloMyrtol forte", "GeloRevoice"],
    "SARS-CoV-2": ["GeloMyrtol forte"],
    "RSV A": ["GeloMyrtol forte", "GeloBronchial"],
}

_TRUTH_LOOKBACK_WEEKS = 26


class RegionalForecastService:
    """Generate calibrated pooled forecasts and gated media actions."""

    def __init__(self, db, models_dir: Path | None = None):
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.feature_builder = RegionalFeatureBuilder(db)
        self.orchestrator = ForecastOrchestrator()
        self.decision_engine = RegionalDecisionEngine()
        self.media_allocation_engine = RegionalMediaAllocationEngine()
        self.campaign_recommendation_service = CampaignRecommendationService()
        self.snapshot_store = RegionalOperationalSnapshotStore(db) if db is not None else None

    @staticmethod
    def _sars_h7_promotion_enabled() -> bool:
        try:
            return bool(get_settings().REGIONAL_SARS_H7_PROMOTION_ENABLED)
        except Exception:
            return False

    def _hero_timeseries_for_virus(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        lookback_points: int = 8,
    ) -> dict[str, Any] | None:
        if self.db is None:
            return None

        latest_run = (
            self.db.query(BacktestRun)
            .filter(
                BacktestRun.mode == "MARKET_CHECK",
                BacktestRun.virus_typ == virus_typ,
            )
            .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
            .first()
        )
        if latest_run is None:
            return None

        history_rows = (
            self.db.query(BacktestPoint)
            .filter(
                BacktestPoint.run_id == latest_run.run_id,
                BacktestPoint.region.is_(None),
            )
            .order_by(BacktestPoint.date.asc(), BacktestPoint.id.asc())
            .all()
        )
        actual_rows = [row for row in history_rows if row.date is not None and row.real_qty is not None]
        if not actual_rows:
            return None

        points = [
            {
                "date": row.date.date().isoformat(),
                "actual_value": round(float(row.real_qty), 1),
            }
            for row in actual_rows[-max(int(lookback_points), 1):]
        ]

        latest_forecast = (
            self.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ == virus_typ,
                MLForecast.region == "DE",
                MLForecast.horizon_days == int(horizon_days),
            )
            .order_by(MLForecast.created_at.desc(), MLForecast.forecast_date.desc(), MLForecast.id.desc())
            .first()
        )

        if (
            latest_forecast is not None
            and latest_forecast.forecast_date is not None
            and latest_forecast.predicted_value is not None
        ):
            points.append(
                {
                    "date": latest_forecast.forecast_date.date().isoformat(),
                    "forecast_value": round(float(latest_forecast.predicted_value), 1),
                }
            )

        return {
            "virus_typ": virus_typ,
            "run_id": latest_run.run_id,
            "points": points,
        }

    def _effective_rollout_contract(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        metadata: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any] | None]:
        if virus_typ != "SARS-CoV-2" or int(horizon_days) != 7:
            return (
                metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ, horizon_days=horizon_days),
                metadata.get("activation_policy")
                or activation_policy_for_virus(virus_typ, horizon_days=horizon_days),
                None,
            )

        recent_snapshots = (
            self.snapshot_store.recent_scope_snapshots(
                virus_typ=virus_typ,
                horizon_days=horizon_days,
                limit=2,
            )
            if self.snapshot_store is not None
            else []
        )
        promotion = sars_h7_promotion_status(
            recent_snapshots=recent_snapshots,
            promotion_flag_enabled=self._sars_h7_promotion_enabled(),
        )
        if promotion["promoted"]:
            return (
                rollout_mode_for_virus(virus_typ, horizon_days=horizon_days, sars_h7_promoted=True),
                activation_policy_for_virus(virus_typ, horizon_days=horizon_days, sars_h7_promoted=True),
                promotion,
            )
        return (
            metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ, horizon_days=horizon_days),
            metadata.get("activation_policy")
            or activation_policy_for_virus(virus_typ, horizon_days=horizon_days),
            promotion,
        )

    def predict_region(
        self,
        virus_typ: str,
        bundesland: str,
        horizon_days: int = 7,
    ) -> dict[str, Any] | None:
        horizon = ensure_supported_horizon(horizon_days)
        payload = self.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon)
        return next((item for item in payload["predictions"] if item["bundesland"] == bundesland.upper()), None)

    def predict_all_regions(
        self,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return regional_forecast_prediction.predict_all_regions(
            self,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            regional_horizon_support_status_fn=regional_horizon_support_status,
            supported_forecast_horizons=SUPPORTED_FORECAST_HORIZONS,
            target_window_days_default=TARGET_WINDOW_DAYS,
            signal_bundle_version_for_virus_fn=signal_bundle_version_for_virus,
            rollout_mode_for_virus_fn=rollout_mode_for_virus,
            activation_policy_for_virus_fn=activation_policy_for_virus,
            event_definition_version=EVENT_DEFINITION_VERSION,
            artifact_source_coverage_scope=ARTIFACT_SOURCE_COVERAGE_SCOPE,
            geo_hierarchy_helper_cls=GeoHierarchyHelper,
            tsfm_adapter_cls=TSFMAdapter,
            pd_module=pd,
            np_module=np,
            utc_now_fn=utc_now,
        )

    def generate_media_allocation(
        self,
        virus_typ: str = "Influenza A",
        weekly_budget_eur: float = 50000,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return regional_forecast_workflows.generate_media_allocation(
            self,
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
            rollout_mode_for_virus_fn=rollout_mode_for_virus,
            activation_policy_for_virus_fn=activation_policy_for_virus,
            portfolio_products=DEFAULT_PORTFOLIO_PRODUCTS,
            media_channels=MEDIA_CHANNELS,
            utc_now_fn=utc_now,
        )

    def generate_media_activation(
        self,
        virus_typ: str = "Influenza A",
        weekly_budget_eur: float = 50000,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return regional_forecast_workflows.generate_media_activation(
            self,
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
        )

    def generate_campaign_recommendations(
        self,
        virus_typ: str = "Influenza A",
        weekly_budget_eur: float = 50000,
        horizon_days: int = 7,
        top_n: int | None = None,
    ) -> dict[str, Any]:
        return regional_forecast_workflows.generate_campaign_recommendations(
            self,
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
            top_n=top_n,
        )

    @staticmethod
    def _target_window_for_horizon(horizon_days: int) -> list[int]:
        horizon = ensure_supported_horizon(horizon_days)
        return [horizon, horizon]

    def _empty_forecast_response(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        status: str,
        message: str,
        artifact_transition_mode: str | None = None,
        supported_horizon_days_for_virus: list[int] | None = None,
    ) -> dict[str, Any]:
        return regional_forecast_views.empty_forecast_response(
            self,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            status=status,
            message=message,
            artifact_transition_mode=artifact_transition_mode,
            supported_horizon_days_for_virus=supported_horizon_days_for_virus,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            supported_forecast_horizons=SUPPORTED_FORECAST_HORIZONS,
            utc_now_fn=utc_now,
        )

    def _empty_media_allocation_response(
        self,
        *,
        virus_typ: str,
        weekly_budget_eur: float,
        horizon_days: int,
        status: str,
        message: str,
        quality_gate: dict[str, Any],
        business_gate: dict[str, Any],
        rollout_mode: str,
        activation_policy: str,
    ) -> dict[str, Any]:
        return regional_forecast_views.empty_media_allocation_response(
            self,
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
            status=status,
            message=message,
            quality_gate=quality_gate,
            business_gate=business_gate,
            rollout_mode=rollout_mode,
            activation_policy=activation_policy,
            portfolio_products=DEFAULT_PORTFOLIO_PRODUCTS,
            supported_forecast_horizons=SUPPORTED_FORECAST_HORIZONS,
            utc_now_fn=utc_now,
        )

    def benchmark_supported_viruses(
        self,
        *,
        reference_virus: str = "Influenza A",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return regional_forecast_views.benchmark_supported_viruses(
            self,
            reference_virus=reference_virus,
            horizon_days=horizon_days,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            supported_virus_types=SUPPORTED_VIRUS_TYPES,
            regional_horizon_support_status_fn=regional_horizon_support_status,
            artifact_source_coverage_scope=ARTIFACT_SOURCE_COVERAGE_SCOPE,
            rollout_mode_for_virus_fn=rollout_mode_for_virus,
            activation_policy_for_virus_fn=activation_policy_for_virus,
            signal_bundle_version_for_virus_fn=signal_bundle_version_for_virus,
            utc_now_fn=utc_now,
        )

    def build_hero_overview(
        self,
        *,
        horizon_days: int = 7,
        reference_virus: str = "Influenza A",
    ) -> dict[str, Any]:
        return regional_forecast_views.build_hero_overview(
            self,
            horizon_days=horizon_days,
            reference_virus=reference_virus,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            supported_virus_types=SUPPORTED_VIRUS_TYPES,
            portfolio_products=DEFAULT_PORTFOLIO_PRODUCTS,
            utc_now_fn=utc_now,
        )

    def build_portfolio_view(
        self,
        *,
        horizon_days: int = 7,
        top_n: int = 12,
        reference_virus: str = "Influenza A",
    ) -> dict[str, Any]:
        return regional_forecast_views.build_portfolio_view(
            self,
            horizon_days=horizon_days,
            top_n=top_n,
            reference_virus=reference_virus,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            supported_virus_types=SUPPORTED_VIRUS_TYPES,
            portfolio_products=DEFAULT_PORTFOLIO_PRODUCTS,
            media_channels=MEDIA_CHANNELS,
            utc_now_fn=utc_now,
        )

    def get_validation_summary(
        self,
        *,
        virus_typ: str = "Influenza A",
        brand: str = "gelo",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return regional_forecast_views.get_validation_summary(
            self,
            virus_typ=virus_typ,
            brand=brand,
            horizon_days=horizon_days,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            regional_horizon_support_status_fn=regional_horizon_support_status,
            artifact_source_coverage_scope=ARTIFACT_SOURCE_COVERAGE_SCOPE,
            signal_bundle_version_for_virus_fn=signal_bundle_version_for_virus,
            rollout_mode_for_virus_fn=rollout_mode_for_virus,
            activation_policy_for_virus_fn=activation_policy_for_virus,
            utc_now_fn=utc_now,
        )

    def _load_artifacts(self, virus_typ: str, horizon_days: int = 7) -> dict[str, Any]:
        return regional_forecast_artifacts.load_artifacts(
            self,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            ensure_supported_horizon_fn=ensure_supported_horizon,
            regional_model_artifact_dir_fn=regional_model_artifact_dir,
            supported_forecast_horizons=SUPPORTED_FORECAST_HORIZONS,
            target_window_days=TARGET_WINDOW_DAYS,
            virus_slug_fn=_virus_slug,
            training_only_panel_columns=TRAINING_ONLY_PANEL_COLUMNS,
        )

    @staticmethod
    def _required_artifact_paths(model_dir: Path) -> dict[str, Path]:
        return regional_forecast_artifacts.required_artifact_paths(model_dir)

    @classmethod
    def _missing_artifact_files(cls, model_dir: Path) -> list[str]:
        return regional_forecast_artifacts.missing_artifact_files(
            model_dir,
            required_artifact_paths_fn=cls._required_artifact_paths,
        )

    @staticmethod
    def _invalid_inference_feature_columns(feature_columns: list[str]) -> list[str]:
        return regional_forecast_artifacts.invalid_inference_feature_columns(
            feature_columns,
            training_only_panel_columns=TRAINING_ONLY_PANEL_COLUMNS,
        )

    @classmethod
    def _artifact_payload_from_dir(cls, model_dir: Path) -> dict[str, Any]:
        return regional_forecast_artifacts.artifact_payload_from_dir(
            model_dir,
            required_artifact_paths_fn=cls._required_artifact_paths,
            xgb_classifier_cls=XGBClassifier,
            xgb_regressor_cls=XGBRegressor,
            json_module=json,
            pickle_module=pickle,
        )

    @staticmethod
    def _apply_calibration(calibration: Any, raw_probabilities: np.ndarray) -> np.ndarray:
        return regional_forecast_artifacts.apply_calibration(
            calibration,
            raw_probabilities,
            np_module=np,
        )

    def _latest_as_of_date(self, virus_typ: str) -> pd.Timestamp:
        return self.feature_builder.latest_available_as_of_date(virus_typ=virus_typ)

    @staticmethod
    def _decision_stage_sort_value(stage: str | None) -> int:
        return regional_forecast_media.decision_stage_sort_value(stage)

    @classmethod
    def _decision_priority_sort_key(cls, item: dict[str, Any]) -> tuple[float, float, float, float]:
        return regional_forecast_media.decision_priority_sort_key(item)

    @classmethod
    def _decision_summary(cls, predictions: list[dict[str, Any]]) -> dict[str, Any]:
        return regional_forecast_media.decision_summary(predictions)

    @staticmethod
    def _media_spend_gate(
        *,
        quality_gate: dict[str, Any],
        business_gate: dict[str, Any],
        activation_policy: str,
    ) -> tuple[bool, list[str]]:
        return regional_forecast_media.media_spend_gate(
            quality_gate=quality_gate,
            business_gate=business_gate,
            activation_policy=activation_policy,
        )

    @staticmethod
    def _media_action(
        *,
        recommended_level: str,
        spend_enabled: bool,
    ) -> str:
        return regional_forecast_media.media_action(
            recommended_level=recommended_level,
            spend_enabled=spend_enabled,
        )

    @staticmethod
    def _media_intensity(action: str) -> str:
        return regional_forecast_media.media_intensity(action)

    @staticmethod
    def _products_from_allocation(
        *,
        allocation_item: dict[str, Any],
        virus_typ: str,
    ) -> list[str]:
        return regional_forecast_media.products_from_allocation(
            allocation_item=allocation_item,
            virus_typ=virus_typ,
            portfolio_products=DEFAULT_PORTFOLIO_PRODUCTS,
        )

    @staticmethod
    def _media_timeline(
        *,
        action: str,
        spend_enabled: bool,
        activation_policy: str,
        business_gate: dict[str, Any],
        quality_gate: dict[str, Any],
    ) -> str:
        return regional_forecast_media.media_timeline(
            action=action,
            spend_enabled=spend_enabled,
            activation_policy=activation_policy,
            business_gate=business_gate,
            quality_gate=quality_gate,
            target_window_days=TARGET_WINDOW_DAYS,
        )

    @staticmethod
    def _media_headline(
        *,
        virus_typ: str,
        recommendations: list[dict[str, Any]],
        spend_enabled: bool,
    ) -> str:
        return regional_forecast_media.media_headline(
            virus_typ=virus_typ,
            recommendations=recommendations,
            spend_enabled=spend_enabled,
        )

    @staticmethod
    def _metric_delta(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, float]:
        return regional_forecast_media.metric_delta(candidate, reference)

    @staticmethod
    def _benchmark_score(item: dict[str, Any]) -> float:
        return regional_forecast_media.benchmark_score(item)

    def _portfolio_priority_score(
        self,
        *,
        prediction: dict[str, Any],
        benchmark_item: dict[str, Any],
    ) -> float:
        return regional_forecast_media.portfolio_priority_score(
            prediction=prediction,
            benchmark_item=benchmark_item,
        )

    def _portfolio_action(
        self,
        *,
        prediction: dict[str, Any],
        benchmark_item: dict[str, Any],
    ) -> tuple[str, str]:
        return regional_forecast_media.portfolio_action(
            prediction=prediction,
            benchmark_item=benchmark_item,
        )

    @staticmethod
    def _region_rollup(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return regional_forecast_media.region_rollup(opportunities)

    def _truth_readiness(self, *, brand: str = "gelo") -> dict[str, Any]:
        return regional_forecast_truth.truth_readiness(
            self,
            brand=brand,
            forecast_decision_service_cls=ForecastDecisionService,
        )

    def _business_gate(
        self,
        *,
        quality_gate: dict[str, Any],
        truth_readiness: dict[str, Any] | None = None,
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return regional_forecast_truth.business_gate(
            self,
            quality_gate=quality_gate,
            truth_readiness=truth_readiness,
            brand=brand,
            business_validation_service_cls=BusinessValidationService,
        )

    def _truth_layer_assessment_for_products(
        self,
        *,
        region_code: str,
        products: list[str],
        target_week_start: Any,
        signal_context: dict[str, Any],
        operational_action: str,
        operational_gate_open: bool,
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return regional_forecast_truth.truth_layer_assessment_for_products(
            self,
            region_code=region_code,
            products=products,
            target_week_start=target_week_start,
            signal_context=signal_context,
            operational_action=operational_action,
            operational_gate_open=operational_gate_open,
            brand=brand,
        )

    def _truth_layer_assessment_for_product(
        self,
        *,
        brand: str,
        region_code: str,
        product: str | None,
        window_start: datetime,
        window_end: datetime,
        signal_context: dict[str, Any],
    ) -> dict[str, Any]:
        return regional_forecast_truth.truth_layer_assessment_for_product(
            self,
            brand=brand,
            region_code=region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
            signal_context=signal_context,
            truth_layer_service_cls=TruthLayerService,
            logger=logger,
        )

    @staticmethod
    def _truth_assessment_window(target_week_start: Any) -> tuple[datetime, datetime]:
        return regional_forecast_truth.truth_assessment_window(
            target_week_start,
            truth_lookback_weeks=_TRUTH_LOOKBACK_WEEKS,
            pd_module=pd,
        )

    @staticmethod
    def _truth_signal_context(
        *,
        prediction: dict[str, Any],
        confidence: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        return regional_forecast_truth.truth_signal_context(
            prediction=prediction,
            confidence=confidence,
            stage=stage,
        )

    @staticmethod
    def _fallback_truth_assessment(
        *,
        brand: str,
        region_code: str,
        product: str | None,
        window_start: datetime,
        window_end: datetime,
        signal_context: dict[str, Any],
        source_mode: str,
        message: str,
    ) -> dict[str, Any]:
        return regional_forecast_truth.fallback_truth_assessment(
            brand=brand,
            region_code=region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
            signal_context=signal_context,
            source_mode=source_mode,
            message=message,
        )

    @staticmethod
    def _commercial_truth_gate(
        *,
        truth_assessment: dict[str, Any],
        operational_action: str,
        operational_gate_open: bool,
    ) -> tuple[str, str]:
        return regional_forecast_truth.commercial_truth_gate(
            truth_assessment=truth_assessment,
            operational_action=operational_action,
            operational_gate_open=operational_gate_open,
        )

    def _truth_layer_rollup(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return regional_forecast_truth.truth_layer_rollup(
            self,
            items,
            truth_lookback_weeks=_TRUTH_LOOKBACK_WEEKS,
        )

    @staticmethod
    def _model_version(metadata: dict[str, Any]) -> str:
        return regional_forecast_views.model_version(metadata)

    @staticmethod
    def _calibration_version(metadata: dict[str, Any]) -> str:
        return regional_forecast_views.calibration_version(metadata)
