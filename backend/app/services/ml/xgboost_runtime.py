from __future__ import annotations

import os
import re
from typing import Any


_CUDA_DEVICE_PATTERN = re.compile(r"^cuda:\d+$")


def resolve_xgboost_runtime_device(device: str | None = None) -> str | None:
    raw_value = str(
        device if device is not None else os.getenv("REGIONAL_XGBOOST_DEVICE", "cpu")
    ).strip().lower()
    if raw_value in {"", "cpu"}:
        return None
    if raw_value in {"gpu", "cuda"}:
        return "cuda"
    if _CUDA_DEVICE_PATTERN.match(raw_value):
        return raw_value
    raise ValueError(
        "REGIONAL_XGBOOST_DEVICE must be 'cpu', 'cuda', 'gpu', or 'cuda:<index>'."
    )


def resolve_xgboost_runtime_config(
    config: dict[str, Any] | None,
    *,
    device: str | None = None,
) -> dict[str, Any]:
    resolved = dict(config or {})
    runtime_device = resolve_xgboost_runtime_device(device)
    if runtime_device is None:
        return resolved
    resolved["device"] = runtime_device
    resolved.setdefault("tree_method", "hist")
    return resolved
