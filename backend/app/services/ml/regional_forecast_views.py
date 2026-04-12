"""View and response helper functions for regional forecast service."""

from __future__ import annotations

from typing import Any


def empty_forecast_response(
    service,
    *,
    virus_typ: str,
    horizon_days: int,
    status: str,
    message: str,
    artifact_transition_mode: str | None = None,
    artifact_diagnostic: dict[str, Any] | None = None,
    supported_horizon_days_for_virus: list[int] | None = None,
    ensure_supported_horizon_fn,
    supported_forecast_horizons,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    diagnostic = dict(artifact_diagnostic or {})
    artifact_scope = diagnostic.get("artifact_scope")
    return {
        "virus_typ": virus_typ,
        "status": status,
        "message": message,
        "operator_message": diagnostic.get("operator_message"),
        "bootstrap_command": diagnostic.get("bootstrap_command"),
        "missing_artifacts": bool(diagnostic.get("bootstrap_required")),
        "missing_scopes": [artifact_scope] if artifact_scope else [],
        "artifact_diagnostic": diagnostic or None,
        "horizon_days": horizon,
        "supported_horizon_days": list(supported_forecast_horizons),
        "supported_horizon_days_for_virus": list(
            supported_horizon_days_for_virus or supported_forecast_horizons
        ),
        "target_window_days": service._target_window_for_horizon(horizon),
        "artifact_transition_mode": artifact_transition_mode,
        "predictions": [],
        "top_5": [],
        "top_decisions": [],
        "decision_summary": service._decision_summary([]),
        "total_regions": 0,
        "generated_at": utc_now_fn().isoformat(),
    }


def empty_media_allocation_response(
    service,
    *,
    virus_typ: str,
    weekly_budget_eur: float,
    horizon_days: int,
    status: str,
    message: str,
    quality_gate: dict[str, Any],
    business_gate: dict[str, Any],
    rollout_mode: str,
    activation_policy: str,
    portfolio_products,
    supported_forecast_horizons,
    utc_now_fn,
) -> dict[str, Any]:
    allocation = service.media_allocation_engine.allocate(
        virus_typ=virus_typ,
        predictions=[],
        total_budget_eur=weekly_budget_eur,
        spend_enabled=False,
        spend_blockers=[],
        default_products=portfolio_products.get(virus_typ, ["GeloMyrtol forte"]),
    )
    summary = dict(allocation.get("summary") or {})
    summary.update(
        {
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "evidence_tier": business_gate.get("evidence_tier"),
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "allocation_policy_version": allocation.get("allocation_policy_version"),
        }
    )
    return {
        "virus_typ": virus_typ,
        "status": status,
        "message": message,
        "headline": allocation.get("headline") or f"{virus_typ}: keine regionalen Allocation-Empfehlungen verfügbar",
        "summary": summary,
        "allocation_config": allocation.get("config") or {},
        "horizon_days": horizon_days,
        "supported_horizon_days": list(supported_forecast_horizons),
        "target_window_days": service._target_window_for_horizon(horizon_days),
        "truth_layer": service._truth_layer_rollup([]),
        "generated_at": utc_now_fn().isoformat(),
        "recommendations": [],
    }


def benchmark_supported_viruses(
    service,
    *,
    reference_virus: str = "Influenza A",
    horizon_days: int = 7,
    ensure_supported_horizon_fn,
    supported_virus_types,
    regional_horizon_support_status_fn,
    artifact_source_coverage_scope,
    rollout_mode_for_virus_fn,
    activation_policy_for_virus_fn,
    signal_bundle_version_for_virus_fn,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    items: list[dict[str, Any]] = []
    reference_metrics: dict[str, Any] | None = None
    truth_readiness = service._truth_readiness()

    for virus_typ in supported_virus_types:
        support = regional_horizon_support_status_fn(virus_typ, horizon)
        if not support["supported"]:
            unsupported_business_gate = service._business_gate(
                quality_gate={"overall_passed": False},
                truth_readiness=truth_readiness,
            )
            items.append(
                {
                    "virus_typ": virus_typ,
                    "horizon_days": horizon,
                    "target_window_days": service._target_window_for_horizon(horizon),
                    "status": "unsupported",
                    "message": support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
                    "trained_at": None,
                    "states": 0,
                    "rows": 0,
                    "truth_source": None,
                    "source_coverage": {},
                    "source_coverage_scope": artifact_source_coverage_scope,
                    "point_in_time_snapshot": {},
                    "aggregate_metrics": {},
                    "quality_gate": {"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
                    "business_gate": unsupported_business_gate,
                    "evidence_tier": unsupported_business_gate.get("evidence_tier"),
                    "rollout_mode": rollout_mode_for_virus_fn(virus_typ),
                    "activation_policy": activation_policy_for_virus_fn(virus_typ),
                    "signal_bundle_version": signal_bundle_version_for_virus_fn(virus_typ),
                    "model_version": None,
                    "calibration_version": None,
                }
            )
            continue

        artifacts = service._load_artifacts(virus_typ, horizon_days=horizon)
        metadata = artifacts.get("metadata") or {}
        load_error = str(artifacts.get("load_error") or "").strip()
        aggregate_metrics = metadata.get("aggregate_metrics") or {}
        quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
        dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
        business_gate = service._business_gate(
            quality_gate=quality_gate,
            truth_readiness=truth_readiness,
        )

        item = {
            "virus_typ": virus_typ,
            "horizon_days": int(metadata.get("horizon_days") or horizon),
            "target_window_days": metadata.get("target_window_days") or service._target_window_for_horizon(horizon),
            "status": "trained" if aggregate_metrics and not load_error else "no_model",
            "message": load_error or metadata.get("message"),
            "trained_at": metadata.get("trained_at"),
            "states": int(dataset_manifest.get("states") or 0),
            "rows": int(dataset_manifest.get("rows") or 0),
            "truth_source": dataset_manifest.get("truth_source"),
            "source_coverage": dataset_manifest.get("source_coverage") or {},
            "source_coverage_scope": artifact_source_coverage_scope,
            "point_in_time_snapshot": artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {},
            "aggregate_metrics": aggregate_metrics,
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "evidence_tier": business_gate.get("evidence_tier"),
            "rollout_mode": metadata.get("rollout_mode") or rollout_mode_for_virus_fn(virus_typ),
            "activation_policy": metadata.get("activation_policy") or activation_policy_for_virus_fn(virus_typ),
            "signal_bundle_version": metadata.get("signal_bundle_version") or signal_bundle_version_for_virus_fn(virus_typ),
            "model_version": metadata.get("model_version") or service._model_version(metadata),
            "calibration_version": metadata.get("calibration_version") or service._calibration_version(metadata),
            "selection": metadata.get("label_selection") or {},
            "shadow_evaluation": metadata.get("shadow_evaluation") or {},
        }
        if virus_typ == reference_virus and aggregate_metrics:
            reference_metrics = aggregate_metrics
        items.append(item)

    for item in items:
        item["delta_vs_reference"] = service._metric_delta(
            item.get("aggregate_metrics") or {},
            reference_metrics or {},
        )
        item["benchmark_score"] = service._benchmark_score(item)

    ranked = sorted(
        items,
        key=lambda item: (
            item.get("status") == "trained",
            bool((item.get("quality_gate") or {}).get("overall_passed")),
            float((item.get("aggregate_metrics") or {}).get("precision_at_top3") or 0.0),
            float((item.get("aggregate_metrics") or {}).get("pr_auc") or 0.0),
            -float((item.get("aggregate_metrics") or {}).get("ece") or 1.0),
            -float((item.get("aggregate_metrics") or {}).get("activation_false_positive_rate") or 1.0),
        ),
        reverse=True,
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank

    summary_business_gate = service._business_gate(
        quality_gate={"overall_passed": any((item.get("quality_gate") or {}).get("overall_passed") for item in ranked)},
        truth_readiness=truth_readiness,
    )
    return {
        "reference_virus": reference_virus,
        "horizon_days": horizon,
        "target_window_days": service._target_window_for_horizon(horizon),
        "generated_at": utc_now_fn().isoformat(),
        "trained_viruses": sum(1 for item in ranked if item["status"] == "trained"),
        "go_viruses": sum(
            1
            for item in ranked
            if (item.get("quality_gate") or {}).get("overall_passed")
            and item.get("activation_policy") != "watch_only"
        ),
        "business_gate": summary_business_gate,
        "evidence_tier": summary_business_gate.get("evidence_tier"),
        "benchmark": ranked,
    }


def build_hero_overview(
    service,
    *,
    horizon_days: int = 7,
    reference_virus: str = "Influenza A",
    ensure_supported_horizon_fn,
    supported_virus_types,
    portfolio_products,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    snapshots = (
        service.snapshot_store.latest_scope_snapshots(
            virus_types=supported_virus_types,
            horizon_days_list=[horizon],
            limit=500,
        )
        if service.snapshot_store is not None
        else {}
    )

    virus_rollup: list[dict[str, Any]] = []
    hero_timeseries: list[dict[str, Any]] = []
    latest_as_of_date: str | None = None

    for virus_typ in supported_virus_types:
        metadata = snapshots.get((virus_typ, horizon)) or {}
        series = service._hero_timeseries_for_virus(
            virus_typ=virus_typ,
            horizon_days=horizon,
        )
        if series:
            hero_timeseries.append(series)
        if not metadata:
            continue

        top_change_pct = metadata.get("top_change_pct")
        if top_change_pct is None:
            continue

        forecast_as_of_date = metadata.get("forecast_as_of_date")
        if forecast_as_of_date:
            latest_as_of_date = str(
                max(
                    filter(
                        None,
                        [latest_as_of_date, str(forecast_as_of_date)],
                    )
                )
            )

        virus_rollup.append(
            {
                "virus_typ": virus_typ,
                "quality_gate": metadata.get("quality_gate") or {},
                "business_gate": metadata.get("business_gate") or {},
                "evidence_tier": metadata.get("evidence_tier"),
                "aggregate_metrics": {},
                "top_region": metadata.get("top_region"),
                "top_region_name": metadata.get("top_region_name"),
                "top_event_probability": metadata.get("top_event_probability"),
                "top_change_pct": top_change_pct,
                "top_trend": metadata.get("top_trend"),
                "products": portfolio_products.get(virus_typ, ["GeloMyrtol forte"]),
            }
        )

    go_viruses = sum(
        1
        for item in virus_rollup
        if bool((item.get("quality_gate") or {}).get("overall_passed"))
        and str((item.get("business_gate") or {}).get("action_class") or "") != "watch_only"
    )

    return {
        "generated_at": utc_now_fn().isoformat(),
        "reference_virus": reference_virus,
        "latest_as_of_date": latest_as_of_date,
        "summary": {
            "trained_viruses": len(virus_rollup),
            "go_viruses": go_viruses,
            "total_opportunities": len(virus_rollup),
            "watchlist_opportunities": max(len(virus_rollup) - go_viruses, 0),
            "priority_opportunities": 0,
            "validated_opportunities": go_viruses,
        },
        "business_gate": service._business_gate(
            quality_gate={"overall_passed": bool(go_viruses)},
        ),
        "evidence_tier": None,
        "benchmark": [],
        "virus_rollup": virus_rollup,
        "hero_timeseries": hero_timeseries,
        "region_rollup": [],
        "top_opportunities": [],
    }


def build_portfolio_view(
    service,
    *,
    horizon_days: int = 7,
    top_n: int = 12,
    reference_virus: str = "Influenza A",
    ensure_supported_horizon_fn,
    supported_virus_types,
    portfolio_products,
    media_channels,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    benchmark_payload = service.benchmark_supported_viruses(
        reference_virus=reference_virus,
        horizon_days=horizon,
    )
    benchmark_map = {
        item["virus_typ"]: item
        for item in benchmark_payload.get("benchmark", [])
        if item.get("status") == "trained"
    }

    opportunities: list[dict[str, Any]] = []
    virus_rollup: list[dict[str, Any]] = []
    latest_as_of_date: str | None = None

    for virus_typ in supported_virus_types:
        benchmark_item = benchmark_map.get(virus_typ)
        if not benchmark_item:
            continue

        forecast = service.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon)
        predictions = forecast.get("predictions") or []
        if not predictions:
            continue

        top_prediction = predictions[0]
        top_event_probability = (
            top_prediction.get("event_probability")
            or top_prediction.get("event_probability_calibrated")
        )
        latest_as_of_date = str(max(filter(None, [latest_as_of_date, forecast.get("as_of_date")])))
        virus_rollup.append(
            {
                "virus_typ": virus_typ,
                "rank": benchmark_item.get("rank"),
                "benchmark_score": benchmark_item.get("benchmark_score"),
                "quality_gate": benchmark_item.get("quality_gate"),
                "business_gate": benchmark_item.get("business_gate"),
                "evidence_tier": benchmark_item.get("evidence_tier"),
                "rollout_mode": benchmark_item.get("rollout_mode"),
                "activation_policy": benchmark_item.get("activation_policy"),
                "aggregate_metrics": benchmark_item.get("aggregate_metrics"),
                "top_region": top_prediction.get("bundesland"),
                "top_region_name": top_prediction.get("bundesland_name"),
                "top_event_probability": top_event_probability,
                "top_change_pct": top_prediction.get("change_pct"),
                "products": portfolio_products.get(virus_typ, ["GeloMyrtol forte"]),
            }
        )

        for prediction in predictions:
            action, intensity = service._portfolio_action(
                prediction=prediction,
                benchmark_item=benchmark_item,
            )
            truth_overlay = service._truth_layer_assessment_for_products(
                region_code=prediction["bundesland"],
                products=portfolio_products.get(virus_typ, ["GeloMyrtol forte"]),
                target_week_start=prediction["target_week_start"],
                signal_context=service._truth_signal_context(prediction=prediction),
                operational_action=action,
                operational_gate_open=action in {"activate", "prepare"},
            )
            opportunities.append(
                {
                    "virus_typ": virus_typ,
                    "bundesland": prediction["bundesland"],
                    "bundesland_name": prediction["bundesland_name"],
                    "rank_within_virus": prediction["rank"],
                    "portfolio_action": action,
                    "portfolio_intensity": intensity,
                    "portfolio_priority_score": service._portfolio_priority_score(
                        prediction=prediction,
                        benchmark_item=benchmark_item,
                    ),
                    "event_probability": (
                        prediction.get("event_probability")
                        or prediction.get("event_probability_calibrated")
                    ),
                    "expected_next_week_incidence": prediction["expected_next_week_incidence"],
                    "prediction_interval": prediction["prediction_interval"],
                    "current_known_incidence": prediction["current_known_incidence"],
                    "change_pct": prediction["change_pct"],
                    "trend": prediction["trend"],
                    "quality_gate": prediction["quality_gate"],
                    "business_gate": prediction.get("business_gate") or benchmark_item.get("business_gate"),
                    "evidence_tier": (prediction.get("business_gate") or benchmark_item.get("business_gate") or {}).get("evidence_tier"),
                    "rollout_mode": prediction.get("rollout_mode"),
                    "activation_policy": prediction.get("activation_policy"),
                    "signal_bundle_version": prediction.get("signal_bundle_version"),
                    "model_version": prediction.get("model_version") or benchmark_item.get("model_version"),
                    "calibration_version": prediction.get("calibration_version") or benchmark_item.get("calibration_version"),
                    "benchmark_rank": benchmark_item.get("rank"),
                    "benchmark_score": benchmark_item.get("benchmark_score"),
                    "aggregate_metrics": benchmark_item.get("aggregate_metrics"),
                    "products": portfolio_products.get(virus_typ, ["GeloMyrtol forte"]),
                    "channels": media_channels[intensity],
                    "as_of_date": prediction["as_of_date"],
                    "target_week_start": prediction["target_week_start"],
                    "truth_layer_enabled": truth_overlay["truth_layer_enabled"],
                    "truth_scope": truth_overlay["truth_scope"],
                    "outcome_readiness": truth_overlay["outcome_readiness"],
                    "evidence_status": truth_overlay["evidence_status"],
                    "evidence_confidence": truth_overlay["evidence_confidence"],
                    "signal_outcome_agreement": truth_overlay["signal_outcome_agreement"],
                    "spend_gate_status": truth_overlay["spend_gate_status"],
                    "budget_release_recommendation": truth_overlay["budget_release_recommendation"],
                    "commercial_gate": truth_overlay["commercial_gate"],
                    "truth_assessments": truth_overlay["truth_assessments"],
                }
            )

    opportunities.sort(
        key=lambda item: (
            float(item.get("portfolio_priority_score") or 0.0),
            float(item.get("event_probability") or 0.0),
            float(item.get("change_pct") or 0.0),
        ),
        reverse=True,
    )
    for rank, item in enumerate(opportunities, start=1):
        item["rank"] = rank

    region_rollup = service._region_rollup(opportunities)
    return {
        "generated_at": utc_now_fn().isoformat(),
        "reference_virus": reference_virus,
        "horizon_days": horizon,
        "target_window_days": service._target_window_for_horizon(horizon),
        "latest_as_of_date": latest_as_of_date,
        "summary": {
            "trained_viruses": benchmark_payload.get("trained_viruses", 0),
            "go_viruses": benchmark_payload.get("go_viruses", 0),
            "total_opportunities": len(opportunities),
            "watchlist_opportunities": sum(1 for item in opportunities if item["portfolio_action"] == "watch"),
            "priority_opportunities": sum(1 for item in opportunities if item["portfolio_action"] == "prioritize"),
            "validated_opportunities": sum(1 for item in opportunities if item["portfolio_action"] in {"activate", "prepare"}),
        },
        "business_gate": benchmark_payload.get("business_gate") or service._business_gate(quality_gate={"overall_passed": False}),
        "evidence_tier": benchmark_payload.get("evidence_tier"),
        "truth_layer": service._truth_layer_rollup(opportunities),
        "benchmark": benchmark_payload.get("benchmark", []),
        "virus_rollup": virus_rollup,
        "region_rollup": region_rollup,
        "top_opportunities": opportunities[: max(int(top_n), 1)],
    }


def get_validation_summary(
    service,
    *,
    virus_typ: str = "Influenza A",
    brand: str = "gelo",
    horizon_days: int = 7,
    ensure_supported_horizon_fn,
    regional_horizon_support_status_fn,
    artifact_source_coverage_scope,
    signal_bundle_version_for_virus_fn,
    rollout_mode_for_virus_fn,
    activation_policy_for_virus_fn,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    support = regional_horizon_support_status_fn(virus_typ, horizon)
    if not support["supported"]:
        business_gate = service._business_gate(
            quality_gate={"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
            brand=brand,
        )
        return {
            "virus_typ": virus_typ,
            "brand": str(brand or "gelo").strip().lower(),
            "horizon_days": horizon,
            "target_window_days": service._target_window_for_horizon(horizon),
            "status": "unsupported",
            "message": support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
            "generated_at": utc_now_fn().isoformat(),
            "quality_gate": {"overall_passed": False, "forecast_readiness": "UNSUPPORTED"},
            "business_gate": business_gate,
            "operator_context": business_gate.get("operator_context"),
            "evidence_tier": business_gate.get("evidence_tier"),
            "model_version": None,
            "calibration_version": None,
            "point_in_time_snapshot": {},
            "source_coverage": {},
            "source_coverage_scope": artifact_source_coverage_scope,
            "signal_bundle_version": signal_bundle_version_for_virus_fn(virus_typ),
            "rollout_mode": rollout_mode_for_virus_fn(virus_typ),
            "activation_policy": activation_policy_for_virus_fn(virus_typ),
            "aggregate_metrics": {},
        }

    artifacts = service._load_artifacts(virus_typ, horizon_days=horizon)
    metadata = artifacts.get("metadata") or {}
    load_error = str(artifacts.get("load_error") or "").strip()
    quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
    business_gate = service._business_gate(
        quality_gate=quality_gate,
        brand=brand,
    )
    dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
    return {
        "virus_typ": virus_typ,
        "brand": str(brand or "gelo").strip().lower(),
        "horizon_days": int(metadata.get("horizon_days") or horizon),
        "target_window_days": metadata.get("target_window_days") or service._target_window_for_horizon(horizon),
        "status": "trained" if not load_error and metadata.get("aggregate_metrics") else "no_model",
        "message": load_error or metadata.get("message"),
        "generated_at": utc_now_fn().isoformat(),
        "quality_gate": quality_gate,
        "business_gate": business_gate,
        "operator_context": business_gate.get("operator_context"),
        "evidence_tier": business_gate.get("evidence_tier"),
        "model_version": metadata.get("model_version") or service._model_version(metadata),
        "calibration_version": metadata.get("calibration_version") or service._calibration_version(metadata),
        "point_in_time_snapshot": artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {},
        "source_coverage": dataset_manifest.get("source_coverage") or {},
        "source_coverage_scope": artifact_source_coverage_scope,
        "signal_bundle_version": metadata.get("signal_bundle_version") or signal_bundle_version_for_virus_fn(virus_typ),
        "rollout_mode": metadata.get("rollout_mode") or rollout_mode_for_virus_fn(virus_typ),
        "activation_policy": metadata.get("activation_policy") or activation_policy_for_virus_fn(virus_typ),
        "aggregate_metrics": metadata.get("aggregate_metrics") or {},
    }


def model_version(metadata: dict[str, Any]) -> str:
    model_family = str(metadata.get("model_family") or "regional_pooled_panel")
    trained_at = str(metadata.get("trained_at") or "unversioned")
    horizon = metadata.get("horizon_days")
    if horizon is None:
        return f"{model_family}:{trained_at}"
    return f"{model_family}:h{horizon}:{trained_at}"


def calibration_version(metadata: dict[str, Any]) -> str:
    trained_at = str(metadata.get("trained_at") or "unversioned")
    horizon = metadata.get("horizon_days")
    if horizon is None:
        return f"isotonic:{trained_at}"
    return f"isotonic:h{horizon}:{trained_at}"
