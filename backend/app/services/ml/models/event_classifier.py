from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

from app.services.ml.regional_panel_utils import choose_action_threshold


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
    calibration: IsotonicRegression | None
    action_threshold: float
    calibration_mode: str

    @classmethod
    def fit(
        cls,
        *,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_calibration: np.ndarray | None = None,
        y_calibration: np.ndarray | None = None,
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
        classifier = XGBClassifier(**clf_config)
        classifier.fit(X_train, labels)

        calibration = None
        calibration_mode = "raw_passthrough"
        calib_probs = classifier.predict_proba(X_train)[:, 1]
        calib_labels = labels
        if X_calibration is not None and y_calibration is not None and len(np.unique(y_calibration)) >= 2:
            calib_probs = classifier.predict_proba(X_calibration)[:, 1]
            calib_labels = np.asarray(y_calibration, dtype=int)
            if len(calib_labels) >= 20:
                calibration = IsotonicRegression(out_of_bounds="clip")
                calibration.fit(calib_probs, calib_labels.astype(float))
                calibration_mode = "isotonic"
        effective_probs = np.clip(
            calibration.predict(calib_probs.astype(float)) if calibration is not None else calib_probs.astype(float),
            0.001,
            0.999,
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
        if self.calibration is None:
            return np.clip(raw.astype(float), 0.001, 0.999)
        return np.clip(self.calibration.predict(raw.astype(float)), 0.001, 0.999)

    def metadata(self) -> dict[str, Any]:
        return {
            "model_family": "learned_event_xgb",
            "action_threshold": round(float(self.action_threshold), 6),
            "calibration_mode": self.calibration_mode,
            "calibration_enabled": self.calibration is not None,
        }
