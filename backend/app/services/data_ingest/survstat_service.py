"""SURVSTAT Ingestion Service — lokale RKI SURVSTAT-Wochendateien.

Erwartetes Dateiformat:
- UTF-16 codierte TSV-Datei (Dateiendung .csv)
- Zeile 1: "Bundesland", "Krankheit"
- Zeile 2: "All" + weitere Krankheits-Spalten
- Zeile 3+: Bundesland-Werte inkl. "Gesamt"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import csv
import logging
import re

from sqlalchemy.orm import Session

from app.models.database import SurvstatWeeklyData

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


class SurvstatIngestionService:
    """Importiert lokale SURVSTAT-Wochenexports in die Datenbank."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _clean_text(value) -> str:
        if value is None:
            return ""
        text = str(value).strip().strip('"')
        if text.lower() in {"nan", "none"}:
            return ""
        return text

    @classmethod
    def _parse_number(cls, value) -> float | None:
        raw = cls._clean_text(value)
        if not raw:
            return None

        if "," in raw and "." in raw:
            # German locale fallback: 1.234,56
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
        """Parst eine einzelne SURVSTAT-Datei in Long-Format Records."""
        week_label, year, week, week_start = self._parse_week_from_filename(path)
        available_time = week_start + timedelta(days=7)

        with path.open("r", encoding="utf-16", newline="") as fh:
            rows = list(csv.reader(fh, delimiter="\t"))

        if len(rows) < 3:
            raise ValueError(f"Datei '{path.name}' hat zu wenige Zeilen für den SURVSTAT-Import.")

        header_row = rows[1]
        disease_cols: dict[int, str] = {}
        for idx in range(1, len(header_row)):
            disease = self._clean_text(header_row[idx] if idx < len(header_row) else "")
            if disease:
                disease_cols[idx] = disease

        if not disease_cols:
            raise ValueError(f"Datei '{path.name}' enthält keine Krankheits-Spalten in Zeile 2.")

        records: list[_SurvstatRecord] = []
        for row in rows[2:]:
            bundesland = self._clean_text(row[0] if len(row) > 0 else "")
            if not bundesland:
                continue

            for col_idx, disease in disease_cols.items():
                if col_idx >= len(row):
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
                    )
                )

        logger.info(
            "SURVSTAT parsed %s: %s records, %s diseases",
            path.name,
            len(records),
            len({r.disease for r in records}),
        )
        return records

    def import_records(self, records: list[_SurvstatRecord]) -> tuple[int, int]:
        """Upsert der SURVSTAT-Records in die DB."""
        if not records:
            return 0, 0

        week_labels = sorted({r.week_label for r in records})
        existing = self.db.query(SurvstatWeeklyData).filter(
            SurvstatWeeklyData.week_label.in_(week_labels)
        ).all()
        existing_map = {
            (row.week_label, row.bundesland, row.disease): row
            for row in existing
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
                )
                self.db.add(row)
                existing_map[key] = row
                inserted += 1

        self.db.commit()
        logger.info("SURVSTAT import: %s new, %s updated", inserted, updated)
        return inserted, updated

    @staticmethod
    def _latest_week_label(records: list[_SurvstatRecord]) -> str | None:
        if not records:
            return None
        latest = max(records, key=lambda r: (r.year, r.week))
        return latest.week_label

    def run_local_import(self, folder_path: str) -> dict:
        """Importiert alle SURVSTAT-Dateien aus einem lokalen Ordner."""
        base = Path(folder_path).expanduser()
        if not base.exists() or not base.is_dir():
            raise ValueError(f"SURVSTAT-Ordner nicht gefunden: {base}")

        files = sorted(p for p in base.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
        if not files:
            return {
                "success": False,
                "folder": str(base),
                "message": "Keine CSV-Dateien gefunden.",
                "timestamp": datetime.utcnow().isoformat(),
            }

        all_records: list[_SurvstatRecord] = []
        parsed_files = 0
        errors: list[dict[str, str]] = []

        for path in files:
            try:
                recs = self.parse_file(path)
                all_records.extend(recs)
                parsed_files += 1
            except Exception as exc:  # pragma: no cover - defensive handling
                logger.error("SURVSTAT parse failed for %s: %s", path.name, exc)
                errors.append({"file": path.name, "error": str(exc)})

        inserted, updated = self.import_records(all_records)

        return {
            "success": len(all_records) > 0 and len(errors) == 0,
            "folder": str(base),
            "files_found": len(files),
            "files_parsed": parsed_files,
            "records_total": len(all_records),
            "imported": inserted,
            "updated": updated,
            "latest_week": self._latest_week_label(all_records),
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat(),
        }
