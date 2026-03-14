"""Calibrated regional forecast inference and media activation service."""

from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from app.services.media.business_validation_service import BusinessValidationService
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    TARGET_WINDOW_DAYS,
    activation_policy_for_virus,
    rollout_mode_for_virus,
    signal_bundle_version_for_virus,
)
from app.services.ml.regional_trainer import _virus_slug
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"

MEDIA_CHANNELS = {
    "high": ["Banner (programmatic)", "Digi-CLP (regional)", "Meta (regional)", "LinkedIn (Fachkreise)"],
    "medium": ["Banner (programmatic)", "Meta (regional)"],
    "low": ["Meta (national awareness)"],
}

GELO_PRODUCTS = {
    "Influenza A": ["GeloMyrtol forte", "GeloRevoice"],
    "Influenza B": ["GeloMyrtol forte", "GeloRevoice"],
    "SARS-CoV-2": ["GeloMyrtol forte"],
    "RSV A": ["GeloMyrtol forte", "GeloBronchial"],
}


class RegionalForecastService:
    """Generate calibrated pooled forecasts and gated media actions."""

    def __init__(self, db, models_dir: Path | None = None):
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.feature_builder = RegionalFeatureBuilder(db)

    def predict_region(
        self,
        virus_typ: str,
        bundesland: str,
        horizon_days: int = 7,
    ) -> dict[str, Any] | None:
        if horizon_days not in range(TARGET_WINDOW_DAYS[0], TARGET_WINDOW_DAYS[1] + 1):
            horizon_days = TARGET_WINDOW_DAYS[1]

        payload = self.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)
        return next((item for item in payload["predictions"] if item["bundesland"] == bundesland.upper()), None)

    def predict_all_regions(
        self,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        artifacts = self._load_artifacts(virus_typ)
        metadata = artifacts.get("metadata") or {}
        feature_columns = metadata.get("feature_columns") or []
        if not artifacts or not feature_columns:
            return {
                "virus_typ": virus_typ,
                "status": "no_model",
                "message": "Keine regionalen Panel-Modelle verfügbar. Bitte Training starten.",
                "predictions": [],
                "top_5": [],
                "total_regions": 0,
            }

        as_of_date = self._latest_as_of_date(virus_typ=virus_typ)
        panel = self.feature_builder.build_inference_panel(
            virus_typ=virus_typ,
            as_of_date=as_of_date.to_pydatetime(),
            lookback_days=180,
        )
        if panel.empty:
            return {
                "virus_typ": virus_typ,
                "status": "no_data",
                "message": "Keine regionalen Features für den aktuellen Datenstand verfügbar.",
                "predictions": [],
                "top_5": [],
                "total_regions": 0,
            }

        X = panel[feature_columns].to_numpy()
        classifier: XGBClassifier = artifacts["classifier"]
        calibration = artifacts.get("calibration")
        reg_median: XGBRegressor = artifacts["regressor_median"]
        reg_lower: XGBRegressor = artifacts["regressor_lower"]
        reg_upper: XGBRegressor = artifacts["regressor_upper"]

        raw_prob = classifier.predict_proba(X)[:, 1]
        calibrated_prob = self._apply_calibration(calibration, raw_prob)
        pred_next = np.expm1(reg_median.predict(X))
        pred_low = np.expm1(reg_lower.predict(X))
        pred_high = np.expm1(reg_upper.predict(X))

        action_threshold = float(metadata.get("action_threshold") or 0.6)
        quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "WATCH"}
        rollout_mode = metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ)
        activation_policy = metadata.get("activation_policy") or activation_policy_for_virus(virus_typ)
        signal_bundle_version = metadata.get("signal_bundle_version") or signal_bundle_version_for_virus(virus_typ)
        model_version = metadata.get("model_version") or self._model_version(metadata)
        calibration_version = metadata.get("calibration_version") or self._calibration_version(metadata)
        dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
        point_in_time_snapshot = artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {}
        source_coverage = dataset_manifest.get("source_coverage") or {}
        business_gate = self._business_gate(quality_gate=quality_gate)
        predictions = []
        for idx, row in panel.reset_index(drop=True).iterrows():
            current_incidence = float(row["current_known_incidence"] or 0.0)
            expected_next = max(float(pred_next[idx]), 0.0)
            change_pct = ((expected_next - current_incidence) / max(current_incidence, 1.0)) * 100.0
            event_probability = float(calibrated_prob[idx])
            activation_candidate = bool(
                activation_policy != "watch_only"
                and quality_gate.get("overall_passed")
                and event_probability >= action_threshold
            )
            predictions.append(
                {
                    "bundesland": str(row["bundesland"]),
                    "bundesland_name": str(row["bundesland_name"]),
                    "virus_typ": virus_typ,
                    "as_of_date": str(row["as_of_date"]),
                    "target_week_start": str(row["target_week_start"]),
                    "target_window_days": list(TARGET_WINDOW_DAYS),
                    "event_definition_version": metadata.get("event_definition_version", EVENT_DEFINITION_VERSION),
                    "event_probability_calibrated": round(event_probability, 4),
                    "expected_next_week_incidence": round(expected_next, 2),
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
                    "model_version": model_version,
                    "calibration_version": calibration_version,
                    "point_in_time_snapshot": point_in_time_snapshot,
                    "source_coverage": source_coverage,
                    "action_threshold": round(action_threshold, 4),
                    "activation_candidate": activation_candidate,
                    "current_load": round(current_incidence, 2),
                    "predicted_load": round(expected_next, 2),
                    "trend": "steigend" if change_pct > 10 else "fallend" if change_pct < -10 else "stabil",
                    "data_points": int(len(panel)),
                    "last_data_date": str(as_of_date),
                    "pollen_context_score": round(float(row.get("pollen_context_score") or 0.0), 2),
                }
            )

        predictions.sort(key=lambda item: item["event_probability_calibrated"], reverse=True)
        for rank, item in enumerate(predictions, start=1):
            item["rank"] = rank

        return {
            "virus_typ": virus_typ,
            "as_of_date": str(as_of_date),
            "target_window_days": list(TARGET_WINDOW_DAYS),
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "evidence_tier": business_gate.get("evidence_tier"),
            "rollout_mode": rollout_mode,
            "activation_policy": activation_policy,
            "signal_bundle_version": signal_bundle_version,
            "model_version": model_version,
            "calibration_version": calibration_version,
            "point_in_time_snapshot": point_in_time_snapshot,
            "source_coverage": source_coverage,
            "action_threshold": round(action_threshold, 4),
            "total_regions": len(predictions),
            "predictions": predictions,
            "top_5": predictions[:5],
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_media_activation(
        self,
        virus_typ: str = "Influenza A",
        weekly_budget_eur: float = 50000,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        forecast = self.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)
        predictions = forecast.get("predictions") or []
        quality_gate = forecast.get("quality_gate") or {"overall_passed": False}
        business_gate = forecast.get("business_gate") or self._business_gate(quality_gate=quality_gate)
        threshold = float(forecast.get("action_threshold") or 0.6)
        rollout_mode = str(forecast.get("rollout_mode") or rollout_mode_for_virus(virus_typ))
        activation_policy = str(forecast.get("activation_policy") or activation_policy_for_virus(virus_typ))

        if not predictions:
            return {
                "virus_typ": virus_typ,
                "status": "no_data",
                "message": "Keine regionalen Prognosen verfügbar.",
                "recommendations": [],
            }

        gated_predictions = [
            item
            for item in predictions
            if quality_gate.get("overall_passed") and float(item["event_probability_calibrated"]) >= threshold
        ]
        total_prob = sum(float(item["event_probability_calibrated"]) for item in gated_predictions)

        recommendations = []
        for item in predictions:
            probability = float(item["event_probability_calibrated"])
            change_pct = float(item["change_pct"])
            if activation_policy == "watch_only":
                action = "watch"
                intensity = "low"
            elif not business_gate.get("validated_for_budget_activation"):
                action = "watch"
                intensity = "low"
            elif not quality_gate.get("overall_passed"):
                action = "watch"
                intensity = "low"
            elif probability >= threshold and change_pct >= 20:
                action = "activate"
                intensity = "high"
            elif probability >= threshold:
                action = "prepare"
                intensity = "medium"
            else:
                action = "watch"
                intensity = "low"

            budget_share = (
                probability / max(total_prob, 1e-8)
                if (
                    action in {"activate", "prepare"}
                    and quality_gate.get("overall_passed")
                    and business_gate.get("validated_for_budget_activation")
                )
                else 0.0
            )
            budget_eur = round(weekly_budget_eur * budget_share, 2)

            if action == "activate":
                timeline = f"Sofort aktivieren — Wellenfenster in {TARGET_WINDOW_DAYS[0]}-{TARGET_WINDOW_DAYS[1]} Tagen"
            elif action == "prepare":
                timeline = "In 1-2 Tagen vorbereiten — Signal oberhalb des Aktivierungsschwellenwerts"
            else:
                timeline = (
                    "Nur beobachten — Shadow-Policy blockiert Aktivierung"
                    if activation_policy == "watch_only"
                    else "Nur beobachten — Business-Gate noch nicht validiert"
                    if not business_gate.get("validated_for_budget_activation")
                    else
                    "Nur beobachten — Quality Gate blockiert Aktivierung"
                    if not quality_gate.get("overall_passed")
                    else "Beobachten — unterhalb des validierten Aktivierungsschwellenwerts"
                )

            recommendations.append(
                {
                    "bundesland": item["bundesland"],
                    "bundesland_name": item["bundesland_name"],
                    "rank": item["rank"],
                    "action": action,
                    "intensity": intensity,
                    "event_probability": item["event_probability_calibrated"],
                    "change_pct": item["change_pct"],
                    "trend": item["trend"],
                    "budget_eur": budget_eur,
                    "channels": MEDIA_CHANNELS[intensity],
                    "products": GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
                    "timeline": timeline,
                    "current_load": item["current_known_incidence"],
                    "predicted_load": item["expected_next_week_incidence"],
                    "quality_gate": quality_gate,
                    "business_gate": business_gate,
                    "evidence_tier": business_gate.get("evidence_tier"),
                    "rollout_mode": rollout_mode,
                    "activation_policy": activation_policy,
                    "activation_threshold": threshold,
                    "as_of_date": item["as_of_date"],
                    "target_week_start": item["target_week_start"],
                }
            )

        active = [item for item in recommendations if item["action"] in {"activate", "prepare"}]
        headline_regions = [item["bundesland"] for item in active[:3]]
        headline = (
            f"{virus_typ}: Budgets in {', '.join(headline_regions)} erhöhen"
            if headline_regions
            else f"{virus_typ}: aktuell kein validierter Aktivierungs-Case"
        )

        return {
            "virus_typ": virus_typ,
            "headline": headline,
            "summary": {
                "activate_regions": sum(1 for item in recommendations if item["action"] == "activate"),
                "prepare_regions": sum(1 for item in recommendations if item["action"] == "prepare"),
                "total_budget_allocated": round(sum(item["budget_eur"] for item in recommendations), 2),
                "weekly_budget": weekly_budget_eur,
                "quality_gate": quality_gate,
                "business_gate": business_gate,
                "evidence_tier": business_gate.get("evidence_tier"),
                "rollout_mode": rollout_mode,
                "activation_policy": activation_policy,
            },
            "horizon_days": horizon_days,
            "generated_at": datetime.utcnow().isoformat(),
            "recommendations": recommendations,
        }

    def benchmark_supported_viruses(
        self,
        *,
        reference_virus: str = "Influenza A",
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        reference_metrics: dict[str, Any] | None = None
        truth_readiness = self._truth_readiness()

        for virus_typ in SUPPORTED_VIRUS_TYPES:
            artifacts = self._load_artifacts(virus_typ)
            metadata = artifacts.get("metadata") or {}
            aggregate_metrics = metadata.get("aggregate_metrics") or {}
            quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
            dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
            business_gate = self._business_gate(
                quality_gate=quality_gate,
                truth_readiness=truth_readiness,
            )

            item = {
                "virus_typ": virus_typ,
                "status": "trained" if aggregate_metrics else "no_model",
                "trained_at": metadata.get("trained_at"),
                "states": int(dataset_manifest.get("states") or 0),
                "rows": int(dataset_manifest.get("rows") or 0),
                "truth_source": dataset_manifest.get("truth_source"),
                "source_coverage": dataset_manifest.get("source_coverage") or {},
                "point_in_time_snapshot": artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {},
                "aggregate_metrics": aggregate_metrics,
                "quality_gate": quality_gate,
                "business_gate": business_gate,
                "evidence_tier": business_gate.get("evidence_tier"),
                "rollout_mode": metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ),
                "activation_policy": metadata.get("activation_policy") or activation_policy_for_virus(virus_typ),
                "signal_bundle_version": metadata.get("signal_bundle_version") or signal_bundle_version_for_virus(virus_typ),
                "model_version": metadata.get("model_version") or self._model_version(metadata),
                "calibration_version": metadata.get("calibration_version") or self._calibration_version(metadata),
                "selection": metadata.get("label_selection") or {},
                "shadow_evaluation": metadata.get("shadow_evaluation") or {},
            }
            if virus_typ == reference_virus and aggregate_metrics:
                reference_metrics = aggregate_metrics
            items.append(item)

        for item in items:
            item["delta_vs_reference"] = self._metric_delta(
                item.get("aggregate_metrics") or {},
                reference_metrics or {},
            )
            item["benchmark_score"] = self._benchmark_score(item)

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

        summary_business_gate = self._business_gate(
            quality_gate={"overall_passed": any((item.get("quality_gate") or {}).get("overall_passed") for item in ranked)},
            truth_readiness=truth_readiness,
        )
        return {
            "reference_virus": reference_virus,
            "generated_at": datetime.utcnow().isoformat(),
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

    def build_portfolio_view(
        self,
        *,
        horizon_days: int = 7,
        top_n: int = 12,
        reference_virus: str = "Influenza A",
    ) -> dict[str, Any]:
        benchmark_payload = self.benchmark_supported_viruses(reference_virus=reference_virus)
        benchmark_map = {
            item["virus_typ"]: item
            for item in benchmark_payload.get("benchmark", [])
            if item.get("status") == "trained"
        }

        opportunities: list[dict[str, Any]] = []
        virus_rollup: list[dict[str, Any]] = []
        latest_as_of_date: str | None = None

        for virus_typ in SUPPORTED_VIRUS_TYPES:
            benchmark_item = benchmark_map.get(virus_typ)
            if not benchmark_item:
                continue

            forecast = self.predict_all_regions(virus_typ=virus_typ, horizon_days=horizon_days)
            predictions = forecast.get("predictions") or []
            if not predictions:
                continue

            top_prediction = predictions[0]
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
                    "top_event_probability": top_prediction.get("event_probability_calibrated"),
                    "top_change_pct": top_prediction.get("change_pct"),
                    "products": GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
                }
            )

            for prediction in predictions:
                action, intensity = self._portfolio_action(
                    prediction=prediction,
                    benchmark_item=benchmark_item,
                )
                opportunity = {
                    "virus_typ": virus_typ,
                    "bundesland": prediction["bundesland"],
                    "bundesland_name": prediction["bundesland_name"],
                    "rank_within_virus": prediction["rank"],
                    "portfolio_action": action,
                    "portfolio_intensity": intensity,
                    "portfolio_priority_score": self._portfolio_priority_score(
                        prediction=prediction,
                        benchmark_item=benchmark_item,
                    ),
                    "event_probability_calibrated": prediction["event_probability_calibrated"],
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
                    "products": GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"]),
                    "channels": MEDIA_CHANNELS[intensity],
                    "as_of_date": prediction["as_of_date"],
                    "target_week_start": prediction["target_week_start"],
                }
                opportunities.append(opportunity)

        opportunities.sort(
            key=lambda item: (
                float(item.get("portfolio_priority_score") or 0.0),
                float(item.get("event_probability_calibrated") or 0.0),
                float(item.get("change_pct") or 0.0),
            ),
            reverse=True,
        )
        for rank, item in enumerate(opportunities, start=1):
            item["rank"] = rank

        region_rollup = self._region_rollup(opportunities)
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "reference_virus": reference_virus,
            "latest_as_of_date": latest_as_of_date,
            "summary": {
                "trained_viruses": benchmark_payload.get("trained_viruses", 0),
                "go_viruses": benchmark_payload.get("go_viruses", 0),
                "total_opportunities": len(opportunities),
                "watchlist_opportunities": sum(1 for item in opportunities if item["portfolio_action"] == "watch"),
                "priority_opportunities": sum(1 for item in opportunities if item["portfolio_action"] == "prioritize"),
                "validated_opportunities": sum(1 for item in opportunities if item["portfolio_action"] in {"activate", "prepare"}),
            },
            "business_gate": benchmark_payload.get("business_gate") or self._business_gate(quality_gate={"overall_passed": False}),
            "evidence_tier": benchmark_payload.get("evidence_tier"),
            "benchmark": benchmark_payload.get("benchmark", []),
            "virus_rollup": virus_rollup,
            "region_rollup": region_rollup,
            "top_opportunities": opportunities[: max(int(top_n), 1)],
        }

    def get_validation_summary(
        self,
        *,
        virus_typ: str = "Influenza A",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        artifacts = self._load_artifacts(virus_typ)
        metadata = artifacts.get("metadata") or {}
        quality_gate = metadata.get("quality_gate") or {"overall_passed": False, "forecast_readiness": "NO_MODEL"}
        business_gate = self._business_gate(
            quality_gate=quality_gate,
            brand=brand,
        )
        dataset_manifest = artifacts.get("dataset_manifest") or metadata.get("dataset_manifest") or {}
        return {
            "virus_typ": virus_typ,
            "brand": str(brand or "gelo").strip().lower(),
            "generated_at": datetime.utcnow().isoformat(),
            "quality_gate": quality_gate,
            "business_gate": business_gate,
            "operator_context": business_gate.get("operator_context"),
            "evidence_tier": business_gate.get("evidence_tier"),
            "model_version": metadata.get("model_version") or self._model_version(metadata),
            "calibration_version": metadata.get("calibration_version") or self._calibration_version(metadata),
            "point_in_time_snapshot": artifacts.get("point_in_time_snapshot") or metadata.get("point_in_time_snapshot") or {},
            "source_coverage": dataset_manifest.get("source_coverage") or {},
            "signal_bundle_version": metadata.get("signal_bundle_version") or signal_bundle_version_for_virus(virus_typ),
            "rollout_mode": metadata.get("rollout_mode") or rollout_mode_for_virus(virus_typ),
            "activation_policy": metadata.get("activation_policy") or activation_policy_for_virus(virus_typ),
            "aggregate_metrics": metadata.get("aggregate_metrics") or {},
        }

    def _load_artifacts(self, virus_typ: str) -> dict[str, Any]:
        model_dir = self.models_dir / _virus_slug(virus_typ)
        required_paths = {
            "classifier": model_dir / "classifier.json",
            "regressor_median": model_dir / "regressor_median.json",
            "regressor_lower": model_dir / "regressor_lower.json",
            "regressor_upper": model_dir / "regressor_upper.json",
            "calibration": model_dir / "calibration.pkl",
            "metadata": model_dir / "metadata.json",
        }
        if not all(path.exists() for path in required_paths.values()):
            return {}

        classifier = XGBClassifier()
        classifier.load_model(str(required_paths["classifier"]))
        regressor_median = XGBRegressor()
        regressor_median.load_model(str(required_paths["regressor_median"]))
        regressor_lower = XGBRegressor()
        regressor_lower.load_model(str(required_paths["regressor_lower"]))
        regressor_upper = XGBRegressor()
        regressor_upper.load_model(str(required_paths["regressor_upper"]))
        with open(required_paths["calibration"], "rb") as handle:
            calibration = pickle.load(handle)
        metadata = json.loads(required_paths["metadata"].read_text())
        dataset_manifest_path = model_dir / "dataset_manifest.json"
        point_in_time_path = model_dir / "point_in_time_snapshot.json"
        return {
            "classifier": classifier,
            "regressor_median": regressor_median,
            "regressor_lower": regressor_lower,
            "regressor_upper": regressor_upper,
            "calibration": calibration,
            "metadata": metadata,
            "dataset_manifest": json.loads(dataset_manifest_path.read_text()) if dataset_manifest_path.exists() else None,
            "point_in_time_snapshot": json.loads(point_in_time_path.read_text()) if point_in_time_path.exists() else None,
        }

    @staticmethod
    def _apply_calibration(calibration: Any, raw_probabilities: np.ndarray) -> np.ndarray:
        if calibration is None:
            return np.clip(raw_probabilities.astype(float), 0.001, 0.999)
        return np.clip(calibration.predict(raw_probabilities.astype(float)), 0.001, 0.999)

    def _latest_as_of_date(self, virus_typ: str) -> pd.Timestamp:
        return self.feature_builder.latest_available_as_of_date(virus_typ=virus_typ)

    @staticmethod
    def _metric_delta(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, float]:
        delta: dict[str, float] = {}
        for metric in (
            "precision_at_top3",
            "precision_at_top5",
            "pr_auc",
            "brier_score",
            "ece",
            "activation_false_positive_rate",
        ):
            if metric in candidate and metric in reference:
                delta[metric] = round(float(candidate[metric]) - float(reference[metric]), 6)
        return delta

    @staticmethod
    def _benchmark_score(item: dict[str, Any]) -> float:
        metrics = item.get("aggregate_metrics") or {}
        quality_gate = item.get("quality_gate") or {}
        precision = float(metrics.get("precision_at_top3") or 0.0)
        pr_auc = float(metrics.get("pr_auc") or 0.0)
        ece = float(metrics.get("ece") or 1.0)
        fp_rate = float(metrics.get("activation_false_positive_rate") or 1.0)
        score = (
            precision * 0.4
            + pr_auc * 0.35
            + max(0.0, 1.0 - min(ece, 1.0)) * 0.15
            + max(0.0, 1.0 - min(fp_rate, 1.0)) * 0.10
        )
        if quality_gate.get("overall_passed"):
            score += 0.1
        return round(score * 100.0, 2)

    def _portfolio_priority_score(
        self,
        *,
        prediction: dict[str, Any],
        benchmark_item: dict[str, Any],
    ) -> float:
        probability = float(prediction.get("event_probability_calibrated") or 0.0)
        change_pct = float(prediction.get("change_pct") or 0.0)
        benchmark_score = float(benchmark_item.get("benchmark_score") or 0.0) / 100.0
        quality_gate = prediction.get("quality_gate") or {}
        activation_policy = str(prediction.get("activation_policy") or "quality_gate")
        business_gate = prediction.get("business_gate") or benchmark_item.get("business_gate") or {}
        if activation_policy == "watch_only":
            readiness_multiplier = 0.78
        elif not business_gate.get("validated_for_budget_activation"):
            readiness_multiplier = 0.84 if quality_gate.get("overall_passed") else 0.68
        else:
            readiness_multiplier = 1.0 if quality_gate.get("overall_passed") else 0.72
        momentum_multiplier = 1.0 + min(max(change_pct, 0.0), 80.0) / 200.0
        return round(probability * max(benchmark_score, 0.05) * readiness_multiplier * momentum_multiplier * 100.0, 2)

    def _portfolio_action(
        self,
        *,
        prediction: dict[str, Any],
        benchmark_item: dict[str, Any],
    ) -> tuple[str, str]:
        probability = float(prediction.get("event_probability_calibrated") or 0.0)
        change_pct = float(prediction.get("change_pct") or 0.0)
        threshold = float(prediction.get("action_threshold") or 0.6)
        quality_gate = prediction.get("quality_gate") or {}
        activation_policy = str(prediction.get("activation_policy") or "quality_gate")
        business_gate = prediction.get("business_gate") or benchmark_item.get("business_gate") or {}

        if activation_policy == "watch_only":
            if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
                return "prioritize", "medium"
            return "watch", "low"

        if not business_gate.get("validated_for_budget_activation"):
            if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
                return "prioritize", "medium"
            return "watch", "low"
        if quality_gate.get("overall_passed") and probability >= threshold and change_pct >= 20:
            return "activate", "high"
        if quality_gate.get("overall_passed") and probability >= threshold:
            return "prepare", "medium"
        if float(benchmark_item.get("benchmark_score") or 0.0) >= 35.0 and probability >= max(0.45, threshold * 0.8):
            return "prioritize", "medium"
        return "watch", "low"

    @staticmethod
    def _region_rollup(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in opportunities:
            grouped.setdefault(item["bundesland"], []).append(item)

        region_rollup: list[dict[str, Any]] = []
        for bundesland, items in grouped.items():
            ranked_items = sorted(
                items,
                key=lambda item: float(item.get("portfolio_priority_score") or 0.0),
                reverse=True,
            )
            leader = ranked_items[0]
            region_rollup.append(
                {
                    "bundesland": bundesland,
                    "bundesland_name": leader["bundesland_name"],
                    "leading_virus": leader["virus_typ"],
                    "leading_probability": leader["event_probability_calibrated"],
                    "leading_priority_score": leader["portfolio_priority_score"],
                    "top_signals": [
                        {
                            "virus_typ": item["virus_typ"],
                            "portfolio_action": item["portfolio_action"],
                            "portfolio_priority_score": item["portfolio_priority_score"],
                            "event_probability_calibrated": item["event_probability_calibrated"],
                        }
                        for item in ranked_items[:3]
                    ],
                }
            )

        region_rollup.sort(
            key=lambda item: float(item.get("leading_priority_score") or 0.0),
            reverse=True,
        )
        return region_rollup

    def _truth_readiness(self, *, brand: str = "gelo") -> dict[str, Any]:
        if self.db is None:
            return {
                "coverage_weeks": 0,
                "truth_readiness": "noch_nicht_angeschlossen",
                "truth_ready": False,
                "expected_units_lift_enabled": False,
                "expected_revenue_lift_enabled": False,
            }
        return ForecastDecisionService(self.db).get_truth_readiness(brand=brand)

    def _business_gate(
        self,
        *,
        quality_gate: dict[str, Any],
        truth_readiness: dict[str, Any] | None = None,
        brand: str = "gelo",
    ) -> dict[str, Any]:
        forecast_ready = bool((quality_gate or {}).get("overall_passed"))
        if self.db is None:
            truth = truth_readiness or self._truth_readiness(brand=brand)
            return {
                "truth_readiness": str(truth.get("truth_readiness") or "noch_nicht_angeschlossen"),
                "truth_ready": bool(truth.get("truth_ready")),
                "coverage_weeks": int(truth.get("coverage_weeks") or 0),
                "expected_units_lift_enabled": False,
                "expected_revenue_lift_enabled": False,
                "action_class": "watch_only" if not forecast_ready else "market_watch",
                "validation_status": "pending_truth_connection" if int(truth.get("coverage_weeks") or 0) <= 0 else "building_truth_layer",
                "decision_scope": "decision_support_only",
                "validated_for_budget_activation": False,
                "evidence_tier": "no_truth" if int(truth.get("coverage_weeks") or 0) <= 0 else "observational",
            }

        validation = BusinessValidationService(self.db).evaluate(
            brand=brand,
            truth_coverage=truth_readiness,
        )
        validation["quality_gate_passed"] = forecast_ready
        return validation

    @staticmethod
    def _model_version(metadata: dict[str, Any]) -> str:
        model_family = str(metadata.get("model_family") or "regional_pooled_panel")
        trained_at = str(metadata.get("trained_at") or "unversioned")
        return f"{model_family}:{trained_at}"

    @staticmethod
    def _calibration_version(metadata: dict[str, Any]) -> str:
        trained_at = str(metadata.get("trained_at") or "unversioned")
        return f"isotonic:{trained_at}"
