"""Calibrated regional forecast inference and media activation service."""

from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from app.core.config import get_settings
from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.campaign_recommendation_service import CampaignRecommendationService
from app.services.media.truth_layer_service import TruthLayerService
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
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
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

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"

MEDIA_CHANNELS = {
    "high": ["Banner (programmatic)", "Digi-CLP (regional)", "Meta (regional)", "LinkedIn (Fachkreise)"],
    "medium": ["Banner (programmatic)", "Meta (regional)"],
    "low": ["Meta (national awareness)"],
}

GELO_PRODUCTS = {
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
        horizon = ensure_supported_horizon(horizon_days)
        support = regional_horizon_support_status(virus_typ, horizon)
        if not support["supported"]:
            return self._empty_forecast_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="unsupported",
                message=support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
                supported_horizon_days_for_virus=support["supported_horizons"],
            )
        target_window_days = self._target_window_for_horizon(horizon)
        artifacts = self._load_artifacts(virus_typ, horizon_days=horizon)
        metadata = artifacts.get("metadata") or {}
        artifact_transition_mode = str(
            artifacts.get("artifact_transition_mode")
            or metadata.get("artifact_transition_mode")
            or ""
        ).strip() or None
        feature_columns = metadata.get("feature_columns") or []
        load_error = str(artifacts.get("load_error") or "").strip()
        if load_error:
            return self._empty_forecast_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="no_model",
                message=load_error,
                artifact_transition_mode=artifact_transition_mode,
                supported_horizon_days_for_virus=support["supported_horizons"],
            )
        if not artifacts or not feature_columns:
            message = (
                f"Kein regionales Panel-Modell für Horizon {horizon} verfügbar. "
                "Bitte horizon-spezifisches Training starten."
            )
            if artifact_transition_mode == "legacy_default_window_fallback":
                message = (
                    f"Horizon {horizon} nutzt noch Legacy-3-7-Tage-Artefakte. "
                    "Bitte horizon-spezifisches Retraining durchführen."
                )
            return self._empty_forecast_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="no_model",
                message=message,
                artifact_transition_mode=artifact_transition_mode,
                supported_horizon_days_for_virus=support["supported_horizons"],
            )

        as_of_date = self._latest_as_of_date(virus_typ=virus_typ)
        revision_policy = self.orchestrator.resolve_revision_policy(metadata=metadata)
        revision_policy_metadata = metadata.get("revision_policy_metadata") or {}
        source_revision_policy = revision_policy_metadata.get("source_policies") or {}
        try:
            panel = self.feature_builder.build_inference_panel(
                virus_typ=virus_typ,
                as_of_date=as_of_date.to_pydatetime(),
                lookback_days=180,
                horizon_days=horizon,
                include_nowcast=True,
                use_revision_adjusted=False,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
            )
        except TypeError:
            panel = self.feature_builder.build_inference_panel(
                virus_typ=virus_typ,
                as_of_date=as_of_date.to_pydatetime(),
                lookback_days=180,
                horizon_days=horizon,
                include_nowcast=True,
                use_revision_adjusted=False,
            )
        if panel.empty:
            return self._empty_forecast_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="no_data",
                message=f"Keine regionalen Features für Horizon {horizon} und den aktuellen Datenstand verfügbar.",
                artifact_transition_mode=artifact_transition_mode,
                supported_horizon_days_for_virus=support["supported_horizons"],
            )

        missing_feature_columns = sorted(
            {
                str(column)
                for column in feature_columns
                if str(column) not in panel.columns
            }
        )
        if missing_feature_columns:
            return self._empty_forecast_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="no_model",
                message=(
                    f"Artefakt-Bundle für {virus_typ}/h{horizon} referenziert Inferenz-Features, "
                    f"die im aktuellen Panel fehlen: {', '.join(missing_feature_columns)}. "
                    "Bitte horizon-spezifisches Retraining durchführen."
                ),
                artifact_transition_mode=artifact_transition_mode,
                supported_horizon_days_for_virus=support["supported_horizons"],
            )

        X = panel[feature_columns].to_numpy()
        classifier: XGBClassifier = artifacts["classifier"]
        calibration = artifacts.get("calibration")
        reg_median: XGBRegressor = artifacts["regressor_median"]
        reg_lower: XGBRegressor = artifacts["regressor_lower"]
        reg_upper: XGBRegressor = artifacts["regressor_upper"]
        quantile_regressors: dict[float, XGBRegressor] = artifacts.get("quantile_regressors") or {}
        hierarchy_models = artifacts.get("hierarchy_models") or {}

        raw_prob = classifier.predict_proba(X)[:, 1]
        calibrated_prob = self._apply_calibration(calibration, raw_prob)
        quantile_predictions: dict[float, np.ndarray] = {
            0.1: np.expm1(reg_lower.predict(X)),
            0.5: np.expm1(reg_median.predict(X)),
            0.9: np.expm1(reg_upper.predict(X)),
        }
        for quantile, model in sorted(quantile_regressors.items()):
            if quantile in quantile_predictions:
                continue
            quantile_predictions[float(quantile)] = np.expm1(model.predict(X))

        hierarchy_meta = metadata.get("hierarchy_reconciliation") or {}
        hierarchy_feature_columns = metadata.get("hierarchy_feature_columns") or feature_columns
        hierarchy_model_modes = hierarchy_meta.get("model_modes") or {}
        hierarchy_cluster_assignments = hierarchy_meta.get("cluster_assignments") or {}
        aggregate_blend_weights = hierarchy_meta.get("aggregate_blend_weights") or {}
        aggregate_blend_policy = hierarchy_meta.get("aggregate_blend_policy") or {}
        cluster_blend_resolution = GeoHierarchyHelper.resolve_blend_weight_policy(
            aggregate_blend_policy.get("cluster"),
            as_of_date=as_of_date,
            horizon_days=horizon,
            fallback=float(aggregate_blend_weights.get("cluster") or 0.0),
        )
        national_blend_resolution = GeoHierarchyHelper.resolve_blend_weight_policy(
            aggregate_blend_policy.get("national"),
            as_of_date=as_of_date,
            horizon_days=horizon,
            fallback=float(aggregate_blend_weights.get("national") or 0.0),
        )
        resolved_blend_weights = {
            "cluster": float(cluster_blend_resolution.get("weight") or 0.0),
            "national": float(national_blend_resolution.get("weight") or 0.0),
        }
        blend_weight_scope = {
            "cluster": cluster_blend_resolution.get("scope"),
            "national": national_blend_resolution.get("scope"),
        }
        blend_regime = cluster_blend_resolution.get("regime") or national_blend_resolution.get("regime")
        state_weights = {
            str(row["bundesland"]): float(row.get("state_population_millions") or 1.0)
            for _, row in panel.iterrows()
        } if "state_population_millions" in panel.columns else {}
        if hierarchy_meta.get("enabled"):
            current_clusters = GeoHierarchyHelper.build_dynamic_clusters(
                panel,
                state_col="bundesland",
                value_col="current_known_incidence",
                date_col="as_of_date",
            )
            if current_clusters:
                hierarchy_cluster_assignments = current_clusters
            cluster_quantiles = None
            national_quantiles = None
            cluster_feature_frame = GeoHierarchyHelper.aggregate_feature_frame(
                panel,
                feature_columns=hierarchy_feature_columns,
                cluster_assignments=hierarchy_cluster_assignments,
                level="cluster",
            )
            national_feature_frame = GeoHierarchyHelper.aggregate_feature_frame(
                panel,
                feature_columns=hierarchy_feature_columns,
                level="national",
            )
            derived_cluster_quantiles = {
                quantile: GeoHierarchyHelper._aggregate_states(
                    np.asarray(values, dtype=float),
                    state_order=[str(value) for value in panel["bundesland"].tolist()],
                    cluster_assignments=hierarchy_cluster_assignments,
                    cluster_order=GeoHierarchyHelper._cluster_order(
                        [str(value) for value in panel["bundesland"].tolist()],
                        hierarchy_cluster_assignments,
                    ),
                    state_weights=state_weights,
                )[0]
                for quantile, values in quantile_predictions.items()
            }
            derived_national_quantiles = {
                quantile: GeoHierarchyHelper._aggregate_states(
                    np.asarray(values, dtype=float),
                    state_order=[str(value) for value in panel["bundesland"].tolist()],
                    cluster_assignments=hierarchy_cluster_assignments,
                    cluster_order=GeoHierarchyHelper._cluster_order(
                        [str(value) for value in panel["bundesland"].tolist()],
                        hierarchy_cluster_assignments,
                    ),
                    state_weights=state_weights,
                )[1]
                for quantile, values in quantile_predictions.items()
            }
            if not cluster_feature_frame.empty:
                cluster_order = GeoHierarchyHelper._cluster_order(
                    [str(value) for value in panel["bundesland"].tolist()],
                    hierarchy_cluster_assignments,
                )
                cluster_baseline_map = {
                    str(cluster_id): {
                        "hierarchy_state_baseline_q10": float(derived_cluster_quantiles.get(0.1, np.asarray([], dtype=float))[idx]),
                        "hierarchy_state_baseline_q50": float(derived_cluster_quantiles.get(0.5, np.asarray([], dtype=float))[idx]),
                        "hierarchy_state_baseline_q90": float(derived_cluster_quantiles.get(0.9, np.asarray([], dtype=float))[idx]),
                        "hierarchy_state_baseline_width_80": float(
                            max(
                                float(derived_cluster_quantiles.get(0.9, np.asarray([], dtype=float))[idx])
                                - float(derived_cluster_quantiles.get(0.1, np.asarray([], dtype=float))[idx]),
                                0.0,
                            )
                        ),
                    }
                    for idx, cluster_id in enumerate(cluster_order)
                }
                for column in GeoHierarchyHelper.HIERARCHY_STATE_BASELINE_FEATURE_COLUMNS:
                    cluster_feature_frame[column] = [
                        float((cluster_baseline_map.get(str(group)) or {}).get(column, 0.0))
                        for group in cluster_feature_frame["hierarchy_group"].astype(str)
                    ]
            if not national_feature_frame.empty:
                national_feature_frame = national_feature_frame.copy()
                national_feature_frame["hierarchy_state_baseline_q10"] = float(np.asarray(derived_national_quantiles.get(0.1), dtype=float)[0])
                national_feature_frame["hierarchy_state_baseline_q50"] = float(np.asarray(derived_national_quantiles.get(0.5), dtype=float)[0])
                national_feature_frame["hierarchy_state_baseline_q90"] = float(np.asarray(derived_national_quantiles.get(0.9), dtype=float)[0])
                national_feature_frame["hierarchy_state_baseline_width_80"] = float(
                    max(
                        float(np.asarray(derived_national_quantiles.get(0.9), dtype=float)[0])
                        - float(np.asarray(derived_national_quantiles.get(0.1), dtype=float)[0]),
                        0.0,
                    )
                )
            cluster_model_bundle = (hierarchy_models.get("cluster") or {})
            national_model_bundle = (hierarchy_models.get("national") or {})
            if not cluster_feature_frame.empty and cluster_model_bundle:
                cluster_X = cluster_feature_frame[hierarchy_feature_columns].to_numpy(dtype=float)
                if str(hierarchy_model_modes.get("cluster") or "direct_log") == "residual_log":
                    model_cluster_quantiles = {
                        0.1: np.expm1(
                            np.log1p(cluster_feature_frame["hierarchy_state_baseline_q10"].to_numpy(dtype=float))
                            + cluster_model_bundle["lower"].predict(cluster_X)
                        ),
                        0.5: np.expm1(
                            np.log1p(cluster_feature_frame["hierarchy_state_baseline_q50"].to_numpy(dtype=float))
                            + cluster_model_bundle["median"].predict(cluster_X)
                        ),
                        0.9: np.expm1(
                            np.log1p(cluster_feature_frame["hierarchy_state_baseline_q90"].to_numpy(dtype=float))
                            + cluster_model_bundle["upper"].predict(cluster_X)
                        ),
                    }
                else:
                    model_cluster_quantiles = {
                        0.1: np.expm1(cluster_model_bundle["lower"].predict(cluster_X)),
                        0.5: np.expm1(cluster_model_bundle["median"].predict(cluster_X)),
                        0.9: np.expm1(cluster_model_bundle["upper"].predict(cluster_X)),
                    }
                cluster_quantiles = GeoHierarchyHelper.blend_quantiles(
                    model_quantiles=model_cluster_quantiles,
                    baseline_quantiles=derived_cluster_quantiles,
                    blend_weight=float(resolved_blend_weights.get("cluster") or 0.0),
                )
            if not national_feature_frame.empty and national_model_bundle:
                national_X = national_feature_frame[hierarchy_feature_columns].to_numpy(dtype=float)
                model_national_quantiles = {
                    0.1: np.asarray(np.expm1(national_model_bundle["lower"].predict(national_X)), dtype=float),
                    0.5: np.asarray(np.expm1(national_model_bundle["median"].predict(national_X)), dtype=float),
                    0.9: np.asarray(np.expm1(national_model_bundle["upper"].predict(national_X)), dtype=float),
                }
                national_quantiles = GeoHierarchyHelper.blend_quantiles(
                    model_quantiles=model_national_quantiles,
                    baseline_quantiles=derived_national_quantiles,
                    blend_weight=float(resolved_blend_weights.get("national") or 0.0),
                )
            cluster_weight = float(resolved_blend_weights.get("cluster") or 0.0)
            national_weight = float(resolved_blend_weights.get("national") or 0.0)
            if (aggregate_blend_weights or aggregate_blend_policy) and cluster_weight <= 0.0 and national_weight <= 0.0:
                reconciled_quantiles = quantile_predictions
                reconciled_meta = {
                    "reconciliation_method": "state_sum_passthrough",
                    "hierarchy_consistency_status": "coherent",
                    "cluster_order": hierarchy_meta.get("cluster_order") or [],
                    "national_quantiles": national_quantiles or {},
                    "cluster_quantiles": cluster_quantiles or {},
                }
            else:
                reconciled_quantiles, reconciled_meta = GeoHierarchyHelper.reconcile_quantiles(
                    quantile_predictions,
                    cluster_assignments=hierarchy_cluster_assignments,
                    state_order=[str(value) for value in panel["bundesland"].tolist()],
                    cluster_quantiles=cluster_quantiles,
                    national_quantiles=national_quantiles,
                    residual_history=(
                        np.asarray(hierarchy_meta.get("state_residual_history") or [], dtype=float)
                        if hierarchy_meta.get("state_residual_history")
                        else None
                    ),
                    state_weights=state_weights,
                )
            if reconciled_quantiles:
                reconciled_attribution = {
                    "state": float(reconciled_meta.get("state", 1.0)),
                    "cluster": float(reconciled_meta.get("cluster", 0.0)),
                    "national": float(reconciled_meta.get("national", 0.0)),
                }
                quantile_predictions = reconciled_quantiles
                metadata = {
                    **metadata,
                    "hierarchy_driver_attribution": reconciled_attribution,
                    "reconciliation_method": reconciled_meta.get("reconciliation_method") or metadata.get("reconciliation_method"),
                    "hierarchy_consistency_status": reconciled_meta.get("hierarchy_consistency_status") or metadata.get("hierarchy_consistency_status"),
                }
                hierarchy_meta = {
                    **hierarchy_meta,
                    "aggregate_input_strategy": (
                        "dedicated_aggregate_models"
                        if cluster_model_bundle or national_model_bundle
                        else hierarchy_meta.get("aggregate_input_strategy") or "state_only"
                    ),
                    "aggregate_blend_weights_resolved": resolved_blend_weights,
                    "aggregate_blend_weight_scope": blend_weight_scope,
                    "blend_regime": blend_regime,
                    "cluster_assignments": hierarchy_cluster_assignments,
                    "cluster_order": reconciled_meta.get("cluster_order") or hierarchy_meta.get("cluster_order") or [],
                    "national_quantiles": {
                        str(key): np.asarray(value, dtype=float).reshape(-1).tolist()
                        for key, value in (reconciled_meta.get("national_quantiles") or {}).items()
                    },
                    "cluster_quantiles": {
                        str(key): np.asarray(value, dtype=float).reshape(-1).tolist()
                        for key, value in (reconciled_meta.get("cluster_quantiles") or {}).items()
                    },
                }

        pred_next = np.maximum(np.asarray(quantile_predictions.get(0.5), dtype=float), 0.0)
        pred_low = np.maximum(np.asarray(quantile_predictions.get(0.1, pred_next), dtype=float), 0.0)
        pred_high = np.maximum(np.asarray(quantile_predictions.get(0.9, pred_next), dtype=float), 0.0)

        action_threshold = float(metadata.get("action_threshold") or 0.6)
        quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "WATCH"}
        rollout_mode, activation_policy, sars_h7_promotion = self._effective_rollout_contract(
            virus_typ=virus_typ,
            horizon_days=horizon,
            metadata=metadata,
        )
        signal_bundle_version = metadata.get("signal_bundle_version") or signal_bundle_version_for_virus(virus_typ)
        model_version = metadata.get("model_version") or self._model_version(metadata)
        calibration_version = metadata.get("calibration_version") or self._calibration_version(metadata)
        champion_model_family = str(metadata.get("model_family") or "regional_pooled_panel")
        component_model_family = str(metadata.get("component_model_family") or champion_model_family)
        ensemble_component_weights = metadata.get("ensemble_component_weights") or {champion_model_family: 1.0}
        hierarchy_driver_attribution = metadata.get("hierarchy_driver_attribution") or {"state": 1.0, "cluster": 0.0, "national": 0.0}
        reconciliation_method = str(metadata.get("reconciliation_method") or "not_reconciled")
        hierarchy_consistency_status = str(metadata.get("hierarchy_consistency_status") or "not_checked")
        aggregate_blend_weights_resolved = (
            (hierarchy_meta.get("aggregate_blend_weights_resolved") or {})
            if hierarchy_meta
            else {}
        ) or resolved_blend_weights
        aggregate_blend_weight_scope = (
            (hierarchy_meta.get("aggregate_blend_weight_scope") or {})
            if hierarchy_meta
            else {}
        ) or blend_weight_scope
        active_blend_regime = str((hierarchy_meta.get("blend_regime") if hierarchy_meta else None) or blend_regime or "")
        benchmark_evidence_reference = (
            ((metadata.get("registry_scope") or {}).get("champion") or {}).get("created_at")
            or ((metadata.get("benchmark_summary") or {}).get("primary_metric"))
        )
        benchmark_metrics = dict((metadata.get("benchmark_summary") or {}).get("metrics") or {})
        tsfm_metadata = dict(
            metadata.get("tsfm_metadata")
            or TSFMAdapter.from_settings(
                enabled=bool(self.orchestrator.settings.FORECAST_ENABLE_TSFM_CHALLENGERS),
                provider=str(self.orchestrator.settings.FORECAST_TSFM_PROVIDER),
            ).metadata()
        )
        dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
        point_in_time_snapshot = artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {}
        source_coverage = dataset_manifest.get("source_coverage") or {}
        business_gate = self._business_gate(quality_gate=quality_gate)
        cluster_forecast_quantiles = hierarchy_meta.get("cluster_quantiles") or {}
        national_forecast_quantiles = hierarchy_meta.get("national_quantiles") or {}
        predictions = []
        for idx, row in panel.reset_index(drop=True).iterrows():
            current_incidence = float(row["current_known_incidence"] or 0.0)
            expected_next = max(float(pred_next[idx]), 0.0)
            change_pct = ((expected_next - current_incidence) / max(current_incidence, 1.0)) * 100.0
            event_probability = float(calibrated_prob[idx])
            target_date = pd.Timestamp(
                row.get("target_date") or (pd.Timestamp(row["as_of_date"]) + pd.Timedelta(days=horizon))
            ).normalize()
            activation_candidate = bool(
                activation_policy != "watch_only"
                and quality_gate.get("overall_passed")
                and event_probability >= action_threshold
            )
            prediction = {
                "bundesland": str(row["bundesland"]),
                "bundesland_name": str(row["bundesland_name"]),
                "virus_typ": virus_typ,
                "as_of_date": str(row["as_of_date"]),
                "target_date": str(target_date),
                "target_week_start": str(row["target_week_start"]),
                "target_window_days": list(target_window_days),
                "horizon_days": horizon,
                "event_definition_version": metadata.get("event_definition_version", EVENT_DEFINITION_VERSION),
                "event_probability_calibrated": round(event_probability, 4),
                "expected_next_week_incidence": round(expected_next, 2),
                "expected_target_incidence": round(expected_next, 2),
                "prediction_interval": {
                    "lower": round(max(float(pred_low[idx]), 0.0), 2),
                    "upper": round(max(float(pred_high[idx]), 0.0), 2),
                },
                "current_known_incidence": round(current_incidence, 2),
                "seasonal_baseline": round(float(row["seasonal_baseline"] or 0.0), 2),
                "seasonal_mad": round(float(row["seasonal_mad"] or 0.0), 2),
                "change_pct": round(change_pct, 1),
                "quality_gate": quality_gate,
                "business_gate": business_gate,
                "evidence_tier": business_gate.get("evidence_tier"),
                "rollout_mode": rollout_mode,
                "activation_policy": activation_policy,
                "signal_bundle_version": signal_bundle_version,
                "champion_model_family": champion_model_family,
                "component_model_family": component_model_family,
                "ensemble_component_weights": ensemble_component_weights,
                "hierarchy_driver_attribution": hierarchy_driver_attribution,
                "cluster_id": hierarchy_cluster_assignments.get(str(row["bundesland"])),
                "reconciliation_method": reconciliation_method,
                "hierarchy_consistency_status": hierarchy_consistency_status,
                "aggregate_blend_weights_resolved": aggregate_blend_weights_resolved,
                "aggregate_blend_weight_scope": aggregate_blend_weight_scope,
                "blend_regime": active_blend_regime,
                "revision_policy_used": revision_policy,
                "benchmark_evidence_reference": benchmark_evidence_reference,
                "benchmark_metrics": benchmark_metrics,
                "tsfm_metadata": tsfm_metadata,
                "model_version": model_version,
                "calibration_version": calibration_version,
                "point_in_time_snapshot": point_in_time_snapshot,
                "source_coverage": source_coverage,
                "action_threshold": round(action_threshold, 4),
                "activation_candidate": activation_candidate,
                "current_load": round(current_incidence, 2),
                "predicted_load": round(expected_next, 2),
                "trend": "steigend" if change_pct > 10 else "fallend" if change_pct < -10 else "stabil",
                "data_points": int(len(panel)),
                "last_data_date": str(as_of_date),
                "pollen_context_score": round(float(row.get("pollen_context_score") or 0.0), 2),
                "state_population_millions": round(float(row.get("state_population_millions") or 0.0), 3),
            }
            decision = self.decision_engine.evaluate(
                virus_typ=virus_typ,
                prediction=prediction,
                feature_row=row.to_dict(),
                metadata={"aggregate_metrics": metadata.get("aggregate_metrics") or {}},
            ).to_dict()
            prediction["decision"] = decision
            prediction["decision_label"] = str(decision.get("stage") or "watch").title()
            prediction["priority_score"] = float(decision.get("decision_score") or 0.0)
            prediction["reason_trace"] = decision.get("reason_trace") or {}
            prediction["uncertainty_summary"] = str(decision.get("uncertainty_summary") or "")
            prediction["decision_rank"] = None
            predictions.append(prediction)

        predictions.sort(key=lambda item: item["event_probability_calibrated"], reverse=True)
        for rank, item in enumerate(predictions, start=1):
            item["rank"] = rank

        ranked_decisions = sorted(
            predictions,
            key=self._decision_priority_sort_key,
            reverse=True,
        )
        for decision_rank, item in enumerate(ranked_decisions, start=1):
            item["decision_rank"] = decision_rank

        return {
            "virus_typ": virus_typ,
            "as_of_date": str(as_of_date),
            "horizon_days": horizon,
            "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
            "supported_horizon_days_for_virus": support["supported_horizons"],
            "target_window_days": list(target_window_days),
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "evidence_tier": business_gate.get("evidence_tier"),
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "signal_bundle_version": signal_bundle_version,
            "champion_model_family": champion_model_family,
            "component_model_family": component_model_family,
            "ensemble_component_weights": ensemble_component_weights,
            "hierarchy_driver_attribution": hierarchy_driver_attribution,
            "hierarchy_cluster_assignments": hierarchy_cluster_assignments,
            "hierarchy_cluster_forecast_quantiles": cluster_forecast_quantiles,
            "national_forecast_quantiles": national_forecast_quantiles,
            "reconciliation_method": reconciliation_method,
            "hierarchy_consistency_status": hierarchy_consistency_status,
            "aggregate_blend_weights_resolved": aggregate_blend_weights_resolved,
            "aggregate_blend_weight_scope": aggregate_blend_weight_scope,
            "blend_regime": active_blend_regime,
            "revision_policy_used": revision_policy,
            "benchmark_evidence_reference": benchmark_evidence_reference,
            "benchmark_metrics": benchmark_metrics,
            "tsfm_metadata": tsfm_metadata,
            "model_version": model_version,
            "calibration_version": calibration_version,
            "artifact_transition_mode": artifact_transition_mode,
            "point_in_time_snapshot": point_in_time_snapshot,
            "source_coverage": source_coverage,
            "action_threshold": round(action_threshold, 4),
            "decision_policy_version": self.decision_engine.get_config(virus_typ).version,
            "decision_summary": self._decision_summary(predictions),
            "total_regions": len(predictions),
            "predictions": predictions,
            "top_5": predictions[:5],
            "top_decisions": ranked_decisions[:5],
            "sars_h7_promotion": sars_h7_promotion,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_media_allocation(
        self,
        virus_typ: str = "Influenza A",
        weekly_budget_eur: float = 50000,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        forecast = self.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)
        predictions = forecast.get("predictions") or []
        quality_gate = forecast.get("quality_gate") or {"overall_passed": False}
        business_gate = forecast.get("business_gate") or self._business_gate(quality_gate=quality_gate)
        threshold = float(forecast.get("action_threshold") or 0.6)
        rollout_mode = str(forecast.get("rollout_mode") or rollout_mode_for_virus(virus_typ))
        activation_policy = str(forecast.get("activation_policy") or activation_policy_for_virus(virus_typ))

        if not predictions:
            return self._empty_media_allocation_response(
                virus_typ=virus_typ,
                weekly_budget_eur=weekly_budget_eur,
                horizon_days=horizon_days,
                status=str(forecast.get("status") or "no_data"),
                message=str(
                    forecast.get("message")
                    or "Keine regionalen Forecast-/Decision-Daten verfügbar."
                ),
                quality_gate=quality_gate,
                business_gate=business_gate,
                rollout_mode=rollout_mode,
                activation_policy=activation_policy,
            )

        spend_enabled, spend_blockers = self._media_spend_gate(
            quality_gate=quality_gate,
            business_gate=business_gate,
            activation_policy=activation_policy,
        )
        allocation = self.media_allocation_engine.allocate(
            virus_typ=virus_typ,
            predictions=predictions,
            total_budget_eur=weekly_budget_eur,
            spend_enabled=spend_enabled,
            spend_blockers=spend_blockers,
            default_products=GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
        )
        allocation_by_region = {
            item["bundesland"]: item
            for item in allocation.get("recommendations") or []
        }

        recommendations = []
        for item in predictions:
            allocation_item = allocation_by_region.get(item["bundesland"], {})
            recommended_level = str(
                allocation_item.get("recommended_activation_level")
                or item.get("decision_label")
                or "Watch"
            )
            action = self._media_action(
                recommended_level=recommended_level,
                spend_enabled=spend_enabled,
            )
            intensity = self._media_intensity(action)
            budget_share = round(float(allocation_item.get("suggested_budget_share") or 0.0), 6)
            budget_eur = round(float(allocation_item.get("suggested_budget_eur") or 0.0), 2)
            suggested_budget_amount = round(
                float(allocation_item.get("suggested_budget_amount") or budget_eur),
                2,
            )
            allocation_reason_trace = (
                allocation_item.get("allocation_reason_trace")
                or allocation_item.get("reason_trace")
                or item.get("reason_trace")
            )
            products = self._products_from_allocation(
                allocation_item=allocation_item,
                virus_typ=virus_typ,
            )
            truth_overlay = self._truth_layer_assessment_for_products(
                region_code=item["bundesland"],
                products=products,
                target_week_start=item["target_week_start"],
                signal_context=self._truth_signal_context(
                    prediction=item,
                    confidence=allocation_item.get("confidence"),
                    stage=recommended_level,
                ),
                operational_action=action,
                operational_gate_open=spend_enabled,
            )

            recommendations.append(
                {
                    "bundesland": item["bundesland"],
                    "bundesland_name": item["bundesland_name"],
                    "rank": item["rank"],
                    "decision_rank": item.get("decision_rank"),
                    "priority_rank": allocation_item.get("priority_rank"),
                    "action": action,
                    "intensity": intensity,
                    "recommended_activation_level": recommended_level,
                    "spend_readiness": allocation_item.get("spend_readiness"),
                    "event_probability": item["event_probability_calibrated"],
                    "decision_label": item.get("decision_label"),
                    "priority_score": item.get("priority_score"),
                    "allocation_score": allocation_item.get("allocation_score"),
                    "confidence": allocation_item.get("confidence"),
                    "reason_trace": allocation_reason_trace,
                    "allocation_reason_trace": allocation_reason_trace,
                    "uncertainty_summary": item.get("uncertainty_summary"),
                    "decision": item.get("decision"),
                    "change_pct": item["change_pct"],
                    "trend": item["trend"],
                    "budget_share": budget_share,
                    "suggested_budget_share": budget_share,
                    "budget_eur": budget_eur,
                    "suggested_budget_eur": budget_eur,
                    "suggested_budget_amount": suggested_budget_amount,
                    "channels": MEDIA_CHANNELS[intensity],
                    "products": products,
                    "product_clusters": allocation_item.get("product_clusters") or [],
                    "keyword_clusters": allocation_item.get("keyword_clusters") or [],
                    "timeline": self._media_timeline(
                        action=action,
                        spend_enabled=spend_enabled,
                        activation_policy=activation_policy,
                        business_gate=business_gate,
                        quality_gate=quality_gate,
                    ),
                    "current_load": item["current_known_incidence"],
                    "predicted_load": item["expected_next_week_incidence"],
                    "quality_gate": quality_gate,
                    "business_gate": business_gate,
                    "evidence_tier": business_gate.get("evidence_tier"),
                    "rollout_mode": rollout_mode,
                    "activation_policy": activation_policy,
                    "activation_threshold": threshold,
                    "allocation_policy_version": allocation.get("allocation_policy_version"),
                    "as_of_date": item["as_of_date"],
                    "target_week_start": item["target_week_start"],
                    "truth_layer_enabled": truth_overlay["truth_layer_enabled"],
                    "truth_scope": truth_overlay["truth_scope"],
                    "outcome_readiness": truth_overlay["outcome_readiness"],
                    "evidence_status": truth_overlay["evidence_status"],
                    "evidence_confidence": truth_overlay["evidence_confidence"],
                    "signal_outcome_agreement": truth_overlay["signal_outcome_agreement"],
                    "spend_gate_status": truth_overlay["spend_gate_status"],
                    "budget_release_recommendation": truth_overlay["budget_release_recommendation"],
                    "commercial_gate": truth_overlay["commercial_gate"],
                    "truth_assessments": truth_overlay["truth_assessments"],
                }
            )

        recommendations.sort(
            key=lambda item: (
                float(item.get("priority_rank") or 0),
                -float(item.get("suggested_budget_share") or 0.0),
            ),
        )
        recommendations = list(recommendations)

        summary = {
            "activate_regions": sum(1 for item in recommendations if item["action"] == "activate"),
            "prepare_regions": sum(1 for item in recommendations if item["action"] == "prepare"),
            "watch_regions": sum(1 for item in recommendations if item["action"] == "watch"),
            "total_budget_allocated": round(sum(item["budget_eur"] for item in recommendations), 2),
            "budget_share_total": round(sum(item["suggested_budget_share"] for item in recommendations), 6),
            "weekly_budget": round(float(weekly_budget_eur), 2),
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "evidence_tier": business_gate.get("evidence_tier"),
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "allocation_policy_version": allocation.get("allocation_policy_version"),
            "spend_enabled": spend_enabled,
            "spend_blockers": spend_blockers,
        }
        truth_layer = self._truth_layer_rollup(recommendations)

        return {
            "virus_typ": virus_typ,
            "headline": self._media_headline(
                virus_typ=virus_typ,
                recommendations=recommendations,
                spend_enabled=spend_enabled,
            ),
            "summary": summary,
            "allocation_config": allocation.get("config") or {},
            "horizon_days": horizon_days,
            "truth_layer": truth_layer,
            "generated_at": datetime.utcnow().isoformat(),
            "recommendations": recommendations,
        }

    def generate_media_activation(
        self,
        virus_typ: str = "Influenza A",
        weekly_budget_eur: float = 50000,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return self.generate_media_allocation(
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
        allocation_payload = self.generate_media_allocation(
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
        )
        recommendation_payload = self.campaign_recommendation_service.recommend_from_allocation(
            allocation_payload=allocation_payload,
            top_n=top_n,
        )
        recommendation_payload.setdefault("horizon_days", horizon_days)
        recommendation_payload.setdefault(
            "target_window_days",
            allocation_payload.get("target_window_days") or self._target_window_for_horizon(horizon_days),
        )
        return recommendation_payload

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
        horizon = ensure_supported_horizon(horizon_days)
        return {
            "virus_typ": virus_typ,
            "status": status,
            "message": message,
            "horizon_days": horizon,
            "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
            "supported_horizon_days_for_virus": list(
                supported_horizon_days_for_virus or SUPPORTED_FORECAST_HORIZONS
            ),
            "target_window_days": self._target_window_for_horizon(horizon),
            "artifact_transition_mode": artifact_transition_mode,
            "predictions": [],
            "top_5": [],
            "top_decisions": [],
            "decision_summary": self._decision_summary([]),
            "total_regions": 0,
            "generated_at": datetime.utcnow().isoformat(),
        }

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
        allocation = self.media_allocation_engine.allocate(
            virus_typ=virus_typ,
            predictions=[],
            total_budget_eur=weekly_budget_eur,
            spend_enabled=False,
            spend_blockers=[],
            default_products=GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
        )
        summary = dict(allocation.get("summary") or {})
        summary.update(
            {
                "quality_gate": quality_gate,
                "business_gate": business_gate,
                "evidence_tier": business_gate.get("evidence_tier"),
                "rollout_mode": rollout_mode,
                "activation_policy": activation_policy,
                "allocation_policy_version": allocation.get("allocation_policy_version"),
            }
        )
        return {
            "virus_typ": virus_typ,
            "status": status,
            "message": message,
            "headline": allocation.get("headline") or f"{virus_typ}: keine regionalen Allocation-Empfehlungen verfügbar",
            "summary": summary,
            "allocation_config": allocation.get("config") or {},
            "horizon_days": horizon_days,
            "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
            "target_window_days": self._target_window_for_horizon(horizon_days),
            "truth_layer": self._truth_layer_rollup([]),
            "generated_at": datetime.utcnow().isoformat(),
            "recommendations": [],
        }

    def benchmark_supported_viruses(
        self,
        *,
        reference_virus: str = "Influenza A",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        items: list[dict[str, Any]] = []
        reference_metrics: dict[str, Any] | None = None
        truth_readiness = self._truth_readiness()

        for virus_typ in SUPPORTED_VIRUS_TYPES:
            support = regional_horizon_support_status(virus_typ, horizon)
            if not support["supported"]:
                unsupported_business_gate = self._business_gate(
                    quality_gate={"overall_passed": False},
                    truth_readiness=truth_readiness,
                )
                items.append(
                    {
                        "virus_typ": virus_typ,
                        "horizon_days": horizon,
                        "target_window_days": self._target_window_for_horizon(horizon),
                        "status": "unsupported",
                        "message": support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
                        "trained_at": None,
                        "states": 0,
                        "rows": 0,
                        "truth_source": None,
                        "source_coverage": {},
                        "point_in_time_snapshot": {},
                        "aggregate_metrics": {},
                        "quality_gate": {"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
                        "business_gate": unsupported_business_gate,
                        "evidence_tier": unsupported_business_gate.get("evidence_tier"),
                        "rollout_mode": rollout_mode_for_virus(virus_typ),
                        "activation_policy": activation_policy_for_virus(virus_typ),
                        "signal_bundle_version": signal_bundle_version_for_virus(virus_typ),
                        "model_version": None,
                        "calibration_version": None,
                    }
                )
                continue
            artifacts = self._load_artifacts(virus_typ, horizon_days=horizon)
            metadata = artifacts.get("metadata") or {}
            load_error = str(artifacts.get("load_error") or "").strip()
            aggregate_metrics = metadata.get("aggregate_metrics") or {}
            quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
            dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
            business_gate = self._business_gate(
                quality_gate=quality_gate,
                truth_readiness=truth_readiness,
            )

            item = {
                "virus_typ": virus_typ,
                "horizon_days": int(metadata.get("horizon_days") or horizon),
                "target_window_days": metadata.get("target_window_days") or self._target_window_for_horizon(horizon),
                "status": "trained" if aggregate_metrics and not load_error else "no_model",
                "message": load_error or metadata.get("message"),
                "trained_at": metadata.get("trained_at"),
                "states": int(dataset_manifest.get("states") or 0),
                "rows": int(dataset_manifest.get("rows") or 0),
                "truth_source": dataset_manifest.get("truth_source"),
                "source_coverage": dataset_manifest.get("source_coverage") or {},
                "point_in_time_snapshot": artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {},
                "aggregate_metrics": aggregate_metrics,
                "quality_gate": quality_gate,
                "business_gate": business_gate,
                "evidence_tier": business_gate.get("evidence_tier"),
                "rollout_mode": metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ),
                "activation_policy": metadata.get("activation_policy") or activation_policy_for_virus(virus_typ),
                "signal_bundle_version": metadata.get("signal_bundle_version") or signal_bundle_version_for_virus(virus_typ),
                "model_version": metadata.get("model_version") or self._model_version(metadata),
                "calibration_version": metadata.get("calibration_version") or self._calibration_version(metadata),
                "selection": metadata.get("label_selection") or {},
                "shadow_evaluation": metadata.get("shadow_evaluation") or {},
            }
            if virus_typ == reference_virus and aggregate_metrics:
                reference_metrics = aggregate_metrics
            items.append(item)

        for item in items:
            item["delta_vs_reference"] = self._metric_delta(
                item.get("aggregate_metrics") or {},
                reference_metrics or {},
            )
            item["benchmark_score"] = self._benchmark_score(item)

        ranked = sorted(
            items,
            key=lambda item: (
                item.get("status") == "trained",
                bool((item.get("quality_gate") or {}).get("overall_passed")),
                float((item.get("aggregate_metrics") or {}).get("precision_at_top3") or 0.0),
                float((item.get("aggregate_metrics") or {}).get("pr_auc") or 0.0),
                -float((item.get("aggregate_metrics") or {}).get("ece") or 1.0),
                -float((item.get("aggregate_metrics") or {}).get("activation_false_positive_rate") or 1.0),
            ),
            reverse=True,
        )
        for rank, item in enumerate(ranked, start=1):
            item["rank"] = rank

        summary_business_gate = self._business_gate(
            quality_gate={"overall_passed": any((item.get("quality_gate") or {}).get("overall_passed") for item in ranked)},
            truth_readiness=truth_readiness,
        )
        return {
            "reference_virus": reference_virus,
            "horizon_days": horizon,
            "target_window_days": self._target_window_for_horizon(horizon),
            "generated_at": datetime.utcnow().isoformat(),
            "trained_viruses": sum(1 for item in ranked if item["status"] == "trained"),
            "go_viruses": sum(
                1
                for item in ranked
                if (item.get("quality_gate") or {}).get("overall_passed")
                and item.get("activation_policy") != "watch_only"
            ),
            "business_gate": summary_business_gate,
            "evidence_tier": summary_business_gate.get("evidence_tier"),
            "benchmark": ranked,
        }

    def build_portfolio_view(
        self,
        *,
        horizon_days: int = 7,
        top_n: int = 12,
        reference_virus: str = "Influenza A",
    ) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        benchmark_payload = self.benchmark_supported_viruses(
            reference_virus=reference_virus,
            horizon_days=horizon,
        )
        benchmark_map = {
            item["virus_typ"]: item
            for item in benchmark_payload.get("benchmark", [])
            if item.get("status") == "trained"
        }

        opportunities: list[dict[str, Any]] = []
        virus_rollup: list[dict[str, Any]] = []
        latest_as_of_date: str | None = None

        for virus_typ in SUPPORTED_VIRUS_TYPES:
            benchmark_item = benchmark_map.get(virus_typ)
            if not benchmark_item:
                continue

            forecast = self.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon)
            predictions = forecast.get("predictions") or []
            if not predictions:
                continue

            top_prediction = predictions[0]
            latest_as_of_date = str(max(filter(None, [latest_as_of_date, forecast.get("as_of_date")])))
            virus_rollup.append(
                {
                    "virus_typ": virus_typ,
                    "rank": benchmark_item.get("rank"),
                    "benchmark_score": benchmark_item.get("benchmark_score"),
                    "quality_gate": benchmark_item.get("quality_gate"),
                    "business_gate": benchmark_item.get("business_gate"),
                    "evidence_tier": benchmark_item.get("evidence_tier"),
                    "rollout_mode": benchmark_item.get("rollout_mode"),
                    "activation_policy": benchmark_item.get("activation_policy"),
                    "aggregate_metrics": benchmark_item.get("aggregate_metrics"),
                    "top_region": top_prediction.get("bundesland"),
                    "top_region_name": top_prediction.get("bundesland_name"),
                    "top_event_probability": top_prediction.get("event_probability_calibrated"),
                    "top_change_pct": top_prediction.get("change_pct"),
                    "products": GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
                }
            )

            for prediction in predictions:
                action, intensity = self._portfolio_action(
                    prediction=prediction,
                    benchmark_item=benchmark_item,
                )
                truth_overlay = self._truth_layer_assessment_for_products(
                    region_code=prediction["bundesland"],
                    products=GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
                    target_week_start=prediction["target_week_start"],
                    signal_context=self._truth_signal_context(prediction=prediction),
                    operational_action=action,
                    operational_gate_open=action in {"activate", "prepare"},
                )
                opportunity = {
                    "virus_typ": virus_typ,
                    "bundesland": prediction["bundesland"],
                    "bundesland_name": prediction["bundesland_name"],
                    "rank_within_virus": prediction["rank"],
                    "portfolio_action": action,
                    "portfolio_intensity": intensity,
                    "portfolio_priority_score": self._portfolio_priority_score(
                        prediction=prediction,
                        benchmark_item=benchmark_item,
                    ),
                    "event_probability_calibrated": prediction["event_probability_calibrated"],
                    "expected_next_week_incidence": prediction["expected_next_week_incidence"],
                    "prediction_interval": prediction["prediction_interval"],
                    "current_known_incidence": prediction["current_known_incidence"],
                    "change_pct": prediction["change_pct"],
                    "trend": prediction["trend"],
                    "quality_gate": prediction["quality_gate"],
                    "business_gate": prediction.get("business_gate") or benchmark_item.get("business_gate"),
                    "evidence_tier": (prediction.get("business_gate") or benchmark_item.get("business_gate") or {}).get("evidence_tier"),
                    "rollout_mode": prediction.get("rollout_mode"),
                    "activation_policy": prediction.get("activation_policy"),
                    "signal_bundle_version": prediction.get("signal_bundle_version"),
                    "model_version": prediction.get("model_version") or benchmark_item.get("model_version"),
                    "calibration_version": prediction.get("calibration_version") or benchmark_item.get("calibration_version"),
                    "benchmark_rank": benchmark_item.get("rank"),
                    "benchmark_score": benchmark_item.get("benchmark_score"),
                    "aggregate_metrics": benchmark_item.get("aggregate_metrics"),
                    "products": GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
                    "channels": MEDIA_CHANNELS[intensity],
                    "as_of_date": prediction["as_of_date"],
                    "target_week_start": prediction["target_week_start"],
                    "truth_layer_enabled": truth_overlay["truth_layer_enabled"],
                    "truth_scope": truth_overlay["truth_scope"],
                    "outcome_readiness": truth_overlay["outcome_readiness"],
                    "evidence_status": truth_overlay["evidence_status"],
                    "evidence_confidence": truth_overlay["evidence_confidence"],
                    "signal_outcome_agreement": truth_overlay["signal_outcome_agreement"],
                    "spend_gate_status": truth_overlay["spend_gate_status"],
                    "budget_release_recommendation": truth_overlay["budget_release_recommendation"],
                    "commercial_gate": truth_overlay["commercial_gate"],
                    "truth_assessments": truth_overlay["truth_assessments"],
                }
                opportunities.append(opportunity)

        opportunities.sort(
            key=lambda item: (
                float(item.get("portfolio_priority_score") or 0.0),
                float(item.get("event_probability_calibrated") or 0.0),
                float(item.get("change_pct") or 0.0),
            ),
            reverse=True,
        )
        for rank, item in enumerate(opportunities, start=1):
            item["rank"] = rank

        region_rollup = self._region_rollup(opportunities)
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "reference_virus": reference_virus,
            "horizon_days": horizon,
            "target_window_days": self._target_window_for_horizon(horizon),
            "latest_as_of_date": latest_as_of_date,
            "summary": {
                "trained_viruses": benchmark_payload.get("trained_viruses", 0),
                "go_viruses": benchmark_payload.get("go_viruses", 0),
                "total_opportunities": len(opportunities),
                "watchlist_opportunities": sum(1 for item in opportunities if item["portfolio_action"] == "watch"),
                "priority_opportunities": sum(1 for item in opportunities if item["portfolio_action"] == "prioritize"),
                "validated_opportunities": sum(1 for item in opportunities if item["portfolio_action"] in {"activate", "prepare"}),
            },
            "business_gate": benchmark_payload.get("business_gate") or self._business_gate(quality_gate={"overall_passed": False}),
            "evidence_tier": benchmark_payload.get("evidence_tier"),
            "truth_layer": self._truth_layer_rollup(opportunities),
            "benchmark": benchmark_payload.get("benchmark", []),
            "virus_rollup": virus_rollup,
            "region_rollup": region_rollup,
            "top_opportunities": opportunities[: max(int(top_n), 1)],
        }

    def get_validation_summary(
        self,
        *,
        virus_typ: str = "Influenza A",
        brand: str = "gelo",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        support = regional_horizon_support_status(virus_typ, horizon)
        if not support["supported"]:
            business_gate = self._business_gate(
                quality_gate={"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
                brand=brand,
            )
            return {
                "virus_typ": virus_typ,
                "brand": str(brand or "gelo").strip().lower(),
                "horizon_days": horizon,
                "target_window_days": self._target_window_for_horizon(horizon),
                "status": "unsupported",
                "message": support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
                "generated_at": datetime.utcnow().isoformat(),
                "quality_gate": {"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
                "business_gate": business_gate,
                "operator_context": business_gate.get("operator_context"),
                "evidence_tier": business_gate.get("evidence_tier"),
                "model_version": None,
                "calibration_version": None,
                "point_in_time_snapshot": {},
                "source_coverage": {},
                "signal_bundle_version": signal_bundle_version_for_virus(virus_typ),
                "rollout_mode": rollout_mode_for_virus(virus_typ),
                "activation_policy": activation_policy_for_virus(virus_typ),
                "aggregate_metrics": {},
            }
        artifacts = self._load_artifacts(virus_typ, horizon_days=horizon)
        metadata = artifacts.get("metadata") or {}
        load_error = str(artifacts.get("load_error") or "").strip()
        quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
        business_gate = self._business_gate(
            quality_gate=quality_gate,
            brand=brand,
        )
        dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
        return {
            "virus_typ": virus_typ,
            "brand": str(brand or "gelo").strip().lower(),
            "horizon_days": int(metadata.get("horizon_days") or horizon),
            "target_window_days": metadata.get("target_window_days") or self._target_window_for_horizon(horizon),
            "status": "trained" if not load_error and metadata.get("aggregate_metrics") else "no_model",
            "message": load_error or metadata.get("message"),
            "generated_at": datetime.utcnow().isoformat(),
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "operator_context": business_gate.get("operator_context"),
            "evidence_tier": business_gate.get("evidence_tier"),
            "model_version": metadata.get("model_version") or self._model_version(metadata),
            "calibration_version": metadata.get("calibration_version") or self._calibration_version(metadata),
            "point_in_time_snapshot": artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {},
            "source_coverage": dataset_manifest.get("source_coverage") or {},
            "signal_bundle_version": metadata.get("signal_bundle_version") or signal_bundle_version_for_virus(virus_typ),
            "rollout_mode": metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ),
            "activation_policy": metadata.get("activation_policy") or activation_policy_for_virus(virus_typ),
            "aggregate_metrics": metadata.get("aggregate_metrics") or {},
        }

    def _load_artifacts(self, virus_typ: str, horizon_days: int = 7) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        model_dir = regional_model_artifact_dir(
            self.models_dir,
            virus_typ=virus_typ,
            horizon_days=horizon,
        )
        if model_dir.exists():
            missing_files = self._missing_artifact_files(model_dir)
            if missing_files:
                return {
                    "load_error": (
                        f"Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig: "
                        f"{', '.join(missing_files)}"
                    ),
                }
        payload = self._artifact_payload_from_dir(model_dir)
        if payload:
            metadata = dict(payload.get("metadata") or {})
            metadata_horizon = metadata.get("horizon_days")
            if metadata_horizon is None:
                payload["load_error"] = (
                    f"Metadaten für {virus_typ}/h{horizon} fehlen das Pflichtfeld 'horizon_days'."
                )
                return payload
            if int(metadata_horizon) != horizon:
                payload["load_error"] = (
                    f"Metadaten-Horizon {metadata_horizon} passt nicht zur Anfrage h{horizon}."
                )
                return payload
            metadata.setdefault("target_window_days", self._target_window_for_horizon(horizon))
            metadata.setdefault("supported_horizon_days", list(SUPPORTED_FORECAST_HORIZONS))
            invalid_feature_columns = self._invalid_inference_feature_columns(
                metadata.get("feature_columns") or []
            )
            if invalid_feature_columns:
                payload["load_error"] = (
                    f"Artefakt-Bundle für {virus_typ}/h{horizon} enthält trainingsinterne "
                    f"Feature-Spalten: {', '.join(invalid_feature_columns)}. "
                    "Bitte horizon-spezifisches Retraining durchführen."
                )
                return payload
            payload["metadata"] = metadata
            return payload

        if horizon != 7:
            return {}

        legacy_dir = self.models_dir / _virus_slug(virus_typ)
        if legacy_dir.exists():
            missing_files = self._missing_artifact_files(legacy_dir)
            if missing_files:
                return {
                    "load_error": (
                        f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig: "
                        f"{', '.join(missing_files)}"
                    ),
                }
        legacy_payload = self._artifact_payload_from_dir(legacy_dir)
        if not legacy_payload:
            return {}

        metadata = dict(legacy_payload.get("metadata") or {})
        metadata["horizon_days"] = horizon
        metadata["target_window_days"] = metadata.get("target_window_days") or list(TARGET_WINDOW_DAYS)
        metadata["requested_horizon_days"] = horizon
        metadata["supported_horizon_days"] = list(SUPPORTED_FORECAST_HORIZONS)
        metadata["artifact_transition_mode"] = "legacy_default_window_fallback"
        legacy_payload["metadata"] = metadata
        legacy_payload["artifact_transition_mode"] = "legacy_default_window_fallback"
        invalid_feature_columns = self._invalid_inference_feature_columns(
            metadata.get("feature_columns") or []
        )
        if invalid_feature_columns:
            legacy_payload["load_error"] = (
                f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} enthält trainingsinterne "
                f"Feature-Spalten: {', '.join(invalid_feature_columns)}. "
                "Bitte horizon-spezifisches Retraining durchführen."
            )
        return legacy_payload

    @staticmethod
    def _required_artifact_paths(model_dir: Path) -> dict[str, Path]:
        return {
            "classifier": model_dir / "classifier.json",
            "regressor_median": model_dir / "regressor_median.json",
            "regressor_lower": model_dir / "regressor_lower.json",
            "regressor_upper": model_dir / "regressor_upper.json",
            "calibration": model_dir / "calibration.pkl",
            "metadata": model_dir / "metadata.json",
        }

    @classmethod
    def _missing_artifact_files(cls, model_dir: Path) -> list[str]:
        return [
            path.name
            for path in cls._required_artifact_paths(model_dir).values()
            if not path.exists()
        ]

    @staticmethod
    def _invalid_inference_feature_columns(feature_columns: list[str]) -> list[str]:
        return sorted(
            {
                str(column)
                for column in feature_columns
                if str(column) in TRAINING_ONLY_PANEL_COLUMNS
            }
        )

    @classmethod
    def _artifact_payload_from_dir(cls, model_dir: Path) -> dict[str, Any]:
        required_paths = cls._required_artifact_paths(model_dir)
        if not all(path.exists() for path in required_paths.values()):
            return {}

        classifier = XGBClassifier()
        classifier.load_model(str(required_paths["classifier"]))
        regressor_median = XGBRegressor()
        regressor_median.load_model(str(required_paths["regressor_median"]))
        regressor_lower = XGBRegressor()
        regressor_lower.load_model(str(required_paths["regressor_lower"]))
        regressor_upper = XGBRegressor()
        regressor_upper.load_model(str(required_paths["regressor_upper"]))
        metadata = json.loads(required_paths["metadata"].read_text())
        hierarchy_models: dict[str, dict[str, XGBRegressor]] = {}
        optional_hierarchy_paths = {
            "cluster": {
                "median": model_dir / "cluster_regressor_median.json",
                "lower": model_dir / "cluster_regressor_lower.json",
                "upper": model_dir / "cluster_regressor_upper.json",
            },
            "national": {
                "median": model_dir / "national_regressor_median.json",
                "lower": model_dir / "national_regressor_lower.json",
                "upper": model_dir / "national_regressor_upper.json",
            },
        }
        for level, level_paths in optional_hierarchy_paths.items():
            if not all(path.exists() for path in level_paths.values()):
                continue
            bundle: dict[str, XGBRegressor] = {}
            for name, path in level_paths.items():
                model = XGBRegressor()
                model.load_model(str(path))
                bundle[name] = model
            hierarchy_models[level] = bundle
        quantile_regressors: dict[float, XGBRegressor] = {}
        for quantile in metadata.get("forecast_quantiles") or []:
            quantile_path = model_dir / f"q{int(round(float(quantile) * 1000)):04d}.json"
            if not quantile_path.exists():
                continue
            model = XGBRegressor()
            model.load_model(str(quantile_path))
            quantile_regressors[float(quantile)] = model
        with open(required_paths["calibration"], "rb") as handle:
            calibration = pickle.load(handle)
        dataset_manifest_path = model_dir / "dataset_manifest.json"
        point_in_time_path = model_dir / "point_in_time_snapshot.json"
        return {
            "classifier": classifier,
            "regressor_median": regressor_median,
            "regressor_lower": regressor_lower,
            "regressor_upper": regressor_upper,
            "quantile_regressors": quantile_regressors,
            "hierarchy_models": hierarchy_models,
            "calibration": calibration,
            "metadata": metadata,
            "dataset_manifest": json.loads(dataset_manifest_path.read_text()) if dataset_manifest_path.exists() else None,
            "point_in_time_snapshot": json.loads(point_in_time_path.read_text()) if point_in_time_path.exists() else None,
        }

    @staticmethod
    def _apply_calibration(calibration: Any, raw_probabilities: np.ndarray) -> np.ndarray:
        if calibration is None:
            return np.clip(raw_probabilities.astype(float), 0.001, 0.999)
        return np.clip(calibration.predict(raw_probabilities.astype(float)), 0.001, 0.999)

    def _latest_as_of_date(self, virus_typ: str) -> pd.Timestamp:
        return self.feature_builder.latest_available_as_of_date(virus_typ=virus_typ)

    @staticmethod
    def _decision_stage_sort_value(stage: str | None) -> int:
        return {
            "activate": 3,
            "prepare": 2,
            "watch": 1,
        }.get(str(stage or "watch").strip().lower(), 0)

    @classmethod
    def _decision_priority_sort_key(cls, item: dict[str, Any]) -> tuple[float, float, float, float]:
        decision = item.get("decision") or {}
        return (
            float(cls._decision_stage_sort_value(decision.get("stage"))),
            float(item.get("priority_score") or 0.0),
            float(item.get("event_probability_calibrated") or 0.0),
            float(item.get("change_pct") or 0.0),
        )

    @classmethod
    def _decision_summary(cls, predictions: list[dict[str, Any]]) -> dict[str, Any]:
        if not predictions:
            return {
                "watch_regions": 0,
                "prepare_regions": 0,
                "activate_regions": 0,
                "avg_priority_score": 0.0,
                "top_region": None,
                "top_region_decision": None,
            }

        ranked_decisions = sorted(
            predictions,
            key=cls._decision_priority_sort_key,
            reverse=True,
        )
        top_region = ranked_decisions[0]
        return {
            "watch_regions": sum(1 for item in predictions if str(item.get("decision_label") or "").lower() == "watch"),
            "prepare_regions": sum(1 for item in predictions if str(item.get("decision_label") or "").lower() == "prepare"),
            "activate_regions": sum(1 for item in predictions if str(item.get("decision_label") or "").lower() == "activate"),
            "avg_priority_score": round(
                sum(float(item.get("priority_score") or 0.0) for item in predictions) / len(predictions),
                4,
            ),
            "top_region": top_region.get("bundesland"),
            "top_region_decision": top_region.get("decision_label"),
        }

    @staticmethod
    def _media_spend_gate(
        *,
        quality_gate: dict[str, Any],
        business_gate: dict[str, Any],
        activation_policy: str,
    ) -> tuple[bool, list[str]]:
        blockers: list[str] = []
        if activation_policy == "watch_only":
            blockers.append("Activation policy 'watch_only' forces observation mode.")
        if not business_gate.get("validated_for_budget_activation"):
            blockers.append("Business-Gate noch nicht validiert.")
        if not quality_gate.get("overall_passed"):
            blockers.append("Quality Gate blockiert Aktivierung.")
        return len(blockers) == 0, blockers

    @staticmethod
    def _media_action(
        *,
        recommended_level: str,
        spend_enabled: bool,
    ) -> str:
        if not spend_enabled:
            return "watch"
        stage = str(recommended_level or "Watch").strip().lower()
        if stage in {"activate", "prepare"}:
            return stage
        return "watch"

    @staticmethod
    def _media_intensity(action: str) -> str:
        return {
            "activate": "high",
            "prepare": "medium",
        }.get(str(action or "watch").strip().lower(), "low")

    @staticmethod
    def _products_from_allocation(
        *,
        allocation_item: dict[str, Any],
        virus_typ: str,
    ) -> list[str]:
        product_clusters = allocation_item.get("product_clusters") or []
        if product_clusters:
            cluster = product_clusters[0] or {}
            products = [str(item) for item in cluster.get("products") or [] if str(item).strip()]
            if products:
                return products
        return GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"])

    @staticmethod
    def _media_timeline(
        *,
        action: str,
        spend_enabled: bool,
        activation_policy: str,
        business_gate: dict[str, Any],
        quality_gate: dict[str, Any],
    ) -> str:
        if not spend_enabled:
            return (
                "Nur beobachten — Shadow-Policy blockiert Aktivierung"
                if activation_policy == "watch_only"
                else "Nur beobachten — Business-Gate noch nicht validiert"
                if not business_gate.get("validated_for_budget_activation")
                else "Nur beobachten — Quality Gate blockiert Aktivierung"
                if not quality_gate.get("overall_passed")
                else "Nur beobachten — Spend aktuell blockiert"
            )
        if action == "activate":
            return f"Sofort aktivieren — Wellenfenster in {TARGET_WINDOW_DAYS[0]}-{TARGET_WINDOW_DAYS[1]} Tagen"
        if action == "prepare":
            return "In 1-2 Tagen vorbereiten — Signal fuer regionale Aktivierung vorhanden"
        return "Beobachten — unterhalb des operationalen Spend-Niveaus"

    @staticmethod
    def _media_headline(
        *,
        virus_typ: str,
        recommendations: list[dict[str, Any]],
        spend_enabled: bool,
    ) -> str:
        prioritized = [
            item["bundesland"]
            for item in recommendations
            if item["action"] in {"activate", "prepare"} and float(item.get("suggested_budget_share") or 0.0) > 0.0
        ]
        if prioritized and spend_enabled:
            return f"{virus_typ}: Budget auf {', '.join(prioritized[:3])} fokussieren"
        return f"{virus_typ}: aktuell kein validierter Aktivierungs-Case"

    @staticmethod
    def _metric_delta(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, float]:
        delta: dict[str, float] = {}
        for metric in (
            "precision_at_top3",
            "precision_at_top5",
            "pr_auc",
            "brier_score",
            "ece",
            "activation_false_positive_rate",
        ):
            if metric in candidate and metric in reference:
                delta[metric] = round(float(candidate[metric]) - float(reference[metric]), 6)
        return delta

    @staticmethod
    def _benchmark_score(item: dict[str, Any]) -> float:
        metrics = item.get("aggregate_metrics") or {}
        quality_gate = item.get("quality_gate") or {}
        precision = float(metrics.get("precision_at_top3") or 0.0)
        pr_auc = float(metrics.get("pr_auc") or 0.0)
        ece = float(metrics.get("ece") or 1.0)
        fp_rate = float(metrics.get("activation_false_positive_rate") or 1.0)
        score = (
            precision * 0.4
            + pr_auc * 0.35
            + max(0.0, 1.0 - min(ece, 1.0)) * 0.15
            + max(0.0, 1.0 - min(fp_rate, 1.0)) * 0.10
        )
        if quality_gate.get("overall_passed"):
            score += 0.1
        return round(score * 100.0, 2)

    def _portfolio_priority_score(
        self,
        *,
        prediction: dict[str, Any],
        benchmark_item: dict[str, Any],
    ) -> float:
        probability = float(prediction.get("event_probability_calibrated") or 0.0)
        change_pct = float(prediction.get("change_pct") or 0.0)
        benchmark_score = float(benchmark_item.get("benchmark_score") or 0.0) / 100.0
        quality_gate = prediction.get("quality_gate") or {}
        activation_policy = str(prediction.get("activation_policy") or "quality_gate")
        business_gate = prediction.get("business_gate") or benchmark_item.get("business_gate") or {}
        if activation_policy == "watch_only":
            readiness_multiplier = 0.78
        elif not business_gate.get("validated_for_budget_activation"):
            readiness_multiplier = 0.84 if quality_gate.get("overall_passed") else 0.68
        else:
            readiness_multiplier = 1.0 if quality_gate.get("overall_passed") else 0.72
        momentum_multiplier = 1.0 + min(max(change_pct, 0.0), 80.0) / 200.0
        return round(probability * max(benchmark_score, 0.05) * readiness_multiplier * momentum_multiplier * 100.0, 2)

    def _portfolio_action(
        self,
        *,
        prediction: dict[str, Any],
        benchmark_item: dict[str, Any],
    ) -> tuple[str, str]:
        probability = float(prediction.get("event_probability_calibrated") or 0.0)
        change_pct = float(prediction.get("change_pct") or 0.0)
        threshold = float(prediction.get("action_threshold") or 0.6)
        quality_gate = prediction.get("quality_gate") or {}
        activation_policy = str(prediction.get("activation_policy") or "quality_gate")
        business_gate = prediction.get("business_gate") or benchmark_item.get("business_gate") or {}

        if activation_policy == "watch_only":
            if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
                return "prioritize", "medium"
            return "watch", "low"

        if not business_gate.get("validated_for_budget_activation"):
            if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
                return "prioritize", "medium"
            return "watch", "low"
        if quality_gate.get("overall_passed") and probability >= threshold and change_pct >= 20:
            return "activate", "high"
        if quality_gate.get("overall_passed") and probability >= threshold:
            return "prepare", "medium"
        if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
            return "prioritize", "medium"
        return "watch", "low"

    @staticmethod
    def _region_rollup(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in opportunities:
            grouped.setdefault(item["bundesland"], []).append(item)

        region_rollup: list[dict[str, Any]] = []
        for bundesland, items in grouped.items():
            ranked_items = sorted(
                items,
                key=lambda item: float(item.get("portfolio_priority_score") or 0.0),
                reverse=True,
            )
            leader = ranked_items[0]
            region_rollup.append(
                {
                    "bundesland": bundesland,
                    "bundesland_name": leader["bundesland_name"],
                    "leading_virus": leader["virus_typ"],
                    "leading_probability": leader["event_probability_calibrated"],
                    "leading_priority_score": leader["portfolio_priority_score"],
                    "top_signals": [
                        {
                            "virus_typ": item["virus_typ"],
                            "portfolio_action": item["portfolio_action"],
                            "portfolio_priority_score": item["portfolio_priority_score"],
                            "event_probability_calibrated": item["event_probability_calibrated"],
                        }
                        for item in ranked_items[:3]
                    ],
                }
            )

        region_rollup.sort(
            key=lambda item: float(item.get("leading_priority_score") or 0.0),
            reverse=True,
        )
        return region_rollup

    def _truth_readiness(self, *, brand: str = "gelo") -> dict[str, Any]:
        if self.db is None:
            return {
                "coverage_weeks": 0,
                "truth_readiness": "noch_nicht_angeschlossen",
                "truth_ready": False,
                "expected_units_lift_enabled": False,
                "expected_revenue_lift_enabled": False,
            }
        return ForecastDecisionService(self.db).get_truth_readiness(brand=brand)

    def _business_gate(
        self,
        *,
        quality_gate: dict[str, Any],
        truth_readiness: dict[str, Any] | None = None,
        brand: str = "gelo",
    ) -> dict[str, Any]:
        forecast_ready = bool((quality_gate or {}).get("overall_passed"))
        if self.db is None:
            truth = truth_readiness or self._truth_readiness(brand=brand)
            return {
                "truth_readiness": str(truth.get("truth_readiness") or "noch_nicht_angeschlossen"),
                "truth_ready": bool(truth.get("truth_ready")),
                "coverage_weeks": int(truth.get("coverage_weeks") or 0),
                "expected_units_lift_enabled": False,
                "expected_revenue_lift_enabled": False,
                "action_class": "watch_only" if not forecast_ready else "market_watch",
                "validation_status": "pending_truth_connection" if int(truth.get("coverage_weeks") or 0) <= 0 else "building_truth_layer",
                "decision_scope": "decision_support_only",
                "validated_for_budget_activation": False,
                "evidence_tier": "no_truth" if int(truth.get("coverage_weeks") or 0) <= 0 else "observational",
            }

        validation = BusinessValidationService(self.db).evaluate(
            brand=brand,
            truth_coverage=truth_readiness,
        )
        validation["quality_gate_passed"] = forecast_ready
        return validation

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
        normalized_products = [
            str(product).strip()
            for product in products
            if str(product or "").strip()
        ] or [""]
        window_start, window_end = self._truth_assessment_window(target_week_start)
        assessments: list[dict[str, Any]] = []
        for product in normalized_products:
            assessment = self._truth_layer_assessment_for_product(
                brand=brand,
                region_code=region_code,
                product=product or None,
                window_start=window_start,
                window_end=window_end,
                signal_context=signal_context,
            )
            spend_gate_status, budget_release_recommendation = self._commercial_truth_gate(
                truth_assessment=assessment,
                operational_action=operational_action,
                operational_gate_open=operational_gate_open,
            )
            assessments.append(
                {
                    "product": product or None,
                    "scope": assessment.get("scope") or {},
                    "outcome_readiness": assessment.get("outcome_readiness") or {},
                    "evidence_status": assessment.get("evidence_status"),
                    "evidence_confidence": assessment.get("evidence_confidence"),
                    "signal_outcome_agreement": assessment.get("signal_outcome_agreement") or {},
                    "holdout_eligibility": assessment.get("holdout_eligibility") or {},
                    "commercial_gate": assessment.get("commercial_gate") or {},
                    "metadata": assessment.get("metadata") or {},
                    "spend_gate_status": spend_gate_status,
                    "budget_release_recommendation": budget_release_recommendation,
                }
            )

        primary = assessments[0]
        return {
            "truth_layer_enabled": bool(self.db is not None),
            "truth_scope": {
                "brand": str(brand or "gelo").strip().lower(),
                "region_code": str(region_code or "").strip().upper() or None,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "lookback_weeks": _TRUTH_LOOKBACK_WEEKS,
                "products": [item["product"] for item in assessments],
                "primary_product": primary["product"],
            },
            "outcome_readiness": primary["outcome_readiness"],
            "evidence_status": primary["evidence_status"],
            "evidence_confidence": primary["evidence_confidence"],
            "signal_outcome_agreement": primary["signal_outcome_agreement"],
            "spend_gate_status": primary["spend_gate_status"],
            "budget_release_recommendation": primary["budget_release_recommendation"],
            "commercial_gate": primary["commercial_gate"],
            "truth_assessments": assessments,
        }

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
        if self.db is None:
            return self._fallback_truth_assessment(
                brand=brand,
                region_code=region_code,
                product=product,
                window_start=window_start,
                window_end=window_end,
                signal_context=signal_context,
                source_mode="unavailable",
                message="Truth-Layer ist optional; in dieser Laufzeit ist keine Outcome-Datenbank verbunden.",
            )
        try:
            return TruthLayerService(self.db).assess(
                brand=brand,
                region_code=region_code,
                product=product,
                window_start=window_start,
                window_end=window_end,
                signal_context=signal_context,
            )
        except Exception:
            logger.exception(
                "Truth layer assessment failed for brand=%s region=%s product=%s",
                brand,
                region_code,
                product,
            )
            return self._fallback_truth_assessment(
                brand=brand,
                region_code=region_code,
                product=product,
                window_start=window_start,
                window_end=window_end,
                signal_context=signal_context,
                source_mode="error",
                message="Truth-Layer konnte fuer diese Scope-Abfrage nicht ausgewertet werden.",
            )

    @staticmethod
    def _truth_assessment_window(target_week_start: Any) -> tuple[datetime, datetime]:
        target_start = pd.Timestamp(target_week_start).normalize()
        return (
            (target_start - pd.Timedelta(weeks=_TRUTH_LOOKBACK_WEEKS)).to_pydatetime(),
            (target_start + pd.Timedelta(days=6)).to_pydatetime(),
        )

    @staticmethod
    def _truth_signal_context(
        *,
        prediction: dict[str, Any],
        confidence: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        decision = dict(prediction.get("decision") or {})
        decision_stage = str(
            stage
            or decision.get("stage")
            or prediction.get("decision_label")
            or ""
        ).strip().lower()
        event_probability = float(prediction.get("event_probability_calibrated") or 0.0)
        forecast_confidence = (
            confidence
            if confidence is not None
            else decision.get("forecast_confidence")
        )
        signal_present = decision_stage in {"activate", "prepare"} or event_probability >= 0.5
        context = {
            "signal_present": signal_present,
            "decision_stage": decision_stage or None,
            "event_probability": event_probability,
        }
        if forecast_confidence is not None:
            context["confidence"] = float(forecast_confidence)
            context["forecast_confidence"] = float(forecast_confidence)
        return context

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
        signal_present = bool(signal_context.get("signal_present"))
        signal_confidence = signal_context.get("confidence") or signal_context.get("forecast_confidence")
        try:
            normalized_confidence = float(signal_confidence or signal_context.get("event_probability") or 0.0)
        except (TypeError, ValueError):
            normalized_confidence = 0.0
        return {
            "scope": {
                "brand": str(brand or "gelo").strip().lower(),
                "region_code": str(region_code or "").strip().upper() or None,
                "product": str(product).strip() if product else None,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
            },
            "outcome_readiness": {
                "status": "missing",
                "score": 0.0,
                "coverage_weeks": 0,
                "metrics_present": [],
                "regions_present": 0,
                "products_present": 0,
                "spend_windows": 0,
                "response_windows": 0,
                "notes": [message],
            },
            "signal_outcome_agreement": {
                "status": "no_outcome_support" if signal_present else "no_signal",
                "signal_present": signal_present,
                "historical_response_observed": False,
                "score": round(0.2 * normalized_confidence, 4) if signal_present else None,
                "signal_confidence": round(normalized_confidence, 4) if signal_present else None,
                "outcome_support_score": 0.0,
                "outcome_confidence": 0.0,
                "notes": [message],
            },
            "holdout_eligibility": {
                "eligible": False,
                "ready": False,
                "holdout_groups": [],
                "reason": "No scoped outcome data is available for holdout validation.",
            },
            "evidence_status": "no_truth",
            "evidence_confidence": 0.0,
            "commercial_gate": {
                "budget_decision_allowed": False,
                "decision_scope": "decision_support_only",
                "message": message,
            },
            "metadata": {
                "source_mode": source_mode,
                "observations": 0,
                "metrics_present": [],
                "optional_layer": True,
            },
        }

    @staticmethod
    def _commercial_truth_gate(
        *,
        truth_assessment: dict[str, Any],
        operational_action: str,
        operational_gate_open: bool,
    ) -> tuple[str, str]:
        action = str(operational_action or "watch").strip().lower()
        evidence_status = str(truth_assessment.get("evidence_status") or "no_truth").strip().lower()
        budget_allowed = bool((truth_assessment.get("commercial_gate") or {}).get("budget_decision_allowed"))

        if action == "prioritize":
            return "prioritize_only", "hold"
        if action not in {"activate", "prepare"}:
            return "not_applicable", "hold"
        if not operational_gate_open:
            return "blocked_operational_gate", "hold"
        if budget_allowed or evidence_status == "commercially_validated":
            return "released", "release"
        if evidence_status in {"holdout_ready", "truth_backed"}:
            return "guarded_release", "limited_release"
        return "manual_review_required", "manual_review"

    def _truth_layer_rollup(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        evidence_status_counts: dict[str, int] = {}
        spend_gate_status_counts: dict[str, int] = {}
        budget_release_counts: dict[str, int] = {}
        for item in items:
            evidence_status = str(item.get("evidence_status") or "").strip()
            spend_gate_status = str(item.get("spend_gate_status") or "").strip()
            budget_release = str(item.get("budget_release_recommendation") or "").strip()
            if evidence_status:
                evidence_status_counts[evidence_status] = evidence_status_counts.get(evidence_status, 0) + 1
            if spend_gate_status:
                spend_gate_status_counts[spend_gate_status] = spend_gate_status_counts.get(spend_gate_status, 0) + 1
            if budget_release:
                budget_release_counts[budget_release] = budget_release_counts.get(budget_release, 0) + 1
        return {
            "enabled": bool(self.db is not None),
            "lookback_weeks": _TRUTH_LOOKBACK_WEEKS,
            "scopes_evaluated": len(items),
            "evidence_status_counts": evidence_status_counts,
            "spend_gate_status_counts": spend_gate_status_counts,
            "budget_release_recommendation_counts": budget_release_counts,
        }

    @staticmethod
    def _model_version(metadata: dict[str, Any]) -> str:
        model_family = str(metadata.get("model_family") or "regional_pooled_panel")
        trained_at = str(metadata.get("trained_at") or "unversioned")
        horizon = metadata.get("horizon_days")
        if horizon is None:
            return f"{model_family}:{trained_at}"
        return f"{model_family}:h{horizon}:{trained_at}"

    @staticmethod
    def _calibration_version(metadata: dict[str, Any]) -> str:
        trained_at = str(metadata.get("trained_at") or "unversioned")
        horizon = metadata.get("horizon_days")
        if horizon is None:
            return f"isotonic:{trained_at}"
        return f"isotonic:h{horizon}:{trained_at}"
