from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

TARGET_WINDOW_DAYS: tuple[int, int] = (3, 7)
EVENT_DEFINITION_VERSION = "regional_survstat_v2"
MIN_EVENT_ABSOLUTE_INCIDENCE = 5.0
CORE_SIGNAL_BUNDLE_VERSION = "core_panel_v1"
SARS_SIGNAL_BUNDLE_VERSION = "sars_hybrid_v1"
DEFAULT_ROLLOUT_MODE = "gated"
DEFAULT_ACTIVATION_POLICY = "quality_gate"
SARS_SHADOW_ROLLOUT_MODE = "shadow"
SARS_SHADOW_ACTIVATION_POLICY = "watch_only"


@dataclass(frozen=True)
class EventDefinitionConfig:
    min_absolute_incidence: float = MIN_EVENT_ABSOLUTE_INCIDENCE
    tau_grid: tuple[float, ...] = (0.10, 0.15, 0.20, 0.25, 0.30)
    kappa_grid: tuple[float, ...] = (0.0, 0.5, 1.0)
    min_recall_for_selection: float = 0.35
    baseline_max_history_weeks: int | None = None
    baseline_upper_quantile_cap: float | None = None

    def to_manifest(self) -> dict[str, float | int | list[float] | None]:
        return {
            "min_absolute_incidence": float(self.min_absolute_incidence),
            "tau_grid": [float(value) for value in self.tau_grid],
            "kappa_grid": [float(value) for value in self.kappa_grid],
            "min_recall_for_selection": float(self.min_recall_for_selection),
            "baseline_max_history_weeks": (
                int(self.baseline_max_history_weeks)
                if self.baseline_max_history_weeks is not None
                else None
            ),
            "baseline_upper_quantile_cap": (
                float(self.baseline_upper_quantile_cap)
                if self.baseline_upper_quantile_cap is not None
                else None
            ),
        }


DEFAULT_EVENT_DEFINITION_CONFIG = EventDefinitionConfig()
VIRUS_EVENT_DEFINITION_OVERRIDES: dict[str, EventDefinitionConfig] = {
    "SARS-CoV-2": EventDefinitionConfig(
        tau_grid=(0.05, 0.10, 0.15, 0.20, 0.25),
        kappa_grid=(0.0, 0.25, 0.50),
        baseline_max_history_weeks=104,
        baseline_upper_quantile_cap=0.75,
    ),
}


def event_definition_config_for_virus(virus_typ: str) -> EventDefinitionConfig:
    return VIRUS_EVENT_DEFINITION_OVERRIDES.get(virus_typ, DEFAULT_EVENT_DEFINITION_CONFIG)


def signal_bundle_version_for_virus(virus_typ: str) -> str:
    if virus_typ == "SARS-CoV-2":
        return SARS_SIGNAL_BUNDLE_VERSION
    return CORE_SIGNAL_BUNDLE_VERSION


def rollout_mode_for_virus(virus_typ: str) -> str:
    if virus_typ == "SARS-CoV-2":
        return SARS_SHADOW_ROLLOUT_MODE
    return DEFAULT_ROLLOUT_MODE


def activation_policy_for_virus(virus_typ: str) -> str:
    if virus_typ == "SARS-CoV-2":
        return SARS_SHADOW_ACTIVATION_POLICY
    return DEFAULT_ACTIVATION_POLICY

SOURCE_LAG_DAYS: dict[str, int] = {
    "survstat_weekly": 7,
    "survstat_kreis": 7,
    "are_konsultation": 7,
    "grippeweb": 7,
    "influenza_ifsg": 7,
    "rsv_ifsg": 7,
    "school_holidays": 0,
    "weather_forecast": 0,
    "pollen": 1,
    "notaufnahme": 0,
    "google_trends": 3,
}

ALL_BUNDESLAENDER = [
    "BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV",
    "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH",
]

BUNDESLAND_NAMES: dict[str, str] = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}

STATE_NAME_TO_CODE = {name: code for code, name in BUNDESLAND_NAMES.items()}

CITY_TO_BUNDESLAND: dict[str, str] = {
    "Berlin": "BE",
    "Bremen": "HB",
    "Dresden": "SN",
    "Düsseldorf": "NW",
    "Erfurt": "TH",
    "Hamburg": "HH",
    "Hannover": "NI",
    "Kiel": "SH",
    "Magdeburg": "ST",
    "Mainz": "RP",
    "München": "BY",
    "Potsdam": "BB",
    "Saarbrücken": "SL",
    "Schwerin": "MV",
    "Stuttgart": "BW",
    "Wiesbaden": "HE",
}

REGIONAL_NEIGHBORS: dict[str, list[str]] = {
    "BW": ["BY", "HE", "RP"],
    "BY": ["BW", "HE", "TH", "SN"],
    "BE": ["BB"],
    "BB": ["BE", "MV", "NI", "SN", "ST"],
    "HB": ["NI"],
    "HH": ["NI", "SH"],
    "HE": ["BW", "BY", "NI", "NW", "RP", "TH"],
    "MV": ["BB", "NI", "SH"],
    "NI": ["BB", "HB", "HH", "HE", "MV", "NW", "SH", "ST", "TH"],
    "NW": ["HE", "NI", "RP"],
    "RP": ["BW", "HE", "NW", "SL"],
    "SL": ["RP"],
    "SN": ["BB", "BY", "ST", "TH"],
    "ST": ["BB", "NI", "SN", "TH"],
    "SH": ["HH", "MV", "NI"],
    "TH": ["BY", "HE", "NI", "SN", "ST"],
}


def normalize_state_code(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip()
    if cleaned in BUNDESLAND_NAMES:
        return cleaned
    return STATE_NAME_TO_CODE.get(cleaned)


def effective_available_time(
    reference_date: datetime | pd.Timestamp,
    available_time: datetime | pd.Timestamp | None,
    lag_days: int,
) -> pd.Timestamp:
    if available_time is not None and pd.notna(available_time):
        return pd.Timestamp(available_time)
    return pd.Timestamp(reference_date) + pd.Timedelta(days=max(0, int(lag_days)))


def circular_week_distance(a: int, b: int) -> int:
    diff = abs(int(a) - int(b))
    return min(diff, 52 - diff)


def first_week_start_in_window(
    as_of_date: datetime | pd.Timestamp,
    week_starts: Sequence[datetime | pd.Timestamp],
    lower_days: int = TARGET_WINDOW_DAYS[0],
    upper_days: int = TARGET_WINDOW_DAYS[1],
) -> pd.Timestamp | None:
    lower = pd.Timestamp(as_of_date) + pd.Timedelta(days=lower_days)
    upper = pd.Timestamp(as_of_date) + pd.Timedelta(days=upper_days)
    for week_start in sorted(pd.Timestamp(value) for value in week_starts):
        if lower <= week_start <= upper:
            return week_start
    return None


def seasonal_baseline_and_mad(
    state_truth: pd.DataFrame,
    target_week_start: datetime | pd.Timestamp,
    *,
    max_history_weeks: int | None = None,
    upper_quantile_cap: float | None = None,
) -> tuple[float, float]:
    target_ts = pd.Timestamp(target_week_start)
    if state_truth.empty:
        return 0.0, 1.0

    hist = state_truth.loc[state_truth["week_start"] < target_ts].copy()
    if hist.empty:
        return 0.0, 1.0

    if max_history_weeks is not None and int(max_history_weeks) > 0:
        cutoff = target_ts - pd.Timedelta(weeks=int(max_history_weeks))
        recent_hist = hist.loc[hist["week_start"] >= cutoff].copy()
        if not recent_hist.empty:
            hist = recent_hist

    iso_week = int(target_ts.isocalendar().week)
    hist["iso_week"] = hist["week_start"].dt.isocalendar().week.astype(int)
    seasonal = hist.loc[
        hist["iso_week"].apply(lambda value: circular_week_distance(value, iso_week) <= 1)
    ]

    if len(seasonal) < 5:
        seasonal = hist.tail(12)
    if seasonal.empty:
        seasonal = hist

    values = seasonal["incidence"].astype(float).dropna().to_numpy()
    if (
        upper_quantile_cap is not None
        and 0.0 < float(upper_quantile_cap) < 1.0
        and len(values) >= 5
    ):
        cap = float(np.quantile(values, float(upper_quantile_cap)))
        values = np.clip(values, a_min=0.0, a_max=max(cap, 0.0))
    baseline = float(np.median(values)) if len(values) else 0.0
    mad = float(np.median(np.abs(values - baseline))) if len(values) else 1.0
    return baseline, max(mad, 1.0)


def absolute_incidence_threshold(
    *,
    seasonal_baseline: float,
    seasonal_mad: float,
    kappa: float,
    min_absolute_incidence: float = MIN_EVENT_ABSOLUTE_INCIDENCE,
) -> float:
    baseline = max(float(seasonal_baseline or 0.0), 0.0)
    mad = max(float(seasonal_mad or 0.0), 1.0)
    return max(float(min_absolute_incidence), baseline + float(kappa) * mad)


def build_event_label(
    *,
    current_known_incidence: float,
    next_week_incidence: float,
    seasonal_baseline: float,
    seasonal_mad: float,
    tau: float,
    kappa: float,
    min_absolute_incidence: float = MIN_EVENT_ABSOLUTE_INCIDENCE,
) -> int:
    current_val = max(float(current_known_incidence or 0.0), 0.0)
    next_val = max(float(next_week_incidence or 0.0), 0.0)

    relative_jump = math.log1p(next_val) - math.log1p(current_val)
    absolute_threshold = absolute_incidence_threshold(
        seasonal_baseline=seasonal_baseline,
        seasonal_mad=seasonal_mad,
        kappa=kappa,
        min_absolute_incidence=min_absolute_incidence,
    )
    return int(relative_jump >= float(tau) and next_val >= absolute_threshold)


def compute_ece(y_true: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> float:
    y_arr = np.asarray(y_true, dtype=float)
    p_arr = np.asarray(probabilities, dtype=float)
    if len(y_arr) == 0:
        return 0.0

    edges = np.linspace(0.0, 1.0, bins + 1)
    total = float(len(y_arr))
    ece = 0.0
    for idx in range(bins):
        lower = edges[idx]
        upper = edges[idx + 1]
        if idx == bins - 1:
            mask = (p_arr >= lower) & (p_arr <= upper)
        else:
            mask = (p_arr >= lower) & (p_arr < upper)
        if not mask.any():
            continue
        mean_pred = float(np.mean(p_arr[mask]))
        mean_obs = float(np.mean(y_arr[mask]))
        ece += abs(mean_pred - mean_obs) * (float(np.sum(mask)) / total)
    return round(float(ece), 6)


def average_precision_safe(y_true: Sequence[int], scores: Sequence[float]) -> float:
    from sklearn.metrics import average_precision_score

    y_arr = np.asarray(y_true, dtype=int)
    if len(np.unique(y_arr)) < 2:
        return 0.0
    return float(average_precision_score(y_arr, np.asarray(scores, dtype=float)))


def brier_score_safe(y_true: Sequence[int], probabilities: Sequence[float]) -> float:
    y_arr = np.asarray(y_true, dtype=float)
    p_arr = np.asarray(probabilities, dtype=float)
    if len(y_arr) == 0:
        return 0.0
    return float(np.mean(np.square(p_arr - y_arr)))


def precision_recall_for_threshold(
    probabilities: Sequence[float],
    labels: Sequence[int],
    threshold: float,
) -> tuple[float, float]:
    probs = np.asarray(probabilities, dtype=float)
    y_true = np.asarray(labels, dtype=int)
    y_pred = (probs >= float(threshold)).astype(int)

    tp = float(np.sum((y_pred == 1) & (y_true == 1)))
    fp = float(np.sum((y_pred == 1) & (y_true == 0)))
    fn = float(np.sum((y_pred == 0) & (y_true == 1)))

    precision = tp / max(tp + fp, 1.0)
    recall = tp / max(tp + fn, 1.0)
    return precision, recall


def choose_action_threshold(
    probabilities: Sequence[float],
    labels: Sequence[int],
    min_recall: float = 0.35,
) -> tuple[float, float, float]:
    best_threshold = 0.5
    best_precision = 0.0
    best_recall = 0.0

    candidate_thresholds = [round(value, 2) for value in np.arange(0.35, 0.91, 0.05)]
    for threshold in candidate_thresholds:
        precision, recall = precision_recall_for_threshold(probabilities, labels, threshold)
        if recall < min_recall:
            continue
        if precision > best_precision or (math.isclose(precision, best_precision) and recall > best_recall):
            best_threshold = threshold
            best_precision = precision
            best_recall = recall

    if best_precision == 0.0:
        for threshold in candidate_thresholds:
            precision, recall = precision_recall_for_threshold(probabilities, labels, threshold)
            if precision > best_precision or (math.isclose(precision, best_precision) and recall > best_recall):
                best_threshold = threshold
                best_precision = precision
                best_recall = recall

    return best_threshold, best_precision, best_recall


def time_based_panel_splits(
    dates: Iterable[datetime | pd.Timestamp],
    *,
    n_splits: int = 5,
    min_train_periods: int = 90,
    min_test_periods: int = 21,
) -> list[tuple[list[pd.Timestamp], list[pd.Timestamp]]]:
    unique_dates = sorted({pd.Timestamp(value).normalize() for value in dates})
    if len(unique_dates) < max(min_train_periods + min_test_periods, 30):
        return []

    remaining = len(unique_dates) - min_train_periods
    fold_size = max(min_test_periods, remaining // max(n_splits, 1))
    splits: list[tuple[list[pd.Timestamp], list[pd.Timestamp]]] = []

    train_end = min_train_periods
    while train_end + min_test_periods <= len(unique_dates) and len(splits) < n_splits:
        test_end = min(train_end + fold_size, len(unique_dates))
        train_dates = unique_dates[:train_end]
        test_dates = unique_dates[train_end:test_end]
        if len(test_dates) < min_test_periods:
            break
        splits.append((train_dates, test_dates))
        train_end = test_end
    return splits


def precision_at_k(
    frame: pd.DataFrame,
    *,
    k: int,
    score_col: str = "event_probability_calibrated",
    label_col: str = "event_label",
    group_col: str = "as_of_date",
) -> float:
    if frame.empty:
        return 0.0

    precisions: list[float] = []
    for _, group in frame.groupby(group_col):
        ranked = group.sort_values(score_col, ascending=False).head(k)
        if ranked.empty:
            continue
        precisions.append(float(ranked[label_col].mean()))
    return round(float(np.mean(precisions)), 6) if precisions else 0.0


def activation_false_positive_rate(
    frame: pd.DataFrame,
    *,
    threshold: float | None = None,
    score_col: str = "event_probability_calibrated",
    label_col: str = "event_label",
    threshold_col: str = "action_threshold",
) -> float:
    if frame.empty:
        return 0.0
    if threshold is None and threshold_col in frame.columns:
        activated = frame.loc[frame[score_col] >= frame[threshold_col]]
    else:
        effective_threshold = float(threshold or 0.5)
        activated = frame.loc[frame[score_col] >= effective_threshold]
    if activated.empty:
        return 0.0
    false_positives = activated.loc[activated[label_col] == 0]
    return round(float(len(false_positives) / len(activated)), 6)


def median_lead_days(
    frame: pd.DataFrame,
    *,
    threshold: float | None = None,
    score_col: str = "event_probability_calibrated",
    label_col: str = "event_label",
    threshold_col: str = "action_threshold",
) -> float:
    if frame.empty:
        return 0.0
    if threshold is None and threshold_col in frame.columns:
        hits = frame.loc[(frame[score_col] >= frame[threshold_col]) & (frame[label_col] == 1)].copy()
    else:
        effective_threshold = float(threshold or 0.5)
        hits = frame.loc[(frame[score_col] >= effective_threshold) & (frame[label_col] == 1)].copy()
    if hits.empty:
        return 0.0
    deltas = (
        pd.to_datetime(hits["target_week_start"]) - pd.to_datetime(hits["as_of_date"])
    ).dt.days.astype(float)
    return round(float(np.median(deltas)), 1) if not deltas.empty else 0.0


def quality_gate_from_metrics(
    *,
    metrics: dict[str, float],
    baseline_metrics: dict[str, dict[str, float]],
) -> dict[str, object]:
    baseline_pr_auc = max(
        float((baseline_metrics.get(name) or {}).get("pr_auc") or 0.0)
        for name in ("persistence", "climatology", "amelag_only")
    )
    climatology_brier = float((baseline_metrics.get("climatology") or {}).get("brier_score") or 1.0)

    checks = {
        "precision_at_top3_passed": float(metrics.get("precision_at_top3") or 0.0) >= 0.70,
        "activation_fp_rate_passed": float(metrics.get("activation_false_positive_rate") or 1.0) <= 0.25,
        "pr_auc_passed": float(metrics.get("pr_auc") or 0.0) >= baseline_pr_auc * 1.15,
        "brier_passed": float(metrics.get("brier_score") or 1.0) <= climatology_brier * 0.90,
        "ece_passed": float(metrics.get("ece") or 1.0) <= 0.05,
    }
    overall_passed = all(checks.values())
    return {
        "overall_passed": overall_passed,
        "forecast_readiness": "GO" if overall_passed else "WATCH",
        "checks": checks,
        "thresholds": {
            "precision_at_top3": 0.70,
            "activation_false_positive_rate": 0.25,
            "pr_auc_vs_best_baseline_multiplier": 1.15,
            "brier_vs_climatology_multiplier": 0.90,
            "ece": 0.05,
        },
        "baseline_metrics": baseline_metrics,
    }
