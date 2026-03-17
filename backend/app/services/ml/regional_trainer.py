"""Pooled regional panel trainer for leakage-safe outbreak forecasting."""

from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier, XGBRegressor

from app.services.ml.forecast_horizon_utils import (
    SUPPORTED_FORECAST_HORIZONS,
    ensure_supported_horizon,
    regional_horizon_support_status,
    regional_model_artifact_dir,
)
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

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"

CALIBRATION_HOLDOUT_FRACTION = 0.20

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
    "current_known_incidence",
    "next_week_incidence",
    "seasonal_baseline",
    "seasonal_mad",
    "event_label",
    "y_next_log",
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


class RegionalModelTrainer:
    """Train pooled per-virus panel models across all Bundesländer."""

    def __init__(self, db, models_dir: Path | None = None) -> None:
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.feature_builder = RegionalFeatureBuilder(db)

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
        )

    def _train_single_horizon(
        self,
        *,
        virus_typ: str,
        lookback_days: int,
        persist: bool,
        horizon_days: int,
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
        logger.info("Training pooled regional panel model for %s (horizon=%s)", virus_typ, horizon)
        previous_artifact = self.load_artifacts(virus_typ=virus_typ, horizon_days=horizon)
        panel = self.feature_builder.build_panel_training_data(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            horizon_days=horizon,
            include_nowcast=True,
            use_revision_adjusted=False,
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
            ww_only_columns=ww_only_columns,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            event_config=event_config,
        )
        rollout_info = self._rollout_metadata(
            virus_typ=virus_typ,
            aggregate_metrics=backtest_bundle["aggregate_metrics"],
            baseline_metrics=(backtest_bundle["backtest_payload"].get("baselines") or {}),
            previous_artifact=previous_artifact,
        )
        backtest_bundle["backtest_payload"].update(_json_safe(rollout_info))
        final_artifacts = self._fit_final_models(
            panel=panel,
            feature_columns=feature_columns,
            oof_frame=backtest_bundle["oof_frame"],
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
        model_dir = regional_model_artifact_dir(
            self.models_dir,
            virus_typ=virus_typ,
            horizon_days=horizon,
        )
        metadata = {
            "virus_typ": virus_typ,
            "model_family": "regional_pooled_panel",
            "trained_at": datetime.utcnow().isoformat(),
            "model_version": None,
            "calibration_version": None,
            "horizon_days": horizon,
            "target_window_days": _target_window_for_horizon(horizon),
            "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
            "forecast_target_semantics": "current_known_incidence_at_as_of_plus_horizon_days",
            "feature_columns": feature_columns,
            "ww_only_feature_columns": ww_only_columns,
            "selected_tau": tau,
            "selected_kappa": kappa,
            "action_threshold": action_threshold,
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "min_event_absolute_incidence": event_config.min_absolute_incidence,
            "event_definition_config": event_config.to_manifest(),
            "dataset_manifest": dataset_manifest,
            "nowcast_features_enabled": True,
            "signal_bundle_version": rollout_info["signal_bundle_version"],
            "rollout_mode": rollout_info["rollout_mode"],
            "activation_policy": rollout_info["activation_policy"],
            "shadow_evaluation": rollout_info.get("shadow_evaluation"),
            "quality_gate": backtest_bundle["quality_gate"],
            "aggregate_metrics": backtest_bundle["aggregate_metrics"],
            "label_selection": selection,
            "point_in_time_snapshot": {
                "snapshot_type": point_in_time_manifest.get("snapshot_type"),
                "captured_at": point_in_time_manifest.get("captured_at"),
                "unique_as_of_dates": point_in_time_manifest.get("unique_as_of_dates"),
            },
        }
        metadata["model_version"] = f"{metadata['model_family']}:h{horizon}:{metadata['trained_at']}"
        metadata["calibration_version"] = f"isotonic:h{horizon}:{metadata['trained_at']}"

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
            "model_dir": str(model_dir),
            "backtest": backtest_bundle["backtest_payload"],
            "selection": selection,
        }

    def train_all_viruses_all_regions(
        self,
        lookback_days: int = 900,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        return self.train_selected_viruses_all_regions(
            virus_types=SUPPORTED_VIRUS_TYPES,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
        )

    def train_selected_viruses_all_regions(
        self,
        *,
        virus_types: list[str] | tuple[str, ...],
        lookback_days: int = 900,
        horizon_days: int = 7,
        horizon_days_list: list[int] | None = None,
    ) -> dict[str, Any]:
        return {
            virus_typ: self.train_all_regions(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
                horizon_days=horizon_days,
                horizon_days_list=horizon_days_list,
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

    def _rollout_metadata(
        self,
        *,
        virus_typ: str,
        aggregate_metrics: dict[str, Any],
        baseline_metrics: dict[str, dict[str, Any]],
        previous_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        rollout_mode = rollout_mode_for_virus(virus_typ)
        activation_policy = activation_policy_for_virus(virus_typ)
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

            classifier = self._fit_classifier(
                model_train_df[feature_columns].to_numpy(),
                model_train_df["event_label"].to_numpy(),
            )
            calibration = self._fit_isotonic(
                classifier.predict_proba(cal_df[feature_columns].to_numpy())[:, 1],
                cal_df["event_label"].to_numpy(),
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
        ww_only_columns: list[str],
        tau: float,
        kappa: float,
        action_threshold: float,
        event_config=None,
    ) -> dict[str, Any]:
        config = event_config or event_definition_config_for_virus(virus_typ)
        working = panel.copy()
        working["event_label"] = self._event_labels(
            working,
            virus_typ=virus_typ,
            tau=tau,
            kappa=kappa,
            event_config=config,
        )
        working["y_next_log"] = np.log1p(working["next_week_incidence"].astype(float).clip(lower=0.0))
        working["as_of_date"] = pd.to_datetime(working["as_of_date"]).dt.normalize()
        working["target_week_start"] = pd.to_datetime(working["target_week_start"]).dt.normalize()

        splits = time_based_panel_splits(
            working["as_of_date"],
            n_splits=5,
            min_train_periods=90,
            min_test_periods=21,
        )
        if not splits:
            raise ValueError("Unable to build time-based backtest splits for regional panel.")

        fold_frames: list[pd.DataFrame] = []
        fold_selection_summary: list[dict[str, Any]] = []
        for fold_idx, (train_dates, test_dates) in enumerate(splits):
            train_df = working.loc[working["as_of_date"].isin(train_dates)].copy()
            test_df = working.loc[working["as_of_date"].isin(test_dates)].copy()
            if train_df.empty or test_df.empty:
                continue

            fold_selection = self._select_event_definition(
                virus_typ=virus_typ,
                panel=train_df,
                feature_columns=feature_columns,
                event_config=config,
            )
            fold_tau = float(fold_selection["tau"])
            fold_kappa = float(fold_selection["kappa"])
            fold_threshold = float(fold_selection["action_threshold"])

            train_df["event_label"] = self._event_labels(
                train_df,
                virus_typ=virus_typ,
                tau=fold_tau,
                kappa=fold_kappa,
                event_config=config,
            )
            test_df["event_label"] = self._event_labels(
                test_df,
                virus_typ=virus_typ,
                tau=fold_tau,
                kappa=fold_kappa,
                event_config=config,
            )
            if train_df["event_label"].nunique() < 2:
                continue

            calib_split = self._calibration_split_dates(train_dates)
            if not calib_split:
                continue
            model_train_dates, cal_dates = calib_split
            model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
            cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
            if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
                continue

            classifier = self._fit_classifier(
                model_train_df[feature_columns].to_numpy(),
                model_train_df["event_label"].to_numpy(),
            )
            calibration = self._fit_isotonic(
                classifier.predict_proba(cal_df[feature_columns].to_numpy())[:, 1],
                cal_df["event_label"].to_numpy(),
            )
            raw_prob = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
            calibrated_prob = self._apply_calibration(calibration, raw_prob)

            ww_prob = self._amelag_only_probabilities(
                train_df=train_df,
                test_df=test_df,
                feature_columns=ww_only_columns,
            )

            reg_median = self._fit_regressor(
                train_df[feature_columns].to_numpy(),
                train_df["y_next_log"].to_numpy(),
                config=REGIONAL_REGRESSOR_CONFIG["median"],
            )
            reg_lower = self._fit_regressor(
                train_df[feature_columns].to_numpy(),
                train_df["y_next_log"].to_numpy(),
                config=REGIONAL_REGRESSOR_CONFIG["lower"],
            )
            reg_upper = self._fit_regressor(
                train_df[feature_columns].to_numpy(),
                train_df["y_next_log"].to_numpy(),
                config=REGIONAL_REGRESSOR_CONFIG["upper"],
            )

            pred_log = reg_median.predict(test_df[feature_columns].to_numpy())
            pred_lo = reg_lower.predict(test_df[feature_columns].to_numpy())
            pred_hi = reg_upper.predict(test_df[feature_columns].to_numpy())
            pred_next = np.expm1(pred_log)
            pred_next_lo = np.expm1(pred_lo)
            pred_next_hi = np.expm1(pred_hi)

            persistence_prob = self._event_probability_from_prediction(
                predicted_next=test_df["current_known_incidence"].to_numpy(),
                current_known=test_df["current_known_incidence"].to_numpy(),
                baseline=test_df["seasonal_baseline"].to_numpy(),
                mad=test_df["seasonal_mad"].to_numpy(),
                tau=fold_tau,
                kappa=fold_kappa,
                min_absolute_incidence=config.min_absolute_incidence,
            )
            climatology_prob = self._event_probability_from_prediction(
                predicted_next=test_df["seasonal_baseline"].to_numpy(),
                current_known=test_df["current_known_incidence"].to_numpy(),
                baseline=test_df["seasonal_baseline"].to_numpy(),
                mad=test_df["seasonal_mad"].to_numpy(),
                tau=fold_tau,
                kappa=fold_kappa,
                min_absolute_incidence=config.min_absolute_incidence,
            )

            fold_selection_summary.append(
                {
                    "fold": fold_idx,
                    "train_start": str(min(train_dates)),
                    "train_end": str(max(train_dates)),
                    "test_start": str(min(test_dates)),
                    "test_end": str(max(test_dates)),
                    "selected_tau": fold_tau,
                    "selected_kappa": fold_kappa,
                    "action_threshold": fold_threshold,
                    "selection_precision": fold_selection.get("precision"),
                    "selection_recall": fold_selection.get("recall"),
                    "selection_pr_auc": fold_selection.get("pr_auc"),
                }
            )
            fold_frames.append(
                pd.DataFrame(
                    {
                        "fold": fold_idx,
                        "virus_typ": test_df["virus_typ"].values,
                        "bundesland": test_df["bundesland"].values,
                        "bundesland_name": test_df["bundesland_name"].values,
                        "as_of_date": test_df["as_of_date"].values,
                        "target_date": test_df["target_date"].values if "target_date" in test_df.columns else None,
                        "target_week_start": test_df["target_week_start"].values,
                        "horizon_days": test_df["horizon_days"].values.astype(int) if "horizon_days" in test_df.columns else np.full(len(test_df), TARGET_WINDOW_DAYS[1], dtype=int),
                        "event_label": test_df["event_label"].values.astype(int),
                        "event_probability_calibrated": calibrated_prob,
                        "event_probability_raw": raw_prob,
                        "amelag_only_probability": ww_prob,
                        "persistence_probability": persistence_prob,
                        "climatology_probability": climatology_prob,
                        "current_known_incidence": test_df["current_known_incidence"].values.astype(float),
                        "next_week_incidence": test_df["next_week_incidence"].values.astype(float),
                        "expected_next_week_incidence": pred_next,
                        "expected_target_incidence": pred_next,
                        "prediction_interval_lower": pred_next_lo,
                        "prediction_interval_upper": pred_next_hi,
                        "selected_tau": fold_tau,
                        "selected_kappa": fold_kappa,
                        "action_threshold": fold_threshold,
                    }
                )
            )

        if not fold_frames:
            raise ValueError("Regional backtest produced no valid folds.")

        oof_frame = pd.concat(fold_frames, ignore_index=True)
        aggregate_metrics = self._aggregate_metrics(
            frame=oof_frame,
            action_threshold=action_threshold,
        )
        baselines = self._baseline_metrics(
            frame=oof_frame,
            action_threshold=action_threshold,
        )
        quality_gate = quality_gate_from_metrics(metrics=aggregate_metrics, baseline_metrics=baselines)
        backtest_payload = self._build_backtest_payload(
            frame=oof_frame,
            aggregate_metrics=aggregate_metrics,
            baselines=baselines,
            quality_gate=quality_gate,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            fold_selection_summary=fold_selection_summary,
        )
        return {
            "oof_frame": oof_frame,
            "aggregate_metrics": aggregate_metrics,
            "quality_gate": quality_gate,
            "backtest_payload": backtest_payload,
        }

    def _fit_final_models(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        oof_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        classifier = self._fit_classifier(
            panel[feature_columns].to_numpy(),
            panel["event_label"].to_numpy(),
        )
        calibration = self._fit_isotonic(
            oof_frame["event_probability_raw"].to_numpy(),
            oof_frame["event_label"].to_numpy(),
        )
        reg_median = self._fit_regressor(
            panel[feature_columns].to_numpy(),
            panel["y_next_log"].to_numpy(),
            config=REGIONAL_REGRESSOR_CONFIG["median"],
        )
        reg_lower = self._fit_regressor(
            panel[feature_columns].to_numpy(),
            panel["y_next_log"].to_numpy(),
            config=REGIONAL_REGRESSOR_CONFIG["lower"],
        )
        reg_upper = self._fit_regressor(
            panel[feature_columns].to_numpy(),
            panel["y_next_log"].to_numpy(),
            config=REGIONAL_REGRESSOR_CONFIG["upper"],
        )
        return {
            "classifier": classifier,
            "calibration": calibration,
            "regressor_median": reg_median,
            "regressor_lower": reg_lower,
            "regressor_upper": reg_upper,
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
        if len(train_dates) < 35:
            return None
        calibration_size = max(14, int(len(train_dates) * CALIBRATION_HOLDOUT_FRACTION))
        calibration_size = min(calibration_size, len(train_dates) - 20)
        if calibration_size <= 0:
            return None
        return train_dates[:-calibration_size], train_dates[-calibration_size:]

    @staticmethod
    def _fit_classifier(X: np.ndarray, y: np.ndarray) -> XGBClassifier:
        positives = max(int(np.sum(y == 1)), 1)
        negatives = max(int(np.sum(y == 0)), 1)
        config = dict(REGIONAL_CLASSIFIER_CONFIG)
        config["scale_pos_weight"] = float(negatives / positives)
        model = XGBClassifier(**config)
        model.fit(X, y)
        return model

    @staticmethod
    def _fit_regressor(X: np.ndarray, y: np.ndarray, *, config: dict[str, Any]) -> XGBRegressor:
        model = XGBRegressor(**config)
        model.fit(X, y)
        return model

    @staticmethod
    def _fit_isotonic(raw_probabilities: np.ndarray, labels: np.ndarray) -> IsotonicRegression | None:
        if len(raw_probabilities) < 20 or len(np.unique(labels)) < 2:
            return None
        calibration = IsotonicRegression(out_of_bounds="clip")
        calibration.fit(raw_probabilities, labels.astype(float))
        return calibration

    @staticmethod
    def _apply_calibration(calibration: IsotonicRegression | None, raw_probabilities: np.ndarray) -> np.ndarray:
        if calibration is None:
            return np.clip(raw_probabilities.astype(float), 0.001, 0.999)
        return np.clip(calibration.predict(raw_probabilities.astype(float)), 0.001, 0.999)

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

        classifier = self._fit_classifier(
            train_df[feature_columns].to_numpy(),
            train_df["event_label"].to_numpy(),
        )
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
        effective_threshold = None if "action_threshold" in frame.columns else action_threshold
        return {
            "precision_at_top3": precision_at_k(frame, k=3),
            "precision_at_top5": precision_at_k(frame, k=5),
            "pr_auc": round(
                average_precision_safe(frame["event_label"], frame["event_probability_calibrated"]),
                6,
            ),
            "brier_score": round(
                brier_score_safe(frame["event_label"], frame["event_probability_calibrated"]),
                6,
            ),
            "ece": round(
                compute_ece(frame["event_label"], frame["event_probability_calibrated"]),
                6,
            ),
            "median_lead_days": median_lead_days(frame, threshold=effective_threshold),
            "activation_false_positive_rate": activation_false_positive_rate(
                frame,
                threshold=effective_threshold,
            ),
            "action_threshold": round(float(action_threshold), 4),
        }

    def _baseline_metrics(self, frame: pd.DataFrame, *, action_threshold: float) -> dict[str, dict[str, float]]:
        baselines: dict[str, dict[str, float]] = {}
        effective_threshold = None if "action_threshold" in frame.columns else action_threshold
        for name, column in {
            "persistence": "persistence_probability",
            "climatology": "climatology_probability",
            "amelag_only": "amelag_only_probability",
        }.items():
            baseline_frame = frame.copy()
            baseline_frame["baseline_probability"] = baseline_frame[column]
            baselines[name] = {
                "pr_auc": round(average_precision_safe(frame["event_label"], frame[column]), 6),
                "brier_score": round(brier_score_safe(frame["event_label"], frame[column]), 6),
                "ece": round(compute_ece(frame["event_label"], frame[column]), 6),
                "precision_at_top3": precision_at_k(
                    baseline_frame,
                    k=3,
                    score_col="baseline_probability",
                ),
                "activation_false_positive_rate": activation_false_positive_rate(
                    baseline_frame,
                    threshold=effective_threshold,
                    score_col="baseline_probability",
                ),
            }
        return baselines

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
        details: dict[str, Any] = {}
        ranking = []
        for state, state_frame in frame.groupby("bundesland"):
            precision, recall = self._state_precision_recall(state_frame, action_threshold=action_threshold)
            activation_mask = self._activation_mask(state_frame, action_threshold=action_threshold)
            state_metrics = {
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "pr_auc": round(
                    average_precision_safe(state_frame["event_label"], state_frame["event_probability_calibrated"]),
                    6,
                ),
                "brier_score": round(
                    brier_score_safe(state_frame["event_label"], state_frame["event_probability_calibrated"]),
                    6,
                ),
                "ece": round(
                    compute_ece(state_frame["event_label"], state_frame["event_probability_calibrated"]),
                    6,
                ),
                "activations": int(np.sum(activation_mask)),
                "events": int(np.sum(state_frame["event_label"] == 1)),
                "precision_at_top3": precision_at_k(state_frame, k=3),
            }
            timeline = (
                state_frame.sort_values("as_of_date")
                .tail(20)
                .assign(
                    activated=lambda df: (
                        df["event_probability_calibrated"] >= df["action_threshold"]
                        if "action_threshold" in df.columns
                        else df["event_probability_calibrated"] >= action_threshold
                    )
                )
                .to_dict(orient="records")
            )
            details[state] = {
                "bundesland": state,
                "bundesland_name": BUNDESLAND_NAMES.get(state, state),
                "total_windows": int(len(state_frame)),
                "metrics": _json_safe(state_metrics),
                "timeline": _json_safe(timeline),
            }
            ranking.append(
                {
                    "bundesland": state,
                    "name": BUNDESLAND_NAMES.get(state, state),
                    "precision": state_metrics["precision"],
                    "recall": state_metrics["recall"],
                    "pr_auc": state_metrics["pr_auc"],
                    "events": state_metrics["events"],
                }
            )

        ranking.sort(key=lambda item: (item["precision"], item["pr_auc"]), reverse=True)
        horizon = int(frame["horizon_days"].iloc[0]) if "horizon_days" in frame.columns else TARGET_WINDOW_DAYS[1]
        return {
            "virus_typ": str(frame["virus_typ"].iloc[0]),
            "horizon_days": horizon,
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "target_window_days": _target_window_for_horizon(horizon),
            "selected_tau": tau,
            "selected_kappa": kappa,
            "action_threshold": action_threshold,
            "aggregate_metrics": _json_safe(aggregate_metrics),
            "baselines": _json_safe(baselines),
            "quality_gate": _json_safe(quality_gate),
            "nested_selection_summary": _json_safe(fold_selection_summary),
            "total_regions": len(details),
            "backtested": len(details),
            "failed": max(0, len(ALL_BUNDESLAENDER) - len(details)),
            "ranking": _json_safe(ranking),
            "details": _json_safe(details),
            "generated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _activation_mask(state_frame: pd.DataFrame, *, action_threshold: float) -> pd.Series:
        if "action_threshold" in state_frame.columns:
            return state_frame["event_probability_calibrated"] >= state_frame["action_threshold"]
        return state_frame["event_probability_calibrated"] >= action_threshold

    @staticmethod
    def _state_precision_recall(state_frame: pd.DataFrame, *, action_threshold: float) -> tuple[float, float]:
        activated = RegionalModelTrainer._activation_mask(state_frame, action_threshold=action_threshold)
        positives = state_frame["event_label"] == 1
        tp = float(np.sum(activated & positives))
        fp = float(np.sum(activated & ~positives))
        fn = float(np.sum(~activated & positives))
        precision = tp / max(tp + fp, 1.0)
        recall = tp / max(tp + fn, 1.0)
        return precision, recall


# Backward-compatible alias for scripts and older imports.
RegionalTrainer = RegionalModelTrainer
