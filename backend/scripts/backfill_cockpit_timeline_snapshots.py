"""Backfill-Script: Historische ml_forecasts → Cockpit-Timeline-Snapshots.

Migriert alle historischen Runs aus ``ml_forecasts`` (national, region='DE')
in das ``COCKPIT_TIMELINE_SNAPSHOT``-Audit-Log-Format, damit der Vintage-
Endpoint zukünftig aus einer einzigen Quelle (audit_logs) lesen kann statt
aus zwei (ml_forecasts + audit_logs).

Idempotent: wenn ein Snapshot für (virus_typ, horizon_days, DATE(run_date))
bereits existiert, überspringt das Script diesen Run. Kann beliebig oft
ausgeführt werden.

Lauf-Kontext: einmalig beim Deploy von Option C. Danach akkumuliert
Option D organisch weitere Snapshots pro GET /cockpit/snapshot.

Lauf:
    docker exec virusradar_backend python /app/scripts/backfill_cockpit_timeline_snapshots.py
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from typing import Any

from app.db.session import SessionLocal
from app.models.database import AuditLog
from app.core.time import utc_now
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ACTION = "COCKPIT_TIMELINE_SNAPSHOT"
ENTITY = "CockpitTimeline"

# Viren die wir backfillen. SARS-CoV-2 überspringen (Legacy-Artefakt, nicht
# im Cockpit-Kontext relevant).
TARGET_VIRUSES = {"Influenza A", "Influenza B", "RSV A"}


def main() -> int:
    db = SessionLocal()
    try:
        # Pro Virus: sammel alle ml_forecasts-Rows, gruppiere nach created_at.
        # Jede created_at = ein Run = ein zukünftiger Cockpit-Timeline-Snapshot.
        rows = db.execute(
            text("""
                SELECT virus_typ, created_at, forecast_date, horizon_days,
                       predicted_value, lower_bound, upper_bound
                FROM ml_forecasts
                WHERE region = 'DE'
                  AND virus_typ = ANY(:vs)
                  AND predicted_value IS NOT NULL
                ORDER BY virus_typ, created_at ASC, forecast_date ASC
            """),
            {"vs": list(TARGET_VIRUSES)},
        ).all()

        # Gruppieren nach (virus, DATE(created_at), horizon) — weil ml_forecasts
        # jeden einzelnen Point als separaten Row mit eigenem exaktem Timestamp
        # speichert. Alle Rows vom gleichen Tag gehören zum selben Run.
        by_run: dict[tuple[str, Any, int], dict[str, Any]] = defaultdict(lambda: {"points": [], "latest_ts": None})
        for r in rows:
            horizon = int(r.horizon_days) if r.horizon_days is not None else 7
            run_day = r.created_at.date()
            key = (str(r.virus_typ), run_day, horizon)
            bucket = by_run[key]
            bucket["points"].append({
                "date": r.forecast_date.isoformat() if r.forecast_date else None,
                "observed": None,        # ml_forecasts hat keine Observations
                "edActivity": None,       # auch keine ED-Activity
                "q10": float(r.lower_bound) if r.lower_bound is not None else None,
                "q50": float(r.predicted_value) if r.predicted_value is not None else None,
                "q90": float(r.upper_bound) if r.upper_bound is not None else None,
                "interpolated": False,
                "horizon_days": horizon,
            })
            # Latest timestamp innerhalb des Tages als run-timestamp verwenden
            if bucket["latest_ts"] is None or r.created_at > bucket["latest_ts"]:
                bucket["latest_ts"] = r.created_at

        log.info("Found %d unique (virus, run, horizon) tuples across %d rows",
                 len(by_run), len(rows))

        created = 0
        skipped_existing = 0
        skipped_empty = 0

        for (virus_typ, run_date, horizon_days), bucket in by_run.items():
            points = bucket["points"]
            created_at = bucket["latest_ts"]
            if not points or created_at is None:
                skipped_empty += 1
                continue

            # Sort points by forecast_date
            points.sort(key=lambda p: p["date"] or "")

            # Idempotenz-Check: existiert schon ein Snapshot für diesen Tag?
            existing = db.execute(
                text("""
                    SELECT COUNT(id) FROM audit_logs
                    WHERE action = :act
                      AND entity_type = :ent
                      AND DATE(timestamp) = :d
                      AND (new_value->'metadata'->>'virus_typ') = :v
                      AND (new_value->'metadata'->>'horizon_days') = :h
                """),
                {
                    "act": ACTION, "ent": ENTITY, "d": run_date,
                    "v": virus_typ, "h": str(int(horizon_days)),
                },
            ).scalar()
            if existing and int(existing) > 0:
                skipped_existing += 1
                continue

            payload = {
                "action": ACTION,
                "timestamp": created_at.isoformat(),
                "metadata": {
                    "virus_typ": virus_typ,
                    "horizon_days": int(horizon_days),
                    "snapshot_day": run_date.isoformat(),
                    "timeline_length": len(points),
                    "source": "backfill_from_ml_forecasts",
                    "backfilled_at": utc_now().isoformat(),
                },
                "timeline": points,
            }

            entry = AuditLog(
                timestamp=created_at,
                action=ACTION,
                entity_type=ENTITY,
                entity_id=0,
                user="system.backfill_cockpit_timeline",
                new_value=payload,
                reason=f"Backfill {virus_typ} h{horizon_days} @ {run_date.isoformat()} from ml_forecasts",
            )
            db.add(entry)
            db.commit()
            created += 1
            log.info("  wrote %s h%d @ %s — %d points",
                     virus_typ, horizon_days, run_date, len(points))

        log.info("---")
        log.info("Summary: %d created, %d skipped (already existed), %d skipped (empty)",
                 created, skipped_existing, skipped_empty)
        log.info("All COCKPIT_TIMELINE_SNAPSHOT rows now:")
        totals = db.execute(
            text("""
                SELECT (new_value->'metadata'->>'virus_typ') as v, COUNT(*) n
                FROM audit_logs
                WHERE action = :act
                GROUP BY v
                ORDER BY v
            """),
            {"act": ACTION},
        ).all()
        for t in totals:
            log.info("  %s: %d runs", t.v, t.n)

        return 0
    except Exception:  # noqa: BLE001
        log.exception("Backfill failed")
        db.rollback()
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
