"""Model fitting and calibration helpers for RegionalModelTrainer."""

from __future__ import annotations


def fit_classifier(
    *,
    X,
    y,
    sample_weight=None,
    classifier_cls,
    classifier_config,
):
    positives = max(int(sum(label == 1 for label in y)), 1)
    negatives = max(int(sum(label == 0 for label in y)), 1)
    config = dict(classifier_config)
    config["scale_pos_weight"] = float(negatives / positives)
    model = classifier_cls(**config)
    fit_kwargs = {}
    if sample_weight is not None:
        fit_kwargs["sample_weight"] = sample_weight
    model.fit(X, y, **fit_kwargs)
    return model


def fit_regressor(
    *,
    X,
    y,
    config,
    sample_weight=None,
    regressor_cls,
):
    model = regressor_cls(**config)
    fit_kwargs = {}
    if sample_weight is not None:
        fit_kwargs["sample_weight"] = sample_weight
    model.fit(X, y, **fit_kwargs)
    return model


def fit_classifier_from_frame(service, frame, feature_columns):
    return service._fit_classifier(
        frame[feature_columns].to_numpy(),
        frame["event_label"].to_numpy(),
        sample_weight=service._sample_weights(frame),
    )


def fit_regressor_from_frame(
    service,
    frame,
    feature_columns,
    config,
    *,
    target_col="y_next_log",
):
    return service._fit_regressor(
        frame[feature_columns].to_numpy(),
        frame[target_col].to_numpy(),
        config=config,
        sample_weight=service._sample_weights(frame),
    )


def fit_isotonic(raw_probabilities, labels, *, fit_isotonic_calibrator_fn):
    return fit_isotonic_calibrator_fn(
        raw_probabilities,
        labels,
        min_samples=20,
        min_class_support=1,
    )


def apply_calibration(calibration, raw_probabilities, *, apply_probability_calibration_fn):
    return apply_probability_calibration_fn(calibration, raw_probabilities)
