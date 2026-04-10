from pathlib import Path
from unittest.mock import ANY, patch

import pandas as pd

from app.services.ml import wave_prediction_service as wave_module
from app.services.ml.wave_prediction_service import WavePredictionService


def test_load_source_frames_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    sentinel = {"truth": pd.DataFrame()}

    with patch(
        "app.services.ml.wave_prediction_sources.load_source_frames",
        return_value=sentinel,
    ) as mocked:
        result = service._load_source_frames(
            pathogen="Influenza A",
            start_date=pd.Timestamp("2026-01-01"),
            end_date=pd.Timestamp("2026-01-31"),
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        pathogen="Influenza A",
        start_date=pd.Timestamp("2026-01-01"),
        end_date=pd.Timestamp("2026-01-31"),
    )


def test_build_rows_for_pathogen_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    sentinel = [{"region": "BY"}]

    with patch(
        "app.services.ml.wave_prediction_sources.build_rows_for_pathogen",
        return_value=sentinel,
    ) as mocked:
        result = service._build_rows_for_pathogen(
            pathogen="Influenza A",
            source_frames={"truth": pd.DataFrame()},
            start_date=pd.Timestamp("2026-01-01"),
            end_date=pd.Timestamp("2026-01-31"),
            horizon_days=14,
            region_code="BY",
        )

    assert result is sentinel
    mocked.assert_called_once()
    args, kwargs = mocked.call_args
    assert args == (service,)
    assert kwargs["pathogen"] == "Influenza A"
    assert kwargs["start_date"] == pd.Timestamp("2026-01-01")
    assert kwargs["end_date"] == pd.Timestamp("2026-01-31")
    assert kwargs["horizon_days"] == 14
    assert kwargs["region_code"] == "BY"
    assert list(kwargs["source_frames"].keys()) == ["truth"]
    assert kwargs["source_frames"]["truth"].empty
    assert kwargs["wave_label_config_for_pathogen_fn"] is wave_module.wave_label_config_for_pathogen
    assert kwargs["build_daily_signal_features_fn"] is wave_module.build_daily_signal_features
    assert kwargs["weather_context_features_fn"] is wave_module.weather_context_features
    assert kwargs["school_holiday_features_fn"] is wave_module.school_holiday_features
    assert kwargs["bundesland_names"] is wave_module.BUNDESLAND_NAMES
    assert kwargs["pathogen_slug_fn"] is wave_module._pathogen_slug
    assert kwargs["pd_module"] is wave_module.pd
    assert kwargs["np_module"] is wave_module.np


def test_visible_as_of_wrapper_delegates_to_module() -> None:
    frame = pd.DataFrame({"datum": pd.to_datetime(["2026-01-01"])})
    sentinel = pd.DataFrame({"datum": pd.to_datetime(["2026-01-01"])})

    with patch(
        "app.services.ml.wave_prediction_sources.visible_as_of",
        return_value=sentinel,
    ) as mocked:
        result = WavePredictionService._visible_as_of(frame, pd.Timestamp("2026-01-02"))

    assert result is sentinel
    mocked.assert_called_once_with(frame, pd.Timestamp("2026-01-02"), pd_module=wave_module.pd)


def test_group_by_state_wrapper_delegates_to_module() -> None:
    frame = pd.DataFrame({"bundesland": ["BY"], "datum": pd.to_datetime(["2026-01-01"])})
    sentinel = {"BY": frame}

    with patch(
        "app.services.ml.wave_prediction_sources.group_by_state",
        return_value=sentinel,
    ) as mocked:
        result = WavePredictionService._group_by_state(frame)

    assert result is sentinel
    mocked.assert_called_once_with(frame)


def test_coerce_frame_wrapper_delegates_to_module() -> None:
    frame = pd.DataFrame({"value": [1.0]})
    sentinel = pd.DataFrame({"value": [1.0]})

    with patch(
        "app.services.ml.wave_prediction_sources.coerce_frame",
        return_value=sentinel,
    ) as mocked:
        result = WavePredictionService._coerce_frame(frame)

    assert result is sentinel
    mocked.assert_called_once_with(frame)


def test_latest_column_value_wrapper_delegates_to_module() -> None:
    frame = pd.DataFrame({"incidence": [1.0, 2.0]})

    with patch(
        "app.services.ml.wave_prediction_sources.latest_column_value",
        return_value=2.0,
    ) as mocked:
        result = WavePredictionService._latest_column_value(frame, "incidence")

    assert result == 2.0
    mocked.assert_called_once_with(frame, "incidence")


def test_growth_ratio_wrapper_delegates_to_module() -> None:
    frame = pd.DataFrame({"incidence": [1.0, 2.0]})

    with patch(
        "app.services.ml.wave_prediction_sources.growth_ratio",
        return_value=1.0,
    ) as mocked:
        result = WavePredictionService._growth_ratio(frame)

    assert result == 1.0
    mocked.assert_called_once_with(frame)


def test_run_wave_prediction_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    sentinel = {"pathogen": "Influenza A", "region": "BY"}

    with patch(
        "app.services.ml.wave_prediction_artifacts.run_wave_prediction",
        return_value=sentinel,
    ) as mocked:
        result = service.run_wave_prediction(
            pathogen="Influenza A",
            region="BY",
            horizon_days=14,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        pathogen="Influenza A",
        region="BY",
        horizon_days=14,
        normalize_virus_type_fn=wave_module.normalize_virus_type,
        normalize_state_code_fn=wave_module.normalize_state_code,
        get_regression_feature_columns_fn=wave_module.get_regression_feature_columns,
        get_classification_feature_columns_fn=wave_module.get_classification_feature_columns,
        utc_now_fn=wave_module.utc_now,
        np_module=wave_module.np,
    )


def test_run_wave_backtest_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    panel = pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-01-01"]),
            "target_regression": [1.0],
            "target_wave14": [0],
        }
    )
    sentinel = {"status": "ok"}

    with patch(
        "app.services.ml.wave_prediction_backtest.run_wave_backtest",
        return_value=sentinel,
    ) as mocked:
        result = service.run_wave_backtest(
            pathogen="Influenza A",
            region="BY",
            horizon_days=14,
            panel=panel,
            include_oof_predictions=True,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        pathogen="Influenza A",
        region="BY",
        lookback_days=None,
        horizon_days=14,
        panel=panel,
        include_oof_predictions=True,
        normalize_virus_type_fn=wave_module.normalize_virus_type,
        get_regression_feature_columns_fn=wave_module.get_regression_feature_columns,
        get_classification_feature_columns_fn=wave_module.get_classification_feature_columns,
        build_backtest_splits_fn=wave_module.build_backtest_splits,
        mean_absolute_error_fn=wave_module.mean_absolute_error,
        false_alarm_rate_fn=wave_module.false_alarm_rate,
        mean_lead_time_days_fn=wave_module.mean_lead_time_days,
        safe_mape_fn=wave_module.safe_mape,
        safe_pr_auc_fn=wave_module.safe_pr_auc,
        safe_roc_auc_fn=wave_module.safe_roc_auc,
        precision_score_fn=wave_module.precision_score,
        recall_score_fn=wave_module.recall_score,
        f1_score_fn=wave_module.f1_score,
        brier_score_loss_fn=wave_module.brier_score_loss,
        json_safe_fn=wave_module.json_safe,
        np_module=wave_module.np,
        pd_module=wave_module.pd,
    )


def test_persist_artifacts_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)

    with patch(
        "app.services.ml.wave_prediction_artifacts.persist_artifacts",
    ) as mocked:
        service._persist_artifacts(
            pathogen="Influenza A",
            regressor_bundle={"regressor": object()},
            classifier_bundle={"classifier": object(), "calibration": None},
            metadata={"model_version": "test"},
            backtest={"status": "ok"},
            dataset_manifest={"rows": 1},
        )

    mocked.assert_called_once_with(
        service,
        pathogen="Influenza A",
        regressor_bundle=ANY,
        classifier_bundle=ANY,
        metadata={"model_version": "test"},
        backtest={"status": "ok"},
        dataset_manifest={"rows": 1},
        pathogen_slug_fn=wave_module._pathogen_slug,
        atomic_pickle_dump_fn=wave_module.atomic_pickle_dump,
        atomic_json_dump_fn=wave_module.atomic_json_dump,
    )


def test_load_artifacts_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    sentinel = {"metadata": {"model_version": "test"}}

    with patch(
        "app.services.ml.wave_prediction_artifacts.load_artifacts",
        return_value=sentinel,
    ) as mocked:
        result = service._load_artifacts("Influenza A")

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        "Influenza A",
        pathogen_slug_fn=wave_module._pathogen_slug,
        regressor_cls=wave_module.XGBRegressor,
        classifier_cls=wave_module.XGBClassifier,
        pickle_module=wave_module.pickle,
    )


def test_atomic_save_model_wrapper_delegates_to_module() -> None:
    model = object()
    target = Path("/tmp/model.json")

    with patch(
        "app.services.ml.wave_prediction_artifacts.atomic_save_model",
    ) as mocked:
        WavePredictionService._atomic_save_model(model, target)

    mocked.assert_called_once_with(model, target)


def test_load_json_wrapper_delegates_to_module() -> None:
    sentinel = {"status": "ok"}
    path = Path("/tmp/metadata.json")

    with patch(
        "app.services.ml.wave_prediction_artifacts.load_json",
        return_value=sentinel,
    ) as mocked:
        result = WavePredictionService._load_json(path)

    assert result is sentinel
    mocked.assert_called_once_with(path)


def test_select_classification_threshold_wrapper_delegates_to_module() -> None:
    labels = wave_module.np.array([1, 0])
    scores = wave_module.np.array([0.8, 0.2])

    with patch(
        "app.services.ml.wave_prediction_metrics.select_classification_threshold",
        return_value=0.4,
    ) as mocked:
        result = WavePredictionService._select_classification_threshold(
            labels,
            scores,
            default_threshold=0.5,
        )

    assert result == 0.4
    mocked.assert_called_once_with(
        labels,
        scores,
        default_threshold=0.5,
        precision_score_fn=wave_module.precision_score,
        recall_score_fn=wave_module.recall_score,
        f1_score_fn=wave_module.f1_score,
        false_alarm_rate_fn=wave_module.false_alarm_rate,
        np_module=wave_module.np,
    )


def test_resolve_decision_strategy_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    labels = wave_module.np.array([1, 0])
    scores = wave_module.np.array([0.8, 0.2])
    sentinel = {"use_calibration": False, "threshold": 0.5, "notes": []}

    with patch(
        "app.services.ml.wave_prediction_metrics.resolve_decision_strategy",
        return_value=sentinel,
    ) as mocked:
        result = service._resolve_decision_strategy(
            y_true=labels,
            raw_scores=scores,
            calibration=None,
            default_threshold=0.5,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        y_true=labels,
        raw_scores=scores,
        calibration=None,
        default_threshold=0.5,
        f1_score_fn=wave_module.f1_score,
        brier_score_loss_fn=wave_module.brier_score_loss,
        np_module=wave_module.np,
    )


def test_aggregate_fold_metrics_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    folds = [{"mae": 1.0, "rows": 2, "positive_rows": 1, "tp": 1, "fp": 0, "tn": 1, "fn": 0}]
    sentinel = {"fold_count": 1}

    with patch(
        "app.services.ml.wave_prediction_metrics.aggregate_fold_metrics",
        return_value=sentinel,
    ) as mocked:
        result = service._aggregate_fold_metrics(folds)

    assert result is sentinel
    mocked.assert_called_once_with(folds, np_module=wave_module.np)


def test_dataset_manifest_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    panel = pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-01-01"]),
            "pathogen": ["Influenza A"],
            "region": ["BY"],
            "truth_available": [1.0],
        }
    )
    sentinel = {"rows": 1}

    with patch(
        "app.services.ml.wave_prediction_metrics.dataset_manifest",
        return_value=sentinel,
    ) as mocked:
        result = service._dataset_manifest(panel)

    assert result is sentinel
    mocked.assert_called_once_with(panel)


def test_train_regression_model_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    panel = pd.DataFrame({"target_regression": [1.0], "feature_a": [2.0]})
    sentinel = {"regressor": object(), "feature_columns": ["feature_a"], "metrics": {}}

    with patch(
        "app.services.ml.wave_prediction_training.train_regression_model",
        return_value=sentinel,
    ) as mocked:
        result = service.train_regression_model(
            panel,
            feature_columns=["feature_a"],
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        panel,
        feature_columns=["feature_a"],
        get_regression_feature_columns_fn=wave_module.get_regression_feature_columns,
        regressor_config=wave_module.REGRESSOR_CONFIG,
        xgb_regressor_cls=wave_module.XGBRegressor,
        mean_absolute_error_fn=wave_module.mean_absolute_error,
        safe_mape_fn=wave_module.safe_mape,
        np_module=wave_module.np,
    )


def test_train_wave_classifier_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    panel = pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-01-01"]),
            "target_wave14": [1],
            "feature_a": [2.0],
        }
    )
    sentinel = {"classifier": object(), "calibration": None, "feature_columns": ["feature_a"], "threshold": 0.5}

    with patch(
        "app.services.ml.wave_prediction_training.train_wave_classifier",
        return_value=sentinel,
    ) as mocked:
        result = service.train_wave_classifier(
            panel,
            feature_columns=["feature_a"],
            sample_weights=None,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        panel,
        feature_columns=["feature_a"],
        sample_weights=None,
        get_classification_feature_columns_fn=wave_module.get_classification_feature_columns,
        constant_classifier_cls=wave_module._ConstantBinaryClassifier,
        classifier_config=wave_module.CLASSIFIER_CONFIG,
        xgb_classifier_cls=wave_module.XGBClassifier,
        np_module=wave_module.np,
        pd_module=wave_module.pd,
    )


def test_train_models_wrapper_delegates_to_module() -> None:
    service = WavePredictionService(db=None)
    sentinel = {"status": "ok", "pathogen": "Influenza A"}

    with patch(
        "app.services.ml.wave_prediction_training.train_models",
        return_value=sentinel,
    ) as mocked:
        result = service.train_models(
            pathogen="Influenza A",
            region="BY",
            lookback_days=180,
            horizon_days=14,
            persist=False,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        pathogen="Influenza A",
        region="BY",
        lookback_days=180,
        horizon_days=14,
        persist=False,
        normalize_virus_type_fn=wave_module.normalize_virus_type,
        get_regression_feature_columns_fn=wave_module.get_regression_feature_columns,
        get_classification_feature_columns_fn=wave_module.get_classification_feature_columns,
        wave_label_config_for_pathogen_fn=wave_module.wave_label_config_for_pathogen,
        top_feature_importance_fn=wave_module.top_feature_importance,
        utc_now_fn=wave_module.utc_now,
    )
