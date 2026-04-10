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


def test_build_rows_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = [{"bundesland": "BY"}]
    kwargs = {
        "virus_typ": "Influenza A",
        "wastewater": pd.DataFrame(),
        "wastewater_context": {},
        "truth": pd.DataFrame(),
        "grippeweb": pd.DataFrame(),
        "influenza_ifsg": pd.DataFrame(),
        "rsv_ifsg": pd.DataFrame(),
        "are": pd.DataFrame(),
        "notaufnahme": pd.DataFrame(),
        "trends": pd.DataFrame(),
        "weather": pd.DataFrame(),
        "pollen": pd.DataFrame(),
        "holidays": {},
        "state_populations": {},
        "start_date": pd.Timestamp("2026-01-01"),
        "end_date": pd.Timestamp("2026-01-31"),
        "horizon_days": 7,
        "include_targets": True,
        "include_nowcast": False,
        "use_revision_adjusted": False,
        "revision_policy": "none",
        "source_revision_policy": None,
        "weather_forecast_vintage_mode": "disabled",
        "weather_forecast_metadata": {},
    }

    with patch(
        "app.services.ml.regional_features_builders.build_rows",
        return_value=sentinel,
    ) as mocked:
        result = builder._build_rows(**kwargs)

    assert result is sentinel
    mocked.assert_called_once_with(builder, **kwargs)


def test_build_feature_row_wrapper_delegates_to_module() -> None:
    builder = RegionalFeatureBuilder(db=None)
    sentinel = {"ww_level": 1.0}
    kwargs = {
        "virus_typ": "Influenza A",
        "state": "BY",
        "as_of": pd.Timestamp("2026-03-10"),
        "visible_ww": pd.DataFrame([{"datum": pd.Timestamp("2026-03-10"), "site_count": 1, "under_bg_share": 0.0, "viral_std": 0.0, "viral_load": 1.0}]),
        "visible_truth": pd.DataFrame([{"week_start": pd.Timestamp("2026-03-03"), "incidence": 2.0}]),
        "visible_grippeweb_state": {},
        "visible_grippeweb_national": {},
        "visible_influenza_ifsg": None,
        "visible_rsv_ifsg": None,
        "visible_are": None,
        "visible_notaufnahme": None,
        "visible_trends": None,
        "weather_frame": None,
        "pollen_frame": None,
        "holiday_ranges": [],
        "latest_ww_snapshot": {},
        "latest_cross_virus_snapshots": {},
        "state_population": 1000000.0,
        "max_site_count": 1,
        "horizon_days": 7,
        "target_week_start": pd.Timestamp("2026-03-17"),
        "current_known_incidence": 2.0,
        "seasonal_baseline": 1.0,
        "seasonal_mad": 1.0,
        "include_nowcast": False,
        "use_revision_adjusted": False,
        "revision_policy": "none",
        "source_revision_policy": None,
        "weather_forecast_vintage_mode": "disabled",
        "weather_forecast_metadata": {},
        "truth_nowcast": object(),
    }

    with patch(
        "app.services.ml.regional_features_builders.build_feature_row",
        return_value=sentinel,
    ) as mocked:
        result = builder._build_feature_row(**kwargs)

    assert result is sentinel
    mocked.assert_called_once_with(builder, **kwargs)
