from unittest.mock import patch

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
        gelo_products=regional_forecast_module.GELO_PRODUCTS,
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
