from __future__ import annotations

from datetime import timedelta
import math
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score


def estimate_step_days(df_sim: pd.DataFrame) -> int:
    dates = pd.to_datetime(df_sim["date"], errors="coerce").dropna().sort_values()
    if len(dates) < 2:
        return 7

    day_diffs = dates.diff().dropna().dt.days
    if day_diffs.empty:
        return 7

    median_days = int(round(float(day_diffs.median())))
    return median_days if median_days > 0 else 7


def best_bio_lead_lag(df_sim: pd.DataFrame, *, max_lag_points: int = 6) -> dict:
    if df_sim.empty or len(df_sim) < 8:
        return {
            "best_lag_points": 0,
            "best_lag_days": 0,
            "lag_step_days": 7,
            "lag_correlation": 0.0,
            "bio_leads_target": False,
        }

    bio = pd.to_numeric(df_sim["bio"], errors="coerce").fillna(0.0).to_numpy()
    target = pd.to_numeric(df_sim["real_qty"], errors="coerce").fillna(0.0).to_numpy()
    step_days = estimate_step_days(df_sim)

    best_lag = 0
    best_corr = 0.0
    best_abs_lag = 0
    best_abs_corr = 0.0
    best_pos_lag = 0
    best_pos_corr = -1.0

    for lag in range(-max_lag_points, max_lag_points + 1):
        if lag > 0:
            x = bio[:-lag]
            y = target[lag:]
        elif lag < 0:
            x = bio[-lag:]
            y = target[:lag]
        else:
            x = bio
            y = target

        if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
            continue

        corr = float(np.corrcoef(x, y)[0, 1])
        if np.isnan(corr):
            continue

        if abs(corr) > abs(best_abs_corr):
            best_abs_corr = corr
            best_abs_lag = lag

        if corr > best_pos_corr:
            best_pos_corr = corr
            best_pos_lag = lag

    if best_pos_corr > 0:
        best_corr = best_pos_corr
        best_lag = best_pos_lag
    else:
        best_corr = best_abs_corr
        best_lag = best_abs_lag

    lead_days = best_lag * step_days
    return {
        "best_lag_points": int(best_lag),
        "best_lag_days": int(lead_days),
        "lag_step_days": int(step_days),
        "lag_correlation": round(float(best_corr), 3),
        "bio_leads_target": bool(lead_days > 0 and best_corr > 0),
    }


def augment_lead_lag_with_horizon(lead_lag: dict, horizon_days: int) -> dict:
    relative_lag_days = int(lead_lag.get("best_lag_days", 0) or 0)
    lag_corr = float(lead_lag.get("lag_correlation", 0.0) or 0.0)
    effective_lead_days = int(horizon_days) + relative_lag_days

    enriched = dict(lead_lag or {})
    enriched["relative_lag_days"] = relative_lag_days
    enriched["horizon_days"] = int(horizon_days)
    enriched["effective_lead_days"] = int(effective_lead_days)
    enriched["bio_leads_target_effective"] = bool(effective_lead_days > 0 and lag_corr > 0)
    enriched["target_leads_bio_effective"] = bool(effective_lead_days < 0 and lag_corr > 0)
    return enriched


def compute_forecast_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    if len(y_true) == 0:
        return {
            "r2_score": 0.0,
            "correlation": 0.0,
            "correlation_pct": 0.0,
            "mae": 0.0,
            "rmse": 0.0,
            "smape": 0.0,
            "data_points": 0,
        }

    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(np.mean(np.square(y_true - y_pred))))
    denom = np.abs(y_true) + np.abs(y_pred)
    smape = float(np.mean(np.where(denom > 0, 200.0 * np.abs(y_true - y_pred) / denom, 0.0)))

    corr = float(np.corrcoef(y_true, y_pred)[0, 1]) if len(y_true) > 2 else 0.0
    if np.isnan(corr):
        corr = 0.0

    try:
        r2 = float(r2_score(y_true, y_pred))
        if np.isnan(r2):
            r2 = 0.0
    except Exception:
        r2 = 0.0

    return {
        "r2_score": round(r2, 3),
        "correlation": round(corr, 3),
        "correlation_pct": round(abs(corr) * 100, 1),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "smape": round(smape, 3),
        "data_points": int(len(y_true)),
    }


def compute_vintage_metrics(
    forecast_records: list[dict],
    configured_horizon_days: int,
) -> dict:
    lead_days: list[int] = []
    abs_errors: list[float] = []

    for row in forecast_records or []:
        issue = pd.to_datetime(row.get("issue_date"), errors="coerce")
        target = pd.to_datetime(row.get("target_date"), errors="coerce")
        if not pd.isna(issue) and not pd.isna(target):
            lead_days.append(int((target - issue).days))

        try:
            y_hat = float(row.get("y_hat"))
            y_true = float(row.get("y_true"))
        except (TypeError, ValueError):
            continue
        if np.isfinite(y_hat) and np.isfinite(y_true):
            abs_errors.append(abs(y_hat - y_true))

    median_lead_days = (
        int(round(float(np.median(lead_days))))
        if lead_days
        else int(configured_horizon_days)
    )
    p90_abs_error = (
        round(float(np.percentile(abs_errors, 90)), 3)
        if abs_errors
        else 0.0
    )

    return {
        "configured_horizon_days": int(configured_horizon_days),
        "median_lead_days": int(median_lead_days),
        "p90_abs_error": float(p90_abs_error),
        "oos_points": int(len(abs_errors)),
    }


def compute_interval_coverage_metrics(chart_data: list[dict]) -> dict:
    historical = [
        row for row in (chart_data or [])
        if not row.get("is_forecast") and row.get("real_qty") is not None
    ]
    if not historical:
        return {
            "points": 0,
            "coverage_80_pct": 0.0,
            "coverage_95_pct": 0.0,
            "coverage_80_gap_pct": 80.0,
            "coverage_95_gap_pct": 95.0,
            "coverage_80_gap_score": 0.0,
            "interval_passed": False,
        }

    covered_80 = 0
    covered_95 = 0
    observed = 0
    for row in historical:
        try:
            y_true = float(row["real_qty"])
        except (TypeError, ValueError):
            continue
        observed += 1
        lo_80 = row.get("ci_80_lower")
        hi_80 = row.get("ci_80_upper")
        lo_95 = row.get("ci_95_lower")
        hi_95 = row.get("ci_95_upper")
        if lo_80 is not None and hi_80 is not None and float(lo_80) <= y_true <= float(hi_80):
            covered_80 += 1
        if lo_95 is not None and hi_95 is not None and float(lo_95) <= y_true <= float(hi_95):
            covered_95 += 1

    if observed == 0:
        return {
            "points": 0,
            "coverage_80_pct": 0.0,
            "coverage_95_pct": 0.0,
            "coverage_80_gap_pct": 80.0,
            "coverage_95_gap_pct": 95.0,
            "coverage_80_gap_score": 0.0,
            "interval_passed": False,
        }

    coverage_80 = (covered_80 / observed) * 100.0
    coverage_95 = (covered_95 / observed) * 100.0
    gap_80 = abs(coverage_80 - 80.0)
    gap_95 = abs(coverage_95 - 95.0)
    gap_score = max(0.0, 1.0 - (gap_80 / 30.0))
    interval_passed = gap_80 <= 15.0 and gap_95 <= 10.0
    return {
        "points": int(observed),
        "coverage_80_pct": round(float(coverage_80), 1),
        "coverage_95_pct": round(float(coverage_95), 1),
        "coverage_80_gap_pct": round(float(gap_80), 1),
        "coverage_95_gap_pct": round(float(gap_95), 1),
        "coverage_80_gap_score": round(float(gap_score), 4),
        "interval_passed": bool(interval_passed),
    }


def compute_event_calibration_metrics(
    forecast_records: list[dict],
    *,
    threshold_pct: float = 25.0,
    decision_baseline_window_days: int,
    heuristic_event_score_source: str,
) -> dict:
    pairs: list[tuple[float, float]] = []
    bucket_counts = [0] * 5
    bucket_pred = [0.0] * 5
    bucket_obs = [0.0] * 5
    skipped_heuristic_only = False

    valid_rows = []
    for row in forecast_records or []:
        issue = pd.to_datetime(row.get("issue_date"), errors="coerce")
        target = pd.to_datetime(row.get("target_date"), errors="coerce")
        probability_source = str(row.get("probability_source") or "")
        raw_probability = row.get("event_probability")
        if raw_probability is None and (
            row.get("heuristic_event_score") is not None
            or probability_source == heuristic_event_score_source
        ):
            skipped_heuristic_only = True
            continue
        if raw_probability is None:
            raw_probability = row.get("p_event")
        try:
            probability = float(raw_probability)
            y_true = float(row.get("y_true"))
        except (TypeError, ValueError):
            continue
        if pd.isna(issue) or pd.isna(target):
            continue
        if not (np.isfinite(probability) and np.isfinite(y_true)):
            continue
        valid_rows.append(
            {
                "issue_date": issue,
                "target_date": target,
                "y_true": y_true,
                "p_event": min(max(probability, 0.0), 1.0),
            }
        )

    if not valid_rows:
        return {
            "samples": 0,
            "brier_score": None,
            "ece": None,
            "calibration_passed": None,
            "calibration_method": (
                "skipped_heuristic_event_score"
                if skipped_heuristic_only
                else "unavailable"
            ),
            "calibration_skipped": bool(skipped_heuristic_only),
            "skip_reason": (
                "heuristic_event_score_only"
                if skipped_heuristic_only
                else "no_probability_records"
            ),
            "buckets": [],
        }

    truth_rows = sorted(valid_rows, key=lambda r: r["target_date"])
    threshold_ratio = float(threshold_pct or 0.0) / 100.0

    for row in valid_rows:
        baseline_start = row["issue_date"] - timedelta(days=decision_baseline_window_days)
        baseline_vals = [
            item["y_true"]
            for item in truth_rows
            if baseline_start <= item["target_date"] <= row["issue_date"]
        ]
        if not baseline_vals:
            baseline_vals = [item["y_true"] for item in truth_rows if item["target_date"] <= row["issue_date"]]
        if not baseline_vals:
            continue

        baseline = float(np.median(baseline_vals))
        if not np.isfinite(baseline) or baseline <= 0:
            continue

        observed_event = 1.0 if ((float(row["y_true"]) - baseline) / baseline) >= threshold_ratio else 0.0
        probability = float(row["p_event"])
        pairs.append((probability, observed_event))
        bucket = min(int(probability * 5.0), 4)
        bucket_counts[bucket] += 1
        bucket_pred[bucket] += probability
        bucket_obs[bucket] += observed_event

    if not pairs:
        return {
            "samples": 0,
            "brier_score": None,
            "ece": None,
            "calibration_passed": False,
            "calibration_method": "growth_sigmoid_with_oos_gate",
            "calibration_skipped": False,
            "skip_reason": "no_baseline_comparable_rows",
            "buckets": [],
        }

    probs = np.asarray([item[0] for item in pairs], dtype=float)
    obs = np.asarray([item[1] for item in pairs], dtype=float)
    brier = float(np.mean(np.square(probs - obs)))
    total = float(len(pairs))
    ece = 0.0
    buckets: list[dict[str, Any]] = []
    for idx, count in enumerate(bucket_counts):
        if count <= 0:
            continue
        mean_pred = bucket_pred[idx] / count
        mean_obs = bucket_obs[idx] / count
        ece += abs(mean_pred - mean_obs) * (count / total)
        buckets.append(
            {
                "bucket": idx,
                "samples": int(count),
                "mean_predicted": round(float(mean_pred), 4),
                "mean_observed": round(float(mean_obs), 4),
            }
        )

    calibration_passed = brier <= 0.25 and ece <= 0.15
    return {
        "samples": int(len(pairs)),
        "brier_score": round(float(brier), 4),
        "ece": round(float(ece), 4),
        "calibration_passed": bool(calibration_passed),
        "calibration_method": "growth_sigmoid_with_oos_gate",
        "calibration_skipped": False,
        "skip_reason": None,
        "buckets": buckets,
    }


def build_lead_feature_set(feature_cols: list[str]) -> list[str]:
    excluded = {"target_level", "target_roc"}
    lead_cols = [col for col in feature_cols if col not in excluded]
    return lead_cols if lead_cols else list(feature_cols)


def compute_timing_metrics(
    forecast_records: list[dict],
    horizon_days: int,
    *,
    y_hat_key: str = "y_hat",
    max_lag_points: int = 8,
    quality_gate_lead_target_days: int,
) -> dict:
    valid_rows: list[dict] = []
    for row in forecast_records or []:
        issue = pd.to_datetime(row.get("issue_date"), errors="coerce")
        target = pd.to_datetime(row.get("target_date"), errors="coerce")
        region = str(row.get("region") or "__all__")
        try:
            y_hat = float(row.get(y_hat_key))
            y_true = float(row.get("y_true"))
        except (TypeError, ValueError):
            continue
        if pd.isna(issue) or pd.isna(target):
            continue
        if not (np.isfinite(y_hat) and np.isfinite(y_true)):
            continue
        valid_rows.append(
            {
                "region": region,
                "issue_date": issue.normalize(),
                "target_date": target.normalize(),
                "y_hat": y_hat,
                "y_true": y_true,
            }
        )

    default = {
        "configured_horizon_days": int(horizon_days),
        "best_lag_days": 0,
        "corr_at_best_lag": 0.0,
        "corr_at_horizon": 0.0,
        "lead_passed": False,
        "lag_step_days": 7,
        "aligned_points": 0,
    }
    if len(valid_rows) < 3:
        return default

    target_dates = sorted({row["target_date"] for row in valid_rows})
    if len(target_dates) >= 2:
        diffs = [
            int((target_dates[i] - target_dates[i - 1]).days)
            for i in range(1, len(target_dates))
            if (target_dates[i] - target_dates[i - 1]).days > 0
        ]
        step_days = int(round(float(np.median(diffs)))) if diffs else 7
    else:
        step_days = 7
    step_days = max(step_days, 1)

    truth_map: dict[tuple[str, pd.Timestamp], float] = {}
    pred_points: list[tuple[str, pd.Timestamp, float]] = []
    for row in valid_rows:
        key = (row["region"], row["target_date"])
        truth_map[key] = row["y_true"]
        pred_points.append((row["region"], row["issue_date"], row["y_hat"]))

    def _corr_for_lag_days(lag_days: int) -> tuple[float, int]:
        xs: list[float] = []
        ys: list[float] = []
        lag_delta = timedelta(days=int(lag_days))
        for region, issue_date, pred_val in pred_points:
            target_date = issue_date + lag_delta
            true_val = truth_map.get((region, target_date))
            if true_val is None:
                continue
            xs.append(float(pred_val))
            ys.append(float(true_val))

        n = len(xs)
        if n < 3:
            return 0.0, n
        x = np.asarray(xs, dtype=float)
        y = np.asarray(ys, dtype=float)
        if np.std(x) <= 1e-12 or np.std(y) <= 1e-12:
            return 0.0, n
        corr = float(np.corrcoef(x, y)[0, 1])
        if not np.isfinite(corr):
            corr = 0.0
        return corr, n

    best_lag_days = 0
    best_corr = -1.0
    best_n = 0
    for lag_points in range(-max_lag_points, max_lag_points + 1):
        lag_days = lag_points * step_days
        corr, n = _corr_for_lag_days(lag_days)
        if n < 3:
            continue
        if (corr > best_corr + 1e-12) or (
            abs(corr - best_corr) <= 1e-12 and lag_days > best_lag_days
        ):
            best_lag_days = int(lag_days)
            best_corr = float(corr)
            best_n = int(n)

    horizon_lag_days = int(round(float(horizon_days) / float(step_days))) * step_days
    corr_at_horizon, _ = _corr_for_lag_days(horizon_lag_days)
    if best_corr < 0:
        best_corr = 0.0

    lead_passed = best_lag_days >= int(quality_gate_lead_target_days)
    return {
        "configured_horizon_days": int(horizon_days),
        "best_lag_days": int(best_lag_days),
        "corr_at_best_lag": round(float(best_corr), 3),
        "corr_at_horizon": round(float(corr_at_horizon), 3),
        "lead_passed": bool(lead_passed),
        "lag_step_days": int(step_days),
        "aligned_points": int(best_n),
    }


def compute_decision_metrics(
    forecast_records: list[dict],
    *,
    threshold_pct: float = 25.0,
    vintage_metrics: Optional[dict] = None,
    decision_baseline_window_days: int,
    quality_gate_ttd_target_days: int,
    quality_gate_hit_rate_target_pct: float,
    quality_gate_p90_error_rel_target_pct: float,
) -> dict:
    valid_rows: list[dict] = []
    abs_errors: list[float] = []

    for row in forecast_records or []:
        issue = pd.to_datetime(row.get("issue_date"), errors="coerce")
        target = pd.to_datetime(row.get("target_date"), errors="coerce")
        try:
            y_hat = float(row.get("y_hat"))
            y_true = float(row.get("y_true"))
        except (TypeError, ValueError):
            continue
        if pd.isna(issue) or pd.isna(target):
            continue
        if not (np.isfinite(y_hat) and np.isfinite(y_true)):
            continue

        valid_rows.append(
            {
                "issue_date": issue,
                "target_date": target,
                "y_hat": y_hat,
                "y_true": y_true,
            }
        )
        abs_errors.append(abs(y_hat - y_true))

    threshold_pct = float(threshold_pct or 0.0)
    threshold_ratio = threshold_pct / 100.0
    default_metrics = {
        "event_threshold_pct": round(threshold_pct, 1),
        "alerts": 0,
        "events": 0,
        "hits": 0,
        "false_alarms": 0,
        "misses": 0,
        "hit_rate_pct": 0.0,
        "recall_pct": 0.0,
        "false_alarm_rate_pct": 0.0,
        "median_ttd_days": 0,
        "p90_abs_error": round(
            float(vintage_metrics.get("p90_abs_error", 0.0))
            if vintage_metrics
            else (float(np.percentile(abs_errors, 90)) if abs_errors else 0.0),
            3,
        ),
        "median_y_true_last_12w": 0.0,
        "error_relative_pct": 0.0,
        "readiness_score_0_100": 0.0,
        "analyzed_points": int(len(valid_rows)),
    }
    if not valid_rows:
        return default_metrics

    valid_rows.sort(key=lambda r: (r["issue_date"], r["target_date"]))
    truth_rows = sorted(valid_rows, key=lambda r: r["target_date"])

    alerts = 0
    events = 0
    hits = 0
    false_alarms = 0
    misses = 0
    hit_ttd_days: list[int] = []

    for row in valid_rows:
        issue_date = row["issue_date"]
        baseline_start = issue_date - timedelta(days=decision_baseline_window_days)
        baseline_vals = [
            r["y_true"]
            for r in truth_rows
            if baseline_start <= r["target_date"] <= issue_date
        ]
        if not baseline_vals:
            baseline_vals = [r["y_true"] for r in truth_rows if r["target_date"] <= issue_date]

        if not baseline_vals:
            continue

        baseline = float(np.median(baseline_vals))
        if not np.isfinite(baseline) or baseline <= 0:
            continue

        pred_growth = (float(row["y_hat"]) - baseline) / baseline
        real_growth = (float(row["y_true"]) - baseline) / baseline
        alert = pred_growth >= threshold_ratio
        event = real_growth >= threshold_ratio

        if alert:
            alerts += 1
        if event:
            events += 1

        if alert and event:
            hits += 1
            hit_ttd_days.append(int((row["target_date"] - row["issue_date"]).days))
        elif alert and not event:
            false_alarms += 1
        elif event and not alert:
            misses += 1

    latest_issue_date = max(row["issue_date"] for row in valid_rows)
    gate_start = latest_issue_date - timedelta(days=decision_baseline_window_days)
    gate_values = [
        float(r["y_true"])
        for r in truth_rows
        if gate_start <= r["target_date"] <= latest_issue_date
    ]
    if not gate_values:
        gate_values = [float(r["y_true"]) for r in truth_rows]

    median_y_true_last_12w = (
        float(np.median(gate_values))
        if gate_values
        else 0.0
    )
    p90_abs_error = (
        float(vintage_metrics.get("p90_abs_error", 0.0))
        if vintage_metrics
        else (float(np.percentile(abs_errors, 90)) if abs_errors else 0.0)
    )
    error_relative_pct = (
        (p90_abs_error / median_y_true_last_12w) * 100.0
        if median_y_true_last_12w > 0
        else 0.0
    )

    hit_rate_pct = (hits / alerts * 100.0) if alerts > 0 else 0.0
    recall_pct = (hits / events * 100.0) if events > 0 else 0.0
    false_alarm_rate_pct = (false_alarms / alerts * 100.0) if alerts > 0 else 0.0
    median_ttd_days = int(round(float(np.median(hit_ttd_days)))) if hit_ttd_days else 0

    ttd_target = float(quality_gate_ttd_target_days)
    hit_target = float(quality_gate_hit_rate_target_pct)
    err_target = float(quality_gate_p90_error_rel_target_pct)

    ttd_score = min(100.0, max(0.0, (median_ttd_days / max(ttd_target, 1e-9)) * 100.0))
    hit_score = min(100.0, max(0.0, hit_rate_pct))
    if error_relative_pct <= err_target:
        error_score = 100.0
    else:
        over = (error_relative_pct - err_target) / max(err_target, 1e-9)
        error_score = max(0.0, 100.0 - over * 100.0)
    readiness_score = round(0.4 * hit_score + 0.35 * ttd_score + 0.25 * error_score, 1)

    return {
        "event_threshold_pct": round(threshold_pct, 1),
        "alerts": int(alerts),
        "events": int(events),
        "hits": int(hits),
        "false_alarms": int(false_alarms),
        "misses": int(misses),
        "hit_rate_pct": round(float(hit_rate_pct), 1),
        "recall_pct": round(float(recall_pct), 1),
        "false_alarm_rate_pct": round(float(false_alarm_rate_pct), 1),
        "median_ttd_days": int(median_ttd_days),
        "p90_abs_error": round(float(p90_abs_error), 3),
        "median_y_true_last_12w": round(float(median_y_true_last_12w), 3),
        "error_relative_pct": round(float(error_relative_pct), 2),
        "readiness_score_0_100": float(readiness_score),
        "analyzed_points": int(len(valid_rows)),
    }


def build_quality_gate(
    decision_metrics: dict,
    timing_metrics: Optional[dict] = None,
    *,
    improvement_vs_baselines: Optional[dict] = None,
    interval_coverage: Optional[dict] = None,
    event_calibration: Optional[dict] = None,
    quality_gate_ttd_target_days: int,
    quality_gate_hit_rate_target_pct: float,
    quality_gate_p90_error_rel_target_pct: float,
    quality_gate_lead_target_days: int,
) -> dict:
    ttd_target = int(quality_gate_ttd_target_days)
    hit_target = float(quality_gate_hit_rate_target_pct)
    err_target = float(quality_gate_p90_error_rel_target_pct)
    lead_target = int(quality_gate_lead_target_days)

    median_ttd_days = float(decision_metrics.get("median_ttd_days", 0.0) or 0.0)
    hit_rate_pct = float(decision_metrics.get("hit_rate_pct", 0.0) or 0.0)
    error_relative_pct = float(decision_metrics.get("error_relative_pct", 0.0) or 0.0)
    best_lag_days = float((timing_metrics or {}).get("best_lag_days", 0.0) or 0.0)

    ttd_passed = median_ttd_days >= float(ttd_target)
    hit_rate_passed = hit_rate_pct >= hit_target
    error_passed = error_relative_pct <= err_target
    if timing_metrics is None:
        lead_passed = True
    else:
        lead_passed = best_lag_days >= float(lead_target)
    baseline_schema = improvement_vs_baselines or {}
    baseline_passed = bool(
        float(baseline_schema.get("mae_vs_persistence_pct", 0.0) or 0.0) >= 0.0
        and float(baseline_schema.get("mae_vs_seasonal_pct", 0.0) or 0.0) >= 0.0
    )
    interval_passed = bool(
        interval_coverage.get("interval_passed", True)
        if interval_coverage is not None
        else True
    )
    calibration_passed = bool(
        event_calibration.get("calibration_passed", True)
        if event_calibration is not None
        else True
    )
    overall_passed = bool(
        ttd_passed
        and hit_rate_passed
        and error_passed
        and lead_passed
        and baseline_passed
        and interval_passed
        and calibration_passed
    )

    return {
        "ttd_target_days": ttd_target,
        "hit_rate_target_pct": hit_target,
        "p90_error_relative_target_pct": err_target,
        "lead_target_days": lead_target,
        "ttd_passed": bool(ttd_passed),
        "hit_rate_passed": bool(hit_rate_passed),
        "error_passed": bool(error_passed),
        "lead_passed": bool(lead_passed),
        "baseline_passed": bool(baseline_passed),
        "interval_passed": bool(interval_passed),
        "event_calibration_passed": bool(calibration_passed),
        "overall_passed": bool(overall_passed),
        "forecast_readiness": "GO" if overall_passed else "WATCH",
    }


def sanitize_for_json(value):
    if isinstance(value, dict):
        return {k: sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value
