"""Offline XGBoost Training Module.

Decouples model training (heavy, infrequent) from model inference
(lightweight, real-time). The ``XGBoostTrainer`` class extracts the
training pipeline from ``ForecastService``, serialises the fitted
XGBoost meta-learner to disk, and invalidates the in-memory model
cache so that subsequent ``ForecastService.predict()`` calls pick up
the freshly trained artefacts.

Serialisation layout per virus type (e.g. ``influenza_a/``)::

    backend/app/ml_models/
        influenza_a/
            model_median.json   # XGBRegressor, quantile_alpha=0.8
            model_lower.json    # XGBRegressor, quantile_alpha=0.1
            model_upper.json    # XGBRegressor, quantile_alpha=0.9
            metadata.json       # version, trained_at, feature_names, ...
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.services.ml.forecast_service import META_FEATURES, ForecastService

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models"


def _virus_slug(virus_typ: str) -> str:
    """Normalise virus name to a filesystem-safe directory name.

    ``"Influenza A"`` → ``"influenza_a"``
    ``"SARS-CoV-2"``  → ``"sars_cov_2"``
    """
    return virus_typ.lower().replace(" ", "_").replace("-", "_")


class XGBoostTrainer:
    """Train and serialise XGBoost meta-learner stacking models.

    This class owns the *training + serialisation* pipeline only.
    Inference is handled by ``ForecastService.predict()``.
    """

    VIRUS_TYPES: list[str] = ["Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"]

    def __init__(self, db: Session, models_dir: Path | None = None) -> None:
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self._forecast_svc = ForecastService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(self, virus_typ: str = "Influenza A") -> dict[str, Any]:
        """Full training pipeline for a single virus type.

        Steps:
            1. Prepare training data (wastewater, trends, holidays …)
            2. Generate out-of-fold predictions (TimeSeriesSplit, 5 folds)
            3. Fit 3 XGBoost quantile models (median, lower, upper)
            4. Serialise models + metadata to disk
            5. Invalidate in-memory model cache

        Returns:
            Metadata dict with training stats and model path.
        """
        logger.info(f"=== XGBoostTrainer: training for {virus_typ} ===")

        # 1. Prepare data
        df = self._forecast_svc.prepare_training_data(virus_typ=virus_typ)
        if df.empty or len(df) < 10:
            msg = f"Insufficient data ({len(df)} rows) for {virus_typ}"
            logger.warning(msg)
            return {"error": msg, "virus_typ": virus_typ}

        # 2. Out-of-fold predictions
        oof = self._forecast_svc._generate_oof_predictions(df, n_splits=5)

        # 3. Fit XGBoost meta-learner (3 quantile models)
        model_med, model_lo, model_hi, feature_importance = (
            self._forecast_svc._fit_xgboost_meta(df, oof)
        )

        # 4. Serialise
        available_meta = [
            f for f in META_FEATURES
            if f in df.columns or f in ("hw_pred", "ridge_pred", "prophet_pred")
        ]
        metadata = self._save_models(
            virus_typ=virus_typ,
            model_median=model_med,
            model_lower=model_lo,
            model_upper=model_hi,
            feature_names=available_meta,
            feature_importance=feature_importance,
            training_samples=len(df),
        )

        # 5. Invalidate cache
        try:
            from app.services.ml.forecast_service import invalidate_model_cache
            invalidate_model_cache(virus_typ)
        except ImportError:
            pass

        logger.info(
            f"XGBoostTrainer: saved models for {virus_typ} "
            f"→ {metadata['model_dir']}"
        )
        return metadata

    def train_all(self) -> dict[str, Any]:
        """Train models for all supported virus types."""
        results: dict[str, Any] = {}
        for virus in self.VIRUS_TYPES:
            try:
                results[virus] = self.train(virus_typ=virus)
            except Exception as e:
                logger.error(f"Training failed for {virus}: {e}", exc_info=True)
                results[virus] = {"error": str(e)}
        return results

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _save_models(
        self,
        virus_typ: str,
        model_median: Any,
        model_lower: Any,
        model_upper: Any,
        feature_names: list[str],
        feature_importance: dict[str, float],
        training_samples: int,
    ) -> dict[str, Any]:
        """Serialise 3 XGBoost models + metadata sidecar to disk.

        Uses atomic write (temp file + rename) to avoid partial reads
        during concurrent inference.
        """
        slug = _virus_slug(virus_typ)
        model_dir = self.models_dir / slug
        model_dir.mkdir(parents=True, exist_ok=True)

        # Atomic save helper
        def _atomic_save_model(model: Any, target: Path) -> None:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(model_dir), suffix=".json.tmp",
            )
            os.close(fd)
            try:
                model.save_model(tmp_path)
                os.replace(tmp_path, str(target))
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

        _atomic_save_model(model_median, model_dir / "model_median.json")
        _atomic_save_model(model_lower, model_dir / "model_lower.json")
        _atomic_save_model(model_upper, model_dir / "model_upper.json")

        # Metadata sidecar
        now = datetime.utcnow()
        metadata: dict[str, Any] = {
            "virus_typ": virus_typ,
            "version": f"xgb_stack_v1_{now.strftime('%Y%m%dT%H%M')}",
            "trained_at": now.isoformat(),
            "training_samples": training_samples,
            "feature_names": feature_names,
            "feature_importance": {
                k: float(v) for k, v in feature_importance.items()
            },
            "model_dir": str(model_dir),
        }

        meta_path = model_dir / "metadata.json"
        fd, tmp_path = tempfile.mkstemp(
            dir=str(model_dir), suffix=".meta.tmp",
        )
        os.close(fd)
        try:
            with open(tmp_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)
            os.replace(tmp_path, str(meta_path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return metadata
