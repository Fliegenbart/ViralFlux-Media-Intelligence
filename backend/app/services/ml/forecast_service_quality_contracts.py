from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.ml.forecast_contracts import HEURISTIC_EVENT_SCORE_SOURCE, heuristic_event_score_from_forecast


def compute_regression_metrics(
    predicted: list[float],
    actual: list[float],
    *,
    np_module: Any,
) -> dict[str, float]:
    pred_arr = np_module.asarray(predicted, dtype=float)
    act_arr = np_module.asarray(actual, dtype=float)
    errors = pred_arr - act_arr
    mae = float(np_module.mean(np_module.abs(errors)))
    rmse = float(np_module.sqrt(np_module.mean(errors ** 2)))
    nonzero = act_arr != 0
    mape = (
        float(np_module.mean(np_module.abs(errors[nonzero] / act_arr[nonzero])) * 100)
        if nonzero.any()
        else 0.0
    )
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 2),
    }


def backtest_quality_score(backtest_metrics: dict[str, Any] | None) -> float | None:
    if not backtest_metrics:
        return None
    mape = backtest_metrics.get("mape")
    if mape is None:
        return None
    return round(max(0.0, min(1.0, 1.0 - (float(mape) / 100.0))), 4)


def calibration_passed(backtest_metrics: dict[str, Any] | None) -> bool | None:
    if not backtest_metrics:
        return None
    brier = backtest_metrics.get("brier_score")
    ece = backtest_metrics.get("ece")
    logloss_value = backtest_metrics.get("logloss")
    checks: list[bool] = []
    if brier is not None:
        checks.append(float(brier) <= 0.25)
    if ece is not None:
        checks.append(float(ece) <= 0.10)
    if logloss_value is not None:
        checks.append(float(logloss_value) <= 0.70)
    if not checks:
        return None
    return all(checks)


def quality_meta_from_backtest(
    service: Any,
    *,
    backtest_metrics: dict[str, Any] | None,
    event_probability: float | None,
    probability_source: str,
    calibration_mode: str,
    fallback_reason: str | None = None,
    learned_model_version: str | None = None,
    forecast_ready: bool,
    drift_status: str,
    baseline_deltas: dict[str, Any] | None = None,
    timing_metrics: dict[str, Any] | None = None,
    interval_coverage: dict[str, Any] | None = None,
    promotion_gate: dict[str, Any] | None = None,
    reliability_score_from_metrics_fn: Any,
    backtest_reliability_proxy_source: str,
) -> dict[str, Any]:
    metrics = dict(backtest_metrics or {})
    reliability_score = metrics.get("reliability_score")
    if reliability_score is None:
        reliability_score = reliability_score_from_metrics_fn(
            metrics,
            coverage_metrics=metrics,
        )
    return {
        "event_probability": event_probability,
        "forecast_ready": forecast_ready,
        "drift_status": drift_status,
        "baseline_deltas": baseline_deltas or {},
        "timing_metrics": timing_metrics or {},
        "interval_coverage": interval_coverage or {},
        "promotion_gate": promotion_gate or {},
        "reliability_score": reliability_score,
        "backtest_quality_score": service._backtest_quality_score(metrics),
        "brier_score": metrics.get("brier_score"),
        "ece": metrics.get("ece"),
        "calibration_passed": service._calibration_passed(metrics),
        "probability_source": probability_source,
        "calibration_mode": calibration_mode,
        "calibration_method": f"{probability_source}:{calibration_mode}",
        "uncertainty_source": backtest_reliability_proxy_source,
        "fallback_reason": fallback_reason,
        "learned_model_version": learned_model_version,
        "fallback_used": fallback_reason is not None,
    }


def compute_outbreak_risk(
    prediction: float,
    y_history: Any,
    *,
    window: int = 30,
    np_module: Any,
    sigmoid_fn: Any,
) -> float:
    recent = y_history[-min(window, len(y_history)) :]
    mean_val = float(np_module.mean(recent))
    std_val = float(np_module.std(recent))
    if std_val < 1e-9:
        return 0.5
    z = (prediction - mean_val) / std_val
    return round(sigmoid_fn(z), 3)


def build_contracts(
    service: Any,
    *,
    virus_typ: str,
    region: str,
    horizon_days: int,
    forecast_records: list[dict[str, Any]],
    model_version: str,
    y_history: Any,
    issue_date: datetime | None = None,
    quality_meta: dict[str, Any] | None = None,
    normalize_forecast_region_fn: Any,
    ensure_supported_horizon_fn: Any,
    burden_forecast_cls: Any,
    burden_forecast_point_cls: Any,
    event_forecast_cls: Any,
    forecast_quality_cls: Any,
    confidence_label_fn: Any,
    backtest_reliability_proxy_source: str,
    default_decision_event_threshold_pct: float,
    utc_now_fn: Any,
    np_module: Any,
) -> dict[str, Any]:
    region_code = normalize_forecast_region_fn(region)
    horizon = ensure_supported_horizon_fn(horizon_days)
    issue_ts = issue_date or utc_now_fn()
    burden = burden_forecast_cls(
        target=virus_typ,
        region=region_code,
        issue_date=issue_ts.isoformat(),
        horizon_days=horizon,
        model_version=model_version,
        points=[
            burden_forecast_point_cls(
                target_date=item["ds"].isoformat() if item.get("ds") else "",
                median=float(item.get("yhat") or 0.0),
                lower=(float(item["yhat_lower"]) if item.get("yhat_lower") is not None else None),
                upper=(float(item["yhat_upper"]) if item.get("yhat_upper") is not None else None),
            )
            for item in forecast_records
        ],
    )

    baseline = float(np_module.median(y_history[-min(len(y_history), 84) :])) if len(y_history) > 0 else 0.0
    event_probability = quality_meta.get("event_probability") if quality_meta else None
    reliability_score = (
        quality_meta.get("reliability_score")
        if quality_meta and quality_meta.get("reliability_score") is not None
        else (quality_meta.get("confidence") if quality_meta else None)
    )
    backtest_quality_score_value = quality_meta.get("backtest_quality_score") if quality_meta else None
    calibration_mode = (quality_meta.get("calibration_mode") if quality_meta else None) or "raw_probability"
    probability_source = (quality_meta.get("probability_source") if quality_meta else None) or "empirical_event_prevalence"
    fallback_reason = quality_meta.get("fallback_reason") if quality_meta else None
    first_forecast = forecast_records[0] if forecast_records else {}
    heuristic_event_score = (
        quality_meta.get("heuristic_event_score")
        if quality_meta and quality_meta.get("heuristic_event_score") is not None
        else None
    )
    if event_probability is None and heuristic_event_score is None and baseline > 0 and first_forecast:
        heuristic_event_score = heuristic_event_score_from_forecast(
            prediction=float(first_forecast.get("yhat") or 0.0),
            baseline=baseline,
            lower_bound=first_forecast.get("yhat_lower"),
            upper_bound=first_forecast.get("yhat_upper"),
            threshold_pct=default_decision_event_threshold_pct,
        )
    signal_source = (
        probability_source
        if event_probability is not None
        else (
            quality_meta.get("signal_source")
            if quality_meta and quality_meta.get("signal_source") is not None
            else HEURISTIC_EVENT_SCORE_SOURCE
        )
    )
    probability_source_value = probability_source if event_probability is not None else None

    event = event_forecast_cls(
        event_key=f"{virus_typ.lower().replace(' ', '_')}_growth_h{horizon}",
        horizon_days=horizon,
        event_probability=event_probability,
        threshold_pct=default_decision_event_threshold_pct,
        baseline_value=round(baseline, 3) if baseline > 0 else None,
        threshold_value=round(baseline * 1.25, 3) if baseline > 0 else None,
        calibration_method=(quality_meta.get("calibration_method") if quality_meta else None)
        or f"{probability_source}:{calibration_mode}",
        heuristic_event_score=heuristic_event_score,
        brier_score=quality_meta.get("brier_score") if quality_meta else None,
        ece=quality_meta.get("ece") if quality_meta else None,
        calibration_passed=quality_meta.get("calibration_passed") if quality_meta else None,
        reliability_score=reliability_score,
        backtest_quality_score=backtest_quality_score_value,
        probability_source=probability_source_value,
        calibration_mode=calibration_mode,
        uncertainty_source=(quality_meta.get("uncertainty_source") if quality_meta else None)
        or backtest_reliability_proxy_source,
        fallback_reason=fallback_reason,
        learned_model_version=(quality_meta.get("learned_model_version") if quality_meta else None),
        fallback_used=bool((quality_meta.get("fallback_used") if quality_meta else fallback_reason is not None)),
    )
    event_payload = event.to_dict()
    event_payload["signal_source"] = signal_source
    forecast_quality = forecast_quality_cls(
        forecast_readiness="GO" if quality_meta and quality_meta.get("forecast_ready") else "WATCH",
        drift_status=str(quality_meta.get("drift_status") or "unknown") if quality_meta else "unknown",
        freshness_status="fresh",
        baseline_deltas=quality_meta.get("baseline_deltas") or {} if quality_meta else {},
        timing_metrics=quality_meta.get("timing_metrics") or {} if quality_meta else {},
        interval_coverage=quality_meta.get("interval_coverage") or {} if quality_meta else {},
        promotion_gate=quality_meta.get("promotion_gate") or {} if quality_meta else {},
    )
    return {
        "burden_forecast": burden.to_dict(),
        "event_forecast": event_payload,
        "forecast_quality": forecast_quality.to_dict(),
    }
