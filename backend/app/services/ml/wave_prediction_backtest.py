"""Backtest helpers for wave prediction."""

from __future__ import annotations

from typing import Any


def run_wave_backtest(
    service: Any,
    *,
    pathogen: str,
    region: str | None = None,
    lookback_days: int | None = None,
    horizon_days: int | None = None,
    panel: Any | None = None,
    include_oof_predictions: bool = False,
    normalize_virus_type_fn: Any,
    get_regression_feature_columns_fn: Any,
    get_classification_feature_columns_fn: Any,
    build_backtest_splits_fn: Any,
    mean_absolute_error_fn: Any,
    false_alarm_rate_fn: Any,
    mean_lead_time_days_fn: Any,
    safe_mape_fn: Any,
    safe_pr_auc_fn: Any,
    safe_roc_auc_fn: Any,
    precision_score_fn: Any,
    recall_score_fn: Any,
    f1_score_fn: Any,
    brier_score_loss_fn: Any,
    json_safe_fn: Any,
    np_module: Any,
    pd_module: Any,
) -> dict[str, Any]:
    normalized_pathogen = normalize_virus_type_fn(pathogen)
    frame = (
        panel.copy()
        if panel is not None
        else service.build_wave_panel(
            pathogen=normalized_pathogen,
            region=region,
            lookback_days=lookback_days or service.settings.WAVE_PREDICTION_LOOKBACK_DAYS,
            horizon_days=horizon_days or service.settings.WAVE_PREDICTION_HORIZON_DAYS,
        )
    )
    frame = frame.dropna(subset=["target_regression", "target_wave14"]).copy()
    if frame.empty:
        return {"status": "error", "pathogen": normalized_pathogen, "error": "No backtest rows available."}

    regression_columns = get_regression_feature_columns_fn(frame)
    classification_columns = get_classification_feature_columns_fn(frame)
    unique_dates = sorted(pd_module.to_datetime(frame["as_of_date"]).dt.normalize().unique())
    splits = build_backtest_splits_fn(
        unique_dates,
        n_splits=int(service.settings.WAVE_PREDICTION_BACKTEST_FOLDS),
        min_train_periods=int(service.settings.WAVE_PREDICTION_MIN_TRAIN_PERIODS),
        min_test_periods=int(service.settings.WAVE_PREDICTION_MIN_TEST_PERIODS),
    )
    if not splits:
        return {
            "status": "error",
            "pathogen": normalized_pathogen,
            "error": "Insufficient periods for walk-forward validation.",
        }

    fold_metrics: list[dict[str, Any]] = []
    oof_rows: list[Any] = []
    for fold_idx, (train_dates, test_dates) in enumerate(splits, start=1):
        train_frame = frame.loc[frame["as_of_date"].isin(train_dates)].copy()
        test_frame = frame.loc[frame["as_of_date"].isin(test_dates)].copy()
        if train_frame.empty or test_frame.empty:
            continue

        regressor_bundle = service.train_regression_model(train_frame, feature_columns=regression_columns)
        classifier_bundle = service.train_wave_classifier(train_frame, feature_columns=classification_columns)
        regressor = regressor_bundle["regressor"]
        classifier = classifier_bundle["classifier"]
        calibration = classifier_bundle.get("calibration")
        threshold = float(classifier_bundle["threshold"])

        x_reg = test_frame[regression_columns].fillna(0.0).to_numpy(dtype=float)
        x_clf = test_frame[classification_columns].fillna(0.0).to_numpy(dtype=float)
        regression_pred = np_module.expm1(regressor.predict(x_reg))
        raw_scores = classifier.predict_proba(x_clf)[:, 1]
        probabilities = service._apply_calibration(calibration, raw_scores) if calibration is not None else None
        decision_scores = probabilities if probabilities is not None else raw_scores
        predicted_flags = (decision_scores >= threshold).astype(int)
        output_field = "wave_probability" if probabilities is not None else "wave_score"

        test_frame = test_frame.copy()
        test_frame["fold"] = fold_idx
        test_frame["regression_prediction"] = regression_pred
        test_frame["wave_score_raw"] = raw_scores
        test_frame["decision_score"] = decision_scores
        test_frame["score_output_field"] = output_field
        if probabilities is not None:
            test_frame["wave_probability"] = probabilities
        else:
            test_frame["wave_score"] = raw_scores
        test_frame["wave_flag"] = predicted_flags
        oof_rows.append(test_frame)

        y_true = test_frame["target_wave14"].astype(int).to_numpy()
        score_values = probabilities if probabilities is not None else raw_scores
        tp = int(np_module.sum((y_true == 1) & (predicted_flags == 1)))
        fp = int(np_module.sum((y_true == 0) & (predicted_flags == 1)))
        tn = int(np_module.sum((y_true == 0) & (predicted_flags == 0)))
        fn = int(np_module.sum((y_true == 1) & (predicted_flags == 0)))
        fold_metrics.append(
            {
                "fold": fold_idx,
                "train_start": str(min(train_dates)),
                "train_end": str(max(train_dates)),
                "test_start": str(min(test_dates)),
                "test_end": str(max(test_dates)),
                "rows": int(len(test_frame)),
                "positive_rows": int(np_module.sum(y_true == 1)),
                "mae": float(mean_absolute_error_fn(test_frame["target_regression"], regression_pred)),
                "rmse": float(np_module.sqrt(np_module.mean((test_frame["target_regression"].to_numpy() - regression_pred) ** 2))),
                "mape": safe_mape_fn(test_frame["target_regression"], regression_pred),
                "roc_auc": safe_roc_auc_fn(y_true, score_values),
                "pr_auc": safe_pr_auc_fn(y_true, score_values),
                "brier_score": (
                    float(brier_score_loss_fn(y_true, score_values))
                    if len(np_module.unique(y_true)) > 1
                    else None
                ),
                "precision": float(precision_score_fn(y_true, predicted_flags, zero_division=0)),
                "recall": float(recall_score_fn(y_true, predicted_flags, zero_division=0)),
                "f1": float(f1_score_fn(y_true, predicted_flags, zero_division=0)),
                "ece": (
                    float(service._compute_calibration_summary(y_true, score_values))
                    if probabilities is not None
                    else None
                ),
                "false_alarm_rate": false_alarm_rate_fn(y_true, predicted_flags),
                "mean_lead_time_days": mean_lead_time_days_fn(
                    test_frame["as_of_date"],
                    test_frame["wave_event_date"],
                    y_true,
                    predicted_flags,
                ),
                "probability_output": bool(probabilities is not None),
                "output_field": output_field,
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
            }
        )

    aggregate = service._aggregate_fold_metrics(fold_metrics)
    oof_frame = pd_module.concat(oof_rows, ignore_index=True) if oof_rows else pd_module.DataFrame()
    payload = {
        "status": "ok",
        "pathogen": normalized_pathogen,
        "horizon_days": int(horizon_days or service.settings.WAVE_PREDICTION_HORIZON_DAYS),
        "folds": fold_metrics,
        "aggregate_metrics": aggregate,
        "oof_rows": int(len(oof_frame.index)),
    }
    if include_oof_predictions:
        payload["oof_predictions"] = json_safe_fn(oof_frame.to_dict(orient="records"))
    return payload
