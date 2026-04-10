from __future__ import annotations

from typing import Any


def evaluate_training_candidate(
    service: Any,
    virus_typ: str,
    *,
    include_internal_history: bool,
    model_config: dict[str, dict[str, Any]] | None,
    n_windows: int | None,
    walk_forward_stride: int,
    max_splits: int | None,
    region: str,
    horizon_days: int,
    normalize_forecast_region_fn: Any,
    ensure_supported_horizon_fn: Any,
    default_forecast_region: str,
    default_decision_horizon_days: int,
    default_walk_forward_stride: int,
    min_direct_train_points: int,
    build_walk_forward_splits_fn: Any,
    compute_regression_metrics_fn: Any,
    compute_classification_metrics_fn: Any,
    summarize_probabilistic_metrics_fn: Any,
    np_module: Any,
    pd_module: Any,
) -> dict[str, Any]:
    region_code = normalize_forecast_region_fn(region or default_forecast_region)
    horizon = ensure_supported_horizon_fn(horizon_days or default_decision_horizon_days)
    stride = max(int(walk_forward_stride or default_walk_forward_stride), 1)
    effective_max_splits = int(max_splits) if max_splits is not None else (
        int(n_windows) if n_windows is not None else None
    )
    df = service.prepare_training_data(
        virus_typ=virus_typ,
        include_internal_history=include_internal_history,
        region=region_code,
    )

    panel = service._build_direct_training_panel_from_frame(
        df,
        horizon_days=horizon,
        n_splits=max(int(effective_max_splits or 5), 3),
    )

    if panel.empty or len(panel) < max(min_direct_train_points, 24):
        return {
            "error": f"Insufficient training data ({len(panel) if not panel.empty else 0} rows)",
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
            "include_internal_history": include_internal_history,
        }

    predictions: list[float] = []
    predictions_lo: list[float] = []
    predictions_hi: list[float] = []
    baseline_predictions: list[float] = []
    baseline_predictions_lo: list[float] = []
    baseline_predictions_hi: list[float] = []
    actuals: list[float] = []
    labels: list[float] = []
    windows: list[dict[str, Any]] = []
    event_bundle = service._build_event_probability_model_from_panel(
        panel,
        walk_forward_stride=stride,
        max_splits=effective_max_splits,
    )
    event_oof = event_bundle.get("oof_frame")
    probability_by_issue_date = {}
    if isinstance(event_oof, pd_module.DataFrame) and not event_oof.empty:
        ordered_event_oof = event_oof.sort_values("issue_date").drop_duplicates("issue_date", keep="last")
        probability_by_issue_date = {
            pd_module.Timestamp(row["issue_date"]).normalize(): float(row["event_probability_calibrated"])
            for _, row in ordered_event_oof.iterrows()
        }
    splits = build_walk_forward_splits_fn(
        len(panel),
        min_train_points=max(min_direct_train_points, 24),
        stride=stride,
        max_splits=effective_max_splits,
    )
    for fold, split in enumerate(splits, start=1):
        train_panel = panel.iloc[: split.train_end_idx].copy()
        test_panel = panel.iloc[[split.test_idx]].copy()
        if len(train_panel) < max(min_direct_train_points, 24) or test_panel.empty:
            continue

        model_med, model_lo, model_hi, feature_names, _ = service._fit_xgboost_meta_from_panel(
            train_panel,
            target_column="y_target",
            model_config=model_config,
        )
        X_test = test_panel[feature_names].to_numpy(dtype=float)
        X_test = np_module.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

        pred = max(0.0, float(model_med.predict(X_test)[0]))
        pred_lo = max(0.0, float(model_lo.predict(X_test)[0]))
        pred_hi = max(0.0, float(model_hi.predict(X_test)[0]))
        actual = float(test_panel.iloc[0]["y_target"])
        current = max(float(test_panel.iloc[0]["current_y"]), 1.0)
        persistence_scale = max(
            float(np_module.std(train_panel["y_target"].to_numpy(dtype=float))) if len(train_panel) > 1 else 1.0,
            1.0,
        )
        issue_date_value = pd_module.Timestamp(test_panel.iloc[0]["issue_date"]).normalize()
        event_probability = probability_by_issue_date.get(issue_date_value)
        if event_probability is None:
            event_probability = float(event_bundle.get("calibrated_metrics", {}).get("prevalence") or 0.0)

        predictions.append(pred)
        predictions_lo.append(pred_lo)
        predictions_hi.append(pred_hi)
        baseline_predictions.append(current)
        baseline_predictions_lo.append(max(current - persistence_scale, 0.0))
        baseline_predictions_hi.append(current + persistence_scale)
        actuals.append(actual)
        labels.append(float(test_panel.iloc[0]["event_target"]))
        windows.append(
            {
                "fold": fold,
                "issue_date": issue_date_value.isoformat(),
                "target_date": pd_module.Timestamp(test_panel.iloc[0]["target_date"]).isoformat(),
                "predicted": round(pred, 4),
                "actual": round(actual, 4),
                "event_probability": round(float(event_probability), 4),
            }
        )

    if not predictions:
        return {
            "error": "No validation windows available",
            "virus_typ": virus_typ,
            "region": region_code,
            "horizon_days": horizon,
            "include_internal_history": include_internal_history,
        }

    metrics = compute_regression_metrics_fn(predictions, actuals)
    event_probabilities = [float(item["event_probability"]) for item in windows]
    metrics.update(compute_classification_metrics_fn(event_probabilities, labels))
    metrics.update(
        summarize_probabilistic_metrics_fn(
            y_true=actuals,
            quantile_predictions={
                0.1: predictions_lo,
                0.5: predictions,
                0.9: predictions_hi,
            },
            baseline_quantiles={
                0.1: baseline_predictions_lo,
                0.5: baseline_predictions,
                0.9: baseline_predictions_hi,
            },
            event_labels=labels,
            event_probabilities=event_probabilities,
            action_threshold=0.5,
        )
    )
    metrics["windows"] = windows
    metrics["window_count"] = len(windows)
    metrics["horizon_days"] = horizon
    metrics["region"] = region_code
    metrics["training_window"] = {
        "start": df["ds"].min().isoformat(),
        "end": df["ds"].max().isoformat(),
        "samples": int(len(df)),
        "panel_rows": int(len(panel)),
    }
    metrics["walk_forward"] = {
        "enabled": True,
        "folds": len(windows),
        "min_train_points": max(min_direct_train_points, 24),
        "horizon_days": horizon,
        "region": region_code,
        "strategy": "direct",
        "stride": stride,
        "max_splits": effective_max_splits,
    }
    metrics["probability_source"] = event_bundle.get("probability_source")
    metrics["event_model_family"] = event_bundle.get("model_family")
    metrics["calibration_mode"] = event_bundle.get("calibration_mode")
    metrics["fallback_reason"] = event_bundle.get("fallback_reason")
    metrics["reliability_metrics"] = event_bundle.get("reliability_metrics") or {}
    metrics["reliability_source"] = event_bundle.get("reliability_source")
    metrics["reliability_score"] = event_bundle.get("reliability_score")
    metrics["include_internal_history"] = include_internal_history
    return metrics
