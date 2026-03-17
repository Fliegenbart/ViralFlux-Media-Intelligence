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
            model_median.json   # XGBRegressor, quantile_alpha=0.5
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

from sqlalchemy.orm import Session

from app.services.ml.forecast_horizon_utils import (
    DEFAULT_FORECAST_REGION,
    DEFAULT_FORECAST_REGION,
    ensure_supported_horizon,
    model_artifact_dir,
    normalize_forecast_region,
)
from app.services.ml.forecast_service import ForecastService
from app.services.ml.training_contract import (
    SUPPORTED_VIRUS_TYPES,
    normalize_scope_selection,
)

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

    VIRUS_TYPES: list[str] = list(SUPPORTED_VIRUS_TYPES)
    RESEARCH_CANDIDATES: list[dict[str, Any]] = [
        {
            "name": "public_baseline",
            "include_internal_history": False,
            "model_config": None,
        },
        {
            "name": "history_hybrid_default",
            "include_internal_history": True,
            "model_config": None,
        },
        {
            "name": "history_hybrid_compact",
            "include_internal_history": True,
            "model_config": {
                "median": {"n_estimators": 160, "max_depth": 4, "learning_rate": 0.04},
                "lower": {"n_estimators": 80, "max_depth": 3, "learning_rate": 0.04},
                "upper": {"n_estimators": 80, "max_depth": 3, "learning_rate": 0.04},
            },
        },
        {
            "name": "history_hybrid_responsive",
            "include_internal_history": True,
            "model_config": {
                "median": {"n_estimators": 240, "max_depth": 4, "learning_rate": 0.03},
                "lower": {"n_estimators": 120, "max_depth": 4, "learning_rate": 0.03},
                "upper": {"n_estimators": 120, "max_depth": 4, "learning_rate": 0.03},
            },
        },
    ]

    def __init__(self, db: Session, models_dir: Path | None = None) -> None:
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self._forecast_svc = ForecastService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(
        self,
        virus_typ: str = "Influenza A",
        *,
        include_internal_history: bool = True,
        research_mode: bool = False,
        region: str | None = None,
        regions: list[str] | None = None,
        horizon_days: int | None = None,
        horizon_days_list: list[int] | None = None,
    ) -> dict[str, Any]:
        """Full training pipeline for a single virus type.
        """
        scope = normalize_scope_selection(
            region=region,
            regions=regions,
            horizon_days=horizon_days,
            horizon_days_list=horizon_days_list,
        )
        scoped_results: dict[str, Any] = {}
        for region_code in scope.regions:
            for horizon in scope.horizons:
                key = f"{region_code}:h{horizon}"
                scoped_results[key] = self._train_scoped(
                    virus_typ=virus_typ,
                    region=region_code,
                    horizon_days=horizon,
                    include_internal_history=include_internal_history,
                    research_mode=research_mode,
                )

        if len(scoped_results) == 1:
            return next(iter(scoped_results.values()))

        return {
            "virus_typ": virus_typ,
            "regions": list(scope.regions),
            "horizon_days_list": list(scope.horizons),
            "scopes": scoped_results,
        }

    def train_all(
        self,
        *,
        virus_types: list[str] | None = None,
        include_internal_history: bool = True,
        research_mode: bool = False,
        region: str | None = None,
        regions: list[str] | None = None,
        horizon_days: int | None = None,
        horizon_days_list: list[int] | None = None,
    ) -> dict[str, Any]:
        """Train models for all supported virus types."""
        scope = normalize_scope_selection(
            region=region,
            regions=regions,
            horizon_days=horizon_days,
            horizon_days_list=horizon_days_list,
        )
        results: dict[str, Any] = {}
        for virus in (virus_types or self.VIRUS_TYPES):
            try:
                results[virus] = self.train(
                    virus_typ=virus,
                    include_internal_history=include_internal_history,
                    research_mode=research_mode,
                    regions=list(scope.regions),
                    horizon_days_list=list(scope.horizons),
                )
            except Exception as e:
                logger.error(f"Training failed for {virus}: {e}", exc_info=True)
                results[virus] = {"error": str(e)}
        return results

    def _evaluate_candidates(
        self,
        *,
        virus_typ: str,
        include_internal_history: bool,
        research_mode: bool,
        region: str,
        horizon_days: int,
    ) -> list[dict[str, Any]]:
        raw_candidates = self.RESEARCH_CANDIDATES if research_mode else [
            {
                "name": "default_internal_history" if include_internal_history else "default_public_only",
                "include_internal_history": include_internal_history,
                "model_config": None,
            }
        ]

        summaries: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            if candidate["include_internal_history"] and not include_internal_history and research_mode:
                continue

            metrics = self._forecast_svc.evaluate_training_candidate(
                virus_typ=virus_typ,
                include_internal_history=bool(candidate["include_internal_history"]),
                model_config=candidate.get("model_config"),
                region=region,
                horizon_days=horizon_days,
            )
            summaries.append(
                {
                    "name": candidate["name"],
                    "include_internal_history": bool(candidate["include_internal_history"]),
                    "model_config": candidate.get("model_config"),
                    "backtest_metrics": metrics,
                }
            )
        return summaries

    def _train_scoped(
        self,
        *,
        virus_typ: str,
        region: str,
        horizon_days: int,
        include_internal_history: bool,
        research_mode: bool,
    ) -> dict[str, Any]:
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        logger.info("=== XGBoostTrainer: training for %s/%s/h%s ===", virus_typ, region_code, horizon)

        candidate_summaries = self._evaluate_candidates(
            virus_typ=virus_typ,
            include_internal_history=include_internal_history,
            research_mode=research_mode,
            region=region_code,
            horizon_days=horizon,
        )
        best_candidate = self._select_best_candidate(candidate_summaries)
        if not best_candidate:
            msg = f"No valid candidate found for {virus_typ}/{region_code}/h{horizon}"
            logger.warning(msg)
            return {
                "error": msg,
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
                "candidate_summaries": candidate_summaries,
            }

        df = self._forecast_svc.prepare_training_data(
            virus_typ=virus_typ,
            include_internal_history=bool(best_candidate["include_internal_history"]),
            region=region_code,
        )
        panel = self._forecast_svc._build_direct_training_panel_from_frame(
            df,
            horizon_days=horizon,
            n_splits=5,
        )
        if df.empty or panel.empty:
            msg = f"Insufficient data ({len(df)} raw rows / {len(panel)} panel rows) for {virus_typ}/{region_code}/h{horizon}"
            logger.warning(msg)
            return {
                "error": msg,
                "virus_typ": virus_typ,
                "region": region_code,
                "horizon_days": horizon,
            }

        model_med, model_lo, model_hi, feature_names, feature_importance = (
            self._forecast_svc._fit_xgboost_meta_from_panel(
                panel,
                target_column="y_target",
                model_config=best_candidate.get("model_config"),
            )
        )

        current_metadata = self._read_existing_metadata(
            virus_typ,
            region=region_code,
            horizon_days=horizon,
        )
        promoted = self._should_promote_candidate(
            existing_metrics=(current_metadata or {}).get("backtest_metrics"),
            candidate_metrics=best_candidate.get("backtest_metrics"),
        )

        prophet_mode = (
            "full_prophet"
            if region_code == DEFAULT_FORECAST_REGION
            else "proxy_rolling_mean"
        )
        model_dir = model_artifact_dir(
            self.models_dir,
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
        )
        backtest_metrics = best_candidate.get("backtest_metrics") or {}
        metadata: dict[str, Any] = {
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
            "training_samples": len(df),
            "panel_training_samples": len(panel),
            "feature_names": list(feature_names),
            "feature_importance": {k: float(v) for k, v in feature_importance.items()},
            "candidate_name": best_candidate["name"],
            "candidate_count": len(candidate_summaries),
            "candidate_summaries": candidate_summaries,
            "research_mode": research_mode,
            "data_sources": {
                "internal_history": bool(best_candidate["include_internal_history"]),
                "public_signals": True,
            },
            "training_window": backtest_metrics.get("training_window") or {
                "start": df["ds"].min().isoformat(),
                "end": df["ds"].max().isoformat(),
                "samples": int(len(df)),
                "panel_rows": int(len(panel)),
            },
            "backtest_metrics": backtest_metrics,
            "promotion_decision": {
                "promoted": promoted,
                "scoped_to": {
                    "region": region_code,
                    "horizon_days": horizon,
                },
                "existing_live_model_found": current_metadata is not None,
            },
            "promoted": promoted,
            "promoted_at": datetime.utcnow().isoformat() if promoted else None,
            "rejected_reason": None if promoted else "candidate_did_not_beat_live_model",
            "prophet_mode": prophet_mode,
            "model_dir": str(model_dir),
        }

        if promoted:
            metadata = self._save_models(
                virus_typ=virus_typ,
                region=region_code,
                horizon_days=horizon,
                model_median=model_med,
                model_lower=model_lo,
                model_upper=model_hi,
                feature_names=list(feature_names),
                feature_importance=feature_importance,
                training_samples=len(df),
                metadata_overrides=metadata,
            )
            try:
                from app.services.ml.forecast_service import invalidate_model_cache
                invalidate_model_cache(virus_typ)
            except ImportError:
                pass
        else:
            metadata["existing_live_model"] = current_metadata

        logger.info(
            "XGBoostTrainer: %s candidate %s for %s/%s/h%s → %s",
            "promoted" if promoted else "kept existing model after evaluating",
            best_candidate["name"],
            virus_typ,
            region_code,
            horizon,
            metadata["model_dir"],
        )
        return metadata

    @staticmethod
    def _select_best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        valid = [item for item in candidates if "error" not in (item.get("backtest_metrics") or {})]
        if not valid:
            return None
        return min(
            valid,
            key=lambda item: (
                float(item["backtest_metrics"].get("mape", float("inf"))),
                float(item["backtest_metrics"].get("rmse", float("inf"))),
                item["name"],
            ),
        )

    @staticmethod
    def _should_promote_candidate(
        *,
        existing_metrics: dict[str, Any] | None,
        candidate_metrics: dict[str, Any] | None,
    ) -> bool:
        if not candidate_metrics or "error" in candidate_metrics:
            return False
        if not existing_metrics or "mape" not in existing_metrics:
            return True

        candidate_mape = float(candidate_metrics.get("mape", float("inf")))
        existing_mape = float(existing_metrics.get("mape", float("inf")))
        if candidate_mape < existing_mape:
            return True
        if candidate_mape > existing_mape:
            return False
        return float(candidate_metrics.get("rmse", float("inf"))) < float(
            existing_metrics.get("rmse", float("inf")),
        )

    def _read_existing_metadata(
        self,
        virus_typ: str,
        *,
        region: str,
        horizon_days: int,
    ) -> dict[str, Any] | None:
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        metadata_path = model_artifact_dir(
            self.models_dir,
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
        ) / "metadata.json"
        if not metadata_path.exists() and region_code == DEFAULT_FORECAST_REGION and horizon == 7:
            metadata_path = self.models_dir / _virus_slug(virus_typ) / "metadata.json"
        if not metadata_path.exists():
            return None
        try:
            with open(metadata_path) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not read metadata for %s: %s", virus_typ, exc)
            return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _save_models(
        self,
        virus_typ: str,
        *,
        region: str,
        horizon_days: int,
        model_median: Any,
        model_lower: Any,
        model_upper: Any,
        feature_names: list[str],
        feature_importance: dict[str, float],
        training_samples: int,
        metadata_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Serialise 3 XGBoost models + metadata sidecar to disk.

        Uses atomic write (temp file + rename) to avoid partial reads
        during concurrent inference.
        """
        region_code = normalize_forecast_region(region)
        horizon = ensure_supported_horizon(horizon_days)
        model_dir = model_artifact_dir(
            self.models_dir,
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
        )
        model_dir.mkdir(parents=True, exist_ok=True)

        # Atomic save helper
        def _atomic_save_model(model: Any, target: Path) -> None:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(model_dir), suffix=".tmp.json",
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
            "region": region_code,
            "horizon_days": horizon,
            "version": f"xgb_stack_direct_{region_code.lower()}_h{horizon}_{now.strftime('%Y%m%dT%H%M')}",
            "trained_at": now.isoformat(),
            "training_samples": training_samples,
            "feature_names": feature_names,
            "feature_importance": {
                k: float(v) for k, v in feature_importance.items()
            },
            "model_dir": str(model_dir),
        }
        if metadata_overrides:
            metadata.update(metadata_overrides)

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
