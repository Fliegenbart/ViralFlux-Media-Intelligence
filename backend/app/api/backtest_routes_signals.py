"""Signal and radar backtest API routes."""

from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.database import SurvstatWeeklyData, WastewaterAggregated

router = APIRouter()

VALID_VIRUS_TYPES = {"Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"}

_SURVSTAT_DISEASE_MAP = {
    "Influenza A": "influenza, saisonal",
    "Influenza B": "influenza, saisonal",
    "SARS-CoV-2": "covid-19",
    "RSV A": "rsv (meldepflicht gemäß ifsg)",
}

_VIRUS_TO_WW = {
    "Influenza A": "Influenza A",
    "Influenza B": "Influenza B",
    "SARS-CoV-2": "SARS-CoV-2",
    "RSV A": "RSV",
}

DISEASE_ALIASES = {
    "influenza": "Influenza, saisonal",
    "mycoplasma": "Mycoplasma",
    "keuchhusten": "Keuchhusten (Meldepflicht gemäß IfSG)",
    "pneumokokken": "Pneumokokken (Meldepflicht gemäß IfSG)",
    "parainfluenza": "Parainfluenza",
    "rsv": "RSV (Meldepflicht gemäß IfSG)",
    "covid": "COVID-19",
    "norovirus": "Norovirus-Gastroenteritis",
    "rotavirus": "Rotavirus-Gastroenteritis",
}

BUNDESLAENDER = [
    "Baden-Württemberg",
    "Bayern",
    "Berlin",
    "Brandenburg",
    "Bremen",
    "Hamburg",
    "Hessen",
    "Mecklenburg-Vorpommern",
    "Niedersachsen",
    "Nordrhein-Westfalen",
    "Rheinland-Pfalz",
    "Saarland",
    "Sachsen",
    "Sachsen-Anhalt",
    "Schleswig-Holstein",
    "Thüringen",
]

ALERT_DISEASES = [
    "Influenza, saisonal",
    "Mycoplasma",
    "Keuchhusten (Meldepflicht gemäß IfSG)",
    "Pneumokokken (Meldepflicht gemäß IfSG)",
    "Parainfluenza",
    "RSV (Meldepflicht gemäß IfSG)",
    "COVID-19",
    "Norovirus-Gastroenteritis",
    "Rotavirus-Gastroenteritis",
]

DISEASE_SHORT = {
    "Influenza, saisonal": "Influenza",
    "Mycoplasma": "Mycoplasma",
    "Keuchhusten (Meldepflicht gemäß IfSG)": "Keuchhusten",
    "Pneumokokken (Meldepflicht gemäß IfSG)": "Pneumokokken",
    "Parainfluenza": "Parainfluenza",
    "RSV (Meldepflicht gemäß IfSG)": "RSV",
    "COVID-19": "COVID-19",
    "Norovirus-Gastroenteritis": "Norovirus",
    "Rotavirus-Gastroenteritis": "Rotavirus",
}

DISEASE_CLUSTER = {
    "Influenza, saisonal": "RESPIRATORY",
    "Mycoplasma": "RESPIRATORY",
    "Keuchhusten (Meldepflicht gemäß IfSG)": "RESPIRATORY",
    "Pneumokokken (Meldepflicht gemäß IfSG)": "RESPIRATORY",
    "Parainfluenza": "RESPIRATORY",
    "RSV (Meldepflicht gemäß IfSG)": "RESPIRATORY",
    "COVID-19": "RESPIRATORY",
    "Norovirus-Gastroenteritis": "GASTROINTESTINAL",
    "Rotavirus-Gastroenteritis": "GASTROINTESTINAL",
}


@router.get("/peix-validation", dependencies=[Depends(get_current_user)])
async def peix_validation(
    virus_typ: str = Query(default="Influenza A"),
    weeks_back: int = Query(default=104, ge=26, le=260),
    spike_percentile: float = Query(default=75.0, ge=50, le=95),
    alert_threshold: float = Query(default=0.45, ge=0.1, le=0.9),
    db: Session = Depends(get_db),
):
    """PEIX-Validierung: Wie gut hat das Abwasser-Frühsignal SURVSTAT-Spitzen vorhergesagt?"""
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    now = utc_now()
    cutoff = now - timedelta(weeks=weeks_back)
    disease = _SURVSTAT_DISEASE_MAP.get(virus_typ, "influenza, saisonal")
    ww_virus = _VIRUS_TO_WW.get(virus_typ, virus_typ)

    surv_rows = (
        db.query(
            SurvstatWeeklyData.week_start,
            func.sum(SurvstatWeeklyData.incidence).label("total_inc"),
        )
        .filter(
            func.lower(SurvstatWeeklyData.disease) == disease.lower(),
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.week_start >= cutoff,
        )
        .group_by(SurvstatWeeklyData.week_start)
        .order_by(SurvstatWeeklyData.week_start)
        .all()
    )
    if len(surv_rows) < 10:
        return {"error": f"Zu wenig SURVSTAT-Daten für '{disease}' (nur {len(surv_rows)} Wochen)."}

    surv_df = pd.DataFrame(
        [{"week_start": row.week_start, "incidence": float(row.total_inc or 0)} for row in surv_rows]
    ).sort_values("week_start").reset_index(drop=True)

    ww_rows = (
        db.query(
            func.date_trunc("week", WastewaterAggregated.datum).label("week_start"),
            func.avg(WastewaterAggregated.viruslast_normalisiert).label("avg_vl"),
        )
        .filter(
            WastewaterAggregated.virus_typ == ww_virus,
            WastewaterAggregated.datum >= cutoff,
        )
        .group_by(func.date_trunc("week", WastewaterAggregated.datum))
        .order_by(func.date_trunc("week", WastewaterAggregated.datum))
        .all()
    )
    ww_df = pd.DataFrame(
        [{"week_start": row.week_start, "wastewater": float(row.avg_vl or 0)} for row in ww_rows]
    ).sort_values("week_start").reset_index(drop=True)

    if ww_df.empty:
        return {"error": f"Keine AMELAG-Abwasserdaten für '{ww_virus}'."}

    surv_df["week_start"] = pd.to_datetime(surv_df["week_start"]).dt.tz_localize(None)
    ww_df["week_start"] = pd.to_datetime(ww_df["week_start"]).dt.tz_localize(None)
    merged = pd.merge_asof(
        surv_df.sort_values("week_start"),
        ww_df.sort_values("week_start"),
        on="week_start",
        direction="nearest",
        tolerance=pd.Timedelta("10D"),
    ).dropna(subset=["wastewater"])

    if len(merged) < 10:
        return {"error": "Zu wenig überlappende Wochen zwischen AMELAG und SURVSTAT."}

    ww_max = merged["wastewater"].max()
    merged["bio_signal"] = merged["wastewater"] / ww_max if ww_max > 0 else 0.0

    merged["inc_rolling_p75"] = merged["incidence"].rolling(
        min(52, len(merged) // 2),
        min_periods=8,
    ).quantile(spike_percentile / 100.0)
    merged["is_spike"] = merged["incidence"] > merged["inc_rolling_p75"]
    merged["is_alert"] = merged["bio_signal"] > alert_threshold

    valid = merged.dropna(subset=["inc_rolling_p75"]).reset_index(drop=True)
    if valid.empty:
        return {"error": "Nicht genug Daten nach Rolling-Window-Berechnung."}

    tp = 0
    fp = 0
    lead_weeks: list[int] = []
    look_ahead = 4

    spike_indices = set(valid.index[valid["is_spike"]])
    alert_indices = set(valid.index[valid["is_alert"]])
    matched_spikes: set[int] = set()
    for alert_index in sorted(alert_indices):
        found = False
        for ahead in range(0, look_ahead + 1):
            spike_index = alert_index + ahead
            if spike_index in spike_indices and spike_index not in matched_spikes:
                tp += 1
                lead_weeks.append(ahead)
                matched_spikes.add(spike_index)
                found = True
                break
        if not found:
            fp += 1

    fn = len(spike_indices - matched_spikes)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    median_lead = float(np.median(lead_weeks)) if lead_weeks else 0.0
    corr = float(valid["bio_signal"].corr(valid["incidence"]))

    chart_data = [
        {
            "date": row["week_start"].strftime("%Y-%m-%d"),
            "incidence": round(float(row["incidence"]), 2),
            "bio_signal": round(float(row["bio_signal"]), 4),
            "is_spike": bool(row["is_spike"]),
            "is_alert": bool(row["is_alert"]),
            "threshold": round(float(row.get("inc_rolling_p75", 0)), 2),
        }
        for _, row in valid.iterrows()
    ]

    return {
        "virus_typ": virus_typ,
        "weeks_analyzed": len(valid),
        "spike_percentile": spike_percentile,
        "alert_threshold": alert_threshold,
        "metrics": {
            "precision": round(precision * 100, 1),
            "recall": round(recall * 100, 1),
            "f1_score": round(f1 * 100, 1),
            "median_lead_weeks": round(median_lead, 1),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "correlation": round(corr, 3),
        },
        "summary": (
            f"PEIX Bio-Signal erkannte {round(recall * 100)}% der SURVSTAT-Spitzen "
            f"(Precision {round(precision * 100)}%, F1 {round(f1 * 100)}%). "
            f"Medianer Vorlauf: {round(median_lead, 1)} Wochen. "
            f"Korrelation Abwasser↔Inzidenz: r={round(corr, 2)}."
        ),
        "chart_data": chart_data,
    }


@router.get("/wave-radar", dependencies=[Depends(get_current_user)])
async def wave_radar(
    disease: str = Query(default="influenza", description="Krankheit (influenza, mycoplasma, keuchhusten, ...)"),
    season: str = Query(default="", description="Saison im Format YYYY/YYYY (z.B. 2024/2025). Leer = letzte verfügbare."),
    threshold_pct: float = Query(default=50.0, ge=10, le=200, description="Schwellwert: Prozent über Saison-Median = Wellenstart"),
    db: Session = Depends(get_db),
):
    """Wellen-Radar: Wann und wo beginnt eine Krankheitswelle?"""
    disease_name = DISEASE_ALIASES.get(disease.lower().strip(), disease)

    if season and "/" in season:
        parts = season.split("/")
        season_start = datetime(int(parts[0]), 10, 1)
        season_end = datetime(int(parts[1]), 5, 31)
    else:
        latest = (
            db.query(func.max(SurvstatWeeklyData.week_start))
            .filter(
                SurvstatWeeklyData.disease == disease_name,
                SurvstatWeeklyData.bundesland != "Gesamt",
            )
            .scalar()
        )
        if not latest:
            return {"error": f"Keine regionalen Daten für '{disease_name}'.", "available": list(DISEASE_ALIASES.keys())}
        if latest.month >= 10:
            season_start = datetime(latest.year, 10, 1)
            season_end = datetime(latest.year + 1, 5, 31)
        else:
            season_start = datetime(latest.year - 1, 10, 1)
            season_end = datetime(latest.year, 5, 31)

    season_label = f"{season_start.year}/{season_end.year}"

    baseline_rows = (
        db.query(
            SurvstatWeeklyData.bundesland,
            func.avg(SurvstatWeeklyData.incidence).label("avg_inc"),
        )
        .filter(
            SurvstatWeeklyData.disease == disease_name,
            SurvstatWeeklyData.bundesland != "Gesamt",
            SurvstatWeeklyData.week_start < season_start,
            SurvstatWeeklyData.incidence > 0,
        )
        .group_by(SurvstatWeeklyData.bundesland)
        .all()
    )

    bl_baseline = {row.bundesland: float(row.avg_inc) for row in baseline_rows}

    if not bl_baseline:
        national_avg = (
            db.query(func.avg(SurvstatWeeklyData.incidence))
            .filter(
                SurvstatWeeklyData.disease == disease_name,
                SurvstatWeeklyData.bundesland == "Gesamt",
                SurvstatWeeklyData.incidence > 0,
            )
            .scalar()
        )
        for bundesland in BUNDESLAENDER:
            bl_baseline[bundesland] = float(national_avg or 1.0)

    season_rows = (
        db.query(
            SurvstatWeeklyData.bundesland,
            SurvstatWeeklyData.week_start,
            SurvstatWeeklyData.week_label,
            SurvstatWeeklyData.incidence,
        )
        .filter(
            SurvstatWeeklyData.disease == disease_name,
            SurvstatWeeklyData.bundesland != "Gesamt",
            SurvstatWeeklyData.week_start >= season_start,
            SurvstatWeeklyData.week_start <= season_end,
        )
        .order_by(
            SurvstatWeeklyData.bundesland,
            SurvstatWeeklyData.week_start,
        )
        .all()
    )

    bl_data: dict[str, list] = {bundesland: [] for bundesland in BUNDESLAENDER}
    for row in season_rows:
        if row.bundesland in bl_data:
            bl_data[row.bundesland].append(
                {
                    "week_start": row.week_start,
                    "week_label": row.week_label,
                    "incidence": float(row.incidence),
                }
            )

    results = []
    timeline = []
    all_weeks = set()

    for bundesland in BUNDESLAENDER:
        weeks = bl_data.get(bundesland, [])
        baseline = bl_baseline.get(bundesland, 1.0)
        threshold = baseline * (1 + threshold_pct / 100)

        wave_start = None
        peak_week = None
        peak_inc = 0.0
        total_inc = 0.0

        for week in weeks:
            all_weeks.add(week["week_label"])
            total_inc += week["incidence"]
            if week["incidence"] > peak_inc:
                peak_inc = week["incidence"]
                peak_week = week["week_label"]

            if wave_start is None and week["incidence"] >= threshold:
                wave_start = week["week_start"]

        results.append(
            {
                "bundesland": bundesland,
                "wave_start": wave_start.strftime("%Y-%m-%d") if wave_start else None,
                "wave_week": next((week["week_label"] for week in weeks if week["week_start"] == wave_start), None) if wave_start else None,
                "peak_week": peak_week,
                "peak_incidence": round(peak_inc, 3),
                "baseline_avg": round(baseline, 3),
                "threshold": round(threshold, 3),
                "total_incidence": round(total_inc, 3),
                "data_points": len(weeks),
            }
        )

        if wave_start:
            timeline.append((wave_start, bundesland))

    timeline.sort(key=lambda item: item[0])
    rank = 1
    for date, bundesland in timeline:
        for result in results:
            if result["bundesland"] == bundesland:
                result["wave_rank"] = rank
                break
        rank += 1

    for result in results:
        if "wave_rank" not in result:
            result["wave_rank"] = None

    sorted_weeks = sorted(all_weeks)
    heatmap = []
    for week_label in sorted_weeks:
        week_entry = {"week_label": week_label}
        for bundesland in BUNDESLAENDER:
            match = next((week for week in bl_data.get(bundesland, []) if week["week_label"] == week_label), None)
            week_entry[bundesland] = round(match["incidence"], 3) if match else 0.0
        heatmap.append(week_entry)

    first_wave = timeline[0] if timeline else None
    last_wave = timeline[-1] if timeline else None
    spread_days = (last_wave[0] - first_wave[0]).days if first_wave and last_wave else 0

    return {
        "disease": disease_name,
        "season": season_label,
        "threshold_pct": threshold_pct,
        "summary": {
            "first_onset": {
                "bundesland": first_wave[1] if first_wave else None,
                "date": first_wave[0].strftime("%Y-%m-%d") if first_wave else None,
            },
            "last_onset": {
                "bundesland": last_wave[1] if last_wave else None,
                "date": last_wave[0].strftime("%Y-%m-%d") if last_wave else None,
            },
            "spread_days": spread_days,
            "regions_affected": len(timeline),
            "regions_total": len(BUNDESLAENDER),
        },
        "regions": sorted(results, key=lambda result: result["wave_rank"] or 999),
        "heatmap": heatmap,
    }


def _compute_lead_lag(
    db: Session,
    disease: str,
    bundesland: str,
    lookback_weeks: int = 200,
) -> int:
    """Berechne wie viele Wochen ein Bundesland der nationalen Welle voraus-/hinterherläuft."""
    cutoff = datetime.now() - timedelta(weeks=lookback_weeks)

    bl_rows = (
        db.query(
            SurvstatWeeklyData.week_label,
            SurvstatWeeklyData.incidence,
        )
        .filter(
            SurvstatWeeklyData.disease == disease,
            SurvstatWeeklyData.bundesland == bundesland,
            SurvstatWeeklyData.week_start >= cutoff,
        )
        .order_by(SurvstatWeeklyData.week_label)
        .all()
    )

    nat_rows = (
        db.query(
            SurvstatWeeklyData.week_label,
            SurvstatWeeklyData.incidence,
        )
        .filter(
            SurvstatWeeklyData.disease == disease,
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.week_start >= cutoff,
        )
        .order_by(SurvstatWeeklyData.week_label)
        .all()
    )

    if len(bl_rows) < 20 or len(nat_rows) < 20:
        return 0

    nat_dict = {row.week_label: float(row.incidence) for row in nat_rows}
    aligned_bl = []
    aligned_nat = []
    for row in bl_rows:
        if row.week_label in nat_dict:
            aligned_bl.append(float(row.incidence))
            aligned_nat.append(nat_dict[row.week_label])

    if len(aligned_bl) < 20:
        return 0

    bl_arr = np.array(aligned_bl)
    nat_arr = np.array(aligned_nat)

    bl_std = bl_arr.std()
    nat_std = nat_arr.std()
    if bl_std == 0 or nat_std == 0:
        return 0
    bl_norm = (bl_arr - bl_arr.mean()) / bl_std
    nat_norm = (nat_arr - nat_arr.mean()) / nat_std

    best_lag = 0
    best_corr = -1.0
    length = len(bl_norm)
    for lag in range(-6, 7):
        if lag >= 0:
            corr = np.dot(bl_norm[: length - lag], nat_norm[lag:]) / (length - abs(lag))
        else:
            corr = np.dot(bl_norm[-lag:], nat_norm[: length + lag]) / (length - abs(lag))
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    return -best_lag


@router.get("/outbreak-alerts", dependencies=[Depends(get_current_user)])
async def outbreak_alerts(
    db: Session = Depends(get_db),
):
    """Ausbruchs-Radar: Prognose-getriebene Alerts."""
    from collections import defaultdict

    latest_date = (
        db.query(func.max(SurvstatWeeklyData.week_start))
        .filter(
            SurvstatWeeklyData.bundesland != "Gesamt",
            SurvstatWeeklyData.incidence > 0,
        )
        .scalar()
    )

    if not latest_date:
        return {"error": "Keine regionalen Daten verfügbar."}

    recent_cutoff = latest_date - timedelta(weeks=3)
    prior_cutoff = recent_cutoff - timedelta(weeks=3)

    six_week_rows = (
        db.query(
            SurvstatWeeklyData.bundesland,
            SurvstatWeeklyData.disease,
            SurvstatWeeklyData.week_start,
            SurvstatWeeklyData.week_label,
            SurvstatWeeklyData.incidence,
        )
        .filter(
            SurvstatWeeklyData.disease.in_(ALERT_DISEASES),
            SurvstatWeeklyData.week_start > prior_cutoff,
            SurvstatWeeklyData.incidence > 0,
        )
        .all()
    )

    recent_data: dict[tuple[str, str], list[float]] = defaultdict(list)
    prior_data: dict[tuple[str, str], list[float]] = defaultdict(list)
    national_recent: dict[str, list[float]] = defaultdict(list)
    national_prior: dict[str, list[float]] = defaultdict(list)

    for row in six_week_rows:
        key = (row.bundesland, row.disease)
        incidence = float(row.incidence)
        if row.week_start > recent_cutoff:
            if row.bundesland == "Gesamt":
                national_recent[row.disease].append(incidence)
            else:
                recent_data[key].append(incidence)
        else:
            if row.bundesland == "Gesamt":
                national_prior[row.disease].append(incidence)
            else:
                prior_data[key].append(incidence)

    national_forecast: dict[str, dict] = {}
    for disease in ALERT_DISEASES:
        recent_values = national_recent.get(disease, [])
        prior_values = national_prior.get(disease, [])

        if not recent_values or not prior_values:
            bl_recent_vals = []
            bl_prior_vals = []
            for (bundesland, disease_name), values in recent_data.items():
                if disease_name == disease:
                    bl_recent_vals.extend(value for value in values)
            for (bundesland, disease_name), values in prior_data.items():
                if disease_name == disease:
                    bl_prior_vals.extend(value for value in values)
            if bl_recent_vals:
                recent_values = [sum(bl_recent_vals) / len(bl_recent_vals)]
            if bl_prior_vals:
                prior_values = [sum(bl_prior_vals) / len(bl_prior_vals)]

        if recent_values and prior_values:
            avg_recent = sum(recent_values) / len(recent_values)
            avg_prior = sum(prior_values) / len(prior_values)
            if avg_prior > 0:
                change_pct = round((avg_recent - avg_prior) / avg_prior * 100, 1)
            else:
                change_pct = 100.0 if avg_recent > 0 else 0.0
            direction = "rising" if change_pct > 10 else "falling" if change_pct < -10 else "stable"
            national_forecast[disease] = {
                "current": round(avg_recent, 3),
                "prior": round(avg_prior, 3),
                "change_pct": change_pct,
                "direction": direction,
            }

    lead_lag_cache: dict[tuple[str, str], int] = {}
    alerts = []

    for (bundesland, disease), recent_vals in recent_data.items():
        if bundesland == "Gesamt":
            continue
        prior_vals = prior_data.get((bundesland, disease), [])
        if not recent_vals:
            continue

        avg_recent = sum(recent_vals) / len(recent_vals)
        avg_prior = sum(prior_vals) / len(prior_vals) if prior_vals else 0.0

        if avg_prior > 0:
            momentum_pct = round((avg_recent - avg_prior) / avg_prior * 100, 1)
        elif avg_recent > 0:
            momentum_pct = 100.0
        else:
            continue

        cache_key = (bundesland, disease)
        if cache_key not in lead_lag_cache:
            lead_lag_cache[cache_key] = _compute_lead_lag(db, disease, bundesland)
        lead_lag_weeks = lead_lag_cache[cache_key]

        nat = national_forecast.get(disease, {})
        nat_direction = nat.get("direction", "stable")
        nat_change = nat.get("change_pct", 0.0)

        momentum_score = max(0, momentum_pct) / 50
        lead_bonus = max(0, lead_lag_weeks) * 0.3
        nat_boost = max(0, nat_change) / 100

        severity = round(momentum_score + lead_bonus + nat_boost, 2)
        if severity < 0.5 and momentum_pct < 20:
            continue

        if momentum_pct > 80 or (momentum_pct > 50 and nat_direction == "rising"):
            action = "JETZT aktivieren"
            urgency = "high"
        elif momentum_pct > 30 or (momentum_pct > 15 and nat_direction == "rising"):
            action = "Kampagne vorbereiten"
            urgency = "medium"
        elif momentum_pct > 0 and lead_lag_weeks < -1 and nat_direction in ("rising", "stable"):
            weeks_eta = max(1, abs(lead_lag_weeks))
            action = f"Welle erreicht Region in ~{weeks_eta} Wochen"
            urgency = "medium" if nat_direction == "rising" else "low"
        elif momentum_pct < -20:
            action = "Welle ebbt ab — Budget umschichten"
            urgency = "info"
        else:
            action = "Beobachten"
            urgency = "low"

        alerts.append(
            {
                "bundesland": bundesland,
                "disease": DISEASE_SHORT.get(disease, disease),
                "disease_full": disease,
                "cluster": DISEASE_CLUSTER.get(disease, "OTHER"),
                "severity": severity,
                "momentum_pct": momentum_pct,
                "lead_lag_weeks": lead_lag_weeks,
                "current_incidence": round(avg_recent, 3),
                "prior_incidence": round(avg_prior, 3),
                "national_direction": nat_direction,
                "national_change_pct": nat_change,
                "action": action,
                "urgency": urgency,
            }
        )

    urgency_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    alerts.sort(key=lambda alert: (urgency_order.get(alert["urgency"], 9), -alert["severity"]))

    bl_summary: dict[str, dict] = {}
    for bundesland in BUNDESLAENDER:
        bl_alerts = [alert for alert in alerts if alert["bundesland"] == bundesland]
        if bl_alerts:
            high_count = sum(1 for alert in bl_alerts if alert["urgency"] in ("high", "medium"))
            bl_summary[bundesland] = {
                "alert_count": len(bl_alerts),
                "high_urgency_count": high_count,
                "max_severity": max(alert["severity"] for alert in bl_alerts),
                "top_disease": bl_alerts[0]["disease"],
                "top_action": bl_alerts[0]["action"],
                "diseases": list(set(alert["disease"] for alert in bl_alerts)),
            }
        else:
            bl_summary[bundesland] = {
                "alert_count": 0,
                "high_urgency_count": 0,
                "max_severity": 0,
                "top_disease": None,
                "top_action": "Kein Signal",
                "diseases": [],
            }

    disease_summary: dict[str, dict] = {}
    for disease in ALERT_DISEASES:
        short = DISEASE_SHORT.get(disease, disease)
        disease_alerts = [alert for alert in alerts if alert["disease_full"] == disease]
        nat = national_forecast.get(disease, {})
        if disease_alerts or nat:
            disease_summary[short] = {
                "alert_count": len(disease_alerts),
                "national_direction": nat.get("direction", "unknown"),
                "national_change_pct": nat.get("change_pct", 0),
                "regions_rising": len([alert for alert in disease_alerts if alert["momentum_pct"] > 20]),
                "regions_falling": len([alert for alert in disease_alerts if alert["momentum_pct"] < -20]),
                "hottest_region": disease_alerts[0]["bundesland"] if disease_alerts else None,
            }

    return {
        "scan_date": latest_date.strftime("%Y-%m-%d"),
        "total_alerts": len(alerts),
        "high_urgency": len([alert for alert in alerts if alert["urgency"] == "high"]),
        "alerts": alerts[:60],
        "region_summary": bl_summary,
        "disease_summary": disease_summary,
        "national_forecast": {
            DISEASE_SHORT.get(disease, disease): forecast
            for disease, forecast in national_forecast.items()
        },
    }
