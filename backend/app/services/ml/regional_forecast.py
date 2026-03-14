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

from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    TARGET_WINDOW_DAYS,
)
from app.services.ml.regional_trainer import _virus_slug

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
        predictions = []
        for idx, row in panel.reset_index(drop=True).iterrows():
            current_incidence = float(row["current_known_incidence"] or 0.0)
            expected_next = max(float(pred_next[idx]), 0.0)
            change_pct = ((expected_next - current_incidence) / max(current_incidence, 1.0)) * 100.0
            event_probability = float(calibrated_prob[idx])
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
                    "action_threshold": round(action_threshold, 4),
                    "activation_candidate": bool(quality_gate.get("overall_passed") and event_probability >= action_threshold),
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
        threshold = float(forecast.get("action_threshold") or 0.6)

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
            if not quality_gate.get("overall_passed"):
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
                if action in {"activate", "prepare"} and quality_gate.get("overall_passed")
                else 0.0
            )
            budget_eur = round(weekly_budget_eur * budget_share, 2)

            if action == "activate":
                timeline = f"Sofort aktivieren — Wellenfenster in {TARGET_WINDOW_DAYS[0]}-{TARGET_WINDOW_DAYS[1]} Tagen"
            elif action == "prepare":
                timeline = "In 1-2 Tagen vorbereiten — Signal oberhalb des Aktivierungsschwellenwerts"
            else:
                timeline = (
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
            },
            "horizon_days": horizon_days,
            "generated_at": datetime.utcnow().isoformat(),
            "recommendations": recommendations,
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
        return {
            "classifier": classifier,
            "regressor_median": regressor_median,
            "regressor_lower": regressor_lower,
            "regressor_upper": regressor_upper,
            "calibration": calibration,
            "metadata": metadata,
        }

    @staticmethod
    def _apply_calibration(calibration: Any, raw_probabilities: np.ndarray) -> np.ndarray:
        if calibration is None:
            return np.clip(raw_probabilities.astype(float), 0.001, 0.999)
        return np.clip(calibration.predict(raw_probabilities.astype(float)), 0.001, 0.999)

    def _latest_as_of_date(self, virus_typ: str) -> pd.Timestamp:
        return self.feature_builder.latest_available_as_of_date(virus_typ=virus_typ)
