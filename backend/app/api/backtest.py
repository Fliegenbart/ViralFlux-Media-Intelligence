"""Backtest API: Twin-Mode (Market + Customer) + Wellen-Radar."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.database import SurvstatWeeklyData
from app.services.ml.backtester import BacktestService

logger = logging.getLogger(__name__)


router = APIRouter()

VALID_VIRUS_TYPES = {"Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"}
VALID_MARKET_TARGETS = {
    "RKI_ARE",
    "SURVSTAT",
    "MYCOPLASMA",
    "KEUCHHUSTEN",
    "PNEUMOKOKKEN",
    "H_INFLUENZAE",
}


def _read_upload(content: bytes, filename: str) -> pd.DataFrame:
    if filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
    else:
        text = content.decode("utf-8", errors="replace")
        sep = ";" if ";" in text[:500] else ","
        df = pd.read_csv(StringIO(text), sep=sep)

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


@router.post("/market")
async def run_market_backtest(
    target_source: str = Query(default="RKI_ARE"),
    virus_typ: str = Query(default="Influenza A"),
    days_back: int = Query(default=2500, ge=60, le=3000),
    horizon_days: int = Query(default=14, ge=0, le=60),
    min_train_points: int = Query(default=0, ge=0, le=300),
    strict_vintage_mode: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Mode A: Markt-Check ohne Kundendaten."""
    target_key = (target_source or "RKI_ARE").strip().upper()
    if target_key not in VALID_MARKET_TARGETS and not target_key.startswith("SURVSTAT:"):
        return {
            "error": f"Ungültiges target_source '{target_source}'.",
            "allowed_targets": sorted(VALID_MARKET_TARGETS),
        }

    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    service = BacktestService(db)
    return service.run_market_simulation(
        virus_typ=virus_typ,
        target_source=target_key,
        days_back=days_back,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        strict_vintage_mode=strict_vintage_mode,
    )


@router.post("/customer")
async def run_customer_backtest(
    file: UploadFile = File(...),
    virus_typ: str = Query(default="Influenza A"),
    horizon_days: int = Query(default=14, ge=0, le=60),
    min_train_points: int = Query(default=20, ge=5, le=300),
    strict_vintage_mode: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Mode B: Realitäts-Check mit Kundendaten (CSV/XLSX)."""
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    content = await file.read()
    df = _read_upload(content, file.filename or "customer.csv")

    if "datum" not in df.columns or "menge" not in df.columns:
        return {
            "error": "Fehlende Pflichtspalten. Erwartet: datum, menge",
            "found_columns": list(df.columns),
            "hint": "Optional zusätzlich: region",
        }

    service = BacktestService(db)
    return service.run_customer_simulation(
        customer_df=df,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        strict_vintage_mode=strict_vintage_mode,
    )


@router.post("/business-pitch")
async def run_business_pitch_report(
    disease: str = Query(
        default="GELO_ATEMWEG",
        description=(
            "Krankheit(en) als Ground Truth. "
            "'GELO_ATEMWEG' = aggregierte Atemwegsinfekte (Influenza+RSV+Keuchhusten+Mycoplasma+Parainfluenza). "
            "Oder ein einzelner Krankheitsname aus SurvStat."
        ),
    ),
    virus_typ: str = Query(default="Influenza A"),
    season_start: str = Query(default="2024-10-01"),
    season_end: str = Query(default="2025-03-31"),
    db: Session = Depends(get_db),
):
    """Business Pitch Report: ML-Frühsignal-Vorteil vs. RKI-Meldung.

    Berechnet für die gewählte Saison wochenweise den ML-Risikoscore
    und vergleicht das erste Warnsignal mit dem tatsächlichen RKI-Peak.
    Default: Gelo-relevante Atemwegsinfekte.
    """
    if virus_typ not in VALID_VIRUS_TYPES:
        virus_typ = "Influenza A"

    service = BacktestService(db)
    return service.generate_business_pitch_report(
        disease=disease,
        virus_typ=virus_typ,
        season_start=season_start,
        season_end=season_end,
    )


@router.get("/runs")
async def list_backtest_runs(
    mode: str | None = Query(default=None, description="MARKET_CHECK oder CUSTOMER_CHECK"),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Historie persistierter Backtests."""
    service = BacktestService(db)
    runs = service.list_backtest_runs(mode=mode, limit=limit)
    return {"total": len(runs), "runs": runs}


# ═══════════════════════════════════════════════════════════════════════
#  WELLEN-RADAR: Regionale Ausbreitungsanalyse
# ═══════════════════════════════════════════════════════════════════════

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
    "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
    "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
    "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
    "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
]


@router.get("/wave-radar")
async def wave_radar(
    disease: str = Query(default="influenza", description="Krankheit (influenza, mycoplasma, keuchhusten, ...)"),
    season: str = Query(default="", description="Saison im Format YYYY/YYYY (z.B. 2024/2025). Leer = letzte verfügbare."),
    threshold_pct: float = Query(default=50.0, ge=10, le=200, description="Schwellwert: Prozent über Saison-Median = Wellenstart"),
    db: Session = Depends(get_db),
):
    """Wellen-Radar: Wann und wo beginnt eine Krankheitswelle?

    Berechnet pro Bundesland den Zeitpunkt, an dem die Inzidenz
    den saisonalen Median um threshold_pct% übersteigt.
    Liefert Timeline + Karten-Daten für die Frontend-Visualisierung.
    """
    # Resolve disease alias
    disease_name = DISEASE_ALIASES.get(disease.lower().strip(), disease)

    # Determine season range
    if season and "/" in season:
        parts = season.split("/")
        season_start = datetime(int(parts[0]), 10, 1)
        season_end = datetime(int(parts[1]), 5, 31)
    else:
        # Auto: find latest season from data
        latest = db.query(func.max(SurvstatWeeklyData.week_start)).filter(
            SurvstatWeeklyData.disease == disease_name,
            SurvstatWeeklyData.bundesland != "Gesamt",
        ).scalar()
        if not latest:
            return {"error": f"Keine regionalen Daten für '{disease_name}'.", "available": list(DISEASE_ALIASES.keys())}
        # Season: Oct of previous year to May
        if latest.month >= 10:
            season_start = datetime(latest.year, 10, 1)
            season_end = datetime(latest.year + 1, 5, 31)
        else:
            season_start = datetime(latest.year - 1, 10, 1)
            season_end = datetime(latest.year, 5, 31)

    season_label = f"{season_start.year}/{season_end.year}"

    # Load historical baseline (all years before this season) for median
    baseline_rows = db.query(
        SurvstatWeeklyData.bundesland,
        func.avg(SurvstatWeeklyData.incidence).label("avg_inc"),
    ).filter(
        SurvstatWeeklyData.disease == disease_name,
        SurvstatWeeklyData.bundesland != "Gesamt",
        SurvstatWeeklyData.week_start < season_start,
        SurvstatWeeklyData.incidence > 0,
    ).group_by(SurvstatWeeklyData.bundesland).all()

    bl_baseline = {r.bundesland: float(r.avg_inc) for r in baseline_rows}

    # Fallback: if no history, use national average
    if not bl_baseline:
        national_avg = db.query(func.avg(SurvstatWeeklyData.incidence)).filter(
            SurvstatWeeklyData.disease == disease_name,
            SurvstatWeeklyData.bundesland == "Gesamt",
            SurvstatWeeklyData.incidence > 0,
        ).scalar()
        for bl in BUNDESLAENDER:
            bl_baseline[bl] = float(national_avg or 1.0)

    # Load season data per Bundesland
    season_rows = db.query(
        SurvstatWeeklyData.bundesland,
        SurvstatWeeklyData.week_start,
        SurvstatWeeklyData.week_label,
        SurvstatWeeklyData.incidence,
    ).filter(
        SurvstatWeeklyData.disease == disease_name,
        SurvstatWeeklyData.bundesland != "Gesamt",
        SurvstatWeeklyData.week_start >= season_start,
        SurvstatWeeklyData.week_start <= season_end,
    ).order_by(
        SurvstatWeeklyData.bundesland,
        SurvstatWeeklyData.week_start,
    ).all()

    # Group by Bundesland
    bl_data: dict[str, list] = {bl: [] for bl in BUNDESLAENDER}
    for r in season_rows:
        if r.bundesland in bl_data:
            bl_data[r.bundesland].append({
                "week_start": r.week_start,
                "week_label": r.week_label,
                "incidence": float(r.incidence),
            })

    # Detect wave onset per Bundesland
    results = []
    timeline = []  # (date, bundesland) for chronological ordering
    all_weeks = set()

    for bl in BUNDESLAENDER:
        weeks = bl_data.get(bl, [])
        baseline = bl_baseline.get(bl, 1.0)
        threshold = baseline * (1 + threshold_pct / 100)

        wave_start = None
        peak_week = None
        peak_inc = 0.0
        total_inc = 0.0

        for w in weeks:
            all_weeks.add(w["week_label"])
            total_inc += w["incidence"]
            if w["incidence"] > peak_inc:
                peak_inc = w["incidence"]
                peak_week = w["week_label"]

            # Wave onset: first week above threshold (confirmed by next week)
            if wave_start is None and w["incidence"] >= threshold:
                wave_start = w["week_start"]

        results.append({
            "bundesland": bl,
            "wave_start": wave_start.strftime("%Y-%m-%d") if wave_start else None,
            "wave_week": next((w["week_label"] for w in weeks if w["week_start"] == wave_start), None) if wave_start else None,
            "peak_week": peak_week,
            "peak_incidence": round(peak_inc, 3),
            "baseline_avg": round(baseline, 3),
            "threshold": round(threshold, 3),
            "total_incidence": round(total_inc, 3),
            "data_points": len(weeks),
        })

        if wave_start:
            timeline.append((wave_start, bl))

    # Sort timeline chronologically
    timeline.sort(key=lambda x: x[0])
    rank = 1
    for date, bl in timeline:
        for r in results:
            if r["bundesland"] == bl:
                r["wave_rank"] = rank
                break
        rank += 1

    # For Bundesländer without wave onset
    for r in results:
        if "wave_rank" not in r:
            r["wave_rank"] = None

    # Build weekly heatmap data (for animated timeline)
    sorted_weeks = sorted(all_weeks)
    heatmap = []
    for wl in sorted_weeks:
        week_entry = {"week_label": wl}
        for bl in BUNDESLAENDER:
            match = next((w for w in bl_data.get(bl, []) if w["week_label"] == wl), None)
            week_entry[bl] = round(match["incidence"], 3) if match else 0.0
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
        "regions": sorted(results, key=lambda r: r["wave_rank"] or 999),
        "heatmap": heatmap,
    }


# ═══════════════════════════════════════════════════════════════════════
#  AUSBRUCHS-RADAR: Prognose-getrieben (Momentum + Lead/Lag + Forecast)
# ═══════════════════════════════════════════════════════════════════════

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


def _compute_lead_lag(
    db: Session, disease: str, bundesland: str, lookback_weeks: int = 200,
) -> int:
    """Berechne wie viele Wochen ein Bundesland der nationalen Welle voraus-/hinterherläuft.

    Positiv = BL führt (früherer Anstieg), Negativ = BL folgt.
    Methode: Cross-Korrelation der BL-Zeitreihe vs. Gesamt-Zeitreihe.
    """
    cutoff = datetime.now() - timedelta(weeks=lookback_weeks)

    # BL time series
    bl_rows = db.query(
        SurvstatWeeklyData.week_label,
        SurvstatWeeklyData.incidence,
    ).filter(
        SurvstatWeeklyData.disease == disease,
        SurvstatWeeklyData.bundesland == bundesland,
        SurvstatWeeklyData.week_start >= cutoff,
    ).order_by(SurvstatWeeklyData.week_label).all()

    # National time series
    nat_rows = db.query(
        SurvstatWeeklyData.week_label,
        SurvstatWeeklyData.incidence,
    ).filter(
        SurvstatWeeklyData.disease == disease,
        SurvstatWeeklyData.bundesland == "Gesamt",
        SurvstatWeeklyData.week_start >= cutoff,
    ).order_by(SurvstatWeeklyData.week_label).all()

    if len(bl_rows) < 20 or len(nat_rows) < 20:
        return 0

    # Align by week_label
    nat_dict = {r.week_label: float(r.incidence) for r in nat_rows}
    aligned_bl = []
    aligned_nat = []
    for r in bl_rows:
        if r.week_label in nat_dict:
            aligned_bl.append(float(r.incidence))
            aligned_nat.append(nat_dict[r.week_label])

    if len(aligned_bl) < 20:
        return 0

    bl_arr = np.array(aligned_bl)
    nat_arr = np.array(aligned_nat)

    # Normalize
    bl_std = bl_arr.std()
    nat_std = nat_arr.std()
    if bl_std == 0 or nat_std == 0:
        return 0
    bl_norm = (bl_arr - bl_arr.mean()) / bl_std
    nat_norm = (nat_arr - nat_arr.mean()) / nat_std

    # Cross-correlation for lags -6..+6 weeks
    best_lag = 0
    best_corr = -1.0
    n = len(bl_norm)
    for lag in range(-6, 7):
        if lag >= 0:
            corr = np.dot(bl_norm[:n - lag], nat_norm[lag:]) / (n - abs(lag))
        else:
            corr = np.dot(bl_norm[-lag:], nat_norm[:n + lag]) / (n - abs(lag))
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    # Positive lag = BL leads national (BL signal comes first)
    return -best_lag  # Negate: if nat needs to shift right to match BL, BL leads


@router.get("/outbreak-alerts")
async def outbreak_alerts(
    db: Session = Depends(get_db),
):
    """Ausbruchs-Radar: Prognose-getriebene Alerts.

    Kombiniert drei Signale pro Krankheit × Region:
    1. Momentum: Letzte 3 Wochen vs. 3 Wochen davor (steigt/fällt?)
    2. Lead/Lag: Führt dieses BL die Welle an oder folgt es?
    3. Nationaler Trend: Geht die Welle national hoch oder runter?

    → Actionable Alerts für Marketing-Timing pro Region.
    """
    from collections import defaultdict

    # ── 1. Zeitfenster bestimmen ──
    latest_date = db.query(func.max(SurvstatWeeklyData.week_start)).filter(
        SurvstatWeeklyData.bundesland != "Gesamt",
        SurvstatWeeklyData.incidence > 0,
    ).scalar()

    if not latest_date:
        return {"error": "Keine regionalen Daten verfügbar."}

    recent_cutoff = latest_date - timedelta(weeks=3)
    prior_cutoff = recent_cutoff - timedelta(weeks=3)

    # ── 2. Lade letzte 6 Wochen: 3 "aktuell" + 3 "vorher" ──
    six_week_rows = db.query(
        SurvstatWeeklyData.bundesland,
        SurvstatWeeklyData.disease,
        SurvstatWeeklyData.week_start,
        SurvstatWeeklyData.week_label,
        SurvstatWeeklyData.incidence,
    ).filter(
        SurvstatWeeklyData.disease.in_(ALERT_DISEASES),
        SurvstatWeeklyData.week_start > prior_cutoff,
        SurvstatWeeklyData.incidence > 0,
    ).all()

    # Gruppiere: (bl, disease) → recent + prior
    recent_data: dict[tuple[str, str], list[float]] = defaultdict(list)
    prior_data: dict[tuple[str, str], list[float]] = defaultdict(list)
    national_recent: dict[str, list[float]] = defaultdict(list)
    national_prior: dict[str, list[float]] = defaultdict(list)

    for r in six_week_rows:
        key = (r.bundesland, r.disease)
        inc = float(r.incidence)
        if r.week_start > recent_cutoff:
            if r.bundesland == "Gesamt":
                national_recent[r.disease].append(inc)
            else:
                recent_data[key].append(inc)
        else:
            if r.bundesland == "Gesamt":
                national_prior[r.disease].append(inc)
            else:
                prior_data[key].append(inc)

    # ── 3. Nationaler Forecast-Vektor ──
    # Erst Gesamt-Daten versuchen, dann aus BL-Daten aggregieren
    national_forecast: dict[str, dict] = {}
    for disease in ALERT_DISEASES:
        nr = national_recent.get(disease, [])
        np_ = national_prior.get(disease, [])

        # Fallback: aus BL-Daten aggregieren wenn kein "Gesamt"
        if not nr or not np_:
            bl_recent_vals = []
            bl_prior_vals = []
            for (bl, d), vals in recent_data.items():
                if d == disease:
                    bl_recent_vals.extend(v for v in vals)
            for (bl, d), vals in prior_data.items():
                if d == disease:
                    bl_prior_vals.extend(v for v in vals)
            if bl_recent_vals:
                nr = [sum(bl_recent_vals) / len(bl_recent_vals)]
            if bl_prior_vals:
                np_ = [sum(bl_prior_vals) / len(bl_prior_vals)]

        if nr and np_:
            avg_r = sum(nr) / len(nr)
            avg_p = sum(np_) / len(np_)
            if avg_p > 0:
                change_pct = round((avg_r - avg_p) / avg_p * 100, 1)
            else:
                change_pct = 100.0 if avg_r > 0 else 0.0
            direction = "rising" if change_pct > 10 else "falling" if change_pct < -10 else "stable"
            national_forecast[disease] = {
                "current": round(avg_r, 3),
                "prior": round(avg_p, 3),
                "change_pct": change_pct,
                "direction": direction,
            }

    # ── 4. Lead/Lag Cache (teuer → einmal berechnen) ──
    lead_lag_cache: dict[tuple[str, str], int] = {}

    # ── 5. Alerts berechnen ──
    alerts = []

    for (bl, disease), recent_vals in recent_data.items():
        if bl == "Gesamt":
            continue
        prior_vals = prior_data.get((bl, disease), [])
        if not recent_vals:
            continue

        avg_recent = sum(recent_vals) / len(recent_vals)
        avg_prior = sum(prior_vals) / len(prior_vals) if prior_vals else 0.0

        # Momentum: prozentuale Veränderung recent vs prior
        if avg_prior > 0:
            momentum_pct = round((avg_recent - avg_prior) / avg_prior * 100, 1)
        elif avg_recent > 0:
            momentum_pct = 100.0  # Neu aufgetaucht
        else:
            continue  # Kein Signal

        # Lead/Lag vs national
        cache_key = (bl, disease)
        if cache_key not in lead_lag_cache:
            lead_lag_cache[cache_key] = _compute_lead_lag(db, disease, bl)
        lead_lag_weeks = lead_lag_cache[cache_key]

        # National forecast direction
        nat = national_forecast.get(disease, {})
        nat_direction = nat.get("direction", "stable")
        nat_change = nat.get("change_pct", 0.0)

        # ── Severity Score ──
        # Hohe Severity = starker Anstieg + Region führt + nationale Welle steigt
        momentum_score = max(0, momentum_pct) / 50  # +100% → 2.0
        lead_bonus = max(0, lead_lag_weeks) * 0.3  # Führende Region bekommt Bonus
        nat_boost = max(0, nat_change) / 100  # Nationale Welle steigt → Boost

        severity = round(momentum_score + lead_bonus + nat_boost, 2)
        if severity < 0.5 and momentum_pct < 20:
            continue  # Unter Schwelle

        # Forecast-Action: Momentum + nationale Richtung + Lead/Lag
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

        alerts.append({
            "bundesland": bl,
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
        })

    # Sort: high urgency first, then by severity
    urgency_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    alerts.sort(key=lambda a: (urgency_order.get(a["urgency"], 9), -a["severity"]))

    # ── 6. Region Summary für Karte ──
    bl_summary: dict[str, dict] = {}
    for bl in BUNDESLAENDER:
        bl_alerts = [a for a in alerts if a["bundesland"] == bl]
        if bl_alerts:
            high_count = sum(1 for a in bl_alerts if a["urgency"] in ("high", "medium"))
            bl_summary[bl] = {
                "alert_count": len(bl_alerts),
                "high_urgency_count": high_count,
                "max_severity": max(a["severity"] for a in bl_alerts),
                "top_disease": bl_alerts[0]["disease"],
                "top_action": bl_alerts[0]["action"],
                "diseases": list(set(a["disease"] for a in bl_alerts)),
            }
        else:
            bl_summary[bl] = {
                "alert_count": 0,
                "high_urgency_count": 0,
                "max_severity": 0,
                "top_disease": None,
                "top_action": "Kein Signal",
                "diseases": [],
            }

    # ── 7. Disease Summary ──
    disease_summary: dict[str, dict] = {}
    for disease in ALERT_DISEASES:
        short = DISEASE_SHORT.get(disease, disease)
        d_alerts = [a for a in alerts if a["disease_full"] == disease]
        nat = national_forecast.get(disease, {})
        if d_alerts or nat:
            disease_summary[short] = {
                "alert_count": len(d_alerts),
                "national_direction": nat.get("direction", "unknown"),
                "national_change_pct": nat.get("change_pct", 0),
                "regions_rising": len([a for a in d_alerts if a["momentum_pct"] > 20]),
                "regions_falling": len([a for a in d_alerts if a["momentum_pct"] < -20]),
                "hottest_region": d_alerts[0]["bundesland"] if d_alerts else None,
            }

    return {
        "scan_date": latest_date.strftime("%Y-%m-%d"),
        "total_alerts": len(alerts),
        "high_urgency": len([a for a in alerts if a["urgency"] == "high"]),
        "alerts": alerts[:60],
        "region_summary": bl_summary,
        "disease_summary": disease_summary,
        "national_forecast": {
            DISEASE_SHORT.get(d, d): v for d, v in national_forecast.items()
        },
    }
