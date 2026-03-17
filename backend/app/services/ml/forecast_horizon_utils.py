"""Shared utilities for direct multi-horizon stacking forecasts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.forecast_contracts import DEFAULT_DECISION_EVENT_THRESHOLD_PCT


SUPPORTED_FORECAST_HORIZONS: tuple[int, int, int] = (3, 5, 7)
DEFAULT_FORECAST_REGION = "DE"
MIN_DIRECT_TRAIN_POINTS = 60


@dataclass(frozen=True)
class HorizonSplit:
    train_end_idx: int
    test_idx: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def normalize_forecast_region(region: str | None) -> str:
    text = str(region or DEFAULT_FORECAST_REGION).strip().upper()
    return text or DEFAULT_FORECAST_REGION


def ensure_supported_horizon(horizon_days: int) -> int:
    horizon = int(horizon_days or 0)
    if horizon not in SUPPORTED_FORECAST_HORIZONS:
        raise ValueError(f"Unsupported forecast horizon: {horizon_days}")
    return horizon


def horizon_artifact_subdir(horizon_days: int) -> str:
    horizon = ensure_supported_horizon(horizon_days)
    return f"horizon_{horizon}"


def model_artifact_dir(
    models_dir: Path,
    *,
    virus_typ: str,
    region: str,
    horizon_days: int,
) -> Path:
    virus_slug = virus_typ.lower().replace(" ", "_").replace("-", "_")
    region_slug = normalize_forecast_region(region).lower()
    return Path(models_dir) / virus_slug / region_slug / horizon_artifact_subdir(horizon_days)


def regional_model_artifact_dir(
    models_dir: Path,
    *,
    virus_typ: str,
    horizon_days: int,
) -> Path:
    virus_slug = virus_typ.lower().replace(" ", "_").replace("-", "_")
    return Path(models_dir) / virus_slug / horizon_artifact_subdir(horizon_days)


def build_direct_target_frame(
    frame: pd.DataFrame,
    *,
    horizon_days: int,
    threshold_pct: float = DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
) -> pd.DataFrame:
    horizon = ensure_supported_horizon(horizon_days)
    if frame.empty:
        return pd.DataFrame()

    direct = frame.copy().sort_values("ds").reset_index(drop=True)
    direct["y_target"] = direct["y"].shift(-horizon)
    direct["current_y"] = direct["y"].astype(float)
    direct["growth_target_pct"] = (
        (direct["y_target"] - direct["current_y"]) / direct["current_y"].replace(0.0, np.nan)
    ) * 100.0
    direct["event_target"] = (
        (direct["y_target"] >= direct["current_y"] * (1.0 + float(threshold_pct) / 100.0))
        & direct["y_target"].notna()
    ).astype(float)
    direct["horizon_days"] = float(horizon)
    direct = direct.iloc[:-horizon].copy() if len(direct) > horizon else pd.DataFrame(columns=direct.columns)
    if direct.empty:
        return direct
    direct["issue_date"] = pd.to_datetime(direct["ds"]).dt.normalize()
    direct["target_date"] = pd.to_datetime(direct["ds"]).dt.normalize() + pd.Timedelta(days=horizon)
    return direct.reset_index(drop=True)


def build_walk_forward_splits(
    n_rows: int,
    *,
    min_train_points: int = MIN_DIRECT_TRAIN_POINTS,
    n_splits: int = 5,
) -> list[HorizonSplit]:
    if n_rows <= max(min_train_points, 1):
        return []

    start = max(int(min_train_points), 1)
    end = n_rows - 1
    candidates = np.linspace(start, end, num=min(int(n_splits), max(end - start + 1, 1)), dtype=int)
    splits: list[HorizonSplit] = []
    seen: set[int] = set()
    for idx in candidates.tolist():
        if idx in seen or idx <= start:
            continue
        seen.add(idx)
        splits.append(HorizonSplit(train_end_idx=int(idx), test_idx=int(idx)))
    return splits


def compute_regression_metrics(predicted: list[float], actual: list[float]) -> dict[str, float]:
    pred_arr = np.asarray(predicted, dtype=float)
    act_arr = np.asarray(actual, dtype=float)
    if len(pred_arr) == 0 or len(act_arr) == 0:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "correlation": 0.0}

    errors = pred_arr - act_arr
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    nonzero = np.abs(act_arr) > 1e-9
    mape = float(np.mean(np.abs(errors[nonzero] / act_arr[nonzero])) * 100.0) if nonzero.any() else 0.0
    correlation = 0.0
    if len(pred_arr) >= 3 and float(np.std(pred_arr)) > 0.0 and float(np.std(act_arr)) > 0.0:
        correlation = float(np.corrcoef(pred_arr, act_arr)[0, 1])
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 2),
        "correlation": round(correlation, 4),
    }


def compute_calibration_error(
    probabilities: list[float],
    labels: list[float],
    *,
    n_bins: int = 10,
) -> dict[str, float]:
    if not probabilities or not labels:
        return {"ece": 0.0, "brier_score": 0.0}

    probs = np.clip(np.asarray(probabilities, dtype=float), 0.0, 1.0)
    obs = np.asarray(labels, dtype=float)
    brier = float(np.mean((probs - obs) ** 2))

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for left, right in zip(bins[:-1], bins[1:]):
        if right >= 1.0:
            mask = (probs >= left) & (probs <= right)
        else:
            mask = (probs >= left) & (probs < right)
        if not mask.any():
            continue
        bin_conf = float(np.mean(probs[mask]))
        bin_acc = float(np.mean(obs[mask]))
        ece += abs(bin_acc - bin_conf) * (float(np.sum(mask)) / float(len(probs)))

    return {
        "ece": round(float(ece), 4),
        "brier_score": round(brier, 4),
    }
