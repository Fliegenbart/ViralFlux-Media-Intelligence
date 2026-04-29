from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.forecast_science_contract import default_science_contract_metadata
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.regional_panel_utils import event_definition_config_for_virus
from app.services.ml.weather_forecast_vintage import WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1


def train_single_horizon(
    trainer,
    *,
    virus_typ: str,
    lookback_days: int,
    persist: bool,
    horizon_days: int,
    weather_forecast_vintage_mode: str | None = None,
    weather_vintage_comparison: bool = False,
    target_window_for_horizon_fn,
    ensure_supported_horizon_fn,
    regional_horizon_support_status_fn,
    supported_forecast_horizons,
    canonical_forecast_quantiles,
    default_metric_semantics_version,
    default_promotion_min_sample_count,
    event_definition_version,
    all_bundeslaender,
    normalize_weather_forecast_vintage_mode_fn,
    regional_model_artifact_dir_fn,
    json_safe_fn,
    utc_now_fn,
    logger,
    traceback_module,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    support = regional_horizon_support_status_fn(virus_typ, horizon)
    if not support["supported"]:
        return {
            "status": "unsupported",
            "virus_typ": virus_typ,
            "horizon_days": horizon,
            "target_window_days": target_window_for_horizon_fn(horizon),
            "supported_horizon_days_for_virus": support["supported_horizons"],
            "message": support["reason"] or f"{virus_typ} unterstützt h{horizon} operativ nicht.",
            "trained": 0,
            "failed": 0,
        }
    try:
        logger.info("Training pooled regional panel model for %s (horizon=%s)", virus_typ, horizon)
        previous_artifact = trainer.load_artifacts(virus_typ=virus_typ, horizon_days=horizon)
        panel = trainer._build_training_panel(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            horizon_days=horizon,
            weather_forecast_vintage_mode=weather_forecast_vintage_mode,
        )
        panel = trainer._prepare_horizon_panel(panel, horizon_days=horizon)
        if panel.empty or len(panel) < 200:
            return {
                "status": "error",
                "virus_typ": virus_typ,
                "horizon_days": horizon,
                "target_window_days": target_window_for_horizon_fn(horizon),
                "error": f"Insufficient pooled panel data ({len(panel)} rows) for horizon {horizon}.",
            }

        panel = panel.copy()
        panel["y_next_log"] = np.log1p(panel["next_week_incidence"].astype(float).clip(lower=0.0))
        feature_columns = trainer._feature_columns(panel)
        event_feature_columns = trainer._event_feature_columns(
            panel,
            base_feature_columns=feature_columns,
        )
        hierarchy_feature_columns = GeoHierarchyHelper.hierarchy_feature_columns(feature_columns)
        ww_only_columns = trainer._ww_only_feature_columns(feature_columns)
        event_config = event_definition_config_for_virus(virus_typ)

        selection = trainer._select_event_definition(
            virus_typ=virus_typ,
            panel=panel,
            feature_columns=event_feature_columns,
            event_config=event_config,
        )
        tau = float(selection["tau"])
        kappa = float(selection["kappa"])
        action_threshold = float(selection["action_threshold"])

        panel["event_label"] = trainer._event_labels(
            panel,
            virus_typ=virus_typ,
            tau=tau,
            kappa=kappa,
            event_config=event_config,
        )
        backtest_bundle = trainer._build_backtest_bundle(
            virus_typ=virus_typ,
            panel=panel,
            feature_columns=feature_columns,
            event_feature_columns=event_feature_columns,
            hierarchy_feature_columns=hierarchy_feature_columns,
            ww_only_columns=ww_only_columns,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            horizon_days=horizon,
            event_config=event_config,
        )
        rollout_info = trainer._rollout_metadata(
            virus_typ=virus_typ,
            horizon_days=horizon,
            aggregate_metrics=backtest_bundle["aggregate_metrics"],
            baseline_metrics=(backtest_bundle["backtest_payload"].get("baselines") or {}),
            previous_artifact=previous_artifact,
        )
        backtest_bundle["backtest_payload"].update(json_safe_fn(rollout_info))
        backtest_bundle["backtest_payload"]["benchmark_summary"] = json_safe_fn(
            backtest_bundle.get("benchmark_summary") or {}
        )
        final_artifacts = trainer._fit_final_models(
            panel=panel,
            feature_columns=feature_columns,
            event_feature_columns=event_feature_columns,
            hierarchy_feature_columns=hierarchy_feature_columns,
            oof_frame=backtest_bundle["oof_frame"],
            action_threshold=action_threshold,
        )
        calibration_mode = str(
            final_artifacts.get("calibration_mode")
            or ("isotonic" if final_artifacts.get("calibration") is not None else "raw_passthrough")
        )

        dataset_manifest = {
            **trainer.feature_builder.dataset_manifest(virus_typ=virus_typ, panel=panel),
            "horizon_days": horizon,
            "target_window_days": target_window_for_horizon_fn(horizon),
        }
        point_in_time_manifest = {
            **trainer.feature_builder.point_in_time_snapshot_manifest(virus_typ=virus_typ, panel=panel),
            "horizon_days": horizon,
            "target_window_days": target_window_for_horizon_fn(horizon),
        }
        signal_bundle_metadata = trainer.feature_builder.signal_bundle_metadata(
            virus_typ=virus_typ,
            panel=panel,
            feature_columns=feature_columns,
        )
        dataset_manifest.update(json_safe_fn(signal_bundle_metadata))
        point_in_time_manifest.update(json_safe_fn(signal_bundle_metadata))
        primary_weather_vintage_summary = trainer._weather_vintage_mode_summary(
            weather_forecast_vintage_mode=normalize_weather_forecast_vintage_mode_fn(
                dataset_manifest.get("weather_forecast_vintage_mode")
            ),
            dataset_manifest=dataset_manifest,
            backtest_bundle=backtest_bundle,
            selection=selection,
            calibration_mode=calibration_mode,
        )
        weather_vintage_mode = normalize_weather_forecast_vintage_mode_fn(
            dataset_manifest.get("weather_forecast_vintage_mode")
        )
        weather_vintage_discipline_passed = (
            weather_vintage_mode != WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1
            or bool(dataset_manifest.get("weather_forecast_run_identity_present"))
        )
        forecast_quantiles = [float(value) for value in canonical_forecast_quantiles]
        science_contract_metadata = default_science_contract_metadata(
            virus_typ=virus_typ,
            horizon_days=horizon,
            calibration_mode=calibration_mode,
            event_definition_version=event_definition_version,
            metric_semantics_version=default_metric_semantics_version,
            forecast_quantiles=forecast_quantiles,
        )
        weather_vintage_comparison_payload = (
            trainer._build_weather_vintage_comparison(
                virus_typ=virus_typ,
                lookback_days=lookback_days,
                horizon_days=horizon,
                primary_summary=primary_weather_vintage_summary,
                event_config=event_config,
            )
            if weather_vintage_comparison
            else None
        )
        if weather_vintage_comparison_payload is not None:
            backtest_bundle.setdefault("benchmark_summary", {})[
                "weather_vintage_comparison"
            ] = json_safe_fn(weather_vintage_comparison_payload)
        hierarchy_metadata = trainer._build_hierarchy_metadata(
            panel=panel,
            oof_frame=backtest_bundle["oof_frame"],
        )
        hierarchy_benchmark = (backtest_bundle.get("benchmark_summary") or {}).get("hierarchy_benchmark") or {}
        hierarchy_diagnostics = (backtest_bundle.get("benchmark_summary") or {}).get("hierarchy_diagnostics") or {}
        cluster_homogeneity = (backtest_bundle.get("benchmark_summary") or {}).get("cluster_homogeneity") or {}
        hierarchy_metadata["enabled"] = bool(hierarchy_benchmark.get("promote_reconciliation"))
        hierarchy_metadata["selection_basis"] = hierarchy_benchmark.get("selection_basis") or "benchmark_pending"
        hierarchy_metadata["benchmark_metrics"] = hierarchy_benchmark.get("comparison") or {}
        hierarchy_metadata["component_diagnostics"] = hierarchy_diagnostics
        hierarchy_metadata["cluster_homogeneity"] = cluster_homogeneity
        hierarchy_metadata["model_modes"] = final_artifacts.get("hierarchy_model_modes") or {}
        hierarchy_metadata["aggregate_blend_policy"] = {
            "cluster": ((hierarchy_diagnostics.get("cluster") or {}).get("blend_policy") or {}),
            "national": ((hierarchy_diagnostics.get("national") or {}).get("blend_policy") or {}),
        }
        policy_reference_date = (
            pd.to_datetime(panel["as_of_date"], errors="coerce").max()
            if "as_of_date" in panel.columns
            else None
        )
        cluster_blend_resolution = GeoHierarchyHelper.resolve_blend_weight_policy(
            hierarchy_metadata["aggregate_blend_policy"].get("cluster"),
            as_of_date=policy_reference_date or utc_now_fn(),
            horizon_days=horizon,
            fallback=float(((hierarchy_diagnostics.get("cluster") or {}).get("recommended_blend_weight") or 0.0)),
        )
        national_blend_resolution = GeoHierarchyHelper.resolve_blend_weight_policy(
            hierarchy_metadata["aggregate_blend_policy"].get("national"),
            as_of_date=policy_reference_date or utc_now_fn(),
            horizon_days=horizon,
            fallback=float(((hierarchy_diagnostics.get("national") or {}).get("recommended_blend_weight") or 0.0)),
        )
        hierarchy_metadata["aggregate_blend_weights"] = {
            "cluster": float(cluster_blend_resolution.get("weight") or 0.0),
            "national": float(national_blend_resolution.get("weight") or 0.0),
        }
        hierarchy_metadata["aggregate_blend_context"] = {
            "regime": cluster_blend_resolution.get("regime") or national_blend_resolution.get("regime"),
            "cluster": cluster_blend_resolution,
            "national": national_blend_resolution,
        }
        model_dir = regional_model_artifact_dir_fn(
            trainer.models_dir,
            virus_typ=virus_typ,
            horizon_days=horizon,
        )
        metadata = {
            "virus_typ": virus_typ,
            "model_family": "regional_pooled_panel",
            "champion_model_family": "regional_pooled_panel",
            "trained_at": utc_now_fn().isoformat(),
            "model_version": None,
            "calibration_version": None,
            "horizon_days": horizon,
            "target_window_days": target_window_for_horizon_fn(horizon),
            "supported_horizon_days": list(supported_forecast_horizons),
            "forecast_target_semantics": signal_bundle_metadata.get("forecast_target_semantics"),
            "target_week_start_formula": signal_bundle_metadata.get("target_week_start_formula"),
            "issue_calendar_type": signal_bundle_metadata.get("issue_calendar_type"),
            "feature_asof_policy": signal_bundle_metadata.get("feature_asof_policy"),
            "target_join_policy": signal_bundle_metadata.get("target_join_policy"),
            "metric_semantics_version": default_metric_semantics_version,
            "science_contract_version": science_contract_metadata["science_contract_version"],
            "quantile_grid_version": science_contract_metadata["quantile_grid_version"],
            "weather_forecast_vintage_mode": dataset_manifest.get("weather_forecast_vintage_mode"),
            "exogenous_feature_semantics_version": dataset_manifest.get("exogenous_feature_semantics_version"),
            "feature_columns": feature_columns,
            "event_feature_columns": event_feature_columns,
            "hierarchy_feature_columns": hierarchy_feature_columns,
            "ww_only_feature_columns": ww_only_columns,
            "active_feature_families": signal_bundle_metadata.get("active_feature_families") or [],
            "feature_family_columns": signal_bundle_metadata.get("feature_family_columns") or {},
            "source_lineage": signal_bundle_metadata.get("source_lineage") or {},
            "max_source_week": signal_bundle_metadata.get("max_source_week"),
            "max_data_age_days": signal_bundle_metadata.get("max_data_age_days"),
            "selected_tau": tau,
            "selected_kappa": kappa,
            "action_threshold": action_threshold,
            "selection_brier_score": float(selection.get("brier_score") or 0.0),
            "selection_ece": float(selection.get("ece") or 0.0),
            "event_definition_version": event_definition_version,
            "min_event_absolute_incidence": event_config.min_absolute_incidence,
            "event_definition_config": event_config.to_manifest(),
            "dataset_manifest": dataset_manifest,
            "nowcast_features_enabled": True,
            "forecast_quantiles": forecast_quantiles,
            "calibration_mode": science_contract_metadata["calibration_mode"],
            "calibration_evidence_mode": science_contract_metadata["calibration_evidence_mode"],
            "champion_scope_active": science_contract_metadata["champion_scope_active"],
            "champion_scope_reason": science_contract_metadata["champion_scope_reason"],
            "oof_calibration_only": True,
            "quantile_monotonicity_passed": forecast_quantiles == sorted(forecast_quantiles),
            "weather_vintage_discipline_passed": weather_vintage_discipline_passed,
            "signal_bundle_version": rollout_info["signal_bundle_version"],
            "rollout_mode": rollout_info["rollout_mode"],
            "activation_policy": rollout_info["activation_policy"],
            "shadow_evaluation": rollout_info.get("shadow_evaluation"),
            "quality_gate": backtest_bundle["quality_gate"],
            "aggregate_metrics": backtest_bundle["aggregate_metrics"],
            "benchmark_summary": backtest_bundle.get("benchmark_summary") or {},
            "label_selection": selection,
            "revision_policy_metadata": {
                "default_policy": "raw",
                "supported_policies": ["raw", "adjusted", "adaptive"],
                "selection_basis": "fallback_no_benchmark_evidence",
                "source_policies": {},
            },
            "learned_event_model": (
                final_artifacts["learned_event_model"].metadata()
                if final_artifacts.get("learned_event_model") is not None
                else {
                    "model_family": "learned_event_xgb",
                    "action_threshold": action_threshold,
                    "calibration_mode": calibration_mode,
                    "calibration_enabled": final_artifacts.get("calibration") is not None,
                }
            ),
            "ensemble_component_weights": {"regional_pooled_panel": 1.0},
            "hierarchy_driver_attribution": hierarchy_metadata["hierarchy_driver_attribution"],
            "reconciliation_method": hierarchy_metadata["reconciliation_method"],
            "hierarchy_consistency_status": hierarchy_metadata["hierarchy_consistency_status"],
            "hierarchy_reconciliation": hierarchy_metadata,
            "point_in_time_snapshot": {
                "snapshot_type": point_in_time_manifest.get("snapshot_type"),
                "captured_at": point_in_time_manifest.get("captured_at"),
                "unique_as_of_dates": point_in_time_manifest.get("unique_as_of_dates"),
            },
            "weather_vintage_comparison": weather_vintage_comparison_payload,
        }
        metadata["model_version"] = f"{metadata['model_family']}:h{horizon}:{metadata['trained_at']}"
        metadata["calibration_version"] = f"{calibration_mode}:h{horizon}:{metadata['trained_at']}"
        registry_scope = trainer.registry.load_scope(virus_typ=virus_typ, horizon_days=horizon)
        current_champion = registry_scope.get("champion") or {}
        current_champion_metrics = (current_champion.get("metrics") or {})
        current_champion_metadata = (current_champion.get("metadata") or {})
        promotion_candidate_metrics = {
            **(backtest_bundle.get("benchmark_summary") or {}).get("metrics", {}),
            **backtest_bundle["aggregate_metrics"],
        }
        oof_frame = backtest_bundle.get("oof_frame")
        candidate_sample_count = next(
            (
                int(item.get("samples") or 0)
                for item in ((backtest_bundle.get("benchmark_summary") or {}).get("candidate_summaries") or [])
                if str(item.get("candidate") or "") == "regional_pooled_panel"
            ),
            int(len(oof_frame)) if oof_frame is not None else 0,
        )
        promotion_evidence = trainer.registry.evaluate_promotion(
            candidate_metrics=promotion_candidate_metrics,
            champion_metrics=current_champion_metrics,
            candidate_metadata={
                "virus_typ": virus_typ,
                "horizon_days": horizon,
                "quality_gate_overall_passed": bool(backtest_bundle["quality_gate"].get("overall_passed")),
                "metric_semantics_version": metadata["metric_semantics_version"],
                "event_definition_version": metadata["event_definition_version"],
                "quantile_grid_version": metadata["quantile_grid_version"],
                "calibration_mode": metadata["calibration_mode"],
                "science_contract_version": metadata["science_contract_version"],
                "champion_scope_active": metadata["champion_scope_active"],
                "weather_vintage_discipline_passed": metadata["weather_vintage_discipline_passed"],
                "oof_calibration_only": metadata["oof_calibration_only"],
                "quantile_monotonicity_passed": metadata["quantile_monotonicity_passed"],
                "sample_count": candidate_sample_count,
            },
            champion_metadata=current_champion_metadata,
            minimum_sample_count=default_promotion_min_sample_count,
        )
        promote = bool(promotion_evidence.get("promotion_allowed"))
        registry_payload = trainer.registry.record_evaluation(
            virus_typ=virus_typ,
            horizon_days=horizon,
            model_family="regional_pooled_panel",
            metrics=promotion_candidate_metrics,
            metadata={
                "model_version": metadata["model_version"],
                "calibration_version": metadata["calibration_version"],
                "rollout_mode": metadata["rollout_mode"],
                "registry_status": "champion" if promote else "challenger",
                "metric_semantics_version": metadata["metric_semantics_version"],
                "event_definition_version": metadata["event_definition_version"],
                "quantile_grid_version": metadata["quantile_grid_version"],
                "science_contract_version": metadata["science_contract_version"],
                "calibration_mode": metadata["calibration_mode"],
                "calibration_evidence_mode": metadata["calibration_evidence_mode"],
                "champion_scope_active": metadata["champion_scope_active"],
                "champion_scope_reason": metadata["champion_scope_reason"],
                "oof_calibration_only": metadata["oof_calibration_only"],
                "weather_vintage_discipline_passed": metadata["weather_vintage_discipline_passed"],
                "quantile_monotonicity_passed": metadata["quantile_monotonicity_passed"],
                "sample_count": candidate_sample_count,
                "quality_gate_overall_passed": bool(backtest_bundle["quality_gate"].get("overall_passed")),
                "quality_gate": backtest_bundle["quality_gate"],
                "promotion_evidence": promotion_evidence,
            },
            promote=promote,
        )
        metadata["promotion_evidence"] = promotion_evidence
        metadata["registry_status"] = "champion" if promote else "challenger"
        metadata["registry_scope"] = registry_payload
        backtest_bundle["backtest_payload"].update(json_safe_fn(signal_bundle_metadata))
        backtest_bundle["backtest_payload"]["hierarchy_reconciliation"] = json_safe_fn(hierarchy_metadata)
        backtest_bundle["backtest_payload"]["promotion_evidence"] = json_safe_fn(promotion_evidence)
        if weather_vintage_comparison_payload is not None:
            backtest_bundle["backtest_payload"]["weather_vintage_comparison"] = json_safe_fn(
                weather_vintage_comparison_payload
            )

        if persist:
            trainer._persist_artifacts(
                model_dir=model_dir,
                final_artifacts=final_artifacts,
                metadata=metadata,
                backtest_payload=backtest_bundle["backtest_payload"],
                dataset_manifest=dataset_manifest,
                point_in_time_manifest=point_in_time_manifest,
            )

        per_state = (backtest_bundle["backtest_payload"].get("details") or {})
        return {
            "status": "success",
            "virus_typ": virus_typ,
            "horizon_days": horizon,
            "target_window_days": target_window_for_horizon_fn(horizon),
            "trained": len(per_state),
            "failed": max(0, len(all_bundeslaender) - len(per_state)),
            "quality_gate": backtest_bundle["quality_gate"],
            "aggregate_metrics": backtest_bundle["aggregate_metrics"],
            "rollout_mode": rollout_info["rollout_mode"],
            "activation_policy": rollout_info["activation_policy"],
            "calibration_version": metadata["calibration_version"],
            "weather_forecast_vintage_mode": metadata["weather_forecast_vintage_mode"],
            "exogenous_feature_semantics_version": metadata["exogenous_feature_semantics_version"],
            "selected_calibration_mode": calibration_mode,
            "model_dir": str(model_dir),
            "benchmark_summary": backtest_bundle.get("benchmark_summary") or {},
            "hierarchy_reconciliation": hierarchy_metadata,
            "backtest": backtest_bundle["backtest_payload"],
            "weather_vintage_comparison": weather_vintage_comparison_payload,
            "selection": selection,
            "promotion_evidence": promotion_evidence,
            "registry_status": metadata["registry_status"],
        }
    except Exception as exc:  # pragma: no cover - behavior is covered through wrapper tests
        logger.exception(
            "Training pooled regional panel model failed for %s (horizon=%s)",
            virus_typ,
            horizon,
        )
        return training_error_payload(
            virus_typ=virus_typ,
            horizon_days=horizon,
            exc=exc,
            lookback_days=lookback_days,
            target_window_for_horizon_fn=target_window_for_horizon_fn,
            all_bundeslaender=all_bundeslaender,
            traceback_module=traceback_module,
        )


def training_error_payload(
    *,
    virus_typ: str,
    horizon_days: int,
    exc: Exception,
    lookback_days: int,
    target_window_for_horizon_fn,
    all_bundeslaender,
    traceback_module,
) -> dict[str, Any]:
    error_message = str(exc) or exc.__class__.__name__
    hint = (
        "Der Backtest konnte keine gültigen Zeit-Folds aufbauen. Wahrscheinlich gibt es für diesen Scope "
        "zu wenig stabile Trainingsfenster oder in den Folds fehlt genug Klassenvielfalt für Training/Kalibrierung."
        if "no valid folds" in error_message.lower()
        else "Bitte Fold-Bildung, Datenmenge und Klassenverteilung für diesen Scope prüfen."
    )
    return {
        "status": "error",
        "virus_typ": virus_typ,
        "horizon_days": int(horizon_days),
        "target_window_days": target_window_for_horizon_fn(horizon_days),
        "lookback_days": int(lookback_days),
        "trained": 0,
        "failed": len(all_bundeslaender),
        "error": error_message,
        "error_type": exc.__class__.__name__,
        "error_stage": "train_single_horizon",
        "diagnostic_hint": hint,
        "traceback_tail": traceback_module.format_exc(limit=8).strip().splitlines()[-8:],
    }
