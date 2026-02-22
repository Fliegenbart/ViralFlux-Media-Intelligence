"""RKI SurvStat OLAP-Cube API Pipeline — Landkreis-Level Fallzahlen.

Die SurvStat API liefert keine einfachen JSON-Zeilen, sondern einen
mehrdimensionalen OLAP-Cube (Microsoft SSAS). Die Fallzahlen kommen als
flaches 1D-Array, das über das kartesische Produkt der Dimensionsachsen
(Kreise × Meldewochen) entwirrt werden muss.

Pipeline:
    1. GetAllNodes → Disease-Mapping (Caption → interne NodeId)
    2. Micro-Cubing: Pro Krankheit × Jahr ein GetCubeData-Request
       (Zeilen=Kreise, Spalten=Meldewochen)
    3. OLAP-Cube Flattening: itertools.product × Values → DataFrame
    4. Sparse-Storage: Nur Fallzahl > 0 in die DB
    5. Inzidenz lokal berechnen (Fallzahl / Einwohner × 100.000)

Rate-Limiting: 1.5s sleep zwischen Requests um die RKI-WAF nicht
zu triggern.
"""

from __future__ import annotations

import itertools
import logging
import re
import time
from datetime import datetime
from typing import Any

import pandas as pd
import requests
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.database import KreisEinwohner, SurvstatKreisData
from app.services.data_ingest.otc_disease_clusters import (
    ALL_OTC_DISEASES,
    disease_to_cluster,
)

logger = logging.getLogger(__name__)


class SurvstatApiService:
    """Fetches Landkreis-level case data from the RKI SurvStat OLAP API."""

    BASE_URL = "https://tools.rki.de/SurvStat/SurvStatWebService.svc/rest"
    RATE_LIMIT_DELAY = 1.5  # Seconds between API requests
    REQUEST_TIMEOUT = 60  # Seconds

    # MDX hierarchy identifiers for the SurvStat OLAP cube
    H_DISEASE = "[Krankheit].[Krankheit]"
    H_YEAR = "[MeldeJahrWoche].[Meldejahr]"
    H_WEEK = "[MeldeJahrWoche].[Meldewoche]"
    H_COUNTY = "[Kreis71].[Kreis71]"  # Kreisreform 71 = aktuelle Landkreisstruktur

    # OTC disease whitelist — matches our otc_disease_clusters.py exactly
    OTC_DISEASES: list[str] = sorted(ALL_OTC_DISEASES)

    def __init__(self, db: Session) -> None:
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ViralFlux-DataEngine/1.0",
        })
        self.disease_mapping: dict[str, str] = {}
        self._einwohner_cache: dict[str, int] | None = None

    # ------------------------------------------------------------------
    #  Step 1: Metadata — discover RKI disease NodeIds dynamically
    # ------------------------------------------------------------------

    def fetch_metadata(self) -> None:
        """Fetch disease hierarchy from RKI and build Caption → NodeId mapping.

        The RKI uses internal IDs (e.g. ``&[14]``) — never hard-code them.
        """
        url = f"{self.BASE_URL}/GetAllNodes"
        payload = {"Language": "German", "HierarchyId": self.H_DISEASE}

        logger.info("SurvStat API: Lade Krankheits-Metadaten (GetAllNodes)...")
        resp = self.session.post(url, json=payload, timeout=self.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # WCF response envelope
        if "d" in data:
            data = data["d"]
        elif "GetAllNodesResult" in data:
            data = data["GetAllNodesResult"]

        # Walk the tree recursively
        def _walk(nodes: list[dict]) -> None:
            for node in nodes:
                caption = node.get("Caption", "")
                node_id = node.get("Id", "")
                if caption and node_id:
                    self.disease_mapping[caption] = node_id
                children = node.get("Children") or node.get("Nodes") or []
                if children:
                    _walk(children)

        root = data.get("Children") or data.get("Nodes") or []
        _walk(root)
        logger.info(
            f"SurvStat Metadaten geladen: {len(self.disease_mapping)} "
            f"Krankheiten im RKI-System."
        )

    # ------------------------------------------------------------------
    #  Step 2: Build OLAP cube request payload
    # ------------------------------------------------------------------

    def _build_cube_payload(self, year: int, disease_id: str) -> dict[str, Any]:
        """Build GetCubeData JSON: rows=Kreise, cols=Meldewochen."""
        return {
            "Language": "German",
            "Cube": "SurvStat",
            "HierarchyList": [
                {"Id": self.H_COUNTY},   # Dimension 0 (rows)
                {"Id": self.H_WEEK},     # Dimension 1 (columns)
            ],
            "FilterList": [
                {
                    "HierarchyId": self.H_YEAR,
                    "NodeId": f"{self.H_YEAR}.&[{year}]",
                },
                {
                    "HierarchyId": self.H_DISEASE,
                    "NodeId": disease_id,
                },
            ],
            "IncludeTotalColumn": False,
            "IncludeTotalRow": False,
            "IncludeNullRows": False,
            "IncludeNullColumns": False,
        }

    # ------------------------------------------------------------------
    #  Step 3: Fetch + flatten OLAP cube
    # ------------------------------------------------------------------

    def _fetch_and_parse_cube(
        self, disease: str, disease_id: str, year: int
    ) -> pd.DataFrame:
        """Execute GetCubeData and flatten the OLAP response to a DataFrame."""
        url = f"{self.BASE_URL}/GetCubeData"
        payload = self._build_cube_payload(year, disease_id)

        logger.info(f"SurvStat API: {disease} / {year} — sende Cube-Request...")

        try:
            resp = self.session.post(
                url, json=payload, timeout=self.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"SurvStat API-Fehler für {disease} ({year}): {e}")
            return pd.DataFrame()

        # Unwrap WCF envelope
        if "d" in data:
            data = data["d"]
        elif "GetCubeDataResult" in data:
            data = data["GetCubeDataResult"]

        query_result = data.get("QueryResult", {})
        if not query_result:
            logger.warning(f"Kein QueryResult für {disease} / {year}")
            return pd.DataFrame()

        dimensions = query_result.get("Dimensions", [])
        values = query_result.get("Values", [])

        if len(dimensions) < 2 or not values:
            logger.warning(f"Keine Fälle für {disease} / {year}")
            return pd.DataFrame()

        # Extract axis labels
        def _get_captions(dim: dict) -> list[str]:
            nodes = dim.get("Nodes") or dim.get("Members") or []
            return [n.get("Caption", "Unbekannt") for n in nodes]

        counties = _get_captions(dimensions[0])
        weeks = _get_captions(dimensions[1])

        if not counties or not weeks:
            return pd.DataFrame()

        # Cartesian product — the key trick for OLAP cube flattening
        combinations = list(itertools.product(counties, weeks))

        records: list[dict[str, Any]] = []
        for (kreis, week_str), val in zip(combinations, values):
            # Parse value (RKI returns "" for zero)
            fallzahl = 0
            if val not in (None, ""):
                cleaned = str(val).replace(".", "").replace(",", ".")
                try:
                    fallzahl = int(float(cleaned))
                except (ValueError, TypeError):
                    fallzahl = 0

            # Sparse storage: skip zeros
            if fallzahl <= 0:
                continue

            # Parse week number from e.g. "MW 01", "01", "KW 05"
            week_match = re.search(r"(\d+)", str(week_str))
            week_num = int(week_match.group(1)) if week_match else 0
            if week_num == 0:
                continue

            week_label = f"{year}_{week_num:02d}"
            cluster = disease_to_cluster(disease)

            records.append({
                "year": year,
                "week": week_num,
                "week_label": week_label,
                "kreis": kreis,
                "disease": disease,
                "disease_cluster": cluster,
                "fallzahl": fallzahl,
            })

        df = pd.DataFrame(records)
        if not df.empty:
            logger.info(
                f"SurvStat: {disease} / {year} — {len(df)} Datenpunkte "
                f"(Kreise: {df['kreis'].nunique()}, Wochen: {df['week'].nunique()})"
            )
        return df

    # ------------------------------------------------------------------
    #  Step 4: Compute incidence using local Einwohner data
    # ------------------------------------------------------------------

    def _load_einwohner_cache(self) -> dict[str, int]:
        """Load Kreis → Einwohner mapping from DB."""
        if self._einwohner_cache is not None:
            return self._einwohner_cache

        rows = self.db.query(
            KreisEinwohner.kreis_name, KreisEinwohner.einwohner
        ).all()
        self._einwohner_cache = {r.kreis_name: r.einwohner for r in rows}
        return self._einwohner_cache

    def _compute_inzidenz(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add inzidenz column: Fallzahl / Einwohner × 100.000."""
        einwohner = self._load_einwohner_cache()
        if not einwohner:
            logger.info(
                "Keine Einwohner-Daten in kreis_einwohner — "
                "Inzidenz wird nicht berechnet."
            )
            df["inzidenz"] = None
            return df

        df["inzidenz"] = df.apply(
            lambda row: round(
                row["fallzahl"] / einwohner[row["kreis"]] * 100_000, 2
            )
            if row["kreis"] in einwohner and einwohner[row["kreis"]] > 0
            else None,
            axis=1,
        )
        matched = df["inzidenz"].notna().sum()
        logger.info(
            f"Inzidenz berechnet für {matched}/{len(df)} Datenpunkte "
            f"({len(einwohner)} Kreise in Referenztabelle)."
        )
        return df

    # ------------------------------------------------------------------
    #  Step 5: Upsert to database
    # ------------------------------------------------------------------

    def _save_to_db(self, df: pd.DataFrame) -> dict[str, int]:
        """Upsert DataFrame rows into survstat_kreis_data."""
        if df.empty:
            return {"inserted": 0, "updated": 0}

        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            stmt = pg_insert(SurvstatKreisData).values(
                year=int(row["year"]),
                week=int(row["week"]),
                week_label=row["week_label"],
                kreis=row["kreis"],
                disease=row["disease"],
                disease_cluster=row.get("disease_cluster"),
                fallzahl=int(row["fallzahl"]),
                inzidenz=row.get("inzidenz"),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_survstat_kreis",
                set_={
                    "fallzahl": stmt.excluded.fallzahl,
                    "inzidenz": stmt.excluded.inzidenz,
                    "disease_cluster": stmt.excluded.disease_cluster,
                },
            )
            result = self.db.execute(stmt)
            if result.rowcount:
                # PostgreSQL: rowcount=1 for both insert and update
                inserted += 1
            else:
                updated += 1

        self.db.commit()
        logger.info(f"DB Upsert: {inserted} Zeilen geschrieben.")
        return {"inserted": inserted, "updated": updated}

    # ------------------------------------------------------------------
    #  Step 6: Discover Kreis names and seed KreisEinwohner
    # ------------------------------------------------------------------

    def discover_and_seed_kreise(self) -> int:
        """Fetch Kreis hierarchy from RKI and seed KreisEinwohner entries.

        Only creates entries for Kreise that don't exist yet.
        Sets einwohner=0 as placeholder (to be updated with Destatis data).
        Returns count of newly discovered Kreise.
        """
        url = f"{self.BASE_URL}/GetAllNodes"
        payload = {"Language": "German", "HierarchyId": self.H_COUNTY}

        logger.info("SurvStat API: Lade Kreis-Hierarchie (GetAllNodes)...")
        resp = self.session.post(url, json=payload, timeout=self.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if "d" in data:
            data = data["d"]
        elif "GetAllNodesResult" in data:
            data = data["GetAllNodesResult"]

        kreise: list[str] = []

        def _walk(nodes: list[dict]) -> None:
            for node in nodes:
                caption = node.get("Caption", "")
                if caption and caption != "Unbekannt":
                    kreise.append(caption)
                children = node.get("Children") or node.get("Nodes") or []
                if children:
                    _walk(children)

        root = data.get("Children") or data.get("Nodes") or []
        _walk(root)

        # Infer Bundesland from Kreis name (heuristic)
        existing = {
            r.kreis_name
            for r in self.db.query(KreisEinwohner.kreis_name).all()
        }
        new_count = 0
        for kreis in kreise:
            if kreis in existing:
                continue
            # RKI Kreis names often start with "SK" (Stadtkreis) or "LK" (Landkreis)
            self.db.add(KreisEinwohner(
                kreis_name=kreis,
                bundesland="",  # To be filled by admin
                einwohner=0,    # Placeholder
            ))
            new_count += 1

        if new_count:
            self.db.commit()
            logger.info(
                f"KreisEinwohner: {new_count} neue Kreise aus RKI-Hierarchie "
                f"geseedet (Einwohner=0, bitte Destatis-Daten nachpflegen)."
            )
        return new_count

    # ------------------------------------------------------------------
    #  Main orchestration
    # ------------------------------------------------------------------

    def run(
        self,
        years: list[int] | None = None,
        diseases: list[str] | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Run the full SurvStat Landkreis pipeline.

        Args:
            years: Years to fetch. Default: [current-1, current].
            diseases: Disease filter. Default: all OTC diseases.
            progress_callback: Optional callable(state, meta) for Celery progress.

        Returns:
            Summary dict with counts and errors.
        """
        start = time.time()
        current_year = datetime.now().year

        if years is None:
            years = [current_year - 1, current_year]
        if diseases is None:
            diseases = self.OTC_DISEASES

        errors: list[str] = []
        total_records = 0
        total_diseases_fetched = 0

        # Step 1: Metadata
        try:
            self.fetch_metadata()
        except Exception as e:
            msg = f"Metadata-Abruf fehlgeschlagen: {e}"
            logger.error(msg)
            return {"success": False, "error": msg}

        # Resolve disease names to IDs
        disease_tasks: list[tuple[str, str]] = []
        for disease in diseases:
            disease_id = self.disease_mapping.get(disease)
            if not disease_id:
                logger.warning(
                    f"Krankheit '{disease}' nicht im RKI-System gefunden. "
                    f"Überspringe..."
                )
                errors.append(f"Krankheit nicht gefunden: {disease}")
                continue
            disease_tasks.append((disease, disease_id))

        total_tasks = len(disease_tasks) * len(years)
        completed = 0

        # Step 2-5: Micro-cubing loop
        all_dfs: list[pd.DataFrame] = []

        for disease, disease_id in disease_tasks:
            for year in years:
                try:
                    df = self._fetch_and_parse_cube(disease, disease_id, year)
                    if not df.empty:
                        all_dfs.append(df)
                        total_records += len(df)
                        total_diseases_fetched += 1
                except Exception as e:
                    msg = f"{disease} / {year}: {e}"
                    logger.error(f"Cube-Fehler: {msg}")
                    errors.append(msg)

                completed += 1
                if progress_callback and total_tasks > 0:
                    progress_callback(
                        "PROGRESS",
                        {
                            "step": f"{disease} / {year}",
                            "progress": int(completed / total_tasks * 100),
                            "records_so_far": total_records,
                        },
                    )

                # Rate limiting — critical for RKI WAF
                time.sleep(self.RATE_LIMIT_DELAY)

        # Combine and compute incidence
        db_result = {"inserted": 0, "updated": 0}
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            combined = self._compute_inzidenz(combined)
            db_result = self._save_to_db(combined)

        elapsed = round(time.time() - start, 1)

        result = {
            "success": True,
            "years": years,
            "diseases_requested": len(diseases),
            "diseases_found": len(disease_tasks),
            "diseases_with_data": total_diseases_fetched,
            "total_records": total_records,
            "db_inserted": db_result["inserted"],
            "db_updated": db_result["updated"],
            "errors": errors,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info(
            f"SurvStat Pipeline abgeschlossen: {total_records} Datenpunkte "
            f"in {elapsed}s ({len(errors)} Fehler)"
        )
        return result
