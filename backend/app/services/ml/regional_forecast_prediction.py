"""Prediction workflow helpers for regional forecast service."""

from __future__ import annotations

from typing import Any

from app.services.ml.benchmarking.contracts import CANONICAL_FORECAST_QUANTILES
from app.services.ml.forecast_science_contract import (
    CALIBRATION_EVIDENCE_MODE,
    QUANTILE_GRID_VERSION,
    SCIENCE_CONTRACT_VERSION,
)
from app.services.ml.regional_panel_utils import ALL_BUNDESLAENDER


def _regional_as_of_lag_days(*, run_as_of_date: Any, row_as_of_date: Any, pd_module: Any) -> int:
    run_as_of = pd_module.Timestamp(run_as_of_date).normalize()
    row_as_of = pd_module.Timestamp(row_as_of_date).normalize()
    return max(int((run_as_of - row_as_of).days), 0)


def _force_watch_for_regional_coverage(
    decision: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    updated = dict(decision)
    updated["stage"] = "watch"
    reason_trace = dict(updated.get("reason_trace") or {})
    policy_overrides = list(reason_trace.get("policy_overrides") or [])
    if reason not in policy_overrides:
        policy_overrides.append(reason)
    reason_trace["policy_overrides"] = policy_overrides
    policy_override_details = list(reason_trace.get("policy_override_details") or [])
    policy_override_details.append(
        {
            "key": "regional_data_stale",
            "message": reason,
        }
    )
    reason_trace["policy_override_details"] = policy_override_details
    uncertainty = list(reason_trace.get("uncertainty") or [])
    uncertainty.append(reason)
    reason_trace["uncertainty"] = uncertainty
    updated["reason_trace"] = reason_trace
    updated["explanation_summary"] = reason
    updated["uncertainty_summary"] = reason
    metadata = dict(updated.get("metadata") or {})
    metadata["coverage_blocked"] = True
    updated["metadata"] = metadata
    return updated


def _legacy_non_sars_context_fill_columns(
    *,
    virus_typ: str,
    missing_columns: list[str],
) -> list[str]:
    if str(virus_typ or "").strip() == "SARS-CoV-2":
        return []
    return sorted(
        column
        for column in missing_columns
        if str(column).startswith("sars_")
    )


def predict_all_regions(
    service,
    *,
    virus_typ: str = "Influenza A",
    brand: str,
    horizon_days: int = 7,
    ensure_supported_horizon_fn,
    regional_horizon_support_status_fn,
    supported_forecast_horizons,
    target_window_days_default,
    signal_bundle_version_for_virus_fn,
    rollout_mode_for_virus_fn,
    activation_policy_for_virus_fn,
    event_definition_version,
    artifact_source_coverage_scope,
    geo_hierarchy_helper_cls,
    tsfm_adapter_cls,
    pd_module,
    np_module,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    support = regional_horizon_support_status_fn(virus_typ, horizon)
    if not support["supported"]:
        return service._empty_forecast_response(
            virus_typ=virus_typ,
            horizon_days=horizon,
            status="unsupported",
            message=support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
            supported_horizon_days_for_virus=support["supported_horizons"],
        )
    target_window_days = service._target_window_for_horizon(horizon)
    artifacts = service._load_artifacts(virus_typ, horizon_days=horizon)
    artifact_diagnostic = artifacts.get("artifact_diagnostic")
    metadata = artifacts.get("metadata") or {}
    artifact_transition_mode = str(
        artifacts.get("artifact_transition_mode")
        or metadata.get("artifact_transition_mode")
        or ""
    ).strip() or None
    feature_columns = metadata.get("feature_columns") or []
    load_error = str(artifacts.get("load_error") or "").strip()
    if load_error:
        return service._empty_forecast_response(
            virus_typ=virus_typ,
            horizon_days=horizon,
            status="no_model",
            message=load_error,
            artifact_transition_mode=artifact_transition_mode,
            artifact_diagnostic=artifact_diagnostic,
            supported_horizon_days_for_virus=support["supported_horizons"],
        )
    if not artifacts or not feature_columns:
        message = (
            f"Kein regionales Panel-Modell für Horizon {horizon} verfügbar. "
            "Bitte horizon-spezifisches Training starten."
        )
        if artifact_diagnostic and artifact_diagnostic.get("operator_message"):
            message = str(artifact_diagnostic["operator_message"])
        elif artifact_transition_mode == "legacy_default_window_fallback":
            message = (
                f"Horizon {horizon} nutzt noch Legacy-3-7-Tage-Artefakte. "
                "Bitte horizon-spezifisches Retraining durchführen."
            )
        return service._empty_forecast_response(
            virus_typ=virus_typ,
            horizon_days=horizon,
            status="no_model",
            message=message,
            artifact_transition_mode=artifact_transition_mode,
            artifact_diagnostic=artifact_diagnostic,
            supported_horizon_days_for_virus=support["supported_horizons"],
        )

    as_of_date = service._latest_as_of_date(virus_typ=virus_typ)
    run_as_of_date = pd_module.Timestamp(as_of_date).normalize()
    revision_policy = service.orchestrator.resolve_revision_policy(metadata=metadata)
    revision_policy_metadata = metadata.get("revision_policy_metadata") or {}
    source_revision_policy = revision_policy_metadata.get("source_policies") or {}
    try:
        panel = service.feature_builder.build_inference_panel(
            virus_typ=virus_typ,
            as_of_date=as_of_date.to_pydatetime(),
            lookback_days=180,
            horizon_days=horizon,
            include_nowcast=True,
            use_revision_adjusted=False,
            revision_policy=revision_policy,
            source_revision_policy=source_revision_policy,
        )
    except TypeError:
        panel = service.feature_builder.build_inference_panel(
            virus_typ=virus_typ,
            as_of_date=as_of_date.to_pydatetime(),
            lookback_days=180,
            horizon_days=horizon,
            include_nowcast=True,
            use_revision_adjusted=False,
        )
    if panel.empty:
        return service._empty_forecast_response(
            virus_typ=virus_typ,
            horizon_days=horizon,
            status="no_data",
            message=f"Keine regionalen Features für Horizon {horizon} und den aktuellen Datenstand verfügbar.",
            artifact_transition_mode=artifact_transition_mode,
            supported_horizon_days_for_virus=support["supported_horizons"],
        )

    event_feature_columns = metadata.get("event_feature_columns") or feature_columns

    initially_missing_columns = sorted(
        {
            str(column)
            for column in [*feature_columns, *event_feature_columns]
            if str(column) not in panel.columns
        }
    )
    artifact_feature_compatibility_fills = _legacy_non_sars_context_fill_columns(
        virus_typ=virus_typ,
        missing_columns=initially_missing_columns,
    )
    if artifact_feature_compatibility_fills:
        panel = panel.copy()
        for column in artifact_feature_compatibility_fills:
            panel[column] = 0.0

    missing_feature_columns = sorted(
        {
            str(column)
            for column in feature_columns
            if str(column) not in panel.columns
        }
    )
    missing_event_feature_columns = sorted(
        {
            str(column)
            for column in event_feature_columns
            if str(column) not in panel.columns
        }
    )
    if missing_feature_columns or missing_event_feature_columns:
        missing_columns = sorted({*missing_feature_columns, *missing_event_feature_columns})
        return service._empty_forecast_response(
            virus_typ=virus_typ,
            horizon_days=horizon,
            status="no_model",
            message=(
                f"Artefakt-Bundle für {virus_typ}/h{horizon} referenziert Inferenz-Features, "
                f"die im aktuellen Panel fehlen: {', '.join(missing_columns)}. "
                "Bitte horizon-spezifisches Retraining durchführen."
            ),
            artifact_transition_mode=artifact_transition_mode,
            supported_horizon_days_for_virus=support["supported_horizons"],
        )

    X = panel[feature_columns].to_numpy()
    X_event = panel[event_feature_columns].to_numpy()
    classifier = artifacts["classifier"]
    calibration = artifacts.get("calibration")
    reg_median = artifacts["regressor_median"]
    reg_lower = artifacts["regressor_lower"]
    reg_upper = artifacts["regressor_upper"]
    quantile_regressors = artifacts.get("quantile_regressors") or {}
    hierarchy_models = artifacts.get("hierarchy_models") or {}

    raw_prob = classifier.predict_proba(X_event)[:, 1]
    calibrated_prob = service._apply_calibration(calibration, raw_prob)
    quantile_predictions: dict[float, Any] = {
        0.1: np_module.expm1(reg_lower.predict(X)),
        0.5: np_module.expm1(reg_median.predict(X)),
        0.9: np_module.expm1(reg_upper.predict(X)),
    }
    for quantile, model in sorted(quantile_regressors.items()):
        if quantile in quantile_predictions:
            continue
        quantile_predictions[float(quantile)] = np_module.expm1(model.predict(X))

    hierarchy_meta = metadata.get("hierarchy_reconciliation") or {}
    hierarchy_feature_columns = metadata.get("hierarchy_feature_columns") or feature_columns
    hierarchy_model_modes = hierarchy_meta.get("model_modes") or {}
    hierarchy_cluster_assignments = hierarchy_meta.get("cluster_assignments") or {}
    aggregate_blend_weights = hierarchy_meta.get("aggregate_blend_weights") or {}
    aggregate_blend_policy = hierarchy_meta.get("aggregate_blend_policy") or {}
    cluster_blend_resolution = geo_hierarchy_helper_cls.resolve_blend_weight_policy(
        aggregate_blend_policy.get("cluster"),
        as_of_date=as_of_date,
        horizon_days=horizon,
        fallback=float(aggregate_blend_weights.get("cluster") or 0.0),
    )
    national_blend_resolution = geo_hierarchy_helper_cls.resolve_blend_weight_policy(
        aggregate_blend_policy.get("national"),
        as_of_date=as_of_date,
        horizon_days=horizon,
        fallback=float(aggregate_blend_weights.get("national") or 0.0),
    )
    resolved_blend_weights = {
        "cluster": float(cluster_blend_resolution.get("weight") or 0.0),
        "national": float(national_blend_resolution.get("weight") or 0.0),
    }
    blend_weight_scope = {
        "cluster": cluster_blend_resolution.get("scope"),
        "national": national_blend_resolution.get("scope"),
    }
    blend_regime = cluster_blend_resolution.get("regime") or national_blend_resolution.get("regime")
    state_weights = {
        str(row["bundesland"]): float(row.get("state_population_millions") or 1.0)
        for _, row in panel.iterrows()
    } if "state_population_millions" in panel.columns else {}
    if hierarchy_meta.get("enabled"):
        current_clusters = geo_hierarchy_helper_cls.build_dynamic_clusters(
            panel,
            state_col="bundesland",
            value_col="current_known_incidence",
            date_col="as_of_date",
        )
        if current_clusters:
            hierarchy_cluster_assignments = current_clusters
        cluster_quantiles = None
        national_quantiles = None
        cluster_feature_frame = geo_hierarchy_helper_cls.aggregate_feature_frame(
            panel,
            feature_columns=hierarchy_feature_columns,
            cluster_assignments=hierarchy_cluster_assignments,
            level="cluster",
        )
        national_feature_frame = geo_hierarchy_helper_cls.aggregate_feature_frame(
            panel,
            feature_columns=hierarchy_feature_columns,
            level="national",
        )
        derived_cluster_quantiles = {
            quantile: geo_hierarchy_helper_cls._aggregate_states(
                np_module.asarray(values, dtype=float),
                state_order=[str(value) for value in panel["bundesland"].tolist()],
                cluster_assignments=hierarchy_cluster_assignments,
                cluster_order=geo_hierarchy_helper_cls._cluster_order(
                    [str(value) for value in panel["bundesland"].tolist()],
                    hierarchy_cluster_assignments,
                ),
                state_weights=state_weights,
            )[0]
            for quantile, values in quantile_predictions.items()
        }
        derived_national_quantiles = {
            quantile: geo_hierarchy_helper_cls._aggregate_states(
                np_module.asarray(values, dtype=float),
                state_order=[str(value) for value in panel["bundesland"].tolist()],
                cluster_assignments=hierarchy_cluster_assignments,
                cluster_order=geo_hierarchy_helper_cls._cluster_order(
                    [str(value) for value in panel["bundesland"].tolist()],
                    hierarchy_cluster_assignments,
                ),
                state_weights=state_weights,
            )[1]
            for quantile, values in quantile_predictions.items()
        }
        if not cluster_feature_frame.empty:
            cluster_order = geo_hierarchy_helper_cls._cluster_order(
                [str(value) for value in panel["bundesland"].tolist()],
                hierarchy_cluster_assignments,
            )
            cluster_baseline_map = {
                str(cluster_id): {
                    "hierarchy_state_baseline_q10": float(derived_cluster_quantiles.get(0.1, np_module.asarray([], dtype=float))[idx]),
                    "hierarchy_state_baseline_q50": float(derived_cluster_quantiles.get(0.5, np_module.asarray([], dtype=float))[idx]),
                    "hierarchy_state_baseline_q90": float(derived_cluster_quantiles.get(0.9, np_module.asarray([], dtype=float))[idx]),
                    "hierarchy_state_baseline_width_80": float(
                        max(
                            float(derived_cluster_quantiles.get(0.9, np_module.asarray([], dtype=float))[idx])
                            - float(derived_cluster_quantiles.get(0.1, np_module.asarray([], dtype=float))[idx]),
                            0.0,
                        )
                    ),
                }
                for idx, cluster_id in enumerate(cluster_order)
            }
            for column in geo_hierarchy_helper_cls.HIERARCHY_STATE_BASELINE_FEATURE_COLUMNS:
                cluster_feature_frame[column] = [
                    float((cluster_baseline_map.get(str(group)) or {}).get(column, 0.0))
                    for group in cluster_feature_frame["hierarchy_group"].astype(str)
                ]
        if not national_feature_frame.empty:
            national_feature_frame = national_feature_frame.copy()
            national_feature_frame["hierarchy_state_baseline_q10"] = float(np_module.asarray(derived_national_quantiles.get(0.1), dtype=float)[0])
            national_feature_frame["hierarchy_state_baseline_q50"] = float(np_module.asarray(derived_national_quantiles.get(0.5), dtype=float)[0])
            national_feature_frame["hierarchy_state_baseline_q90"] = float(np_module.asarray(derived_national_quantiles.get(0.9), dtype=float)[0])
            national_feature_frame["hierarchy_state_baseline_width_80"] = float(
                max(
                    float(np_module.asarray(derived_national_quantiles.get(0.9), dtype=float)[0])
                    - float(np_module.asarray(derived_national_quantiles.get(0.1), dtype=float)[0]),
                    0.0,
                )
            )
        cluster_model_bundle = hierarchy_models.get("cluster") or {}
        national_model_bundle = hierarchy_models.get("national") or {}
        if not cluster_feature_frame.empty and cluster_model_bundle:
            cluster_X = cluster_feature_frame[hierarchy_feature_columns].to_numpy(dtype=float)
            if str(hierarchy_model_modes.get("cluster") or "direct_log") == "residual_log":
                model_cluster_quantiles = {
                    0.1: np_module.expm1(
                        np_module.log1p(cluster_feature_frame["hierarchy_state_baseline_q10"].to_numpy(dtype=float))
                        + cluster_model_bundle["lower"].predict(cluster_X)
                    ),
                    0.5: np_module.expm1(
                        np_module.log1p(cluster_feature_frame["hierarchy_state_baseline_q50"].to_numpy(dtype=float))
                        + cluster_model_bundle["median"].predict(cluster_X)
                    ),
                    0.9: np_module.expm1(
                        np_module.log1p(cluster_feature_frame["hierarchy_state_baseline_q90"].to_numpy(dtype=float))
                        + cluster_model_bundle["upper"].predict(cluster_X)
                    ),
                }
            else:
                model_cluster_quantiles = {
                    0.1: np_module.expm1(cluster_model_bundle["lower"].predict(cluster_X)),
                    0.5: np_module.expm1(cluster_model_bundle["median"].predict(cluster_X)),
                    0.9: np_module.expm1(cluster_model_bundle["upper"].predict(cluster_X)),
                }
            cluster_quantiles = geo_hierarchy_helper_cls.blend_quantiles(
                model_quantiles=model_cluster_quantiles,
                baseline_quantiles=derived_cluster_quantiles,
                blend_weight=float(resolved_blend_weights.get("cluster") or 0.0),
            )
        if not national_feature_frame.empty and national_model_bundle:
            national_X = national_feature_frame[hierarchy_feature_columns].to_numpy(dtype=float)
            model_national_quantiles = {
                0.1: np_module.asarray(np_module.expm1(national_model_bundle["lower"].predict(national_X)), dtype=float),
                0.5: np_module.asarray(np_module.expm1(national_model_bundle["median"].predict(national_X)), dtype=float),
                0.9: np_module.asarray(np_module.expm1(national_model_bundle["upper"].predict(national_X)), dtype=float),
            }
            national_quantiles = geo_hierarchy_helper_cls.blend_quantiles(
                model_quantiles=model_national_quantiles,
                baseline_quantiles=derived_national_quantiles,
                blend_weight=float(resolved_blend_weights.get("national") or 0.0),
            )
        cluster_weight = float(resolved_blend_weights.get("cluster") or 0.0)
        national_weight = float(resolved_blend_weights.get("national") or 0.0)
        if (aggregate_blend_weights or aggregate_blend_policy) and cluster_weight <= 0.0 and national_weight <= 0.0:
            reconciled_quantiles = quantile_predictions
            reconciled_meta = {
                "reconciliation_method": "state_sum_passthrough",
                "hierarchy_consistency_status": "coherent",
                "cluster_order": hierarchy_meta.get("cluster_order") or [],
                "national_quantiles": national_quantiles or {},
                "cluster_quantiles": cluster_quantiles or {},
            }
        else:
            reconciled_quantiles, reconciled_meta = geo_hierarchy_helper_cls.reconcile_quantiles(
                quantile_predictions,
                cluster_assignments=hierarchy_cluster_assignments,
                state_order=[str(value) for value in panel["bundesland"].tolist()],
                cluster_quantiles=cluster_quantiles,
                national_quantiles=national_quantiles,
                residual_history=(
                    np_module.asarray(hierarchy_meta.get("state_residual_history") or [], dtype=float)
                    if hierarchy_meta.get("state_residual_history")
                    else None
                ),
                state_weights=state_weights,
            )
        if reconciled_quantiles:
            reconciled_attribution = {
                "state": float(reconciled_meta.get("state", 1.0)),
                "cluster": float(reconciled_meta.get("cluster", 0.0)),
                "national": float(reconciled_meta.get("national", 0.0)),
            }
            quantile_predictions = reconciled_quantiles
            metadata = {
                **metadata,
                "hierarchy_driver_attribution": reconciled_attribution,
                "reconciliation_method": reconciled_meta.get("reconciliation_method") or metadata.get("reconciliation_method"),
                "hierarchy_consistency_status": reconciled_meta.get("hierarchy_consistency_status") or metadata.get("hierarchy_consistency_status"),
            }
            hierarchy_meta = {
                **hierarchy_meta,
                "aggregate_input_strategy": (
                    "dedicated_aggregate_models"
                    if cluster_model_bundle or national_model_bundle
                    else hierarchy_meta.get("aggregate_input_strategy") or "state_only"
                ),
                "aggregate_blend_weights_resolved": resolved_blend_weights,
                "aggregate_blend_weight_scope": blend_weight_scope,
                "blend_regime": blend_regime,
                "cluster_assignments": hierarchy_cluster_assignments,
                "cluster_order": reconciled_meta.get("cluster_order") or hierarchy_meta.get("cluster_order") or [],
                "national_quantiles": {
                    str(key): np_module.asarray(value, dtype=float).reshape(-1).tolist()
                    for key, value in (reconciled_meta.get("national_quantiles") or {}).items()
                },
                "cluster_quantiles": {
                    str(key): np_module.asarray(value, dtype=float).reshape(-1).tolist()
                    for key, value in (reconciled_meta.get("cluster_quantiles") or {}).items()
                },
            }

    pred_next = np_module.maximum(np_module.asarray(quantile_predictions.get(0.5), dtype=float), 0.0)
    pred_low = np_module.maximum(np_module.asarray(quantile_predictions.get(0.1, pred_next), dtype=float), 0.0)
    pred_high = np_module.maximum(np_module.asarray(quantile_predictions.get(0.9, pred_next), dtype=float), 0.0)

    action_threshold = float(metadata.get("action_threshold") or 0.6)
    quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "WATCH"}
    rollout_mode, activation_policy, sars_h7_promotion = service._effective_rollout_contract(
        virus_typ=virus_typ,
        horizon_days=horizon,
        metadata=metadata,
    )
    signal_bundle_version = metadata.get("signal_bundle_version") or signal_bundle_version_for_virus_fn(virus_typ)
    model_version = metadata.get("model_version") or service._model_version(metadata)
    calibration_version = metadata.get("calibration_version") or service._calibration_version(metadata)
    science_contract_version = str(metadata.get("science_contract_version") or SCIENCE_CONTRACT_VERSION)
    quantile_grid_version = str(metadata.get("quantile_grid_version") or QUANTILE_GRID_VERSION)
    forecast_quantiles = [
        float(value)
        for value in (
            metadata.get("forecast_quantiles")
            or list(CANONICAL_FORECAST_QUANTILES)
        )
    ]
    calibration_mode = str(
        metadata.get("calibration_mode")
        or ((metadata.get("learned_event_model") or {}).get("calibration_mode") or "raw_passthrough")
    )
    champion_model_family = str(metadata.get("model_family") or "regional_pooled_panel")
    component_model_family = str(metadata.get("component_model_family") or champion_model_family)
    ensemble_component_weights = metadata.get("ensemble_component_weights") or {champion_model_family: 1.0}
    hierarchy_driver_attribution = metadata.get("hierarchy_driver_attribution") or {"state": 1.0, "cluster": 0.0, "national": 0.0}
    reconciliation_method = str(metadata.get("reconciliation_method") or "not_reconciled")
    hierarchy_consistency_status = str(metadata.get("hierarchy_consistency_status") or "not_checked")
    aggregate_blend_weights_resolved = (
        (hierarchy_meta.get("aggregate_blend_weights_resolved") or {})
        if hierarchy_meta
        else {}
    ) or resolved_blend_weights
    aggregate_blend_weight_scope = (
        (hierarchy_meta.get("aggregate_blend_weight_scope") or {})
        if hierarchy_meta
        else {}
    ) or blend_weight_scope
    active_blend_regime = str((hierarchy_meta.get("blend_regime") if hierarchy_meta else None) or blend_regime or "")
    benchmark_evidence_reference = (
        ((metadata.get("registry_scope") or {}).get("champion") or {}).get("created_at")
        or ((metadata.get("benchmark_summary") or {}).get("primary_metric"))
    )
    benchmark_metrics = dict((metadata.get("benchmark_summary") or {}).get("metrics") or {})
    tsfm_metadata = dict(
        metadata.get("tsfm_metadata")
        or tsfm_adapter_cls.from_settings(
            enabled=bool(service.orchestrator.settings.FORECAST_ENABLE_TSFM_CHALLENGERS),
            provider=str(service.orchestrator.settings.FORECAST_TSFM_PROVIDER),
        ).metadata()
    )
    dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
    point_in_time_snapshot = artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {}
    source_coverage = dataset_manifest.get("source_coverage") or {}
    business_gate = service._business_gate(quality_gate=quality_gate, brand=brand)
    cluster_forecast_quantiles = hierarchy_meta.get("cluster_quantiles") or {}
    national_forecast_quantiles = hierarchy_meta.get("national_quantiles") or {}
    max_regional_as_of_lag_days = int(
        metadata.get("max_regional_as_of_lag_days")
        or metadata.get("regional_data_freshness_max_lag_days")
        or horizon
    )
    predictions = []
    stale_regions: list[str] = []
    for idx, row in panel.reset_index(drop=True).iterrows():
        regional_lag_days = _regional_as_of_lag_days(
            run_as_of_date=run_as_of_date,
            row_as_of_date=row["as_of_date"],
            pd_module=pd_module,
        )
        regional_data_fresh = regional_lag_days <= max_regional_as_of_lag_days
        coverage_blockers = [] if regional_data_fresh else ["regional_data_stale"]
        if not regional_data_fresh:
            stale_regions.append(str(row["bundesland"]))
        current_incidence = float(row["current_known_incidence"] or 0.0)
        expected_next = max(float(pred_next[idx]), 0.0)
        change_pct = ((expected_next - current_incidence) / max(current_incidence, 1.0)) * 100.0
        event_probability = float(calibrated_prob[idx])
        target_date = pd_module.Timestamp(
            row.get("target_date") or (pd_module.Timestamp(row["as_of_date"]) + pd_module.Timedelta(days=horizon))
        ).normalize()
        activation_candidate = bool(
            activation_policy != "watch_only"
            and quality_gate.get("overall_passed")
            and event_probability >= action_threshold
            and regional_data_fresh
        )
        prediction = {
            "bundesland": str(row["bundesland"]),
            "bundesland_name": str(row["bundesland_name"]),
            "virus_typ": virus_typ,
            "as_of_date": str(row["as_of_date"]),
            "run_as_of_date": str(run_as_of_date),
            "regional_as_of_lag_days": int(regional_lag_days),
            "regional_data_fresh": bool(regional_data_fresh),
            "max_regional_as_of_lag_days": int(max_regional_as_of_lag_days),
            "coverage_blockers": list(coverage_blockers),
            "target_date": str(target_date),
            "target_week_start": str(row["target_week_start"]),
            "target_window_days": list(target_window_days),
            "horizon_days": horizon,
            "event_definition_version": metadata.get("event_definition_version", event_definition_version),
            "event_probability": round(event_probability, 4),
            "expected_next_week_incidence": round(expected_next, 2),
            "expected_target_incidence": round(expected_next, 2),
            "prediction_interval": {
                "lower": round(max(float(pred_low[idx]), 0.0), 2),
                "upper": round(max(float(pred_high[idx]), 0.0), 2),
            },
            "current_known_incidence": round(current_incidence, 2),
            "seasonal_baseline": round(float(row["seasonal_baseline"] or 0.0), 2),
            "seasonal_mad": round(float(row["seasonal_mad"] or 0.0), 2),
            "change_pct": round(change_pct, 1),
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "evidence_tier": business_gate.get("evidence_tier"),
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "signal_bundle_version": signal_bundle_version,
            "champion_model_family": champion_model_family,
            "component_model_family": component_model_family,
            "ensemble_component_weights": ensemble_component_weights,
            "hierarchy_driver_attribution": hierarchy_driver_attribution,
            "cluster_id": hierarchy_cluster_assignments.get(str(row["bundesland"])),
            "reconciliation_method": reconciliation_method,
            "hierarchy_consistency_status": hierarchy_consistency_status,
            "aggregate_blend_weights_resolved": aggregate_blend_weights_resolved,
            "aggregate_blend_weight_scope": aggregate_blend_weight_scope,
            "blend_regime": active_blend_regime,
            "revision_policy_used": revision_policy,
            "benchmark_evidence_reference": benchmark_evidence_reference,
            "benchmark_metrics": benchmark_metrics,
            "tsfm_metadata": tsfm_metadata,
            "model_version": model_version,
            "calibration_version": calibration_version,
            "point_in_time_snapshot": point_in_time_snapshot,
            "source_coverage": source_coverage,
            "source_coverage_scope": artifact_source_coverage_scope,
            "action_threshold": round(action_threshold, 4),
            "activation_candidate": activation_candidate,
            "current_load": round(current_incidence, 2),
            "predicted_load": round(expected_next, 2),
            "trend": "steigend" if change_pct > 10 else "fallend" if change_pct < -10 else "stabil",
            "data_points": int(len(panel)),
            "last_data_date": str(as_of_date),
            "pollen_context_score": round(float(row.get("pollen_context_score") or 0.0), 2),
            "state_population_millions": round(float(row.get("state_population_millions") or 0.0), 3),
        }
        decision = service.decision_engine.evaluate(
            virus_typ=virus_typ,
            prediction=prediction,
            feature_row=row.to_dict(),
            metadata={"aggregate_metrics": metadata.get("aggregate_metrics") or {}},
        ).to_dict()
        if not regional_data_fresh:
            reason = (
                "Regional data is stale versus the shared run date, so this region stays Watch."
            )
            decision = _force_watch_for_regional_coverage(decision, reason=reason)
        prediction["decision"] = decision
        prediction["decision_label"] = str(decision.get("stage") or "watch").title()
        prediction["decision_priority_index"] = float(
            decision.get("decision_priority_index")
            or decision.get("decision_score")
            or 0.0
        )
        prediction["reason_trace"] = decision.get("reason_trace") or {}
        prediction["uncertainty_summary"] = str(decision.get("uncertainty_summary") or "")
        prediction["decision_rank"] = None
        predictions.append(prediction)

    predictions.sort(key=lambda item: float(item.get("event_probability") or 0.0), reverse=True)
    for rank, item in enumerate(predictions, start=1):
        item["rank"] = rank

    ranked_decisions = sorted(
        predictions,
        key=service._decision_priority_sort_key,
        reverse=True,
    )
    for decision_rank, item in enumerate(ranked_decisions, start=1):
        item["decision_rank"] = decision_rank

    observed_regions = sorted({str(item.get("bundesland")) for item in predictions})
    expected_regions = list(ALL_BUNDESLAENDER)
    missing_regions = [region for region in expected_regions if region not in observed_regions]

    return {
        "virus_typ": virus_typ,
        "as_of_date": str(as_of_date),
        "run_as_of_date": str(run_as_of_date),
        "horizon_days": horizon,
        "supported_horizon_days": list(supported_forecast_horizons),
        "supported_horizon_days_for_virus": support["supported_horizons"],
        "target_window_days": list(target_window_days),
        "quality_gate": quality_gate,
        "business_gate": business_gate,
        "evidence_tier": business_gate.get("evidence_tier"),
        "rollout_mode": rollout_mode,
        "activation_policy": activation_policy,
        "signal_bundle_version": signal_bundle_version,
        "champion_model_family": champion_model_family,
        "component_model_family": component_model_family,
        "ensemble_component_weights": ensemble_component_weights,
        "hierarchy_driver_attribution": hierarchy_driver_attribution,
        "hierarchy_cluster_assignments": hierarchy_cluster_assignments,
        "hierarchy_cluster_forecast_quantiles": cluster_forecast_quantiles,
        "national_forecast_quantiles": national_forecast_quantiles,
        "reconciliation_method": reconciliation_method,
        "hierarchy_consistency_status": hierarchy_consistency_status,
        "aggregate_blend_weights_resolved": aggregate_blend_weights_resolved,
        "aggregate_blend_weight_scope": aggregate_blend_weight_scope,
        "blend_regime": active_blend_regime,
        "revision_policy_used": revision_policy,
        "benchmark_evidence_reference": benchmark_evidence_reference,
        "benchmark_metrics": benchmark_metrics,
        "tsfm_metadata": tsfm_metadata,
        "model_version": model_version,
        "calibration_version": calibration_version,
        "metric_semantics_version": metadata.get("metric_semantics_version"),
        "event_definition_version": metadata.get("event_definition_version", event_definition_version),
        "science_contract_version": science_contract_version,
        "quantile_grid_version": quantile_grid_version,
        "forecast_quantiles": forecast_quantiles,
        "calibration_mode": calibration_mode,
        "calibration_evidence_mode": str(
            metadata.get("calibration_evidence_mode") or CALIBRATION_EVIDENCE_MODE
        ),
        "artifact_feature_compatibility_fills": list(artifact_feature_compatibility_fills),
        "promotion_evidence": metadata.get("promotion_evidence") or {},
        "registry_status": metadata.get("registry_status"),
        "artifact_transition_mode": artifact_transition_mode,
        "point_in_time_snapshot": point_in_time_snapshot,
        "source_coverage": source_coverage,
        "source_coverage_scope": artifact_source_coverage_scope,
        "action_threshold": round(action_threshold, 4),
        "decision_policy_version": service.decision_engine.get_config(virus_typ).version,
        "decision_summary": service._decision_summary(predictions),
        "regional_coverage": {
            "expected_regions": expected_regions,
            "observed_regions": observed_regions,
            "missing_regions": missing_regions,
            "stale_regions": sorted(set(stale_regions)),
            "complete": not missing_regions,
            "max_regional_as_of_lag_days": int(max_regional_as_of_lag_days),
        },
        "total_regions": len(predictions),
        "predictions": predictions,
        "top_5": predictions[:5],
        "top_decisions": ranked_decisions[:5],
        "sars_h7_promotion": sars_h7_promotion,
        "generated_at": utc_now_fn().isoformat(),
    }
