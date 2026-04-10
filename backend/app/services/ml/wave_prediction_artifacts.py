"""Artifact persistence and inference helpers for wave prediction."""

from __future__ import annotations

import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


def persist_artifacts(
    service: Any,
    *,
    pathogen: str,
    regressor_bundle: dict[str, Any],
    classifier_bundle: dict[str, Any],
    metadata: dict[str, Any],
    backtest: dict[str, Any],
    dataset_manifest: dict[str, Any],
    pathogen_slug_fn: Any,
    atomic_pickle_dump_fn: Any,
    atomic_json_dump_fn: Any,
) -> None:
    model_dir = service.models_dir / pathogen_slug_fn(pathogen)
    model_dir.mkdir(parents=True, exist_ok=True)

    service._atomic_save_model(regressor_bundle["regressor"], model_dir / "regressor.json")
    service._atomic_save_model(classifier_bundle["classifier"], model_dir / "classifier.json")
    if classifier_bundle.get("calibration") is not None:
        atomic_pickle_dump_fn(classifier_bundle["calibration"], model_dir / "calibration.pkl")
    elif (model_dir / "calibration.pkl").exists():
        (model_dir / "calibration.pkl").unlink()

    atomic_json_dump_fn(metadata, model_dir / "metadata.json")
    atomic_json_dump_fn(backtest, model_dir / "backtest.json")
    atomic_json_dump_fn(dataset_manifest, model_dir / "dataset_manifest.json")


def load_artifacts(
    service: Any,
    pathogen: str,
    *,
    pathogen_slug_fn: Any,
    regressor_cls: Any,
    classifier_cls: Any,
    pickle_module: Any,
) -> dict[str, Any]:
    model_dir = service.models_dir / pathogen_slug_fn(pathogen)
    if not model_dir.exists():
        return {}
    paths = {
        "regressor": model_dir / "regressor.json",
        "classifier": model_dir / "classifier.json",
        "calibration": model_dir / "calibration.pkl",
        "metadata": model_dir / "metadata.json",
        "backtest": model_dir / "backtest.json",
        "dataset_manifest": model_dir / "dataset_manifest.json",
    }
    if not paths["regressor"].exists() or not paths["classifier"].exists():
        return {}

    regressor = regressor_cls()
    regressor.load_model(str(paths["regressor"]))
    classifier = classifier_cls()
    classifier.load_model(str(paths["classifier"]))
    calibration = None
    if paths["calibration"].exists():
        with open(paths["calibration"], "rb") as handle:
            calibration = pickle_module.load(handle)

    return {
        "regressor": regressor,
        "classifier": classifier,
        "calibration": calibration,
        "metadata": service._load_json(paths["metadata"]),
        "backtest": service._load_json(paths["backtest"]),
        "dataset_manifest": service._load_json(paths["dataset_manifest"]),
    }


def run_wave_prediction(
    service: Any,
    *,
    pathogen: str,
    region: str,
    horizon_days: int,
    normalize_virus_type_fn: Any,
    normalize_state_code_fn: Any,
    get_regression_feature_columns_fn: Any,
    get_classification_feature_columns_fn: Any,
    utc_now_fn: Any,
    np_module: Any,
) -> dict[str, Any]:
    normalized_pathogen = normalize_virus_type_fn(pathogen)
    region_code = normalize_state_code_fn(region) or region.upper()
    artifacts = service._load_artifacts(normalized_pathogen)
    metadata = artifacts.get("metadata") or {}
    regressor = artifacts.get("regressor")
    classifier = artifacts.get("classifier")
    if regressor is None or classifier is None:
        return {
            "pathogen": normalized_pathogen,
            "region": region_code,
            "generated_at": utc_now_fn().isoformat(),
            "horizon_days": int(horizon_days),
            "model_version": None,
            "top_features": {},
            "notes": ["No trained wave prediction artifacts available."],
        }

    panel = service.build_wave_panel(
        pathogen=normalized_pathogen,
        region=region_code,
        lookback_days=max(int(service.settings.WAVE_PREDICTION_MIN_TRAIN_PERIODS), 90),
        horizon_days=horizon_days,
    )
    if panel.empty:
        return {
            "pathogen": normalized_pathogen,
            "region": region_code,
            "generated_at": utc_now_fn().isoformat(),
            "horizon_days": int(horizon_days),
            "model_version": metadata.get("model_version"),
            "top_features": metadata.get("top_features") or {},
            "notes": ["No inference row could be built for the requested region."],
        }

    row = panel.sort_values("as_of_date").tail(1).reset_index(drop=True)
    regression_columns = metadata.get("regression_feature_columns") or get_regression_feature_columns_fn(row)
    classification_columns = metadata.get("classification_feature_columns") or get_classification_feature_columns_fn(row)
    x_reg = row[regression_columns].fillna(0.0).to_numpy(dtype=float)
    x_clf = row[classification_columns].fillna(0.0).to_numpy(dtype=float)
    regression_forecast = float(np_module.expm1(regressor.predict(x_reg))[0])
    raw_score = float(classifier.predict_proba(x_clf)[:, 1][0])
    calibration = artifacts.get("calibration")
    threshold = float(
        metadata.get("classification_threshold")
        or service.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD
    )
    notes: list[str] = []
    payload = {
        "pathogen": normalized_pathogen,
        "region": region_code,
        "generated_at": utc_now_fn().isoformat(),
        "horizon_days": int(horizon_days),
        "regression_forecast": round(max(regression_forecast, 0.0), 4),
        "model_version": metadata.get("model_version"),
        "top_features": metadata.get("top_features") or {},
        "notes": notes,
    }
    if calibration is not None:
        wave_probability = float(
            np_module.clip(service._apply_calibration(calibration, np_module.array([raw_score]))[0], 0.0, 1.0)
        )
        payload["wave_probability"] = round(wave_probability, 6)
        payload["wave_flag"] = bool(wave_probability >= threshold)
    else:
        payload["wave_score"] = round(raw_score, 6)
        payload["wave_flag"] = bool(raw_score >= threshold)
        notes.append(
            "Classifier output is uncalibrated; returning wave_score instead of wave_probability."
        )
    return payload


def atomic_save_model(model: Any, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp.json")
    os.close(fd)
    try:
        model.save_model(tmp_path)
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
