"""Importer für RKI SurvStat@RKI 2.0 Web-Exports.

Liest die drei Standard-Export-Formate des SurvStat-Webtools:
  1. nach_meldewoche — Krankheit × Kalenderwoche (nationale Inzidenz)
  2. nach_bundesland — Krankheit × 16 Bundesländer (kumulative Inzidenz)
  3. nach_landkreis  — Krankheit × ~400 Kreise (kumulative Inzidenz)

Alle drei: UTF-16 TSV, "transponiert" (Krankheiten = Zeilen, Dimensionen = Spalten),
deutsches Zahlenformat (Punkt = Tausender, Komma = Dezimal).

OTC-Filtering: Nur Krankheiten aus der Whitelist werden importiert.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import SurvstatKreisData, SurvstatWeeklyData
from app.services.data_ingest.otc_disease_clusters import disease_to_cluster

logger = logging.getLogger(__name__)


def _parse_german_number(raw: str) -> float | None:
    """Konvertiert deutsches Zahlenformat: '1.642,34' → 1642.34."""
    raw = raw.strip().strip('"')
    if not raw or raw.lower() in {"nan", "none", "-", ""}:
        return None
    # Punkt = Tausendertrennzeichen, Komma = Dezimaltrennzeichen
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _read_transposed_tsv(path: Path) -> tuple[list[str], list[str], list[list[str]]]:
    """Liest transponiertes SurvStat-TSV.

    Returns:
        (diseases, column_headers, value_rows)
        - diseases: Liste der Krankheitsnamen (aus Zeile 2+, Spalte 0)
        - column_headers: z.B. Bundesländer, Kreise oder Kalenderwochen
        - value_rows: Datenzeilen (jede Zeile = [disease, val1, val2, ...])
    """
    with path.open("r", encoding="utf-16", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))

    if len(rows) < 3:
        raise ValueError(f"Datei '{path.name}' hat zu wenige Zeilen ({len(rows)})")

    # Row 0: Meta-Header ["Krankheit", "Bundesland"/"Kreis"/"Meldewoche"]
    # Row 1: Spaltenheader ["", "Baden-Württemberg", "Bayern", ...] oder ["", "01", "02", ...]
    # Row 2+: Datenzeilen ["COVID-19", "47.516,13", "54.038,17", ...]

    col_headers = [c.strip().strip('"') for c in rows[1][1:]]
    data_rows = rows[2:]

    diseases: list[str] = []
    for row in data_rows:
        disease = row[0].strip().strip('"') if row else ""
        if disease:
            diseases.append(disease)

    return diseases, col_headers, data_rows


# ═══════════════════════════════════════════════════════════════════════
#  FORMAT 1: nach_meldewoche (Krankheit × Kalenderwoche)
# ═══════════════════════════════════════════════════════════════════════


def import_meldewoche(
    db: Session,
    path: Path,
    year: int,
    source_tag: str = "survstat_export",
) -> dict:
    """Importiert Meldewoche-Export → SurvstatWeeklyData.

    Jede Zeile wird zu N Records (ein pro Kalenderwoche).
    bundesland = 'Gesamt' (nationale Aggregation).
    """
    diseases, week_numbers, data_rows = _read_transposed_tsv(path)

    inserted, updated, skipped = 0, 0, 0

    for row in data_rows:
        disease = row[0].strip().strip('"') if row else ""
        if not disease:
            continue

        cluster = disease_to_cluster(disease)
        if cluster is None:
            skipped += 1
            continue

        for col_idx, week_str in enumerate(week_numbers, start=1):
            if col_idx >= len(row):
                break

            incidence = _parse_german_number(row[col_idx])
            if incidence is None:
                continue

            week = int(week_str)
            week_label = f"{year}_{week:02d}"

            try:
                week_start = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
            except ValueError:
                logger.warning("Ungültige Woche: %s_%02d", year, week)
                continue

            available_time = datetime(year + 1, 2, 21)  # Abfragedatum

            existing = (
                db.query(SurvstatWeeklyData)
                .filter(
                    SurvstatWeeklyData.week_label == week_label,
                    SurvstatWeeklyData.bundesland == "Gesamt",
                    SurvstatWeeklyData.disease == disease,
                )
                .first()
            )

            if existing:
                existing.incidence = incidence
                existing.disease_cluster = cluster
                existing.source_file = source_tag
                updated += 1
            else:
                db.add(SurvstatWeeklyData(
                    week_label=week_label,
                    week_start=week_start,
                    available_time=available_time,
                    year=year,
                    week=week,
                    bundesland="Gesamt",
                    disease=disease,
                    disease_cluster=cluster,
                    incidence=incidence,
                    source_file=source_tag,
                ))
                inserted += 1

    db.commit()
    logger.info(
        "Meldewoche import: %d inserted, %d updated, %d non-OTC skipped",
        inserted, updated, skipped,
    )
    return {
        "format": "meldewoche",
        "inserted": inserted,
        "updated": updated,
        "skipped_non_otc": skipped,
        "year": year,
    }


# ═══════════════════════════════════════════════════════════════════════
#  FORMAT 2: nach_bundesland (Krankheit × Bundesland)
# ═══════════════════════════════════════════════════════════════════════


def import_bundesland(
    db: Session,
    path: Path,
    year: int,
    source_tag: str = "survstat_export",
) -> dict:
    """Importiert Bundesland-Export → SurvstatWeeklyData.

    Kumulative Jahresinzidenz pro Bundesland. Wird mit week_label 'YYYY_00'
    (= Jahresaggregat) und week=0 gespeichert.
    """
    diseases, states, data_rows = _read_transposed_tsv(path)

    inserted, updated, skipped = 0, 0, 0
    week_label = f"{year}_00"
    week_start = datetime(year, 1, 1)
    available_time = datetime(year + 1, 2, 21)

    for row in data_rows:
        disease = row[0].strip().strip('"') if row else ""
        if not disease:
            continue

        cluster = disease_to_cluster(disease)
        if cluster is None:
            skipped += 1
            continue

        for col_idx, state in enumerate(states, start=1):
            if col_idx >= len(row):
                break

            incidence = _parse_german_number(row[col_idx])
            if incidence is None:
                continue

            existing = (
                db.query(SurvstatWeeklyData)
                .filter(
                    SurvstatWeeklyData.week_label == week_label,
                    SurvstatWeeklyData.bundesland == state,
                    SurvstatWeeklyData.disease == disease,
                )
                .first()
            )

            if existing:
                existing.incidence = incidence
                existing.disease_cluster = cluster
                existing.source_file = source_tag
                updated += 1
            else:
                db.add(SurvstatWeeklyData(
                    week_label=week_label,
                    week_start=week_start,
                    available_time=available_time,
                    year=year,
                    week=0,
                    bundesland=state,
                    disease=disease,
                    disease_cluster=cluster,
                    incidence=incidence,
                    source_file=source_tag,
                ))
                inserted += 1

    db.commit()
    logger.info(
        "Bundesland import: %d inserted, %d updated, %d non-OTC skipped",
        inserted, updated, skipped,
    )
    return {
        "format": "bundesland",
        "inserted": inserted,
        "updated": updated,
        "skipped_non_otc": skipped,
        "year": year,
    }


# ═══════════════════════════════════════════════════════════════════════
#  FORMAT 3: nach_landkreis (Krankheit × Kreis)
# ═══════════════════════════════════════════════════════════════════════


def import_landkreis(
    db: Session,
    path: Path,
    year: int,
    source_tag: str = "survstat_export",
) -> dict:
    """Importiert Landkreis-Export → SurvstatKreisData.

    Kumulative Jahresinzidenz pro Landkreis. week=0, week_label='YYYY_00'.
    fallzahl=0 (nur Inzidenz im Export verfügbar).
    """
    diseases, kreise, data_rows = _read_transposed_tsv(path)

    inserted, updated, skipped = 0, 0, 0
    week_label = f"{year}_00"

    for row in data_rows:
        disease = row[0].strip().strip('"') if row else ""
        if not disease:
            continue

        cluster = disease_to_cluster(disease)
        if cluster is None:
            skipped += 1
            continue

        for col_idx, kreis in enumerate(kreise, start=1):
            if col_idx >= len(row):
                break

            inzidenz = _parse_german_number(row[col_idx])
            if inzidenz is None:
                continue

            existing = (
                db.query(SurvstatKreisData)
                .filter(
                    SurvstatKreisData.week_label == week_label,
                    SurvstatKreisData.kreis == kreis,
                    SurvstatKreisData.disease == disease,
                )
                .first()
            )

            if existing:
                existing.inzidenz = inzidenz
                existing.disease_cluster = cluster
                updated += 1
            else:
                db.add(SurvstatKreisData(
                    year=year,
                    week=0,
                    week_label=week_label,
                    kreis=kreis,
                    disease=disease,
                    disease_cluster=cluster,
                    fallzahl=0,
                    inzidenz=inzidenz,
                ))
                inserted += 1

    db.commit()
    logger.info(
        "Landkreis import: %d inserted, %d updated, %d non-OTC skipped",
        inserted, updated, skipped,
    )
    return {
        "format": "landkreis",
        "inserted": inserted,
        "updated": updated,
        "skipped_non_otc": skipped,
        "year": year,
        "kreise_count": len(kreise),
    }


# ═══════════════════════════════════════════════════════════════════════
#  BATCH-IMPORT: ganzer Ordner
# ═══════════════════════════════════════════════════════════════════════


def import_survstat_exports(
    db: Session,
    folder: str,
    year: int = 2025,
) -> dict:
    """Importiert alle drei SurvStat-Export-Formate aus einem Ordner.

    Erwartet Unterordner:
      - nach_meldewoche/  (mit Data*.csv)
      - nach_bundesland/  (mit Data*.csv)
      - nach_landkreis/   (mit Data*.csv)

    Oder direkt CSV-Dateien mit Schlüsselwörtern im Pfad/Namen.
    """
    base = Path(folder).expanduser()
    if not base.exists():
        raise ValueError(f"Ordner nicht gefunden: {base}")

    results: dict[str, dict] = {}
    source_tag = f"survstat_export_{year}"

    # Auto-detect by subfolder name
    for sub in base.iterdir():
        if not sub.is_dir():
            continue

        csvs = sorted(sub.glob("*.csv"))
        if not csvs:
            continue

        csv_path = csvs[0]  # Nimm die erste CSV pro Unterordner
        name_lower = sub.name.lower()

        try:
            if "meldewoche" in name_lower:
                results["meldewoche"] = import_meldewoche(db, csv_path, year, source_tag)
            elif "bundesland" in name_lower:
                results["bundesland"] = import_bundesland(db, csv_path, year, source_tag)
            elif "landkreis" in name_lower or "kreis" in name_lower:
                results["landkreis"] = import_landkreis(db, csv_path, year, source_tag)
            else:
                logger.info("Überspringe unbekannten Unterordner: %s", sub.name)
        except Exception as exc:
            logger.error("Fehler beim Import von %s: %s", sub.name, exc)
            results[sub.name] = {"error": str(exc)}

    if not results:
        # Fallback: Einzeldateien im Ordner
        for csv_path in sorted(base.glob("*.csv")):
            name_lower = csv_path.stem.lower()
            try:
                if "meldewoche" in name_lower:
                    results["meldewoche"] = import_meldewoche(db, csv_path, year, source_tag)
                elif "bundesland" in name_lower:
                    results["bundesland"] = import_bundesland(db, csv_path, year, source_tag)
                elif "landkreis" in name_lower or "kreis" in name_lower:
                    results["landkreis"] = import_landkreis(db, csv_path, year, source_tag)
            except Exception as exc:
                logger.error("Fehler beim Import von %s: %s", csv_path.name, exc)
                results[csv_path.stem] = {"error": str(exc)}

    total_inserted = sum(r.get("inserted", 0) for r in results.values() if isinstance(r, dict))
    total_updated = sum(r.get("updated", 0) for r in results.values() if isinstance(r, dict))

    return {
        "success": total_inserted + total_updated > 0,
        "folder": str(base),
        "year": year,
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "formats": results,
        "timestamp": datetime.utcnow().isoformat(),
    }
