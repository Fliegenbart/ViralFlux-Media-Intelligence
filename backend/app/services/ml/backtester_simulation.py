from __future__ import annotations

from datetime import timedelta
import logging
import math
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def simulate_rows_from_target(
    service,
    *,
    target_df: pd.DataFrame,
    virus_typ: str,
    horizon_days: int = 0,
    delay_rules: Optional[dict[str, int]] = None,
    enhanced: bool = False,
    target_disease: Optional[str] = None,
) -> list[dict]:
    """Berechnet Simulationszeilen aus Zielwerten ohne Future-Leak."""
    if target_df.empty:
        return []

    df = target_df.copy()
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
    df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)

    menge_values = df["menge"].tolist()
    df["_iso_week"] = df["datum"].apply(lambda d: d.isocalendar()[1])
    seasonal_baselines: dict[int, float] = {}
    for wk in range(1, 54):
        vals = df[df["_iso_week"] == wk]["menge"].tolist()
        seasonal_baselines[wk] = float(np.median(vals)) if vals else 0.0

    simulation_rows = []
    for idx, row in df.iterrows():
        target_date = row["datum"]
        sim_date = target_date - timedelta(days=max(0, int(horizon_days)))
        real_qty = float(row["menge"])
        baseline = seasonal_baselines.get(int(row["_iso_week"]), 0.0)

        try:
            scores = service._compute_sub_scores_at_date(
                sim_date,
                virus_typ,
                delay_rules=delay_rules,
                target_disease=target_disease,
            )
            row_dict = {
                "date": target_date.strftime("%Y-%m-%d"),
                "feature_date": sim_date.strftime("%Y-%m-%d"),
                "real_qty": real_qty,
                "bio": scores["bio"],
                "market": scores["market"],
                "psycho": scores["psycho"],
                "context": scores["context"],
                "school_start": scores["school_start"],
            }

            if enhanced:
                row_dict["wastewater_raw"] = scores["wastewater_raw"]
                row_dict["positivity_raw"] = scores["positivity_raw"]
                row_dict["are_consultation_raw"] = scores.get("are_consultation_raw", 0.0)
                row_dict["trends_raw"] = scores["trends_raw"]
                row_dict["weather_temp"] = scores["weather_temp"]
                row_dict["weather_humidity"] = scores["weather_humidity"]
                row_dict["school_start_float"] = scores["school_start_float"]
                row_dict["xdisease_load"] = scores["xdisease_load"]

                row_dict["ww_lag0w"] = scores["ww_lag0w"]
                row_dict["ww_lag1w"] = scores["ww_lag1w"]
                row_dict["ww_lag2w"] = scores["ww_lag2w"]
                row_dict["ww_lag3w"] = scores["ww_lag3w"]
                row_dict["ww_max_3w"] = scores["ww_max_3w"]
                row_dict["ww_slope_2w"] = scores["ww_slope_2w"]

                row_dict["grippeweb_are"] = scores["grippeweb_are"]
                row_dict["notaufnahme_ari"] = scores["notaufnahme_ari"]

                row_dict["survstat_xdisease_1"] = scores["survstat_xdisease_1"]
                row_dict["survstat_xdisease_2"] = scores["survstat_xdisease_2"]

                i = int(idx)
                if "available_time" in df.columns:
                    vintage_mask = df["available_time"] <= sim_date
                    vintage_vals = df.loc[vintage_mask, "menge"].tolist()
                else:
                    vintage_vals = menge_values[:i]
                if len(vintage_vals) >= 2:
                    row_dict["target_roc"] = (
                        (vintage_vals[-1] - vintage_vals[-2]) / vintage_vals[-2]
                        if vintage_vals[-2] > 0
                        else 0.0
                    )
                else:
                    row_dict["target_roc"] = 0.0

                row_dict["seasonal_baseline"] = baseline
                if vintage_vals:
                    seasonal_med = max(float(np.median(vintage_vals)), 1.0)
                    row_dict["target_level"] = round(float(vintage_vals[-1]) / seasonal_med, 4)
                else:
                    row_dict["target_level"] = 0.0

                iso_week = target_date.isocalendar()[1]
                row_dict["week_sin"] = round(math.sin(2 * math.pi * iso_week / 52), 4)
                row_dict["week_cos"] = round(math.cos(2 * math.pi * iso_week / 52), 4)

            simulation_rows.append(row_dict)
        except Exception as exc:
            logger.warning("Simulation für %s fehlgeschlagen: %s", sim_date, exc)
            continue

    return simulation_rows


def fit_regression_from_simulation(
    service,
    *,
    df_sim: pd.DataFrame,
    virus_typ: str,
    use_llm: bool = True,
) -> dict:
    """Trainiert den Ridge-Fit auf simulierten Features und berechnet Kennzahlen."""
    if df_sim.empty:
        return {"error": "Keine Datenpunkte konnten simuliert werden."}

    feature_cols = ["bio", "market", "psycho", "context"]
    X = df_sim[feature_cols].values
    y = df_sim["real_qty"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=1.0, fit_intercept=True)
    model.fit(X_scaled, y)

    y_pred = model.predict(X_scaled)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)

    raw_coefs = np.abs(model.coef_)
    total = raw_coefs.sum()
    if total > 0:
        weights_pct = {
            col: round(float(raw_coefs[i] / total), 2)
            for i, col in enumerate(feature_cols)
        }
    else:
        weights_pct = dict(service.DEFAULT_WEIGHTS)

    if y.max() > 0:
        y_pred_scaled = y_pred * (y.mean() / y_pred.mean()) if y_pred.mean() > 0 else y_pred
    else:
        y_pred_scaled = y_pred

    chart_data = []
    records = df_sim.to_dict(orient="records")
    for i, row in enumerate(records):
        chart_data.append({
            "date": row["date"],
            "real_qty": row["real_qty"],
            "predicted_qty": round(float(y_pred_scaled[i]), 1),
            "bio": row["bio"],
            "psycho": row["psycho"],
            "context": row["context"],
        })

    correlation = float(np.corrcoef(y, y_pred)[0, 1]) if len(y) > 2 else 0.0
    if np.isnan(correlation):
        correlation = 0.0

    if use_llm:
        llm_insight = service._generate_llm_insight(
            weights_pct, r2, correlation, mae, len(df_sim), virus_typ,
        )
    else:
        llm_insight = (
            f"Simulation über {len(df_sim)} Datenpunkte: "
            f"R²={r2:.2f}, Korrelation={correlation:.1%}, MAE={mae:.1f}. "
            f"Dominanter Treiber: {max(weights_pct, key=weights_pct.get)}."
        )

    return {
        "metrics": {
            "r2_score": round(r2, 3),
            "correlation": round(correlation, 3),
            "correlation_pct": round(abs(correlation) * 100, 1),
            "mae": round(mae, 1),
            "data_points": len(df_sim),
            "date_range": {
                "start": df_sim["date"].min(),
                "end": df_sim["date"].max(),
            },
        },
        "default_weights": dict(service.DEFAULT_WEIGHTS),
        "optimized_weights": weights_pct,
        "llm_insight": llm_insight,
        "chart_data": chart_data,
    }
