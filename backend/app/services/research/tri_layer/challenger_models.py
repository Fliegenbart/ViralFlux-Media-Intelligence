"""Optional heavy challenger models for Tri-Layer research backtests.

These models are research-only. They are intentionally kept behind an explicit
backtest flag so live snapshots and polling endpoints stay cheap and read-only.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

from app.services.research.tri_layer.gpu_runtime import resolve_tri_layer_xgboost_config


DEFAULT_CLASSIFIER_CONFIG: dict[str, Any] = {
    "n_estimators": 120,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": 1,
}

DEFAULT_PHASE_CLASSIFIER_CONFIG: dict[str, Any] = {
    **DEFAULT_CLASSIFIER_CONFIG,
    "objective": "multi:softprob",
    "eval_metric": "mlogloss",
}

DEFAULT_RANKER_CONFIG: dict[str, Any] = {
    "n_estimators": 120,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "rank:pairwise",
    "random_state": 42,
    "verbosity": 0,
    "n_jobs": 1,
}

SOURCE_ABLATION_FEATURES: dict[str, list[str]] = {
    "clinical_only": ["clinical_only_probability"],
    "wastewater_only": ["wastewater_only_probability"],
    "wastewater_plus_clinical": [
        "wastewater_only_probability",
        "clinical_only_probability",
        "wastewater_plus_clinical_probability",
    ],
    "forecast_proxy_only": ["forecast_proxy_only_probability"],
    "tri_layer_epi_no_sales": [
        "early_warning_probability",
        "wastewater_only_probability",
        "clinical_only_probability",
        "wastewater_plus_clinical_probability",
        "forecast_proxy_only_probability",
        "tri_layer_epi_no_sales_probability",
    ],
}
ALL_FEATURE_COLUMNS = SOURCE_ABLATION_FEATURES["tri_layer_epi_no_sales"]
PHASE_ORDER = ["baseline", "early_growth", "acceleration", "peak", "decline", "unknown"]


def resolve_tri_layer_challenger_xgboost_params(
    config: dict[str, Any] | None,
    *,
    device: str | None = None,
) -> dict[str, Any]:
    """Resolve XGBoost params using the shared regional CPU/GPU switch."""
    return resolve_tri_layer_xgboost_config(config, device=device)


def _default_classifier_cls():
    from xgboost import XGBClassifier

    return XGBClassifier


def _default_ranker_cls():
    from xgboost import XGBRanker

    return XGBRanker


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(number):
        return None
    return number


def _prediction_probability(row: Mapping[str, Any], model_name: str) -> float | None:
    predictions = row.get("model_predictions") if isinstance(row.get("model_predictions"), Mapping) else {}
    model_prediction = predictions.get(model_name) if isinstance(predictions, Mapping) else {}
    if not isinstance(model_prediction, Mapping):
        return None
    return _safe_float(model_prediction.get("onset_probability"))


def _training_frame(cutoff_results: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in cutoff_results or []:
        onset = row.get("observed_onset")
        if onset is None:
            continue
        phase = str(row.get("observed_phase") or "unknown")
        if phase not in PHASE_ORDER:
            phase = "unknown"
        early_warning = _safe_float(row.get("early_warning_score"))
        rows.append(
            {
                "cutoff_date": str(row.get("cutoff_date") or ""),
                "region_code": str(row.get("region_code") or ""),
                "observed_onset": 1 if bool(onset) else 0,
                "observed_phase": phase,
                "phase_label": PHASE_ORDER.index(phase),
                "early_warning_probability": (early_warning / 100.0) if early_warning is not None else None,
                "clinical_only_probability": _prediction_probability(row, "clinical_only"),
                "wastewater_only_probability": _prediction_probability(row, "wastewater_only"),
                "wastewater_plus_clinical_probability": _prediction_probability(row, "wastewater_plus_clinical"),
                "forecast_proxy_only_probability": _prediction_probability(row, "forecast_proxy_only"),
                "tri_layer_epi_no_sales_probability": _prediction_probability(row, "tri_layer_epi_no_sales"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for column in ALL_FEATURE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["cutoff_date", "region_code"]).reset_index(drop=True)


def _fit_classifier(
    *,
    frame: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    classifier_cls,
    config: dict[str, Any],
    device: str | None,
    min_samples: int,
) -> dict[str, Any]:
    usable = frame.dropna(subset=[*feature_columns, label_column]).copy()
    labels = usable[label_column].astype(int)
    if len(usable) < int(min_samples):
        return {"status": "insufficient_data", "n_samples": int(len(usable)), "features": feature_columns}
    if labels.nunique() < 2:
        return {"status": "insufficient_labels", "n_samples": int(len(usable)), "features": feature_columns}

    resolved = resolve_tri_layer_challenger_xgboost_params(config, device=device)
    model = classifier_cls(**resolved)
    model.fit(usable[feature_columns].to_numpy(), labels.to_numpy())
    return {
        "status": "trained",
        "n_samples": int(len(usable)),
        "features": feature_columns,
        "xgboost_params": resolved,
    }


def _fit_ranker(
    *,
    frame: pd.DataFrame,
    feature_columns: list[str],
    ranker_cls,
    config: dict[str, Any],
    device: str | None,
    min_samples: int,
) -> dict[str, Any]:
    usable = frame.dropna(subset=[*feature_columns, "observed_onset", "cutoff_date"]).copy()
    if len(usable) < int(min_samples):
        return {"status": "insufficient_data", "n_samples": int(len(usable)), "features": feature_columns}
    if usable["observed_onset"].astype(int).nunique() < 2:
        return {"status": "insufficient_labels", "n_samples": int(len(usable)), "features": feature_columns}
    groups = usable.groupby("cutoff_date", sort=False).size().astype(int).tolist()
    if not groups or max(groups) < 2:
        return {"status": "insufficient_groups", "n_samples": int(len(usable)), "features": feature_columns}

    resolved = resolve_tri_layer_challenger_xgboost_params(config, device=device)
    model = ranker_cls(**resolved)
    model.fit(
        usable[feature_columns].to_numpy(),
        usable["observed_onset"].astype(int).to_numpy(),
        group=groups,
    )
    return {
        "status": "trained",
        "n_samples": int(len(usable)),
        "groups": groups,
        "features": feature_columns,
        "xgboost_params": resolved,
    }


def _runtime_device_from_params(params: dict[str, Any]) -> str:
    return str(params.get("device") or "cpu")


def fit_tri_layer_challenger_models(
    cutoff_results: Iterable[Mapping[str, Any]],
    *,
    classifier_cls=None,
    ranker_cls=None,
    device: str | None = None,
    min_samples: int = 24,
) -> dict[str, Any]:
    """Fit optional XGBoost challenger models for scientific ablations.

    The returned payload is JSON-safe metadata only. Model objects are not
    persisted by this v1 hook because the report is meant for research review,
    not production serving.
    """
    frame = _training_frame(cutoff_results)
    runtime_params = resolve_tri_layer_challenger_xgboost_params({}, device=device)
    runtime_device = _runtime_device_from_params(runtime_params)
    if frame.empty:
        return {
            "status": "insufficient_data",
            "runtime": {"engine": "xgboost", "device": runtime_device},
            "models": {},
        }

    classifier = classifier_cls or _default_classifier_cls()
    ranker = ranker_cls or _default_ranker_cls()
    onset_config = dict(DEFAULT_CLASSIFIER_CONFIG)
    phase_config = dict(DEFAULT_PHASE_CLASSIFIER_CONFIG)
    phase_config["num_class"] = len(PHASE_ORDER)
    ranker_config = dict(DEFAULT_RANKER_CONFIG)

    models: dict[str, Any] = {
        "onset_classifier": _fit_classifier(
            frame=frame,
            feature_columns=ALL_FEATURE_COLUMNS,
            label_column="observed_onset",
            classifier_cls=classifier,
            config=onset_config,
            device=device,
            min_samples=min_samples,
        ),
        "phase_classifier": _fit_classifier(
            frame=frame,
            feature_columns=ALL_FEATURE_COLUMNS,
            label_column="phase_label",
            classifier_cls=classifier,
            config=phase_config,
            device=device,
            min_samples=min_samples,
        ),
        "regional_ranker": _fit_ranker(
            frame=frame,
            feature_columns=ALL_FEATURE_COLUMNS,
            ranker_cls=ranker,
            config=ranker_config,
            device=device,
            min_samples=min_samples,
        ),
    }
    models["source_ablation_classifiers"] = {
        name: _fit_classifier(
            frame=frame,
            feature_columns=features,
            label_column="observed_onset",
            classifier_cls=classifier,
            config=onset_config,
            device=device,
            min_samples=min_samples,
        )
        for name, features in SOURCE_ABLATION_FEATURES.items()
    }

    trained_count = sum(
        int(model.get("status") == "trained")
        for model in [models["onset_classifier"], models["phase_classifier"], models["regional_ranker"]]
    ) + sum(
        int(model.get("status") == "trained")
        for model in models["source_ablation_classifiers"].values()
    )
    return {
        "status": "trained" if trained_count > 0 else "insufficient_data",
        "runtime": {
            "engine": "xgboost",
            "device": runtime_device,
            "device_env": "REGIONAL_XGBOOST_DEVICE",
            "gpu_opt_in": runtime_device != "cpu",
        },
        "n_rows": int(len(frame)),
        "models": models,
    }
