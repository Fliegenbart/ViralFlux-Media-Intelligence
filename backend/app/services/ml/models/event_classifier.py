from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from xgboost import XGBClassifier

from app.services.ml.forecast_horizon_utils import (
    apply_probability_calibration,
    select_probability_calibration_from_raw,
)
from app.services.ml.regional_panel_utils import choose_action_threshold
from app.services.ml.xgboost_runtime import resolve_xgboost_runtime_config


DEFAULT_EVENT_CLASSIFIER_CONFIG: dict[str, Any] = {
    "n_estimators": 120,
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


@dataclass
class LearnedEventModel:
    classifier: XGBClassifier
    calibration: Any | None
    action_threshold: float
    calibration_mode: str

    @classmethod
    def fit(
        cls,
        *,
        X_train: np.ndarray,
        y_train: np.ndarray,
        sample_weight_train: np.ndarray | None = None,
        X_calibration: np.ndarray | None = None,
        y_calibration: np.ndarray | None = None,
        calibration_dates: Any | None = None,
        min_recall: float = 0.35,
        config: dict[str, Any] | None = None,
    ) -> "LearnedEventModel":
        labels = np.asarray(y_train, dtype=int)
        positives = max(int(np.sum(labels == 1)), 1)
        negatives = max(int(np.sum(labels == 0)), 1)
        clf_config = dict(DEFAULT_EVENT_CLASSIFIER_CONFIG)
        if config:
            clf_config.update(config)
        clf_config["scale_pos_weight"] = float(negatives / positives)
        clf_config = resolve_xgboost_runtime_config(clf_config)
        classifier = XGBClassifier(**clf_config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight_train is not None:
            fit_kwargs["sample_weight"] = np.asarray(sample_weight_train, dtype=float)
        classifier.fit(X_train, labels, **fit_kwargs)

        calibration = None
        calibration_mode = "raw_passthrough"
        calib_probs = classifier.predict_proba(X_train)[:, 1]
        calib_labels = labels
        if X_calibration is not None and y_calibration is not None and len(np.unique(y_calibration)) >= 2:
            calib_probs = classifier.predict_proba(X_calibration)[:, 1]
            calib_labels = np.asarray(y_calibration, dtype=int)
            # Reuse the canonical shared helper path, but keep this model conservative:
            # it still exposes only isotonic or raw_passthrough, not a new product mode.
            calibration_payload = select_probability_calibration_from_raw(
                calib_probs,
                calib_labels,
                as_of_dates=calibration_dates,
                allowed_modes=("isotonic", "raw_probability"),
                isotonic_min_samples=20,
                isotonic_min_class_support=1,
            )
            calibration = calibration_payload.get("calibration")
            calibration_mode = (
                "isotonic"
                if str(calibration_payload.get("calibration_mode") or "raw_probability") == "isotonic"
                else "raw_passthrough"
            )
        effective_probs = apply_probability_calibration(
            calibration,
            np.asarray(calib_probs, dtype=float),
        )
        threshold, _, _ = choose_action_threshold(
            effective_probs,
            calib_labels,
            min_recall=min_recall,
        )
        return cls(
            classifier=classifier,
            calibration=calibration,
            action_threshold=float(threshold),
            calibration_mode=calibration_mode,
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw = self.classifier.predict_proba(X)[:, 1]
        return apply_probability_calibration(self.calibration, raw)

    def metadata(self) -> dict[str, Any]:
        return {
            "model_family": "learned_event_xgb",
            "action_threshold": round(float(self.action_threshold), 6),
            "calibration_mode": self.calibration_mode,
            "calibration_enabled": self.calibration is not None,
        }
