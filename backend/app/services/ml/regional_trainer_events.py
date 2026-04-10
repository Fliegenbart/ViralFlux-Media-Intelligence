"""Event-definition and event-probability helpers for RegionalModelTrainer."""

from __future__ import annotations

from typing import Any

import numpy as np


def event_labels(
    panel,
    *,
    virus_typ: str,
    tau: float,
    kappa: float,
    event_config=None,
    np_module,
    build_event_label_fn,
    event_definition_config_for_virus_fn,
):
    config = event_config or event_definition_config_for_virus_fn(virus_typ)
    return np_module.asarray(
        [
            build_event_label_fn(
                current_known_incidence=row.current_known_incidence,
                next_week_incidence=row.next_week_incidence,
                seasonal_baseline=row.seasonal_baseline,
                seasonal_mad=row.seasonal_mad,
                tau=tau,
                kappa=kappa,
                min_absolute_incidence=config.min_absolute_incidence,
            )
            for row in panel.itertuples()
        ],
        dtype=int,
    )


def select_event_definition(
    service,
    *,
    virus_typ: str,
    panel,
    feature_columns: list[str],
    event_config=None,
    event_definition_config_for_virus_fn,
    choose_action_threshold_fn,
    average_precision_safe_fn,
) -> dict[str, Any]:
    config = event_config or event_definition_config_for_virus_fn(virus_typ)
    best: dict[str, Any] | None = None

    for tau in config.tau_grid:
        for kappa in config.kappa_grid:
            labels = service._event_labels(
                panel,
                virus_typ=virus_typ,
                tau=tau,
                kappa=kappa,
                event_config=config,
            )
            if labels.sum() < 12:
                continue
            evaluation = service._oof_classification_predictions(
                panel=panel,
                labels=labels,
                feature_columns=feature_columns,
                min_recall_for_threshold=config.min_recall_for_selection,
            )
            if evaluation is None:
                continue
            threshold, precision, recall = choose_action_threshold_fn(
                evaluation["event_probability_calibrated"],
                evaluation["event_label"],
                min_recall=config.min_recall_for_selection,
            )
            candidate = {
                "tau": tau,
                "kappa": kappa,
                "action_threshold": threshold,
                "precision": precision,
                "recall": recall,
                "pr_auc": average_precision_safe_fn(
                    evaluation["event_label"],
                    evaluation["event_probability_calibrated"],
                ),
                "positive_rate": float(np.mean(labels)),
            }
            if best is None:
                best = candidate
                continue
            if candidate["precision"] > best["precision"]:
                best = candidate
            elif np.isclose(candidate["precision"], best["precision"]):
                if candidate["pr_auc"] > best["pr_auc"] or (
                    np.isclose(candidate["pr_auc"], best["pr_auc"])
                    and candidate["recall"] > best["recall"]
                ):
                    best = candidate

    if best is None:
        best = {
            "tau": float(config.tau_grid[min(len(config.tau_grid) // 2, len(config.tau_grid) - 1)]),
            "kappa": float(config.kappa_grid[min(len(config.kappa_grid) // 2, len(config.kappa_grid) - 1)]),
            "action_threshold": 0.6,
            "precision": 0.0,
            "recall": 0.0,
            "pr_auc": 0.0,
            "positive_rate": 0.0,
        }
    return best


def oof_classification_predictions(
    service,
    *,
    panel,
    labels,
    feature_columns: list[str],
    min_recall_for_threshold: float = 0.35,
    pd_module,
    time_based_panel_splits_fn,
):
    working = panel.copy()
    working["event_label"] = labels.astype(int)
    working["as_of_date"] = pd_module.to_datetime(working["as_of_date"]).dt.normalize()
    splits = time_based_panel_splits_fn(
        working["as_of_date"],
        n_splits=5,
        min_train_periods=90,
        min_test_periods=21,
    )
    if not splits:
        return None

    oof_frames: list[Any] = []
    for fold_idx, (train_dates, test_dates) in enumerate(splits):
        train_mask = working["as_of_date"].isin(train_dates)
        test_mask = working["as_of_date"].isin(test_dates)
        train_df = working.loc[train_mask].copy()
        test_df = working.loc[test_mask].copy()
        if train_df.empty or test_df.empty or train_df["event_label"].nunique() < 2:
            continue

        calib_split = service._calibration_split_dates(train_dates)
        if not calib_split:
            continue
        model_train_dates, cal_dates = calib_split
        model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
        cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
        if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
            continue

        classifier = service._fit_classifier_from_frame(model_train_df, feature_columns)
        calibration, _calibration_mode = service._select_guarded_calibration(
            calibration_frame=pd_module.DataFrame(
                {
                    "as_of_date": cal_df["as_of_date"].values,
                    "event_label": cal_df["event_label"].values.astype(int),
                    "event_probability_raw": classifier.predict_proba(
                        cal_df[feature_columns].to_numpy()
                    )[:, 1],
                }
            ),
            raw_probability_col="event_probability_raw",
            min_recall_for_threshold=min_recall_for_threshold,
        )
        raw_probs = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
        calibrated_probs = service._apply_calibration(calibration, raw_probs)

        oof_frames.append(
            pd_module.DataFrame(
                {
                    "fold": fold_idx,
                    "as_of_date": test_df["as_of_date"].values,
                    "event_label": test_df["event_label"].values,
                    "event_probability_calibrated": calibrated_probs,
                }
            )
        )

    if not oof_frames:
        return None
    return pd_module.concat(oof_frames, ignore_index=True)


def amelag_only_probabilities(
    service,
    *,
    train_df,
    test_df,
    feature_columns: list[str],
    np_module,
):
    if not feature_columns or train_df["event_label"].nunique() < 2:
        base_rate = float(train_df["event_label"].mean() or 0.0)
        return np_module.full(len(test_df), base_rate, dtype=float)

    classifier = service._fit_classifier_from_frame(train_df, feature_columns)
    raw_prob = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
    train_raw = classifier.predict_proba(train_df[feature_columns].to_numpy())[:, 1]
    calibration = service._fit_isotonic(train_raw, train_df["event_label"].to_numpy())
    return service._apply_calibration(calibration, raw_prob)


def event_probability_from_prediction(
    *,
    predicted_next,
    current_known,
    baseline,
    mad,
    tau: float,
    kappa: float,
    min_absolute_incidence: float,
    np_module,
    absolute_incidence_threshold_fn,
):
    predicted_next = np_module.asarray(predicted_next, dtype=float)
    current_known = np_module.asarray(current_known, dtype=float)
    baseline = np_module.asarray(baseline, dtype=float)
    mad = np_module.maximum(np_module.asarray(mad, dtype=float), 1.0)

    relative_gap = np_module.log1p(np_module.maximum(predicted_next, 0.0)) - np_module.log1p(
        np_module.maximum(current_known, 0.0)
    ) - tau
    absolute_threshold = np_module.asarray(
        [
            absolute_incidence_threshold_fn(
                seasonal_baseline=baseline_value,
                seasonal_mad=mad_value,
                kappa=kappa,
                min_absolute_incidence=min_absolute_incidence,
            )
            for baseline_value, mad_value in zip(baseline, mad, strict=False)
        ],
        dtype=float,
    )
    absolute_gap = (predicted_next - absolute_threshold) / mad
    logits = np_module.minimum(relative_gap / max(tau, 0.05), absolute_gap)
    return 1.0 / (1.0 + np_module.exp(-logits))
