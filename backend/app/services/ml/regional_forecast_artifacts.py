"""Artifact loading helper functions for regional forecast service."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bootstrap_command(*, supported_horizons: list[int]) -> str:
    horizon_args = " ".join(f"--horizon {int(h)}" for h in sorted(set(supported_horizons)))
    return f"cd backend && python scripts/backfill_regional_model_artifacts.py {horizon_args}".strip()


def build_artifact_diagnostic(
    *,
    virus_typ: str,
    horizon_days: int,
    artifact_dir: Path,
    missing_files: list[str],
    load_error: str,
    supported_horizons: list[int],
    artifact_transition_mode: str | None = None,
) -> dict[str, Any]:
    status = "missing"
    if missing_files:
        status = "incomplete"
    elif load_error:
        status = "invalid"

    bootstrap = bootstrap_command(supported_horizons=supported_horizons)
    operator_message = (
        f"Regionales Modellartefakt für {virus_typ}/h{horizon_days} fehlt. "
        f"Bitte den Bootstrap ausführen: {bootstrap}"
    )
    if status == "incomplete":
        operator_message = (
            f"Artefakt-Bundle für {virus_typ}/h{horizon_days} ist unvollständig: "
            f"{', '.join(missing_files)}. "
            f"Bitte den Bootstrap ausführen: {bootstrap}"
        )
    if status == "invalid" and load_error:
        operator_message = f"{load_error} Bootstrap: {bootstrap}"

    return {
        "status": status,
        "artifact_scope": {"virus_typ": virus_typ, "horizon_days": int(horizon_days)},
        "artifact_dir": str(artifact_dir),
        "missing_files": list(missing_files),
        "bootstrap_required": True,
        "operator_message": operator_message,
        "bootstrap_command": bootstrap,
        "artifact_transition_mode": artifact_transition_mode,
        "load_error": load_error or None,
    }


def load_artifacts(
    service,
    *,
    virus_typ: str,
    horizon_days: int,
    ensure_supported_horizon_fn,
    regional_model_artifact_dir_fn,
    supported_forecast_horizons,
    target_window_days,
    virus_slug_fn,
    training_only_panel_columns,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    model_dir = regional_model_artifact_dir_fn(
        service.models_dir,
        virus_typ=virus_typ,
        horizon_days=horizon,
    )
    if not model_dir.exists():
        if horizon != 7:
            return {
                "artifact_diagnostic": build_artifact_diagnostic(
                    virus_typ=virus_typ,
                    horizon_days=horizon,
                    artifact_dir=model_dir,
                    missing_files=[],
                    load_error="",
                    supported_horizons=list(supported_forecast_horizons),
                )
            }
    else:
        missing_files = service._missing_artifact_files(model_dir)
        if missing_files:
            return {
                "load_error": (
                    f"Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig: "
                    f"{', '.join(missing_files)}"
                ),
                "artifact_diagnostic": build_artifact_diagnostic(
                    virus_typ=virus_typ,
                    horizon_days=horizon,
                    artifact_dir=model_dir,
                    missing_files=missing_files,
                    load_error=f"Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig.",
                    supported_horizons=list(supported_forecast_horizons),
                ),
            }
    payload = service._artifact_payload_from_dir(model_dir)
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
        metadata.setdefault("target_window_days", service._target_window_for_horizon(horizon))
        metadata.setdefault("supported_horizon_days", list(supported_forecast_horizons))
        invalid_feature_columns = service._invalid_inference_feature_columns(
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
        return {
            "artifact_diagnostic": build_artifact_diagnostic(
                virus_typ=virus_typ,
                horizon_days=horizon,
                artifact_dir=model_dir,
                missing_files=[],
                load_error="",
                supported_horizons=list(supported_forecast_horizons),
            )
        }

    legacy_dir = service.models_dir / virus_slug_fn(virus_typ)
    if legacy_dir.exists():
        missing_files = service._missing_artifact_files(legacy_dir)
        if missing_files:
            return {
                "load_error": (
                    f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig: "
                    f"{', '.join(missing_files)}"
                ),
                "artifact_diagnostic": build_artifact_diagnostic(
                    virus_typ=virus_typ,
                    horizon_days=horizon,
                    artifact_dir=legacy_dir,
                    missing_files=missing_files,
                    load_error=(
                        f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig."
                    ),
                    supported_horizons=list(supported_forecast_horizons),
                    artifact_transition_mode="legacy_default_window_fallback",
                ),
            }
    legacy_payload = service._artifact_payload_from_dir(legacy_dir)
    if not legacy_payload:
        return {
            "artifact_diagnostic": build_artifact_diagnostic(
                virus_typ=virus_typ,
                horizon_days=horizon,
                artifact_dir=legacy_dir,
                missing_files=[],
                load_error="",
                supported_horizons=list(supported_forecast_horizons),
                artifact_transition_mode="legacy_default_window_fallback",
            )
        }

    metadata = dict(legacy_payload.get("metadata") or {})
    metadata["horizon_days"] = horizon
    metadata["target_window_days"] = metadata.get("target_window_days") or list(target_window_days)
    metadata["requested_horizon_days"] = horizon
    metadata["supported_horizon_days"] = list(supported_forecast_horizons)
    metadata["artifact_transition_mode"] = "legacy_default_window_fallback"
    legacy_payload["metadata"] = metadata
    legacy_payload["artifact_transition_mode"] = "legacy_default_window_fallback"
    invalid_feature_columns = service._invalid_inference_feature_columns(
        metadata.get("feature_columns") or []
    )
    if invalid_feature_columns:
        legacy_payload["load_error"] = (
            f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} enthält trainingsinterne "
            f"Feature-Spalten: {', '.join(invalid_feature_columns)}. "
            "Bitte horizon-spezifisches Retraining durchführen."
        )
    return legacy_payload


def required_artifact_paths(model_dir: Path) -> dict[str, Path]:
    return {
        "classifier": model_dir / "classifier.json",
        "regressor_median": model_dir / "regressor_median.json",
        "regressor_lower": model_dir / "regressor_lower.json",
        "regressor_upper": model_dir / "regressor_upper.json",
        "calibration": model_dir / "calibration.pkl",
        "metadata": model_dir / "metadata.json",
    }


def missing_artifact_files(
    model_dir: Path,
    *,
    required_artifact_paths_fn,
) -> list[str]:
    return [
        path.name
        for path in required_artifact_paths_fn(model_dir).values()
        if not path.exists()
    ]


def invalid_inference_feature_columns(
    feature_columns: list[str],
    *,
    training_only_panel_columns,
) -> list[str]:
    return sorted(
        {
            str(column)
            for column in feature_columns
            if str(column) in training_only_panel_columns
        }
    )


def artifact_payload_from_dir(
    model_dir: Path,
    *,
    required_artifact_paths_fn,
    xgb_classifier_cls,
    xgb_regressor_cls,
    json_module,
    pickle_module,
) -> dict[str, Any]:
    required_paths = required_artifact_paths_fn(model_dir)
    if not all(path.exists() for path in required_paths.values()):
        return {}

    classifier = xgb_classifier_cls()
    classifier.load_model(str(required_paths["classifier"]))
    regressor_median = xgb_regressor_cls()
    regressor_median.load_model(str(required_paths["regressor_median"]))
    regressor_lower = xgb_regressor_cls()
    regressor_lower.load_model(str(required_paths["regressor_lower"]))
    regressor_upper = xgb_regressor_cls()
    regressor_upper.load_model(str(required_paths["regressor_upper"]))
    metadata = json_module.loads(required_paths["metadata"].read_text())
    hierarchy_models: dict[str, dict[str, Any]] = {}
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
        bundle: dict[str, Any] = {}
        for name, path in level_paths.items():
            model = xgb_regressor_cls()
            model.load_model(str(path))
            bundle[name] = model
        hierarchy_models[level] = bundle
    quantile_regressors: dict[float, Any] = {}
    for quantile in metadata.get("forecast_quantiles") or []:
        quantile_path = model_dir / f"q{int(round(float(quantile) * 1000)):04d}.json"
        if not quantile_path.exists():
            continue
        model = xgb_regressor_cls()
        model.load_model(str(quantile_path))
        quantile_regressors[float(quantile)] = model
    with open(required_paths["calibration"], "rb") as handle:
        calibration = pickle_module.load(handle)
    forecast_implied_calibration_path = model_dir / "forecast_implied_calibration.pkl"
    forecast_implied_calibration = None
    if forecast_implied_calibration_path.exists():
        with open(forecast_implied_calibration_path, "rb") as handle:
            forecast_implied_calibration = pickle_module.load(handle)
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
        "forecast_implied_calibration": forecast_implied_calibration,
        "metadata": metadata,
        "dataset_manifest": json_module.loads(dataset_manifest_path.read_text()) if dataset_manifest_path.exists() else None,
        "point_in_time_snapshot": json_module.loads(point_in_time_path.read_text()) if point_in_time_path.exists() else None,
    }


def apply_calibration(calibration: Any, raw_probabilities: Any, *, np_module) -> Any:
    if calibration is None:
        return np_module.clip(raw_probabilities.astype(float), 0.001, 0.999)
    return np_module.clip(calibration.predict(raw_probabilities.astype(float)), 0.001, 0.999)
