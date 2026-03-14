"""Regional XGBoost Training Module.

Trains per-Bundesland forecast models using regional features
(wastewater, SurvStat, weather, pollen, holidays).

Serialisation layout::

    backend/app/ml_models/
        regional/
            influenza_a/
                by/model_median.json
                by/model_lower.json
                by/model_upper.json
                by/metadata.json
                nw/model_median.json
                ...
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor

from app.services.ml.regional_features import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    RegionalFeatureBuilder,
)
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional"

# Regional meta-features (different from national model)
REGIONAL_META_FEATURES: list[str] = [
    "amelag_regional_lag4",
    "amelag_regional_lag7",
    "trend_momentum_7d",
    "survstat_regional",
    "survstat_regional_lag7",
    "survstat_regional_lag14",
    "temperature_avg_7d",
    "humidity_avg_7d",
    "pollen_severity_max",
    "schulferien_regional",
]

# XGBoost config (lighter than national — less data per region)
REGIONAL_XGB_CONFIG: dict[str, dict[str, Any]] = {
    "median": {
        "n_estimators": 120,
        "max_depth": 4,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.5,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "lower": {
        "n_estimators": 80,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.1,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
    "upper": {
        "n_estimators": 80,
        "max_depth": 3,
        "learning_rate": 0.05,
        "objective": "reg:quantileerror",
        "quantile_alpha": 0.9,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": 1,
    },
}


def _virus_slug(virus_typ: str) -> str:
    return virus_typ.lower().replace(" ", "_").replace("-", "_")


class RegionalModelTrainer:
    """Train per-Bundesland XGBoost forecast models."""

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
        """Train a single regional model.

        Returns metadata dict with training stats, accuracy metrics, and model path.
        """
        logger.info("Training regional model: %s / %s", virus_typ, bundesland)

        # 1. Build regional features
        df = self.feature_builder.build_regional_training_data(
            virus_typ=virus_typ,
            bundesland=bundesland,
            lookback_days=lookback_days,
        )

        if df.empty or len(df) < 30:
            msg = f"Insufficient data ({len(df)} rows) for {virus_typ}/{bundesland}"
            logger.warning(msg)
            return {"error": msg, "virus_typ": virus_typ, "bundesland": bundesland}

        # 2. Prepare feature matrix
        available_features = [f for f in REGIONAL_META_FEATURES if f in df.columns]
        if len(available_features) < 3:
            msg = f"Too few features ({len(available_features)}) for {virus_typ}/{bundesland}"
            logger.warning(msg)
            return {"error": msg, "virus_typ": virus_typ, "bundesland": bundesland}

        X = df[available_features].values
        y = df["y"].values

        # 3. Time-series cross-validation backtest
        n_splits = min(5, max(2, len(df) // 30))
        tscv = TimeSeriesSplit(n_splits=n_splits)

        cv_metrics = []
        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            model = XGBRegressor(**REGIONAL_XGB_CONFIG["median"])
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

            mae = float(np.mean(np.abs(y_test - y_pred)))
            mape = float(np.mean(np.abs((y_test - y_pred) / np.maximum(y_test, 1e-8))) * 100)
            corr = float(np.corrcoef(y_test, y_pred)[0, 1]) if len(y_test) > 2 else 0.0

            cv_metrics.append({"fold": fold, "mae": mae, "mape": mape, "correlation": corr})

        avg_mape = np.mean([m["mape"] for m in cv_metrics])
        avg_mae = np.mean([m["mae"] for m in cv_metrics])
        avg_corr = np.mean([m["correlation"] for m in cv_metrics])

        # 4. Train final models on all data (3 quantile models)
        model_med = XGBRegressor(**REGIONAL_XGB_CONFIG["median"])
        model_lo = XGBRegressor(**REGIONAL_XGB_CONFIG["lower"])
        model_hi = XGBRegressor(**REGIONAL_XGB_CONFIG["upper"])

        model_med.fit(X, y)
        model_lo.fit(X, y)
        model_hi.fit(X, y)

        # Feature importance
        importance = dict(zip(available_features, model_med.feature_importances_.tolist()))

        # 5. Save models
        slug = _virus_slug(virus_typ)
        bl_lower = bundesland.lower()
        model_dir = self.models_dir / slug / bl_lower
        model_dir.mkdir(parents=True, exist_ok=True)

        model_med.save_model(str(model_dir / "model_median.json"))
        model_lo.save_model(str(model_dir / "model_lower.json"))
        model_hi.save_model(str(model_dir / "model_upper.json"))

        metadata = {
            "virus_typ": virus_typ,
            "bundesland": bundesland,
            "bundesland_name": BUNDESLAND_NAMES.get(bundesland, bundesland),
            "training_samples": len(df),
            "features": available_features,
            "feature_importance": importance,
            "cv_folds": n_splits,
            "cv_metrics": cv_metrics,
            "avg_mape": round(avg_mape, 2),
            "avg_mae": round(avg_mae, 2),
            "avg_correlation": round(avg_corr, 4),
            "date_range": {
                "start": str(df["ds"].min()),
                "end": str(df["ds"].max()),
            },
            "trained_at": datetime.utcnow().isoformat(),
            "model_dir": str(model_dir),
        }

        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2, default=str)

        logger.info(
            "Regional model trained: %s/%s — %d samples, MAPE=%.1f%%, corr=%.3f",
            virus_typ, bundesland, len(df), avg_mape, avg_corr,
        )
        return metadata

    def train_all_regions(
        self,
        virus_typ: str = "Influenza A",
        lookback_days: int = 900,
    ) -> dict[str, Any]:
        """Train models for all available Bundesländer."""
        available = self.feature_builder.get_available_bundeslaender(virus_typ)
        logger.info("Training regional models for %s: %d Bundesländer", virus_typ, len(available))

        results: dict[str, Any] = {}
        trained = 0
        failed = 0

        for bl_code in available:
            try:
                result = self.train_region(
                    virus_typ=virus_typ,
                    bundesland=bl_code,
                    lookback_days=lookback_days,
                )
                results[bl_code] = result
                if "error" not in result:
                    trained += 1
                else:
                    failed += 1
            except Exception as exc:
                logger.error("Training failed for %s/%s: %s", virus_typ, bl_code, exc)
                results[bl_code] = {"error": str(exc)}
                failed += 1

        return {
            "virus_typ": virus_typ,
            "total_attempted": len(available),
            "trained": trained,
            "failed": failed,
            "results": results,
            "trained_at": datetime.utcnow().isoformat(),
        }

    def train_all_viruses_all_regions(self, lookback_days: int = 900) -> dict[str, Any]:
        """Train regional models for all virus types × all Bundesländer."""
        results = {}
        for virus_typ in SUPPORTED_VIRUS_TYPES:
            results[virus_typ] = self.train_all_regions(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
            )
        return results

    def get_regional_accuracy_summary(self, virus_typ: str = "Influenza A") -> list[dict]:
        """Read saved metadata for all regional models and return accuracy summary."""
        slug = _virus_slug(virus_typ)
        base_dir = self.models_dir / slug
        if not base_dir.exists():
            return []

        summaries = []
        for bl_dir in sorted(base_dir.iterdir()):
            if not bl_dir.is_dir():
                continue
            meta_path = bl_dir / "metadata.json"
            if not meta_path.exists():
                continue
            with open(meta_path) as f:
                meta = json.load(f)
            summaries.append({
                "bundesland": meta.get("bundesland", bl_dir.name.upper()),
                "name": meta.get("bundesland_name", ""),
                "samples": meta.get("training_samples", 0),
                "mape": meta.get("avg_mape"),
                "correlation": meta.get("avg_correlation"),
                "trained_at": meta.get("trained_at"),
            })

        return summaries
