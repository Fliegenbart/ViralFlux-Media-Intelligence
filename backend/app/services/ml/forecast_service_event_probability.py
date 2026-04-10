from __future__ import annotations

from typing import Any


def fit_event_classifier_model(
    train_df,
    *,
    feature_names: list[str],
    model_family: str,
    np_module,
    empirical_event_classifier_cls,
    default_event_classifier_config,
    pipeline_cls,
    standard_scaler_cls,
    logistic_regression_cls,
) -> Any:
    X_train = train_df[feature_names].to_numpy(dtype=float)
    y_train = train_df["event_target"].to_numpy(dtype=int)
    positives = int(np_module.sum(y_train == 1))
    negatives = int(np_module.sum(y_train == 0))
    if min(positives, negatives) <= 0:
        return empirical_event_classifier_cls(float(np_module.mean(y_train) if len(y_train) else 0.0))

    if model_family == "xgb_classifier":
        from xgboost import XGBClassifier

        config = dict(default_event_classifier_config)
        config["scale_pos_weight"] = float(negatives / max(positives, 1))
        model = XGBClassifier(**config)
        model.fit(X_train, y_train)
        return model

    model = pipeline_cls(
        steps=[
            ("scaler", standard_scaler_cls()),
            (
                "classifier",
                logistic_regression_cls(
                    max_iter=1000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    return model


def build_event_oof_predictions(
    service,
    panel,
    *,
    feature_names: list[str],
    model_family: str,
    walk_forward_stride: int,
    max_splits: int | None,
    min_train_points: int,
    default_walk_forward_stride,
    min_direct_train_points,
    build_walk_forward_splits_fn,
    np_module,
    pd_module,
):
    stride = walk_forward_stride if walk_forward_stride is not None else default_walk_forward_stride
    min_points = min_train_points if min_train_points is not None else max(min_direct_train_points, 24)
    splits = build_walk_forward_splits_fn(
        len(panel),
        min_train_points=min_points,
        stride=stride,
        max_splits=max_splits,
    )
    if not splits:
        return pd_module.DataFrame()

    frames: list[Any] = []
    for fold_idx, split in enumerate(splits, start=1):
        train_df = panel.iloc[: split.train_end_idx].copy()
        test_df = panel.iloc[[split.test_idx]].copy()
        if len(train_df) < min_points or test_df.empty:
            continue
        if train_df["event_target"].nunique() < 2:
            raw_prob = np_module.full(
                len(test_df),
                float(train_df["event_target"].mean() or 0.0),
                dtype=float,
            )
        else:
            model = service._fit_event_classifier_model(
                train_df,
                feature_names=feature_names,
                model_family=model_family,
            )
            raw_prob = np_module.asarray(
                model.predict_proba(test_df[feature_names].to_numpy(dtype=float))[:, 1],
                dtype=float,
            )
        frames.append(
            pd_module.DataFrame(
                {
                    "fold": fold_idx,
                    "issue_date": pd_module.to_datetime(test_df["issue_date"]).dt.normalize().values,
                    "target_date": pd_module.to_datetime(test_df["target_date"]).dt.normalize().values,
                    "event_target": test_df["event_target"].to_numpy(dtype=int),
                    "event_probability_raw": np_module.clip(raw_prob, 0.001, 0.999),
                }
            )
        )

    if not frames:
        return pd_module.DataFrame()
    return pd_module.concat(frames, ignore_index=True)


def select_best_event_candidate(candidates: list[dict[str, Any]], *, pd_module) -> dict[str, Any] | None:
    valid = [
        candidate
        for candidate in candidates
        if isinstance(candidate.get("oof_frame"), pd_module.DataFrame) and not candidate["oof_frame"].empty
    ]
    if not valid:
        return None
    return min(
        valid,
        key=lambda item: (
            float((item.get("raw_metrics") or {}).get("logloss", float("inf"))),
            float((item.get("raw_metrics") or {}).get("brier_score", float("inf"))),
            -float((item.get("raw_metrics") or {}).get("pr_auc", float("-inf"))),
            -float((item.get("raw_metrics") or {}).get("sample_count", 0.0)),
            str(item.get("model_family") or ""),
        ),
    )


def build_event_probability_model_from_panel(
    service,
    panel,
    *,
    walk_forward_stride: int,
    max_splits: int | None,
    default_walk_forward_stride,
    min_direct_train_points,
    learned_probability_model_cls,
    empirical_event_classifier_cls,
    compute_classification_metrics_fn,
    select_probability_calibration_fn,
    apply_probability_calibration_fn,
    reliability_score_from_metrics_fn,
    np_module,
    pd_module,
) -> dict[str, Any]:
    if panel.empty or "event_target" not in panel.columns:
        prevalence = float(panel["event_target"].mean()) if "event_target" in panel.columns and not panel.empty else 0.0
        fallback_model = learned_probability_model_cls(
            classifier=empirical_event_classifier_cls(prevalence),
            feature_names=[],
            model_family="empirical_prevalence",
            calibration=None,
            calibration_mode="raw_probability",
            probability_source="empirical_event_prevalence",
            fallback_reason="event_training_panel_empty",
            metadata={"prevalence": round(prevalence, 6)},
        )
        return {
            "model": fallback_model,
            "model_family": "empirical_prevalence",
            "feature_names": [],
            "calibration_mode": "raw_probability",
            "probability_source": "empirical_event_prevalence",
            "fallback_reason": "event_training_panel_empty",
            "oof_frame": pd_module.DataFrame(),
            "raw_metrics": {
                "prevalence": round(prevalence, 6),
                "sample_count": float(len(panel)),
                "positive_count": float(np_module.sum(panel["event_target"] == 1))
                if "event_target" in panel.columns
                else 0.0,
                "negative_count": float(np_module.sum(panel["event_target"] == 0))
                if "event_target" in panel.columns
                else 0.0,
            },
            "calibrated_metrics": {},
            "reliability_metrics": {},
            "reliability_source": "unavailable",
            "reliability_score": None,
        }

    feature_names = service._event_feature_columns(panel)
    if not feature_names:
        prevalence = float(panel["event_target"].mean() or 0.0)
        fallback_model = learned_probability_model_cls(
            classifier=empirical_event_classifier_cls(prevalence),
            feature_names=[],
            model_family="empirical_prevalence",
            calibration=None,
            calibration_mode="raw_probability",
            probability_source="empirical_event_prevalence",
            fallback_reason="event_feature_columns_missing",
            metadata={"prevalence": round(prevalence, 6)},
        )
        return {
            "model": fallback_model,
            "model_family": "empirical_prevalence",
            "feature_names": [],
            "calibration_mode": "raw_probability",
            "probability_source": "empirical_event_prevalence",
            "fallback_reason": "event_feature_columns_missing",
            "oof_frame": pd_module.DataFrame(),
            "raw_metrics": {
                "prevalence": round(prevalence, 6),
                "sample_count": float(len(panel)),
                "positive_count": float(np_module.sum(panel["event_target"] == 1)),
                "negative_count": float(np_module.sum(panel["event_target"] == 0)),
            },
            "calibrated_metrics": {},
            "reliability_metrics": {},
            "reliability_source": "unavailable",
            "reliability_score": None,
        }

    candidate_payloads: list[dict[str, Any]] = []
    min_train_points = max(min_direct_train_points, 24)
    for model_family in service._event_model_candidates():
        oof_frame = service._build_event_oof_predictions(
            panel,
            feature_names=feature_names,
            model_family=model_family,
            walk_forward_stride=walk_forward_stride,
            max_splits=max_splits,
            min_train_points=min_train_points,
        )
        if oof_frame.empty:
            continue
        raw_metrics = compute_classification_metrics_fn(
            oof_frame["event_probability_raw"].to_numpy(dtype=float),
            oof_frame["event_target"].to_numpy(dtype=int),
        )
        candidate_payloads.append(
            {
                "model_family": model_family,
                "feature_names": feature_names,
                "oof_frame": oof_frame,
                "raw_metrics": raw_metrics,
            }
        )

    selected = service._select_best_event_candidate(candidate_payloads)
    if selected is None:
        prevalence = float(panel["event_target"].mean() or 0.0)
        fallback_model = learned_probability_model_cls(
            classifier=empirical_event_classifier_cls(prevalence),
            feature_names=feature_names,
            model_family="empirical_prevalence",
            calibration=None,
            calibration_mode="raw_probability",
            probability_source="empirical_event_prevalence",
            fallback_reason="insufficient_valid_event_oof_rows",
            metadata={"prevalence": round(prevalence, 6)},
        )
        fallback_metrics = compute_classification_metrics_fn(
            np_module.full(len(panel), prevalence, dtype=float),
            panel["event_target"].to_numpy(dtype=int),
        )
        return {
            "model": fallback_model,
            "model_family": "empirical_prevalence",
            "feature_names": feature_names,
            "calibration_mode": "raw_probability",
            "probability_source": "empirical_event_prevalence",
            "fallback_reason": "insufficient_valid_event_oof_rows",
            "oof_frame": pd_module.DataFrame(),
            "raw_metrics": fallback_metrics,
            "calibrated_metrics": fallback_metrics,
            "reliability_metrics": fallback_metrics,
            "reliability_source": "oof_full_sample",
            "reliability_score": reliability_score_from_metrics_fn(fallback_metrics),
        }

    calibration_payload = select_probability_calibration_fn(
        selected["oof_frame"][["issue_date", "event_target", "event_probability_raw"]].rename(
            columns={"issue_date": "as_of_date", "event_target": "event_label"}
        ),
        raw_probability_col="event_probability_raw",
        label_col="event_label",
        date_col="as_of_date",
    )
    calibration = calibration_payload.get("calibration")
    calibrated_probs = apply_probability_calibration_fn(
        calibration,
        selected["oof_frame"]["event_probability_raw"].to_numpy(dtype=float),
    )
    calibrated_metrics = compute_classification_metrics_fn(
        calibrated_probs,
        selected["oof_frame"]["event_target"].to_numpy(dtype=int),
    )
    oof_frame = selected["oof_frame"].copy()
    oof_frame["event_probability_calibrated"] = calibrated_probs

    if panel["event_target"].nunique() < 2:
        final_classifier = empirical_event_classifier_cls(float(panel["event_target"].mean() or 0.0))
    else:
        final_classifier = service._fit_event_classifier_model(
            panel,
            feature_names=feature_names,
            model_family=str(selected["model_family"]),
        )

    probability_source = f"learned_exceedance_{selected['model_family']}"
    model = learned_probability_model_cls(
        classifier=final_classifier,
        feature_names=list(feature_names),
        model_family=str(selected["model_family"]),
        calibration=calibration,
        calibration_mode=str(calibration_payload.get("calibration_mode") or "raw_probability"),
        probability_source=probability_source,
        fallback_reason=calibration_payload.get("fallback_reason"),
        metadata={
            "oof_row_count": int(len(oof_frame)),
            "raw_metrics": selected["raw_metrics"],
            "calibrated_metrics": calibrated_metrics,
            "reliability_metrics": calibration_payload.get("reliability_metrics") or calibrated_metrics,
            "reliability_source": calibration_payload.get("reliability_source"),
        },
    )
    reliability_metrics = calibration_payload.get("reliability_metrics") or calibrated_metrics
    return {
        "model": model,
        "model_family": str(selected["model_family"]),
        "feature_names": list(feature_names),
        "calibration_mode": str(calibration_payload.get("calibration_mode") or "raw_probability"),
        "probability_source": probability_source,
        "fallback_reason": calibration_payload.get("fallback_reason"),
        "oof_frame": oof_frame,
        "raw_metrics": selected["raw_metrics"],
        "calibrated_metrics": calibrated_metrics,
        "reliability_metrics": reliability_metrics,
        "reliability_source": calibration_payload.get("reliability_source"),
        "reliability_score": reliability_score_from_metrics_fn(reliability_metrics),
    }
