from __future__ import annotations

from typing import Any


def predict(
    service,
    *,
    virus_typ: str,
    region: str,
    horizon_days: int,
    include_internal_history: bool,
    normalize_forecast_region_fn,
    ensure_supported_horizon_fn,
    load_cached_models_fn,
    is_model_feature_compatibility_error_fn,
    logger,
) -> dict[str, Any]:
    region_code = normalize_forecast_region_fn(region)
    horizon = ensure_supported_horizon_fn(horizon_days)
    cached = load_cached_models_fn(
        virus_typ,
        region=region_code,
        horizon_days=horizon,
    )

    if cached is None:
        logger.info(
            f"No pre-trained model found for {virus_typ}/{region_code}/h{horizon}, "
            f"falling back to in-memory train_and_forecast()"
        )
        return service.train_and_forecast(
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
            include_internal_history=include_internal_history,
        )

    model_med, model_lo, model_hi, metadata, event_model = cached
    try:
        return service._inference_from_loaded_models(
            virus_typ=virus_typ,
            model_med=model_med,
            model_lo=model_lo,
            model_hi=model_hi,
            metadata=metadata,
            event_model=event_model,
            region=region_code,
            horizon_days=horizon,
            include_internal_history=include_internal_history,
        )
    except Exception as exc:
        if not is_model_feature_compatibility_error_fn(exc):
            raise

        logger.warning(
            "Cached forecast model for %s/%s/h%s is incompatible with current features (%s). "
            "Falling back to in-memory train_and_forecast().",
            virus_typ,
            region_code,
            horizon,
            exc,
        )
        return service.train_and_forecast(
            virus_typ=virus_typ,
            region=region_code,
            horizon_days=horizon,
            include_internal_history=include_internal_history,
        )


def inference_from_loaded_models(
    service,
    *,
    virus_typ: str,
    model_med: Any,
    model_lo: Any,
    model_hi: Any,
    metadata: dict[str, Any],
    event_model,
    region: str,
    horizon_days: int,
    include_internal_history: bool,
    normalize_forecast_region_fn,
    ensure_supported_horizon_fn,
    min_direct_train_points: int,
    np_module,
    pd_module,
    timedelta_cls,
    utc_now_fn,
    logger,
) -> dict[str, Any]:
    from app.services.ml.forecast_service import _resolve_loaded_model_feature_names

    region_code = normalize_forecast_region_fn(region)
    horizon = ensure_supported_horizon_fn(horizon_days)
    logger.info(
        f"=== Inference for {virus_typ}/{region_code}/h{horizon} "
        f"(model={metadata.get('version')}) ==="
    )

    internal_history_enabled = bool(
        metadata.get("data_sources", {}).get("internal_history", include_internal_history)
    )
    df = service.prepare_training_data(
        virus_typ=virus_typ,
        include_internal_history=internal_history_enabled,
        region=region_code,
    )

    if df.empty or len(df) < max(min_direct_train_points, 10):
        logger.error(
            "Insufficient data for inference (%s rows) for %s/%s/h%s",
            len(df),
            virus_typ,
            region_code,
            horizon,
        )
        return {
            "error": "Insufficient data for inference",
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
        }

    y = df["y"].values
    live_feature_row = service._build_live_direct_feature_row(
        df,
        virus_typ=virus_typ,
        horizon_days=horizon,
        region=region_code,
    )
    if not live_feature_row:
        return {
            "error": "Failed to build live direct feature row",
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
        }

    feature_names = _resolve_loaded_model_feature_names(
        metadata=metadata,
        live_feature_row=live_feature_row,
        model=model_med,
    )
    X_row = np_module.array([[live_feature_row.get(name, 0.0) for name in feature_names]], dtype=float)
    X_row = np_module.nan_to_num(X_row, nan=0.0, posinf=0.0, neginf=0.0)

    prediction = max(0.0, float(model_med.predict(X_row)[0]))
    lower_bound = max(0.0, float(model_lo.predict(X_row)[0]))
    upper_bound = max(0.0, float(model_hi.predict(X_row)[0]))
    lower_bound = min(lower_bound, prediction)
    upper_bound = max(upper_bound, prediction)

    issue_date = pd_module.Timestamp(df["ds"].max()).to_pydatetime()
    target_date = issue_date + timedelta_cls(days=horizon)
    last_momentum = float(df["trend_momentum_7d"].iloc[-1]) if "trend_momentum_7d" in df.columns else 0.0
    risk = service._compute_outbreak_risk(prediction, y)
    forecast_records: list[dict[str, Any]] = [
        {
            "ds": target_date,
            "yhat": prediction,
            "yhat_lower": lower_bound,
            "yhat_upper": upper_bound,
            "trend_momentum_7d": last_momentum,
            "outbreak_risk_score": risk,
        }
    ]

    model_version = metadata.get("version", "xgb_stack_v1_loaded")
    backtest_metrics = dict(metadata.get("backtest_metrics") or {})
    live_event_feature_row = service._build_live_event_feature_row(
        raw=df,
        live_feature_row=live_feature_row,
        horizon_days=horizon,
    )
    event_bundle: dict[str, Any] | None = None
    if event_model is None:
        panel = service._build_direct_training_panel_from_frame(
            df,
            horizon_days=horizon,
            n_splits=max(int(metadata.get("event_oof_splits") or 5), 3),
        )
        if not panel.empty:
            event_bundle = service._build_event_probability_model_from_panel(panel)
            event_model = event_bundle.get("model")
            backtest_metrics.update(event_bundle.get("calibrated_metrics") or {})
            backtest_metrics["probability_source"] = event_bundle.get("probability_source")
            backtest_metrics["calibration_mode"] = event_bundle.get("calibration_mode")
            backtest_metrics["fallback_reason"] = event_bundle.get("fallback_reason")
            backtest_metrics["reliability_score"] = event_bundle.get("reliability_score")

    probability_source = str(
        (event_bundle or {}).get("probability_source")
        or getattr(event_model, "probability_source", None)
        or backtest_metrics.get("probability_source")
        or metadata.get("event_probability_source")
        or "empirical_event_prevalence"
    )
    calibration_mode = str(
        (event_bundle or {}).get("calibration_mode")
        or getattr(event_model, "calibration_mode", None)
        or backtest_metrics.get("calibration_mode")
        or metadata.get("event_calibration_mode")
        or "raw_probability"
    )
    fallback_reason = (
        (event_bundle or {}).get("fallback_reason")
        or getattr(event_model, "fallback_reason", None)
        or metadata.get("event_fallback_reason")
    )
    event_probability: float | None = None
    if event_model is not None:
        event_feature_names = list(getattr(event_model, "feature_names", []) or [])
        X_event = np_module.array(
            [[live_event_feature_row.get(name, 0.0) for name in (event_feature_names or ["current_y"])]],
            dtype=float,
        )
        X_event = np_module.nan_to_num(X_event, nan=0.0, posinf=0.0, neginf=0.0)
        event_probability = float(event_model.predict_proba(X_event)[0])
    contracts = service._build_contracts(
        virus_typ=virus_typ,
        region=region_code,
        horizon_days=horizon,
        forecast_records=forecast_records,
        model_version=model_version,
        y_history=y,
        issue_date=issue_date,
        quality_meta=service._quality_meta_from_backtest(
            backtest_metrics=backtest_metrics,
            event_probability=event_probability,
            probability_source=probability_source,
            calibration_mode=calibration_mode,
            fallback_reason=fallback_reason,
            learned_model_version=model_version,
            forecast_ready="error" not in backtest_metrics,
            drift_status="ok" if "error" not in backtest_metrics else "unknown",
        ),
    )

    result: dict[str, Any] = {
        "virus_typ": virus_typ,
        "region": region_code,
        "horizon_days": horizon,
        "training_samples": metadata.get("training_samples", len(df)),
        "forecast_days": horizon,
        "data_frequency_days": horizon,
        "forecast": forecast_records,
        "feature_names": feature_names,
        "feature_importance": metadata.get("feature_importance", {}),
        "model_version": model_version,
        "confidence": contracts["event_forecast"].get("reliability_score"),
        "training_window": metadata.get("training_window"),
        "backtest_metrics": backtest_metrics,
        "contracts": contracts,
        "timestamp": utc_now_fn(),
    }

    logger.info(
        f"Inference completed for {virus_typ}/{region_code}/h{horizon}: "
        f"target_date={target_date.date()}, model={model_version}"
    )
    return result
