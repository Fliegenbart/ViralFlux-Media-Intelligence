"""GET /api/v1/media/cockpit/forecast-vintage — Vintage-Forecast-Runs.

Für § III Forecast-Zeitreise: liefert historische Forecast-Runs aus
``ml_forecasts`` plus predicted-vs-actual Pairs aus
``forecast_accuracy_log``. Der Frontend-Chart überlagert die Vintage-
Spuren als Geister-Traces über den aktuellen Forecast-Kegel und zeigt
die Pairs als "Hatten wir recht?"-Tabelle.

Scope: national aggregiert (region = 'DE'), weil nur dort historische
Runs persistiert sind. Per-BL Vintage-Runs würde bedeuten, den Regional-
Forecast strict-vintage-modus re-zu-laufen — das ist ein eigenes
Backfill-Projekt, nicht dieser Endpoint.

Auth: cockpit-gate — selbe Policy wie snapshot/backtest/impact.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPPORTED_VIRUSES = {"Influenza A", "Influenza B", "RSV A", "SARS-CoV-2"}


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    try:
        return ts.isoformat()
    except Exception:
        return str(ts)


@router.get(
    "/cockpit/forecast-vintage",
    dependencies=[Depends(require_cockpit_auth)],
)
async def get_cockpit_forecast_vintage(
    virus_typ: str = Query("Influenza A"),
    run_limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Vintage-Forecast-Runs + predicted-vs-actual Pairs für § III.

    Returns
    -------
    {
      "virus_typ": "...",
      "runs": [
        {
          "run_date": "2026-03-09T09:54:36",
          "anchor_date": "2026-03-09",
          "points": [{"date": "2026-03-09", "q50": .., "q10": .., "q90": ..}, ...]
        }, ...
      ],
      "reconciliation": {
        "window_days": 59, "samples": 10,
        "mae": .., "mape": .., "correlation": ..,
        "pairs": [{"date": "...", "predicted": .., "actual": ..}, ...]
      } | null
    }
    """
    if virus_typ not in _SUPPORTED_VIRUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"virus_typ must be one of {sorted(_SUPPORTED_VIRUSES)}",
        )

    # Vintage runs — gruppiere ml_forecasts nach created_at,
    # filtere auf virus_typ und region='DE'. Runs mit nur 1 Punkt
    # (Mikro-Test-Runs) werden rausgefiltert; wir wollen echte
    # Horizont-Runs (>= 5 Punkte).
    rows = db.execute(
        text("""
            SELECT
                created_at,
                forecast_date,
                predicted_value,
                lower_bound,
                upper_bound,
                horizon_days
            FROM ml_forecasts
            WHERE virus_typ = :v
              AND region = 'DE'
              AND predicted_value IS NOT NULL
            ORDER BY created_at DESC, forecast_date ASC
        """),
        {"v": virus_typ},
    ).all()

    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[r.created_at].append({
            "date": _iso(r.forecast_date),
            "q50": float(r.predicted_value) if r.predicted_value is not None else None,
            "q10": float(r.lower_bound) if r.lower_bound is not None else None,
            "q90": float(r.upper_bound) if r.upper_bound is not None else None,
            "horizon_days": int(r.horizon_days) if r.horizon_days is not None else None,
        })

    runs: list[dict[str, Any]] = []
    for created_at, points in grouped.items():
        # Runs mit nur 1 Punkt sind Mikro-Tests → überspringen, außer
        # wir haben nichts anderes.
        anchor_point = points[0]
        runs.append({
            "run_date": _iso(created_at),
            "anchor_date": anchor_point["date"],
            "anchor_value": anchor_point["q50"],
            "num_points": len(points),
            "points": points,
        })

    # Zusätzlich: Cockpit-Timeline-Snapshots aus audit_logs lesen.
    # Diese werden seit Option-D (2026-04-19) bei jedem ersten Snapshot
    # pro Tag persistiert und liefern die REAL in der Cockpit-UI gezeigte
    # Timeline — also das richtige Modell, nicht die Legacy-ml_forecasts.
    audit_rows = db.execute(
        text("""
            SELECT timestamp, new_value
            FROM audit_logs
            WHERE action = 'COCKPIT_TIMELINE_SNAPSHOT'
              AND entity_type = 'CockpitTimeline'
              AND new_value->'metadata'->>'virus_typ' = :v
            ORDER BY timestamp DESC
            LIMIT 60
        """),
        {"v": virus_typ},
    ).all()

    for row in audit_rows:
        payload = row.new_value or {}
        timeline_rows = payload.get("timeline") or []
        if not timeline_rows:
            continue
        # Filter on q50-present points only — observed-only rows don't help
        # as a "forecast" trace.
        fc_points = [
            p for p in timeline_rows
            if p.get("q50") is not None and isinstance(p.get("q50"), (int, float))
        ]
        if len(fc_points) < 3:
            continue
        anchor_point = fc_points[0]
        runs.append({
            "run_date": _iso(row.timestamp),
            "anchor_date": anchor_point.get("date"),
            "anchor_value": anchor_point.get("q50"),
            "num_points": len(fc_points),
            "source": "cockpit_timeline_snapshot",
            "points": [
                {
                    "date": p.get("date"),
                    "q10": p.get("q10"),
                    "q50": p.get("q50"),
                    "q90": p.get("q90"),
                    "horizon_days": p.get("horizon_days"),
                }
                for p in fc_points
            ],
        })

    # Bevorzuge volle Runs (>= 5 Punkte), aber wenn keine da sind, zeige
    # wenigstens die Mikro-Runs damit die Sektion nicht leer bleibt.
    # Cockpit-Timeline-Snapshots (source == 'cockpit_timeline_snapshot')
    # kommen zuerst, weil sie die AUTORITÄREN Vintage-Daten des aktuellen
    # Modells sind. Danach die älteren ml_forecasts-Runs.
    full_runs = [r for r in runs if r["num_points"] >= 5]
    if full_runs:
        runs = full_runs
    # Sort: cockpit_timeline first, then others, then by run_date DESC
    runs.sort(
        key=lambda r: (
            0 if r.get("source") == "cockpit_timeline_snapshot" else 1,
            -(datetime.fromisoformat(r["run_date"].replace("Z", "+00:00")).timestamp()
              if r.get("run_date") else 0),
        )
    )
    runs = runs[:run_limit]

    # Reconciliation — aus forecast_accuracy_log
    acc_row = db.execute(
        text("""
            SELECT computed_at, window_days, samples, mae, rmse, mape,
                   correlation, drift_detected, details
            FROM forecast_accuracy_log
            WHERE virus_typ = :v
            ORDER BY computed_at DESC
            LIMIT 1
        """),
        {"v": virus_typ},
    ).mappings().first()

    reconciliation: dict[str, Any] | None = None
    if acc_row is not None:
        details = acc_row.get("details") or {}
        pairs_raw = details.get("pairs") if isinstance(details, dict) else []
        pairs = []
        for p in pairs_raw or []:
            try:
                pairs.append({
                    "date": p.get("date"),
                    "predicted": float(p["predicted"]) if p.get("predicted") is not None else None,
                    "actual": float(p["actual"]) if p.get("actual") is not None else None,
                })
            except (TypeError, ValueError, KeyError):
                continue
        reconciliation = {
            "computed_at": _iso(acc_row.get("computed_at")),
            "window_days": int(acc_row.get("window_days") or 0),
            "samples": int(acc_row.get("samples") or 0),
            "mae": float(acc_row["mae"]) if acc_row.get("mae") is not None else None,
            "rmse": float(acc_row["rmse"]) if acc_row.get("rmse") is not None else None,
            "mape": float(acc_row["mape"]) if acc_row.get("mape") is not None else None,
            "correlation": float(acc_row["correlation"]) if acc_row.get("correlation") is not None else None,
            "drift_detected": bool(acc_row.get("drift_detected") or False),
            "pairs": pairs,
            # Scope of the underlying metric. The accuracy task hardcodes
            # region='DE' / horizon_days=7 (see services/ml/tasks.py), so
            # the reconciliation we render is strictly national. Surface
            # that explicitly so the cockpit-copy can say 'Nationale
            # Accuracy (DE/h=7)' instead of implying regional coverage.
            "scope": {
                "region": "DE",
                "horizonDays": 7,
                "label": "Nationale Accuracy (DE / h=7)",
                "regionalRolloutPending": True,
                "note": (
                    "Regional-Accuracy pro Bundesland ist Teil des Q2-Backlogs. "
                    "Solange die Panel-Metriken regional sind, bleibt dieser "
                    "Reconciliation-Block eine nationale Gegenprobe."
                ),
            },
        }

    return {
        "virus_typ": virus_typ,
        "runs": runs,
        "reconciliation": reconciliation,
    }
