from pathlib import Path
from unittest.mock import ANY, patch

from app.services.ml import regional_forecast as regional_forecast_module
from app.services.ml.regional_forecast import RegionalForecastService


def test_decision_stage_sort_value_wrapper_delegates_to_module() -> None:
    with patch(
        "app.services.ml.regional_forecast_media.decision_stage_sort_value",
        return_value=7,
    ) as mocked:
        result = RegionalForecastService._decision_stage_sort_value("activate")

    assert result == 7
    mocked.assert_called_once_with("activate")


def test_decision_priority_sort_key_wrapper_delegates_to_module() -> None:
    item = {"decision": {"stage": "activate"}}

    with patch(
        "app.services.ml.regional_forecast_media.decision_priority_sort_key",
        return_value=(3.0, 2.0, 1.0, 0.0),
    ) as mocked:
        result = RegionalForecastService._decision_priority_sort_key(item)

    assert result == (3.0, 2.0, 1.0, 0.0)
    mocked.assert_called_once_with(item)


def test_decision_summary_wrapper_delegates_to_module() -> None:
    predictions = [{"bundesland": "BY"}]
    sentinel = {"activate_regions": 1}

    with patch(
        "app.services.ml.regional_forecast_media.decision_summary",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._decision_summary(predictions)

    assert result is sentinel
    mocked.assert_called_once_with(predictions)


def test_media_spend_gate_wrapper_delegates_to_module() -> None:
    sentinel = (True, ["ok"])

    with patch(
        "app.services.ml.regional_forecast_media.media_spend_gate",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._media_spend_gate(
            quality_gate={"overall_passed": True},
            business_gate={"validated_for_budget_activation": True},
            activation_policy="quality_gate",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        quality_gate={"overall_passed": True},
        business_gate={"validated_for_budget_activation": True},
        activation_policy="quality_gate",
    )


def test_media_action_wrapper_delegates_to_module() -> None:
    with patch(
        "app.services.ml.regional_forecast_media.media_action",
        return_value="prepare",
    ) as mocked:
        result = RegionalForecastService._media_action(
            recommended_level="Prepare",
            spend_enabled=True,
        )

    assert result == "prepare"
    mocked.assert_called_once_with(
        recommended_level="Prepare",
        spend_enabled=True,
    )


def test_media_intensity_wrapper_delegates_to_module() -> None:
    with patch(
        "app.services.ml.regional_forecast_media.media_intensity",
        return_value="medium",
    ) as mocked:
        result = RegionalForecastService._media_intensity("prepare")

    assert result == "medium"
    mocked.assert_called_once_with("prepare")


def test_products_from_allocation_wrapper_delegates_to_module() -> None:
    allocation_item = {"product_clusters": []}

    with patch(
        "app.services.ml.regional_forecast_media.products_from_allocation",
        return_value=["GeloMyrtol forte"],
    ) as mocked:
        result = RegionalForecastService._products_from_allocation(
            allocation_item=allocation_item,
            virus_typ="Influenza A",
        )

    assert result == ["GeloMyrtol forte"]
    mocked.assert_called_once_with(
        allocation_item=allocation_item,
        virus_typ="Influenza A",
        portfolio_products=regional_forecast_module.DEFAULT_PORTFOLIO_PRODUCTS,
    )


def test_media_timeline_wrapper_delegates_to_module() -> None:
    with patch(
        "app.services.ml.regional_forecast_media.media_timeline",
        return_value="Sofort aktivieren",
    ) as mocked:
        result = RegionalForecastService._media_timeline(
            action="activate",
            spend_enabled=True,
            activation_policy="quality_gate",
            business_gate={"validated_for_budget_activation": True},
            quality_gate={"overall_passed": True},
        )

    assert result == "Sofort aktivieren"
    mocked.assert_called_once_with(
        action="activate",
        spend_enabled=True,
        activation_policy="quality_gate",
        business_gate={"validated_for_budget_activation": True},
        quality_gate={"overall_passed": True},
        target_window_days=regional_forecast_module.TARGET_WINDOW_DAYS,
    )


def test_media_headline_wrapper_delegates_to_module() -> None:
    recommendations = [{"bundesland": "BY", "action": "activate", "suggested_budget_share": 0.6}]

    with patch(
        "app.services.ml.regional_forecast_media.media_headline",
        return_value="Influenza A: Budget auf Bayern fokussieren",
    ) as mocked:
        result = RegionalForecastService._media_headline(
            virus_typ="Influenza A",
            recommendations=recommendations,
            spend_enabled=True,
        )

    assert result == "Influenza A: Budget auf Bayern fokussieren"
    mocked.assert_called_once_with(
        virus_typ="Influenza A",
        recommendations=recommendations,
        spend_enabled=True,
    )


def test_metric_delta_wrapper_delegates_to_module() -> None:
    candidate = {"pr_auc": 0.8}
    reference = {"pr_auc": 0.6}
    sentinel = {"pr_auc": 0.2}

    with patch(
        "app.services.ml.regional_forecast_media.metric_delta",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._metric_delta(candidate, reference)

    assert result is sentinel
    mocked.assert_called_once_with(candidate, reference)


def test_benchmark_score_wrapper_delegates_to_module() -> None:
    item = {"aggregate_metrics": {"pr_auc": 0.7}}

    with patch(
        "app.services.ml.regional_forecast_media.benchmark_score",
        return_value=42.0,
    ) as mocked:
        result = RegionalForecastService._benchmark_score(item)

    assert result == 42.0
    mocked.assert_called_once_with(item)


def test_portfolio_priority_score_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    prediction = {"event_probability_calibrated": 0.7}
    benchmark_item = {"benchmark_score": 55.0}

    with patch(
        "app.services.ml.regional_forecast_media.portfolio_priority_score",
        return_value=66.5,
    ) as mocked:
        result = service._portfolio_priority_score(
            prediction=prediction,
            benchmark_item=benchmark_item,
        )

    assert result == 66.5
    mocked.assert_called_once_with(
        prediction=prediction,
        benchmark_item=benchmark_item,
    )


def test_portfolio_action_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    prediction = {"event_probability_calibrated": 0.7}
    benchmark_item = {"benchmark_score": 55.0}

    with patch(
        "app.services.ml.regional_forecast_media.portfolio_action",
        return_value=("activate", "high"),
    ) as mocked:
        result = service._portfolio_action(
            prediction=prediction,
            benchmark_item=benchmark_item,
        )

    assert result == ("activate", "high")
    mocked.assert_called_once_with(
        prediction=prediction,
        benchmark_item=benchmark_item,
    )


def test_region_rollup_wrapper_delegates_to_module() -> None:
    opportunities = [{"bundesland": "BY"}]
    sentinel = [{"bundesland": "BY", "leading_virus": "Influenza A"}]

    with patch(
        "app.services.ml.regional_forecast_media.region_rollup",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._region_rollup(opportunities)

    assert result is sentinel
    mocked.assert_called_once_with(opportunities)


def test_load_artifacts_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"metadata": {"horizon_days": 7}}

    with patch(
        "app.services.ml.regional_forecast_artifacts.load_artifacts",
        return_value=sentinel,
    ) as mocked:
        result = service._load_artifacts("Influenza A", horizon_days=7)

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        horizon_days=7,
        ensure_supported_horizon_fn=ANY,
        regional_model_artifact_dir_fn=ANY,
        supported_forecast_horizons=regional_forecast_module.SUPPORTED_FORECAST_HORIZONS,
        target_window_days=regional_forecast_module.TARGET_WINDOW_DAYS,
        virus_slug_fn=ANY,
        training_only_panel_columns=regional_forecast_module.TRAINING_ONLY_PANEL_COLUMNS,
    )


def test_required_artifact_paths_wrapper_delegates_to_module() -> None:
    model_dir = Path("/tmp/influenza_a")
    sentinel = {"classifier": model_dir / "classifier.json"}

    with patch(
        "app.services.ml.regional_forecast_artifacts.required_artifact_paths",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._required_artifact_paths(model_dir)

    assert result is sentinel
    mocked.assert_called_once_with(model_dir)


def test_missing_artifact_files_wrapper_delegates_to_module() -> None:
    model_dir = Path("/tmp/influenza_a")
    sentinel = ["classifier.json"]

    with patch(
        "app.services.ml.regional_forecast_artifacts.missing_artifact_files",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._missing_artifact_files(model_dir)

    assert result is sentinel
    mocked.assert_called_once_with(
        model_dir,
        required_artifact_paths_fn=ANY,
    )


def test_invalid_inference_feature_columns_wrapper_delegates_to_module() -> None:
    sentinel = ["target_incidence"]

    with patch(
        "app.services.ml.regional_forecast_artifacts.invalid_inference_feature_columns",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._invalid_inference_feature_columns(["f1", "target_incidence"])

    assert result is sentinel
    mocked.assert_called_once_with(
        ["f1", "target_incidence"],
        training_only_panel_columns=regional_forecast_module.TRAINING_ONLY_PANEL_COLUMNS,
    )


def test_artifact_payload_from_dir_wrapper_delegates_to_module() -> None:
    model_dir = Path("/tmp/influenza_a")
    sentinel = {"metadata": {"trained_at": "2026-01-01T00:00:00"}}

    with patch(
        "app.services.ml.regional_forecast_artifacts.artifact_payload_from_dir",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._artifact_payload_from_dir(model_dir)

    assert result is sentinel
    mocked.assert_called_once_with(
        model_dir,
        required_artifact_paths_fn=ANY,
        xgb_classifier_cls=regional_forecast_module.XGBClassifier,
        xgb_regressor_cls=regional_forecast_module.XGBRegressor,
        json_module=regional_forecast_module.json,
        pickle_module=regional_forecast_module.pickle,
    )


def test_apply_calibration_wrapper_delegates_to_module() -> None:
    with patch(
        "app.services.ml.regional_forecast_artifacts.apply_calibration",
        return_value="calibrated",
    ) as mocked:
        result = RegionalForecastService._apply_calibration("calibration", "raw")

    assert result == "calibrated"
    mocked.assert_called_once_with("calibration", "raw", np_module=regional_forecast_module.np)


def test_truth_readiness_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"truth_ready": False}

    with patch(
        "app.services.ml.regional_forecast_truth.truth_readiness",
        return_value=sentinel,
    ) as mocked:
        result = service._truth_readiness(brand="gelo")

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        brand="gelo",
        forecast_decision_service_cls=regional_forecast_module.ForecastDecisionService,
    )


def test_business_gate_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"validated_for_budget_activation": False}

    with patch(
        "app.services.ml.regional_forecast_truth.business_gate",
        return_value=sentinel,
    ) as mocked:
        result = service._business_gate(
            quality_gate={"overall_passed": True},
            truth_readiness={"truth_ready": False},
            brand="gelo",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        quality_gate={"overall_passed": True},
        truth_readiness={"truth_ready": False},
        brand="gelo",
        business_validation_service_cls=regional_forecast_module.BusinessValidationService,
    )


def test_truth_layer_assessment_for_products_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"truth_layer_enabled": False}

    with patch(
        "app.services.ml.regional_forecast_truth.truth_layer_assessment_for_products",
        return_value=sentinel,
    ) as mocked:
        result = service._truth_layer_assessment_for_products(
            region_code="BY",
            products=["GeloMyrtol forte"],
            target_week_start="2026-04-06",
            signal_context={"signal_present": True},
            operational_action="activate",
            operational_gate_open=True,
            brand="gelo",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        region_code="BY",
        products=["GeloMyrtol forte"],
        target_week_start="2026-04-06",
        signal_context={"signal_present": True},
        operational_action="activate",
        operational_gate_open=True,
        brand="gelo",
    )


def test_truth_layer_assessment_for_product_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"evidence_status": "no_truth"}

    with patch(
        "app.services.ml.regional_forecast_truth.truth_layer_assessment_for_product",
        return_value=sentinel,
    ) as mocked:
        result = service._truth_layer_assessment_for_product(
            brand="gelo",
            region_code="BY",
            product="GeloMyrtol forte",
            window_start="2026-01-01",
            window_end="2026-03-31",
            signal_context={"signal_present": True},
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        brand="gelo",
        region_code="BY",
        product="GeloMyrtol forte",
        window_start="2026-01-01",
        window_end="2026-03-31",
        signal_context={"signal_present": True},
        truth_layer_service_cls=regional_forecast_module.TruthLayerService,
        logger=regional_forecast_module.logger,
    )


def test_truth_assessment_window_wrapper_delegates_to_module() -> None:
    sentinel = ("start", "end")

    with patch(
        "app.services.ml.regional_forecast_truth.truth_assessment_window",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._truth_assessment_window("2026-04-06")

    assert result is sentinel
    mocked.assert_called_once_with(
        "2026-04-06",
        truth_lookback_weeks=regional_forecast_module._TRUTH_LOOKBACK_WEEKS,
        pd_module=regional_forecast_module.pd,
    )


def test_truth_signal_context_wrapper_delegates_to_module() -> None:
    sentinel = {"signal_present": True}

    with patch(
        "app.services.ml.regional_forecast_truth.truth_signal_context",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._truth_signal_context(
            prediction={"decision": {"stage": "activate"}},
            confidence=0.8,
            stage="activate",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        prediction={"decision": {"stage": "activate"}},
        confidence=0.8,
        stage="activate",
    )


def test_fallback_truth_assessment_wrapper_delegates_to_module() -> None:
    sentinel = {"evidence_status": "no_truth"}

    with patch(
        "app.services.ml.regional_forecast_truth.fallback_truth_assessment",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._fallback_truth_assessment(
            brand="gelo",
            region_code="BY",
            product="GeloMyrtol forte",
            window_start="2026-01-01",
            window_end="2026-03-31",
            signal_context={"signal_present": True},
            source_mode="unavailable",
            message="fehlend",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        brand="gelo",
        region_code="BY",
        product="GeloMyrtol forte",
        window_start="2026-01-01",
        window_end="2026-03-31",
        signal_context={"signal_present": True},
        source_mode="unavailable",
        message="fehlend",
    )


def test_commercial_truth_gate_wrapper_delegates_to_module() -> None:
    sentinel = ("released", "release")

    with patch(
        "app.services.ml.regional_forecast_truth.commercial_truth_gate",
        return_value=sentinel,
    ) as mocked:
        result = RegionalForecastService._commercial_truth_gate(
            truth_assessment={"evidence_status": "truth_backed"},
            operational_action="activate",
            operational_gate_open=True,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        truth_assessment={"evidence_status": "truth_backed"},
        operational_action="activate",
        operational_gate_open=True,
    )


def test_truth_layer_rollup_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"enabled": False}

    with patch(
        "app.services.ml.regional_forecast_truth.truth_layer_rollup",
        return_value=sentinel,
    ) as mocked:
        result = service._truth_layer_rollup([{"evidence_status": "no_truth"}])

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        [{"evidence_status": "no_truth"}],
        truth_lookback_weeks=regional_forecast_module._TRUTH_LOOKBACK_WEEKS,
    )


def test_empty_forecast_response_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"status": "no_model"}

    with patch(
        "app.services.ml.regional_forecast_views.empty_forecast_response",
        return_value=sentinel,
    ) as mocked:
        result = service._empty_forecast_response(
            virus_typ="Influenza A",
            horizon_days=7,
            status="no_model",
            message="kein Modell",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        horizon_days=7,
        status="no_model",
        message="kein Modell",
        artifact_transition_mode=None,
        supported_horizon_days_for_virus=None,
        ensure_supported_horizon_fn=ANY,
        supported_forecast_horizons=regional_forecast_module.SUPPORTED_FORECAST_HORIZONS,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_empty_media_allocation_response_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"status": "no_model"}

    with patch(
        "app.services.ml.regional_forecast_views.empty_media_allocation_response",
        return_value=sentinel,
    ) as mocked:
        result = service._empty_media_allocation_response(
            virus_typ="Influenza A",
            weekly_budget_eur=1000.0,
            horizon_days=7,
            status="no_model",
            message="kein Modell",
            quality_gate={"overall_passed": False},
            business_gate={"validated_for_budget_activation": False},
            rollout_mode="gated",
            activation_policy="quality_gate",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        weekly_budget_eur=1000.0,
        horizon_days=7,
        status="no_model",
        message="kein Modell",
        quality_gate={"overall_passed": False},
        business_gate={"validated_for_budget_activation": False},
        rollout_mode="gated",
        activation_policy="quality_gate",
        portfolio_products=regional_forecast_module.DEFAULT_PORTFOLIO_PRODUCTS,
        supported_forecast_horizons=regional_forecast_module.SUPPORTED_FORECAST_HORIZONS,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_benchmark_supported_viruses_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"benchmark": []}

    with patch(
        "app.services.ml.regional_forecast_views.benchmark_supported_viruses",
        return_value=sentinel,
    ) as mocked:
        result = service.benchmark_supported_viruses(
            reference_virus="Influenza A",
            horizon_days=7,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        reference_virus="Influenza A",
        horizon_days=7,
        ensure_supported_horizon_fn=ANY,
        supported_virus_types=regional_forecast_module.SUPPORTED_VIRUS_TYPES,
        regional_horizon_support_status_fn=regional_forecast_module.regional_horizon_support_status,
        artifact_source_coverage_scope=regional_forecast_module.ARTIFACT_SOURCE_COVERAGE_SCOPE,
        rollout_mode_for_virus_fn=regional_forecast_module.rollout_mode_for_virus,
        activation_policy_for_virus_fn=regional_forecast_module.activation_policy_for_virus,
        signal_bundle_version_for_virus_fn=regional_forecast_module.signal_bundle_version_for_virus,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_build_hero_overview_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"hero_timeseries": []}

    with patch(
        "app.services.ml.regional_forecast_views.build_hero_overview",
        return_value=sentinel,
    ) as mocked:
        result = service.build_hero_overview(
            horizon_days=7,
            reference_virus="Influenza A",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        horizon_days=7,
        reference_virus="Influenza A",
        ensure_supported_horizon_fn=ANY,
        supported_virus_types=regional_forecast_module.SUPPORTED_VIRUS_TYPES,
        portfolio_products=regional_forecast_module.DEFAULT_PORTFOLIO_PRODUCTS,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_build_portfolio_view_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"top_opportunities": []}

    with patch(
        "app.services.ml.regional_forecast_views.build_portfolio_view",
        return_value=sentinel,
    ) as mocked:
        result = service.build_portfolio_view(
            horizon_days=7,
            top_n=12,
            reference_virus="Influenza A",
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        horizon_days=7,
        top_n=12,
        reference_virus="Influenza A",
        ensure_supported_horizon_fn=ANY,
        supported_virus_types=regional_forecast_module.SUPPORTED_VIRUS_TYPES,
        portfolio_products=regional_forecast_module.DEFAULT_PORTFOLIO_PRODUCTS,
        media_channels=regional_forecast_module.MEDIA_CHANNELS,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_get_validation_summary_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"status": "trained"}

    with patch(
        "app.services.ml.regional_forecast_views.get_validation_summary",
        return_value=sentinel,
    ) as mocked:
        result = service.get_validation_summary(
            virus_typ="Influenza A",
            brand="gelo",
            horizon_days=7,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        brand="gelo",
        horizon_days=7,
        ensure_supported_horizon_fn=ANY,
        regional_horizon_support_status_fn=regional_forecast_module.regional_horizon_support_status,
        artifact_source_coverage_scope=regional_forecast_module.ARTIFACT_SOURCE_COVERAGE_SCOPE,
        signal_bundle_version_for_virus_fn=regional_forecast_module.signal_bundle_version_for_virus,
        rollout_mode_for_virus_fn=regional_forecast_module.rollout_mode_for_virus,
        activation_policy_for_virus_fn=regional_forecast_module.activation_policy_for_virus,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_model_version_wrapper_delegates_to_module() -> None:
    metadata = {"model_family": "regional_pooled_panel", "trained_at": "2026-01-01T00:00:00"}

    with patch(
        "app.services.ml.regional_forecast_views.model_version",
        return_value="regional_pooled_panel:2026",
    ) as mocked:
        result = RegionalForecastService._model_version(metadata)

    assert result == "regional_pooled_panel:2026"
    mocked.assert_called_once_with(metadata)


def test_calibration_version_wrapper_delegates_to_module() -> None:
    metadata = {"trained_at": "2026-01-01T00:00:00"}

    with patch(
        "app.services.ml.regional_forecast_views.calibration_version",
        return_value="isotonic:2026",
    ) as mocked:
        result = RegionalForecastService._calibration_version(metadata)

    assert result == "isotonic:2026"
    mocked.assert_called_once_with(metadata)


def test_predict_all_regions_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"predictions": []}

    with patch(
        "app.services.ml.regional_forecast_prediction.predict_all_regions",
        return_value=sentinel,
    ) as mocked:
        result = service.predict_all_regions(
            virus_typ="Influenza A",
            horizon_days=7,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        horizon_days=7,
        ensure_supported_horizon_fn=regional_forecast_module.ensure_supported_horizon,
        regional_horizon_support_status_fn=regional_forecast_module.regional_horizon_support_status,
        supported_forecast_horizons=regional_forecast_module.SUPPORTED_FORECAST_HORIZONS,
        target_window_days_default=regional_forecast_module.TARGET_WINDOW_DAYS,
        signal_bundle_version_for_virus_fn=regional_forecast_module.signal_bundle_version_for_virus,
        rollout_mode_for_virus_fn=regional_forecast_module.rollout_mode_for_virus,
        activation_policy_for_virus_fn=regional_forecast_module.activation_policy_for_virus,
        event_definition_version=regional_forecast_module.EVENT_DEFINITION_VERSION,
        artifact_source_coverage_scope=regional_forecast_module.ARTIFACT_SOURCE_COVERAGE_SCOPE,
        geo_hierarchy_helper_cls=regional_forecast_module.GeoHierarchyHelper,
        tsfm_adapter_cls=regional_forecast_module.TSFMAdapter,
        pd_module=regional_forecast_module.pd,
        np_module=regional_forecast_module.np,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_generate_media_allocation_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"recommendations": []}

    with patch(
        "app.services.ml.regional_forecast_workflows.generate_media_allocation",
        return_value=sentinel,
    ) as mocked:
        result = service.generate_media_allocation(
            virus_typ="Influenza A",
            weekly_budget_eur=1500.0,
            horizon_days=7,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        weekly_budget_eur=1500.0,
        horizon_days=7,
        rollout_mode_for_virus_fn=regional_forecast_module.rollout_mode_for_virus,
        activation_policy_for_virus_fn=regional_forecast_module.activation_policy_for_virus,
        portfolio_products=regional_forecast_module.DEFAULT_PORTFOLIO_PRODUCTS,
        media_channels=regional_forecast_module.MEDIA_CHANNELS,
        utc_now_fn=regional_forecast_module.utc_now,
    )


def test_generate_media_activation_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"recommendations": []}

    with patch(
        "app.services.ml.regional_forecast_workflows.generate_media_activation",
        return_value=sentinel,
    ) as mocked:
        result = service.generate_media_activation(
            virus_typ="Influenza A",
            weekly_budget_eur=1500.0,
            horizon_days=7,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        weekly_budget_eur=1500.0,
        horizon_days=7,
    )


def test_generate_campaign_recommendations_wrapper_delegates_to_module() -> None:
    service = RegionalForecastService(db=None)
    sentinel = {"recommendations": []}

    with patch(
        "app.services.ml.regional_forecast_workflows.generate_campaign_recommendations",
        return_value=sentinel,
    ) as mocked:
        result = service.generate_campaign_recommendations(
            virus_typ="Influenza A",
            weekly_budget_eur=1500.0,
            horizon_days=7,
            top_n=5,
        )

    assert result is sentinel
    mocked.assert_called_once_with(
        service,
        virus_typ="Influenza A",
        weekly_budget_eur=1500.0,
        horizon_days=7,
        top_n=5,
    )
