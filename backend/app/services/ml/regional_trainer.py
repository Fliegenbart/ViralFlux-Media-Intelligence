"""Pooled regional panel trainer for leakage-safe outbreak forecasting."""

from __future__ import annotations
from app.core.time import utc_now

import json
import logging
import pickle
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier, XGBRegressor

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES, quantile_key
from app.services.ml.benchmarking.leaderboard import build_leaderboard
from app.services.ml.benchmarking.metrics import summarize_probabilistic_metrics
from app.services.ml.benchmarking.registry import (
    DEFAULT_METRIC_SEMANTICS_VERSION,
    DEFAULT_PROMOTION_MIN_SAMPLE_COUNT,
    ForecastRegistry,
)
from app.services.ml.forecast_orchestrator import ForecastOrchestrator
from app.services.ml.forecast_horizon_utils import (
    apply_probability_calibration,
    build_calibration_guard_split_dates,
    build_calibration_split_dates,
    fit_isotonic_calibrator,
    SUPPORTED_FORECAST_HORIZONS,
    ensure_supported_horizon,
    regional_horizon_support_status,
    regional_model_artifact_dir,
)
from app.services.ml.models.event_classifier import LearnedEventModel
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    TARGET_WINDOW_DAYS,
    activation_policy_for_virus,
    absolute_incidence_threshold,
    activation_false_positive_rate,
    average_precision_safe,
    brier_score_safe,
    build_event_label,
    choose_action_threshold,
    compute_ece,
    event_definition_config_for_virus,
    median_lead_days,
    precision_at_k,
    quality_gate_from_metrics,
    rollout_mode_for_virus,
    signal_bundle_version_for_virus,
    time_based_panel_splits,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
    normalize_weather_forecast_vintage_mode,
)
from app.services.ml import regional_trainer_backtest

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"
_REGISTRY_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "forecast_registry"

CALIBRATION_HOLDOUT_FRACTION = 0.20
CALIBRATION_GUARD_FRACTION = 0.35
MIN_CALIBRATION_GUARD_DATES = 7
CALIBRATION_GUARD_EPSILON = 1e-6
HIERARCHY_BLEND_WEIGHT_GRID = tuple(round(value, 2) for value in np.linspace(0.0, 1.0, 11))
HIERARCHY_BLEND_MIN_TOTAL_SAMPLES = 12
HIERARCHY_BLEND_MIN_REGIME_SAMPLES = 6
HIERARCHY_BLEND_EPSILON = 1e-6

REGIONAL_CLASSIFIER_CONFIG: dict[str, Any] = {
    "n_estimators": 160,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": 1,
}

REGIONAL_REGRESSOR_CONFIG: dict[str, dict[str, Any]] = {
    "median": {
        "n_estimators": 140,
        "max_depth": 4,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.5,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "lower": {
        "n_estimators": 100,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.1,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "upper": {
        "n_estimators": 100,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.9,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
}

EXCLUDED_MODEL_COLUMNS = {
    "virus_typ",
    "bundesland",
    "bundesland_name",
    "as_of_date",
    "target_date",
    "target_week_start",
    "target_window_days",
    "horizon_days",
    "event_definition_version",
    "truth_source",
    "target_truth_source",
    "target_incidence",
    "current_known_incidence",
    "next_week_incidence",
    "seasonal_baseline",
    "seasonal_mad",
    "event_label",
    "y_next_log",
}

TRAINING_ONLY_PANEL_COLUMNS = {
    "target_incidence",
}


def _virus_slug(virus_typ: str) -> str:
    return virus_typ.lower().replace(" ", "_").replace("-", "_")


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _target_window_for_horizon(horizon_days: int) -> list[int]:
    horizon = ensure_supported_horizon(horizon_days)
    return [horizon, horizon]


def _quantile_regressor_config(quantile: float) -> dict[str, Any]:
    if np.isclose(quantile, 0.5):
        config = dict(REGIONAL_REGRESSOR_CONFIG["median"])
    elif quantile < 0.5:
        config = dict(REGIONAL_REGRESSOR_CONFIG["lower"])
    else:
        config = dict(REGIONAL_REGRESSOR_CONFIG["upper"])
    config["quantile_alpha"] = float(quantile)
    return config


def _state_order_from_codes(values: list[str]) -> list[str]:
    present = {str(value) for value in values if str(value)}
    ordered = [state for state in ALL_BUNDESLAENDER if state in present]
    if ordered:
        return ordered
    return sorted(present)


class RegionalModelTrainer:
    """Train pooled per-virus panel models across all Bundesländer."""

    def __init__(self, db, models_dir: Path | None = None) -> None:
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.feature_builder = RegionalFeatureBuilder(db)
        self.registry = ForecastRegistry(registry_root=_REGISTRY_DIR)
        self.orchestrator = ForecastOrchestrator(registry_root=_REGISTRY_DIR)

    def train_region(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        lookback_days: int = 900,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        summary = self.train_all_regions(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
        )
        details = (summary.get("backtest") or {}).get("details") or {}
        return details.get(bundesland.upper(), {"error": f"No summary available for {bundesland.upper()}"})

    def train_all_regions(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
        persist: bool = True,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        horizons = self._selected_horizons(
            horizon_days=horizon_days,
            horizon_days_list=horizon_days_list,
        )
        if len(horizons) > 1:
            scopes = {
                f"h{horizon}": self.train_all_regions(
                    virus_typ=virus_typ,
                    lookback_days=lookback_days,
                    persist=persist,
                    horizon_days=horizon,
                    weather_forecast_vintage_mode=weather_forecast_vintage_mode,
                    weather_vintage_comparison=weather_vintage_comparison,
                )
                for horizon in horizons
            }
            statuses = [payload.get("status") for payload in scopes.values()]
            return {
                "status": (
                    "success"
                    if statuses and all(status in {"success", "unsupported"} for status in statuses)
                    else "partial_error"
                ),
                "virus_typ": virus_typ,
                "horizon_days_list": list(horizons),
                "trained": sum(int((payload or {}).get("trained") or 0) for payload in scopes.values()),
                "failed": sum(int((payload or {}).get("failed") or 0) for payload in scopes.values()),
                "unsupported": sum(
                    1
                    for payload in scopes.values()
                    if (payload or {}).get("status") == "unsupported"
                ),
                "scopes": scopes,
                "aggregate_metrics": {
                    key: (payload or {}).get("aggregate_metrics") or {}
                    for key, payload in scopes.items()
                },
                "quality_gate": {
                    key: (payload or {}).get("quality_gate") or {}
                    for key, payload in scopes.items()
                },
            }

        return self._train_single_horizon(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            persist=persist,
            horizon_days=horizons[0],
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            weather_vintage_comparison=weather_vintage_comparison,
        )

    def _train_single_horizon(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        persist: bool,
        horizon_days: int,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        support = regional_horizon_support_status(virus_typ, horizon)
        if not support["supported"]:
            return {
                "status": "unsupported",
                "virus_typ": virus_typ,
                "horizon_days": horizon,
                "target_window_days": _target_window_for_horizon(horizon),
                "supported_horizon_days_for_virus": support["supported_horizons"],
                "message": support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
                "trained": 0,
                "failed": 0,
            }
        try:
            logger.info("Training pooled regional panel model for %s (horizon=%s)", virus_typ, horizon)
            previous_artifact = self.load_artifacts(virus_typ=virus_typ, horizon_days=horizon)
            panel = self._build_training_panel(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
                horizon_days=horizon,
                weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            )
            panel = self._prepare_horizon_panel(panel, horizon_days=horizon)
            if panel.empty or len(panel) < 200:
                return {
                    "status": "error",
                    "virus_typ": virus_typ,
                    "horizon_days": horizon,
                    "target_window_days": _target_window_for_horizon(horizon),
                    "error": f"Insufficient pooled panel data ({len(panel)} rows) for horizon {horizon}.",
                }

            panel = panel.copy()
            panel["y_next_log"] = np.log1p(panel["next_week_incidence"].astype(float).clip(lower=0.0))
            feature_columns = self._feature_columns(panel)
            hierarchy_feature_columns = GeoHierarchyHelper.hierarchy_feature_columns(feature_columns)
            ww_only_columns = self._ww_only_feature_columns(feature_columns)
            event_config = event_definition_config_for_virus(virus_typ)

            selection = self._select_event_definition(
                virus_typ=virus_typ,
                panel=panel,
                feature_columns=feature_columns,
                event_config=event_config,
            )
            tau = float(selection["tau"])
            kappa = float(selection["kappa"])
            action_threshold = float(selection["action_threshold"])

            panel["event_label"] = self._event_labels(
                panel,
                virus_typ=virus_typ,
                tau=tau,
                kappa=kappa,
                event_config=event_config,
            )
            backtest_bundle = self._build_backtest_bundle(
                virus_typ=virus_typ,
                panel=panel,
                feature_columns=feature_columns,
                hierarchy_feature_columns=hierarchy_feature_columns,
                ww_only_columns=ww_only_columns,
                tau=tau,
                kappa=kappa,
                action_threshold=action_threshold,
                horizon_days=horizon,
                event_config=event_config,
            )
            rollout_info = self._rollout_metadata(
                virus_typ=virus_typ,
                horizon_days=horizon,
                aggregate_metrics=backtest_bundle["aggregate_metrics"],
                baseline_metrics=(backtest_bundle["backtest_payload"].get("baselines") or {}),
                previous_artifact=previous_artifact,
            )
            backtest_bundle["backtest_payload"].update(_json_safe(rollout_info))
            backtest_bundle["backtest_payload"]["benchmark_summary"] = _json_safe(backtest_bundle.get("benchmark_summary") or {})
            final_artifacts = self._fit_final_models(
                panel=panel,
                feature_columns=feature_columns,
                hierarchy_feature_columns=hierarchy_feature_columns,
                oof_frame=backtest_bundle["oof_frame"],
                action_threshold=action_threshold,
            )
            calibration_mode = str(
                final_artifacts.get("calibration_mode")
                or ("isotonic" if final_artifacts.get("calibration") is not None else "raw_passthrough")
            )

            dataset_manifest = {
                **self.feature_builder.dataset_manifest(virus_typ=virus_typ, panel=panel),
                "horizon_days": horizon,
                "target_window_days": _target_window_for_horizon(horizon),
            }
            point_in_time_manifest = {
                **self.feature_builder.point_in_time_snapshot_manifest(virus_typ=virus_typ, panel=panel),
                "horizon_days": horizon,
                "target_window_days": _target_window_for_horizon(horizon),
            }
            primary_weather_vintage_summary = self._weather_vintage_mode_summary(
                weather_forecast_vintage_mode=normalize_weather_forecast_vintage_mode(
                    dataset_manifest.get("weather_forecast_vintage_mode")
                ),
                dataset_manifest=dataset_manifest,
                backtest_bundle=backtest_bundle,
                selection=selection,
                calibration_mode=calibration_mode,
            )
            weather_vintage_comparison_payload = (
                self._build_weather_vintage_comparison(
                    virus_typ=virus_typ,
                    lookback_days=lookback_days,
                    horizon_days=horizon,
                    primary_summary=primary_weather_vintage_summary,
                    event_config=event_config,
                )
                if weather_vintage_comparison
                else None
            )
            if weather_vintage_comparison_payload is not None:
                backtest_bundle.setdefault("benchmark_summary", {})[
                    "weather_vintage_comparison"
                ] = _json_safe(weather_vintage_comparison_payload)
            hierarchy_metadata = self._build_hierarchy_metadata(
                panel=panel,
                oof_frame=backtest_bundle["oof_frame"],
            )
            hierarchy_benchmark = (backtest_bundle.get("benchmark_summary") or {}).get("hierarchy_benchmark") or {}
            hierarchy_diagnostics = (backtest_bundle.get("benchmark_summary") or {}).get("hierarchy_diagnostics") or {}
            cluster_homogeneity = (backtest_bundle.get("benchmark_summary") or {}).get("cluster_homogeneity") or {}
            hierarchy_metadata["enabled"] = bool(hierarchy_benchmark.get("promote_reconciliation"))
            hierarchy_metadata["selection_basis"] = hierarchy_benchmark.get("selection_basis") or "benchmark_pending"
            hierarchy_metadata["benchmark_metrics"] = hierarchy_benchmark.get("comparison") or {}
            hierarchy_metadata["component_diagnostics"] = hierarchy_diagnostics
            hierarchy_metadata["cluster_homogeneity"] = cluster_homogeneity
            hierarchy_metadata["model_modes"] = final_artifacts.get("hierarchy_model_modes") or {}
            hierarchy_metadata["aggregate_blend_policy"] = {
                "cluster": ((hierarchy_diagnostics.get("cluster") or {}).get("blend_policy") or {}),
                "national": ((hierarchy_diagnostics.get("national") or {}).get("blend_policy") or {}),
            }
            policy_reference_date = pd.to_datetime(panel["as_of_date"], errors="coerce").max() if "as_of_date" in panel.columns else None
            cluster_blend_resolution = GeoHierarchyHelper.resolve_blend_weight_policy(
                hierarchy_metadata["aggregate_blend_policy"].get("cluster"),
                as_of_date=policy_reference_date or utc_now(),
                horizon_days=horizon,
                fallback=float(((hierarchy_diagnostics.get("cluster") or {}).get("recommended_blend_weight") or 0.0)),
            )
            national_blend_resolution = GeoHierarchyHelper.resolve_blend_weight_policy(
                hierarchy_metadata["aggregate_blend_policy"].get("national"),
                as_of_date=policy_reference_date or utc_now(),
                horizon_days=horizon,
                fallback=float(((hierarchy_diagnostics.get("national") or {}).get("recommended_blend_weight") or 0.0)),
            )
            hierarchy_metadata["aggregate_blend_weights"] = {
                "cluster": float(cluster_blend_resolution.get("weight") or 0.0),
                "national": float(national_blend_resolution.get("weight") or 0.0),
            }
            hierarchy_metadata["aggregate_blend_context"] = {
                "regime": cluster_blend_resolution.get("regime") or national_blend_resolution.get("regime"),
                "cluster": cluster_blend_resolution,
                "national": national_blend_resolution,
            }
            model_dir = regional_model_artifact_dir(
                self.models_dir,
                virus_typ=virus_typ,
                horizon_days=horizon,
            )
            metadata = {
                "virus_typ": virus_typ,
                "model_family": "regional_pooled_panel",
                "trained_at": utc_now().isoformat(),
                "model_version": None,
                "calibration_version": None,
                "horizon_days": horizon,
                "target_window_days": _target_window_for_horizon(horizon),
                "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
                "forecast_target_semantics": "current_known_incidence_at_as_of_plus_horizon_days",
                "metric_semantics_version": DEFAULT_METRIC_SEMANTICS_VERSION,
                "weather_forecast_vintage_mode": dataset_manifest.get("weather_forecast_vintage_mode"),
                "exogenous_feature_semantics_version": dataset_manifest.get("exogenous_feature_semantics_version"),
                "feature_columns": feature_columns,
                "hierarchy_feature_columns": hierarchy_feature_columns,
                "ww_only_feature_columns": ww_only_columns,
                "selected_tau": tau,
                "selected_kappa": kappa,
                "action_threshold": action_threshold,
                "event_definition_version": EVENT_DEFINITION_VERSION,
                "min_event_absolute_incidence": event_config.min_absolute_incidence,
                "event_definition_config": event_config.to_manifest(),
                "dataset_manifest": dataset_manifest,
                "nowcast_features_enabled": True,
                "forecast_quantiles": [float(value) for value in CANONICAL_FORECAST_QUANTILES],
                "signal_bundle_version": rollout_info["signal_bundle_version"],
                "rollout_mode": rollout_info["rollout_mode"],
                "activation_policy": rollout_info["activation_policy"],
                "shadow_evaluation": rollout_info.get("shadow_evaluation"),
                "quality_gate": backtest_bundle["quality_gate"],
                "aggregate_metrics": backtest_bundle["aggregate_metrics"],
                "benchmark_summary": backtest_bundle.get("benchmark_summary") or {},
                "label_selection": selection,
                "revision_policy_metadata": {
                    "default_policy": "raw",
                    "supported_policies": ["raw", "adjusted", "adaptive"],
                    "selection_basis": "fallback_no_benchmark_evidence",
                    "source_policies": {},
                },
                "learned_event_model": (
                    final_artifacts["learned_event_model"].metadata()
                    if final_artifacts.get("learned_event_model") is not None
                    else {
                        "model_family": "learned_event_xgb",
                        "action_threshold": action_threshold,
                        "calibration_mode": calibration_mode,
                        "calibration_enabled": final_artifacts.get("calibration") is not None,
                    }
                ),
                "ensemble_component_weights": {"regional_pooled_panel": 1.0},
                "hierarchy_driver_attribution": hierarchy_metadata["hierarchy_driver_attribution"],
                "reconciliation_method": hierarchy_metadata["reconciliation_method"],
                "hierarchy_consistency_status": hierarchy_metadata["hierarchy_consistency_status"],
                "hierarchy_reconciliation": hierarchy_metadata,
                "point_in_time_snapshot": {
                    "snapshot_type": point_in_time_manifest.get("snapshot_type"),
                    "captured_at": point_in_time_manifest.get("captured_at"),
                    "unique_as_of_dates": point_in_time_manifest.get("unique_as_of_dates"),
                },
                "weather_vintage_comparison": weather_vintage_comparison_payload,
            }
            metadata["model_version"] = f"{metadata['model_family']}:h{horizon}:{metadata['trained_at']}"
            metadata["calibration_version"] = f"{calibration_mode}:h{horizon}:{metadata['trained_at']}"
            registry_scope = self.registry.load_scope(virus_typ=virus_typ, horizon_days=horizon)
            current_champion = registry_scope.get("champion") or {}
            current_champion_metrics = (current_champion.get("metrics") or {})
            current_champion_metadata = (current_champion.get("metadata") or {})
            promotion_candidate_metrics = {
                **(backtest_bundle.get("benchmark_summary") or {}).get("metrics", {}),
                **backtest_bundle["aggregate_metrics"],
            }
            oof_frame = backtest_bundle.get("oof_frame")
            candidate_sample_count = next(
                (
                    int(item.get("samples") or 0)
                    for item in ((backtest_bundle.get("benchmark_summary") or {}).get("candidate_summaries") or [])
                    if str(item.get("candidate") or "") == "regional_pooled_panel"
                ),
                int(len(oof_frame)) if oof_frame is not None else 0,
            )
            promotion_evidence = self.registry.evaluate_promotion(
                candidate_metrics=promotion_candidate_metrics,
                champion_metrics=current_champion_metrics,
                candidate_metadata={
                    "quality_gate_overall_passed": bool(backtest_bundle["quality_gate"].get("overall_passed")),
                    "metric_semantics_version": metadata["metric_semantics_version"],
                    "sample_count": candidate_sample_count,
                },
                champion_metadata=current_champion_metadata,
                minimum_sample_count=DEFAULT_PROMOTION_MIN_SAMPLE_COUNT,
            )
            promote = bool(promotion_evidence.get("promotion_allowed"))
            registry_payload = self.registry.record_evaluation(
                virus_typ=virus_typ,
                horizon_days=horizon,
                model_family="regional_pooled_panel",
                metrics=promotion_candidate_metrics,
                metadata={
                    "model_version": metadata["model_version"],
                    "calibration_version": metadata["calibration_version"],
                    "rollout_mode": metadata["rollout_mode"],
                    "metric_semantics_version": metadata["metric_semantics_version"],
                    "sample_count": candidate_sample_count,
                    "quality_gate_overall_passed": bool(backtest_bundle["quality_gate"].get("overall_passed")),
                    "promotion_evidence": promotion_evidence,
                },
                promote=promote,
            )
            metadata["promotion_evidence"] = promotion_evidence
            metadata["registry_status"] = "champion" if promote else "challenger"
            metadata["registry_scope"] = registry_payload
            backtest_bundle["backtest_payload"]["hierarchy_reconciliation"] = _json_safe(hierarchy_metadata)
            backtest_bundle["backtest_payload"]["promotion_evidence"] = _json_safe(promotion_evidence)
            if weather_vintage_comparison_payload is not None:
                backtest_bundle["backtest_payload"]["weather_vintage_comparison"] = _json_safe(
                    weather_vintage_comparison_payload
                )

            if persist:
                self._persist_artifacts(
                    model_dir=model_dir,
                    final_artifacts=final_artifacts,
                    metadata=metadata,
                    backtest_payload=backtest_bundle["backtest_payload"],
                    dataset_manifest=dataset_manifest,
                    point_in_time_manifest=point_in_time_manifest,
                )

            per_state = (backtest_bundle["backtest_payload"].get("details") or {})
            return {
                "status": "success",
                "virus_typ": virus_typ,
                "horizon_days": horizon,
                "target_window_days": _target_window_for_horizon(horizon),
                "trained": len(per_state),
                "failed": max(0, len(ALL_BUNDESLAENDER) - len(per_state)),
                "quality_gate": backtest_bundle["quality_gate"],
                "aggregate_metrics": backtest_bundle["aggregate_metrics"],
                "rollout_mode": rollout_info["rollout_mode"],
                "activation_policy": rollout_info["activation_policy"],
                "calibration_version": metadata["calibration_version"],
                "weather_forecast_vintage_mode": metadata["weather_forecast_vintage_mode"],
                "exogenous_feature_semantics_version": metadata["exogenous_feature_semantics_version"],
                "selected_calibration_mode": calibration_mode,
                "model_dir": str(model_dir),
                "benchmark_summary": backtest_bundle.get("benchmark_summary") or {},
                "hierarchy_reconciliation": hierarchy_metadata,
                "backtest": backtest_bundle["backtest_payload"],
                "weather_vintage_comparison": weather_vintage_comparison_payload,
                "selection": selection,
                "promotion_evidence": promotion_evidence,
                "registry_status": metadata["registry_status"],
            }
        except Exception as exc:
            logger.exception(
                "Training pooled regional panel model failed for %s (horizon=%s)",
                virus_typ,
                horizon,
            )
            return self._training_error_payload(
                virus_typ=virus_typ,
                horizon_days=horizon,
                exc=exc,
                lookback_days=lookback_days,
            )

    @staticmethod
    def _training_error_payload(
        *,
        virus_typ: str,
        horizon_days: int,
        exc: Exception,
        lookback_days: int,
    ) -> dict[str, Any]:
        error_message = str(exc) or exc.__class__.__name__
        hint = (
            "Der Backtest konnte keine gültigen Zeit-Folds aufbauen. Wahrscheinlich gibt es für diesen Scope "
            "zu wenig stabile Trainingsfenster oder in den Folds fehlt genug Klassenvielfalt für Training/Kalibrierung."
            if "no valid folds" in error_message.lower()
            else "Bitte Fold-Bildung, Datenmenge und Klassenverteilung für diesen Scope prüfen."
        )
        return {
            "status": "error",
            "virus_typ": virus_typ,
            "horizon_days": int(horizon_days),
            "target_window_days": _target_window_for_horizon(horizon_days),
            "lookback_days": int(lookback_days),
            "trained": 0,
            "failed": len(ALL_BUNDESLAENDER),
            "error": error_message,
            "error_type": exc.__class__.__name__,
            "error_stage": "train_single_horizon",
            "diagnostic_hint": hint,
            "traceback_tail": traceback.format_exc(limit=8).strip().splitlines()[-8:],
        }

    def train_all_viruses_all_regions(
        self,
        lookback_days: int = 900,
        horizon_days: int = 7,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        return self.train_selected_viruses_all_regions(
            virus_types=SUPPORTED_VIRUS_TYPES,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
            weather_vintage_comparison=weather_vintage_comparison,
        )

    def train_selected_viruses_all_regions(
        self,
        *,
        virus_types: list[str] | tuple[str, ...],
        lookback_days: int = 900,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
        weather_forecast_vintage_mode: str | None = None,
        weather_vintage_comparison: bool = False,
    ) -> dict[str, Any]:
        return {
            virus_typ: self.train_all_regions(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
                horizon_days=horizon_days,
                horizon_days_list=horizon_days_list,
                weather_forecast_vintage_mode=weather_forecast_vintage_mode,
                weather_vintage_comparison=weather_vintage_comparison,
            )
            for virus_typ in virus_types
        }

    @staticmethod
    def _selected_horizons(
        *,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
    ) -> tuple[int, ...]:
        if horizon_days_list is None:
            return (ensure_supported_horizon(horizon_days),)

        normalized: list[int] = []
        seen: set[int] = set()
        for value in horizon_days_list:
            horizon = ensure_supported_horizon(value)
            if horizon in seen:
                continue
            seen.add(horizon)
            normalized.append(horizon)
        if not normalized:
            raise ValueError("horizon_days_list must not be empty")
        return tuple(normalized)

    def _build_training_panel(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        horizon_days: int,
        weather_forecast_vintage_mode: str | None = None,
    ) -> pd.DataFrame:
        builder_kwargs: dict[str, Any] = {
            "virus_typ": virus_typ,
            "lookback_days": lookback_days,
            "horizon_days": horizon_days,
            "include_nowcast": True,
            "use_revision_adjusted": False,
            "revision_policy": "raw",
        }
        if weather_forecast_vintage_mode is not None:
            builder_kwargs["weather_forecast_vintage_mode"] = weather_forecast_vintage_mode
        return self.feature_builder.build_panel_training_data(**builder_kwargs)

    @staticmethod
    def _weather_vintage_metrics_delta(
        legacy_metrics: dict[str, Any],
        vintage_metrics: dict[str, Any],
    ) -> dict[str, float]:
        deltas: dict[str, float] = {}
        for key in (
            "relative_wis",
            "wis",
            "crps",
            "coverage_80",
            "coverage_95",
            "brier_score",
            "ece",
            "pr_auc",
            "decision_utility",
        ):
            if key not in legacy_metrics or key not in vintage_metrics:
                continue
            deltas[key] = round(
                float(vintage_metrics.get(key) or 0.0)
                - float(legacy_metrics.get(key) or 0.0),
                6,
            )
        return deltas

    @staticmethod
    def _weather_vintage_mode_summary(
        *,
        weather_forecast_vintage_mode: str,
        dataset_manifest: dict[str, Any],
        backtest_bundle: dict[str, Any],
        selection: dict[str, Any],
        calibration_mode: str,
    ) -> dict[str, Any]:
        return {
            "weather_forecast_vintage_mode": weather_forecast_vintage_mode,
            "exogenous_feature_semantics_version": dataset_manifest.get(
                "exogenous_feature_semantics_version"
            ),
            "aggregate_metrics": _json_safe(backtest_bundle.get("aggregate_metrics") or {}),
            "benchmark_metrics": _json_safe(
                (backtest_bundle.get("benchmark_summary") or {}).get("metrics") or {}
            ),
            "quality_gate": _json_safe(backtest_bundle.get("quality_gate") or {}),
            "selected_tau": float(selection.get("tau") or 0.0),
            "selected_kappa": float(selection.get("kappa") or 0.0),
            "action_threshold": float(selection.get("action_threshold") or 0.0),
            "calibration_mode": str(calibration_mode or "raw_passthrough"),
            "weather_forecast_run_identity_present": bool(
                dataset_manifest.get("weather_forecast_run_identity_present")
            ),
            "weather_forecast_run_identity_source": dataset_manifest.get(
                "weather_forecast_run_identity_source"
            ),
            "weather_forecast_run_identity_quality": dataset_manifest.get(
                "weather_forecast_run_identity_quality"
            ),
        }

    def _build_weather_vintage_comparison(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        horizon_days: int,
        primary_summary: dict[str, Any],
        event_config,
    ) -> dict[str, Any]:
        primary_mode = normalize_weather_forecast_vintage_mode(
            primary_summary.get("weather_forecast_vintage_mode")
        )
        alternate_mode = (
            WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1
            if primary_mode != WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1
            else WEATHER_FORECAST_VINTAGE_DISABLED
        )

        comparison: dict[str, Any] = {
            "enabled": True,
            "comparison_status": "ok",
            "comparison_basis": "regional_training_shadow_benchmark_v1",
            "active_training_mode": primary_mode,
            "shadow_mode": alternate_mode,
            "modes": {
                primary_mode: _json_safe(primary_summary)
            },
        }

        try:
            shadow_panel = self._build_training_panel(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
                horizon_days=horizon_days,
                weather_forecast_vintage_mode=alternate_mode,
            )
            shadow_panel = self._prepare_horizon_panel(shadow_panel, horizon_days=horizon_days)
            if shadow_panel.empty or len(shadow_panel) < 200:
                comparison["comparison_status"] = "degraded"
                comparison["comparison_blockers"] = ["insufficient_shadow_panel_rows"]
                return comparison

            shadow_panel = shadow_panel.copy()
            shadow_panel["y_next_log"] = np.log1p(
                shadow_panel["next_week_incidence"].astype(float).clip(lower=0.0)
            )
            shadow_feature_columns = self._feature_columns(shadow_panel)
            shadow_hierarchy_feature_columns = GeoHierarchyHelper.hierarchy_feature_columns(
                shadow_feature_columns
            )
            shadow_ww_only_columns = self._ww_only_feature_columns(shadow_feature_columns)
            shadow_selection = self._select_event_definition(
                virus_typ=virus_typ,
                panel=shadow_panel,
                feature_columns=shadow_feature_columns,
                event_config=event_config,
            )
            shadow_tau = float(shadow_selection["tau"])
            shadow_kappa = float(shadow_selection["kappa"])
            shadow_action_threshold = float(shadow_selection["action_threshold"])
            shadow_panel["event_label"] = self._event_labels(
                shadow_panel,
                virus_typ=virus_typ,
                tau=shadow_tau,
                kappa=shadow_kappa,
                event_config=event_config,
            )
            shadow_backtest_bundle = self._build_backtest_bundle(
                virus_typ=virus_typ,
                panel=shadow_panel,
                feature_columns=shadow_feature_columns,
                hierarchy_feature_columns=shadow_hierarchy_feature_columns,
                ww_only_columns=shadow_ww_only_columns,
                tau=shadow_tau,
                kappa=shadow_kappa,
                action_threshold=shadow_action_threshold,
                horizon_days=horizon_days,
                event_config=event_config,
            )
            shadow_final_artifacts = self._fit_final_models(
                panel=shadow_panel,
                feature_columns=shadow_feature_columns,
                hierarchy_feature_columns=shadow_hierarchy_feature_columns,
                oof_frame=shadow_backtest_bundle["oof_frame"],
                action_threshold=shadow_action_threshold,
            )
            shadow_dataset_manifest = {
                **self.feature_builder.dataset_manifest(virus_typ=virus_typ, panel=shadow_panel),
                "horizon_days": int(horizon_days),
                "target_window_days": _target_window_for_horizon(horizon_days),
            }
            shadow_mode = normalize_weather_forecast_vintage_mode(
                shadow_dataset_manifest.get("weather_forecast_vintage_mode")
            )
            shadow_calibration_mode = str(
                shadow_final_artifacts.get("calibration_mode")
                or (
                    "isotonic"
                    if shadow_final_artifacts.get("calibration") is not None
                    else "raw_passthrough"
                )
            )
            comparison["modes"][shadow_mode] = self._weather_vintage_mode_summary(
                weather_forecast_vintage_mode=shadow_mode,
                dataset_manifest=shadow_dataset_manifest,
                backtest_bundle=shadow_backtest_bundle,
                selection=shadow_selection,
                calibration_mode=shadow_calibration_mode,
            )
            legacy_metrics = (
                (comparison["modes"].get(WEATHER_FORECAST_VINTAGE_DISABLED) or {}).get("benchmark_metrics")
                or {}
            )
            vintage_metrics = (
                (comparison["modes"].get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1) or {}).get("benchmark_metrics")
                or {}
            )
            comparison["legacy_vs_vintage_metric_delta"] = self._weather_vintage_metrics_delta(
                legacy_metrics,
                vintage_metrics,
            )
            legacy_mode_payload = comparison["modes"].get(WEATHER_FORECAST_VINTAGE_DISABLED) or {}
            vintage_mode_payload = comparison["modes"].get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1) or {}
            comparison["quality_gate_change"] = {
                "legacy_forecast_readiness": ((legacy_mode_payload.get("quality_gate") or {}).get("forecast_readiness")),
                "vintage_forecast_readiness": ((vintage_mode_payload.get("quality_gate") or {}).get("forecast_readiness")),
                "overall_passed_changed": bool(
                    ((legacy_mode_payload.get("quality_gate") or {}).get("overall_passed"))
                    != ((vintage_mode_payload.get("quality_gate") or {}).get("overall_passed"))
                ),
            }
            comparison["threshold_change"] = round(
                float(vintage_mode_payload.get("action_threshold") or 0.0)
                - float(legacy_mode_payload.get("action_threshold") or 0.0),
                6,
            )
            comparison["calibration_change"] = {
                "legacy": legacy_mode_payload.get("calibration_mode"),
                "vintage": vintage_mode_payload.get("calibration_mode"),
                "changed": str(legacy_mode_payload.get("calibration_mode") or "")
                != str(vintage_mode_payload.get("calibration_mode") or ""),
            }
            comparison["weather_vintage_run_identity_coverage"] = {
                mode: {
                    "run_identity_present": bool(
                        (payload or {}).get("weather_forecast_run_identity_present")
                    ),
                    "coverage_ratio": (
                        1.0 if bool((payload or {}).get("weather_forecast_run_identity_present")) else 0.0
                    ),
                }
                for mode, payload in comparison["modes"].items()
            }
            return comparison
        except Exception as exc:
            comparison["comparison_status"] = "error"
            comparison["comparison_error"] = str(exc) or exc.__class__.__name__
            return comparison

    @staticmethod
    def _prepare_horizon_panel(
        panel: pd.DataFrame,
        *,
        horizon_days: int,
    ) -> pd.DataFrame:
        horizon = ensure_supported_horizon(horizon_days)
        if panel.empty:
            return panel.copy()

        working = panel.copy()
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        if "target_date" not in working.columns:
            working["target_date"] = working["as_of_date"] + pd.Timedelta(days=horizon)
        working["target_date"] = pd.to_datetime(working["target_date"]).dt.normalize()
        working["target_window_days"] = [_target_window_for_horizon(horizon)] * len(working)
        working["horizon_days"] = float(horizon)

        future_targets = working[
            ["bundesland", "as_of_date", "current_known_incidence", "truth_source"]
        ].rename(
            columns={
                "as_of_date": "target_date",
                "current_known_incidence": "target_incidence",
                "truth_source": "target_truth_source",
            }
        )
        merged = working.merge(
            future_targets,
            on=["bundesland", "target_date"],
            how="left",
        )
        merged["next_week_incidence"] = merged["target_incidence"]
        merged["truth_source"] = merged["target_truth_source"].fillna(merged["truth_source"])
        merged = merged.loc[merged["target_incidence"].notna()].copy()
        return merged.reset_index(drop=True)

    @staticmethod
    def _state_order_from_panel(panel: pd.DataFrame) -> list[str]:
        present = {str(value) for value in panel.get("bundesland", pd.Series(dtype=str)).dropna().astype(str).tolist()}
        ordered = [state for state in ALL_BUNDESLAENDER if state in present]
        if ordered:
            return ordered
        return sorted(present)

    def _build_hierarchy_metadata(
        self,
        *,
        panel: pd.DataFrame,
        oof_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        state_order = self._state_order_from_panel(panel)
        if not state_order:
            return {
                "enabled": False,
                "reconciliation_method": "not_available",
                "hierarchy_consistency_status": "empty",
                "max_coherence_gap": 0.0,
                "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
                "cluster_assignments": {},
                "cluster_order": [],
                "state_order": [],
                "state_residual_history": [],
            }

        cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
            panel,
            state_col="bundesland",
            value_col="current_known_incidence",
            date_col="as_of_date",
        )
        state_weight_map: dict[str, float] = {}
        if {"bundesland", "state_population_millions"}.issubset(panel.columns):
            weights = (
                panel.dropna(subset=["bundesland"])
                .groupby("bundesland")["state_population_millions"]
                .median()
                .to_dict()
            )
            state_weight_map = {str(key): float(value) for key, value in weights.items() if pd.notna(value)}

        residual_history: list[list[float]] = []
        if not oof_frame.empty and {"as_of_date", "bundesland", "residual"}.issubset(oof_frame.columns):
            residual_matrix = (
                oof_frame.assign(as_of_date=pd.to_datetime(oof_frame["as_of_date"]).dt.normalize())
                .pivot_table(
                    index="as_of_date",
                    columns="bundesland",
                    values="residual",
                    aggfunc="mean",
                )
                .reindex(columns=state_order)
                .fillna(0.0)
                .tail(180)
            )
            residual_history = residual_matrix.to_numpy(dtype=float).tolist()

        reconciliation_summary: dict[str, Any] = {
            "reconciliation_method": "not_available",
            "hierarchy_consistency_status": "not_checked",
            "max_coherence_gap": 0.0,
            "hierarchy_driver_attribution": {"state": 1.0, "cluster": 0.0, "national": 0.0},
            "cluster_order": sorted({value for value in cluster_assignments.values()}),
        }
        if not oof_frame.empty and {"bundesland", "prediction_interval_lower", "expected_target_incidence", "prediction_interval_upper"}.issubset(oof_frame.columns):
            latest_state_rows = (
                oof_frame.assign(as_of_date=pd.to_datetime(oof_frame["as_of_date"]).dt.normalize())
                .sort_values("as_of_date")
                .groupby("bundesland", as_index=False)
                .tail(1)
            )
            latest_by_state = latest_state_rows.set_index("bundesland")
            available_states = [state for state in state_order if state in latest_by_state.index]
            if available_states:
                state_quantiles = {
                    0.1: np.asarray([float(latest_by_state.at[state, "prediction_interval_lower"]) for state in available_states], dtype=float),
                    0.5: np.asarray([float(latest_by_state.at[state, "expected_target_incidence"]) for state in available_states], dtype=float),
                    0.9: np.asarray([float(latest_by_state.at[state, "prediction_interval_upper"]) for state in available_states], dtype=float),
                }
                _, reconciliation_summary = GeoHierarchyHelper.reconcile_quantiles(
                    state_quantiles,
                    cluster_assignments={state: cluster_assignments[state] for state in available_states if state in cluster_assignments},
                    state_order=available_states,
                    residual_history=np.asarray(residual_history, dtype=float) if residual_history else None,
                    state_weights={state: state_weight_map.get(state, 1.0) for state in available_states},
                )

        return {
            "enabled": True,
            "aggregate_input_strategy": "weighted_feature_pool_same_model",
            "model_sources": {
                "state": "regional_pooled_panel",
                "cluster": "regional_cluster_aggregate",
                "national": "regional_national_aggregate",
            },
            "reconciliation_method": reconciliation_summary["reconciliation_method"],
            "hierarchy_consistency_status": reconciliation_summary["hierarchy_consistency_status"],
            "max_coherence_gap": reconciliation_summary["max_coherence_gap"],
            "hierarchy_driver_attribution": {
                "state": float(reconciliation_summary.get("state", 1.0)),
                "cluster": float(reconciliation_summary.get("cluster", 0.0)),
                "national": float(reconciliation_summary.get("national", 0.0)),
            },
            "cluster_assignments": cluster_assignments,
            "cluster_order": reconciliation_summary.get("cluster_order") or sorted({value for value in cluster_assignments.values()}),
            "state_order": state_order,
            "state_weights": state_weight_map,
            "state_residual_history": residual_history,
        }

    def get_regional_accuracy_summary(
        self,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
    ) -> list[dict]:
        artifact = self.load_artifacts(virus_typ=virus_typ, horizon_days=horizon_days)
        backtest = artifact.get("backtest") or {}
        details = backtest.get("details") or {}
        summaries: list[dict] = []
        for code, payload in sorted(details.items()):
            metrics = payload.get("metrics") or {}
            summaries.append(
                {
                    "bundesland": code,
                    "name": payload.get("bundesland_name", BUNDESLAND_NAMES.get(code, code)),
                    "horizon_days": int((artifact.get("metadata") or {}).get("horizon_days") or horizon_days),
                    "samples": int(payload.get("total_windows") or 0),
                    "precision": metrics.get("precision"),
                    "recall": metrics.get("recall"),
                    "pr_auc": metrics.get("pr_auc"),
                    "brier_score": metrics.get("brier_score"),
                    "trained_at": (artifact.get("metadata") or {}).get("trained_at"),
                }
            )
        return summaries

    def load_artifacts(self, virus_typ: str, horizon_days: int = 7) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        model_dir = regional_model_artifact_dir(
            self.models_dir,
            virus_typ=virus_typ,
            horizon_days=horizon,
        )
        if model_dir.exists() and not self._artifact_payload_from_dir(model_dir):
            return {
                "load_error": (
                    f"Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig."
                )
            }
        payload = self._artifact_payload_from_dir(model_dir)
        if payload:
            metadata = payload.setdefault("metadata", {})
            metadata.setdefault("horizon_days", horizon)
            metadata.setdefault("target_window_days", _target_window_for_horizon(horizon))
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

        if horizon != 7:
            return {}

        legacy_dir = self.models_dir / _virus_slug(virus_typ)
        if legacy_dir.exists() and not self._artifact_payload_from_dir(legacy_dir):
            return {
                "load_error": (
                    f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig."
                )
            }
        legacy_payload = self._artifact_payload_from_dir(legacy_dir)
        if not legacy_payload:
            return {}

        metadata = dict(legacy_payload.get("metadata") or {})
        metadata.setdefault("horizon_days", horizon)
        metadata["target_window_days"] = metadata.get("target_window_days") or list(TARGET_WINDOW_DAYS)
        metadata["artifact_transition_mode"] = "legacy_default_window_fallback"
        metadata["requested_horizon_days"] = horizon
        metadata["artifact_dir"] = str(legacy_dir)
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
    def _artifact_payload_from_dir(model_dir: Path) -> dict[str, Any]:
        if not model_dir.exists():
            return {}
        payload: dict[str, Any] = {}
        meta_path = model_dir / "metadata.json"
        backtest_path = model_dir / "backtest.json"
        point_in_time_path = model_dir / "point_in_time_snapshot.json"
        if meta_path.exists():
            payload["metadata"] = json.loads(meta_path.read_text())
        if backtest_path.exists():
            payload["backtest"] = json.loads(backtest_path.read_text())
        if point_in_time_path.exists():
            payload["point_in_time_snapshot"] = json.loads(point_in_time_path.read_text())
        return payload

    def _feature_columns(self, panel: pd.DataFrame) -> list[str]:
        columns = [
            column
            for column in panel.columns
            if column not in EXCLUDED_MODEL_COLUMNS and column != "pollen_context_score"
        ]
        return sorted(columns)

    @staticmethod
    def _ww_only_feature_columns(feature_columns: list[str]) -> list[str]:
        return [
            column
            for column in feature_columns
            if column.startswith("ww_")
            or column in {
                "neighbor_ww_level",
                "neighbor_ww_slope7d",
                "national_ww_level",
                "national_ww_slope7d",
                "national_ww_acceleration7d",
            }
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

    def _rollout_metadata(
        self,
        *,
        virus_typ: str,
        horizon_days: int = 7,
        aggregate_metrics: dict[str, Any],
        baseline_metrics: dict[str, dict[str, Any]],
        previous_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        rollout_mode = rollout_mode_for_virus(virus_typ, horizon_days=horizon_days)
        activation_policy = activation_policy_for_virus(virus_typ, horizon_days=horizon_days)
        signal_bundle_version = signal_bundle_version_for_virus(virus_typ)
        if virus_typ != "SARS-CoV-2":
            return {
                "signal_bundle_version": signal_bundle_version,
                "rollout_mode": rollout_mode,
                "activation_policy": activation_policy,
            }

        previous_metadata = previous_artifact.get("metadata") or {}
        previous_metrics = previous_metadata.get("aggregate_metrics") or {}
        persistence_metrics = (baseline_metrics.get("persistence") or {}).copy()
        checks = {
            "beats_previous_precision_at_top3": (
                float(aggregate_metrics.get("precision_at_top3") or 0.0)
                > float(previous_metrics.get("precision_at_top3") or 0.0)
            ),
            "beats_previous_pr_auc": (
                float(aggregate_metrics.get("pr_auc") or 0.0)
                > float(previous_metrics.get("pr_auc") or 0.0)
            ),
            "improves_previous_activation_fp_rate": (
                float(aggregate_metrics.get("activation_false_positive_rate") or 1.0)
                < float(previous_metrics.get("activation_false_positive_rate") or 1.0)
            ),
            "beats_persistence_precision_at_top3": (
                float(aggregate_metrics.get("precision_at_top3") or 0.0)
                >= float(persistence_metrics.get("precision_at_top3") or 0.0)
            ),
            "beats_persistence_pr_auc": (
                float(aggregate_metrics.get("pr_auc") or 0.0)
                >= float(persistence_metrics.get("pr_auc") or 0.0)
            ),
        }
        has_previous_candidate = bool(previous_metrics)
        overall_passed = has_previous_candidate and all(checks.values())
        return {
            "signal_bundle_version": signal_bundle_version,
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "shadow_promotion_candidate": bool(int(horizon_days) == 7),
            "shadow_evaluation": {
                "overall_passed": overall_passed,
                "has_previous_candidate": has_previous_candidate,
                "checks": checks,
                "previous_candidate_metrics": previous_metrics,
                "persistence_metrics": persistence_metrics,
                "candidate_metrics": aggregate_metrics,
            },
        }

    @staticmethod
    def _event_labels(
        panel: pd.DataFrame,
        *,
        virus_typ: str,
        tau: float,
        kappa: float,
        event_config=None,
    ) -> np.ndarray:
        config = event_config or event_definition_config_for_virus(virus_typ)
        return np.asarray(
            [
                build_event_label(
                    current_known_incidence=row.current_known_incidence,
                    next_week_incidence=row.next_week_incidence,
                    seasonal_baseline=row.seasonal_baseline,
                    seasonal_mad=row.seasonal_mad,
                    tau=tau,
                    kappa=kappa,
                    min_absolute_incidence=config.min_absolute_incidence,
                )
                for row in panel.itertuples()
            ],
            dtype=int,
        )

    def _select_event_definition(
        self,
        *,
        virus_typ: str,
        panel: pd.DataFrame,
        feature_columns: list[str],
        event_config=None,
    ) -> dict[str, Any]:
        config = event_config or event_definition_config_for_virus(virus_typ)
        best: dict[str, Any] | None = None

        for tau in config.tau_grid:
            for kappa in config.kappa_grid:
                labels = self._event_labels(
                    panel,
                    virus_typ=virus_typ,
                    tau=tau,
                    kappa=kappa,
                    event_config=config,
                )
                if labels.sum() < 12:
                    continue
                evaluation = self._oof_classification_predictions(
                    panel=panel,
                    labels=labels,
                    feature_columns=feature_columns,
                    min_recall_for_threshold=config.min_recall_for_selection,
                )
                if evaluation is None:
                    continue
                threshold, precision, recall = choose_action_threshold(
                    evaluation["event_probability_calibrated"],
                    evaluation["event_label"],
                    min_recall=config.min_recall_for_selection,
                )
                candidate = {
                    "tau": tau,
                    "kappa": kappa,
                    "action_threshold": threshold,
                    "precision": precision,
                    "recall": recall,
                    "pr_auc": average_precision_safe(
                        evaluation["event_label"],
                        evaluation["event_probability_calibrated"],
                    ),
                    "positive_rate": float(np.mean(labels)),
                }
                if best is None:
                    best = candidate
                    continue
                if candidate["precision"] > best["precision"]:
                    best = candidate
                elif np.isclose(candidate["precision"], best["precision"]):
                    if candidate["pr_auc"] > best["pr_auc"] or (
                        np.isclose(candidate["pr_auc"], best["pr_auc"]) and candidate["recall"] > best["recall"]
                    ):
                        best = candidate

        if best is None:
            best = {
                "tau": float(config.tau_grid[min(len(config.tau_grid) // 2, len(config.tau_grid) - 1)]),
                "kappa": float(config.kappa_grid[min(len(config.kappa_grid) // 2, len(config.kappa_grid) - 1)]),
                "action_threshold": 0.6,
                "precision": 0.0,
                "recall": 0.0,
                "pr_auc": 0.0,
                "positive_rate": 0.0,
            }
        return best

    def _oof_classification_predictions(
        self,
        *,
        panel: pd.DataFrame,
        labels: np.ndarray,
        feature_columns: list[str],
        min_recall_for_threshold: float = 0.35,
    ) -> pd.DataFrame | None:
        working = panel.copy()
        working["event_label"] = labels.astype(int)
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        splits = time_based_panel_splits(
            working["as_of_date"],
            n_splits=5,
            min_train_periods=90,
            min_test_periods=21,
        )
        if not splits:
            return None

        oof_frames: list[pd.DataFrame] = []
        for fold_idx, (train_dates, test_dates) in enumerate(splits):
            train_mask = working["as_of_date"].isin(train_dates)
            test_mask = working["as_of_date"].isin(test_dates)
            train_df = working.loc[train_mask].copy()
            test_df = working.loc[test_mask].copy()
            if train_df.empty or test_df.empty or train_df["event_label"].nunique() < 2:
                continue

            calib_split = self._calibration_split_dates(train_dates)
            if not calib_split:
                continue
            model_train_dates, cal_dates = calib_split
            model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
            cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
            if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
                continue

            classifier = self._fit_classifier_from_frame(model_train_df, feature_columns)
            calibration, _calibration_mode = self._select_guarded_calibration(
                calibration_frame=pd.DataFrame(
                    {
                        "as_of_date": cal_df["as_of_date"].values,
                        "event_label": cal_df["event_label"].values.astype(int),
                        "event_probability_raw": classifier.predict_proba(
                            cal_df[feature_columns].to_numpy()
                        )[:, 1],
                    }
                ),
                raw_probability_col="event_probability_raw",
                min_recall_for_threshold=min_recall_for_threshold,
            )
            raw_probs = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
            calibrated_probs = self._apply_calibration(calibration, raw_probs)

            oof_frames.append(
                pd.DataFrame(
                    {
                        "fold": fold_idx,
                        "as_of_date": test_df["as_of_date"].values,
                        "event_label": test_df["event_label"].values,
                        "event_probability_calibrated": calibrated_probs,
                    }
                )
            )

        if not oof_frames:
            return None
        return pd.concat(oof_frames, ignore_index=True)

    def _build_backtest_bundle(
        self,
        *,
        virus_typ: str,
        panel: pd.DataFrame,
        feature_columns: list[str],
        hierarchy_feature_columns: list[str],
        ww_only_columns: list[str],
        tau: float,
        kappa: float,
        action_threshold: float,
        horizon_days: int = 7,
        event_config=None,
    ) -> dict[str, Any]:
        return regional_trainer_backtest.build_backtest_bundle(
            self,
            virus_typ=virus_typ,
            panel=panel,
            feature_columns=feature_columns,
            hierarchy_feature_columns=hierarchy_feature_columns,
            ww_only_columns=ww_only_columns,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            horizon_days=horizon_days,
            event_config=event_config,
            time_based_panel_splits_fn=time_based_panel_splits,
            quality_gate_from_metrics_fn=quality_gate_from_metrics,
        )

    def _hierarchy_reconciled_benchmark_frame(
        self,
        *,
        oof_frame: pd.DataFrame,
        source_panel: pd.DataFrame,
    ) -> pd.DataFrame:
        required = {
            "as_of_date",
            "bundesland",
            "bundesland_name",
            "virus_typ",
            "horizon_days",
            "event_label",
            "event_probability_calibrated",
            "next_week_incidence",
            "expected_target_incidence",
            "prediction_interval_lower",
            "prediction_interval_upper",
        }
        if oof_frame.empty or not required.issubset(oof_frame.columns):
            return pd.DataFrame()

        working_panel = source_panel.copy()
        working_panel["as_of_date"] = pd.to_datetime(working_panel["as_of_date"]).dt.normalize()
        working_oof = oof_frame.copy()
        working_oof["as_of_date"] = pd.to_datetime(working_oof["as_of_date"]).dt.normalize()
        records: list[dict[str, Any]] = []
        historical_residual_rows: list[dict[str, float]] = []
        historical_cluster_rows: list[dict[str, float]] = []
        historical_national_rows: list[dict[str, float]] = []

        for as_of_date in sorted(working_oof["as_of_date"].dropna().unique()):
            date_value = pd.Timestamp(as_of_date).normalize()
            date_frame = working_oof.loc[working_oof["as_of_date"] == date_value].copy()
            target_regime = GeoHierarchyHelper.season_regime(date_value)
            state_order = _state_order_from_codes(date_frame["bundesland"].astype(str).tolist())
            if not state_order:
                continue
            date_frame = date_frame.drop_duplicates(subset=["bundesland"], keep="last").set_index("bundesland")
            available_states = [state for state in state_order if state in date_frame.index]
            if not available_states:
                continue
            target_horizon_days = (
                int(date_frame["horizon_days"].dropna().iloc[-1])
                if "horizon_days" in date_frame.columns and date_frame["horizon_days"].notna().any()
                else None
            )
            state_quantiles = {
                0.1: np.asarray([float(date_frame.at[state, "prediction_interval_lower"]) for state in available_states], dtype=float),
                0.5: np.asarray([float(date_frame.at[state, "expected_target_incidence"]) for state in available_states], dtype=float),
                0.9: np.asarray([float(date_frame.at[state, "prediction_interval_upper"]) for state in available_states], dtype=float),
            }
            panel_until_date = working_panel.loc[working_panel["as_of_date"] <= date_value].copy()
            cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
                panel_until_date,
                state_col="bundesland",
                value_col="current_known_incidence",
                date_col="as_of_date",
            )
            cluster_order = []
            seen_clusters: set[str] = set()
            for state in available_states:
                cluster_id = str(cluster_assignments.get(state) or "")
                if not cluster_id or cluster_id in seen_clusters:
                    continue
                seen_clusters.add(cluster_id)
                cluster_order.append(cluster_id)
            state_weights = {}
            date_panel = panel_until_date.loc[panel_until_date["bundesland"].isin(available_states)].copy()
            if {"bundesland", "state_population_millions"}.issubset(date_panel.columns):
                latest_weights = (
                    date_panel.sort_values("as_of_date")
                    .groupby("bundesland", as_index=False)
                    .tail(1)
                    .set_index("bundesland")["state_population_millions"]
                    .to_dict()
                )
                state_weights = {str(key): float(value) for key, value in latest_weights.items() if pd.notna(value)}
            residual_history = None
            if historical_residual_rows:
                residual_history = np.asarray(
                    [
                        [float(row.get(state, 0.0)) for state in available_states]
                        for row in historical_residual_rows
                    ],
                    dtype=float,
                )
            derived_cluster_quantiles = {
                quantile: GeoHierarchyHelper._aggregate_states(
                    np.asarray(values, dtype=float),
                    state_order=available_states,
                    cluster_assignments={state: cluster_assignments[state] for state in available_states if state in cluster_assignments},
                    cluster_order=cluster_order,
                    state_weights=state_weights,
                )[0]
                for quantile, values in state_quantiles.items()
            }
            derived_national_quantiles = {
                quantile: GeoHierarchyHelper._aggregate_states(
                    np.asarray(values, dtype=float),
                    state_order=available_states,
                    cluster_assignments={state: cluster_assignments[state] for state in available_states if state in cluster_assignments},
                    cluster_order=cluster_order,
                    state_weights=state_weights,
                )[1]
                for quantile, values in state_quantiles.items()
            }
            model_cluster_quantiles = None
            if cluster_order and "cluster_id" in date_frame.columns and date_frame["cluster_id"].notna().any():
                model_cluster_quantiles = {
                    0.1: np.asarray(
                        [float(date_frame.loc[date_frame["cluster_id"] == cluster_id, "cluster_prediction_interval_lower"].iloc[-1]) for cluster_id in cluster_order],
                        dtype=float,
                    ),
                    0.5: np.asarray(
                        [float(date_frame.loc[date_frame["cluster_id"] == cluster_id, "cluster_expected_target_incidence"].iloc[-1]) for cluster_id in cluster_order],
                        dtype=float,
                    ),
                    0.9: np.asarray(
                        [float(date_frame.loc[date_frame["cluster_id"] == cluster_id, "cluster_prediction_interval_upper"].iloc[-1]) for cluster_id in cluster_order],
                        dtype=float,
                    ),
                }
            model_national_quantiles = None
            if "national_expected_target_incidence" in date_frame.columns and date_frame["national_expected_target_incidence"].notna().any():
                model_national_quantiles = {
                    0.1: np.asarray([float(date_frame["national_prediction_interval_lower"].dropna().iloc[-1])], dtype=float),
                    0.5: np.asarray([float(date_frame["national_expected_target_incidence"].dropna().iloc[-1])], dtype=float),
                    0.9: np.asarray([float(date_frame["national_prediction_interval_upper"].dropna().iloc[-1])], dtype=float),
                }
            cluster_blend_choice = self._estimate_hierarchy_blend_choice(
                historical_cluster_rows,
                target_as_of_date=date_value,
                target_regime=target_regime,
                target_horizon_days=target_horizon_days,
            )
            national_blend_choice = self._estimate_hierarchy_blend_choice(
                historical_national_rows,
                target_as_of_date=date_value,
                target_regime=target_regime,
                target_horizon_days=target_horizon_days,
            )
            cluster_blend_weight = float(cluster_blend_choice.get("weight") or 0.0)
            national_blend_weight = float(national_blend_choice.get("weight") or 0.0)
            cluster_quantiles = self._blend_hierarchy_quantiles(
                model_quantiles=model_cluster_quantiles,
                baseline_quantiles=derived_cluster_quantiles,
                blend_weight=cluster_blend_weight,
            )
            national_quantiles = self._blend_hierarchy_quantiles(
                model_quantiles=model_national_quantiles,
                baseline_quantiles=derived_national_quantiles,
                blend_weight=national_blend_weight,
            )
            if cluster_blend_weight <= 0.0 and national_blend_weight <= 0.0:
                reconciled_quantiles = {
                    float(quantile): np.asarray(values, dtype=float)
                    for quantile, values in state_quantiles.items()
                }
                reconciled_meta = {
                    "reconciliation_method": "state_sum_passthrough",
                    "hierarchy_consistency_status": "coherent",
                }
            else:
                reconciled_quantiles, reconciled_meta = GeoHierarchyHelper.reconcile_quantiles(
                    state_quantiles,
                    cluster_assignments={state: cluster_assignments[state] for state in available_states if state in cluster_assignments},
                    state_order=available_states,
                    cluster_quantiles=cluster_quantiles,
                    national_quantiles=national_quantiles,
                    residual_history=residual_history,
                    state_weights=state_weights,
                )
            for idx, state in enumerate(available_states):
                row = date_frame.loc[state]
                expected_target = float(reconciled_quantiles[0.5][idx])
                lower = float(reconciled_quantiles[0.1][idx])
                upper = float(reconciled_quantiles[0.9][idx])
                y_true = float(row["next_week_incidence"])
                records.append(
                    {
                        "fold": row.get("fold"),
                        "candidate": "regional_pooled_panel_mint",
                        "virus_typ": row["virus_typ"],
                        "bundesland": state,
                        "bundesland_name": row["bundesland_name"],
                        "as_of_date": date_value,
                        "target_date": row.get("target_date"),
                        "target_week_start": row.get("target_week_start"),
                        "horizon_days": int(row["horizon_days"]),
                        "event_label": int(row["event_label"]),
                        "event_probability": float(row["event_probability_calibrated"]),
                        "y_true": y_true,
                        "q_0.1": lower,
                        "q_0.5": expected_target,
                        "q_0.9": upper,
                        "expected_target_incidence": expected_target,
                        "prediction_interval_lower": lower,
                        "prediction_interval_upper": upper,
                        "residual": y_true - expected_target,
                        "absolute_error": abs(y_true - expected_target),
                        "season_regime": target_regime,
                        "reconciliation_method": reconciled_meta.get("reconciliation_method"),
                        "hierarchy_consistency_status": reconciled_meta.get("hierarchy_consistency_status"),
                        "cluster_blend_weight": cluster_blend_weight,
                        "national_blend_weight": national_blend_weight,
                        "cluster_blend_scope": cluster_blend_choice.get("scope"),
                        "national_blend_scope": national_blend_choice.get("scope"),
                    }
                )
            residual_row: dict[str, float] = {}
            for idx, state in enumerate(available_states):
                y_true = float(date_frame.at[state, "next_week_incidence"])
                pred = float(reconciled_quantiles[0.5][idx])
                residual_row[state] = y_true - pred
            historical_residual_rows.append(residual_row)
            if cluster_order:
                cluster_truth = []
                for cluster_id in cluster_order:
                    members = [state for state in available_states if cluster_assignments.get(state) == cluster_id]
                    member_weights = np.asarray([float(state_weights.get(state, 1.0)) for state in members], dtype=float)
                    member_truth = np.asarray([float(date_frame.at[state, "next_week_incidence"]) for state in members], dtype=float)
                    cluster_truth.append(float(np.average(member_truth, weights=member_weights)) if len(member_truth) else 0.0)
                for idx, truth_value in enumerate(cluster_truth):
                    historical_cluster_rows.append(
                        {
                            "fold": date_frame["fold"].dropna().iloc[-1] if "fold" in date_frame.columns and date_frame["fold"].notna().any() else None,
                            "as_of_date": date_value,
                            "horizon_days": target_horizon_days,
                            "regime": target_regime,
                            "model": float(model_cluster_quantiles[0.5][idx]) if model_cluster_quantiles is not None else np.nan,
                            "baseline": float(derived_cluster_quantiles[0.5][idx]),
                            "truth": float(truth_value),
                            "model_q_0.1": float(model_cluster_quantiles[0.1][idx]) if model_cluster_quantiles is not None else np.nan,
                            "model_q_0.5": float(model_cluster_quantiles[0.5][idx]) if model_cluster_quantiles is not None else np.nan,
                            "model_q_0.9": float(model_cluster_quantiles[0.9][idx]) if model_cluster_quantiles is not None else np.nan,
                            "baseline_q_0.1": float(derived_cluster_quantiles[0.1][idx]),
                            "baseline_q_0.5": float(derived_cluster_quantiles[0.5][idx]),
                            "baseline_q_0.9": float(derived_cluster_quantiles[0.9][idx]),
                        }
                    )
            historical_national_rows.append(
                {
                    "fold": date_frame["fold"].dropna().iloc[-1] if "fold" in date_frame.columns and date_frame["fold"].notna().any() else None,
                    "as_of_date": date_value,
                    "horizon_days": target_horizon_days,
                    "regime": target_regime,
                    "model": float(model_national_quantiles[0.5][0]) if model_national_quantiles is not None else np.nan,
                    "baseline": float(derived_national_quantiles[0.5][0]),
                    "truth": float(
                        np.average(
                            np.asarray([float(date_frame.at[state, "next_week_incidence"]) for state in available_states], dtype=float),
                            weights=np.asarray([float(state_weights.get(state, 1.0)) for state in available_states], dtype=float),
                        )
                    ),
                    "model_q_0.1": float(model_national_quantiles[0.1][0]) if model_national_quantiles is not None else np.nan,
                    "model_q_0.5": float(model_national_quantiles[0.5][0]) if model_national_quantiles is not None else np.nan,
                    "model_q_0.9": float(model_national_quantiles[0.9][0]) if model_national_quantiles is not None else np.nan,
                    "baseline_q_0.1": float(derived_national_quantiles[0.1][0]),
                    "baseline_q_0.5": float(derived_national_quantiles[0.5][0]),
                    "baseline_q_0.9": float(derived_national_quantiles[0.9][0]),
                }
            )

        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)

    @staticmethod
    def _prepare_hierarchy_history_frame(
        history_rows: list[dict[str, Any]],
    ) -> pd.DataFrame:
        if not history_rows:
            return pd.DataFrame()
        history = pd.DataFrame(history_rows).replace([np.inf, -np.inf], np.nan).copy()
        required_baseline = {"baseline_q_0.1", "baseline_q_0.5", "baseline_q_0.9", "truth"}
        if history.empty or not required_baseline.issubset(history.columns):
            return pd.DataFrame()
        if "as_of_date" in history.columns:
            history["as_of_date"] = pd.to_datetime(history["as_of_date"], errors="coerce").dt.normalize()
        if "regime" not in history.columns and "as_of_date" in history.columns:
            history["regime"] = history["as_of_date"].apply(GeoHierarchyHelper.season_regime)
        history["horizon_days"] = pd.to_numeric(
            history.get("horizon_days"),
            errors="coerce",
        )
        return history.dropna(subset=["truth", "baseline_q_0.1", "baseline_q_0.5", "baseline_q_0.9"]).copy()

    @staticmethod
    def _quantile_blend_metrics(
        history: pd.DataFrame,
        *,
        blend_weight: float,
    ) -> dict[str, float]:
        if history.empty:
            return {"wis": float("inf"), "crps": float("inf")}
        baseline_quantiles = {
            0.1: history["baseline_q_0.1"].to_numpy(dtype=float),
            0.5: history["baseline_q_0.5"].to_numpy(dtype=float),
            0.9: history["baseline_q_0.9"].to_numpy(dtype=float),
        }
        if blend_weight <= 0.0:
            blended_quantiles = baseline_quantiles
        else:
            blended_quantiles = {}
            for quantile in (0.1, 0.5, 0.9):
                baseline = history[f"baseline_q_{quantile}"].to_numpy(dtype=float)
                model_series = history.get(f"model_q_{quantile}")
                if model_series is None:
                    model = baseline
                else:
                    model = (
                        pd.to_numeric(model_series, errors="coerce")
                        .fillna(pd.Series(baseline, index=history.index))
                        .to_numpy(dtype=float)
                    )
                blended_quantiles[quantile] = (blend_weight * model) + ((1.0 - blend_weight) * baseline)
        metrics = summarize_probabilistic_metrics(
            y_true=history["truth"].to_numpy(dtype=float),
            quantile_predictions=blended_quantiles,
        )
        return {
            "wis": float(metrics.get("wis") or float("inf")),
            "crps": float(metrics.get("crps") or float("inf")),
            "coverage_80": float(metrics.get("coverage_80") or 0.0),
        }

    @staticmethod
    def _blend_weight_improves(
        *,
        baseline_metrics: dict[str, float],
        candidate_metrics: dict[str, float],
    ) -> bool:
        baseline_wis = float(baseline_metrics.get("wis") or float("inf"))
        baseline_crps = float(baseline_metrics.get("crps") or float("inf"))
        candidate_wis = float(candidate_metrics.get("wis") or float("inf"))
        candidate_crps = float(candidate_metrics.get("crps") or float("inf"))
        if candidate_wis < baseline_wis - HIERARCHY_BLEND_EPSILON and candidate_crps <= baseline_crps + HIERARCHY_BLEND_EPSILON:
            return True
        if abs(candidate_wis - baseline_wis) <= HIERARCHY_BLEND_EPSILON and candidate_crps < baseline_crps - HIERARCHY_BLEND_EPSILON:
            return True
        return False

    def _estimate_hierarchy_blend_choice(
        self,
        history_rows: list[dict[str, Any]],
        *,
        target_as_of_date: pd.Timestamp | None = None,
        target_regime: str | None = None,
        target_horizon_days: int | None = None,
        min_total_samples: int = HIERARCHY_BLEND_MIN_TOTAL_SAMPLES,
        min_regime_samples: int = HIERARCHY_BLEND_MIN_REGIME_SAMPLES,
    ) -> dict[str, Any]:
        history = self._prepare_hierarchy_history_frame(history_rows)
        if history.empty:
            return {
                "weight": 0.0,
                "scope": "insufficient_history",
                "samples": 0,
                "regime": target_regime,
                "horizon_days": target_horizon_days,
            }

        if target_as_of_date is not None and "as_of_date" in history.columns:
            history = history.loc[history["as_of_date"] < pd.Timestamp(target_as_of_date).normalize()].copy()
        if history.empty:
            return {
                "weight": 0.0,
                "scope": "insufficient_history",
                "samples": 0,
                "regime": target_regime,
                "horizon_days": target_horizon_days,
            }

        if target_horizon_days is not None and "horizon_days" in history.columns and history["horizon_days"].notna().any():
            horizon_history = history.loc[history["horizon_days"] == float(target_horizon_days)].copy()
            if not horizon_history.empty:
                history = horizon_history

        selected = history
        scope = "all_history"
        minimum_required = int(min_total_samples)
        if target_regime:
            regime_history = history.loc[history.get("regime") == str(target_regime)].copy()
            if len(regime_history) >= int(min_regime_samples):
                selected = regime_history
                scope = "same_regime"
                minimum_required = int(min_regime_samples)
            else:
                scope = "horizon_fallback"

        if len(selected) < minimum_required:
            return {
                "weight": 0.0,
                "scope": "insufficient_history",
                "samples": int(len(selected)),
                "regime": target_regime,
                "horizon_days": target_horizon_days,
            }

        baseline_metrics = self._quantile_blend_metrics(selected, blend_weight=0.0)
        candidate_rows: list[dict[str, Any]] = []
        for weight in HIERARCHY_BLEND_WEIGHT_GRID:
            metrics = self._quantile_blend_metrics(selected, blend_weight=float(weight))
            candidate_rows.append(
                {
                    "weight": round(float(weight), 6),
                    "wis": round(float(metrics["wis"]), 6),
                    "crps": round(float(metrics["crps"]), 6),
                    "coverage_80": round(float(metrics.get("coverage_80") or 0.0), 6),
                }
            )
        candidate_rows.sort(
            key=lambda item: (
                float(item.get("wis") or float("inf")),
                float(item.get("crps") or float("inf")),
                abs(float(item.get("weight") or 0.0)),
            )
        )
        best = candidate_rows[0] if candidate_rows else {
            "weight": 0.0,
            "wis": baseline_metrics["wis"],
            "crps": baseline_metrics["crps"],
            "coverage_80": baseline_metrics.get("coverage_80", 0.0),
        }
        selected_row = best if self._blend_weight_improves(baseline_metrics=baseline_metrics, candidate_metrics=best) else {
            "weight": 0.0,
            "wis": round(float(baseline_metrics["wis"]), 6),
            "crps": round(float(baseline_metrics["crps"]), 6),
            "coverage_80": round(float(baseline_metrics.get("coverage_80") or 0.0), 6),
        }
        return {
            "weight": round(float(selected_row["weight"]), 6),
            "scope": scope if float(selected_row["weight"]) > 0.0 else f"{scope}_baseline_only",
            "samples": int(len(selected)),
            "regime": target_regime,
            "horizon_days": target_horizon_days,
            "wis": round(float(selected_row["wis"]), 6),
            "crps": round(float(selected_row["crps"]), 6),
            "baseline_wis": round(float(baseline_metrics["wis"]), 6),
            "baseline_crps": round(float(baseline_metrics["crps"]), 6),
            "top_candidates": candidate_rows[:3],
        }

    def _build_hierarchy_blend_policy(
        self,
        history_rows: list[dict[str, Any]],
        *,
        horizon_days: int | None,
    ) -> dict[str, Any]:
        history = self._prepare_hierarchy_history_frame(history_rows)
        if history.empty:
            return {
                "version": "fold_probabilistic_wis_crps_v1",
                "horizon_days": horizon_days,
                "fallback": {
                    "weight": 0.0,
                    "scope": "insufficient_history",
                    "samples": 0,
                },
                "by_regime": {},
            }

        fallback = self._estimate_hierarchy_blend_choice(
            history.to_dict("records"),
            target_horizon_days=horizon_days,
            target_regime=None,
        )
        regimes = sorted({str(value) for value in history.get("regime", pd.Series(dtype=str)).dropna().astype(str).tolist()})
        by_regime = {
            regime: self._estimate_hierarchy_blend_choice(
                history.to_dict("records"),
                target_horizon_days=horizon_days,
                target_regime=regime,
            )
            for regime in regimes
        }
        return {
            "version": "fold_probabilistic_wis_crps_v1",
            "horizon_days": horizon_days,
            "fallback": fallback,
            "by_regime": by_regime,
        }

    def _estimate_hierarchy_blend_weight(
        self,
        history_rows: list[dict[str, Any]],
        *,
        min_samples: int = HIERARCHY_BLEND_MIN_TOTAL_SAMPLES,
    ) -> float:
        choice = self._estimate_hierarchy_blend_choice(
            history_rows,
            min_total_samples=min_samples,
        )
        return float(choice.get("weight") or 0.0)

    @staticmethod
    def _blend_hierarchy_quantiles(
        *,
        model_quantiles: dict[float, np.ndarray] | None,
        baseline_quantiles: dict[float, np.ndarray],
        blend_weight: float,
    ) -> dict[float, np.ndarray]:
        return GeoHierarchyHelper.blend_quantiles(
            model_quantiles=model_quantiles,
            baseline_quantiles=baseline_quantiles,
            blend_weight=blend_weight,
        )

    def _hierarchy_component_diagnostics(
        self,
        *,
        oof_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        if oof_frame.empty:
            return {}

        cluster_rows: list[dict[str, float]] = []
        national_rows: list[dict[str, float]] = []
        working = oof_frame.copy()
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        for as_of_date, date_frame in working.groupby("as_of_date", dropna=False):
            date_frame = date_frame.copy().drop_duplicates(subset=["bundesland"], keep="last")
            if date_frame.empty:
                continue
            if "state_population_millions" in date_frame.columns:
                weights = pd.to_numeric(date_frame["state_population_millions"], errors="coerce").fillna(1.0).clip(lower=1e-6)
            else:
                weights = pd.Series(1.0, index=date_frame.index, dtype=float)
            baseline_lower_series = (
                pd.to_numeric(date_frame["prediction_interval_lower"], errors="coerce")
                if "prediction_interval_lower" in date_frame.columns
                else pd.to_numeric(date_frame["expected_target_incidence"], errors="coerce")
            )
            baseline_upper_series = (
                pd.to_numeric(date_frame["prediction_interval_upper"], errors="coerce")
                if "prediction_interval_upper" in date_frame.columns
                else pd.to_numeric(date_frame["expected_target_incidence"], errors="coerce")
            )
            if "cluster_id" in date_frame.columns and date_frame["cluster_id"].notna().any():
                for cluster_id, cluster_frame in date_frame.dropna(subset=["cluster_id"]).groupby("cluster_id", dropna=False):
                    cluster_weights = weights.loc[cluster_frame.index]
                    cluster_baseline_lower = baseline_lower_series.loc[cluster_frame.index]
                    cluster_baseline_upper = baseline_upper_series.loc[cluster_frame.index]
                    cluster_rows.append(
                        {
                            "as_of_date": pd.Timestamp(as_of_date).normalize(),
                            "regime": GeoHierarchyHelper.season_regime(as_of_date),
                            "horizon_days": int(cluster_frame["horizon_days"].iloc[-1]) if "horizon_days" in cluster_frame.columns else None,
                            "truth": float(np.average(cluster_frame["next_week_incidence"].astype(float), weights=cluster_weights)),
                            "baseline": float(np.average(cluster_frame["expected_target_incidence"].astype(float), weights=cluster_weights)),
                            "model": float(cluster_frame["cluster_expected_target_incidence"].iloc[-1]),
                            "baseline_q_0.1": float(np.average(cluster_baseline_lower.astype(float), weights=cluster_weights)),
                            "baseline_q_0.5": float(np.average(cluster_frame["expected_target_incidence"].astype(float), weights=cluster_weights)),
                            "baseline_q_0.9": float(np.average(cluster_baseline_upper.astype(float), weights=cluster_weights)),
                            "model_q_0.1": float(
                                cluster_frame["cluster_prediction_interval_lower"].iloc[-1]
                                if "cluster_prediction_interval_lower" in cluster_frame.columns
                                else cluster_frame["cluster_expected_target_incidence"].iloc[-1]
                            ),
                            "model_q_0.5": float(cluster_frame["cluster_expected_target_incidence"].iloc[-1]),
                            "model_q_0.9": float(
                                cluster_frame["cluster_prediction_interval_upper"].iloc[-1]
                                if "cluster_prediction_interval_upper" in cluster_frame.columns
                                else cluster_frame["cluster_expected_target_incidence"].iloc[-1]
                            ),
                        }
                    )
            if "national_expected_target_incidence" in date_frame.columns and date_frame["national_expected_target_incidence"].notna().any():
                national_rows.append(
                    {
                        "as_of_date": pd.Timestamp(as_of_date).normalize(),
                        "regime": GeoHierarchyHelper.season_regime(as_of_date),
                        "horizon_days": int(date_frame["horizon_days"].iloc[-1]) if "horizon_days" in date_frame.columns else None,
                        "truth": float(np.average(date_frame["next_week_incidence"].astype(float), weights=weights)),
                        "baseline": float(np.average(date_frame["expected_target_incidence"].astype(float), weights=weights)),
                        "model": float(date_frame["national_expected_target_incidence"].iloc[-1]),
                        "baseline_q_0.1": float(np.average(baseline_lower_series.astype(float), weights=weights)),
                        "baseline_q_0.5": float(np.average(date_frame["expected_target_incidence"].astype(float), weights=weights)),
                        "baseline_q_0.9": float(np.average(baseline_upper_series.astype(float), weights=weights)),
                        "model_q_0.1": float(
                            date_frame["national_prediction_interval_lower"].iloc[-1]
                            if "national_prediction_interval_lower" in date_frame.columns
                            else date_frame["national_expected_target_incidence"].iloc[-1]
                        ),
                        "model_q_0.5": float(date_frame["national_expected_target_incidence"].iloc[-1]),
                        "model_q_0.9": float(
                            date_frame["national_prediction_interval_upper"].iloc[-1]
                            if "national_prediction_interval_upper" in date_frame.columns
                            else date_frame["national_expected_target_incidence"].iloc[-1]
                        ),
                    }
                )

        def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
            if not rows:
                return {"samples": 0}
            frame = pd.DataFrame(rows).dropna(subset=["truth", "baseline"])
            if frame.empty:
                return {"samples": 0}
            frame["baseline_abs_error"] = (frame["baseline"] - frame["truth"]).abs()
            model_frame = frame.dropna(subset=["model"]).copy()
            model_mae = float(model_frame["model"].sub(model_frame["truth"]).abs().mean()) if not model_frame.empty else None
            baseline_mae = float(frame["baseline_abs_error"].mean())
            baseline_metrics = self._quantile_blend_metrics(frame, blend_weight=0.0)
            model_metrics = self._quantile_blend_metrics(frame, blend_weight=1.0)
            horizon_values = pd.to_numeric(frame.get("horizon_days"), errors="coerce").dropna().astype(int)
            horizon_days = int(horizon_values.mode().iloc[0]) if not horizon_values.empty else None
            blend_policy = self._build_hierarchy_blend_policy(rows, horizon_days=horizon_days)
            recommended_weight = float(((blend_policy.get("fallback") or {}).get("weight")) or 0.0)
            return {
                "samples": int(len(frame)),
                "baseline_mae": round(float(baseline_mae), 6),
                "model_mae": round(float(model_mae), 6) if model_mae is not None else None,
                "baseline_wis": round(float(baseline_metrics.get("wis") or 0.0), 6),
                "model_wis": round(float(model_metrics.get("wis") or 0.0), 6),
                "baseline_crps": round(float(baseline_metrics.get("crps") or 0.0), 6),
                "model_crps": round(float(model_metrics.get("crps") or 0.0), 6),
                "mae_delta_model_minus_baseline": (
                    round(float(model_mae - baseline_mae), 6)
                    if model_mae is not None
                    else None
                ),
                "recommended_blend_weight": recommended_weight,
                "blend_policy": blend_policy,
            }

        return {
            "cluster": _summarize(cluster_rows),
            "national": _summarize(national_rows),
        }

    def _predict_hierarchy_aggregate_quantiles(
        self,
        *,
        frame: pd.DataFrame,
        source_panel: pd.DataFrame,
        feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
        hierarchy_models: dict[str, dict[str, XGBRegressor] | None] | None = None,
        state_feature_columns: list[str] | None = None,
        hierarchy_model_modes: dict[str, str] | None = None,
    ) -> dict[str, list[Any]]:
        cluster_ids = pd.Series(index=frame.index, dtype=object)
        cluster_lower = pd.Series(np.nan, index=frame.index, dtype=float)
        cluster_median = pd.Series(np.nan, index=frame.index, dtype=float)
        cluster_upper = pd.Series(np.nan, index=frame.index, dtype=float)
        national_lower = pd.Series(np.nan, index=frame.index, dtype=float)
        national_median = pd.Series(np.nan, index=frame.index, dtype=float)
        national_upper = pd.Series(np.nan, index=frame.index, dtype=float)

        working_panel = source_panel.copy()
        working_panel["as_of_date"] = pd.to_datetime(working_panel["as_of_date"]).dt.normalize()
        frame_dates = frame.assign(as_of_date=pd.to_datetime(frame["as_of_date"]).dt.normalize())
        for as_of_date, idx in frame_dates.groupby("as_of_date").groups.items():
            date_slice = frame_dates.loc[idx].copy()
            panel_until_date = working_panel.loc[working_panel["as_of_date"] <= pd.Timestamp(as_of_date)].copy()
            cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
                panel_until_date,
                state_col="bundesland",
                value_col="current_known_incidence",
                date_col="as_of_date",
            )
            cluster_frame = GeoHierarchyHelper.aggregate_feature_frame(
                date_slice,
                feature_columns=feature_columns,
                cluster_assignments=cluster_assignments,
                level="cluster",
            )
            national_frame = GeoHierarchyHelper.aggregate_feature_frame(
                date_slice,
                feature_columns=feature_columns,
                level="national",
            )
            cluster_baseline_map, national_baseline_values = self._hierarchy_state_baseline_features(
                date_slice=date_slice,
                cluster_assignments=cluster_assignments,
                state_feature_columns=state_feature_columns or feature_columns,
                reg_lower=reg_lower,
                reg_median=reg_median,
                reg_upper=reg_upper,
            )
            if not cluster_frame.empty:
                cluster_frame = self._apply_hierarchy_baseline_map(
                    cluster_frame,
                    baseline_map=cluster_baseline_map,
                )
            if not national_frame.empty and national_baseline_values:
                national_frame = national_frame.copy()
                for column, value in national_baseline_values.items():
                    national_frame[column] = float(value)

            cluster_maps: dict[str, dict[str, float]] = {}
            cluster_model_bundle = (hierarchy_models or {}).get("cluster") or {}
            national_model_bundle = (hierarchy_models or {}).get("national") or {}
            if not cluster_frame.empty and cluster_model_bundle:
                cluster_X = cluster_frame[feature_columns].to_numpy(dtype=float)
                cluster_frame = cluster_frame.copy()
                cluster_target_mode = str((hierarchy_model_modes or {}).get("cluster") or "direct_log")
                if cluster_target_mode == "residual_log":
                    cluster_frame["q_0.1"] = self._hierarchy_apply_residual_prediction(
                        baseline=cluster_frame["hierarchy_state_baseline_q10"].to_numpy(dtype=float),
                        residual_log=cluster_model_bundle["lower"].predict(cluster_X),
                    )
                    cluster_frame["q_0.5"] = self._hierarchy_apply_residual_prediction(
                        baseline=cluster_frame["hierarchy_state_baseline_q50"].to_numpy(dtype=float),
                        residual_log=cluster_model_bundle["median"].predict(cluster_X),
                    )
                    cluster_frame["q_0.9"] = self._hierarchy_apply_residual_prediction(
                        baseline=cluster_frame["hierarchy_state_baseline_q90"].to_numpy(dtype=float),
                        residual_log=cluster_model_bundle["upper"].predict(cluster_X),
                    )
                else:
                    cluster_frame["q_0.1"] = np.expm1(cluster_model_bundle["lower"].predict(cluster_X))
                    cluster_frame["q_0.5"] = np.expm1(cluster_model_bundle["median"].predict(cluster_X))
                    cluster_frame["q_0.9"] = np.expm1(cluster_model_bundle["upper"].predict(cluster_X))
                cluster_maps = {
                    str(row["hierarchy_group"]): {
                        "q_0.1": float(row["q_0.1"]),
                        "q_0.5": float(row["q_0.5"]),
                        "q_0.9": float(row["q_0.9"]),
                    }
                    for _, row in cluster_frame.iterrows()
                }

            national_values = {"q_0.1": np.nan, "q_0.5": np.nan, "q_0.9": np.nan}
            if not national_frame.empty and national_model_bundle:
                national_X = national_frame[feature_columns].to_numpy(dtype=float)
                national_values = {
                    "q_0.1": float(np.expm1(national_model_bundle["lower"].predict(national_X))[0]),
                    "q_0.5": float(np.expm1(national_model_bundle["median"].predict(national_X))[0]),
                    "q_0.9": float(np.expm1(national_model_bundle["upper"].predict(national_X))[0]),
                }

            for row_idx, row in date_slice.iterrows():
                state = str(row["bundesland"])
                cluster_id = cluster_assignments.get(state)
                cluster_ids.at[row_idx] = cluster_id
                cluster_values = cluster_maps.get(str(cluster_id), {})
                cluster_lower.at[row_idx] = float(cluster_values.get("q_0.1", np.nan))
                cluster_median.at[row_idx] = float(cluster_values.get("q_0.5", np.nan))
                cluster_upper.at[row_idx] = float(cluster_values.get("q_0.9", np.nan))
                national_lower.at[row_idx] = float(national_values["q_0.1"])
                national_median.at[row_idx] = float(national_values["q_0.5"])
                national_upper.at[row_idx] = float(national_values["q_0.9"])

        return {
            "cluster_ids": cluster_ids.tolist(),
            "cluster_lower": cluster_lower.tolist(),
            "cluster_median": cluster_median.tolist(),
            "cluster_upper": cluster_upper.tolist(),
            "national_lower": national_lower.tolist(),
            "national_median": national_median.tolist(),
            "national_upper": national_upper.tolist(),
        }

    @staticmethod
    def _hierarchy_apply_residual_prediction(
        *,
        baseline: np.ndarray,
        residual_log: np.ndarray,
    ) -> np.ndarray:
        baseline_arr = np.asarray(baseline, dtype=float)
        residual_arr = np.asarray(residual_log, dtype=float)
        return np.expm1(np.log1p(np.clip(baseline_arr, 0.0, None)) + residual_arr)

    def _hierarchy_state_baseline_features(
        self,
        *,
        date_slice: pd.DataFrame,
        cluster_assignments: dict[str, str],
        state_feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
    ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
        if date_slice.empty:
            return {}, {}
        state_order = [str(value) for value in date_slice["bundesland"].tolist()]
        state_weights = {
            str(row["bundesland"]): float(row.get("state_population_millions") or 1.0)
            for _, row in date_slice.iterrows()
        } if "state_population_millions" in date_slice.columns else {}
        X = date_slice[state_feature_columns].to_numpy(dtype=float)
        state_quantiles = {
            0.1: np.expm1(reg_lower.predict(X)),
            0.5: np.expm1(reg_median.predict(X)),
            0.9: np.expm1(reg_upper.predict(X)),
        }
        cluster_quantiles, national_quantiles, cluster_order = GeoHierarchyHelper.derived_aggregate_quantiles(
            state_quantiles,
            state_order=state_order,
            cluster_assignments=cluster_assignments,
            state_weights=state_weights,
        )
        cluster_map: dict[str, dict[str, float]] = {}
        for idx, cluster_id in enumerate(cluster_order):
            lower = float(cluster_quantiles.get(0.1, np.asarray([], dtype=float))[idx])
            median = float(cluster_quantiles.get(0.5, np.asarray([], dtype=float))[idx])
            upper = float(cluster_quantiles.get(0.9, np.asarray([], dtype=float))[idx])
            cluster_map[str(cluster_id)] = {
                "hierarchy_state_baseline_q10": lower,
                "hierarchy_state_baseline_q50": median,
                "hierarchy_state_baseline_q90": upper,
                "hierarchy_state_baseline_width_80": float(max(upper - lower, 0.0)),
            }
        national_values = {
            "hierarchy_state_baseline_q10": float(np.asarray(national_quantiles.get(0.1), dtype=float)[0]),
            "hierarchy_state_baseline_q50": float(np.asarray(national_quantiles.get(0.5), dtype=float)[0]),
            "hierarchy_state_baseline_q90": float(np.asarray(national_quantiles.get(0.9), dtype=float)[0]),
        } if national_quantiles else {}
        if national_values:
            national_values["hierarchy_state_baseline_width_80"] = float(
                max(
                    float(national_values["hierarchy_state_baseline_q90"])
                    - float(national_values["hierarchy_state_baseline_q10"]),
                    0.0,
                )
            )
        return cluster_map, national_values

    @staticmethod
    def _apply_hierarchy_baseline_map(
        frame: pd.DataFrame,
        *,
        baseline_map: dict[str, dict[str, float]],
    ) -> pd.DataFrame:
        if frame.empty:
            return frame
        working = frame.copy()
        for column in GeoHierarchyHelper.HIERARCHY_STATE_BASELINE_FEATURE_COLUMNS:
            working[column] = [
                float((baseline_map.get(str(group)) or {}).get(column, 0.0))
                for group in working["hierarchy_group"].astype(str)
            ]
        return working

    def _build_hierarchy_training_frame(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        state_feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
        level: str,
        target_mode: str = "direct_log",
    ) -> pd.DataFrame:
        if panel.empty:
            return pd.DataFrame()

        working = panel.copy()
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        aggregate_frames: list[pd.DataFrame] = []
        for as_of_date in sorted(working["as_of_date"].dropna().unique()):
            date_value = pd.Timestamp(as_of_date).normalize()
            date_slice = working.loc[working["as_of_date"] == date_value].copy()
            if date_slice.empty:
                continue
            panel_until_date = working.loc[working["as_of_date"] <= date_value].copy()
            cluster_assignments = GeoHierarchyHelper.build_dynamic_clusters(
                panel_until_date,
                state_col="bundesland",
                value_col="current_known_incidence",
                date_col="as_of_date",
            )
            aggregate_frame = GeoHierarchyHelper.aggregate_feature_frame(
                date_slice,
                feature_columns=feature_columns,
                cluster_assignments=cluster_assignments,
                level=level,
            )
            if aggregate_frame.empty or "next_week_incidence" not in aggregate_frame.columns:
                continue
            cluster_baseline_map, national_baseline_values = self._hierarchy_state_baseline_features(
                date_slice=date_slice,
                cluster_assignments=cluster_assignments,
                state_feature_columns=state_feature_columns,
                reg_lower=reg_lower,
                reg_median=reg_median,
                reg_upper=reg_upper,
            )
            if level == "cluster":
                aggregate_frame = self._apply_hierarchy_baseline_map(
                    aggregate_frame,
                    baseline_map=cluster_baseline_map,
                )
            elif level == "national" and national_baseline_values:
                aggregate_frame = aggregate_frame.copy()
                for column, value in national_baseline_values.items():
                    aggregate_frame[column] = float(value)
            aggregate_frames.append(aggregate_frame)

        if not aggregate_frames:
            return pd.DataFrame()
        combined = pd.concat(aggregate_frames, ignore_index=True)
        combined["y_next_log"] = np.log1p(combined["next_week_incidence"].astype(float).clip(lower=0.0))
        if target_mode == "residual_log":
            combined["y_residual_log_lower"] = combined["y_next_log"] - np.log1p(
                combined["hierarchy_state_baseline_q10"].astype(float).clip(lower=0.0)
            )
            combined["y_residual_log_median"] = combined["y_next_log"] - np.log1p(
                combined["hierarchy_state_baseline_q50"].astype(float).clip(lower=0.0)
            )
            combined["y_residual_log_upper"] = combined["y_next_log"] - np.log1p(
                combined["hierarchy_state_baseline_q90"].astype(float).clip(lower=0.0)
            )
        return combined

    def _fit_hierarchy_models(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        state_feature_columns: list[str],
        reg_lower: XGBRegressor,
        reg_median: XGBRegressor,
        reg_upper: XGBRegressor,
    ) -> tuple[dict[str, dict[str, XGBRegressor] | None], dict[str, str]]:
        cluster_training = self._build_hierarchy_training_frame(
            panel=panel,
            feature_columns=feature_columns,
            state_feature_columns=state_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
            level="cluster",
            target_mode="residual_log",
        )
        national_training = self._build_hierarchy_training_frame(
            panel=panel,
            feature_columns=feature_columns,
            state_feature_columns=state_feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
            level="national",
        )

        def _fit_bundle(frame: pd.DataFrame, *, target_mode: str) -> dict[str, XGBRegressor] | None:
            if frame.empty or len(frame) < 40:
                return None
            target_columns = {
                "lower": "y_next_log",
                "median": "y_next_log",
                "upper": "y_next_log",
            }
            if target_mode == "residual_log":
                target_columns = {
                    "lower": "y_residual_log_lower",
                    "median": "y_residual_log_median",
                    "upper": "y_residual_log_upper",
                }
            return {
                "lower": self._fit_regressor_from_frame(
                    frame,
                    feature_columns,
                    REGIONAL_REGRESSOR_CONFIG["lower"],
                    target_col=target_columns["lower"],
                ),
                "median": self._fit_regressor_from_frame(
                    frame,
                    feature_columns,
                    REGIONAL_REGRESSOR_CONFIG["median"],
                    target_col=target_columns["median"],
                ),
                "upper": self._fit_regressor_from_frame(
                    frame,
                    feature_columns,
                    REGIONAL_REGRESSOR_CONFIG["upper"],
                    target_col=target_columns["upper"],
                ),
            }

        return (
            {
                "cluster": _fit_bundle(cluster_training, target_mode="residual_log"),
                "national": _fit_bundle(national_training, target_mode="direct_log"),
            },
            {
                "cluster": "residual_log",
                "national": "direct_log",
            },
        )

    def _fit_final_models(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        hierarchy_feature_columns: list[str],
        oof_frame: pd.DataFrame,
        action_threshold: float = 0.5,
    ) -> dict[str, Any]:
        calibration_frame = oof_frame.copy()
        if "as_of_date" not in calibration_frame.columns:
            calibration_frame["as_of_date"] = pd.date_range(
                start="2000-01-01",
                periods=len(calibration_frame),
                freq="D",
            )

        classifier = self._fit_classifier_from_frame(panel, feature_columns)
        calibration, calibration_mode = self._select_guarded_calibration(
            calibration_frame=calibration_frame[
                ["as_of_date", "event_label", "event_probability_raw"]
            ].copy(),
            raw_probability_col="event_probability_raw",
            action_threshold=action_threshold,
        )
        reg_median = self._fit_regressor_from_frame(
            panel,
            feature_columns,
            REGIONAL_REGRESSOR_CONFIG["median"],
        )
        reg_lower = self._fit_regressor_from_frame(
            panel,
            feature_columns,
            REGIONAL_REGRESSOR_CONFIG["lower"],
        )
        reg_upper = self._fit_regressor_from_frame(
            panel,
            feature_columns,
            REGIONAL_REGRESSOR_CONFIG["upper"],
        )
        hierarchy_models, hierarchy_model_modes = self._fit_hierarchy_models(
            panel=panel,
            feature_columns=hierarchy_feature_columns,
            state_feature_columns=feature_columns,
            reg_lower=reg_lower,
            reg_median=reg_median,
            reg_upper=reg_upper,
        )
        quantile_regressors: dict[float, XGBRegressor] = {
            0.1: reg_lower,
            0.5: reg_median,
            0.9: reg_upper,
        }
        for quantile in CANONICAL_FORECAST_QUANTILES:
            if quantile in quantile_regressors:
                continue
            quantile_regressors[float(quantile)] = self._fit_regressor_from_frame(
                panel,
                feature_columns,
                _quantile_regressor_config(float(quantile)),
            )
        learned_event_model = None
        if "event_label" in panel.columns and panel["event_label"].nunique() >= 2:
            calibration_rows = max(int(len(panel) * CALIBRATION_HOLDOUT_FRACTION), 20)
            calibration_rows = min(calibration_rows, max(len(panel) - 20, 0))
            calibration_frame_full = panel.tail(calibration_rows).copy() if calibration_rows > 0 else pd.DataFrame()
            train_frame_full = panel.iloc[:-calibration_rows].copy() if calibration_rows > 0 else panel.copy()
            if train_frame_full["event_label"].nunique() >= 2:
                # LearnedEventModel now reuses the shared helper path and needs the
                # true tail dates so its calibration guard stays time-respecting.
                calibration_dates = (
                    calibration_frame_full["as_of_date"].to_numpy()
                    if not calibration_frame_full.empty and "as_of_date" in calibration_frame_full.columns
                    else None
                )
                learned_event_model = LearnedEventModel.fit(
                    X_train=train_frame_full[feature_columns].to_numpy(),
                    y_train=train_frame_full["event_label"].to_numpy(),
                    X_calibration=(
                        calibration_frame_full[feature_columns].to_numpy()
                        if not calibration_frame_full.empty and calibration_frame_full["event_label"].nunique() >= 2
                        else None
                    ),
                    y_calibration=(
                        calibration_frame_full["event_label"].to_numpy()
                        if not calibration_frame_full.empty and calibration_frame_full["event_label"].nunique() >= 2
                        else None
                    ),
                    calibration_dates=calibration_dates,
                )
        return {
            "classifier": classifier,
            "calibration": calibration,
            "calibration_mode": calibration_mode,
            "regressor_median": reg_median,
            "regressor_lower": reg_lower,
            "regressor_upper": reg_upper,
            "quantile_regressors": quantile_regressors,
            "learned_event_model": learned_event_model,
            "hierarchy_models": hierarchy_models,
            "hierarchy_model_modes": hierarchy_model_modes,
        }

    def _persist_artifacts(
        self,
        *,
        model_dir: Path,
        final_artifacts: dict[str, Any],
        metadata: dict[str, Any],
        backtest_payload: dict[str, Any],
        dataset_manifest: dict[str, Any],
        point_in_time_manifest: dict[str, Any],
    ) -> None:
        model_dir.mkdir(parents=True, exist_ok=True)

        final_artifacts["classifier"].save_model(str(model_dir / "classifier.json"))
        final_artifacts["regressor_median"].save_model(str(model_dir / "regressor_median.json"))
        final_artifacts["regressor_lower"].save_model(str(model_dir / "regressor_lower.json"))
        final_artifacts["regressor_upper"].save_model(str(model_dir / "regressor_upper.json"))
        hierarchy_models = final_artifacts.get("hierarchy_models") or {}
        cluster_models = hierarchy_models.get("cluster") or {}
        national_models = hierarchy_models.get("national") or {}
        if cluster_models:
            cluster_models["median"].save_model(str(model_dir / "cluster_regressor_median.json"))
            cluster_models["lower"].save_model(str(model_dir / "cluster_regressor_lower.json"))
            cluster_models["upper"].save_model(str(model_dir / "cluster_regressor_upper.json"))
        if national_models:
            national_models["median"].save_model(str(model_dir / "national_regressor_median.json"))
            national_models["lower"].save_model(str(model_dir / "national_regressor_lower.json"))
            national_models["upper"].save_model(str(model_dir / "national_regressor_upper.json"))
        for quantile, model in sorted((final_artifacts.get("quantile_regressors") or {}).items()):
            model.save_model(str(model_dir / f"{quantile_key(float(quantile))}.json"))

        with open(model_dir / "calibration.pkl", "wb") as handle:
            pickle.dump(final_artifacts["calibration"], handle)

        with open(model_dir / "metadata.json", "w") as handle:
            json.dump(_json_safe(metadata), handle, indent=2)

        with open(model_dir / "backtest.json", "w") as handle:
            json.dump(_json_safe(backtest_payload), handle, indent=2)

        with open(model_dir / "threshold_manifest.json", "w") as handle:
            json.dump(
                _json_safe(
                    {
                        "selected_tau": metadata["selected_tau"],
                        "selected_kappa": metadata["selected_kappa"],
                        "action_threshold": metadata["action_threshold"],
                        "min_event_absolute_incidence": metadata["min_event_absolute_incidence"],
                        "event_definition_version": EVENT_DEFINITION_VERSION,
                        "event_definition_config": metadata.get("event_definition_config") or {},
                        "signal_bundle_version": metadata.get("signal_bundle_version"),
                        "rollout_mode": metadata.get("rollout_mode"),
                        "activation_policy": metadata.get("activation_policy"),
                        "horizon_days": metadata.get("horizon_days"),
                        "target_window_days": metadata.get("target_window_days") or list(TARGET_WINDOW_DAYS),
                    }
                ),
                handle,
                indent=2,
            )

        with open(model_dir / "dataset_manifest.json", "w") as handle:
            json.dump(_json_safe(dataset_manifest), handle, indent=2)
        with open(model_dir / "point_in_time_snapshot.json", "w") as handle:
            json.dump(_json_safe(point_in_time_manifest), handle, indent=2)

    @staticmethod
    def _calibration_split_dates(train_dates: list[pd.Timestamp]) -> tuple[list[pd.Timestamp], list[pd.Timestamp]] | None:
        return build_calibration_split_dates(
            train_dates,
            holdout_fraction=CALIBRATION_HOLDOUT_FRACTION,
            min_total_dates=35,
            min_holdout_dates=14,
            min_train_dates=20,
        )

    @staticmethod
    def _calibration_guard_split_dates(
        calibration_dates: list[pd.Timestamp],
    ) -> tuple[list[pd.Timestamp], list[pd.Timestamp]] | None:
        return build_calibration_guard_split_dates(
            calibration_dates,
            guard_fraction=CALIBRATION_GUARD_FRACTION,
            min_guard_dates=MIN_CALIBRATION_GUARD_DATES,
        )

    @staticmethod
    def _fit_classifier(
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> XGBClassifier:
        positives = max(int(np.sum(y == 1)), 1)
        negatives = max(int(np.sum(y == 0)), 1)
        config = dict(REGIONAL_CLASSIFIER_CONFIG)
        config["scale_pos_weight"] = float(negatives / positives)
        model = XGBClassifier(**config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    @staticmethod
    def _fit_regressor(
        X: np.ndarray,
        y: np.ndarray,
        *,
        config: dict[str, Any],
        sample_weight: np.ndarray | None = None,
    ) -> XGBRegressor:
        model = XGBRegressor(**config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    def _sample_weights(self, frame: pd.DataFrame) -> np.ndarray | None:
        return None

    def _fit_classifier_from_frame(self, frame: pd.DataFrame, feature_columns: list[str]) -> XGBClassifier:
        return self._fit_classifier(
            frame[feature_columns].to_numpy(),
            frame["event_label"].to_numpy(),
            sample_weight=self._sample_weights(frame),
        )

    def _fit_regressor_from_frame(
        self,
        frame: pd.DataFrame,
        feature_columns: list[str],
        config: dict[str, Any],
        target_col: str = "y_next_log",
    ) -> XGBRegressor:
        return self._fit_regressor(
            frame[feature_columns].to_numpy(),
            frame[target_col].to_numpy(),
            config=config,
            sample_weight=self._sample_weights(frame),
        )

    @staticmethod
    def _fit_isotonic(raw_probabilities: np.ndarray, labels: np.ndarray) -> IsotonicRegression | None:
        return fit_isotonic_calibrator(
            raw_probabilities,
            labels,
            min_samples=20,
            min_class_support=1,
        )

    @staticmethod
    def _apply_calibration(calibration: IsotonicRegression | None, raw_probabilities: np.ndarray) -> np.ndarray:
        return apply_probability_calibration(calibration, raw_probabilities)

    @staticmethod
    def _calibration_guard_metrics(
        *,
        as_of_dates: Any,
        labels: np.ndarray,
        probabilities: np.ndarray,
        action_threshold: float,
    ) -> dict[str, float]:
        clipped = RegionalModelTrainer._apply_calibration(None, np.asarray(probabilities, dtype=float))
        guard_frame = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(as_of_dates).normalize(),
                "event_label": np.asarray(labels, dtype=int),
                "guard_probability": clipped,
                "action_threshold": np.full(len(clipped), float(action_threshold), dtype=float),
            }
        )
        return {
            "brier_score": float(brier_score_safe(guard_frame["event_label"], clipped)),
            "ece": float(compute_ece(guard_frame["event_label"], clipped)),
            "precision_at_top3": float(
                precision_at_k(
                    guard_frame,
                    k=3,
                    score_col="guard_probability",
                )
            ),
            "activation_false_positive_rate": float(
                activation_false_positive_rate(
                    guard_frame,
                    threshold=None,
                    score_col="guard_probability",
                )
            ),
        }

    def _select_guarded_calibration(
        self,
        *,
        calibration_frame: pd.DataFrame,
        raw_probability_col: str,
        action_threshold: float | None = None,
        min_recall_for_threshold: float = 0.35,
        label_col: str = "event_label",
        date_col: str = "as_of_date",
    ) -> tuple[IsotonicRegression | None, str]:
        if calibration_frame.empty:
            return None, "raw_passthrough"

        working = calibration_frame[[date_col, label_col, raw_probability_col]].copy()
        working[date_col] = pd.to_datetime(working[date_col]).dt.normalize()

        guard_split = self._calibration_guard_split_dates(working[date_col].tolist())
        if not guard_split:
            return None, "raw_passthrough"
        fit_dates, guard_dates = guard_split
        fit_df = working.loc[working[date_col].isin(fit_dates)].copy()
        guard_df = working.loc[working[date_col].isin(guard_dates)].copy()
        if fit_df.empty or guard_df.empty:
            return None, "raw_passthrough"

        calibration = self._fit_isotonic(
            fit_df[raw_probability_col].to_numpy(),
            fit_df[label_col].to_numpy(),
        )
        if calibration is None:
            return None, "raw_passthrough"

        guard_labels = guard_df[label_col].to_numpy(dtype=int)
        raw_guard = self._apply_calibration(None, guard_df[raw_probability_col].to_numpy())
        effective_threshold = float(action_threshold) if action_threshold is not None else float(
            choose_action_threshold(
                raw_guard,
                guard_labels,
                min_recall=min_recall_for_threshold,
            )[0]
        )
        raw_metrics = self._calibration_guard_metrics(
            as_of_dates=guard_df[date_col].to_numpy(),
            labels=guard_labels,
            probabilities=raw_guard,
            action_threshold=effective_threshold,
        )
        calibrated_guard = self._apply_calibration(
            calibration,
            guard_df[raw_probability_col].to_numpy(),
        )
        calibrated_metrics = self._calibration_guard_metrics(
            as_of_dates=guard_df[date_col].to_numpy(),
            labels=guard_labels,
            probabilities=calibrated_guard,
            action_threshold=effective_threshold,
        )
        if (
            calibrated_metrics["brier_score"] <= raw_metrics["brier_score"] + CALIBRATION_GUARD_EPSILON
            and calibrated_metrics["ece"] <= raw_metrics["ece"] + CALIBRATION_GUARD_EPSILON
            and calibrated_metrics["precision_at_top3"] + CALIBRATION_GUARD_EPSILON
            >= raw_metrics["precision_at_top3"]
            and calibrated_metrics["activation_false_positive_rate"]
            <= raw_metrics["activation_false_positive_rate"] + CALIBRATION_GUARD_EPSILON
        ):
            return calibration, "isotonic_guarded"
        return None, "raw_passthrough"

    def _amelag_only_probabilities(
        self,
        *,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        feature_columns: list[str],
    ) -> np.ndarray:
        if not feature_columns or train_df["event_label"].nunique() < 2:
            base_rate = float(train_df["event_label"].mean() or 0.0)
            return np.full(len(test_df), base_rate, dtype=float)

        classifier = self._fit_classifier_from_frame(train_df, feature_columns)
        raw_prob = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
        train_raw = classifier.predict_proba(train_df[feature_columns].to_numpy())[:, 1]
        calibration = self._fit_isotonic(train_raw, train_df["event_label"].to_numpy())
        return self._apply_calibration(calibration, raw_prob)

    @staticmethod
    def _event_probability_from_prediction(
        *,
        predicted_next: np.ndarray,
        current_known: np.ndarray,
        baseline: np.ndarray,
        mad: np.ndarray,
        tau: float,
        kappa: float,
        min_absolute_incidence: float,
    ) -> np.ndarray:
        predicted_next = np.asarray(predicted_next, dtype=float)
        current_known = np.asarray(current_known, dtype=float)
        baseline = np.asarray(baseline, dtype=float)
        mad = np.maximum(np.asarray(mad, dtype=float), 1.0)

        relative_gap = np.log1p(np.maximum(predicted_next, 0.0)) - np.log1p(np.maximum(current_known, 0.0)) - tau
        absolute_threshold = np.asarray(
            [
                absolute_incidence_threshold(
                    seasonal_baseline=baseline_value,
                    seasonal_mad=mad_value,
                    kappa=kappa,
                    min_absolute_incidence=min_absolute_incidence,
                )
                for baseline_value, mad_value in zip(baseline, mad, strict=False)
            ],
            dtype=float,
        )
        absolute_gap = (predicted_next - absolute_threshold) / mad
        logits = np.minimum(relative_gap / max(tau, 0.05), absolute_gap)
        return 1.0 / (1.0 + np.exp(-logits))

    @staticmethod
    def _aggregate_metrics(frame: pd.DataFrame, *, action_threshold: float) -> dict[str, float]:
        return regional_trainer_backtest.aggregate_metrics(
            frame,
            action_threshold=action_threshold,
        )

    def _baseline_metrics(self, frame: pd.DataFrame, *, action_threshold: float) -> dict[str, dict[str, float]]:
        return regional_trainer_backtest.baseline_metrics(
            self,
            frame,
            action_threshold=action_threshold,
        )

    def _build_backtest_payload(
        self,
        *,
        frame: pd.DataFrame,
        aggregate_metrics: dict[str, float],
        baselines: dict[str, dict[str, float]],
        quality_gate: dict[str, Any],
        tau: float,
        kappa: float,
        action_threshold: float,
        fold_selection_summary: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return regional_trainer_backtest.build_backtest_payload(
            self,
            frame=frame,
            aggregate_metrics=aggregate_metrics,
            baselines=baselines,
            quality_gate=quality_gate,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            fold_selection_summary=fold_selection_summary,
        )

    @staticmethod
    def _activation_mask(state_frame: pd.DataFrame, *, action_threshold: float) -> pd.Series:
        return regional_trainer_backtest.activation_mask(
            state_frame,
            action_threshold=action_threshold,
        )

    @staticmethod
    def _state_precision_recall(state_frame: pd.DataFrame, *, action_threshold: float) -> tuple[float, float]:
        return regional_trainer_backtest.state_precision_recall(
            state_frame,
            action_threshold=action_threshold,
        )


# Backward-compatible alias for scripts and older imports.
RegionalTrainer = RegionalModelTrainer
