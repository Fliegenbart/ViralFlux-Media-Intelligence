"""Event-definition and event-probability helpers for RegionalModelTrainer."""

from __future__ import annotations

from typing import Any

import numpy as np


EVENT_ANCHOR_COLUMNS: tuple[str, ...] = (
    "current_known_incidence",
    "seasonal_baseline",
    "seasonal_mad",
    "survstat_current_incidence",
    "survstat_seasonal_baseline",
    "survstat_seasonal_mad",
    "survstat_baseline_gap",
    "survstat_baseline_zscore",
)

EVENT_RECENCY_HALF_LIFE_DAYS_BY_VIRUS: dict[str, float] = {
    "Influenza A": 180.0,
    "Influenza B": 180.0,
    "RSV A": 120.0,
}

RSV_SIGNAL_AGREEMENT_COLUMNS: tuple[str, ...] = (
    "ifsg_rsv_baseline_zscore",
    "ifsg_rsv_momentum_1w",
    "ifsg_rsv_survstat_zscore_gap",
    "survstat_baseline_zscore",
    "survstat_momentum_2w",
    "survstat_momentum_4w",
    "ww_slope7d",
    "ww_acceleration7d",
    "ww_relative_to_national",
    "ww_relative_to_neighbor_mean",
    "grippeweb_ili_baseline_zscore",
    "grippeweb_ili_momentum_1w",
    "grippeweb_are_baseline_zscore",
    "grippeweb_are_momentum_1w",
    "national_ww_slope7d",
    "neighbor_ww_slope7d",
)

RSV_SIGNAL_AGREEMENT_WEIGHT = 0.35


def event_feature_columns(
    panel,
    *,
    base_feature_columns: list[str],
) -> list[str]:
    columns: list[str] = []
    for name in EVENT_ANCHOR_COLUMNS:
        if name in panel.columns and name not in columns:
            columns.append(name)
    for name in base_feature_columns:
        if name in panel.columns and name not in columns:
            columns.append(name)
    return columns


def event_sample_weights(
    panel,
    *,
    virus_typ: str,
    pd_module,
    np_module,
):
    if panel is None or getattr(panel, "empty", True):
        return None
    normalized_virus = str(virus_typ or "").strip()
    half_life = EVENT_RECENCY_HALF_LIFE_DAYS_BY_VIRUS.get(normalized_virus)
    if not half_life or "as_of_date" not in panel.columns:
        return None
    dates = np_module.asarray(
        pd_module.to_datetime(panel["as_of_date"]).values,
        dtype="datetime64[ns]",
    )
    if len(dates) == 0:
        return None
    latest = dates.max()
    age_days = (latest - dates).astype("timedelta64[D]").astype(float)
    weights = np_module.power(0.5, age_days / max(float(half_life), 1.0))
    weights = weights.astype(float)
    if normalized_virus == "RSV A":
        agreement = _rsv_signal_agreement(panel, np_module=np_module)
        weights *= np_module.clip(
            1.0 + (RSV_SIGNAL_AGREEMENT_WEIGHT * agreement),
            0.5,
            1.75,
        )
    return np_module.clip(weights, 0.05, 2.0)


def _rsv_signal_agreement(panel, *, np_module) -> np.ndarray:
    selected = [column for column in RSV_SIGNAL_AGREEMENT_COLUMNS if column in panel.columns]
    if not selected:
        return np_module.zeros(len(panel), dtype=float)
    values = np_module.asarray(panel[selected].to_numpy(dtype=float), dtype=float)
    values = np_module.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    if values.size == 0:
        return np_module.zeros(len(panel), dtype=float)
    positive_share = np_module.mean(values > 0.0, axis=1)
    negative_share = np_module.mean(values < 0.0, axis=1)
    directional_agreement = np_module.maximum(positive_share - negative_share, 0.0)
    strength = np_module.clip(np_module.mean(np_module.abs(np_module.tanh(values)), axis=1), 0.0, 1.0)
    return np_module.clip((0.55 * directional_agreement) + (0.45 * strength), 0.0, 1.0)


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
    brier_score_safe_fn,
    compute_ece_fn,
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
                virus_typ=virus_typ,
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
                "brier_score": float(
                    brier_score_safe_fn(
                        evaluation["event_label"],
                        evaluation["event_probability_calibrated"],
                    )
                ),
                "ece": float(
                    compute_ece_fn(
                        evaluation["event_label"],
                        evaluation["event_probability_calibrated"],
                    )
                ),
                "positive_rate": float(np.mean(labels)),
            }
            candidate_key = (
                -float(candidate["pr_auc"]),
                float(candidate["brier_score"]),
                float(candidate["ece"]),
                -float(candidate["precision"]),
                -float(candidate["recall"]),
            )
            if best is None:
                best = {**candidate, "_selection_key": candidate_key}
                continue
            if candidate_key < best["_selection_key"]:
                best = {**candidate, "_selection_key": candidate_key}

    if best is None:
        best = {
            "tau": float(config.tau_grid[min(len(config.tau_grid) // 2, len(config.tau_grid) - 1)]),
            "kappa": float(config.kappa_grid[min(len(config.kappa_grid) // 2, len(config.kappa_grid) - 1)]),
            "action_threshold": 0.6,
            "precision": 0.0,
            "recall": 0.0,
            "pr_auc": 0.0,
            "brier_score": 1.0,
            "ece": 1.0,
            "positive_rate": 0.0,
        }
    best.pop("_selection_key", None)
    return best


def oof_classification_predictions(
    service,
    *,
    panel,
    labels,
    virus_typ: str | None = None,
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

        sample_weight = (
            service._event_sample_weights(model_train_df, virus_typ=virus_typ)
            if virus_typ
            else None
        )
        classifier = service._fit_classifier_from_frame(
            model_train_df,
            feature_columns,
            sample_weight=sample_weight,
        )
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


def event_threshold_from_context(
    *,
    current_known,
    baseline,
    mad,
    tau: float,
    kappa: float,
    min_absolute_incidence: float,
    np_module,
    absolute_incidence_threshold_fn,
):
    current_arr = np_module.maximum(np_module.asarray(current_known, dtype=float), 0.0)
    baseline_arr = np_module.asarray(baseline, dtype=float)
    mad_arr = np_module.maximum(np_module.asarray(mad, dtype=float), 1.0)
    relative_threshold = np_module.expm1(np_module.log1p(current_arr) + float(tau))
    absolute_threshold = np_module.asarray(
        [
            absolute_incidence_threshold_fn(
                seasonal_baseline=baseline_value,
                seasonal_mad=mad_value,
                kappa=kappa,
                min_absolute_incidence=min_absolute_incidence,
            )
            for baseline_value, mad_value in zip(baseline_arr, mad_arr, strict=False)
        ],
        dtype=float,
    )
    return np_module.maximum(relative_threshold, absolute_threshold)


def forecast_implied_event_probability(
    *,
    quantile_predictions: dict[float, Any],
    current_known,
    baseline,
    mad,
    tau: float,
    kappa: float,
    min_absolute_incidence: float,
    np_module,
    absolute_incidence_threshold_fn,
):
    ordered_quantiles = sorted(float(quantile) for quantile in quantile_predictions)
    if not ordered_quantiles:
        return np_module.asarray([], dtype=float)

    threshold = event_threshold_from_context(
        current_known=current_known,
        baseline=baseline,
        mad=mad,
        tau=tau,
        kappa=kappa,
        min_absolute_incidence=min_absolute_incidence,
        np_module=np_module,
        absolute_incidence_threshold_fn=absolute_incidence_threshold_fn,
    )
    stacked = np_module.vstack(
        [
            np_module.asarray(quantile_predictions[quantile], dtype=float)
            for quantile in ordered_quantiles
        ]
    )
    monotone = np_module.maximum.accumulate(stacked, axis=0)
    exceedance = np_module.zeros(monotone.shape[1], dtype=float)
    for idx in range(monotone.shape[1]):
        values = monotone[:, idx]
        current_threshold = float(threshold[idx])
        unique_values, unique_indices = np_module.unique(values, return_index=True)
        quantiles_for_values = np_module.asarray(
            [ordered_quantiles[int(index)] for index in unique_indices],
            dtype=float,
        )
        if len(unique_values) == 1:
            cdf_value = float(quantiles_for_values[0])
        else:
            cdf_value = float(
                np_module.interp(
                    current_threshold,
                    unique_values,
                    quantiles_for_values,
                    left=float(quantiles_for_values[0]),
                    right=float(quantiles_for_values[-1]),
                )
            )
        exceedance[idx] = 1.0 - cdf_value
    return np_module.clip(exceedance, 0.025, 0.975)
