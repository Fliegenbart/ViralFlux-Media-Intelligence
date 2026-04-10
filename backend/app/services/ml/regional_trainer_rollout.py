from __future__ import annotations

from typing import Any

import numpy as np

from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper


def weather_vintage_metrics_delta(
    legacy_metrics: dict[str, Any],
    vintage_metrics: dict[str, Any],
) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for key in (
        "relative_wis",
        "wis",
        "crps",
        "coverage_80",
        "coverage_95",
        "brier_score",
        "ece",
        "pr_auc",
        "decision_utility",
    ):
        if key not in legacy_metrics or key not in vintage_metrics:
            continue
        deltas[key] = round(
            float(vintage_metrics.get(key) or 0.0) - float(legacy_metrics.get(key) or 0.0),
            6,
        )
    return deltas


def weather_vintage_mode_summary(
    *,
    weather_forecast_vintage_mode: str,
    dataset_manifest: dict[str, Any],
    backtest_bundle: dict[str, Any],
    selection: dict[str, Any],
    calibration_mode: str,
    json_safe_fn,
) -> dict[str, Any]:
    return {
        "weather_forecast_vintage_mode": weather_forecast_vintage_mode,
        "exogenous_feature_semantics_version": dataset_manifest.get(
            "exogenous_feature_semantics_version"
        ),
        "aggregate_metrics": json_safe_fn(backtest_bundle.get("aggregate_metrics") or {}),
        "benchmark_metrics": json_safe_fn(
            (backtest_bundle.get("benchmark_summary") or {}).get("metrics") or {}
        ),
        "quality_gate": json_safe_fn(backtest_bundle.get("quality_gate") or {}),
        "selected_tau": float(selection.get("tau") or 0.0),
        "selected_kappa": float(selection.get("kappa") or 0.0),
        "action_threshold": float(selection.get("action_threshold") or 0.0),
        "calibration_mode": str(calibration_mode or "raw_passthrough"),
        "weather_forecast_run_identity_present": bool(
            dataset_manifest.get("weather_forecast_run_identity_present")
        ),
        "weather_forecast_run_identity_source": dataset_manifest.get(
            "weather_forecast_run_identity_source"
        ),
        "weather_forecast_run_identity_quality": dataset_manifest.get(
            "weather_forecast_run_identity_quality"
        ),
    }


def build_weather_vintage_comparison(
    trainer,
    *,
    virus_typ: str,
    lookback_days: int,
    horizon_days: int,
    primary_summary: dict[str, Any],
    event_config,
    normalize_weather_forecast_vintage_mode_fn,
    weather_forecast_vintage_run_timestamp_v1,
    weather_forecast_vintage_disabled,
    target_window_for_horizon_fn,
    json_safe_fn,
) -> dict[str, Any]:
    primary_mode = normalize_weather_forecast_vintage_mode_fn(
        primary_summary.get("weather_forecast_vintage_mode")
    )
    alternate_mode = (
        weather_forecast_vintage_run_timestamp_v1
        if primary_mode != weather_forecast_vintage_run_timestamp_v1
        else weather_forecast_vintage_disabled
    )

    comparison: dict[str, Any] = {
        "enabled": True,
        "comparison_status": "ok",
        "comparison_basis": "regional_training_shadow_benchmark_v1",
        "active_training_mode": primary_mode,
        "shadow_mode": alternate_mode,
        "modes": {
            primary_mode: json_safe_fn(primary_summary),
        },
    }

    try:
        shadow_panel = trainer._build_training_panel(
            virus_typ=virus_typ,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            weather_forecast_vintage_mode=alternate_mode,
        )
        shadow_panel = trainer._prepare_horizon_panel(shadow_panel, horizon_days=horizon_days)
        if shadow_panel.empty or len(shadow_panel) < 200:
            comparison["comparison_status"] = "degraded"
            comparison["comparison_blockers"] = ["insufficient_shadow_panel_rows"]
            return comparison

        shadow_panel = shadow_panel.copy()
        shadow_panel["y_next_log"] = np.log1p(
            shadow_panel["next_week_incidence"].astype(float).clip(lower=0.0)
        )
        shadow_feature_columns = trainer._feature_columns(shadow_panel)
        shadow_hierarchy_feature_columns = GeoHierarchyHelper.hierarchy_feature_columns(
            shadow_feature_columns
        )
        shadow_ww_only_columns = trainer._ww_only_feature_columns(shadow_feature_columns)
        shadow_selection = trainer._select_event_definition(
            virus_typ=virus_typ,
            panel=shadow_panel,
            feature_columns=shadow_feature_columns,
            event_config=event_config,
        )
        shadow_tau = float(shadow_selection["tau"])
        shadow_kappa = float(shadow_selection["kappa"])
        shadow_action_threshold = float(shadow_selection["action_threshold"])
        shadow_panel["event_label"] = trainer._event_labels(
            shadow_panel,
            virus_typ=virus_typ,
            tau=shadow_tau,
            kappa=shadow_kappa,
            event_config=event_config,
        )
        shadow_backtest_bundle = trainer._build_backtest_bundle(
            virus_typ=virus_typ,
            panel=shadow_panel,
            feature_columns=shadow_feature_columns,
            hierarchy_feature_columns=shadow_hierarchy_feature_columns,
            ww_only_columns=shadow_ww_only_columns,
            tau=shadow_tau,
            kappa=shadow_kappa,
            action_threshold=shadow_action_threshold,
            horizon_days=horizon_days,
            event_config=event_config,
        )
        shadow_final_artifacts = trainer._fit_final_models(
            panel=shadow_panel,
            feature_columns=shadow_feature_columns,
            hierarchy_feature_columns=shadow_hierarchy_feature_columns,
            oof_frame=shadow_backtest_bundle["oof_frame"],
            action_threshold=shadow_action_threshold,
        )
        shadow_dataset_manifest = {
            **trainer.feature_builder.dataset_manifest(virus_typ=virus_typ, panel=shadow_panel),
            "horizon_days": int(horizon_days),
            "target_window_days": target_window_for_horizon_fn(horizon_days),
        }
        shadow_mode = normalize_weather_forecast_vintage_mode_fn(
            shadow_dataset_manifest.get("weather_forecast_vintage_mode")
        )
        shadow_calibration_mode = str(
            shadow_final_artifacts.get("calibration_mode")
            or (
                "isotonic"
                if shadow_final_artifacts.get("calibration") is not None
                else "raw_passthrough"
            )
        )
        comparison["modes"][shadow_mode] = trainer._weather_vintage_mode_summary(
            weather_forecast_vintage_mode=shadow_mode,
            dataset_manifest=shadow_dataset_manifest,
            backtest_bundle=shadow_backtest_bundle,
            selection=shadow_selection,
            calibration_mode=shadow_calibration_mode,
        )
        legacy_metrics = (
            (comparison["modes"].get(weather_forecast_vintage_disabled) or {}).get(
                "benchmark_metrics"
            )
            or {}
        )
        vintage_metrics = (
            (comparison["modes"].get(weather_forecast_vintage_run_timestamp_v1) or {}).get(
                "benchmark_metrics"
            )
            or {}
        )
        comparison["legacy_vs_vintage_metric_delta"] = trainer._weather_vintage_metrics_delta(
            legacy_metrics,
            vintage_metrics,
        )
        legacy_mode_payload = comparison["modes"].get(weather_forecast_vintage_disabled) or {}
        vintage_mode_payload = (
            comparison["modes"].get(weather_forecast_vintage_run_timestamp_v1) or {}
        )
        comparison["quality_gate_change"] = {
            "legacy_forecast_readiness": (
                (legacy_mode_payload.get("quality_gate") or {}).get("forecast_readiness")
            ),
            "vintage_forecast_readiness": (
                (vintage_mode_payload.get("quality_gate") or {}).get("forecast_readiness")
            ),
            "overall_passed_changed": bool(
                ((legacy_mode_payload.get("quality_gate") or {}).get("overall_passed"))
                != ((vintage_mode_payload.get("quality_gate") or {}).get("overall_passed"))
            ),
        }
        comparison["threshold_change"] = round(
            float(vintage_mode_payload.get("action_threshold") or 0.0)
            - float(legacy_mode_payload.get("action_threshold") or 0.0),
            6,
        )
        comparison["calibration_change"] = {
            "legacy": legacy_mode_payload.get("calibration_mode"),
            "vintage": vintage_mode_payload.get("calibration_mode"),
            "changed": str(legacy_mode_payload.get("calibration_mode") or "")
            != str(vintage_mode_payload.get("calibration_mode") or ""),
        }
        comparison["weather_vintage_run_identity_coverage"] = {
            mode: {
                "run_identity_present": bool(
                    (payload or {}).get("weather_forecast_run_identity_present")
                ),
                "coverage_ratio": (
                    1.0
                    if bool((payload or {}).get("weather_forecast_run_identity_present"))
                    else 0.0
                ),
            }
            for mode, payload in comparison["modes"].items()
        }
        return comparison
    except Exception as exc:
        comparison["comparison_status"] = "error"
        comparison["comparison_error"] = str(exc) or exc.__class__.__name__
        return comparison


def rollout_metadata(
    *,
    virus_typ: str,
    horizon_days: int,
    aggregate_metrics: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
    previous_artifact: dict[str, Any],
    rollout_mode_for_virus_fn,
    activation_policy_for_virus_fn,
    signal_bundle_version_for_virus_fn,
) -> dict[str, Any]:
    rollout_mode = rollout_mode_for_virus_fn(virus_typ, horizon_days=horizon_days)
    activation_policy = activation_policy_for_virus_fn(virus_typ, horizon_days=horizon_days)
    signal_bundle_version = signal_bundle_version_for_virus_fn(virus_typ)
    if virus_typ != "SARS-CoV-2":
        return {
            "signal_bundle_version": signal_bundle_version,
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
        }

    previous_metadata = previous_artifact.get("metadata") or {}
    previous_metrics = previous_metadata.get("aggregate_metrics") or {}
    persistence_metrics = (baseline_metrics.get("persistence") or {}).copy()
    checks = {
        "beats_previous_precision_at_top3": (
            float(aggregate_metrics.get("precision_at_top3") or 0.0)
            > float(previous_metrics.get("precision_at_top3") or 0.0)
        ),
        "beats_previous_pr_auc": (
            float(aggregate_metrics.get("pr_auc") or 0.0)
            > float(previous_metrics.get("pr_auc") or 0.0)
        ),
        "improves_previous_activation_fp_rate": (
            float(aggregate_metrics.get("activation_false_positive_rate") or 1.0)
            < float(previous_metrics.get("activation_false_positive_rate") or 1.0)
        ),
        "beats_persistence_precision_at_top3": (
            float(aggregate_metrics.get("precision_at_top3") or 0.0)
            >= float(persistence_metrics.get("precision_at_top3") or 0.0)
        ),
        "beats_persistence_pr_auc": (
            float(aggregate_metrics.get("pr_auc") or 0.0)
            >= float(persistence_metrics.get("pr_auc") or 0.0)
        ),
    }
    has_previous_candidate = bool(previous_metrics)
    overall_passed = has_previous_candidate and all(checks.values())
    return {
        "signal_bundle_version": signal_bundle_version,
        "rollout_mode": rollout_mode,
        "activation_policy": activation_policy,
        "shadow_promotion_candidate": bool(int(horizon_days) == 7),
        "shadow_evaluation": {
            "overall_passed": overall_passed,
            "has_previous_candidate": has_previous_candidate,
            "checks": checks,
            "previous_candidate_metrics": previous_metrics,
            "persistence_metrics": persistence_metrics,
            "candidate_metrics": aggregate_metrics,
        },
    }
