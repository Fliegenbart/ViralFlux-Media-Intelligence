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
