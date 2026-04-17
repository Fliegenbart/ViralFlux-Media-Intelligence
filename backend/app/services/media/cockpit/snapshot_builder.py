"""peix cockpit snapshot builder — honest wiring over existing model outputs.

Built on 2026-04-16 after the math audit (see ~/peix-math-audit.md).
Design principles:

* **No invented numbers.** Every field the frontend renders is either
  (a) pulled from a real model output / DB query, or
  (b) explicitly null with a `notes` entry explaining why.
* **No calibration claims unless calibration happened.** `model_status.calibration_mode`
  is set to `"heuristic"` when the upstream event-score is
  `heuristic_event_score_only`; the frontend uses that to relabel
  "Konfidenz" as "Signalstärke".
* **No media-plan invention.** `mediaPlan.connected` is false in this
  version because GELO's media plan is not connected to the backend yet;
  all EUR-denominated fields are null.
* **Regional honesty.** If the virus has no regional model (as of
  2026-04-16 this is the case for RSV A), `regions` is empty and a note
  explains it.

This module is intentionally read-only — it does not touch any ingestion,
retraining, or mutation paths.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.database import BacktestRun, MLForecast
from app.services.media.cockpit.freshness import (
    build_data_freshness,
    build_source_status,
)


BUNDESLAND_NAMES: dict[str, str] = {
    "SH": "Schleswig-Holstein",
    "HH": "Hamburg",
    "NI": "Niedersachsen",
    "HB": "Bremen",
    "NW": "Nordrhein-Westfalen",
    "HE": "Hessen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "MV": "Mecklenburg-Vorpommern",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "TH": "Thüringen",
}

# Regional XGBoost artefacts that actually exist on disk (see /app/app/ml_models/regional).
_REGIONAL_VIRUSES = {"Influenza A"}

SOURCE_HEALTH_MAP: dict[str, str] = {
    "live": "good",
    "stale": "delayed",
    "no_data": "stale",
}


def _normalize_freshness_timestamp(
    value: datetime | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Mirror of MediaCockpitService._normalize_freshness_timestamp."""
    if value is None:
        return None
    effective_now = now or utc_now()
    normalized = value
    if normalized.tzinfo is not None:
        normalized = normalized.replace(tzinfo=None)
    if normalized > effective_now:
        normalized = effective_now
    return normalized.isoformat()


def _parse_virus_label(virus_typ: str) -> str:
    labels = {
        "RSV A": "RSV",
        "Influenza A": "Influenza A",
        "Influenza B": "Influenza B",
        "SARS-CoV-2": "SARS-CoV-2",
    }
    return labels.get(virus_typ, virus_typ)


def _iso_week_label(at: datetime) -> str:
    iso = at.isocalendar()
    return f"KW {iso.week:02d} / {iso.year}"


def _extract_model_status(
    db: Session,
    virus_typ: str,
    horizon_days: int,
) -> dict[str, Any]:
    """Pull the latest backtest run for the given scope and surface its gate.

    Looked up from the `backtest_runs` table. Fields that don't exist in the
    backtest payload are returned as None — never guessed.
    """
    # Newest successful backtest for this virus/horizon/RKI_ARE target.
    row: BacktestRun | None = (
        db.query(BacktestRun)
        .filter(
            BacktestRun.virus_typ == virus_typ,
            BacktestRun.horizon_days == int(horizon_days),
            BacktestRun.status == "success",
            BacktestRun.target_source == "RKI_ARE",
        )
        .order_by(desc(BacktestRun.created_at))
        .first()
    )

    metrics: dict[str, Any] = dict((row.metrics if row else None) or {})
    baseline_cmp: dict[str, Any] = dict((row.improvement_vs_baselines if row else None) or {})

    quality_gate = metrics.get("quality_gate") or {}
    timing = metrics.get("timing_metrics") or {}
    coverage = metrics.get("interval_coverage") or {}
    event_cal = metrics.get("event_calibration") or {}

    skip_reason = str(event_cal.get("skip_reason") or "").strip()
    method = str(event_cal.get("calibration_method") or "").strip()
    if skip_reason == "heuristic_event_score_only" or method == "skipped_heuristic_event_score":
        # Production path as of 2026-04-16: event score is a sigmoid-of-z
        # heuristic, but we DO produce and use a score — so "heuristic" is
        # the operationally honest label, not "skipped".
        calibration_mode = "heuristic"
    elif event_cal.get("calibration_skipped"):
        calibration_mode = "skipped"
    elif method:
        calibration_mode = "heuristic" if method.startswith("skipped_") else "calibrated"
    else:
        calibration_mode = "unknown"

    readiness_raw = str(quality_gate.get("forecast_readiness") or "").strip().upper()
    forecast_readiness = readiness_raw if readiness_raw in {"GO", "WATCH", "HOLD"} else "UNKNOWN"

    regional_available = virus_typ in _REGIONAL_VIRUSES

    note_parts: list[str] = []
    if calibration_mode in {"heuristic", "skipped"}:
        note_parts.append(
            "Signalwerte sind aktuell nicht kalibriert — als Signalstärke lesen, nicht als Wahrscheinlichkeit."
        )
    if not regional_available:
        note_parts.append(
            f"Für {virus_typ} liegt aktuell kein regionales Modell vor — wir zeigen den nationalen Forecast."
        )
    if quality_gate.get("baseline_passed") is False:
        note_parts.append(
            "Punktprognose-Metrik liegt aktuell auf Niveau der Persistence-Baseline — das Modell ist für Ranking-Entscheidungen einsetzbar, nicht für Absolut-Werte."
        )

    training_window_end = None
    # BacktestRun doesn't carry training_window_end directly; we try to derive
    # from the `end` of the backtest date range as a proxy.
    date_range = metrics.get("date_range") or {}
    if date_range.get("end"):
        training_window_end = str(date_range.get("end"))

    # IMPORTANT: the frontend reads these keys as camelCase (virusTyp,
    # horizonDays, forecastReadiness, ...). Returning snake_case silently
    # turned every field into `undefined` in the UI, which is how the
    # 2026-04-17 "H= · Kalibrierung: UNBEKANNT" header bug came to be. Keep
    # this contract camelCase-consistent with types.ts::ModelStatus.
    return {
        "virusTyp": virus_typ,
        "horizonDays": int(horizon_days),
        "forecastReadiness": forecast_readiness,
        "overallPassed": bool(quality_gate.get("overall_passed") or False),
        "baselinePassed": bool(quality_gate.get("baseline_passed") or False),
        "bestLagDays": _optional_int(timing.get("best_lag_days")),
        "correlationAtHorizon": _optional_float(timing.get("corr_at_horizon")),
        "maeVsPersistencePct": _optional_float(baseline_cmp.get("mae_vs_persistence_pct")),
        "calibrationMode": calibration_mode,
        "intervalCoverage80Pct": _optional_float(coverage.get("coverage_80_pct")),
        "intervalCoverage95Pct": _optional_float(coverage.get("coverage_95_pct")),
        "trainingWindowEnd": training_window_end,
        "regionalAvailable": regional_available,
        "note": " ".join(note_parts) if note_parts else None,
    }


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_sources(db: Session) -> list[dict[str, Any]]:
    data_freshness = build_data_freshness(
        db, normalize_freshness_timestamp=_normalize_freshness_timestamp
    )
    source_status = build_source_status(data_freshness)
    sources: list[dict[str, Any]] = []
    for item in source_status.get("items") or []:
        last_updated = item.get("last_updated")
        age_days = item.get("age_days")
        freshness = str(item.get("freshness_state") or "no_data")
        sources.append(
            {
                "name": item.get("label") or item.get("source_key"),
                "lastUpdate": last_updated,
                "latencyDays": int(age_days) if isinstance(age_days, (int, float)) else 0,
                "health": SOURCE_HEALTH_MAP.get(freshness, "stale"),
                "note": None,
            }
        )
    return sources


def _map_region_predictions(
    regional_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Map service.predict_all_regions() output to the CockpitSnapshot regions[]."""
    notes: list[str] = []
    predictions = regional_payload.get("predictions") or []
    status = regional_payload.get("status")
    if status and status != "success":
        notes.append(
            f"Regional-Forecast-Status: {status} — {regional_payload.get('message') or 'kein regionaler Forecast verfügbar'}."
        )
        return [], notes

    mapped: list[dict[str, Any]] = []
    for pred in predictions:
        bl_code = str(pred.get("bundesland") or "").strip()
        if bl_code not in BUNDESLAND_NAMES:
            continue
        interval = pred.get("prediction_interval") or {}
        expected = pred.get("expected_next_week_incidence")
        q50 = _optional_float(expected)
        q10 = _optional_float(interval.get("lower"))
        q90 = _optional_float(interval.get("upper"))
        # Normalise so 100 = today's observed. We intentionally do NOT invent
        # a "today" baseline; when normalisation isn't possible we pass raw.
        norm_forecast: dict[str, float] | None = None
        if q10 is not None and q50 is not None and q90 is not None and q50 != 0:
            norm_forecast = {
                "q10": round(q10 / q50 * 100.0, 1),
                "q50": 100.0,
                "q90": round(q90 / q50 * 100.0, 1),
            }
        # Regional service returns change_pct in PERCENT, not ratio.
        change_pct_raw = pred.get("change_pct")
        delta7d: float | None = None
        if change_pct_raw is not None:
            try:
                delta7d = round(float(change_pct_raw) / 100.0, 4)
            except (TypeError, ValueError):
                delta7d = None
        # Fallbacks if change_pct is missing.
        if delta7d is None:
            delta7d = _optional_float(pred.get("delta_next_week_vs_current"))
        if delta7d is None:
            current = pred.get("current_known_incidence") or pred.get("current_incidence") or pred.get("current_load")
            if current and q50 is not None and float(current) > 0:
                delta7d = round((q50 / float(current)) - 1.0, 4)

        # reason_trace exposes "why" (list[str]) as the human-readable driver
        # list. Older code referred to a "signals" key which does not exist
        # on the live payload; we keep it as a fallback for safety.
        reason_trace = pred.get("reason_trace") or {}
        drivers: list[str] = []
        why_list = reason_trace.get("why") or []
        for entry in why_list[:3]:
            text = str(entry or "").strip()
            if text:
                drivers.append(text)
        if not drivers:
            for driver in (reason_trace.get("signals") or [])[:3]:
                if isinstance(driver, dict):
                    message = str(driver.get("message") or "").strip()
                    if message:
                        drivers.append(message)

        decision = pred.get("decision") or {}
        decision_label = str(pred.get("decision_label") or decision.get("label") or "").strip() or None
        if decision_label not in {"Watch", "Prepare", "Activate"}:
            decision_label = None

        mapped.append(
            {
                "code": bl_code,
                "name": BUNDESLAND_NAMES[bl_code],
                "delta7d": delta7d,
                "pRising": _optional_float(pred.get("event_probability")),
                "forecast": norm_forecast,
                "drivers": drivers,
                "currentSpendEur": None,
                "recommendedShiftEur": None,
                "decisionLabel": decision_label,
            }
        )
    return mapped, notes


def _build_timeline_from_national(
    db: Session,
    virus_typ: str,
    horizon_days: int,
) -> list[dict[str, Any]]:
    """Build a 21-day timeline (-14..+7) from the ml_forecasts table.

    Observed values are deliberately left null here; the frontend will plot
    past `q50` as nowcast where observed is missing.
    """
    rows: list[MLForecast] = (
        db.query(MLForecast)
        .filter(MLForecast.virus_typ == virus_typ)
        .order_by(desc(MLForecast.forecast_date))
        .limit(30)
        .all()
    )
    if not rows:
        return []

    today = utc_now().date()
    by_date: dict[str, MLForecast] = {}
    for row in rows:
        if not row.forecast_date:
            continue
        by_date[row.forecast_date.date().isoformat()] = row

    timeline: list[dict[str, Any]] = []
    for offset in range(-14, horizon_days + 1):
        target_date = today.fromordinal(today.toordinal() + offset)
        iso = target_date.isoformat()
        row = by_date.get(iso)
        q50 = _optional_float(row.predicted_value) if row else None
        q10 = _optional_float(row.lower_bound) if row else None
        q90 = _optional_float(row.upper_bound) if row else None
        timeline.append(
            {
                "date": iso,
                "observed": q50 if offset <= 0 else None,
                "nowcast": q50 if -14 <= offset <= 0 else None,
                "q10": q10,
                "q50": q50,
                "q90": q90,
                "horizonDays": offset,
            }
        )
    return timeline


def build_cockpit_snapshot(
    db: Session,
    *,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    client: str = "GELO",
    brand: str | None = None,
    regional_forecast_service=None,
) -> dict[str, Any]:
    """Assemble a :class:`CockpitSnapshot` payload for the given scope.

    Parameters
    ----------
    db
        SQLAlchemy session (read-only usage).
    virus_typ
        Virus whose snapshot to build. Must match backtest_runs.virus_typ
        (e.g. ``"RSV A"``, ``"Influenza A"``).
    horizon_days
        Forecast horizon. Fixed at 7 for the current champion scopes.
    client
        Client label shown in the UI, purely cosmetic.
    brand
        Brand passthrough for the regional forecast service; defaults to a
        neutral ``"default"`` so we don't invent GELO-specific behaviour.
    regional_forecast_service
        Optional callable returning the regional forecast payload. Injected
        for testability. When omitted the real RegionalForecastService is
        used.
    """
    generated_at = utc_now()
    model_status = _extract_model_status(db, virus_typ, horizon_days)

    notes: list[str] = []
    regions: list[dict[str, Any]] = []
    if model_status["regionalAvailable"]:
        if regional_forecast_service is None:
            from app.services.ml.regional_forecast import RegionalForecastService

            service = RegionalForecastService(db)
            regional_payload = service.predict_all_regions(
                virus_typ=virus_typ,
                brand=brand or "default",
                horizon_days=horizon_days,
            )
        else:
            regional_payload = regional_forecast_service(
                virus_typ=virus_typ,
                brand=brand or "default",
                horizon_days=horizon_days,
            )
        regions, region_notes = _map_region_predictions(regional_payload)
        notes.extend(region_notes)
    else:
        notes.append(
            f"Für {virus_typ} gibt es aktuell kein regionales Modell — Bundesländer-Ansicht deaktiviert."
        )

    timeline = _build_timeline_from_national(db, virus_typ, horizon_days)

    if model_status["calibrationMode"] in {"heuristic", "skipped"}:
        notes.append(
            "Die Signalstärke pro Bundesland ist ein Ranking-Score auf Skala 0–1, keine kalibrierte "
            "Wahrscheinlichkeit. Volle Kalibrierung gegen echte Verkaufsdaten entsteht sobald der "
            "Feedback-Loop läuft."
        )

    p_values = [r.get("pRising") for r in regions if r.get("pRising") is not None]
    average_confidence = round(sum(p_values) / len(p_values), 4) if p_values else None

    sources = _build_sources(db)

    top_drivers: list[dict[str, str]] = []
    # Pull top driver labels from the first few regions' reason_trace,
    # de-duplicated.
    seen = set()
    for region in regions:
        for driver in region.get("drivers") or []:
            if driver not in seen:
                seen.add(driver)
                top_drivers.append({"label": driver, "value": ""})
            if len(top_drivers) >= 4:
                break
        if len(top_drivers) >= 4:
            break

    return {
        "client": client,
        "virusTyp": virus_typ,
        "virusLabel": _parse_virus_label(virus_typ),
        "isoWeek": _iso_week_label(generated_at),
        "generatedAt": generated_at.isoformat(),
        "totalSpendEur": None,
        "averageConfidence": average_confidence,
        "primaryRecommendation": None,
        "secondaryRecommendations": [],
        "regions": regions,
        "timeline": timeline,
        "sources": sources,
        "topDrivers": top_drivers,
        "modelStatus": model_status,
        "mediaPlan": {
            "connected": False,
            "totalWeeklySpendEur": None,
            "note": (
                "Kein Media-Plan verbunden. EUR-Werte werden als \"—\" dargestellt, "
                "bis der Plan eingelesen wird."
            ),
        },
        "notes": notes,
    }
