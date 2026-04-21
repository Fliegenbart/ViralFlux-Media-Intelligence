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

    # 2026-04-21 A1 Root-Cause-Fix: AMELAG ist ~13 Tage hinterher, dadurch
    # lag ``df["ds"].max()`` vor dem Fix immer 13 Tage in der Vergangenheit.
    # Die resultierende Forecast-Trajektorie endete dann bei ``today - 6``
    # (retrospektiver Fan). Wir extendieren das Feature-Frame jetzt per
    # Forward-Fill bis ``today`` und setzen ``issue_date = today``, so dass
    # die Trajektorie echte Zukunftspunkte ``today+1 .. today+horizon``
    # abdeckt. Die Metadaten (feature_as_of, days_forward_filled) wandern
    # in die gespeicherte ml_forecasts-Zeile, damit der Cockpit-Snapshot
    # das Feature-Alter ehrlich anzeigen kann.
    from app.services.ml.forecast_service_nowcast_extension import (
        extend_training_frame_to_today,
    )
    today_ts = pd_module.Timestamp(utc_now_fn()).normalize()
    df, extension_meta = extend_training_frame_to_today(
        df,
        today=today_ts,
        is_holiday_fn=(
            (lambda d: service._is_holiday(d, region=region_code))
            if hasattr(service, "_is_holiday")
            else None
        ),
        pd_module=pd_module,
        np_module=np_module,
        timedelta_cls=timedelta_cls,
        logger=logger,
    )

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

    raw_prediction = max(0.0, float(model_med.predict(X_row)[0]))
    raw_lower_bound = max(0.0, float(model_lo.predict(X_row)[0]))
    raw_upper_bound = max(0.0, float(model_hi.predict(X_row)[0]))
    raw_lower_bound = min(raw_lower_bound, raw_prediction)
    raw_upper_bound = max(raw_upper_bound, raw_prediction)

    # 2026-04-21 Scale-Kalibrierung: das national-XGB-Modell hat einen
    # systematischen Skalen-Bias (Predicted ~1200-1700 vs. Observed
    # ~400-500 in Peak-Saison 2026). Wir korrigieren T+h-Prediction +
    # Intervall-Bounds per linearer Transformation, die aus den letzten
    # N historischen Forecast-Actual-Paaren gefittet wird. Sicherheits-
    # Fallback auf Identitaet bei zu wenig Paaren oder fehlender
    # RMSE-Verbesserung (siehe forecast_service_scale_calibration).
    from app.services.ml.forecast_service_scale_calibration import (
        fit_scale_calibrator,
        apply_scale_calibration,
    )
    calibration_pairs = _collect_calibration_pairs(
        service=service,
        virus_typ=virus_typ,
        region_code=region_code,
        horizon_days=horizon,
        today=today_ts,
        max_samples=30,
        timedelta_cls=timedelta_cls,
    )
    calibrator = fit_scale_calibrator(calibration_pairs)
    prediction = apply_scale_calibration(raw_prediction, calibrator)
    lower_bound = apply_scale_calibration(raw_lower_bound, calibrator)
    upper_bound = apply_scale_calibration(raw_upper_bound, calibrator)
    # Preserve ordering after calibration (linear transform keeps it if
    # beta > 0, but the clamps can in pathological cases flip it).
    lower_bound = min(lower_bound, prediction)
    upper_bound = max(upper_bound, prediction)

    # A1 Root-Cause-Fix: ``issue_date`` ist jetzt today, nicht mehr das letzte
    # AMELAG-Datum — die Trajektorie deckt echte Zukunftspunkte ab. Das letzte
    # bekannte Truth-Datum wird separat als ``feature_as_of`` persistiert.
    issue_date = today_ts.to_pydatetime()
    feature_as_of = extension_meta.get("feature_as_of")
    days_forward_filled = int(extension_meta.get("days_forward_filled") or 0)
    last_momentum = float(df["trend_momentum_7d"].iloc[-1]) if "trend_momentum_7d" in df.columns else 0.0
    risk = service._compute_outbreak_risk(prediction, y)
    current_y = float(y[-1]) if len(y) > 0 else prediction
    # Trajektorie über alle h Tage statt nur T+h — siehe
    # ``forecast_service_pipeline._expand_forecast_trajectory`` für die
    # Uncertainty-Expansion-Semantik.
    from app.services.ml.forecast_service_pipeline import _expand_forecast_trajectory
    forecast_records: list[dict[str, Any]] = _expand_forecast_trajectory(
        issue_date=issue_date,
        horizon=horizon,
        current_y=current_y,
        prediction=prediction,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        last_momentum=last_momentum,
        outbreak_risk=risk,
        timedelta_cls=timedelta_cls,
    )

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
        # A1 Root-Cause-Fix — feature-freshness transparency. ``save_forecast``
        # merges this dict into ``ml_forecasts.features_used`` so the cockpit
        # snapshot can render "Features as of …" without a second DB hop.
        "feature_freshness": {
            "feature_as_of": feature_as_of,
            "issue_date": issue_date.date().isoformat() if hasattr(issue_date, "date") else None,
            "days_forward_filled": days_forward_filled,
            "extension_reason": extension_meta.get("reason"),
            "extension_applied": bool(extension_meta.get("applied")),
        },
        # 2026-04-21 Scale-Kalibrierung — raw model output vor der
        # Kalibrierung + Kalibrator-Koeffizienten, damit der Cockpit
        # transparent zeigen kann, wie weit der Post-hoc-Fit reicht.
        "scale_calibration": {
            **calibrator,
            "raw_prediction": round(raw_prediction, 3),
            "calibrated_prediction": round(prediction, 3),
        },
        "timestamp": utc_now_fn(),
    }

    _final_target = forecast_records[-1]["ds"] if forecast_records else issue_date
    logger.info(
        f"Inference completed for {virus_typ}/{region_code}/h{horizon}: "
        f"points={len(forecast_records)} target_date={_final_target.date() if hasattr(_final_target, 'date') else _final_target} "
        f"model={model_version}"
    )
    return result


def _collect_calibration_pairs(
    *,
    service,
    virus_typ: str,
    region_code: str,
    horizon_days: int,
    today: Any,
    max_samples: int,
    timedelta_cls: Any,
) -> list[tuple[float, float]]:
    """Pull historical (predicted, actual) pairs for the scale calibrator.

    We use the latest ``ml_forecasts`` rows whose ``forecast_date`` lies in
    the past (so an actual WastewaterAggregated value can be joined) and
    match each to the nearest aggregated measurement within ±1 day. The
    prediction value we compare against is intentionally the raw model
    output persisted in ``ml_forecasts.predicted_value`` — which today
    already reflects any previous calibration round. In practice that
    means the calibrator converges after 2-3 task cycles: the first
    cycle fits against the raw bias, subsequent cycles fine-tune against
    the residual. This keeps the helper simple and still self-correcting.
    """
    from sqlalchemy import func  # local import to match module style

    from app.models.database import MLForecast, WastewaterAggregated

    cutoff = today.to_pydatetime() if hasattr(today, "to_pydatetime") else today
    try:
        forecasts = (
            service.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ == virus_typ,
                MLForecast.region == region_code,
                MLForecast.horizon_days == horizon_days,
                MLForecast.forecast_date < cutoff,
            )
            .order_by(MLForecast.forecast_date.desc())
            .limit(max_samples * 3)  # loose upper bound; we will keep pairs that join
            .all()
        )
    except Exception:
        return []

    pairs: list[tuple[float, float]] = []
    for fc in forecasts:
        try:
            ww = (
                service.db.query(WastewaterAggregated)
                .filter(
                    WastewaterAggregated.virus_typ == virus_typ,
                    WastewaterAggregated.datum >= fc.forecast_date - timedelta_cls(days=1),
                    WastewaterAggregated.datum <= fc.forecast_date + timedelta_cls(days=1),
                )
                .order_by(WastewaterAggregated.datum.asc())
                .first()
            )
        except Exception:
            ww = None
        if ww is None:
            continue
        # The model is trained on raw ``viruslast`` — match the same scale
        # the accuracy task uses (see ``_select_forecast_accuracy_actual``).
        actual_value = getattr(ww, "viruslast", None)
        if actual_value is None or fc.predicted_value is None:
            continue
        try:
            pairs.append((float(fc.predicted_value), float(actual_value)))
        except (TypeError, ValueError):
            continue
        if len(pairs) >= max_samples:
            break
    return pairs
