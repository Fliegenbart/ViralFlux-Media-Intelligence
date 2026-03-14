"""Regional Backtest Service.

Walk-forward validation for per-Bundesland forecast models.
Simulates how the regional models would have performed historically
by training on past data and predicting the next 7 days.

Output: per-Bundesland hit rate, false alarm rate, MAPE, and
a timeline of "would we have correctly activated media here?"
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.services.ml.regional_features import (
    BUNDESLAND_NAMES,
    RegionalFeatureBuilder,
)
from app.services.ml.regional_trainer import REGIONAL_META_FEATURES, REGIONAL_XGB_CONFIG

logger = logging.getLogger(__name__)

# Thresholds for event detection
EVENT_THRESHOLD_PCT = 25  # "significant increase" = +25% over baseline
ACTIVATION_PROBABILITY_THRESHOLD = 0.5  # Activate media if P(event) > 50%


class RegionalBacktester:
    """Walk-forward backtesting for regional forecast models."""

    def __init__(self, db):
        self.db = db
        self.feature_builder = RegionalFeatureBuilder(db)

    def backtest_region(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        min_train_days: int = 120,
        step_days: int = 7,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        """Walk-forward backtest for a single Bundesland.

        1. Build full feature dataset
        2. Walk forward: train on [0:t], predict [t:t+horizon]
        3. Compare prediction vs actual
        4. Compute hit rate, false alarm rate, MAPE

        Returns detailed metrics and a decision timeline.
        """
        logger.info("Backtesting %s / %s", virus_typ, bundesland)

        df = self.feature_builder.build_regional_training_data(
            virus_typ=virus_typ,
            bundesland=bundesland,
            lookback_days=1800,  # Use max available history
        )

        if df.empty or len(df) < min_train_days + horizon_days + 30:
            return {
                "bundesland": bundesland,
                "error": f"Insufficient data: {len(df)} rows (need {min_train_days + horizon_days + 30})",
            }

        available_features = [f for f in REGIONAL_META_FEATURES if f in df.columns]
        if len(available_features) < 3:
            return {"bundesland": bundesland, "error": f"Too few features: {len(available_features)}"}

        X_all = df[available_features].values
        y_all = df["y"].values
        dates = df["ds"].values

        # Walk-forward loop
        results = []
        t = min_train_days

        while t + horizon_days <= len(df):
            X_train = X_all[:t]
            y_train = y_all[:t]

            X_test = X_all[t:t + horizon_days]
            y_test = y_all[t:t + horizon_days]

            if len(X_test) < horizon_days:
                break

            # Train lightweight model on this window
            model = XGBRegressor(**REGIONAL_XGB_CONFIG["median"])
            model.fit(X_train, y_train)

            y_pred = model.predict(X_test)

            # Metrics for this window
            actual_change = ((y_test[-1] / max(y_train[-1], 1e-8)) - 1) * 100
            predicted_change = ((y_pred[-1] / max(y_train[-1], 1e-8)) - 1) * 100

            actual_event = actual_change >= EVENT_THRESHOLD_PCT
            predicted_event = predicted_change >= EVENT_THRESHOLD_PCT

            mae = float(np.mean(np.abs(y_test - y_pred)))
            mape = float(np.mean(np.abs((y_test - y_pred) / np.maximum(y_test, 1e-8))) * 100)

            results.append({
                "window_start": str(dates[t]),
                "window_end": str(dates[min(t + horizon_days - 1, len(dates) - 1)]),
                "actual_change_pct": round(actual_change, 1),
                "predicted_change_pct": round(predicted_change, 1),
                "actual_event": bool(actual_event),
                "predicted_event": bool(predicted_event),
                "hit": bool(actual_event and predicted_event),
                "false_alarm": bool(not actual_event and predicted_event),
                "miss": bool(actual_event and not predicted_event),
                "correct_rejection": bool(not actual_event and not predicted_event),
                "mae": round(mae, 2),
                "mape": round(mape, 1),
            })

            t += step_days

        if not results:
            return {"bundesland": bundesland, "error": "No valid backtest windows"}

        # Aggregate metrics
        n_windows = len(results)
        hits = sum(1 for r in results if r["hit"])
        false_alarms = sum(1 for r in results if r["false_alarm"])
        misses = sum(1 for r in results if r["miss"])
        correct_rejections = sum(1 for r in results if r["correct_rejection"])
        actual_events = hits + misses
        predicted_events = hits + false_alarms

        hit_rate = hits / max(actual_events, 1)
        false_alarm_rate = false_alarms / max(predicted_events, 1)
        precision = hits / max(predicted_events, 1)
        recall = hit_rate
        f1 = 2 * precision * recall / max(precision + recall, 1e-8)

        avg_mape = np.mean([r["mape"] for r in results])
        avg_mae = np.mean([r["mae"] for r in results])

        # Lead time: how many days before actual event did we predict it?
        lead_times = []
        for i, r in enumerate(results):
            if r["hit"] and i > 0:
                # Check previous windows for earliest prediction
                for j in range(max(0, i - 4), i):
                    if results[j]["predicted_event"]:
                        lead_days = (i - j) * step_days
                        lead_times.append(lead_days)
                        break

        avg_lead_time = np.mean(lead_times) if lead_times else 0

        return {
            "bundesland": bundesland,
            "bundesland_name": BUNDESLAND_NAMES.get(bundesland, bundesland),
            "virus_typ": virus_typ,
            "horizon_days": horizon_days,
            "step_days": step_days,
            "total_windows": n_windows,
            "metrics": {
                "hit_rate": round(hit_rate, 3),
                "false_alarm_rate": round(false_alarm_rate, 3),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1_score": round(f1, 3),
                "avg_mape": round(avg_mape, 1),
                "avg_mae": round(avg_mae, 2),
                "avg_lead_time_days": round(avg_lead_time, 1),
            },
            "confusion_matrix": {
                "hits": hits,
                "false_alarms": false_alarms,
                "misses": misses,
                "correct_rejections": correct_rejections,
                "total_actual_events": actual_events,
                "total_predicted_events": predicted_events,
            },
            "date_range": {
                "start": str(dates[0]),
                "end": str(dates[-1]),
            },
            "timeline": results[-20:],  # Last 20 windows for UI
        }

    def backtest_all_regions(
        self,
        virus_typ: str = "Influenza A",
        step_days: int = 7,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        """Run backtest for all available Bundesländer."""
        available = self.feature_builder.get_available_bundeslaender(virus_typ)
        logger.info("Running regional backtest for %s: %d Bundesländer", virus_typ, len(available))

        results = {}
        for bl_code in available:
            try:
                result = self.backtest_region(
                    virus_typ=virus_typ,
                    bundesland=bl_code,
                    step_days=step_days,
                    horizon_days=horizon_days,
                )
                results[bl_code] = result
            except Exception as exc:
                logger.error("Backtest failed for %s/%s: %s", virus_typ, bl_code, exc)
                results[bl_code] = {"bundesland": bl_code, "error": str(exc)}

        # Summary across all regions
        valid = [r for r in results.values() if "metrics" in r]
        if valid:
            avg_hit_rate = np.mean([r["metrics"]["hit_rate"] for r in valid])
            avg_false_alarm = np.mean([r["metrics"]["false_alarm_rate"] for r in valid])
            avg_f1 = np.mean([r["metrics"]["f1_score"] for r in valid])
            avg_mape = np.mean([r["metrics"]["avg_mape"] for r in valid])
        else:
            avg_hit_rate = avg_false_alarm = avg_f1 = avg_mape = 0

        # Rank by F1 score
        ranking = sorted(valid, key=lambda r: r["metrics"]["f1_score"], reverse=True)

        return {
            "virus_typ": virus_typ,
            "total_regions": len(available),
            "backtested": len(valid),
            "failed": len(available) - len(valid),
            "aggregate_metrics": {
                "avg_hit_rate": round(avg_hit_rate, 3),
                "avg_false_alarm_rate": round(avg_false_alarm, 3),
                "avg_f1_score": round(avg_f1, 3),
                "avg_mape": round(avg_mape, 1),
            },
            "ranking": [
                {
                    "bundesland": r["bundesland"],
                    "name": r.get("bundesland_name", ""),
                    "hit_rate": r["metrics"]["hit_rate"],
                    "f1_score": r["metrics"]["f1_score"],
                    "mape": r["metrics"]["avg_mape"],
                }
                for r in ranking
            ],
            "details": results,
            "generated_at": datetime.utcnow().isoformat(),
        }
