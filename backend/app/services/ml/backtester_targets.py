"""Target loading and planning helpers for BacktestService."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy import func

from app.models.database import (
    AREKonsultation,
    SurvstatWeeklyData,
    WastewaterAggregated,
)


def resolve_survstat_disease(service, source_token: str) -> Optional[str]:
    """Mappt Zieltoken auf einen konkreten SURVSTAT-Disease-String."""
    token = (source_token or "").strip()
    token_upper = token.upper()

    if token_upper in service.SURVSTAT_TARGET_ALIASES:
        token = service.SURVSTAT_TARGET_ALIASES[token_upper]

    exact = service.db.query(SurvstatWeeklyData.disease).filter(
        SurvstatWeeklyData.disease == token
    ).first()
    if exact:
        return exact[0]

    pattern = f"%{token.lower()}%"
    row = service.db.query(SurvstatWeeklyData.disease).filter(
        func.lower(SurvstatWeeklyData.disease).like(pattern)
    ).order_by(SurvstatWeeklyData.disease.asc()).first()

    return row[0] if row else None


def load_market_target(
    service,
    *,
    target_source: str = "RKI_ARE",
    days_back: int = 730,
    bundesland: str = "",
) -> Tuple[pd.DataFrame, dict]:
    """Lädt externe Markt-Proxy-Wahrheit für Twin-Mode Market-Check."""
    token = (target_source or "RKI_ARE").strip()
    token_upper = token.upper()
    start_date = datetime.now() - timedelta(days=days_back)
    bl_filter = bundesland.strip() if bundesland else "Gesamt"

    if token_upper == "ATEMWEGSINDEX":
        surv_rows = service.db.query(
            SurvstatWeeklyData.week_start,
            SurvstatWeeklyData.week_label,
            func.sum(SurvstatWeeklyData.incidence).label("total_incidence"),
            func.min(SurvstatWeeklyData.available_time).label("available_time"),
        ).filter(
            SurvstatWeeklyData.disease.in_(service.GELO_ATEMWEG_DISEASES),
            SurvstatWeeklyData.bundesland == bl_filter,
            (SurvstatWeeklyData.age_group == "Gesamt") | (SurvstatWeeklyData.age_group.is_(None)),
            SurvstatWeeklyData.week_start >= start_date,
        ).group_by(
            SurvstatWeeklyData.week_start,
            SurvstatWeeklyData.week_label,
        ).order_by(SurvstatWeeklyData.week_start.asc()).all()

        df = pd.DataFrame(
            [
                {
                    "datum": row.week_start,
                    "menge": float(row.total_incidence or 0),
                    "available_time": row.available_time or row.week_start,
                }
                for row in surv_rows
            ]
        )

        bl_label = bl_filter if bl_filter != "Gesamt" else "Bundesweit"
        return df, {
            "target_source": "ATEMWEGSINDEX",
            "target_label": f"Atemwegsindex ({bl_label})",
            "target_key": "ATEMWEGSINDEX",
            "disease": None,
            "bundesland": bl_filter,
        }

    if token_upper == "RKI_ARE":
        bl_are = "Bundesweit" if bl_filter == "Gesamt" else bl_filter
        are_rows = service.db.query(AREKonsultation).filter(
            AREKonsultation.altersgruppe == "00+",
            AREKonsultation.bundesland == bl_are,
            AREKonsultation.datum >= start_date,
        ).order_by(AREKonsultation.datum.asc()).all()

        df = pd.DataFrame(
            [
                {
                    "datum": row.datum,
                    "menge": row.konsultationsinzidenz,
                    "available_time": row.available_time or row.datum,
                }
                for row in are_rows
                if row.konsultationsinzidenz is not None
            ]
        )

        return df, {
            "target_source": "RKI_ARE",
            "target_label": f"RKI ARE ({bl_are}, 00+)",
            "target_key": "RKI_ARE",
            "bundesland": bl_filter,
        }

    if token_upper.startswith("SURVSTAT:"):
        survstat_token = token.split(":", 1)[1].strip()
    else:
        survstat_token = service.SURVSTAT_TARGET_ALIASES.get(token_upper, token)

    disease = service._resolve_survstat_disease(survstat_token)
    if not disease:
        available = service.db.query(SurvstatWeeklyData.disease).distinct().order_by(
            SurvstatWeeklyData.disease.asc()
        ).limit(12).all()
        available_names = [row[0] for row in available]
        raise ValueError(
            f"SURVSTAT Ziel '{target_source}' nicht gefunden. "
            f"Verfügbar (Auszug): {available_names}"
        )

    surv_rows = service.db.query(SurvstatWeeklyData).filter(
        SurvstatWeeklyData.disease == disease,
        SurvstatWeeklyData.bundesland == bl_filter,
        SurvstatWeeklyData.week_start >= start_date,
    ).order_by(SurvstatWeeklyData.week_start.asc()).all()

    df = pd.DataFrame(
        [
            {
                "datum": row.week_start,
                "menge": row.incidence,
                "available_time": row.available_time or row.week_start,
            }
            for row in surv_rows
            if row.incidence is not None
        ]
    )

    bl_label = bl_filter if bl_filter != "Gesamt" else "Bundesweit"
    return df, {
        "target_source": "SURVSTAT",
        "target_label": f"SURVSTAT {disease} ({bl_label})",
        "target_key": token_upper,
        "disease": disease,
        "bundesland": bl_filter,
    }


def build_planning_curve(
    service,
    *,
    target_df: pd.DataFrame,
    virus_typ: str = "Influenza A",
    days_back: int = 2500,
) -> dict:
    """Planungskurve: Abwasser um empirischen Lead shiften + skalieren."""
    start_date = datetime.now() - timedelta(days=days_back)

    ww_weekly = service.db.query(
        func.date_trunc("week", WastewaterAggregated.datum).label("week"),
        func.avg(WastewaterAggregated.viruslast).label("avg_vl"),
    ).filter(
        WastewaterAggregated.virus_typ == virus_typ,
        WastewaterAggregated.datum >= start_date,
    ).group_by(
        func.date_trunc("week", WastewaterAggregated.datum)
    ).order_by("week").all()

    if len(ww_weekly) < 10:
        return {"lead_days": 0, "correlation": 0, "curve": []}

    ww_df = pd.DataFrame(
        [{"week": r.week, "viruslast": float(r.avg_vl or 0)} for r in ww_weekly]
    ).set_index("week")

    tgt_df = target_df.copy()
    tgt_df["datum"] = pd.to_datetime(tgt_df["datum"])
    tgt_df = tgt_df.set_index("datum")[["menge"]].dropna()

    merged = ww_df.join(tgt_df, how="inner").dropna()
    if len(merged) < 15:
        return {"lead_days": 0, "correlation": 0, "curve": []}

    vl = merged["viruslast"].values
    inc = merged["menge"].values
    vl_n = (vl - vl.mean()) / (vl.std() + 1e-9)
    inc_n = (inc - inc.mean()) / (inc.std() + 1e-9)

    best_lag = 0
    best_corr = 0.0
    for lag in range(0, 5):
        if lag > 0:
            x, y = vl_n[:-lag], inc_n[lag:]
        else:
            x, y = vl_n, inc_n
        if len(x) < 10:
            continue
        corr = float(np.corrcoef(x, y)[0, 1])
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    lead_days = best_lag * 7

    if best_lag > 0:
        X_reg = vl[:-best_lag].reshape(-1, 1)
        y_reg = inc[best_lag:]
    else:
        X_reg = vl.reshape(-1, 1)
        y_reg = inc

    reg = LinearRegression().fit(X_reg, y_reg)

    curve = []
    for _, row_data in ww_df.iterrows():
        ww_date = row_data.name
        target_date = ww_date + timedelta(days=lead_days)
        predicted = max(0, float(reg.predict([[row_data["viruslast"]]])[0]))
        curve.append(
            {
                "date": target_date.strftime("%Y-%m-%d"),
                "based_on": ww_date.strftime("%Y-%m-%d"),
                "issue_date": ww_date.strftime("%Y-%m-%d"),
                "target_date": target_date.strftime("%Y-%m-%d"),
                "planning_qty": round(predicted, 2),
            }
        )

    return {
        "lead_days": lead_days,
        "lead_weeks": best_lag,
        "correlation": round(best_corr, 3),
        "regression_coef": round(float(reg.coef_[0]), 6),
        "regression_intercept": round(float(reg.intercept_), 2),
        "curve": sorted(curve, key=lambda r: r["date"]),
    }
