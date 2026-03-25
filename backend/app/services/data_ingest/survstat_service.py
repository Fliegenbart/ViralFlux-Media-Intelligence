"""SURVSTAT Ingestion Service — lokale RKI SURVSTAT-Wochendateien.

Erwartetes Dateiformat (Standard):
- UTF-16 codierte TSV-Datei (Dateiendung .csv)
- Zeile 1: "Bundesland", "Krankheit"
- Zeile 2: "All" + weitere Krankheits-Spalten
- Zeile 3+: Bundesland-Werte inkl. "Gesamt"

Erweitertes Format (mit Altersgruppen):
- Zeile 1: "Bundesland", "Altersgruppe", "Krankheit"
- Zeile 2: Altersgruppe + Krankheits-Spalten
- Zeile 3+: Bundesland × Altersgruppe × Krankheit

OTC-Filtering:
Nur Krankheiten aus OTC_RELEVANT_DISEASES werden importiert.
Alle anderen werden beim Parsing verworfen. Jeder Record erhält
automatisch seinen disease_cluster (RESPIRATORY, GASTROINTESTINAL,
PEDIATRIC_SKIN, PARASITES_VECTORS).
"""

from __future__ import annotations
from app.core.time import utc_now

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import csv
import logging
import re

from sqlalchemy.orm import Session

from app.models.database import SurvstatWeeklyData
from app.services.data_ingest.otc_disease_clusters import (
    disease_to_cluster,
    is_otc_relevant,
)
from app.services.ml.nowcast_revision import capture_nowcast_snapshots

logger = logging.getLogger(__name__)

WEEK_FILE_RE = re.compile(r"(?P<year>\d{4})[_-](?P<week>\d{1,2})$")


@dataclass
class _SurvstatRecord:
    week_label: str
    week_start: datetime
    available_time: datetime
    year: int
    week: int
    bundesland: str
    disease: str
    incidence: float
    source_file: str
    disease_cluster: str | None = None
    age_group: str | None = None


class SurvstatIngestionService:
    """Importiert lokale SURVSTAT-Wochenexports in die Datenbank.

    Filtert beim Import auf OTC-relevante Krankheiten und weist jedem
    Record automatisch seinen Makro-Cluster zu.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _clean_text(value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip().strip('"')
        if text.lower() in {"nan", "none"}:
            return ""
        return text

    @classmethod
    def _parse_number(cls, value: object) -> float | None:
        raw = cls._clean_text(value)
        if not raw:
            return None

        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")

        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _parse_week_from_filename(path: Path) -> tuple[str, int, int, datetime]:
        match = WEEK_FILE_RE.search(path.stem)
        if not match:
            raise ValueError(
                f"Ungültiger Dateiname '{path.name}'. Erwartet: YYYY_WW.csv (z.B. 2026_08.csv)."
            )

        year = int(match.group("year"))
        week = int(match.group("week"))
        if week < 1 or week > 53:
            raise ValueError(f"Ungültige Kalenderwoche in Dateiname '{path.name}': {week}")

        week_label = f"{year}_{week:02d}"
        week_start = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
        return week_label, year, week, week_start

    def parse_file(self, path: Path) -> list[_SurvstatRecord]:
        """Parst eine einzelne SURVSTAT-Datei in Long-Format Records.

        Erkennt automatisch ob das Standardformat (Bundesland × Krankheit)
        oder das erweiterte Format (Bundesland × Altersgruppe × Krankheit)
        vorliegt. Filtert auf OTC-relevante Krankheiten.
        """
        week_label, year, week, week_start = self._parse_week_from_filename(path)
        available_time = week_start + timedelta(days=7)

        with path.open("r", encoding="utf-16", newline="") as fh:
            rows = list(csv.reader(fh, delimiter="\t"))

        if len(rows) < 3:
            raise ValueError(f"Datei '{path.name}' hat zu wenige Zeilen für den SURVSTAT-Import.")

        # Detect format from header row (row 0)
        header_meta = [self._clean_text(c).lower() for c in rows[0]]
        has_age_group = "altersgruppe" in header_meta

        header_row = rows[1]
        disease_cols: dict[int, str] = {}
        start_col = 2 if has_age_group else 1

        for idx in range(start_col, len(header_row)):
            disease = self._clean_text(header_row[idx] if idx < len(header_row) else "")
            if disease:
                disease_cols[idx] = disease

        if not disease_cols:
            raise ValueError(f"Datei '{path.name}' enthält keine Krankheits-Spalten in Zeile 2.")

        records: list[_SurvstatRecord] = []
        skipped_non_otc = 0

        for row in rows[2:]:
            bundesland = self._clean_text(row[0] if len(row) > 0 else "")
            if not bundesland:
                continue

            age_group: str | None = None
            if has_age_group and len(row) > 1:
                age_group = self._clean_text(row[1]) or None

            for col_idx, disease in disease_cols.items():
                if col_idx >= len(row):
                    continue

                # OTC filter: skip non-relevant diseases early
                cluster = disease_to_cluster(disease)
                if cluster is None and disease.lower() != "all":
                    skipped_non_otc += 1
                    continue

                incidence = self._parse_number(row[col_idx])
                if incidence is None:
                    continue

                records.append(
                    _SurvstatRecord(
                        week_label=week_label,
                        week_start=week_start,
                        available_time=available_time,
                        year=year,
                        week=week,
                        bundesland=bundesland,
                        disease=disease,
                        incidence=incidence,
                        source_file=path.name,
                        disease_cluster=cluster,
                        age_group=age_group,
                    )
                )

        logger.info(
            "SURVSTAT parsed %s: %s OTC records (skipped %s non-OTC), %s diseases%s",
            path.name,
            len(records),
            skipped_non_otc,
            len({r.disease for r in records}),
            f", age_groups={has_age_group}" if has_age_group else "",
        )
        return records

    def import_records(self, records: list[_SurvstatRecord]) -> tuple[int, int]:
        """Upsert der SURVSTAT-Records in die DB mit OTC-Cluster-Mapping."""
        if not records:
            return 0, 0

        week_labels = sorted({r.week_label for r in records})
        existing = (
            self.db.query(SurvstatWeeklyData)
            .filter(SurvstatWeeklyData.week_label.in_(week_labels))
            .all()
        )
        existing_map = {
            (row.week_label, row.bundesland, row.disease): row for row in existing
        }

        inserted = 0
        updated = 0

        for rec in records:
            key = (rec.week_label, rec.bundesland, rec.disease)
            vals = {
                "week_start": rec.week_start,
                "available_time": rec.available_time,
                "year": rec.year,
                "week": rec.week,
                "incidence": rec.incidence,
                "source_file": rec.source_file,
                "disease_cluster": rec.disease_cluster,
                "age_group": rec.age_group,
            }

            row = existing_map.get(key)
            if row:
                for attr, value in vals.items():
                    if attr == "available_time":
                        if row.available_time is None or (
                            value is not None and value < row.available_time
                        ):
                            row.available_time = value
                    else:
                        setattr(row, attr, value)
                updated += 1
            else:
                row = SurvstatWeeklyData(
                    week_label=rec.week_label,
                    week_start=rec.week_start,
                    available_time=rec.available_time,
                    year=rec.year,
                    week=rec.week,
                    bundesland=rec.bundesland,
                    disease=rec.disease,
                    incidence=rec.incidence,
                    source_file=rec.source_file,
                    disease_cluster=rec.disease_cluster,
                    age_group=rec.age_group,
                )
                self.db.add(row)
                existing_map[key] = row
                inserted += 1

        self.db.commit()
        logger.info("SURVSTAT import: %s new, %s updated", inserted, updated)
        return inserted, updated

    def backfill_clusters(self) -> int:
        """Nachträgliches Cluster-Mapping für bestehende DB-Rows ohne disease_cluster.

        Einmalig aufrufen nach der Migration, um alle historischen Daten
        mit ihrem OTC-Cluster zu taggen.
        """
        rows = (
            self.db.query(SurvstatWeeklyData)
            .filter(SurvstatWeeklyData.disease_cluster.is_(None))
            .all()
        )

        updated = 0
        for row in rows:
            cluster = disease_to_cluster(row.disease)
            if cluster:
                row.disease_cluster = cluster
                updated += 1

        if updated:
            self.db.commit()

        logger.info("SURVSTAT backfill: %s rows clustered out of %s unclustered", updated, len(rows))
        return updated

    @staticmethod
    def _latest_week_label(records: list[_SurvstatRecord]) -> str | None:
        if not records:
            return None
        latest = max(records, key=lambda r: (r.year, r.week))
        return latest.week_label

    def run_local_import(self, folder_path: str) -> dict:
        """Importiert alle SURVSTAT-Dateien aus einem lokalen Ordner.

        Filtert automatisch auf OTC-relevante Krankheiten und weist
        jedem Record seinen disease_cluster zu.
        """
        base = Path(folder_path).expanduser()
        if not base.exists() or not base.is_dir():
            raise ValueError(f"SURVSTAT-Ordner nicht gefunden: {base}")

        files = sorted(p for p in base.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
        if not files:
            return {
                "success": False,
                "folder": str(base),
                "message": "Keine CSV-Dateien gefunden.",
                "timestamp": utc_now().isoformat(),
            }

        all_records: list[_SurvstatRecord] = []
        parsed_files = 0
        errors: list[dict[str, str]] = []

        for path in files:
            try:
                recs = self.parse_file(path)
                all_records.extend(recs)
                parsed_files += 1
            except Exception as exc:
                logger.error("SURVSTAT parse failed for %s: %s", path.name, exc)
                errors.append({"file": path.name, "error": str(exc)})

        inserted, updated = self.import_records(all_records)
        snapshot_rows = capture_nowcast_snapshots(self.db, ["survstat_weekly"]).get("survstat_weekly", 0)

        # Count clusters for summary
        cluster_counts = {}
        for r in all_records:
            if r.disease_cluster:
                cluster_counts[r.disease_cluster] = cluster_counts.get(r.disease_cluster, 0) + 1

        return {
            "success": len(all_records) > 0 and len(errors) == 0,
            "folder": str(base),
            "files_found": len(files),
            "files_parsed": parsed_files,
            "records_total": len(all_records),
            "imported": inserted,
            "updated": updated,
            "snapshot_rows": snapshot_rows,
            "latest_week": self._latest_week_label(all_records),
            "cluster_distribution": cluster_counts,
            "errors": errors,
            "timestamp": utc_now().isoformat(),
        }
