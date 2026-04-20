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

import json
import logging
from datetime import date as pd_date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.database import (
    AuditLog,
    BacktestRun,
    MLForecast,
    NotaufnahmeSyndromData,
    SurvstatWeeklyData,
)
from app.services.media.cockpit.freshness import (
    build_data_freshness,
    build_source_status,
)

logger = logging.getLogger(__name__)


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

# Regional panel artefacts that exist on disk today. Three architectures
# in parallel:
#   * Influenza A has per-Bundesland XGBoost artefacts under
#     ml_models/regional/influenza_a/<bl_code>/ (16/16 regions).
#   * Influenza B + RSV A have pooled panels under
#     ml_models/regional_panel/<slug>/horizon_7/ (cluster + national
#     regressors, no per-Bundesland split); the RegionalForecastService
#     still produces predictions per Bundesland via the pooled panel
#     when we enable the virus here. Missing Bundesländer get
#     TrainingPending placeholders in _map_region_predictions.
# A virus landing in this set signals "regional Ansicht freigeschaltet".
# The training-panel badge (see _read_training_panel) carries the
# honesty about N=57 so this list stays a pure enablement switch.
# SARS-CoV-2 stays out intentionally — drift + MAPE 168 % put it in
# shadow/watch-only mode (see REGIONAL_NON_PILOT_HORIZON_REASONS).
_REGIONAL_VIRUSES = {"Influenza A", "Influenza B", "RSV A"}

# Default horizon / target combination for the headline "2 weeks ahead vs
# Notaufnahme"-story. Configurable via the API query parameters, but these
# defaults produce the strongest honest claim the system can back up.
DEFAULT_LEAD_HORIZON_DAYS = 14
DEFAULT_LEAD_TARGET_SOURCE = "ATEMWEGSINDEX"
# BL ranking comes from the regional-panel training run, which only exists
# at the 7-day horizon. Not a product choice — that's where the artefacts are.
RANKING_HORIZON_DAYS = 7

TARGET_SOURCE_LABELS: dict[str, str] = {
    "ATEMWEGSINDEX": "Notaufnahme-Syndromsurveillance (AKTIN)",
    "RKI_ARE": "RKI-Meldewesen (ARE)",
    "SURVSTAT": "RKI SURVSTAT",
    "CUSTOMER_SALES": "Kunden-Verkaufsdaten",
}

# Which training-summary JSON carries the ranking metrics for each virus.
# These files are produced by the `run_h7_pilot_only_training.py` runs that
# the user approved on 2026-04-16. Missing summary = no ranking metrics;
# the UI falls back to an explicit "not available" state.
RANKING_SUMMARY_BY_VIRUS: dict[str, str] = {
    "Influenza A": "regional_panel_h7_pilot_only/influenza_calibration_summary.json",
    "Influenza B": "regional_panel_h7_pilot_only/influenza_calibration_summary.json",
    "RSV A": "regional_panel_h7_pilot_only/rsv_ranking_summary.json",
}
RANKING_SUMMARY_ROOT = Path("/app/app/ml_models")

SOURCE_HEALTH_MAP: dict[str, str] = {
    "live": "good",
    "stale": "delayed",
    "no_data": "stale",
}

# Readiness thresholds for _synthesize_readiness.
#
# These decide which banner state (GO_RANKING / RANKING_OK / LEAD_ONLY / WATCH)
# shows up in the cockpit top-bar. Both are **provisional intuitive defaults**
# chosen while scaffolding the UI on 2026-04-17. They are NOT backed by a
# ROC/precision-recall calibration against a business-relevant outcome yet.
#
# TODO (calibration Q2 2026, see ~/peix-math-deepdive.md finding #3):
#   * Define the business-relevant success event (e.g. "true top-5 actually
#     developed the wave in the subsequent window").
#   * Sweep the precision threshold across observed backtest history and pick
#     the value where precision_at_top3 crosses the business-value break-even.
#   * Replace this constant with the calibrated value plus a provenance note.
#
# In the meantime, 0.65 was picked because the retained Influenza A model
# currently reports ~0.78 precision_at_top3, and we wanted the banner to
# lean "RANKING_OK" by default rather than lock into GO_RANKING based on an
# uncalibrated signal. This is deliberately conservative, not validated.
RANKING_PRECISION_GO_THRESHOLD = 0.65
# best_lag_days >= 0 means the forecast does not lag behind the selected
# truth target. That's a structural condition — no calibration needed.
LEAD_LAG_GO_MIN_DAYS = 0


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


def _wave_probability_context(avg_p: float | None, iso_week_label: str) -> str:
    """Plain-German Einordnung der Wellen-Wahrscheinlichkeit.

    Ziel: einen Pharma-Entscheider davor bewahren, 0.023 als
    "Modell ist zu 2 % zuversichtlich" zu lesen. Der Wert ist
    der Mittelwert der regionalen Steige-Wahrscheinlichkeit; in
    Post-Saison-Wochen erwartungsgemäß niedrig — das ist ein
    Saison-Signal, kein Modell-Schwächesignal.
    """
    if avg_p is None:
        return "—"
    pct = avg_p * 100
    if pct >= 25:
        return f"Hoch — Peak-Wochen-Niveau ({pct:.1f} %)"
    if pct >= 10:
        return f"Erhöht — Welle baut auf ({pct:.1f} %)"
    if pct >= 5:
        return f"Moderat — Übergangs-Phase ({pct:.1f} %)"
    return (
        f"Niedrig — Post-Saison ({pct:.1f} %). Natürliches Saison-Tief, "
        "nicht Modell-Unsicherheit. Der Wert steigt automatisch ab KW 38 wieder."
    )


TRAINING_METADATA_ROOT = Path("/app/app/ml_models")

# Maturity thresholds for the "Phase-1 pilot / Beta / Production" badge.
# N = training_samples of the national XGBoost stack (per ml_models/<slug>/
# metadata.json). Set conservatively on 2026-04-20: RSV A is N=57 today and
# needs to land in "pilot"; Influenza A/B and SARS-CoV-2 sit at N≈103-113
# which is still "beta". A virus crosses into "production" at N≥200 — none
# today. Threshold review belongs into a calibration discussion once the
# outcome loop (T2.2) delivers real sell-through signals.
MATURITY_TIER_PILOT_MAX = 100
MATURITY_TIER_BETA_MAX = 200


# Forecast-trajectory honesty block. Today (2026-04-20) the direct-stacking
# model delivers a single T+7 endpoint; the seven daily points between
# current_y and T+7 are linearly interpolated with a sqrt-expanding
# uncertainty cone (see forecast_service_pipeline._expand_forecast_trajectory).
# The orchestrator already trains h=1..6 artefacts, but they are not wired
# into the cockpit path yet — hence `nativeHorizonsAvailable=False`.
# The snapshot exposes this explicitly so the cockpit-copy can say what it
# actually does instead of implying per-day native forecasts.
FORECAST_TRAJECTORY_SOURCE: dict[str, Any] = {
    "mode": "interpolated_from_h7_endpoint",
    "label": "7-Punkt-Trajektorie aus T+7-Modell",
    "detail": (
        "Das aktive Direct-Stacking-Modell liefert einen Endpunkt bei T+7. "
        "Die sechs Zwischenpunkte sind linear zwischen heute und T+7 "
        "interpoliert, der Unsicherheitskegel wächst mit √t proportional — "
        "keine neue Modell-Inferenz, sondern die ehrliche Rekonstruktion der "
        "Trajektorie aus dem Endpunkt-Forecast."
    ),
    "nativeHorizonsAvailable": False,
}


def _virus_metadata_slug(virus_typ: str) -> str:
    """Mirror forecast_service._virus_slug — keep them in sync."""
    return virus_typ.lower().replace(" ", "_").replace("-", "_")


def _classify_maturity(samples: int | None) -> tuple[str, str]:
    """Return (tier, label) for the training-panel badge.

    The label is rendered verbatim by the frontend; keep it compact so it
    fits into a card badge.
    """
    if samples is None:
        return ("unknown", "Kein Modell-Panel gefunden")
    if samples < MATURITY_TIER_PILOT_MAX:
        return ("pilot", f"Phase-1-Pilot · N={samples}")
    if samples < MATURITY_TIER_BETA_MAX:
        return ("beta", f"Beta-Pilot · N={samples}")
    return ("production", f"Produktiv · N={samples}")


def _read_training_panel(virus_typ: str) -> dict[str, Any]:
    """Expose the national training-panel metadata as an honest badge payload.

    Reads ``ml_models/<slug>/metadata.json`` — the artefact every live virus
    has — and maps ``training_samples`` into a coarse maturity tier. Never
    raises; missing or unreadable metadata returns an ``unknown`` block so
    the UI can still render, and operators get a visible flag.
    """
    slug = _virus_metadata_slug(virus_typ)
    meta_path = TRAINING_METADATA_ROOT / slug / "metadata.json"
    if not meta_path.exists():
        logger.info("training metadata not found for %s at %s", virus_typ, meta_path)
        tier, label = _classify_maturity(None)
        return {
            "trainingSamples": None,
            "maturityTier": tier,
            "maturityLabel": label,
            "trainedAt": None,
            "modelVersion": None,
        }
    try:
        data = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        logger.exception("failed to parse training metadata for %s at %s", virus_typ, meta_path)
        tier, label = _classify_maturity(None)
        return {
            "trainingSamples": None,
            "maturityTier": tier,
            "maturityLabel": label,
            "trainedAt": None,
            "modelVersion": None,
        }
    samples = _optional_int(data.get("training_samples"))
    tier, label = _classify_maturity(samples)
    return {
        "trainingSamples": samples,
        "maturityTier": tier,
        "maturityLabel": label,
        "trainedAt": str(data.get("trained_at") or "") or None,
        "modelVersion": str(data.get("version") or "") or None,
    }


def _read_ranking_metrics(virus_typ: str) -> dict[str, Any]:
    """Load the per-virus ranking metrics from the pilot training summary.

    The h7 pilot training writes one summary JSON per preset. This reads the
    baseline row (i.e. the live-retained model) for the requested virus and
    returns the headline ranking metrics — precisionAtTop3, pr_auc, ece.

    Returns an empty dict if the summary is missing or unparseable; the
    caller must be tolerant of missing fields.
    """
    path_frag = RANKING_SUMMARY_BY_VIRUS.get(virus_typ)
    if not path_frag:
        return {}
    full_path = RANKING_SUMMARY_ROOT / path_frag
    if not full_path.exists():
        logger.info("ranking summary not found for %s at %s", virus_typ, full_path)
        return {}
    try:
        data = json.loads(full_path.read_text())
    except (OSError, ValueError):
        logger.exception("failed to parse ranking summary for %s at %s", virus_typ, full_path)
        return {}
    viruses = data.get("viruses") or {}
    virus_data = viruses.get(virus_typ) or {}
    baseline = virus_data.get("baseline") or {}
    metrics = baseline.get("metrics") or {}
    return {
        "precisionAtTop3": _optional_float(metrics.get("precision_at_top3")),
        "prAuc": _optional_float(metrics.get("pr_auc")),
        "ece": _optional_float(metrics.get("ece")),
        "dataPoints": _optional_int(metrics.get("data_points") or metrics.get("alerts")),
        "trainedAt": str(data.get("generated_at") or "") or None,
    }


def _infer_calibration_mode(event_cal: dict[str, Any]) -> str:
    """Derive the calibration_mode label from a backtest event_calibration block."""
    skip_reason = str(event_cal.get("skip_reason") or "").strip()
    method = str(event_cal.get("calibration_method") or "").strip()
    if skip_reason == "heuristic_event_score_only" or method == "skipped_heuristic_event_score":
        return "heuristic"
    if event_cal.get("calibration_skipped"):
        return "skipped"
    if method:
        return "heuristic" if method.startswith("skipped_") else "calibrated"
    return "unknown"


def _lead_block_from_backtest(
    db: Session,
    *,
    virus_typ: str,
    horizon_days: int,
    target_source: str,
) -> dict[str, Any]:
    """Pull lead-time metrics (corr, lag, coverage) from the backtest_runs table.

    The "lead" block backs the public claim: we forecast X days ahead against
    a fast-truth signal (Notaufnahme, not RKI-Meldewesen). Returns a payload
    with best_lag_days=None and overallPassed=False when no matching backtest
    exists — never fabricates numbers.
    """
    row: BacktestRun | None = (
        db.query(BacktestRun)
        .filter(
            BacktestRun.virus_typ == virus_typ,
            BacktestRun.horizon_days == int(horizon_days),
            BacktestRun.status == "success",
            BacktestRun.target_source == target_source,
        )
        .order_by(desc(BacktestRun.created_at))
        .first()
    )
    metrics = dict((row.metrics if row else None) or {})
    improvement = dict((row.improvement_vs_baselines if row else None) or {})
    timing = metrics.get("timing_metrics") or {}
    quality_gate = metrics.get("quality_gate") or {}
    coverage = metrics.get("interval_coverage") or {}
    event_cal = metrics.get("event_calibration") or {}
    date_range = metrics.get("date_range") or {}

    # 2026-04-20 Tier-2-Fix: ATEMWEGSINDEX-Backtests haben aktuell
    # keine interval_coverage gespeichert; RKI_ARE-Runs für dieselbe
    # virus/horizon Kombination haben sie. Wenn coverage hier leer
    # ist, holen wir den letzten RKI_ARE-Backtest und übernehmen
    # NUR die Coverage-Werte (Source bleibt aber ATEMWEGSINDEX, das
    # ist der korrekte target_source für die Lead-Time-Story).
    coverage_source: str | None = None
    if not coverage and target_source != "RKI_ARE":
        fallback_row = (
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
        if fallback_row:
            fallback_metrics = dict((fallback_row.metrics or {}))
            fallback_coverage = fallback_metrics.get("interval_coverage") or {}
            if fallback_coverage:
                coverage = fallback_coverage
                coverage_source = "RKI_ARE-Backtest (Fallback)"

    return {
        "horizonDays": int(horizon_days),
        "targetSource": target_source,
        "targetLabel": TARGET_SOURCE_LABELS.get(target_source, target_source),
        "bestLagDays": _optional_int(timing.get("best_lag_days")),
        "correlationAtHorizon": _optional_float(timing.get("corr_at_horizon")),
        "correlationAtBestLag": _optional_float(timing.get("corr_at_best_lag")),
        "maeVsPersistencePct": _optional_float(improvement.get("mae_vs_persistence_pct")),
        "maeVsSeasonalPct": _optional_float(improvement.get("mae_vs_seasonal_pct")),
        "overallPassed": bool(quality_gate.get("overall_passed") or False),
        "baselinePassed": bool(quality_gate.get("baseline_passed") or False),
        "intervalCoverage80Pct": _optional_float(coverage.get("coverage_80_pct")),
        "intervalCoverage95Pct": _optional_float(coverage.get("coverage_95_pct")),
        "intervalCoverageSource": coverage_source,
        "backtestEndDate": str(date_range.get("end") or "") or None,
        "backtestCalibrationMode": _infer_calibration_mode(event_cal),
        "hasRun": row is not None,
    }


def _synthesize_readiness(
    *,
    ranking: dict[str, Any],
    lead: dict[str, Any],
) -> str:
    """Synthesize a top-level headline readiness state.

    * GO_RANKING  — BL-ranking is usable AND lead-time story holds up.
    * RANKING_OK  — BL-ranking is usable but lead-time is weak/absent.
    * LEAD_ONLY   — lead-time is solid but we don't have trustworthy ranking.
    * WATCH       — neither is currently defensible; the cockpit surfaces a
                    banner explaining why.
    """
    precision = ranking.get("precisionAtTop3")
    lag = lead.get("bestLagDays")
    ranking_ok = (
        isinstance(precision, (int, float))
        and precision >= RANKING_PRECISION_GO_THRESHOLD
    )
    lead_ok = isinstance(lag, int) and lag >= LEAD_LAG_GO_MIN_DAYS
    if ranking_ok and lead_ok:
        return "GO_RANKING"
    if ranking_ok:
        return "RANKING_OK"
    if lead_ok:
        return "LEAD_ONLY"
    return "WATCH"


def _extract_model_status(
    db: Session,
    virus_typ: str,
    *,
    lead_horizon_days: int = DEFAULT_LEAD_HORIZON_DAYS,
    lead_target_source: str = DEFAULT_LEAD_TARGET_SOURCE,
    ranking_horizon_days: int = RANKING_HORIZON_DAYS,
) -> dict[str, Any]:
    """Build the two-block modelStatus payload.

    After the 2026-04-17 discussion:
      * ``ranking``: how well we order Bundesländer (source: regional h7 panel
        training summary; NOT the daily backtest_runs row, which scores the
        national point-forecast, not the ranking).
      * ``lead``: how far ahead we are vs. a fast-truth signal (source: the
        most recent h14/ATEMWEGSINDEX successful backtest_runs row).

    Top-level fields are kept as aliases of the lead block so existing UI
    references (snapshot.modelStatus.horizonDays etc.) stay valid while the
    UI migrates to reading the structured blocks.
    """
    ranking_metrics = _read_ranking_metrics(virus_typ)
    ranking_metrics.setdefault("horizonDays", ranking_horizon_days)
    ranking_metrics["source"] = "regional_pooled_panel_h7"
    ranking_metrics["sourceLabel"] = (
        "Regionales 7-Tage-Panel (pilot training)"
        if virus_typ in _REGIONAL_VIRUSES
        else "Nur nationaler Forecast — kein regionales Modell"
    )
    training_panel = _read_training_panel(virus_typ)

    lead = _lead_block_from_backtest(
        db,
        virus_typ=virus_typ,
        horizon_days=lead_horizon_days,
        target_source=lead_target_source,
    )
    # The "banner calibration mode" is derived from the lead backtest when we
    # have one, otherwise unknown.
    calibration_mode = lead.get("backtestCalibrationMode") or "unknown"
    regional_available = virus_typ in _REGIONAL_VIRUSES
    forecast_readiness = _synthesize_readiness(ranking=ranking_metrics, lead=lead)

    note_parts: list[str] = []
    if calibration_mode in {"heuristic", "skipped"}:
        note_parts.append(
            "Signalstärke ist ein Ranking-Score (0–1), keine kalibrierte Wahrscheinlichkeit."
        )
    if not regional_available:
        note_parts.append(
            f"Für {virus_typ} liegt aktuell kein regionales Modell vor — Bundesländer-Ansicht deaktiviert."
        )
    if lead.get("bestLagDays") is not None and lead["bestLagDays"] >= 0:
        note_parts.append(
            f"Der Forecast läuft dem {lead['targetLabel']} nicht hinterher — Vorlauf gegenüber dem "
            "RKI-Meldewesen bleibt strukturell erhalten."
        )
    elif lead.get("bestLagDays") is not None:
        note_parts.append(
            f"Der Forecast-Lag gegen {lead['targetLabel']} beträgt {lead['bestLagDays']} Tage; "
            "das Signal bleibt dem Meldewesen voraus, aber nicht der realen Notaufnahme-Aktivität."
        )

    # Top-level aliases: the UI still reads modelStatus.horizonDays /
    # .bestLagDays / .maeVsPersistencePct etc. — keep them pointed at the
    # lead block so no UI code breaks.
    return {
        "virusTyp": virus_typ,
        "forecastReadiness": forecast_readiness,
        "calibrationMode": calibration_mode,
        "regionalAvailable": regional_available,
        # Headline aliases (mirror lead block).
        "horizonDays": int(lead_horizon_days),
        "overallPassed": bool(lead.get("overallPassed")),
        "baselinePassed": bool(lead.get("baselinePassed")),
        "bestLagDays": lead.get("bestLagDays"),
        "correlationAtHorizon": lead.get("correlationAtHorizon"),
        "maeVsPersistencePct": lead.get("maeVsPersistencePct"),
        "intervalCoverage80Pct": lead.get("intervalCoverage80Pct"),
        "intervalCoverage95Pct": lead.get("intervalCoverage95Pct"),
        "trainingWindowEnd": lead.get("backtestEndDate"),
        # Structured blocks for the UI to render two panels.
        "ranking": ranking_metrics,
        "lead": lead,
        # Training-panel transparency badge (N samples + maturity tier).
        # Read directly from ml_models/<slug>/metadata.json so the UI can
        # flag Phase-1 pilots honestly without waiting for outcome data.
        "trainingPanel": training_panel,
        # Forecast-trajectory honesty block — see FORECAST_TRAJECTORY_SOURCE
        # docstring. UI uses this to label the forecast chart so the 7-point
        # line is not read as seven native model inferences.
        "trajectorySource": dict(FORECAST_TRAJECTORY_SOURCE),
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


# Which three data sources we surface as the "top drivers" of the atlas —
# selected for narrative alignment with the lead-time pitch ("Abwasser /
# Notaufnahme / Suchsignale laufen dem RKI-Meldewesen voraus"). Ordered by
# how much they carry the story, not alphabetically.
_ATLAS_DRIVER_SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "AMELAG Abwasser",
        "Abwasser-Viruslast",
        "AMELAG · wöchentlich · strukturell voraus",
    ),
    (
        "RKI/AKTIN Notaufnahme",
        "Notaufnahme-Aktivität",
        "AKTIN · täglich · ARI 7-Tage-MA",
    ),
    (
        "Google Trends",
        "Suchsignale",
        "Google · täglich · Verhaltens-Proxy",
    ),
)


def _format_driver_freshness(latency_days: Any, health: str) -> str:
    """Turn a source's latencyDays + health into a human-readable chip."""
    try:
        d = int(latency_days) if latency_days is not None else None
    except (TypeError, ValueError):
        d = None
    if d is None:
        return "keine Daten"
    if d <= 0:
        return "tagesaktuell"
    if d == 1:
        return "1 Tag alt"
    tag = f"{d} Tage alt"
    if health == "stale":
        tag = f"{tag} · veraltet"
    elif health == "delayed":
        tag = f"{tag} · verzögert"
    return tag


def _top_drivers_from_sources(
    sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build the 3-tile Atlas driver panel from the real source-freshness map.

    Replaces the previous implementation that surfaced ``reason_trace.why``
    strings verbatim — those were English model-internal debug messages
    ("Event probability 0.01 stays below the rule set ...") and landed as
    tiles in the UI, which is both off-brand and unhelpful for a media
    manager.

    Now we show three canonical truth sources with their current freshness.
    If a source is missing from the sources list (e.g. never ingested), we
    skip it rather than render a placeholder.
    """
    by_name: dict[str, dict[str, Any]] = {
        str(s.get("name") or ""): s for s in sources
    }
    out: list[dict[str, str]] = []
    for canonical_name, label, subtitle in _ATLAS_DRIVER_SOURCES:
        item = by_name.get(canonical_name)
        if not item:
            continue
        out.append(
            {
                "label": label,
                "value": _format_driver_freshness(
                    item.get("latencyDays"), str(item.get("health") or "")
                ),
                "subtitle": subtitle,
            }
        )
    return out


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
    """Map service.predict_all_regions() output to the CockpitSnapshot regions[].

    Missing Bundesländer (service returned <16 predictions) are padded with
    explicit ``decisionLabel = "TrainingPending"`` placeholders instead of
    being dropped silently. The frontend can render an honest "Training
    pending" tile rather than a grey blank for those regions, and the
    snapshot note counts how many are still pending.
    """
    notes: list[str] = []
    predictions = regional_payload.get("predictions") or []
    status = regional_payload.get("status")
    if status and status != "success":
        notes.append(
            f"Regional-Forecast-Status: {status} — {regional_payload.get('message') or 'kein regionaler Forecast verfügbar'}."
        )
        return [], notes

    mapped: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for pred in predictions:
        bl_code = str(pred.get("bundesland") or "").strip()
        if bl_code not in BUNDESLAND_NAMES:
            continue
        seen_codes.add(bl_code)
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

    # Pad missing Bundesländer with TrainingPending placeholders so the map
    # always shows all 16 tiles — an absent tile is ambiguous (bug? coverage
    # gap?), an explicit "Training pending" tile names it.
    missing_codes = [code for code in BUNDESLAND_NAMES if code not in seen_codes]
    for bl_code in missing_codes:
        mapped.append(
            {
                "code": bl_code,
                "name": BUNDESLAND_NAMES[bl_code],
                "delta7d": None,
                "pRising": None,
                "forecast": None,
                "drivers": [],
                "currentSpendEur": None,
                "recommendedShiftEur": None,
                "decisionLabel": "TrainingPending",
            }
        )
    if missing_codes:
        notes.append(
            f"{len(missing_codes)} von {len(BUNDESLAND_NAMES)} Bundesländern ohne regionalen Forecast "
            "— Kacheln sind als 'Training pending' markiert."
        )
    return mapped, notes


# Map virus_typ to the SURVSTAT disease string used for the observed-past
# timeline. SURVSTAT uses its own vocabulary; adjust here as we add scopes.
_SURVSTAT_DISEASES_FOR_VIRUS: dict[str, tuple[str, ...]] = {
    "Influenza A": ("Influenza, saisonal",),
    "Influenza B": ("Influenza, saisonal",),
    "RSV A": ("RSV",),
    "SARS-CoV-2": ("COVID-19",),
}


COCKPIT_TIMELINE_SNAPSHOT_ACTION = "COCKPIT_TIMELINE_SNAPSHOT"
COCKPIT_TIMELINE_SNAPSHOT_ENTITY = "CockpitTimeline"


def _persist_cockpit_timeline_snapshot(
    db: Session,
    *,
    virus_typ: str,
    horizon_days: int,
    timeline: list[dict[str, Any]],
) -> None:
    """Write one audit-log entry per (virus, horizon, day).

    Idempotent: skips when a row with the same (action, entity_type,
    metadata.snapshot_day, metadata.virus_typ, metadata.horizon_days)
    already exists today. The payload carries a compact form of the
    timeline (date + observed + q10/q50/q90 + edActivity) so the
    vintage-overlay endpoint can reconstruct the historical forecast
    directly.
    """
    if not timeline:
        return

    today = utc_now().date()
    snapshot_day = today.isoformat()

    # Idempotency check via raw SQL (JSON column, not JSONB → kein .astext).
    # Prüft ob heute bereits ein Snapshot für (virus, horizon) existiert.
    existing = db.execute(
        text("""
            SELECT COUNT(id) FROM audit_logs
            WHERE action = :act
              AND entity_type = :ent
              AND DATE(timestamp) = :today
              AND (new_value->'metadata'->>'virus_typ') = :v
              AND (new_value->'metadata'->>'horizon_days') = :h
        """),
        {
            "act": COCKPIT_TIMELINE_SNAPSHOT_ACTION,
            "ent": COCKPIT_TIMELINE_SNAPSHOT_ENTITY,
            "today": today,
            "v": str(virus_typ),
            "h": str(int(horizon_days)),
        },
    ).scalar()
    if existing and int(existing) > 0:
        return

    # Compact timeline rows
    compact: list[dict[str, Any]] = []
    for row in timeline:
        compact.append({
            "date": row.get("date"),
            "observed": row.get("observed"),
            "edActivity": row.get("edActivity"),
            "q10": row.get("q10"),
            "q50": row.get("q50"),
            "q90": row.get("q90"),
            "interpolated": bool(row.get("interpolated")),
            "horizon_days": row.get("horizonDays") or int(horizon_days),
        })

    payload = {
        "action": COCKPIT_TIMELINE_SNAPSHOT_ACTION,
        "timestamp": utc_now().isoformat(),
        "metadata": {
            "virus_typ": str(virus_typ),
            "horizon_days": int(horizon_days),
            "snapshot_day": snapshot_day,
            "timeline_length": len(compact),
        },
        "timeline": compact,
    }

    entry = AuditLog(
        timestamp=utc_now(),
        action=COCKPIT_TIMELINE_SNAPSHOT_ACTION,
        entity_type=COCKPIT_TIMELINE_SNAPSHOT_ENTITY,
        entity_id=0,
        user="system.cockpit_snapshot",
        new_value=payload,
        reason=f"Auto-snapshot {virus_typ} h{horizon_days} @ {snapshot_day}",
    )
    db.add(entry)
    db.commit()


def _build_timeline_from_national(
    db: Session,
    virus_typ: str,
    horizon_days: int,
) -> list[dict[str, Any]]:
    """Build a `(-14..+horizon)` timeline mixing observed truth with forecasts.

    Observed past:
        SURVSTAT-Gesamt weekly incidence for the selected disease. Weekly
        points are piecewise-linearly interpolated onto daily ticks so the
        fan-chart has a smooth observed line. If SURVSTAT is empty for this
        scope the past stays null.

    Forecast future (and nowcast fill):
        ml_forecasts rows for this virus/horizon, matched to the nearest
        target day within ±``NEAREST_TOLERANCE_DAYS``. This tolerates the
        weekly/sparse cadence of ml_forecasts without faking daily points.

    Interpolation honesty:
        When two anchors are > ``INTERPOLATION_MAX_SPAN_DAYS`` apart, the
        interpolated points get ``"interpolated": true`` in the payload so
        the UI can render them as a dashed line (rather than pretending
        two independent forecasts are a smooth trajectory). Single-anchor
        extrapolation is capped at ``EXTRAPOLATION_MAX_DAYS`` to avoid
        pulling a forecast forward by a full week.

    The returned list spans ``-14 .. +horizon_days`` inclusive.
    """
    NEAREST_TOLERANCE_DAYS = 3
    INTERPOLATION_MAX_SPAN_DAYS = 3  # above this: still interpolate, but flag as such
    EXTRAPOLATION_MAX_DAYS = 2       # single-anchor fallback only this close

    today = utc_now().date()
    timeline_start = today.fromordinal(today.toordinal() - 14)
    timeline_end = today.fromordinal(today.toordinal() + int(horizon_days))

    # --- Observed past from SURVSTAT-Gesamt ---------------------------------
    observed_by_day: dict[str, float] = {}
    diseases = _SURVSTAT_DISEASES_FOR_VIRUS.get(virus_typ)
    if diseases:
        # Pull a bit more history than we strictly need so linear interpolation
        # has at least two anchors inside the range.
        query_start = timeline_start - timedelta(days=21)
        rows: list[SurvstatWeeklyData] = (
            db.query(SurvstatWeeklyData)
            .filter(
                SurvstatWeeklyData.disease.in_(diseases),
                SurvstatWeeklyData.bundesland == "Gesamt",
                SurvstatWeeklyData.week_start >= query_start,
                SurvstatWeeklyData.week_start <= today,
            )
            .order_by(SurvstatWeeklyData.week_start.asc())
            .all()
        )
        weekly: list[tuple[pd_date, float]] = [
            (row.week_start.date(), float(row.incidence))
            for row in rows
            if row.week_start is not None and row.incidence is not None
        ]
        # Linear interpolation between consecutive weekly anchors.
        if len(weekly) >= 2:
            for i in range(len(weekly) - 1):
                d0, v0 = weekly[i]
                d1, v1 = weekly[i + 1]
                span_days = max((d1 - d0).days, 1)
                for offset_days in range((d1 - d0).days + 1):
                    day = d0.fromordinal(d0.toordinal() + offset_days)
                    if day < timeline_start or day > today:
                        continue
                    t = offset_days / span_days
                    observed_by_day[day.isoformat()] = v0 + (v1 - v0) * t
        elif len(weekly) == 1:
            d, v = weekly[0]
            if timeline_start <= d <= today:
                observed_by_day[d.isoformat()] = v

    # --- Forecast points (with a ±N-day tolerance match) --------------------
    forecast_rows: list[MLForecast] = (
        db.query(MLForecast)
        .filter(
            MLForecast.virus_typ == virus_typ,
            MLForecast.forecast_date >= (timeline_start - timedelta(days=NEAREST_TOLERANCE_DAYS)),
            MLForecast.forecast_date <= (timeline_end + timedelta(days=NEAREST_TOLERANCE_DAYS)),
        )
        .order_by(desc(MLForecast.created_at))
        .all()
    )
    # Keep one row per forecast_date: the most recently created.
    forecast_by_exact_date: dict[str, MLForecast] = {}
    for row in forecast_rows:
        if not row.forecast_date:
            continue
        key = row.forecast_date.date().isoformat()
        if key not in forecast_by_exact_date:
            forecast_by_exact_date[key] = row
    # Sorted list of (date, row) for nearest-neighbour lookups.
    forecast_sorted: list[tuple[pd_date, MLForecast]] = sorted(
        ((pd_date.fromisoformat(k), v) for k, v in forecast_by_exact_date.items()),
        key=lambda e: e[0],
    )

    def _interp_forecast(
        target_day: pd_date,
    ) -> tuple[float | None, float | None, float | None, bool]:
        """Interpolate q10/q50/q90 for ``target_day``.

        Returns a 4-tuple ``(q10, q50, q90, interpolated)``. ``interpolated``
        is True when the value comes from blending two anchors whose span
        exceeds ``INTERPOLATION_MAX_SPAN_DAYS``; the frontend uses that flag
        to render those segments as dashed, so users know the line is
        bridging two independent forecasts.

        - Two anchors and target between them → linear blend.
        - One anchor only, within ``EXTRAPOLATION_MAX_DAYS`` → nearest
          fallback (no extrapolation beyond that).
        - Otherwise → ``(None, None, None, False)``.
        """
        if not forecast_sorted:
            return None, None, None, False

        # Find the anchors immediately left and right of target_day.
        left: tuple[pd_date, MLForecast] | None = None
        right: tuple[pd_date, MLForecast] | None = None
        for d, row in forecast_sorted:
            if d <= target_day:
                left = (d, row)
            elif d > target_day and right is None:
                right = (d, row)
                break

        def _pick(row: MLForecast) -> tuple[float | None, float | None, float | None]:
            return (
                _optional_float(row.lower_bound),
                _optional_float(row.predicted_value),
                _optional_float(row.upper_bound),
            )

        if left is not None and right is not None:
            ld, lrow = left
            rd, rrow = right
            span = max((rd - ld).days, 1)
            t = (target_day - ld).days / span
            lq10, lq50, lq90 = _pick(lrow)
            rq10, rq50, rq90 = _pick(rrow)

            def _blend(a: float | None, b: float | None) -> float | None:
                if a is None and b is None:
                    return None
                if a is None:
                    return b
                if b is None:
                    return a
                return round(a + (b - a) * t, 4)

            interpolated = (
                span > INTERPOLATION_MAX_SPAN_DAYS
                and ld != target_day
                and rd != target_day
            )
            return (
                _blend(lq10, rq10),
                _blend(lq50, rq50),
                _blend(lq90, rq90),
                interpolated,
            )

        # Only one neighbour available → single-anchor fallback with a
        # hard ceiling. No extrapolation beyond EXTRAPOLATION_MAX_DAYS.
        anchor = left or right
        if anchor is None:
            return None, None, None, False
        ad, arow = anchor
        if abs((ad - target_day).days) > EXTRAPOLATION_MAX_DAYS:
            return None, None, None, False
        q10, q50, q90 = _pick(arow)
        # A lone-anchor match at the exact target day is not interpolation;
        # anything else within the extrapolation window is.
        interpolated = ad != target_day
        return q10, q50, q90, interpolated

    # --- Secondary truth: Notaufnahme ARI 7-day MA (daily, national) --------
    # Only meaningful for respiratory-ish viruses; skip for SARS-CoV-2 where
    # we would use a different syndrome (COVID), and RSV where ARI is noisy.
    ed_by_day: dict[str, float] = {}
    if virus_typ in {"Influenza A", "Influenza B"}:
        ed_rows: list[NotaufnahmeSyndromData] = (
            db.query(NotaufnahmeSyndromData)
            .filter(
                NotaufnahmeSyndromData.syndrome == "ARI",
                NotaufnahmeSyndromData.ed_type == "all",
                NotaufnahmeSyndromData.age_group == "00+",
                NotaufnahmeSyndromData.datum >= timeline_start,
                NotaufnahmeSyndromData.datum <= today,
            )
            .order_by(NotaufnahmeSyndromData.datum.asc())
            .all()
        )
        for row in ed_rows:
            if row.datum is None:
                continue
            key = row.datum.date().isoformat()
            # Prefer the 7-day moving average for smooth fan-chart display.
            val = row.relative_cases_7day_ma
            if val is None:
                val = row.relative_cases
            if val is not None:
                ed_by_day[key] = float(val)

    timeline: list[dict[str, Any]] = []
    for offset in range(-14, int(horizon_days) + 1):
        target_day = today.fromordinal(today.toordinal() + offset)
        iso = target_day.isoformat()
        observed = observed_by_day.get(iso)
        # Nowcast = observed with a slight (+ real data revision semantics in
        # future) lift for the last 14 days. For now, nowcast == observed on
        # the past, so we just mirror the observed value.
        nowcast = observed if -14 <= offset <= 0 else None
        ed_value = ed_by_day.get(iso) if offset <= 0 else None

        q10, q50, q90, interpolated = _interp_forecast(target_day)

        timeline.append(
            {
                "date": iso,
                "observed": observed,
                "nowcast": nowcast,
                "edActivity": ed_value,
                "q10": q10,
                "q50": q50,
                "q90": q90,
                "interpolated": interpolated,
                "horizonDays": offset,
            }
        )
    return timeline


def build_cockpit_snapshot(
    db: Session,
    *,
    virus_typ: str = "Influenza A",
    horizon_days: int = DEFAULT_LEAD_HORIZON_DAYS,
    client: str = "GELO",
    brand: str | None = None,
    lead_target_source: str = DEFAULT_LEAD_TARGET_SOURCE,
    regional_forecast_service=None,
) -> dict[str, Any]:
    """Assemble a :class:`CockpitSnapshot` payload for the given scope.

    The `horizon_days` parameter controls the **lead-time story** — the
    horizon at which we claim "N days ahead of Notaufnahme-Aktivität". As of
    2026-04-17 this defaults to 14 (the strongest honest claim in
    backtest_runs). The Bundesländer-ranking always uses the regional h7
    panel because that's where the trained artefacts live.

    Parameters
    ----------
    db
        SQLAlchemy session (read-only usage).
    virus_typ
        Virus whose snapshot to build.
    horizon_days
        Lead-time horizon for the headline story (7, 14, or 21 today).
    client
        Client label shown in the UI.
    brand
        Brand passthrough for the regional forecast service.
    lead_target_source
        Which truth target the lead-time is measured against. Default
        ATEMWEGSINDEX (Notaufnahme); ``"RKI_ARE"`` is also valid for
        compatibility with the pre-2026-04-17 story.
    regional_forecast_service
        Optional callable for testability.
    """
    generated_at = utc_now()
    model_status = _extract_model_status(
        db,
        virus_typ,
        lead_horizon_days=horizon_days,
        lead_target_source=lead_target_source,
    )

    # Regional BL ranking always runs at RANKING_HORIZON_DAYS (h=7) because
    # that's the only regional artefact set that exists. This is orthogonal
    # to the lead-time horizon selected above.
    notes: list[str] = []
    regions: list[dict[str, Any]] = []
    if model_status["regionalAvailable"]:
        if regional_forecast_service is None:
            from app.services.ml.regional_forecast import RegionalForecastService

            service = RegionalForecastService(db)
            regional_payload = service.predict_all_regions(
                virus_typ=virus_typ,
                brand=brand or "default",
                horizon_days=RANKING_HORIZON_DAYS,
            )
        else:
            regional_payload = regional_forecast_service(
                virus_typ=virus_typ,
                brand=brand or "default",
                horizon_days=RANKING_HORIZON_DAYS,
            )
        regions, region_notes = _map_region_predictions(regional_payload)
        notes.extend(region_notes)
    else:
        notes.append(
            f"Für {virus_typ} gibt es aktuell kein regionales Modell — Bundesländer-Ansicht deaktiviert."
        )

    timeline = _build_timeline_from_national(db, virus_typ, horizon_days)

    # Option-D: persistiere die Timeline als Audit-Event, idempotent pro Tag.
    # Gibt uns eine wachsende Historie von Forecast-Vintages — jeder Tag
    # akkumuliert einen weiteren Snapshot, ohne extra Cron-Job oder Schema-
    # Änderung. Vintage-Overlay liest dann aus audit_logs direkt.
    try:
        _persist_cockpit_timeline_snapshot(
            db, virus_typ=virus_typ, horizon_days=horizon_days, timeline=timeline,
        )
    except Exception:  # noqa: BLE001
        # Never block snapshot delivery on audit-write failure.
        logger.exception("persist_cockpit_timeline_snapshot failed (non-fatal)")

    if model_status["calibrationMode"] in {"heuristic", "skipped"}:
        notes.append(
            "Die Signalstärke pro Bundesland ist ein Ranking-Score auf Skala 0–1, keine kalibrierte "
            "Wahrscheinlichkeit. Volle Kalibrierung gegen echte Verkaufsdaten entsteht sobald der "
            "Feedback-Loop läuft."
        )

    p_values = [r.get("pRising") for r in regions if r.get("pRising") is not None]
    average_confidence = round(sum(p_values) / len(p_values), 4) if p_values else None

    # primaryRecommendation — 2026-04-20 Pitch-Fix:
    # bisher hardcoded None. Das Frontend rendert volle Fläche dafür;
    # ohne Input bleibt der Kern-Pitch-Claim (Decision-Tool) leer.
    # Jetzt generieren wir eine signal-basierte Empfehlung sobald das
    # Ranking ein klares From/To-Paar hergibt — EUR bleibt null
    # (honest-by-default: keine Budget-Anbindung), der Vorschlag
    # nennt Richtung + Begründung + Modell-Konfidenz.
    _rec_candidates = [
        r for r in regions
        if isinstance(r.get("delta7d"), (int, float))
        and r.get("decisionLabel") != "TrainingPending"
    ]
    _rec_candidates_sorted = sorted(
        _rec_candidates,
        key=lambda r: r.get("delta7d") or 0.0,
        reverse=True,
    )
    primary_recommendation = None
    if len(_rec_candidates_sorted) >= 2:
        top = _rec_candidates_sorted[0]
        bottom = _rec_candidates_sorted[-1]
        top_delta = float(top.get("delta7d") or 0.0)
        bottom_delta = float(bottom.get("delta7d") or 0.0)
        # Empfehlung nur wenn: Top-Riser signifikant positiv ODER
        # Spread zwischen Top und Bottom groß genug.
        spread = top_delta - bottom_delta
        if top_delta > 0.08 or spread > 0.20:
            # Confidence als kontextsensitive Skala 0..1:
            # stärkeres Delta → höhere Konfidenz, aber mit hartem
            # Maximum 0.85 damit kein "95 %-Pill" suggeriert wird.
            confidence = max(0.15, min(0.85, abs(top_delta) * 1.6 + 0.10))
            top_pct = round(top_delta * 100)
            bot_pct = round(bottom_delta * 100)
            why_parts = [
                f"{top.get('name')} zeigt {'+' if top_pct >= 0 else ''}{top_pct} % Wellen-Veränderung in 7 Tagen "
                f"(Top-Riser), während {bottom.get('name')} mit {'+' if bot_pct >= 0 else ''}{bot_pct} % "
                "am unteren Ende steht.",
            ]
            if top_delta > 0.15:
                why_parts.append(
                    "Das Ranking ist eindeutig genug für einen gerichteten Media-Shift — "
                    "Budget folgt der steigenden Welle."
                )
            else:
                why_parts.append(
                    "Kein klassischer Wellen-Peak, aber ein klares Gefälle zwischen Ländern; "
                    "selbst in ruhigeren Wochen lohnt sich die Umschichtung entlang des Signals."
                )
            primary_recommendation = {
                "id": f"signal_auto_{top.get('code')}_{bottom.get('code')}",
                "fromCode": bottom.get("code"),
                "toCode": top.get("code"),
                "fromName": bottom.get("name"),
                "toName": top.get("name"),
                # amountEur bleibt bewusst null — ohne angebundenen
                # Media-Plan rechnet das Tool keine EUR-Beträge. Die
                # Demo-Szene in § II rechnet eine hypothetische Zahl
                # aus, wenn der Nutzer einen Budget-Slider zieht.
                "amountEur": None,
                "confidence": round(confidence, 3),
                "expectedReachUplift": None,
                "why": " ".join(why_parts),
                "primary": True,
                # Flag fürs Frontend: Empfehlung kommt aus Signal-
                # Ranking, nicht aus Budget-Optimierung.
                "signalMode": True,
            }

    sources = _build_sources(db)
    top_drivers = _top_drivers_from_sources(sources)

    return {
        "client": client,
        "virusTyp": virus_typ,
        "virusLabel": _parse_virus_label(virus_typ),
        "isoWeek": _iso_week_label(generated_at),
        "generatedAt": generated_at.isoformat(),
        "totalSpendEur": None,
        # Umbenannt: averageConfidence → averageWaveProbability. Der
        # alte Name suggerierte "Modell-Konfidenz", was ein Pharma-
        # Entscheider als "nur 2 % Vertrauen" fehlliest. Der Wert ist
        # der Mittelwert der Steige-Wahrscheinlichkeit pro Bundesland,
        # Post-Saison naturgemäß klein.
        "averageConfidence": average_confidence,  # legacy alias
        "averageWaveProbability": average_confidence,
        "averageWaveProbabilityContext": _wave_probability_context(average_confidence, _iso_week_label(generated_at)),
        "primaryRecommendation": primary_recommendation,
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
