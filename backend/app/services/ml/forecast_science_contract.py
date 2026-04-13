"""Canonical science-contract metadata for the h7 champion forecast path."""

from __future__ import annotations

from typing import Any

SCIENCE_CONTRACT_VERSION = "regional_h7_science_contract_v2"
QUANTILE_GRID_VERSION = "canonical_quantile_grid_v1"
CHAMPION_MODEL_FAMILY = "regional_pooled_panel"
LEGACY_FORECAST_PATH_ROLE = "legacy_benchmark_admin"
CALIBRATION_EVIDENCE_MODE = "oof_predictions_only"
CANONICAL_FORECAST_QUANTILES: tuple[float, ...] = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)

ACTIVE_H7_CHAMPION_SCOPES: tuple[tuple[str, int], ...] = (
    ("Influenza A", 7),
    ("Influenza B", 7),
)


def is_active_h7_champion_scope(virus_typ: str, horizon_days: int) -> bool:
    return (str(virus_typ or "").strip(), int(horizon_days or 0)) in ACTIVE_H7_CHAMPION_SCOPES


def champion_scope_reason(virus_typ: str, horizon_days: int) -> str:
    normalized_virus = str(virus_typ or "").strip()
    horizon = int(horizon_days or 0)
    if is_active_h7_champion_scope(normalized_virus, horizon):
        return "Active h7 champion scope in the first product phase."
    if horizon != 7:
        return "Only h7 is an active champion scope in the first product phase."
    if normalized_virus == "RSV A":
        return "RSV A / h7 remains watch/shadow-only until the residual forecast path is promoted separately."
    if normalized_virus == "SARS-CoV-2":
        return "SARS-CoV-2 / h7 remains shadow/watch-only in the first champion phase."
    return "Scope remains benchmark/debug only until it is explicitly promoted."


def default_science_contract_metadata(
    *,
    virus_typ: str,
    horizon_days: int,
    calibration_mode: str,
    event_definition_version: str,
    metric_semantics_version: str,
    forecast_quantiles: list[float] | tuple[float, ...] | None = None,
) -> dict[str, Any]:
    quantiles = [float(value) for value in (forecast_quantiles or CANONICAL_FORECAST_QUANTILES)]
    return {
        "science_contract_version": SCIENCE_CONTRACT_VERSION,
        "quantile_grid_version": QUANTILE_GRID_VERSION,
        "forecast_quantiles": quantiles,
        "metric_semantics_version": str(metric_semantics_version or "").strip() or None,
        "event_definition_version": str(event_definition_version or "").strip() or None,
        "calibration_mode": str(calibration_mode or "").strip() or "raw_passthrough",
        "calibration_evidence_mode": CALIBRATION_EVIDENCE_MODE,
        "champion_scope_active": is_active_h7_champion_scope(virus_typ, horizon_days),
        "champion_scope_reason": champion_scope_reason(virus_typ, horizon_days),
        "champion_model_family": CHAMPION_MODEL_FAMILY,
    }
