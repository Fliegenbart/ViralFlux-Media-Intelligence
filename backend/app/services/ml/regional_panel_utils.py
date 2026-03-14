from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

TARGET_WINDOW_DAYS: tuple[int, int] = (3, 7)
EVENT_DEFINITION_VERSION = "regional_survstat_v1"
MIN_EVENT_ABSOLUTE_INCIDENCE = 5.0

SOURCE_LAG_DAYS: dict[str, int] = {
    "survstat_weekly": 7,
    "survstat_kreis": 7,
    "school_holidays": 0,
    "weather_forecast": 0,
    "pollen": 1,
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
) -> tuple[float, float]:
    target_ts = pd.Timestamp(target_week_start)
    if state_truth.empty:
        return 0.0, 1.0

    hist = state_truth.loc[state_truth["week_start"] < target_ts].copy()
    if hist.empty:
        return 0.0, 1.0

    iso_week = int(target_ts.isocalendar().week)
    hist["iso_week"] = hist["week_start"].dt.isocalendar().week.astype(int)
    seasonal = hist.loc[
        hist["iso_week"].apply(lambda value: circular_week_distance(value, iso_week) <= 1)
    ]

    if len(seasonal) < 5:
        seasonal = hist.tail(12)
    if seasonal.empty:
        seasonal = hist

    values = seasonal["incidence"].astype(float).to_numpy()
    baseline = float(np.median(values)) if len(values) else 0.0
    mad = float(np.median(np.abs(values - baseline))) if len(values) else 1.0
    return baseline, max(mad, 1.0)


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
    baseline = max(float(seasonal_baseline or 0.0), 0.0)
    mad = max(float(seasonal_mad or 0.0), 1.0)

    relative_jump = math.log1p(next_val) - math.log1p(current_val)
    absolute_threshold = max(min_absolute_incidence, baseline + float(kappa) * mad)
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
