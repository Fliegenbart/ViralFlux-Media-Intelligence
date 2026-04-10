"""Training helpers for wave prediction."""

from __future__ import annotations

from typing import Any

from app.services.ml.regional_panel_utils import normalize_state_code


def train_models(
    service: Any,
    *,
    pathogen: str,
    region: str | None = None,
    lookback_days: int | None = None,
    horizon_days: int | None = None,
    persist: bool = True,
    normalize_virus_type_fn: Any,
    get_regression_feature_columns_fn: Any,
    get_classification_feature_columns_fn: Any,
    wave_label_config_for_pathogen_fn: Any,
    top_feature_importance_fn: Any,
    utc_now_fn: Any,
) -> dict[str, Any]:
    normalized_pathogen = normalize_virus_type_fn(pathogen)
    panel = service.build_wave_panel(
        pathogen=normalized_pathogen,
        region=region,
        lookback_days=lookback_days or service.settings.WAVE_PREDICTION_LOOKBACK_DAYS,
        horizon_days=horizon_days or service.settings.WAVE_PREDICTION_HORIZON_DAYS,
    )
    if panel.empty:
        return {"status": "error", "pathogen": normalized_pathogen, "error": "No panel rows available."}

    training_frame = panel.dropna(subset=["target_regression"]).copy()
    if len(training_frame) < int(service.settings.WAVE_PREDICTION_MIN_TRAIN_ROWS):
        return {
            "status": "error",
            "pathogen": normalized_pathogen,
            "error": f"Insufficient training rows ({len(training_frame)}).",
        }

    positives = int(training_frame["target_wave14"].sum())
    if positives < int(service.settings.WAVE_PREDICTION_MIN_POSITIVE_ROWS):
        return {
            "status": "error",
            "pathogen": normalized_pathogen,
            "error": f"Insufficient positive rows ({positives}).",
        }

    backtest = service.run_wave_backtest(
        pathogen=normalized_pathogen,
        region=region,
        lookback_days=lookback_days or service.settings.WAVE_PREDICTION_LOOKBACK_DAYS,
        horizon_days=horizon_days or service.settings.WAVE_PREDICTION_HORIZON_DAYS,
        panel=training_frame,
    )
    regression_columns = get_regression_feature_columns_fn(training_frame)
    classification_columns = get_classification_feature_columns_fn(training_frame)
    regressor_bundle = service.train_regression_model(training_frame, feature_columns=regression_columns)
    classifier_bundle = service.train_wave_classifier(training_frame, feature_columns=classification_columns)
    trained_at = utc_now_fn().isoformat()
    top_features = top_feature_importance_fn(
        classifier=classifier_bundle["classifier"],
        regressor=regressor_bundle["regressor"],
        feature_columns=classification_columns,
    )

    metadata = {
        "pathogen": normalized_pathogen,
        "region_scope": normalize_state_code(region) if region else "ALL",
        "trained_at": trained_at,
        "model_version": f"{service.settings.WAVE_PREDICTION_MODEL_VERSION}:{trained_at}",
        "training_window": {
            "start": str(training_frame["as_of_date"].min()),
            "end": str(training_frame["as_of_date"].max()),
            "rows": int(len(training_frame)),
        },
        "horizon_days": int(horizon_days or service.settings.WAVE_PREDICTION_HORIZON_DAYS),
        "target_definition": {
            "regression_target": "SurvStat incidence at the week containing t + horizon_days",
            "event_target": "Wave start within next 14 days",
            "label_config": wave_label_config_for_pathogen_fn(normalized_pathogen, service.settings).to_manifest(),
        },
        "regression_feature_columns": regression_columns,
        "classification_feature_columns": classification_columns,
        "calibration_status": {
            "available": bool(classifier_bundle.get("calibration")),
            "version": (
                f"isotonic:{trained_at}" if classifier_bundle.get("calibration") else None
            ),
            "notes": classifier_bundle.get("notes") or [],
        },
        "classification_threshold": float(classifier_bundle["threshold"]),
        "metrics": backtest.get("aggregate_metrics") or {},
        "top_features": top_features,
    }
    dataset_manifest = service._dataset_manifest(training_frame)

    if persist:
        service._persist_artifacts(
            pathogen=normalized_pathogen,
            regressor_bundle=regressor_bundle,
            classifier_bundle=classifier_bundle,
            metadata=metadata,
            backtest=backtest,
            dataset_manifest=dataset_manifest,
        )

    return {
        "status": "ok",
        "pathogen": normalized_pathogen,
        "trained_at": trained_at,
        "rows": int(len(training_frame)),
        "positives": positives,
        "metadata": metadata,
        "backtest": backtest,
        "dataset_manifest": dataset_manifest,
    }


def train_regression_model(
    panel: Any,
    *,
    feature_columns: list[str] | None = None,
    get_regression_feature_columns_fn: Any,
    regressor_config: dict[str, Any],
    xgb_regressor_cls: Any,
    mean_absolute_error_fn: Any,
    safe_mape_fn: Any,
    np_module: Any,
) -> dict[str, Any]:
    features = feature_columns or get_regression_feature_columns_fn(panel)
    frame = panel.dropna(subset=["target_regression"]).copy()
    x = frame[features].fillna(0.0).to_numpy(dtype=float)
    y = np_module.log1p(frame["target_regression"].astype(float).clip(lower=0.0).to_numpy())
    regressor = xgb_regressor_cls(**regressor_config)
    regressor.fit(x, y)
    train_pred = np_module.expm1(regressor.predict(x))
    metrics = {
        "mae_train": float(mean_absolute_error_fn(frame["target_regression"], train_pred)),
        "rmse_train": float(np_module.sqrt(np_module.mean((frame["target_regression"].to_numpy() - train_pred) ** 2))),
        "mape_train": safe_mape_fn(frame["target_regression"], train_pred),
    }
    return {
        "regressor": regressor,
        "feature_columns": features,
        "metrics": metrics,
    }


def train_wave_classifier(
    service: Any,
    panel: Any,
    *,
    feature_columns: list[str] | None = None,
    sample_weights: Any | None = None,
    get_classification_feature_columns_fn: Any,
    constant_classifier_cls: Any,
    classifier_config: dict[str, Any],
    xgb_classifier_cls: Any,
    np_module: Any,
    pd_module: Any,
) -> dict[str, Any]:
    features = feature_columns or get_classification_feature_columns_fn(panel)
    frame = panel.dropna(subset=["target_wave14"]).sort_values("as_of_date").reset_index(drop=True)
    unique_dates = sorted(pd_module.to_datetime(frame["as_of_date"]).dt.normalize().unique())
    calibration_days = max(
        int(round(len(unique_dates) * float(service.settings.WAVE_PREDICTION_CALIBRATION_HOLDOUT_FRACTION))),
        int(service.settings.WAVE_PREDICTION_MIN_TEST_PERIODS),
    )
    calibration_dates = set(unique_dates[-calibration_days:]) if len(unique_dates) > calibration_days else set()
    calibration_frame = frame.loc[frame["as_of_date"].isin(calibration_dates)].copy()
    train_frame = frame.loc[~frame["as_of_date"].isin(calibration_dates)].copy()
    if train_frame.empty:
        train_frame = frame.copy()
        calibration_frame = pd_module.DataFrame(columns=frame.columns)

    x_train = train_frame[features].fillna(0.0).to_numpy(dtype=float)
    y_train = train_frame["target_wave14"].astype(int).to_numpy()
    if train_frame["target_wave14"].nunique() < 2:
        constant_classifier = constant_classifier_cls(
            positive_probability=float(y_train[0]) if len(y_train) else 0.0,
            feature_count=len(features),
        )
        return {
            "classifier": constant_classifier,
            "calibration": None,
            "feature_columns": features,
            "threshold": float(service.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD),
            "notes": [
                "Single-class training window detected; using a constant classifier fallback."
            ],
        }
    positives = int(np_module.sum(y_train == 1))
    negatives = int(np_module.sum(y_train == 0))
    scale_pos_weight = float(negatives / positives) if positives > 0 else 1.0
    classifier = xgb_classifier_cls(**(classifier_config | {"scale_pos_weight": scale_pos_weight}))
    fit_sample_weights = None
    if sample_weights is not None and len(sample_weights) == len(train_frame):
        fit_sample_weights = sample_weights
    classifier.fit(x_train, y_train, sample_weight=fit_sample_weights)

    default_threshold = float(service.settings.WAVE_PREDICTION_CLASSIFICATION_THRESHOLD)
    calibration = None
    calibration_notes: list[str] = []
    holdout_scores = None
    holdout_labels = None
    if not calibration_frame.empty and calibration_frame["target_wave14"].nunique() > 1:
        x_holdout = calibration_frame[features].fillna(0.0).to_numpy(dtype=float)
        holdout_labels = calibration_frame["target_wave14"].astype(int).to_numpy()
        holdout_scores = classifier.predict_proba(x_holdout)[:, 1]
    if (
        not calibration_frame.empty
        and len(calibration_frame) >= int(service.settings.WAVE_PREDICTION_MIN_CALIBRATION_ROWS)
        and int(calibration_frame["target_wave14"].sum()) >= int(service.settings.WAVE_PREDICTION_MIN_CALIBRATION_POSITIVES)
        and calibration_frame["target_wave14"].nunique() > 1
    ):
        calibration = service._fit_calibration(
            classifier=classifier,
            calibration_frame=calibration_frame,
            feature_columns=features,
        )
    else:
        calibration_notes.append(
            "Calibration skipped; classifier output must be exposed as wave_score, not wave_probability."
        )

    threshold = default_threshold
    if holdout_scores is not None and holdout_labels is not None:
        strategy = service._resolve_decision_strategy(
            y_true=holdout_labels,
            raw_scores=holdout_scores,
            calibration=calibration,
            default_threshold=default_threshold,
        )
        threshold = float(strategy["threshold"])
        if not bool(strategy["use_calibration"]):
            calibration = None
        calibration_notes.extend(strategy["notes"])

    return {
        "classifier": classifier,
        "calibration": calibration,
        "feature_columns": features,
        "threshold": threshold,
        "notes": calibration_notes,
    }
