from unittest.mock import patch

import pandas as pd

from app.services.ml.regional_features import RegionalFeatureBuilder


def test_load_wastewater_daily_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = pd.DataFrame([{"bundesland": "BY"}])

    with patch(
        "app.services.ml.regional_features_sources.load_wastewater_daily",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_wastewater_daily("Influenza A", pd.Timestamp("2026-01-01"))

    assert result is sentinel
    mocked.assert_called_once_with(builder, "Influenza A", pd.Timestamp("2026-01-01"))


def test_load_supported_wastewater_context_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = {"Influenza A": pd.DataFrame([{"bundesland": "BY"}])}

    with patch(
        "app.services.ml.regional_features_sources.load_supported_wastewater_context",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_supported_wastewater_context(
            "Influenza A",
            pd.Timestamp("2026-01-01"),
        )

    assert result is sentinel
    mocked.assert_called_once_with(builder, "Influenza A", pd.Timestamp("2026-01-01"))


def test_load_truth_series_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = pd.DataFrame([{"bundesland": "BY"}])

    with patch(
        "app.services.ml.regional_features_sources.load_truth_series",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_truth_series("Influenza A", pd.Timestamp("2026-01-01"))

    assert result is sentinel
    mocked.assert_called_once_with(builder, "Influenza A", pd.Timestamp("2026-01-01"))


def test_load_landkreis_truth_series_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = pd.DataFrame([{"geo_unit_id": "09162"}])

    with patch(
        "app.services.ml.regional_features_sources.load_landkreis_truth_series",
        return_value=sentinel,
    ) as mocked:
        result = builder.load_landkreis_truth_series("Influenza A", pd.Timestamp("2026-01-01"))

    assert result is sentinel
    mocked.assert_called_once_with(builder, "Influenza A", pd.Timestamp("2026-01-01"))


def test_load_ifsg_signal_frame_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = pd.DataFrame([{"bundesland": "BY"}])
    start_date = pd.Timestamp("2026-01-01")
    end_date = pd.Timestamp("2026-01-31")
    model = object()

    with patch(
        "app.services.ml.regional_features_sources.load_ifsg_signal_frame",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_ifsg_signal_frame(
            model=model,
            start_date=start_date,
            end_date=end_date,
            lag_key="influenza_ifsg",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        builder,
        model=model,
        start_date=start_date,
        end_date=end_date,
        lag_key="influenza_ifsg",
    )


def test_load_weather_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = pd.DataFrame([{"bundesland": "BY"}])
    start_date = pd.Timestamp("2026-03-10")
    end_date = pd.Timestamp("2026-03-20")

    with patch(
        "app.services.ml.regional_features_sources.load_weather",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_weather(start_date, end_date)

    assert result is sentinel
    mocked.assert_called_once_with(builder, start_date, end_date)


def test_load_pollen_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = pd.DataFrame([{"bundesland": "BY"}])
    start_date = pd.Timestamp("2026-03-10")
    end_date = pd.Timestamp("2026-03-20")

    with patch(
        "app.services.ml.regional_features_sources.load_pollen",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_pollen(start_date, end_date)

    assert result is sentinel
    mocked.assert_called_once_with(builder, start_date, end_date)


def test_load_holidays_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = {"BY": [(pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-31"))]}

    with patch(
        "app.services.ml.regional_features_sources.load_holidays",
        return_value=sentinel,
    ) as mocked:
        result = builder._load_holidays()

    assert result is sentinel
    mocked.assert_called_once_with(builder)


def test_dataset_manifest_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    panel = pd.DataFrame([{"bundesland": "BY", "as_of_date": pd.Timestamp("2026-03-01")}])
    sentinel = {"rows": 1}

    with patch(
        "app.services.ml.regional_features_manifests.dataset_manifest",
        return_value=sentinel,
    ) as mocked:
        result = builder.dataset_manifest("Influenza A", panel)

    assert result is sentinel
    mocked.assert_called_once_with(builder, "Influenza A", panel)


def test_point_in_time_snapshot_manifest_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    panel = pd.DataFrame([{"bundesland": "BY", "as_of_date": pd.Timestamp("2026-03-01")}])
    sentinel = {"snapshot_type": "regional_panel_as_of_training"}

    with patch(
        "app.services.ml.regional_features_manifests.point_in_time_snapshot_manifest",
        return_value=sentinel,
    ) as mocked:
        result = builder.point_in_time_snapshot_manifest("Influenza A", panel)

    assert result is sentinel
    mocked.assert_called_once_with(builder, "Influenza A", panel)


def test_live_source_readiness_frames_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    as_of_date = pd.Timestamp("2026-03-10")
    sentinel = {"wastewater": pd.DataFrame([{"bundesland": "BY"}])}

    with patch(
        "app.services.ml.regional_features_manifests.live_source_readiness_frames",
        return_value=sentinel,
    ) as mocked:
        result = builder.live_source_readiness_frames(
            virus_typ="Influenza A",
            as_of_date=as_of_date,
            lookback_days=35,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        builder,
        virus_typ="Influenza A",
        as_of_date=as_of_date,
        lookback_days=35,
    )
