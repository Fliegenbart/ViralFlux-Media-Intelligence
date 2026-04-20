from __future__ import annotations

from pathlib import Path
from typing import Any


def train_all_regions(
    trainer,
    *,
    virus_typ: str = "Influenza A",
    lookback_days: int = 900,
    persist: bool = True,
    horizon_days: int = 7,
    horizon_days_list: list[int] | None = None,
    weather_forecast_vintage_mode: str | None = None,
    weather_vintage_comparison: bool = False,
) -> dict[str, Any]:
    horizons = trainer._selected_horizons(
        horizon_days=horizon_days,
        horizon_days_list=horizon_days_list,
    )
    if len(horizons) > 1:
        scopes = {
            f"h{horizon}": trainer.train_all_regions(
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
                1 for payload in scopes.values() if (payload or {}).get("status") == "unsupported"
            ),
            "scopes": scopes,
            "aggregate_metrics": {
                key: (payload or {}).get("aggregate_metrics") or {}
                for key, payload in scopes.items()
            },
            "quality_gate": {
                key: (payload or {}).get("quality_gate") or {} for key, payload in scopes.items()
            },
        }

    return trainer._train_single_horizon(
        virus_typ=virus_typ,
        lookback_days=lookback_days,
        persist=persist,
        horizon_days=horizons[0],
        weather_forecast_vintage_mode=weather_forecast_vintage_mode,
        weather_vintage_comparison=weather_vintage_comparison,
    )


def train_all_viruses_all_regions(
    trainer,
    *,
    lookback_days: int = 900,
    horizon_days: int = 7,
    weather_forecast_vintage_mode: str | None = None,
    weather_vintage_comparison: bool = False,
    supported_virus_types,
) -> dict[str, Any]:
    return trainer.train_selected_viruses_all_regions(
        virus_types=supported_virus_types,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
        weather_forecast_vintage_mode=weather_forecast_vintage_mode,
        weather_vintage_comparison=weather_vintage_comparison,
    )


def train_selected_viruses_all_regions(
    trainer,
    *,
    virus_types: list[str] | tuple[str, ...],
    lookback_days: int = 900,
    horizon_days: int = 7,
    horizon_days_list: list[int] | None = None,
    weather_forecast_vintage_mode: str | None = None,
    weather_vintage_comparison: bool = False,
) -> dict[str, Any]:
    """Train all regions for each virus, mit Per-Virus-Error-Isolation.

    Ohne try/except würde ein Fehler oder Timeout bei einem Virus (etwa
    Calibration-Fit-Failure bei Influenza A) die Schleife abbrechen —
    die restlichen Viren kriegen kein Update. Mit per-Virus-Catch laufen
    Flu B / RSV A durch, selbst wenn Flu A explodiert. Der Fehler steht
    dann als ``{"status": "error", "error": "..."}`` im Ergebnis-Dict.
    """
    import logging
    log = logging.getLogger(__name__)
    out: dict[str, Any] = {}
    for virus_typ in virus_types:
        try:
            out[virus_typ] = trainer.train_all_regions(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
                horizon_days=horizon_days,
                horizon_days_list=horizon_days_list,
                weather_forecast_vintage_mode=weather_forecast_vintage_mode,
                weather_vintage_comparison=weather_vintage_comparison,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "Regional training failed for %s — continuing with remaining viruses",
                virus_typ,
            )
            out[virus_typ] = {
                "status": "error",
                "virus_typ": virus_typ,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
    return out


def load_artifacts(
    trainer,
    *,
    virus_typ: str,
    horizon_days: int = 7,
    ensure_supported_horizon_fn,
    regional_model_artifact_dir_fn,
    target_window_for_horizon_fn,
    supported_forecast_horizons,
    training_only_panel_columns,
    virus_slug_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    model_dir = regional_model_artifact_dir_fn(
        trainer.models_dir,
        virus_typ=virus_typ,
        horizon_days=horizon,
    )
    if model_dir.exists() and not trainer._artifact_payload_from_dir(model_dir):
        return {
            "load_error": f"Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig."
        }
    payload = trainer._artifact_payload_from_dir(model_dir)
    if payload:
        metadata = payload.setdefault("metadata", {})
        metadata.setdefault("horizon_days", horizon)
        metadata.setdefault("target_window_days", target_window_for_horizon_fn(horizon))
        metadata.setdefault("supported_horizon_days", list(supported_forecast_horizons))
        invalid_feature_columns = sorted(
            {
                str(column)
                for column in (metadata.get("feature_columns") or [])
                if str(column) in training_only_panel_columns
            }
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

    legacy_dir = trainer.models_dir / virus_slug_fn(virus_typ)
    if legacy_dir.exists() and not trainer._artifact_payload_from_dir(legacy_dir):
        return {
            "load_error": f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} ist unvollständig."
        }
    legacy_payload = trainer._artifact_payload_from_dir(legacy_dir)
    if not legacy_payload:
        return {}

    metadata = dict(legacy_payload.get("metadata") or {})
    metadata.setdefault("horizon_days", horizon)
    metadata["target_window_days"] = metadata.get("target_window_days") or target_window_for_horizon_fn(
        horizon
    )
    metadata["artifact_transition_mode"] = "legacy_default_window_fallback"
    metadata["requested_horizon_days"] = horizon
    metadata["artifact_dir"] = str(legacy_dir)
    legacy_payload["metadata"] = metadata
    legacy_payload["artifact_transition_mode"] = "legacy_default_window_fallback"
    invalid_feature_columns = sorted(
        {
            str(column)
            for column in (metadata.get("feature_columns") or [])
            if str(column) in training_only_panel_columns
        }
    )
    if invalid_feature_columns:
        legacy_payload["load_error"] = (
            f"Legacy-Artefakt-Bundle für {virus_typ}/h{horizon} enthält trainingsinterne "
            f"Feature-Spalten: {', '.join(invalid_feature_columns)}. "
            "Bitte horizon-spezifisches Retraining durchführen."
        )
    return legacy_payload


def artifact_payload_from_dir(model_dir: Path, *, json_module) -> dict[str, Any]:
    model_dir = Path(model_dir)
    if not model_dir.exists():
        return {}
    payload: dict[str, Any] = {}
    meta_path = model_dir / "metadata.json"
    backtest_path = model_dir / "backtest.json"
    point_in_time_path = model_dir / "point_in_time_snapshot.json"
    if meta_path.exists():
        payload["metadata"] = json_module.loads(meta_path.read_text())
    if backtest_path.exists():
        payload["backtest"] = json_module.loads(backtest_path.read_text())
    if point_in_time_path.exists():
        payload["point_in_time_snapshot"] = json_module.loads(point_in_time_path.read_text())
    return payload
