"""RKI SurvStat SOAP/OLAP-Cube API Pipeline — Landkreis-Level Fallzahlen.

Die SurvStat API ist ein WCF-SOAP-Service (WSHttpBinding) mit SSAS-Backend.
Die Fallzahlen kommen als OLAP-Cube mit Zeilen=Kreise, Spalten=Meldewochen.

Pipeline:
    1. GetAllHierarchyMembers → Disease-Mapping (Caption → MemberId)
    2. Micro-Cubing: Pro Krankheit × Jahr ein GetOlapData-Request
       (Zeilen=Kreise, Spalten=Meldewochen)
    3. QueryResultRow/Values → DataFrame
    4. Sparse-Storage: Nur Fallzahl > 0 in die DB
    5. Inzidenz lokal berechnen (Fallzahl / Einwohner × 100.000)

Rate-Limiting: 1.5s sleep zwischen Requests um die RKI-WAF nicht
zu triggern.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.database import KreisEinwohner, SurvstatKreisData
from app.services.data_ingest.otc_disease_clusters import (
    ALL_OTC_DISEASES,
    disease_to_cluster,
)

logger = logging.getLogger(__name__)

# SOAP XML namespaces
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_ADDR = "http://www.w3.org/2005/08/addressing"
NS_SVC = "http://tools.rki.de/SurvStat/"
NS_MDX = "http://schemas.datacontract.org/2004/07/Rki.SurvStat.WebService.Contracts.Mdx"


def _tag(ns: str, local: str) -> str:
    """Build a fully-qualified XML tag."""
    return f"{{{ns}}}{local}"


class SurvstatApiService:
    """Fetches Landkreis-level case data from the RKI SurvStat SOAP API."""

    ENDPOINT = "https://tools.rki.de/SurvStat/SurvStatWebService.svc"
    RATE_LIMIT_DELAY = 1.5  # Seconds between API requests
    REQUEST_TIMEOUT = 90  # Seconds

    # Real MDX hierarchy IDs (discovered from GetAllDimensions)
    H_DISEASE = "[PathogenOut].[KategorieNz].[Krankheit DE]"
    H_YEAR = "[ReportingDate].[WeekYear].[WeekYear]"
    H_WEEK = "[ReportingDate].[Week].[Week]"
    H_COUNTY = "[DeutschlandNodes].[Kreise71Web].[CountyKey71]"

    OTC_DISEASES: list[str] = sorted(ALL_OTC_DISEASES)

    def __init__(self, db: Session) -> None:
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/soap+xml; charset=utf-8",
            "User-Agent": "ViralFlux-DataEngine/1.0",
        })
        self.disease_mapping: dict[str, str] = {}
        self._einwohner_cache: dict[str, int] | None = None

    # ------------------------------------------------------------------
    #  SOAP helpers
    # ------------------------------------------------------------------

    def _soap_call(self, action: str, body_xml: str) -> ET.Element:
        """Send SOAP request and return parsed XML root."""
        envelope = (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<s:Envelope xmlns:s="{NS_SOAP}" xmlns:a="{NS_ADDR}">'
            f"<s:Header>"
            f"<a:Action>{NS_SVC}SurvStatWebService/{action}</a:Action>"
            f"<a:To>{self.ENDPOINT}</a:To>"
            f"</s:Header>"
            f"<s:Body>{body_xml}</s:Body>"
            f"</s:Envelope>"
        )

        resp = self.session.post(
            self.ENDPOINT,
            data=envelope.encode("utf-8"),
            timeout=self.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)

        # Check for SOAP fault
        fault = root.find(f"{{{NS_SOAP}}}Body/{{{NS_SOAP}}}Fault")
        if fault is not None:
            reason_el = fault.find(f"{{{NS_SOAP}}}Reason/{{{NS_SOAP}}}Text")
            reason = reason_el.text if reason_el is not None else "Unknown SOAP fault"
            raise RuntimeError(f"SOAP Fault: {reason[:500]}")

        return root

    # ------------------------------------------------------------------
    #  Step 1: Metadata — discover RKI disease member IDs
    # ------------------------------------------------------------------

    def fetch_metadata(self) -> None:
        """Fetch disease members from RKI and build Caption → MemberId mapping."""
        logger.info("SurvStat SOAP: Lade Krankheits-Metadaten...")

        body = (
            f'<GetAllHierarchyMembers xmlns="{NS_SVC}">'
            f'<request xmlns:d="{NS_MDX}">'
            f"<d:Cube>SurvStat</d:Cube>"
            f"<d:HierarchyId>{self.H_DISEASE}</d:HierarchyId>"
            f"<d:Language>German</d:Language>"
            f"</request>"
            f"</GetAllHierarchyMembers>"
        )

        root = self._soap_call("GetAllHierarchyMembers", body)

        for member in root.iter(_tag(NS_MDX, "HierarchyMember")):
            caption_el = member.find(_tag(NS_MDX, "Caption"))
            id_el = member.find(_tag(NS_MDX, "Id"))
            if caption_el is not None and id_el is not None:
                caption = (caption_el.text or "").strip()
                mid = (id_el.text or "").strip()
                if caption and mid:
                    self.disease_mapping[caption] = mid

        logger.info(
            f"SurvStat Metadaten: {len(self.disease_mapping)} Krankheiten gefunden."
        )

    def _resolve_disease_id(self, disease: str) -> str | None:
        """Resolve OTC disease name to RKI member ID.

        Tries exact match first, then case-insensitive substring fallback.
        """
        # Exact match
        if disease in self.disease_mapping:
            return self.disease_mapping[disease]

        # Fuzzy: case-insensitive substring
        dl = disease.lower()
        for rki_name, mid in self.disease_mapping.items():
            if dl in rki_name.lower() or rki_name.lower() in dl:
                logger.info(f"Fuzzy-Match: '{disease}' → '{rki_name}'")
                return mid

        return None

    # ------------------------------------------------------------------
    #  Step 2: Build SOAP body for GetOlapData
    # ------------------------------------------------------------------

    def _build_olap_body(self, year: int, disease_id: str) -> str:
        """Build GetOlapData SOAP body: rows=Kreise, cols=Meldewochen.

        All values are XML-escaped to prevent malformed SOAP envelopes.
        """
        # XML-escape the IDs (they contain '&' characters)
        esc_disease_id = xml_escape(disease_id)
        esc_year_id = xml_escape(f"{self.H_YEAR}.&[{year}]")

        return (
            f'<GetOlapData xmlns="{NS_SVC}">'
            f'<request xmlns:d="{NS_MDX}">'
            f"<d:ColumnHierarchy>{self.H_WEEK}</d:ColumnHierarchy>"
            f"<d:Cube>SurvStat</d:Cube>"
            f"<d:HierarchyFilters>"
            # Filter: Year
            f"<d:KeyValueOfFilterCollectionKeyFilterMemberCollectionb2rWaiIW>"
            f"<d:Key><d:HierarchyId>{self.H_YEAR}</d:HierarchyId></d:Key>"
            f'<d:Value xmlns:e="{NS_MDX}">'
            f"<e:HierarchyMember>"
            f"<e:Caption>{year}</e:Caption>"
            f"<e:Id>{esc_year_id}</e:Id>"
            f"</e:HierarchyMember>"
            f"</d:Value>"
            f"</d:KeyValueOfFilterCollectionKeyFilterMemberCollectionb2rWaiIW>"
            # Filter: Disease
            f"<d:KeyValueOfFilterCollectionKeyFilterMemberCollectionb2rWaiIW>"
            f"<d:Key><d:HierarchyId>{self.H_DISEASE}</d:HierarchyId></d:Key>"
            f'<d:Value xmlns:e="{NS_MDX}">'
            f"<e:HierarchyMember>"
            f"<e:Caption></e:Caption>"
            f"<e:Id>{esc_disease_id}</e:Id>"
            f"</e:HierarchyMember>"
            f"</d:Value>"
            f"</d:KeyValueOfFilterCollectionKeyFilterMemberCollectionb2rWaiIW>"
            f"</d:HierarchyFilters>"
            f"<d:IncludeNullColumns>false</d:IncludeNullColumns>"
            f"<d:IncludeNullRows>false</d:IncludeNullRows>"
            f"<d:IncludeTotalColumn>false</d:IncludeTotalColumn>"
            f"<d:IncludeTotalRow>false</d:IncludeTotalRow>"
            f"<d:Language>German</d:Language>"
            f"<d:Measures>Count</d:Measures>"
            f"<d:RowHierarchy>{self.H_COUNTY}</d:RowHierarchy>"
            f"</request>"
            f"</GetOlapData>"
        )

    # ------------------------------------------------------------------
    #  Step 3: Fetch + parse OLAP cube
    # ------------------------------------------------------------------

    def _fetch_and_parse_cube(
        self, disease: str, disease_id: str, year: int
    ) -> pd.DataFrame:
        """Execute GetOlapData and parse the response to a DataFrame.

        Response structure (WCF data contract):
            GetOlapDataResult
              Columns → QueryResultColumn → Caption (week number)
              QueryResults → QueryResultRow → Caption (Kreis), Values → string[]
        """
        logger.info(f"SurvStat SOAP: {disease} / {year} — sende Cube-Request...")

        try:
            body = self._build_olap_body(year, disease_id)
            root = self._soap_call("GetOlapData", body)
        except requests.exceptions.RequestException as e:
            logger.error(f"SurvStat SOAP-Fehler für {disease} ({year}): {e}")
            return pd.DataFrame()
        except RuntimeError as e:
            logger.error(f"SurvStat SOAP-Fault für {disease} ({year}): {e}")
            return pd.DataFrame()

        # Extract column headers (Meldewochen)
        columns: list[str] = []
        for col in root.iter(_tag(NS_MDX, "QueryResultColumn")):
            caption_el = col.find(_tag(NS_MDX, "Caption"))
            if caption_el is not None and caption_el.text:
                columns.append(caption_el.text.strip())

        if not columns:
            logger.info(f"SurvStat: {disease} / {year} — keine Spalten in Antwort")
            return pd.DataFrame()

        # Extract row data (Kreise × Values)
        records: list[dict[str, Any]] = []
        for row in root.iter(_tag(NS_MDX, "QueryResultRow")):
            caption_el = row.find(_tag(NS_MDX, "Caption"))
            if caption_el is None or not caption_el.text:
                continue
            kreis = caption_el.text.strip()

            # Values: flat array of string elements (NS_MDX namespace)
            values_el = row.find(_tag(NS_MDX, "Values"))
            if values_el is None:
                continue

            vals: list[str] = []
            for v in values_el.iter(_tag(NS_MDX, "string")):
                vals.append(v.text or "")

            # Map values to week columns
            for i, val_str in enumerate(vals):
                if i >= len(columns):
                    break

                fallzahl = 0
                if val_str and val_str.strip():
                    cleaned = val_str.replace(".", "").replace(",", ".")
                    try:
                        fallzahl = int(float(cleaned))
                    except (ValueError, TypeError):
                        fallzahl = 0

                if fallzahl <= 0:
                    continue  # Sparse storage

                # Parse week number from column caption
                week_match = re.search(r"(\d+)", columns[i])
                week_num = int(week_match.group(1)) if week_match else 0
                if week_num == 0:
                    continue

                records.append({
                    "year": year,
                    "week": week_num,
                    "week_label": f"{year}_{week_num:02d}",
                    "kreis": kreis,
                    "disease": disease,
                    "disease_cluster": disease_to_cluster(disease),
                    "fallzahl": fallzahl,
                })

        df = pd.DataFrame(records)
        if not df.empty:
            logger.info(
                f"SurvStat: {disease} / {year} — {len(df)} Datenpunkte "
                f"(Kreise: {df['kreis'].nunique()}, Wochen: {df['week'].nunique()})"
            )
        else:
            logger.info(f"SurvStat: {disease} / {year} — keine Fälle")
        return df

    # ------------------------------------------------------------------
    #  Step 4: Compute incidence
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
            logger.info("Keine Einwohner-Daten — Inzidenz wird nicht berechnet.")
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
            f"Inzidenz: {matched}/{len(df)} berechnet "
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

        written = 0
        batch_size = 500
        for start in range(0, len(df), batch_size):
            batch = df.iloc[start : start + batch_size]
            for _, row in batch.iterrows():
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
                self.db.execute(stmt)
                written += 1
            self.db.commit()

        logger.info(f"DB Upsert: {written} Zeilen geschrieben.")
        return {"inserted": written, "updated": 0}

    # ------------------------------------------------------------------
    #  Step 6: Discover + seed Kreis names from API
    # ------------------------------------------------------------------

    def discover_and_seed_kreise(self) -> dict[str, Any]:
        """Fetch Kreis hierarchy from RKI and seed KreisEinwohner entries.

        Extracts AGS (5-digit code) from the MDX member IDs.
        """
        logger.info("SurvStat SOAP: Lade Kreis-Hierarchie...")

        body = (
            f'<GetAllHierarchyMembers xmlns="{NS_SVC}">'
            f'<request xmlns:d="{NS_MDX}">'
            f"<d:Cube>SurvStat</d:Cube>"
            f"<d:HierarchyId>{self.H_COUNTY}</d:HierarchyId>"
            f"<d:Language>German</d:Language>"
            f"</request>"
            f"</GetAllHierarchyMembers>"
        )

        root = self._soap_call("GetAllHierarchyMembers", body)

        kreise: list[dict[str, str]] = []
        for member in root.iter(_tag(NS_MDX, "HierarchyMember")):
            caption_el = member.find(_tag(NS_MDX, "Caption"))
            id_el = member.find(_tag(NS_MDX, "Id"))
            if caption_el is None or not caption_el.text:
                continue
            name = caption_el.text.strip()
            mid = (id_el.text or "") if id_el is not None else ""

            # Extract 5-digit AGS from MDX path: ...&[08315]
            ags_match = re.search(r"\.&\[(\d{5})\]", mid)
            ags = ags_match.group(1) if ags_match else None

            kreise.append({"name": name, "ags": ags})

        existing = {
            r.kreis_name
            for r in self.db.query(KreisEinwohner.kreis_name).all()
        }
        new_count = 0
        for k in kreise:
            if k["name"] in existing or k["name"] == "Unbekannt":
                continue
            self.db.add(KreisEinwohner(
                kreis_name=k["name"],
                ags=k["ags"],
                bundesland="",
                einwohner=0,
            ))
            new_count += 1

        if new_count:
            self.db.commit()
            logger.info(f"KreisEinwohner: {new_count} neue Kreise geseedet.")

        return {
            "total_rki_kreise": len(kreise),
            "new_seeded": new_count,
            "already_existed": len(existing),
        }

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

        # Resolve disease names to member IDs
        disease_tasks: list[tuple[str, str]] = []
        for disease in diseases:
            disease_id = self._resolve_disease_id(disease)
            if not disease_id:
                logger.warning(f"'{disease}' nicht im RKI-System. Überspringe...")
                errors.append(f"Nicht gefunden: {disease}")
                continue
            disease_tasks.append((disease, disease_id))

        logger.info(
            f"SurvStat: {len(disease_tasks)}/{len(diseases)} Krankheiten "
            f"aufgelöst, {len(years)} Jahre"
        )

        total_tasks = len(disease_tasks) * len(years)
        completed = 0

        # Step 2-3: Micro-cubing loop
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

                time.sleep(self.RATE_LIMIT_DELAY)

        # Step 4-5: Combine, compute incidence, save
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
            "db_written": db_result["inserted"],
            "errors": errors,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info(
            f"SurvStat Pipeline fertig: {total_records} Datenpunkte "
            f"in {elapsed}s ({len(errors)} Fehler)"
        )
        return result
