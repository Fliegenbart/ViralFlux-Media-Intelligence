"""GPU-aware runtime helpers for experimental Tri-Layer XGBoost challengers."""

from __future__ import annotations

from typing import Any

from app.services.ml.xgboost_runtime import resolve_xgboost_runtime_config


def resolve_tri_layer_xgboost_config(
    config: dict[str, Any] | None,
    *,
    device: str | None = None,
) -> dict[str, Any]:
    """Resolve XGBoost config using the shared regional runtime switch.

    Tri-Layer research jobs intentionally reuse ``REGIONAL_XGBOOST_DEVICE`` so
    local dev and CI stay CPU-only by default, while GPU workers can opt in
    with the same cuda/cuda:<index> convention as regional training.
    """
    return resolve_xgboost_runtime_config(config, device=device)
