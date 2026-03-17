"""ER admissions surveillance ingestion service (RKI/AKTIN).

Source: https://github.com/robert-koch-institut/Daten_der_Notaufnahmesurveillance
"""

from datetime import datetime
from io import StringIO
import logging

import pandas as pd
import requests
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import NotaufnahmeStandort, NotaufnahmeSyndromData
from app.services.ml.nowcast_revision import capture_nowcast_snapshots

logger = logging.getLogger(__name__)
settings = get_settings()


class ERAdmissionsIngestionService:
    """Ingest RKI/AKTIN ER admissions surveillance datasets (Syndromdaten)."""

    BASE_URL = settings.RKI_NOTAUFNAHME_URL
    SYNDROME_URL = f"{BASE_URL}/Notaufnahmesurveillance_Zeitreihen_Syndrome.tsv"
    FACILITIES_URL = f"{BASE_URL}/Notaufnahmesurveillance_Standorte.tsv"

    def __init__(self, db: Session):
        self.db = db

    def fetch_syndrome_timeseries(self) -> pd.DataFrame:
        """Fetch syndrome time series TSV from GitHub."""
        logger.info(f"Fetching ER admissions syndrome data from {self.SYNDROME_URL}")

        response = requests.get(self.SYNDROME_URL, timeout=180)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            dtype=str,
            na_values=['NA', 'na', ''],
        )

        required_cols = {
            'date',
            'ed_type',
            'age_group',
            'syndrome',
            'relative_cases',
            'relative_cases_7day_ma',
            'expected_value',
            'expected_lowerbound',
            'expected_upperbound',
            'ed_count',
        }
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"ER admissions syndrome dataset is missing columns: {sorted(missing)}")

        df['datum'] = pd.to_datetime(df['date'], errors='coerce')
        df = df[df['datum'].notna()].copy()

        for col in (
            'relative_cases',
            'relative_cases_7day_ma',
            'expected_value',
            'expected_lowerbound',
            'expected_upperbound',
            'ed_count',
        ):
            df[col] = pd.to_numeric(df[col], errors='coerce')

        logger.info(
            f"Loaded ER admissions syndromes: {len(df)} rows, "
            f"syndromes={sorted(df['syndrome'].dropna().unique().tolist())}, "
            f"ed_types={sorted(df['ed_type'].dropna().unique().tolist())}"
        )
        return df

    def upsert_syndrome_timeseries(self, df: pd.DataFrame) -> tuple[int, int]:
        """Upsert syndrome time series into the DB."""
        if df.empty:
            return 0, 0

        inserted = 0
        updated = 0

        min_date = df['datum'].min().to_pydatetime()
        max_date = df['datum'].max().to_pydatetime()

        existing_rows = self.db.query(NotaufnahmeSyndromData).filter(
            NotaufnahmeSyndromData.datum >= min_date,
            NotaufnahmeSyndromData.datum <= max_date,
        ).all()
        existing_map = {
            (row.datum.date(), row.ed_type, row.age_group, row.syndrome): row
            for row in existing_rows
        }

        for _, row in df.iterrows():
            ed_type = row.get('ed_type')
            age_group = row.get('age_group')
            syndrome = row.get('syndrome')
            datum = row.get('datum')

            if pd.isna(datum) or pd.isna(ed_type) or pd.isna(age_group) or pd.isna(syndrome):
                continue

            key = (datum.date(), str(ed_type), str(age_group), str(syndrome))

            vals = {
                'relative_cases': float(row['relative_cases']) if pd.notna(row['relative_cases']) else None,
                'relative_cases_7day_ma': float(row['relative_cases_7day_ma']) if pd.notna(row['relative_cases_7day_ma']) else None,
                'expected_value': float(row['expected_value']) if pd.notna(row['expected_value']) else None,
                'expected_lowerbound': float(row['expected_lowerbound']) if pd.notna(row['expected_lowerbound']) else None,
                'expected_upperbound': float(row['expected_upperbound']) if pd.notna(row['expected_upperbound']) else None,
                'ed_count': int(row['ed_count']) if pd.notna(row['ed_count']) else None,
            }

            existing = existing_map.get(key)
            if existing:
                for attr, value in vals.items():
                    setattr(existing, attr, value)
                updated += 1
            else:
                record = NotaufnahmeSyndromData(
                    datum=datum,
                    ed_type=str(ed_type),
                    age_group=str(age_group),
                    syndrome=str(syndrome),
                    **vals,
                )
                self.db.add(record)
                existing_map[key] = record
                inserted += 1

        self.db.commit()
        logger.info(f"ER admissions syndromes import: {inserted} new, {updated} updated")
        return inserted, updated

    def fetch_facilities(self) -> pd.DataFrame:
        """Fetch facility metadata TSV from GitHub."""
        logger.info(f"Fetching ER admissions facilities from {self.FACILITIES_URL}")

        response = requests.get(self.FACILITIES_URL, timeout=120)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            dtype=str,
            na_values=['NA', 'na', ''],
        )

        required_cols = {
            'ik_number',
            'ed_name',
            'ed_type',
            'level_of_care',
            'state',
            'state_id',
            'latitude',
            'longitude',
        }
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"ER admissions facilities dataset is missing columns: {sorted(missing)}")

        df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
        df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

        logger.info(
            f"Loaded ER admissions facilities: {len(df)} rows, "
            f"states={df['state'].nunique()}, types={df['ed_type'].nunique()}"
        )
        return df

    def upsert_facilities(self, df: pd.DataFrame) -> tuple[int, int]:
        """Upsert facility metadata into the DB."""
        if df.empty:
            return 0, 0

        inserted = 0
        updated = 0

        existing_rows = self.db.query(NotaufnahmeStandort).all()
        existing_map = {row.ik_number: row for row in existing_rows}

        for _, row in df.iterrows():
            ik = row.get('ik_number')
            if pd.isna(ik):
                continue
            ik = str(ik).strip()
            if not ik:
                continue

            vals = {
                'ed_name': str(row['ed_name']) if pd.notna(row['ed_name']) else None,
                'ed_type': str(row['ed_type']) if pd.notna(row['ed_type']) else None,
                'level_of_care': str(row['level_of_care']) if pd.notna(row['level_of_care']) else None,
                'state': str(row['state']) if pd.notna(row['state']) else None,
                'state_id': str(row['state_id']) if pd.notna(row['state_id']) else None,
                'latitude': float(row['latitude']) if pd.notna(row['latitude']) else None,
                'longitude': float(row['longitude']) if pd.notna(row['longitude']) else None,
            }

            existing = existing_map.get(ik)
            if existing:
                for attr, value in vals.items():
                    setattr(existing, attr, value)
                updated += 1
            else:
                record = NotaufnahmeStandort(
                    ik_number=ik,
                    **vals,
                )
                self.db.add(record)
                existing_map[ik] = record
                inserted += 1

        self.db.commit()
        logger.info(f"ER admissions facilities import: {inserted} new, {updated} updated")
        return inserted, updated

    def run_full_import(self) -> dict:
        """Run full ER admissions ingestion."""
        logger.info("Starting ER admissions full import...")
        results = {}

        try:
            syndromes = self.fetch_syndrome_timeseries()
            inserted, updated = self.upsert_syndrome_timeseries(syndromes)
            results['syndromes'] = {
                "success": True,
                "imported": inserted,
                "updated": updated,
                "fetched": len(syndromes),
                "syndrome_types": sorted(syndromes['syndrome'].dropna().unique().tolist()),
                "latest_date": syndromes['datum'].max().isoformat() if not syndromes.empty else None,
            }
        except Exception as e:
            logger.error(f"ER admissions syndromes import failed: {e}")
            results['syndromes'] = {"success": False, "error": str(e)}

        try:
            facilities = self.fetch_facilities()
            inserted, updated = self.upsert_facilities(facilities)
            results['standorte'] = {
                "success": True,
                "imported": inserted,
                "updated": updated,
                "fetched": len(facilities),
                "bundeslaender": int(facilities['state'].nunique()),
            }
        except Exception as e:
            logger.error(f"ER admissions facilities import failed: {e}")
            results['standorte'] = {"success": False, "error": str(e)}

        snapshot_rows = 0
        if results.get("syndromes", {}).get("success"):
            snapshot_rows = capture_nowcast_snapshots(self.db, ["notaufnahme"]).get("notaufnahme", 0)

        return {
            "success": results.get('syndromes', {}).get("success", False),
            "results": results,
            "snapshot_rows": snapshot_rows,
            "timestamp": datetime.utcnow().isoformat(),
        }
