"""Canonical shared utilities for learned probability calibration helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, log_loss

from app.services.ml.forecast_contracts import DEFAULT_DECISION_EVENT_THRESHOLD_PCT


SUPPORTED_FORECAST_HORIZONS: tuple[int, int, int] = (3, 5, 7)
DEFAULT_FORECAST_REGION = "DE"
MIN_DIRECT_TRAIN_POINTS = 60
DEFAULT_WALK_FORWARD_STRIDE = 1
DEFAULT_CALIBRATION_HOLDOUT_FRACTION = 0.20
DEFAULT_CALIBRATION_GUARD_FRACTION = 0.35
MIN_CALIBRATION_TRAIN_DATES = 20
MIN_CALIBRATION_TOTAL_DATES = 35
MIN_CALIBRATION_HOLDOUT_DATES = 14
MIN_CALIBRATION_GUARD_DATES = 7
DEFAULT_ISOTONIC_MIN_SAMPLES = 40
DEFAULT_ISOTONIC_MIN_CLASS_SUPPORT = 8
DEFAULT_PLATT_MIN_SAMPLES = 12
DEFAULT_PLATT_MIN_CLASS_SUPPORT = 2
CALIBRATION_GUARD_EPSILON = 1e-9

# Product-level support matrix for the operational regional path.
# Empty means "supported unless explicitly excluded".
REGIONAL_UNSUPPORTED_HORIZON_REASONS: dict[str, dict[int, str]] = {
    "RSV A": {
        3: (
            "Regional h3 is unsupported for RSV A because the pooled panel does not "
            "currently provide enough stable training rows for this scope."
        ),
    },
}

# Day-one pilot contract. Scopes not listed here remain technically supported,
# but are not part of the official pilot release until explicitly promoted.
REGIONAL_NON_PILOT_HORIZON_REASONS: dict[str, dict[int, str]] = {
    "Influenza A": {
        3: (
            "Influenza A h3 remains outside the active h7-first product scope. "
            "The hierarchy benchmark is promising, but the scope stays reserve-only until the quality gate is strong enough."
        ),
        5: (
            "Influenza A h5 is technically supported, but paused in the current h7-first product focus "
            "because it has not shown convincing added value."
        ),
    },
    "Influenza B": {
        3: (
            "Influenza B h3 remains outside the active h7-first product scope. "
            "The hierarchy benchmark is promising, but the scope stays reserve-only until the quality gate is strong enough."
        ),
        5: (
            "Influenza B h5 is technically supported, but paused in the current h7-first product focus "
            "because it has not shown convincing added value."
        ),
    },
    "RSV A": {
        5: (
            "RSV A h5 is technically supported, but paused in the current h7-first product focus "
            "because h7 is the only actively prioritized horizon."
        ),
    },
    "SARS-CoV-2": {
        3: (
            "SARS-CoV-2 h3 stays shadow/watch-only and is not part of the active h7-first product scope."
        ),
        5: (
            "SARS-CoV-2 h5 stays paused and shadow/watch-only in the current h7-first product focus."
        ),
        7: (
            "SARS-CoV-2 h7 is the only SARS scope still under active consideration, but remains shadow-only until "
            "the explicit promotion flag is enabled after consecutive operational evidence."
        ),
    },
}


@dataclass(frozen=True)
class HorizonSplit:
    train_end_idx: int
    test_idx: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class LearnedProbabilityModel:
    classifier: Any
    feature_names: list[str]
    model_family: str
    calibration: Any | None = None
    calibration_mode: str = "raw_probability"
    probability_source: str = "learned_exceedance_model"
    fallback_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        if isinstance(X, pd.DataFrame):
            values = X[self.feature_names].to_numpy(dtype=float)
        else:
            values = np.asarray(X, dtype=float)
        raw = self.classifier.predict_proba(values)[:, 1]
        return apply_probability_calibration(self.calibration, raw)

    def to_metadata(self) -> dict[str, Any]:
        payload = {
            "model_family": self.model_family,
            "feature_names": list(self.feature_names),
            "calibration_mode": self.calibration_mode,
            "probability_source": self.probability_source,
            "fallback_reason": self.fallback_reason,
        }
        payload.update(self.metadata or {})
        return payload


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


def supported_regional_horizons_for_virus(virus_typ: str) -> tuple[int, ...]:
    unsupported = REGIONAL_UNSUPPORTED_HORIZON_REASONS.get(str(virus_typ or "").strip(), {})
    return tuple(horizon for horizon in SUPPORTED_FORECAST_HORIZONS if horizon not in unsupported)


def pilot_supported_regional_horizons_for_virus(virus_typ: str) -> tuple[int, ...]:
    normalized_virus = str(virus_typ or "").strip()
    supported = supported_regional_horizons_for_virus(normalized_virus)
    non_pilot = REGIONAL_NON_PILOT_HORIZON_REASONS.get(normalized_virus, {})
    return tuple(horizon for horizon in supported if horizon not in non_pilot)


def regional_horizon_support_status(virus_typ: str, horizon_days: int) -> dict[str, Any]:
    horizon = ensure_supported_horizon(horizon_days)
    normalized_virus = str(virus_typ or "").strip()
    supported_horizons = supported_regional_horizons_for_virus(normalized_virus)
    unsupported = REGIONAL_UNSUPPORTED_HORIZON_REASONS.get(normalized_virus, {})
    reason = unsupported.get(horizon)
    supported = horizon in supported_horizons
    return {
        "virus_typ": normalized_virus,
        "horizon_days": horizon,
        "supported": supported,
        "supported_horizons": list(supported_horizons),
        "reason": reason,
    }


def regional_horizon_pilot_status(virus_typ: str, horizon_days: int) -> dict[str, Any]:
    support = regional_horizon_support_status(virus_typ, horizon_days)
    normalized_virus = str(virus_typ or "").strip()
    pilot_supported_horizons = pilot_supported_regional_horizons_for_virus(normalized_virus)
    non_pilot = REGIONAL_NON_PILOT_HORIZON_REASONS.get(normalized_virus, {})
    reason = non_pilot.get(int(horizon_days))
    pilot_supported = bool(support["supported"]) and int(horizon_days) in pilot_supported_horizons
    return {
        "virus_typ": normalized_virus,
        "horizon_days": int(horizon_days),
        "supported": bool(support["supported"]),
        "pilot_supported": pilot_supported,
        "supported_horizons": list(support["supported_horizons"]),
        "pilot_supported_horizons": list(pilot_supported_horizons),
        "reason": None if pilot_supported else (reason or support["reason"]),
    }


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
    n_splits: int | None = None,
    stride: int = DEFAULT_WALK_FORWARD_STRIDE,
    max_splits: int | None = None,
) -> list[HorizonSplit]:
    if n_rows <= max(min_train_points, 1):
        return []

    start = max(int(min_train_points), 1)
    end = n_rows - 1
    step = max(int(stride), 1)
    candidates = list(range(start, end + 1, step))
    if candidates and candidates[-1] != end:
        candidates.append(end)

    effective_max = (
        int(max_splits)
        if max_splits is not None
        else (int(n_splits) if n_splits is not None else None)
    )
    if effective_max is not None and effective_max > 0 and len(candidates) > effective_max:
        candidates = candidates[-effective_max:]

    return [
        HorizonSplit(train_end_idx=int(idx), test_idx=int(idx))
        for idx in candidates
        if idx >= start
    ]


def build_calibration_split_dates(
    train_dates: list[pd.Timestamp],
    *,
    holdout_fraction: float = DEFAULT_CALIBRATION_HOLDOUT_FRACTION,
    min_total_dates: int = MIN_CALIBRATION_TOTAL_DATES,
    min_holdout_dates: int = MIN_CALIBRATION_HOLDOUT_DATES,
    min_train_dates: int = MIN_CALIBRATION_TRAIN_DATES,
) -> tuple[list[pd.Timestamp], list[pd.Timestamp]] | None:
    unique_dates = sorted({pd.Timestamp(value).normalize() for value in train_dates})
    if len(unique_dates) < int(min_total_dates):
        return None
    calibration_size = max(int(min_holdout_dates), int(len(unique_dates) * float(holdout_fraction)))
    calibration_size = min(calibration_size, len(unique_dates) - int(min_train_dates))
    if calibration_size <= 0:
        return None
    return unique_dates[:-calibration_size], unique_dates[-calibration_size:]


def build_calibration_guard_split_dates(
    calibration_dates: list[pd.Timestamp],
    *,
    guard_fraction: float = DEFAULT_CALIBRATION_GUARD_FRACTION,
    min_guard_dates: int = MIN_CALIBRATION_GUARD_DATES,
) -> tuple[list[pd.Timestamp], list[pd.Timestamp]] | None:
    unique_dates = sorted({pd.Timestamp(value).normalize() for value in calibration_dates})
    if len(unique_dates) < (int(min_guard_dates) * 2):
        return None
    guard_size = max(int(min_guard_dates), int(len(unique_dates) * float(guard_fraction)))
    guard_size = min(guard_size, len(unique_dates) - int(min_guard_dates))
    if guard_size <= 0:
        return None
    return unique_dates[:-guard_size], unique_dates[-guard_size:]


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


def fit_isotonic_calibrator(
    raw_probabilities: np.ndarray,
    labels: np.ndarray,
    *,
    min_samples: int = DEFAULT_ISOTONIC_MIN_SAMPLES,
    min_class_support: int = DEFAULT_ISOTONIC_MIN_CLASS_SUPPORT,
) -> IsotonicRegression | None:
    probs = np.asarray(raw_probabilities, dtype=float)
    obs = np.asarray(labels, dtype=int)
    positives = int(np.sum(obs == 1))
    negatives = int(np.sum(obs == 0))
    if len(probs) < int(min_samples) or min(positives, negatives) < int(min_class_support):
        return None
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(probs, obs.astype(float))
    return calibrator


def fit_platt_calibrator(
    raw_probabilities: np.ndarray,
    labels: np.ndarray,
    *,
    min_samples: int = DEFAULT_PLATT_MIN_SAMPLES,
    min_class_support: int = DEFAULT_PLATT_MIN_CLASS_SUPPORT,
) -> LogisticRegression | None:
    probs = np.asarray(raw_probabilities, dtype=float)
    obs = np.asarray(labels, dtype=int)
    positives = int(np.sum(obs == 1))
    negatives = int(np.sum(obs == 0))
    if len(probs) < int(min_samples) or min(positives, negatives) < int(min_class_support):
        return None
    calibrator = LogisticRegression(max_iter=1000, solver="lbfgs")
    calibrator.fit(probs.reshape(-1, 1), obs)
    return calibrator


def apply_probability_calibration(
    calibration: Any | None,
    raw_probabilities: np.ndarray,
) -> np.ndarray:
    probs = np.asarray(raw_probabilities, dtype=float)
    if calibration is None:
        calibrated = probs
    elif isinstance(calibration, IsotonicRegression):
        calibrated = calibration.predict(probs.astype(float))
    elif hasattr(calibration, "predict_proba"):
        calibrated = calibration.predict_proba(probs.reshape(-1, 1))[:, 1]
    else:
        calibrated = probs
    return np.clip(np.asarray(calibrated, dtype=float), 0.001, 0.999)


def _calibration_guard_metrics(
    probabilities: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    metrics = compute_classification_metrics(probabilities, labels)
    metrics["source_rows"] = float(len(np.asarray(labels)))
    return metrics


def _guard_metrics_not_worse(
    candidate_metrics: dict[str, Any],
    raw_metrics: dict[str, Any],
    *,
    epsilon: float = CALIBRATION_GUARD_EPSILON,
) -> bool:
    candidate_brier = float(candidate_metrics.get("brier_score", float("inf")))
    raw_brier = float(raw_metrics.get("brier_score", float("inf")))
    candidate_ece = float(candidate_metrics.get("ece", float("inf")))
    raw_ece = float(raw_metrics.get("ece", float("inf")))
    return (
        candidate_brier <= raw_brier + float(epsilon)
        and candidate_ece <= raw_ece + float(epsilon)
    )


def _evaluate_calibration_candidate(
    *,
    calibration: Any | None,
    calibration_mode: str,
    guard_probabilities: np.ndarray,
    guard_labels: np.ndarray,
    raw_guard_metrics: dict[str, Any],
) -> dict[str, Any]:
    if calibration is None:
        return {
            "calibration": None,
            "calibration_mode": calibration_mode,
            "supported": False,
            "accepted": False,
            "guard_metrics": None,
        }

    calibrated_guard = apply_probability_calibration(calibration, guard_probabilities)
    guard_metrics = _calibration_guard_metrics(calibrated_guard, guard_labels)
    return {
        "calibration": calibration,
        "calibration_mode": calibration_mode,
        "supported": True,
        "accepted": _guard_metrics_not_worse(guard_metrics, raw_guard_metrics),
        "guard_metrics": guard_metrics,
    }


def _calibration_fallback_reason(candidate_results: list[dict[str, Any]]) -> str | None:
    unsupported = [
        str(result.get("calibration_mode") or "unknown")
        for result in candidate_results
        if not bool(result.get("supported"))
    ]
    rejected = [
        str(result.get("calibration_mode") or "unknown")
        for result in candidate_results
        if bool(result.get("supported")) and not bool(result.get("accepted"))
    ]
    if rejected and unsupported:
        return f"guard_metrics_worsened:{','.join(rejected)};unsupported:{','.join(unsupported)}"
    if rejected:
        return f"guard_metrics_worsened:{','.join(rejected)}"
    if unsupported:
        if len(unsupported) == len(candidate_results):
            return "insufficient_class_support_for_calibration"
        return f"unsupported:{','.join(unsupported)}"
    return None


def compute_classification_metrics(
    probabilities: list[float] | np.ndarray,
    labels: list[float] | np.ndarray,
) -> dict[str, float]:
    probs = np.clip(np.asarray(probabilities, dtype=float), 0.001, 0.999)
    obs = np.asarray(labels, dtype=int)
    if len(probs) == 0 or len(obs) == 0:
        return {
            "brier_score": 0.0,
            "ece": 0.0,
            "logloss": 0.0,
            "pr_auc": 0.0,
            "prevalence": 0.0,
            "sample_count": 0.0,
            "positive_count": 0.0,
            "negative_count": 0.0,
        }

    brier = float(np.mean((probs - obs) ** 2))
    ece = float(compute_calibration_error(probs.tolist(), obs.tolist())["ece"])
    if len(np.unique(obs)) < 2:
        pr_auc = float(obs[0]) if len(obs) else 0.0
        logloss_value = 0.0
    else:
        pr_auc = float(average_precision_score(obs, probs))
        logloss_value = float(log_loss(obs, probs, labels=[0, 1]))
    positive_count = int(np.sum(obs == 1))
    negative_count = int(np.sum(obs == 0))
    return {
        "brier_score": round(brier, 6),
        "ece": round(ece, 6),
        "logloss": round(logloss_value, 6),
        "pr_auc": round(pr_auc, 6),
        "prevalence": round(float(np.mean(obs)), 6),
        "sample_count": float(len(obs)),
        "positive_count": float(positive_count),
        "negative_count": float(negative_count),
    }


def select_probability_calibration(
    calibration_frame: pd.DataFrame,
    *,
    raw_probability_col: str = "event_probability_raw",
    label_col: str = "event_label",
    date_col: str = "as_of_date",
    allowed_modes: tuple[str, ...] = ("isotonic", "platt", "raw_probability"),
    isotonic_min_samples: int = DEFAULT_ISOTONIC_MIN_SAMPLES,
    isotonic_min_class_support: int = DEFAULT_ISOTONIC_MIN_CLASS_SUPPORT,
    platt_min_samples: int = DEFAULT_PLATT_MIN_SAMPLES,
    platt_min_class_support: int = DEFAULT_PLATT_MIN_CLASS_SUPPORT,
) -> dict[str, Any]:
    if calibration_frame.empty:
        return {
            "calibration": None,
            "calibration_mode": "raw_probability",
            "fallback_reason": "calibration_frame_empty",
            "reliability_metrics": {},
            "reliability_source": "unavailable",
        }

    working = calibration_frame[[date_col, label_col, raw_probability_col]].copy()
    working[date_col] = pd.to_datetime(working[date_col]).dt.normalize()
    working = working.dropna(subset=[label_col, raw_probability_col]).sort_values(date_col).reset_index(drop=True)
    if working.empty:
        return {
            "calibration": None,
            "calibration_mode": "raw_probability",
            "fallback_reason": "calibration_frame_empty_after_dropna",
            "reliability_metrics": {},
            "reliability_source": "unavailable",
        }

    raw_full_metrics = _calibration_guard_metrics(
        apply_probability_calibration(None, working[raw_probability_col].to_numpy(dtype=float)),
        working[label_col].to_numpy(dtype=int),
    )

    guard_split = build_calibration_guard_split_dates(working[date_col].tolist())
    if not guard_split:
        return {
            "calibration": None,
            "calibration_mode": "raw_probability",
            "fallback_reason": "calibration_guard_unavailable",
            "reliability_metrics": raw_full_metrics,
            "reliability_source": "oof_full_sample",
        }

    fit_dates, guard_dates = guard_split
    fit_df = working.loc[working[date_col].isin(fit_dates)].copy()
    score_df = working.loc[working[date_col].isin(guard_dates)].copy()
    if fit_df.empty or score_df.empty:
        return {
            "calibration": None,
            "calibration_mode": "raw_probability",
            "fallback_reason": "calibration_guard_split_empty",
            "reliability_metrics": raw_full_metrics,
            "reliability_source": "oof_full_sample",
        }

    fit_probs = fit_df[raw_probability_col].to_numpy(dtype=float)
    fit_labels = fit_df[label_col].to_numpy(dtype=int)
    guard_probs = apply_probability_calibration(
        None,
        score_df[raw_probability_col].to_numpy(dtype=float),
    )
    guard_labels = score_df[label_col].to_numpy(dtype=int)
    raw_guard_metrics = _calibration_guard_metrics(guard_probs, guard_labels)

    # The guard slice must stay later in time than calibration fitting so we only
    # accept calibrators that help, or at least do no harm, on unseen future dates.
    candidate_results: list[dict[str, Any]] = []
    if "isotonic" in allowed_modes:
        isotonic_result = _evaluate_calibration_candidate(
            calibration=fit_isotonic_calibrator(
                fit_probs,
                fit_labels,
                min_samples=isotonic_min_samples,
                min_class_support=isotonic_min_class_support,
            ),
            calibration_mode="isotonic",
            guard_probabilities=guard_probs,
            guard_labels=guard_labels,
            raw_guard_metrics=raw_guard_metrics,
        )
        candidate_results.append(isotonic_result)
        if isotonic_result["accepted"]:
            return {
                "calibration": isotonic_result["calibration"],
                "calibration_mode": "isotonic",
                "fallback_reason": None,
                "reliability_metrics": isotonic_result["guard_metrics"],
                "reliability_source": "temporal_guard",
            }

    if "platt" in allowed_modes:
        platt_result = _evaluate_calibration_candidate(
            calibration=fit_platt_calibrator(
                fit_probs,
                fit_labels,
                min_samples=platt_min_samples,
                min_class_support=platt_min_class_support,
            ),
            calibration_mode="platt",
            guard_probabilities=guard_probs,
            guard_labels=guard_labels,
            raw_guard_metrics=raw_guard_metrics,
        )
        candidate_results.append(platt_result)
        if platt_result["accepted"]:
            return {
                "calibration": platt_result["calibration"],
                "calibration_mode": "platt",
                "fallback_reason": None,
                "reliability_metrics": platt_result["guard_metrics"],
                "reliability_source": "temporal_guard",
            }

    if "raw_probability" not in allowed_modes:
        return {
            "calibration": None,
            "calibration_mode": "raw_probability",
            "fallback_reason": "raw_probability_mode_disabled",
            "reliability_metrics": raw_guard_metrics,
            "reliability_source": "temporal_guard",
        }

    return {
        "calibration": None,
        "calibration_mode": "raw_probability",
        "fallback_reason": _calibration_fallback_reason(candidate_results),
        "reliability_metrics": raw_guard_metrics,
        "reliability_source": "temporal_guard",
    }


def select_probability_calibration_from_raw(
    raw_probabilities: np.ndarray,
    labels: np.ndarray,
    *,
    as_of_dates: Any | None = None,
    allowed_modes: tuple[str, ...] = ("isotonic", "platt", "raw_probability"),
    isotonic_min_samples: int = DEFAULT_ISOTONIC_MIN_SAMPLES,
    isotonic_min_class_support: int = DEFAULT_ISOTONIC_MIN_CLASS_SUPPORT,
    platt_min_samples: int = DEFAULT_PLATT_MIN_SAMPLES,
    platt_min_class_support: int = DEFAULT_PLATT_MIN_CLASS_SUPPORT,
) -> dict[str, Any]:
    probs = np.asarray(raw_probabilities, dtype=float)
    obs = np.asarray(labels, dtype=int)
    if as_of_dates is None:
        dates = pd.date_range("2000-01-01", periods=len(obs), freq="D")
    else:
        dates = pd.to_datetime(as_of_dates).normalize()
    calibration_frame = pd.DataFrame(
        {
            "as_of_date": dates,
            "event_label": obs,
            "event_probability_raw": probs,
        }
    )
    return select_probability_calibration(
        calibration_frame,
        raw_probability_col="event_probability_raw",
        label_col="event_label",
        date_col="as_of_date",
        allowed_modes=allowed_modes,
        isotonic_min_samples=isotonic_min_samples,
        isotonic_min_class_support=isotonic_min_class_support,
        platt_min_samples=platt_min_samples,
        platt_min_class_support=platt_min_class_support,
    )


def reliability_score_from_metrics(
    metrics: dict[str, Any] | None,
    *,
    coverage_metrics: dict[str, Any] | None = None,
) -> float | None:
    if not metrics:
        return None

    components: list[float] = []
    brier = metrics.get("brier_score")
    if brier is not None:
        components.append(max(0.0, min(1.0, 1.0 - (float(brier) / 0.25))))
    ece = metrics.get("ece")
    if ece is not None:
        components.append(max(0.0, min(1.0, 1.0 - (float(ece) / 0.20))))
    logloss_value = metrics.get("logloss")
    if logloss_value is not None:
        components.append(max(0.0, min(1.0, 1.0 - (float(logloss_value) / 1.20))))

    coverage_payload = coverage_metrics or {}
    coverage_80 = coverage_payload.get("coverage_80")
    if coverage_80 is not None:
        components.append(max(0.0, min(1.0, 1.0 - (abs(float(coverage_80) - 0.80) / 0.30))))
    coverage_95 = coverage_payload.get("coverage_95")
    if coverage_95 is not None:
        components.append(max(0.0, min(1.0, 1.0 - (abs(float(coverage_95) - 0.95) / 0.20))))

    if not components:
        return None

    sample_count = float(metrics.get("sample_count") or 0.0)
    positive_count = float(metrics.get("positive_count") or 0.0)
    negative_count = float(metrics.get("negative_count") or 0.0)
    support_factor = min(1.0, sample_count / 40.0) if sample_count > 0 else 0.0
    class_factor = min(1.0, min(positive_count, negative_count) / 10.0) if positive_count and negative_count else 0.0
    stability_factor = max(0.25, min(1.0, max(support_factor, class_factor)))
    return round(float(np.mean(components)) * stability_factor, 4)
