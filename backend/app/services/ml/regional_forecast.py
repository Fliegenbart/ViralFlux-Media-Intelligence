"""Regional Forecast Service.

Uses per-Bundesland trained XGBoost models to generate regional
virus wave predictions and media activation recommendations.

This is the core service that answers the business question:
"Which regions will see virus wave increases in the next 3-7 days,
and where should we activate GELO media campaigns?"
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from xgboost import XGBRegressor

from app.services.ml.regional_features import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    RegionalFeatureBuilder,
)
from app.services.ml.regional_trainer import REGIONAL_META_FEATURES, _virus_slug

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional"

# Media channel recommendations based on wave intensity
MEDIA_CHANNELS = {
    "high": ["Banner (programmatic)", "Digi-CLP (regional)", "Meta (regional)", "LinkedIn (Fachkreise)"],
    "medium": ["Banner (programmatic)", "Meta (regional)"],
    "low": ["Meta (national awareness)"],
}

# GELO product mapping by virus type
GELO_PRODUCTS = {
    "Influenza A": ["GeloMyrtol forte", "GeloRevoice"],
    "Influenza B": ["GeloMyrtol forte", "GeloRevoice"],
    "SARS-CoV-2": ["GeloMyrtol forte"],
    "RSV A": ["GeloMyrtol forte", "GeloBronchial"],
}


class RegionalForecastService:
    """Generate per-Bundesland forecasts and media activation recommendations."""

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
        """Generate forecast for a single Bundesland.

        Returns dict with:
        - current_load: current viral load
        - predicted_load: predicted load at horizon
        - change_pct: percentage change
        - event_probability: probability of significant increase (>25%)
        - confidence_interval: (lower, upper)
        - trend: "steigend" | "stabil" | "fallend"
        """
        slug = _virus_slug(virus_typ)
        bl_lower = bundesland.lower()
        model_dir = self.models_dir / slug / bl_lower

        if not (model_dir / "model_median.json").exists():
            return None

        # Load models
        model_med = XGBRegressor()
        model_lo = XGBRegressor()
        model_hi = XGBRegressor()
        model_med.load_model(str(model_dir / "model_median.json"))
        model_lo.load_model(str(model_dir / "model_lower.json"))
        model_hi.load_model(str(model_dir / "model_upper.json"))

        # Get latest features
        df = self.feature_builder.build_regional_training_data(
            virus_typ=virus_typ,
            bundesland=bundesland,
            lookback_days=60,  # Only need recent data for prediction
        )

        if df.empty or len(df) < 7:
            return None

        # Use available features
        meta = self._load_metadata(model_dir)
        features = meta.get("features", REGIONAL_META_FEATURES) if meta else REGIONAL_META_FEATURES
        available = [f for f in features if f in df.columns]
        if len(available) < 3:
            return None

        # Latest data point as input
        X_latest = df[available].iloc[-1:].values

        pred_med = float(model_med.predict(X_latest)[0])
        pred_lo = float(model_lo.predict(X_latest)[0])
        pred_hi = float(model_hi.predict(X_latest)[0])

        current_load = float(df["y"].iloc[-1])
        change_pct = ((pred_med / max(current_load, 1e-8)) - 1) * 100

        # Event probability: estimate from quantile spread
        # If lower bound is already above current + 25%, high probability
        threshold = current_load * 1.25
        if pred_lo >= threshold:
            event_prob = 0.9
        elif pred_med >= threshold:
            event_prob = 0.6 + 0.3 * ((pred_med - threshold) / max(pred_hi - pred_lo, 1e-8))
        elif pred_hi >= threshold:
            event_prob = 0.2 + 0.4 * ((pred_hi - threshold) / max(pred_hi - pred_med, 1e-8))
        else:
            event_prob = max(0.05, 0.2 * (pred_med / max(threshold, 1e-8)))

        event_prob = min(max(event_prob, 0.0), 1.0)

        if change_pct > 15:
            trend = "steigend"
        elif change_pct < -15:
            trend = "fallend"
        else:
            trend = "stabil"

        return {
            "bundesland": bundesland,
            "bundesland_name": BUNDESLAND_NAMES.get(bundesland, bundesland),
            "virus_typ": virus_typ,
            "current_load": round(current_load, 1),
            "predicted_load": round(pred_med, 1),
            "change_pct": round(change_pct, 1),
            "event_probability": round(event_prob, 3),
            "confidence_interval": {
                "lower": round(pred_lo, 1),
                "upper": round(pred_hi, 1),
            },
            "trend": trend,
            "horizon_days": horizon_days,
            "data_points": len(df),
            "last_data_date": str(df["ds"].max()),
        }

    def predict_all_regions(
        self,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        """Generate forecasts for all Bundesländer and rank by wave probability."""
        predictions = []

        for bl_code in ALL_BUNDESLAENDER:
            try:
                result = self.predict_region(virus_typ, bl_code, horizon_days)
                if result:
                    predictions.append(result)
            except Exception as exc:
                logger.warning("Prediction failed for %s/%s: %s", virus_typ, bl_code, exc)

        # Sort by event probability (highest risk first)
        predictions.sort(key=lambda x: x["event_probability"], reverse=True)

        # Add rank
        for i, pred in enumerate(predictions):
            pred["rank"] = i + 1

        return {
            "virus_typ": virus_typ,
            "horizon_days": horizon_days,
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
        """Generate regional media activation recommendations.

        This is the core output: "Where should GELO activate media this week?"

        Returns per-region recommendations with:
        - Budget allocation (proportional to event probability)
        - Channel mix (based on wave intensity)
        - Product recommendation
        - Activation timeline
        """
        forecast = self.predict_all_regions(virus_typ, horizon_days)
        predictions = forecast["predictions"]

        if not predictions:
            return {
                "virus_typ": virus_typ,
                "status": "no_data",
                "message": "Keine regionalen Prognosen verfügbar. Bitte regionale Modelle trainieren.",
                "recommendations": [],
            }

        # Classify regions by intensity
        recommendations = []
        total_event_prob = sum(p["event_probability"] for p in predictions)

        for pred in predictions:
            prob = pred["event_probability"]
            change = pred["change_pct"]

            # Intensity classification
            if prob >= 0.6 and change > 20:
                intensity = "high"
                action = "activate"
            elif prob >= 0.3 and change > 5:
                intensity = "medium"
                action = "prepare"
            elif change < -15:
                intensity = "low"
                action = "reduce"
            else:
                intensity = "low"
                action = "watch"

            # Budget allocation (proportional to event probability)
            budget_share = (prob / max(total_event_prob, 1e-8)) if action in ("activate", "prepare") else 0
            region_budget = round(weekly_budget_eur * budget_share, 2)

            # Channel recommendation
            channels = MEDIA_CHANNELS.get(intensity, MEDIA_CHANNELS["low"])

            # Product recommendation
            products = GELO_PRODUCTS.get(virus_typ, ["GeloMyrtol forte"])

            # Timeline
            if action == "activate":
                timeline = f"Sofort aktivieren — Welle in {horizon_days} Tagen erwartet"
            elif action == "prepare":
                timeline = f"In 2-3 Tagen vorbereiten — Signal wird stärker"
            elif action == "reduce":
                timeline = "Budget reduzieren — Welle klingt ab"
            else:
                timeline = "Beobachten — kein Handlungsbedarf"

            recommendations.append({
                "bundesland": pred["bundesland"],
                "bundesland_name": pred["bundesland_name"],
                "rank": pred["rank"],
                "action": action,
                "intensity": intensity,
                "event_probability": pred["event_probability"],
                "change_pct": pred["change_pct"],
                "trend": pred["trend"],
                "budget_eur": region_budget,
                "channels": channels,
                "products": products,
                "timeline": timeline,
                "current_load": pred["current_load"],
                "predicted_load": pred["predicted_load"],
            })

        activate_count = sum(1 for r in recommendations if r["action"] == "activate")
        prepare_count = sum(1 for r in recommendations if r["action"] == "prepare")
        total_allocated = sum(r["budget_eur"] for r in recommendations)

        # Generate headline
        top_regions = [r["bundesland"] for r in recommendations[:3] if r["action"] in ("activate", "prepare")]
        if top_regions:
            headline = f"{virus_typ}: Budgets in {', '.join(top_regions)} erhöhen"
        else:
            headline = f"{virus_typ}: Nationale Lage stabil — beobachten"

        return {
            "virus_typ": virus_typ,
            "horizon_days": horizon_days,
            "headline": headline,
            "summary": {
                "activate_regions": activate_count,
                "prepare_regions": prepare_count,
                "total_budget_allocated": round(total_allocated, 2),
                "weekly_budget": weekly_budget_eur,
            },
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _load_metadata(self, model_dir: Path) -> dict | None:
        meta_path = model_dir / "metadata.json"
        if not meta_path.exists():
            return None
        with open(meta_path) as f:
            return json.load(f)
