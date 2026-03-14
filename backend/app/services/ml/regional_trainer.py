"""Pooled regional panel trainer for leakage-safe outbreak forecasting."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier, XGBRegressor

from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    MIN_EVENT_ABSOLUTE_INCIDENCE,
    TARGET_WINDOW_DAYS,
    activation_false_positive_rate,
    average_precision_safe,
    brier_score_safe,
    build_event_label,
    choose_action_threshold,
    compute_ece,
    median_lead_days,
    precision_at_k,
    quality_gate_from_metrics,
    time_based_panel_splits,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"

LABEL_TAU_GRID = [0.10, 0.15, 0.20, 0.25, 0.30]
LABEL_KAPPA_GRID = [0.0, 0.5, 1.0]
CALIBRATION_HOLDOUT_FRACTION = 0.20
MIN_RECALL_FOR_SELECTION = 0.35

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
    "target_week_start",
    "target_window_days",
    "event_definition_version",
    "truth_source",
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


@dataclass
class ProbabilityCalibrator:
    """Serializable wrapper for calibration methods with a unified predict API."""

    method: str
    model: Any | None = None

    def predict(self, raw_probabilities: np.ndarray) -> np.ndarray:
        values = np.asarray(raw_probabilities, dtype=float)
        if self.method == "identity" or self.model is None:
            return np.clip(values, 0.001, 0.999)
        if self.method == "isotonic":
            return np.clip(self.model.predict(values), 0.001, 0.999)
        if self.method == "platt":
            return np.clip(self.model.predict_proba(values.reshape(-1, 1))[:, 1], 0.001, 0.999)
        raise ValueError(f"Unsupported calibration method: {self.method}")


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
    ) -> dict[str, Any]:
        summary = self.train_all_regions(virus_typ=virus_typ, lookback_days=lookback_days)
        details = (summary.get("backtest") or {}).get("details") or {}
        return details.get(bundesland.upper(), {"error": f"No summary available for {bundesland.upper()}"})

    def train_all_regions(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
        persist: bool = True,
    ) -> dict[str, Any]:
        logger.info("Training pooled regional panel model for %s", virus_typ)
        panel = self.feature_builder.build_panel_training_data(virus_typ=virus_typ, lookback_days=lookback_days)
        if panel.empty or len(panel) < 200:
            return {
                "status": "error",
                "virus_typ": virus_typ,
                "error": f"Insufficient pooled panel data ({len(panel)} rows).",
            }

        panel = panel.copy()
        panel["y_next_log"] = np.log1p(panel["next_week_incidence"].astype(float).clip(lower=0.0))
        feature_columns = self._feature_columns(panel)
        ww_only_columns = self._ww_only_feature_columns(feature_columns)

        selection = self._select_event_definition(panel=panel, feature_columns=feature_columns)
        tau = float(selection["tau"])
        kappa = float(selection["kappa"])
        action_threshold = float(selection["action_threshold"])

        panel["event_label"] = self._event_labels(panel, tau=tau, kappa=kappa)
        backtest_bundle = self._build_backtest_bundle(
            panel=panel,
            feature_columns=feature_columns,
            ww_only_columns=ww_only_columns,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
        )
        final_artifacts = self._fit_final_models(
            panel=panel,
            feature_columns=feature_columns,
            oof_frame=backtest_bundle["oof_frame"],
        )

        dataset_manifest = self.feature_builder.dataset_manifest(virus_typ=virus_typ, panel=panel)
        model_dir = self.models_dir / _virus_slug(virus_typ)
        metadata = {
            "virus_typ": virus_typ,
            "model_family": "regional_pooled_panel",
            "trained_at": datetime.utcnow().isoformat(),
            "feature_columns": feature_columns,
            "ww_only_feature_columns": ww_only_columns,
            "selected_tau": tau,
            "selected_kappa": kappa,
            "action_threshold": action_threshold,
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "target_window_days": list(TARGET_WINDOW_DAYS),
            "min_event_absolute_incidence": MIN_EVENT_ABSOLUTE_INCIDENCE,
            "dataset_manifest": dataset_manifest,
            "quality_gate": backtest_bundle["quality_gate"],
            "aggregate_metrics": backtest_bundle["aggregate_metrics"],
            "label_selection": selection,
        }

        if persist:
            self._persist_artifacts(
                model_dir=model_dir,
                final_artifacts=final_artifacts,
                metadata=metadata,
                backtest_payload=backtest_bundle["backtest_payload"],
                dataset_manifest=dataset_manifest,
            )

        per_state = (backtest_bundle["backtest_payload"].get("details") or {})
        return {
            "status": "success",
            "virus_typ": virus_typ,
            "trained": len(per_state),
            "failed": max(0, len(ALL_BUNDESLAENDER) - len(per_state)),
            "quality_gate": backtest_bundle["quality_gate"],
            "aggregate_metrics": backtest_bundle["aggregate_metrics"],
            "model_dir": str(model_dir),
            "backtest": backtest_bundle["backtest_payload"],
            "selection": selection,
        }

    def train_all_viruses_all_regions(self, lookback_days: int = 900) -> dict[str, Any]:
        return {
            virus_typ: self.train_all_regions(virus_typ=virus_typ, lookback_days=lookback_days)
            for virus_typ in SUPPORTED_VIRUS_TYPES
        }

    def get_regional_accuracy_summary(self, virus_typ: str = "Influenza A") -> list[dict]:
        artifact = self.load_artifacts(virus_typ=virus_typ)
        backtest = artifact.get("backtest") or {}
        details = backtest.get("details") or {}
        summaries: list[dict] = []
        for code, payload in sorted(details.items()):
            metrics = payload.get("metrics") or {}
            summaries.append(
                {
                    "bundesland": code,
                    "name": payload.get("bundesland_name", BUNDESLAND_NAMES.get(code, code)),
                    "samples": int(payload.get("total_windows") or 0),
                    "precision": metrics.get("precision"),
                    "recall": metrics.get("recall"),
                    "pr_auc": metrics.get("pr_auc"),
                    "brier_score": metrics.get("brier_score"),
                    "trained_at": (artifact.get("metadata") or {}).get("trained_at"),
                }
            )
        return summaries

    def load_artifacts(self, virus_typ: str) -> dict[str, Any]:
        model_dir = self.models_dir / _virus_slug(virus_typ)
        if not model_dir.exists():
            return {}

        payload: dict[str, Any] = {}
        meta_path = model_dir / "metadata.json"
        backtest_path = model_dir / "backtest.json"
        if meta_path.exists():
            payload["metadata"] = json.loads(meta_path.read_text())
        if backtest_path.exists():
            payload["backtest"] = json.loads(backtest_path.read_text())
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
            if column.startswith("ww_") or column in {"neighbor_ww_level", "national_ww_level"}
        ]

    @staticmethod
    def _event_labels(panel: pd.DataFrame, *, tau: float, kappa: float) -> np.ndarray:
        return np.asarray(
            [
                build_event_label(
                    current_known_incidence=row.current_known_incidence,
                    next_week_incidence=row.next_week_incidence,
                    seasonal_baseline=row.seasonal_baseline,
                    seasonal_mad=row.seasonal_mad,
                    tau=tau,
                    kappa=kappa,
                )
                for row in panel.itertuples()
            ],
            dtype=int,
        )

    def _select_event_definition(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
    ) -> dict[str, Any]:
        best: dict[str, Any] | None = None

        for tau in LABEL_TAU_GRID:
            for kappa in LABEL_KAPPA_GRID:
                labels = self._event_labels(panel, tau=tau, kappa=kappa)
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
                    min_recall=MIN_RECALL_FOR_SELECTION,
                )
                candidate = {
                    "tau": tau,
                    "kappa": kappa,
                    "action_threshold": threshold,
                    "precision_at_top3": precision_at_k(
                        evaluation,
                        k=3,
                        score_col="event_probability_calibrated",
                        tie_breaker_col="event_probability_raw",
                    ),
                    "precision_at_top5": precision_at_k(
                        evaluation,
                        k=5,
                        score_col="event_probability_calibrated",
                        tie_breaker_col="event_probability_raw",
                    ),
                    "precision": precision,
                    "recall": recall,
                    "pr_auc": average_precision_safe(
                        evaluation["event_label"],
                        evaluation["event_probability_calibrated"],
                    ),
                    "ece": compute_ece(
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
                    if candidate["pr_auc"] > best["pr_auc"]:
                        best = candidate
                    elif np.isclose(candidate["pr_auc"], best["pr_auc"]):
                        if candidate["precision_at_top3"] > best["precision_at_top3"]:
                            best = candidate
                        elif np.isclose(candidate["precision_at_top3"], best["precision_at_top3"]):
                            if candidate["ece"] < best["ece"]:
                                best = candidate
                            elif np.isclose(candidate["ece"], best["ece"]) and candidate["recall"] > best["recall"]:
                                best = candidate

        if best is None:
            best = {
                "tau": 0.20,
                "kappa": 0.5,
                "action_threshold": 0.6,
                "precision_at_top3": 0.0,
                "precision_at_top5": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "pr_auc": 0.0,
                "ece": 1.0,
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
            calibration = self._fit_calibrator(
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
                        "event_probability_raw": raw_probs,
                    }
                )
            )

        if not oof_frames:
            return None
        return pd.concat(oof_frames, ignore_index=True)

    def _build_backtest_bundle(
        self,
        *,
        panel: pd.DataFrame,
        feature_columns: list[str],
        ww_only_columns: list[str],
        tau: float,
        kappa: float,
        action_threshold: float,
    ) -> dict[str, Any]:
        working = panel.copy()
        working["event_label"] = self._event_labels(working, tau=tau, kappa=kappa)
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
                panel=train_df,
                feature_columns=feature_columns,
            )
            fold_tau = float(fold_selection["tau"])
            fold_kappa = float(fold_selection["kappa"])
            fold_threshold = float(fold_selection["action_threshold"])

            train_df["event_label"] = self._event_labels(train_df, tau=fold_tau, kappa=fold_kappa)
            test_df["event_label"] = self._event_labels(test_df, tau=fold_tau, kappa=fold_kappa)
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
            calibration = self._fit_calibrator(
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
            )
            climatology_prob = self._event_probability_from_prediction(
                predicted_next=test_df["seasonal_baseline"].to_numpy(),
                current_known=test_df["current_known_incidence"].to_numpy(),
                baseline=test_df["seasonal_baseline"].to_numpy(),
                mad=test_df["seasonal_mad"].to_numpy(),
                tau=fold_tau,
                kappa=fold_kappa,
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
                    "selection_precision_at_top3": fold_selection.get("precision_at_top3"),
                    "selection_precision_at_top5": fold_selection.get("precision_at_top5"),
                    "selection_precision": fold_selection.get("precision"),
                    "selection_recall": fold_selection.get("recall"),
                    "selection_pr_auc": fold_selection.get("pr_auc"),
                    "selection_ece": fold_selection.get("ece"),
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
                        "target_week_start": test_df["target_week_start"].values,
                        "event_label": test_df["event_label"].values.astype(int),
                        "event_probability_calibrated": calibrated_prob,
                        "event_probability_raw": raw_prob,
                        "amelag_only_probability": ww_prob,
                        "persistence_probability": persistence_prob,
                        "climatology_probability": climatology_prob,
                        "current_known_incidence": test_df["current_known_incidence"].values.astype(float),
                        "next_week_incidence": test_df["next_week_incidence"].values.astype(float),
                        "expected_next_week_incidence": pred_next,
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
        calibration = self._fit_calibrator(
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
                        "event_definition_version": EVENT_DEFINITION_VERSION,
                        "target_window_days": list(TARGET_WINDOW_DAYS),
                    }
                ),
                handle,
                indent=2,
            )

        with open(model_dir / "dataset_manifest.json", "w") as handle:
            json.dump(_json_safe(dataset_manifest), handle, indent=2)

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

    def _fit_calibrator(self, raw_probabilities: np.ndarray, labels: np.ndarray) -> ProbabilityCalibrator:
        raw = np.asarray(raw_probabilities, dtype=float)
        y = np.asarray(labels, dtype=int)
        if len(raw) < 20 or len(np.unique(y)) < 2:
            return ProbabilityCalibrator(method="identity")

        split_idx = max(10, int(len(raw) * 0.7))
        split_idx = min(split_idx, len(raw) - 10)
        if split_idx <= 0 or split_idx >= len(raw):
            split_idx = len(raw)

        if split_idx < len(raw):
            fit_raw, eval_raw = raw[:split_idx], raw[split_idx:]
            fit_y, eval_y = y[:split_idx], y[split_idx:]
        else:
            fit_raw, eval_raw = raw, raw
            fit_y, eval_y = y, y

        candidates: list[tuple[str, Any | None]] = [("identity", None)]
        if len(np.unique(fit_y)) >= 2:
            platt = LogisticRegression(random_state=42, solver="lbfgs")
            platt.fit(fit_raw.reshape(-1, 1), fit_y)
            candidates.append(("platt", platt))
            if len(fit_raw) >= 20:
                isotonic = IsotonicRegression(out_of_bounds="clip")
                isotonic.fit(fit_raw, fit_y.astype(float))
                candidates.append(("isotonic", isotonic))

        best_method = "identity"
        best_model: Any | None = None
        best_metrics: tuple[float, float] | None = None
        for method, model in candidates:
            calibrator = ProbabilityCalibrator(method=method, model=model)
            calibrated = calibrator.predict(eval_raw)
            metrics = (
                float(brier_score_safe(eval_y, calibrated)),
                float(compute_ece(eval_y, calibrated)),
            )
            if best_metrics is None or metrics < best_metrics:
                best_method = method
                best_model = model
                best_metrics = metrics

        if best_method == "identity":
            return ProbabilityCalibrator(method="identity")
        if best_method == "platt":
            final_model = LogisticRegression(random_state=42, solver="lbfgs")
            final_model.fit(raw.reshape(-1, 1), y)
            return ProbabilityCalibrator(method="platt", model=final_model)

        final_isotonic = IsotonicRegression(out_of_bounds="clip")
        final_isotonic.fit(raw, y.astype(float))
        return ProbabilityCalibrator(method="isotonic", model=final_isotonic)

    @staticmethod
    def _apply_calibration(calibration: ProbabilityCalibrator | None, raw_probabilities: np.ndarray) -> np.ndarray:
        if calibration is None:
            return np.clip(raw_probabilities.astype(float), 0.001, 0.999)
        return calibration.predict(np.asarray(raw_probabilities, dtype=float))

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
        calibration = self._fit_calibrator(train_raw, train_df["event_label"].to_numpy())
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
    ) -> np.ndarray:
        predicted_next = np.asarray(predicted_next, dtype=float)
        current_known = np.asarray(current_known, dtype=float)
        baseline = np.asarray(baseline, dtype=float)
        mad = np.maximum(np.asarray(mad, dtype=float), 1.0)

        relative_gap = np.log1p(np.maximum(predicted_next, 0.0)) - np.log1p(np.maximum(current_known, 0.0)) - tau
        absolute_threshold = np.maximum(MIN_EVENT_ABSOLUTE_INCIDENCE, baseline + kappa * mad)
        absolute_gap = (predicted_next - absolute_threshold) / mad
        logits = np.minimum(relative_gap / max(tau, 0.05), absolute_gap)
        return 1.0 / (1.0 + np.exp(-logits))

    @staticmethod
    def _aggregate_metrics(frame: pd.DataFrame, *, action_threshold: float) -> dict[str, float]:
        effective_threshold = None if "action_threshold" in frame.columns else action_threshold
        return {
            "precision_at_top3": precision_at_k(
                frame,
                k=3,
                score_col="event_probability_calibrated",
                tie_breaker_col="event_probability_raw",
            ),
            "precision_at_top5": precision_at_k(
                frame,
                k=5,
                score_col="event_probability_calibrated",
                tie_breaker_col="event_probability_raw",
            ),
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
                "precision_at_top3": precision_at_k(
                    state_frame,
                    k=3,
                    score_col="event_probability_calibrated",
                    tie_breaker_col="event_probability_raw",
                ),
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
        return {
            "virus_typ": str(frame["virus_typ"].iloc[0]),
            "event_definition_version": EVENT_DEFINITION_VERSION,
            "target_window_days": list(TARGET_WINDOW_DAYS),
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
