"""peix cockpit impact-tab builder — honest view of the feedback loop.

The impact tab is the closing piece of the cockpit narrative: "we told you
this ranking; this is what actually happened; when we plug GELO sales data
in, this is where it lands." Because the system does NOT persist per-BL
forecasts today (ml_forecasts has region='DE' only), the historical hit-rate
pane intentionally avoids invented metrics and shows:

* a *current* top-5 snapshot from the live forecast service,
* the *actual* SURVSTAT-BL historical activity (last 12 weeks where BL data
  is available — truth layer for visual context),
* the *outcome-pipeline wiring status*: how many media_outcome_records we
  have, how many outcome_observations, how many holdout_groups, last import
  batch. That stays at zero today; the moment GELO sends data, it fills.

No fabricated numbers, no pretend attribution. When the outcome tables are
empty, the UI renders explicit "data pending" states.

Reads only. Does not mutate state.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.database import (
    MediaOutcomeImportBatch,
    MediaOutcomeRecord,
    OutcomeObservation,
    SurvstatWeeklyData,
)


BUNDESLAND_NAME_TO_CODE: dict[str, str] = {
    "Schleswig-Holstein": "SH",
    "Hamburg": "HH",
    "Niedersachsen": "NI",
    "Bremen": "HB",
    "Nordrhein-Westfalen": "NW",
    "Hessen": "HE",
    "Rheinland-Pfalz": "RP",
    "Saarland": "SL",
    "Baden-Württemberg": "BW",
    "Bayern": "BY",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Mecklenburg-Vorpommern": "MV",
    "Sachsen": "SN",
    "Sachsen-Anhalt": "ST",
    "Thüringen": "TH",
}

VIRUS_TO_SURVSTAT_DISEASE: dict[str, tuple[str, ...]] = {
    "Influenza A": ("Influenza, saisonal",),
    "Influenza B": ("Influenza, saisonal",),
    "RSV A": ("RSV",),
    "SARS-CoV-2": ("COVID-19",),
}


def _truth_snapshot_from_survstat(
    db: Session,
    *,
    virus_typ: str,
    weeks_back: int = 12,
) -> list[dict[str, Any]]:
    """Return per-week × BL activity for the last N weeks from SURVSTAT.

    This is *not* a hit-rate backtest — it just shows the user what actually
    happened in the recent past as a truth-layer reference point.
    """
    diseases = VIRUS_TO_SURVSTAT_DISEASE.get(virus_typ)
    if not diseases:
        return []

    latest = db.query(func.max(SurvstatWeeklyData.week_start)).filter(
        SurvstatWeeklyData.disease.in_(diseases),
        SurvstatWeeklyData.bundesland != "Gesamt",
    ).scalar()
    if latest is None:
        return []

    cutoff = latest - timedelta(weeks=int(max(weeks_back, 1)))
    rows = (
        db.query(SurvstatWeeklyData)
        .filter(
            SurvstatWeeklyData.disease.in_(diseases),
            SurvstatWeeklyData.bundesland != "Gesamt",
            SurvstatWeeklyData.week_start >= cutoff,
        )
        .order_by(SurvstatWeeklyData.week_start, SurvstatWeeklyData.bundesland)
        .all()
    )

    by_week: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not row.week_start:
            continue
        code = BUNDESLAND_NAME_TO_CODE.get(row.bundesland)
        if not code:
            continue
        iso = row.week_start.date().isoformat()
        by_week.setdefault(iso, []).append(
            {
                "code": code,
                "name": row.bundesland,
                "incidence": float(row.incidence or 0.0),
                "weekLabel": row.week_label,
            }
        )

    result: list[dict[str, Any]] = []
    for iso in sorted(by_week.keys()):
        entries = sorted(by_week[iso], key=lambda e: e["incidence"], reverse=True)
        top3 = [e["code"] for e in entries[:3]]
        result.append(
            {
                "weekStart": iso,
                "weekLabel": entries[0]["weekLabel"] if entries else iso,
                "regions": entries,
                "top3": top3,
            }
        )
    return result


def _outcome_pipeline_status(db: Session) -> dict[str, Any]:
    """Count whatever is in the outcome tables. Stays at zero until GELO plugs in."""
    media_count = db.query(func.count(MediaOutcomeRecord.id)).scalar() or 0
    batch_count = db.query(func.count(MediaOutcomeImportBatch.id)).scalar() or 0
    observation_count = db.query(func.count(OutcomeObservation.id)).scalar() or 0
    holdout_count = (
        db.query(func.count(func.distinct(OutcomeObservation.holdout_group)))
        .filter(OutcomeObservation.holdout_group.isnot(None))
        .scalar()
        or 0
    )
    last_batch: MediaOutcomeImportBatch | None = (
        db.query(MediaOutcomeImportBatch)
        .order_by(desc(MediaOutcomeImportBatch.created_at))
        .first()
    )
    last_record: MediaOutcomeRecord | None = (
        db.query(MediaOutcomeRecord)
        .order_by(desc(MediaOutcomeRecord.updated_at))
        .first()
    )

    connected = int(media_count) > 0
    if connected:
        note = "Outcome-Daten sind verbunden — Feedback-Loop ist aktiv."
    else:
        note = (
            "Noch keine Outcome-Daten eingespielt. Sobald GELO (oder ein anderer Client) "
            "Verkaufsdaten pro Woche × BL × SKU liefert, schließt sich der Feedback-Loop und "
            "die Kalibrierung lernt mit."
        )

    return {
        "connected": bool(connected),
        "mediaOutcomeRecords": int(media_count),
        "importBatches": int(batch_count),
        "outcomeObservations": int(observation_count),
        "holdoutGroupsDefined": int(holdout_count),
        "lastImportBatchAt": last_batch.created_at.isoformat() if last_batch and last_batch.created_at else None,
        "lastRecordUpdatedAt": last_record.updated_at.isoformat() if last_record and last_record.updated_at else None,
        "note": note,
    }


def _live_ranking_from_snapshot(
    snapshot: dict[str, Any] | None,
    *,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Extract the top-N BL from a cockpit snapshot payload."""
    if not snapshot:
        return []
    regions = snapshot.get("regions") or []
    ranked = [
        r for r in regions
        if (r.get("pRising") is not None or r.get("delta7d") is not None)
    ]
    ranked.sort(
        key=lambda r: (
            r.get("pRising") if r.get("pRising") is not None else 0.0,
            r.get("delta7d") if r.get("delta7d") is not None else 0.0,
        ),
        reverse=True,
    )
    return [
        {
            "code": r.get("code"),
            "name": r.get("name"),
            "pRising": r.get("pRising"),
            "delta7d": r.get("delta7d"),
            "decisionLabel": r.get("decisionLabel"),
        }
        for r in ranked[:top_n]
    ]


def build_impact_payload(
    db: Session,
    *,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    snapshot: dict[str, Any] | None = None,
    weeks_back: int = 12,
) -> dict[str, Any]:
    """Assemble the impact-tab payload for the given scope.

    Parameters
    ----------
    db
        Read-only SQLAlchemy session.
    virus_typ
        Virus scope, must match the champion-virus whitelist.
    horizon_days
        Forecast horizon (currently only 7 is a champion scope).
    snapshot
        Optional pre-built CockpitSnapshot dict. When None we do not invoke
        the regional forecast service here — the caller handles that to avoid
        duplicate heavy computation.
    weeks_back
        Window of SURVSTAT-BL truth history to return.
    """
    generated_at = utc_now()
    live_ranking = _live_ranking_from_snapshot(snapshot, top_n=5)
    truth_timeline = _truth_snapshot_from_survstat(
        db, virus_typ=virus_typ, weeks_back=weeks_back
    )
    pipeline = _outcome_pipeline_status(db)

    notes: list[str] = []
    if not live_ranking:
        notes.append(
            "Kein Live-Ranking verfügbar — entweder fehlt der Snapshot oder der Virus "
            "hat kein regionales Modell (siehe Modell-Status im Haupt-Tab)."
        )
    if not truth_timeline:
        notes.append(
            "Keine historischen SURVSTAT-Bundesländer-Daten für diesen Virus gefunden. "
            "Das Truth-Layer-Panel bleibt leer, bis Daten eintreffen."
        )
    if not pipeline["connected"]:
        notes.append(
            "Outcome-Pipeline wartet auf GELO-Verkaufsdaten. Siehe 'Outcome-Pipeline-Status' "
            "für das Einspielformat."
        )

    return {
        "virusTyp": virus_typ,
        "horizonDays": int(horizon_days),
        "generatedAt": generated_at.isoformat(),
        "liveRanking": live_ranking,
        "truthHistory": {
            "source": "SURVSTAT (wöchentlich, BL-aufgelöst)",
            "weeksBack": int(weeks_back),
            "timeline": truth_timeline,
        },
        "outcomePipeline": pipeline,
        "notes": notes,
    }
