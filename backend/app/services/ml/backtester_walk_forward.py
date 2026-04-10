from __future__ import annotations

from datetime import timedelta
import math
from typing import Optional

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.services.ml.forecast_contracts import (
    HEURISTIC_EVENT_SCORE_SOURCE,
    heuristic_event_score_from_forecast,
)


def seasonal_naive_baseline(train_df: pd.DataFrame, target_week: int, target_month: int) -> float:
    """Seasonal Baseline: Median der gleichen ISO-Woche."""
    same_week = train_df[train_df["iso_week"] == target_week]
    if not same_week.empty:
        return float(same_week["menge"].median())

    same_month = train_df[train_df["month"] == target_month]
    if not same_month.empty:
        return float(same_month["menge"].median())

    return float(train_df["menge"].median())


def run_walk_forward_market_backtest(
    service,
    *,
    target_df: pd.DataFrame,
    virus_typ: str,
    horizon_days: int,
    min_train_points: int,
    delay_rules: Optional[dict[str, int]] = None,
    exclude_are: bool = False,
    target_disease: Optional[str] = None,
) -> dict:
    """Walk-forward Backtest mit XGBoost auf autoregressiven Features."""
    df = target_df.copy()
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
    if "available_time" in df.columns:
        df["available_time"] = pd.to_datetime(df["available_time"], errors="coerce")
    else:
        df["available_time"] = pd.NaT
    df["available_time"] = df["available_time"].fillna(df["datum"])
    df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)
    if df.empty:
        return {"error": "Keine validen Zielwerte für Walk-forward Backtest verfügbar."}

    isocal = df["datum"].dt.isocalendar()
    df["iso_week"] = isocal.week.astype(int)
    df["month"] = df["datum"].dt.month.astype(int)

    feature_cols = list(service.XGBOOST_SURVSTAT_FEATURES)
    folds: list[dict] = []
    importance_accumulator: list[np.ndarray] = []
    xgb_fold_count = 0

    for _, row in df.iterrows():
        target_time = row["datum"]
        target_value = float(row["menge"])
        target_week = int(row["iso_week"])
        target_month = int(row["month"])
        forecast_time = target_time - timedelta(days=max(0, int(horizon_days)))

        if service.strict_vintage_mode:
            train_target_df = df[df["available_time"] <= forecast_time].copy()
        else:
            train_target_df = df[df["datum"] <= forecast_time].copy()
        if len(train_target_df) < min_train_points:
            continue

        train_sorted = train_target_df[["datum", "menge"]].sort_values("datum").reset_index(drop=True)
        X_train, y_train = service._build_survstat_ar_training_data(train_sorted)
        if len(X_train) < 10:
            continue

        n_train = len(X_train)
        xgb_fold_count += 1
        model = XGBRegressor(
            n_estimators=min(200, max(50, n_train * 2)),
            max_depth=4 if n_train >= 60 else 3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            random_state=42,
            verbosity=0,
        )
        model.fit(X_train, y_train)
        importance_accumulator.append(model.feature_importances_)

        series = train_sorted["menge"].reset_index(drop=True)
        test_feat = service._build_survstat_ar_row(
            series, len(series), target_time,
        )
        X_test = np.array([[test_feat.get(c, 0.0) for c in service.XGBOOST_SURVSTAT_FEATURES]])
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

        y_hat = max(0.0, float(model.predict(X_test)[0]))
        y_max = float(y_train.max())
        y_hat = min(y_hat, y_max * 2.5)

        baseline_persistence = float(train_target_df.iloc[-1]["menge"])
        seasonal_bl = seasonal_naive_baseline(
            train_target_df,
            target_week=target_week,
            target_month=target_month,
        )
        decision_window = train_target_df[
            train_target_df["datum"] >= (forecast_time - timedelta(days=service.DECISION_BASELINE_WINDOW_DAYS))
        ]
        if decision_window.empty:
            decision_window = train_target_df
        decision_baseline = float(decision_window["menge"].median()) if not decision_window.empty else seasonal_bl
        heuristic_event_score = heuristic_event_score_from_forecast(
            prediction=y_hat,
            baseline=decision_baseline if decision_baseline > 0 else max(seasonal_bl, 1.0),
            lower_bound=max(0.0, y_hat - 1.28 * max(float(np.std(y_train)), 1.0)),
            upper_bound=y_hat + 1.28 * max(float(np.std(y_train)), 1.0),
            threshold_pct=float(service.DECISION_EVENT_THRESHOLD_PCT),
        )

        amelag_val = service._amelag_raw_at_date(target_time, virus_typ)

        folds.append({
            "forecast_time": forecast_time,
            "target_time": target_time,
            "real_qty": target_value,
            "predicted_qty": y_hat,
            "predicted_qty_level": y_hat,
            "predicted_qty_lead": y_hat,
            "predicted_qty_decision": y_hat,
            "p_event": None,
            "event_probability": None,
            "heuristic_event_score": heuristic_event_score,
            "probability_source": HEURISTIC_EVENT_SCORE_SOURCE,
            "selected_variant": "xgboost",
            "baseline_persistence": baseline_persistence,
            "baseline_seasonal": seasonal_bl,
            "decision_baseline": round(decision_baseline, 4),
            "amelag_viruslast": amelag_val,
        })

    if not folds:
        return {
            "error": (
                "Walk-forward erzeugte keine validen Folds. "
                f"Erhöhe days_back oder reduziere min_train_points (aktuell {min_train_points})."
            )
        }

    pred_df = pd.DataFrame(folds).sort_values("target_time").reset_index(drop=True)
    y_true = pred_df["real_qty"].to_numpy(dtype=float)
    y_hat = pred_df["predicted_qty"].to_numpy(dtype=float)
    y_persistence = pred_df["baseline_persistence"].to_numpy(dtype=float)
    y_seasonal = pred_df["baseline_seasonal"].to_numpy(dtype=float)

    model_metrics = service._compute_forecast_metrics(y_true, y_hat)
    persistence_metrics = service._compute_forecast_metrics(y_true, y_persistence)
    seasonal_metrics = service._compute_forecast_metrics(y_true, y_seasonal)

    model_mae = max(model_metrics["mae"], 1e-9)
    pers_mae = max(persistence_metrics["mae"], 1e-9)
    seas_mae = max(seasonal_metrics["mae"], 1e-9)

    imp_cols = feature_cols
    if importance_accumulator:
        last_imp = importance_accumulator[-1]
        total = float(last_imp.sum())
        if total > 0:
            optimized_weights = {
                col: round(float(last_imp[i] / total), 3)
                for i, col in enumerate(imp_cols[:len(last_imp)])
            }
        else:
            optimized_weights = dict(service.DEFAULT_WEIGHTS)
    else:
        optimized_weights = dict(service.DEFAULT_WEIGHTS)

    forecast_weeks = 6
    residuals = y_true - y_hat
    residual_std = (
        float(np.std(residuals)) if len(residuals) > 2
        else float(np.std(y_true) * 0.3)
    )
    last_target_time = pred_df["target_time"].max()
    rolling_series = list(df.loc[df["datum"] <= last_target_time, "menge"].values)
    forecast_chart: list[dict] = []

    try:
        for w in range(1, forecast_weeks + 1):
            future_target = last_target_time + timedelta(weeks=w)
            future_forecast = future_target - timedelta(days=max(0, int(horizon_days)))

            fc_series = pd.Series(rolling_series, dtype=float)
            fc_feat = service._build_survstat_ar_row(
                fc_series, len(fc_series), future_target,
            )
            X_fc = np.array([[fc_feat.get(c, 0.0) for c in service.XGBOOST_SURVSTAT_FEATURES]])
            X_fc = np.nan_to_num(X_fc, nan=0.0, posinf=0.0, neginf=0.0)
            y_fc = max(0.0, float(model.predict(X_fc)[0]))

            hf = math.sqrt(w)
            ci_80 = 1.28 * residual_std * hf
            ci_95 = 1.96 * residual_std * hf

            forecast_chart.append({
                "date": future_target.strftime("%Y-%m-%d"),
                "issue_date": future_forecast.strftime("%Y-%m-%d"),
                "target_date": future_target.strftime("%Y-%m-%d"),
                "forecast_qty": round(y_fc, 3),
                "ci_80_lower": round(max(0, y_fc - ci_80), 3),
                "ci_80_upper": round(y_fc + ci_80, 3),
                "ci_95_lower": round(max(0, y_fc - ci_95), 3),
                "ci_95_upper": round(y_fc + ci_95, 3),
                "is_forecast": True,
            })
            rolling_series.append(y_fc)
    except Exception:
        pass

    forecast_records = [
        {
            "issue_date": row["forecast_time"].strftime("%Y-%m-%d"),
            "target_date": row["target_time"].strftime("%Y-%m-%d"),
            "y_hat": round(float(row["predicted_qty"]), 3),
            "y_true": float(row["real_qty"]),
            "baseline_persistence": float(row["baseline_persistence"]),
            "baseline_seasonal": float(row["baseline_seasonal"]),
            "decision_baseline": float(row.get("decision_baseline") or 0.0),
            "horizon_days": int(horizon_days),
            "lead_days": int((row["target_time"] - row["forecast_time"]).days),
        }
        for _, row in pred_df.iterrows()
    ]
    decision_forecast_records = [
        {
            "issue_date": row["forecast_time"].strftime("%Y-%m-%d"),
            "target_date": row["target_time"].strftime("%Y-%m-%d"),
            "y_hat": round(float(row.get("predicted_qty_decision", row["predicted_qty"])), 3),
            "y_hat_level": round(float(row.get("predicted_qty_level", row["predicted_qty"])), 3),
            "y_hat_lead": round(float(row.get("predicted_qty_lead", row["predicted_qty"])), 3),
            "p_event": (
                round(float(row["event_probability"]), 4)
                if row.get("event_probability") is not None
                else None
            ),
            "event_probability": (
                round(float(row["event_probability"]), 4)
                if row.get("event_probability") is not None
                else None
            ),
            "heuristic_event_score": (
                round(float(row["heuristic_event_score"]), 4)
                if row.get("heuristic_event_score") is not None
                else None
            ),
            "probability_source": str(row.get("probability_source") or HEURISTIC_EVENT_SCORE_SOURCE),
            "selected_variant": str(row.get("selected_variant") or "level"),
            "y_true": float(row["real_qty"]),
            "baseline_persistence": float(row["baseline_persistence"]),
            "baseline_seasonal": float(row["baseline_seasonal"]),
            "decision_baseline": float(row.get("decision_baseline") or 0.0),
            "horizon_days": int(horizon_days),
            "lead_days": int((row["target_time"] - row["forecast_time"]).days),
        }
        for _, row in pred_df.iterrows()
    ]

    ci_80_half = 1.28 * residual_std
    ci_95_half = 1.96 * residual_std
    historical_chart = [
        {
            "date": row["target_time"].strftime("%Y-%m-%d"),
            "issue_date": row["forecast_time"].strftime("%Y-%m-%d"),
            "target_date": row["target_time"].strftime("%Y-%m-%d"),
            "real_qty": float(row["real_qty"]),
            "predicted_qty": round(float(row["predicted_qty"]), 3),
            "ci_80_lower": round(max(0.0, float(row["predicted_qty"]) - ci_80_half), 3),
            "ci_80_upper": round(float(row["predicted_qty"]) + ci_80_half, 3),
            "ci_95_lower": round(max(0.0, float(row["predicted_qty"]) - ci_95_half), 3),
            "ci_95_upper": round(float(row["predicted_qty"]) + ci_95_half, 3),
            "amelag_viruslast": round(float(row["amelag_viruslast"]), 3) if row.get("amelag_viruslast") is not None else None,
            "is_forecast": False,
        }
        for _, row in pred_df.iterrows()
    ]

    if historical_chart and forecast_chart:
        historical_chart[-1]["forecast_qty"] = historical_chart[-1]["predicted_qty"]

    chart_data = historical_chart + forecast_chart
    vintage_records = decision_forecast_records or forecast_records
    vintage_metrics = service._compute_vintage_metrics(
        forecast_records=vintage_records,
        configured_horizon_days=int(horizon_days),
    )
    decision_metrics = service._compute_decision_metrics(
        forecast_records=vintage_records,
        threshold_pct=float(service.DECISION_EVENT_THRESHOLD_PCT),
        vintage_metrics=vintage_metrics,
    )
    interval_coverage = service._compute_interval_coverage_metrics(historical_chart)
    event_calibration = service._compute_event_calibration_metrics(
        decision_forecast_records,
        threshold_pct=float(service.DECISION_EVENT_THRESHOLD_PCT),
    )
    timing_metrics = service._compute_timing_metrics(
        forecast_records=vintage_records,
        horizon_days=int(horizon_days),
    )
    quality_gate = service._build_quality_gate(
        decision_metrics,
        timing_metrics,
        improvement_vs_baselines={
            "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
            "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
        },
        interval_coverage=interval_coverage,
        event_calibration=None if event_calibration.get("calibration_skipped") else event_calibration,
    )

    return {
        "metrics": {
            **model_metrics,
            "data_points": int(len(pred_df)),
            "date_range": {
                "start": pred_df["target_time"].min().strftime("%Y-%m-%d"),
                "end": pred_df["target_time"].max().strftime("%Y-%m-%d"),
            },
        },
        "baseline_metrics": {
            "persistence": persistence_metrics,
            "seasonal_naive": seasonal_metrics,
        },
        "improvement_vs_baselines": {
            "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
            "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
        },
        "optimized_weights": optimized_weights,
        "default_weights": dict(service.DEFAULT_WEIGHTS),
        "model_type": "XGBoost",
        "xgb_folds": xgb_fold_count,
        "feature_count": len(imp_cols) if importance_accumulator else len(feature_cols),
        "feature_names": imp_cols if importance_accumulator else feature_cols,
        "chart_data": chart_data,
        "forecast_records": forecast_records,
        "decision_forecast_records": decision_forecast_records,
        "vintage_metrics": vintage_metrics,
        "decision_metrics": decision_metrics,
        "interval_coverage": interval_coverage,
        "event_calibration": event_calibration,
        "timing_metrics": timing_metrics,
        "quality_gate": quality_gate,
        "forecast_weeks": len(forecast_chart),
        "residual_std": round(residual_std, 4),
        "walk_forward": {
            "enabled": True,
            "folds": int(len(pred_df)),
            "horizon_days": int(horizon_days),
            "min_train_points": int(min_train_points),
            "strict_vintage_mode": bool(service.strict_vintage_mode),
            "delay_rules_days": dict(service.DEFAULT_DELAY_RULES_DAYS | (delay_rules or {})),
        },
    }
