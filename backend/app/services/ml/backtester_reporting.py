from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func

from app.core.time import utc_now
from app.models.database import GanzimmunData, LabConfiguration, SurvstatKreisData

logger = logging.getLogger(__name__)


def run_global_calibration(
    service,
    *,
    virus_typ: str = "Influenza A",
    days_back: int = 1095,
) -> dict:
    """Trainiert globale Default-Gewichte aus internen Daten oder RKI-Fallbacks."""
    logger.info(
        "Starte globale Kalibrierung: %s, Rückblick=%s Tage (%.1f Jahre)",
        virus_typ,
        days_back,
        days_back / 365,
    )

    start_date = datetime.now() - timedelta(days=days_back)
    internal_data = service.db.query(GanzimmunData).filter(
        GanzimmunData.test_typ.ilike(f"%{virus_typ}%"),
        GanzimmunData.datum >= start_date,
    ).order_by(GanzimmunData.datum.asc()).all()

    target_source = "INTERNAL_SALES"

    if not internal_data or len(internal_data) < 50:
        logger.info("Keine ausreichenden internen Daten. Fallback auf RKI ARE.")

        try:
            df, target_meta = service._load_market_target(
                target_source="RKI_ARE",
                days_back=days_back,
            )
            target_source = target_meta.get("target_source", "RKI_ARE")
        except Exception as exc:
            logger.warning("ARE-Fallback fehlgeschlagen: %s", exc)
            df = pd.DataFrame()

        if len(df) < 20:
            logger.info("ARE nicht ausreichend. Fallback auf SURVSTAT All.")
            try:
                df, target_meta = service._load_market_target(
                    target_source="SURVSTAT",
                    days_back=days_back,
                )
                target_source = target_meta.get("target_source", "SURVSTAT")
            except Exception as exc:
                logger.warning("SURVSTAT-Fallback fehlgeschlagen: %s", exc)
                df = pd.DataFrame()

        if len(df) < 5:
            return {"error": "Weder interne Daten noch valide RKI-Proxy-Daten verfügbar."}
    else:
        df = pd.DataFrame([{
            "datum": row.datum,
            "menge": row.anzahl_tests,
        } for row in internal_data])

    if len(df) < 5:
        return {"error": f"Zu wenig Datenpunkte ({len(df)}) für Kalibrierung."}

    result = service.run_calibration(df, virus_typ=virus_typ)
    if "error" in result:
        return result

    new_weights = result["optimized_weights"]
    canonical_weights = service._canonicalize_factor_weights(new_weights)
    metrics = result["metrics"]

    save_global_defaults(service, canonical_weights, metrics["r2_score"], len(df))

    message = (
        f"Analyse über {len(df)} Datenpunkte "
        f"({len(df) / 365 * 7:.1f} Wochen) abgeschlossen. "
        f"Basis: {target_source}. "
        f"Neue Gewichtung: Bio {canonical_weights['bio'] * 100:.0f}%, "
        f"Markt {canonical_weights['market'] * 100:.0f}%, "
        f"Psycho {canonical_weights['psycho'] * 100:.0f}%, "
        f"Kontext {canonical_weights['context'] * 100:.0f}%."
    )

    return {
        "status": "success",
        "calibration_source": target_source,
        "period_days": days_back,
        "data_points": len(df),
        "new_weights": new_weights,
        "new_weights_canonical": canonical_weights,
        "metrics": metrics,
        "message": message,
    }


def save_global_defaults(service, weights: dict, score: float, days_count: int) -> None:
    """Speichert optimierte Gewichte als globale Standardkonfiguration."""
    weights = service._canonicalize_factor_weights(weights)
    config = service.db.query(LabConfiguration).filter_by(
        is_global_default=True,
    ).first()

    if not config:
        config = LabConfiguration(is_global_default=True)
        service.db.add(config)

    config.weight_bio = weights.get("bio", 0.35)
    config.weight_market = weights.get("market", 0.35)
    config.weight_psycho = weights.get("psycho", 0.10)
    config.weight_context = weights.get("context", 0.20)
    config.correlation_score = score
    config.analyzed_days = days_count
    config.last_calibration_date = utc_now()
    config.calibration_source = "GLOBAL_AUTO_3Y"

    service.db.commit()
    logger.info("Globale System-Defaults aktualisiert (R²=%.2f)", score)


def generate_business_pitch_report(
    service,
    *,
    disease: str | list[str] = "Norovirus-Gastroenteritis",
    virus_typ: str = "Influenza A",
    season_start: str = "2024-10-01",
    season_end: str = "2025-03-31",
    output_path: str | None = None,
) -> dict:
    """Erzeugt einen retrospektiven Business-Proof-Report für den Früherkennungs-Vorteil."""
    if isinstance(disease, str) and disease.upper() == "GELO_ATEMWEG":
        disease_list = service.GELO_ATEMWEG_DISEASES
        disease_label = (
            "Gelo Atemwegsinfekte "
            "(Influenza+RSV+Keuchhusten+Mycoplasma+Parainfluenza)"
        )
    elif isinstance(disease, list):
        disease_list = disease
        disease_label = " + ".join(disease_list)
    else:
        disease_list = [disease]
        disease_label = disease

    start_dt = datetime.strptime(season_start, "%Y-%m-%d")
    end_dt = datetime.strptime(season_end, "%Y-%m-%d")
    lookback_dt = start_dt - timedelta(weeks=8)

    logger.info(
        "Business Pitch Report: diseases=%s, virus=%s, period=%s to %s",
        disease_label, virus_typ, season_start, season_end,
    )

    kreis_rows = service.db.query(
        SurvstatKreisData.year,
        SurvstatKreisData.week,
        SurvstatKreisData.week_label,
        func.sum(SurvstatKreisData.fallzahl).label("total_cases"),
    ).filter(
        SurvstatKreisData.disease.in_(disease_list),
    ).group_by(
        SurvstatKreisData.year,
        SurvstatKreisData.week,
        SurvstatKreisData.week_label,
    ).order_by(
        SurvstatKreisData.year,
        SurvstatKreisData.week,
    ).all()

    if not kreis_rows:
        return {"error": f"No SurvstatKreisData found for diseases: {disease_list}"}

    all_weekly = []
    for row in kreis_rows:
        try:
            week_date = datetime.strptime(f"{row.year}-W{row.week:02d}-1", "%Y-W%W-%w")
        except ValueError:
            continue
        if lookback_dt <= week_date <= end_dt:
            all_weekly.append({
                "date": week_date,
                "week_label": row.week_label,
                "actual_rki_cases": int(row.total_cases or 0),
            })

    df_all = pd.DataFrame(all_weekly).sort_values("date").reset_index(drop=True)
    if len(df_all) < 8:
        return {"error": f"Insufficient data points ({len(df_all)}) in evaluation window"}

    scores = []
    for _, row in df_all.iterrows():
        sub = service._compute_sub_scores_at_date(
            target=row["date"],
            virus_typ=virus_typ,
            delay_rules=service.DEFAULT_DELAY_RULES_DAYS,
        )
        weights = service.DEFAULT_WEIGHTS
        composite = round(min(1.0, max(0.0,
            sub["bio"] * weights["bio"] + sub["market"] * weights["market"]
            + sub["psycho"] * weights["psycho"] + sub["context"] * weights["context"]
        )), 4)
        scores.append({**sub, "ml_risk_score": composite})

    df_all["ml_risk_score"] = [score["ml_risk_score"] for score in scores]
    df_all["bio_score"] = [score["bio"] for score in scores]
    df_all["psycho_score"] = [score["psycho"] for score in scores]
    df_all["context_score"] = [score["context"] for score in scores]

    df_all["cases_prev"] = df_all["actual_rki_cases"].shift(1)
    df_all["wow_growth"] = (
        (df_all["actual_rki_cases"] - df_all["cases_prev"])
        / df_all["cases_prev"].replace(0, np.nan)
    ).fillna(0)

    df_all["bio_rolling_mean"] = df_all["bio_score"].rolling(4, min_periods=2).mean()
    df_all["bio_above_trend"] = df_all["bio_score"] > df_all["bio_rolling_mean"]
    df_all["bio_above_streak"] = 0

    streak = 0
    for i in range(len(df_all)):
        if df_all.iloc[i]["bio_above_trend"]:
            streak += 1
        else:
            streak = 0
        df_all.iloc[i, df_all.columns.get_loc("bio_above_streak")] = streak

    df_all["alert_triggered"] = (
        (df_all["wow_growth"] >= 0.40) & (df_all["bio_above_streak"] >= 2)
    )

    df_eval = df_all[df_all["date"] >= start_dt].copy().reset_index(drop=True)
    if df_eval.empty:
        return {"error": "No data points in evaluation window after filtering"}

    peak_idx = df_eval["actual_rki_cases"].idxmax()
    rki_peak_date = df_eval.loc[peak_idx, "date"]
    rki_peak_cases = int(df_eval.loc[peak_idx, "actual_rki_cases"])

    alert_rows = df_eval[df_eval["alert_triggered"]]
    ml_first_alert_date = alert_rows.iloc[0]["date"] if not alert_rows.empty else None
    ttd_days = (rki_peak_date - ml_first_alert_date).days if ml_first_alert_date else 0

    report_rows = []
    for _, row in df_eval.iterrows():
        report_rows.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "region": "Gesamt",
            "disease": disease_label,
            "actual_rki_cases": int(row["actual_rki_cases"]),
            "ml_risk_score": float(row["ml_risk_score"]),
            "alert_triggered": bool(row["alert_triggered"]),
            "ttd_advantage_days": ttd_days,
            "bio_score": float(row["bio_score"]),
            "psycho_score": float(row["psycho_score"]),
            "context_score": float(row["context_score"]),
            "wow_growth_pct": round(float(row["wow_growth"]) * 100, 1),
        })

    df_report = pd.DataFrame(report_rows)

    if output_path is None:
        out_dir = Path("/app/data/processed")
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / "backtest_business_report.csv")

    df_report.to_csv(output_path, index=False)
    logger.info("Business pitch report exported to %s (%d rows)", output_path, len(df_report))

    alerts_count = int(df_report["alert_triggered"].sum())
    total_weeks = len(df_report)

    summary = {
        "status": "success",
        "disease": disease_label,
        "disease_list": disease_list,
        "virus_typ": virus_typ,
        "season": f"{season_start} → {season_end}",
        "total_weeks": total_weeks,
        "rki_peak_date": rki_peak_date.strftime("%Y-%m-%d"),
        "rki_peak_cases": rki_peak_cases,
        "ml_first_alert_date": ml_first_alert_date.strftime("%Y-%m-%d") if ml_first_alert_date else None,
        "ttd_advantage_days": ttd_days,
        "detection_method": "Adaptive: WoW_growth>=40% AND bio_score>4wk_trailing_avg for 2+ weeks",
        "alerts_triggered": alerts_count,
        "alert_rate_pct": round(alerts_count / total_weeks * 100, 1),
        "output_path": output_path,
        "proof_statement": (
            f"ViralFlux-Signal zeigte {ttd_days} Tage vor dem RKI-Peak "
            f"({rki_peak_date.strftime('%Y-%m-%d')}, {rki_peak_cases:,} Faelle) ein Frühsignal. "
            f"Erste Warnung: {ml_first_alert_date.strftime('%Y-%m-%d') if ml_first_alert_date else 'k.A.'}. "
            "(Retrospektive Analyse — kein garantierter Vorhersagevorteil.)"
        ) if ml_first_alert_date else (
            f"Kein ML-Frühsignal im Evaluationszeitraum ausgelöst. "
            f"RKI-Peak: {rki_peak_date.strftime('%Y-%m-%d')} ({rki_peak_cases:,} Faelle)."
        ),
    }

    logger.info("Business proof: TTD=%d days, peak=%s", ttd_days, rki_peak_date.strftime("%Y-%m-%d"))
    return summary
