"""Influenza IfSG Ingestion Service — RKI Influenzafälle in Deutschland."""

import pandas as pd
import requests
from io import StringIO
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from app.core.config import get_settings
from app.models.database import InfluenzaData

logger = logging.getLogger(__name__)
settings = get_settings()


class InfluenzaIngestionService:
    """Service zum Importieren von RKI IfSG Influenza-Meldedaten."""

    DATA_URL = settings.RKI_INFLUENZA_URL
    AVAILABILITY_DELAY_DAYS = 1

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_iso_week(kw_str: str) -> datetime:
        """Convert 'YYYY-Wxx' to the Monday of that ISO week."""
        return datetime.strptime(kw_str.strip() + '-1', '%G-W%V-%u')

    def fetch_data(self) -> pd.DataFrame:
        """Lade Influenza-TSV von GitHub."""
        logger.info(f"Fetching Influenza data from {self.DATA_URL}")

        response = requests.get(self.DATA_URL, timeout=120)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            dtype=str,
            na_values=['NA', 'na', ''],
        )

        logger.info(f"Loaded {len(df)} raw rows, columns: {df.columns.tolist()}")

        # Datum parsen
        df['datum'] = df['Meldewoche'].apply(self._parse_iso_week)

        # Numerische Spalten konvertieren
        df['Fallzahl'] = pd.to_numeric(df['Fallzahl'], errors='coerce')
        df['Inzidenz'] = pd.to_numeric(df['Inzidenz'], errors='coerce')

        logger.info(
            f"Parsed Influenza: {len(df)} rows, "
            f"Regionen: {df['Region'].nunique()}, "
            f"Altersgruppen: {df['Altersgruppe'].unique().tolist()}"
        )
        return df

    def import_data(self, df: pd.DataFrame) -> int:
        """Importiere Influenza-Daten in die Datenbank (Upsert)."""
        count = 0
        updated = 0

        for _, row in df.iterrows():
            datum = row['datum']
            region = row['Region']
            altersgruppe = row['Altersgruppe']
            meldewoche = row['Meldewoche']
            region_id = row.get('Region_Id')
            fallzahl = row['Fallzahl']
            inzidenz = row['Inzidenz']

            available_time = datum + timedelta(days=self.AVAILABILITY_DELAY_DAYS)

            vals = {
                'meldewoche': meldewoche,
                'region_id': region_id if pd.notna(region_id) else None,
                'fallzahl': int(fallzahl) if pd.notna(fallzahl) else None,
                'inzidenz': float(inzidenz) if pd.notna(inzidenz) else None,
            }

            existing = self.db.query(InfluenzaData).filter(
                InfluenzaData.datum == datum,
                InfluenzaData.region == region,
                InfluenzaData.altersgruppe == altersgruppe,
            ).first()

            if existing:
                for k, v in vals.items():
                    setattr(existing, k, v)
                if existing.available_time is None:
                    existing.available_time = available_time
                updated += 1
            else:
                data = InfluenzaData(
                    datum=datum,
                    available_time=available_time,
                    region=region,
                    altersgruppe=altersgruppe,
                    **vals,
                )
                self.db.add(data)
                count += 1

        self.db.commit()
        logger.info(f"Influenza import: {count} new, {updated} updated")
        return count

    def run_full_import(self) -> dict:
        """Führe kompletten Influenza-Import durch."""
        logger.info("Starting Influenza full import...")

        try:
            df = self.fetch_data()
            count = self.import_data(df)

            return {
                "success": True,
                "imported": count,
                "fetched": len(df),
                "regionen": int(df['Region'].nunique()),
                "altersgruppen": df['Altersgruppe'].unique().tolist(),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Influenza import failed: {e}")
            return {"success": False, "error": str(e)}
