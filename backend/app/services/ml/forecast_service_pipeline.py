from __future__ import annotations

from typing import Any


def train_and_forecast(
    service: Any,
    *,
    virus_typ: str,
    region: str,
    horizon_days: int,
    include_internal_history: bool,
    normalize_forecast_region_fn: Any,
    ensure_supported_horizon_fn: Any,
    min_direct_train_points: int,
    utc_now_fn: Any,
    timedelta_cls: Any,
    np_module: Any,
    pd_module: Any,
    logger: Any,
) -> dict[str, Any]:
    region_code = normalize_forecast_region_fn(region)
    horizon = ensure_supported_horizon_fn(horizon_days)
    logger.info(f"=== Direct stacking forecast for {virus_typ}/{region_code}/h{horizon} ===")

    df = service.prepare_training_data(
        virus_typ=virus_typ,
        include_internal_history=include_internal_history,
        region=region_code,
    )

    panel = service._build_direct_training_panel_from_frame(
        df,
        horizon_days=horizon,
        n_splits=5,
    )
    if panel.empty or len(panel) < max(min_direct_train_points, 24):
        logger.error(
            "Insufficient data for direct training (%s rows) for %s/%s/h%s",
            len(panel) if not panel.empty else 0,
            virus_typ,
            region_code,
            horizon,
        )
        return {
            "error": "Insufficient training data",
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
        }

    model_med, model_lo, model_hi, feature_names, feature_importance = (
        service._fit_xgboost_meta_from_panel(panel, target_column="y_target")
    )
    live_feature_row = service._build_live_direct_feature_row(
        df,
        virus_typ=virus_typ,
        horizon_days=horizon,
        region=region_code,
    )
    X_row = np_module.array([[live_feature_row.get(name, 0.0) for name in feature_names]], dtype=float)
    X_row = np_module.nan_to_num(X_row, nan=0.0, posinf=0.0, neginf=0.0)

    prediction = max(0.0, float(model_med.predict(X_row)[0]))
    lower_bound = max(0.0, float(model_lo.predict(X_row)[0]))
    upper_bound = max(0.0, float(model_hi.predict(X_row)[0]))
    lower_bound = min(lower_bound, prediction)
    upper_bound = max(upper_bound, prediction)

    y = df["y"].to_numpy(dtype=float)
    issue_date = pd_module.Timestamp(df["ds"].max()).to_pydatetime()
    target_date = issue_date + timedelta_cls(days=horizon)
    last_momentum = float(df["trend_momentum_7d"].iloc[-1]) if "trend_momentum_7d" in df.columns else 0.0
    forecast_records = [
        {
            "ds": target_date,
            "yhat": prediction,
            "yhat_lower": lower_bound,
            "yhat_upper": upper_bound,
            "trend_momentum_7d": last_momentum,
            "outbreak_risk_score": service._compute_outbreak_risk(prediction, y),
        }
    ]
    event_bundle = service._build_event_probability_model_from_panel(panel)
    event_model = event_bundle.get("model")
    live_event_feature_row = service._build_live_event_feature_row(
        raw=df,
        live_feature_row=live_feature_row,
        horizon_days=horizon,
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
    try:
        backtest_metrics = service.evaluate_training_candidate(
            virus_typ=virus_typ,
            include_internal_history=include_internal_history,
            region=region_code,
            horizon_days=horizon,
        )
    except Exception as exc:
        logger.warning("Backtest evaluation failed for %s/%s/h%s: %s", virus_typ, region_code, horizon, exc)
        backtest_metrics = {"error": str(exc)}

    if "error" not in backtest_metrics:
        backtest_metrics.update(event_bundle.get("calibrated_metrics") or {})
        backtest_metrics["probability_source"] = event_bundle.get("probability_source")
        backtest_metrics["event_model_family"] = event_bundle.get("model_family")
        backtest_metrics["calibration_mode"] = event_bundle.get("calibration_mode")
        backtest_metrics["fallback_reason"] = event_bundle.get("fallback_reason")
        backtest_metrics["reliability_metrics"] = event_bundle.get("reliability_metrics") or {}
        backtest_metrics["reliability_source"] = event_bundle.get("reliability_source")
        backtest_metrics["reliability_score"] = event_bundle.get("reliability_score")

    model_version = f"xgb_stack_direct_h{horizon}_inline"
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
            probability_source=str(event_bundle.get("probability_source") or "empirical_event_prevalence"),
            calibration_mode=str(event_bundle.get("calibration_mode") or "raw_probability"),
            fallback_reason=event_bundle.get("fallback_reason"),
            learned_model_version=model_version,
            forecast_ready="error" not in backtest_metrics,
            drift_status="unknown",
        ),
    )

    result: dict[str, Any] = {
        "virus_typ": virus_typ,
        "region": region_code,
        "horizon_days": horizon,
        "training_samples": len(df),
        "forecast_days": horizon,
        "data_frequency_days": horizon,
        "forecast": forecast_records,
        "feature_names": feature_names,
        "feature_importance": feature_importance,
        "model_version": model_version,
        "confidence": contracts["event_forecast"].get("reliability_score"),
        "training_window": {
            "start": df["ds"].min().isoformat(),
            "end": df["ds"].max().isoformat(),
            "samples": int(len(df)),
            "panel_rows": int(len(panel)),
        },
        "backtest_metrics": backtest_metrics,
        "contracts": contracts,
        "timestamp": utc_now_fn(),
    }

    logger.info(
        "Forecast completed for %s/%s/h%s: target_date=%s, features=%s",
        virus_typ,
        region_code,
        horizon,
        target_date.date(),
        len(feature_importance),
    )
    return result


def save_forecast(
    service: Any,
    forecast_data: dict[str, Any],
    *,
    normalize_forecast_region_fn: Any,
    ensure_supported_horizon_fn: Any,
    normalize_event_forecast_payload_fn: Any,
    default_decision_horizon_days: int,
    ml_forecast_cls: Any,
    logger: Any,
) -> int:
    logger.info("Saving forecast to database...")
    count = 0
    region_code = normalize_forecast_region_fn(forecast_data.get("region"))
    horizon = ensure_supported_horizon_fn(
        forecast_data.get("horizon_days", default_decision_horizon_days)
    )
    contracts_payload = forecast_data.get("contracts") or {}
    raw_event_forecast = contracts_payload.get("event_forecast") or {}
    normalized_event_forecast = normalize_event_forecast_payload_fn(raw_event_forecast)
    stored_confidence = normalized_event_forecast.get("reliability_score")
    if stored_confidence is None and forecast_data.get("confidence") is not None:
        normalized_event_forecast["reliability_score"] = float(forecast_data["confidence"])
        normalized_event_forecast = normalize_event_forecast_payload_fn(normalized_event_forecast)
        stored_confidence = normalized_event_forecast.get("reliability_score")
    if stored_confidence is None:
        stored_confidence = forecast_data.get("confidence", 0.95)

    for item in forecast_data["forecast"]:
        existing = (
            service.db.query(ml_forecast_cls)
            .filter(
                ml_forecast_cls.forecast_date == item["ds"],
                ml_forecast_cls.virus_typ == forecast_data["virus_typ"],
                ml_forecast_cls.region == region_code,
                ml_forecast_cls.horizon_days == horizon,
            )
            .first()
        )

        kwargs = {
            "predicted_value": item["yhat"],
            "lower_bound": item["yhat_lower"],
            "upper_bound": item["yhat_upper"],
            "confidence": stored_confidence,
            "model_version": forecast_data["model_version"],
            "features_used": {
                "feature_names": forecast_data.get("feature_names", []),
                "feature_importance": forecast_data.get("feature_importance", {}),
                "training_window": forecast_data.get("training_window"),
                "backtest_metrics": forecast_data.get("backtest_metrics"),
                "event_forecast": normalized_event_forecast,
                "forecast_quality": ((forecast_data.get("contracts") or {}).get("forecast_quality") or {}),
            },
            "trend_momentum_7d": item.get("trend_momentum_7d"),
            "outbreak_risk_score": item.get("outbreak_risk_score"),
        }

        if existing:
            for key, val in kwargs.items():
                setattr(existing, key, val)
        else:
            forecast_record = ml_forecast_cls(
                forecast_date=item["ds"],
                virus_typ=forecast_data["virus_typ"],
                region=region_code,
                horizon_days=horizon,
                **kwargs,
            )
            service.db.add(forecast_record)
            count += 1

    service.db.commit()
    logger.info(f"Saved {count} new forecast records")
    return count


def run_forecasts_for_all_viruses(
    service: Any,
    *,
    region: str,
    horizon_days: int,
    include_internal_history: bool,
    normalize_forecast_region_fn: Any,
    ensure_supported_horizon_fn: Any,
    default_forecast_region: str,
    default_decision_horizon_days: int,
    logger: Any,
) -> dict[str, Any]:
    region_code = normalize_forecast_region_fn(region or default_forecast_region)
    horizon = ensure_supported_horizon_fn(horizon_days or default_decision_horizon_days)
    virus_types = ["Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"]

    results: dict[str, Any] = {}
    for virus in virus_types:
        logger.info(f"Processing forecast for {virus}/{region_code}/h{horizon}...")
        try:
            forecast = service.predict(
                virus_typ=virus,
                region=region_code,
                horizon_days=horizon,
                include_internal_history=include_internal_history,
            )
            if "error" not in forecast:
                service.save_forecast(forecast)
            results[virus] = forecast
        except Exception as e:
            logger.error(f"Forecast failed for {virus}: {e}")
            results[virus] = {"error": str(e)}

    return results
