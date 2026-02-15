"""ARE-Konsultationsinzidenz Ingestion Service — RKI Syndromische Surveillance.

Wöchentliche Arztbesuche wegen akuter Atemwegserkrankungen pro 100.000 Einwohner.
Datenquelle: https://github.com/robert-koch-institut/ARE-Konsultationsinzidenz
"""

import pandas as pd
import requests
from io import StringIO
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.core.config import get_settings
from app.models.database import AREKonsultation

logger = logging.getLogger(__name__)
settings = get_settings()


class AREKonsultationIngestionService:
    """Service zum Importieren von RKI ARE-Konsultationsinzidenz Daten."""

    DATA_URL = settings.RKI_ARE_KONSULTATION_URL

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_iso_week(kw_str: str) -> datetime:
        """Convert 'YYYY-Www' to the Monday of that ISO week.

        Example: '2024-W03' -> datetime(2024, 1, 15)
        """
        return datetime.strptime(kw_str.strip() + '-1', '%G-W%V-%u')

    @staticmethod
    def _extract_week_number(kw_str: str) -> int:
        """Extract week number from 'YYYY-Www' -> int (e.g., 3)."""
        return int(kw_str.strip().split('-W')[1])

    def fetch_data(self) -> pd.DataFrame:
        """Lade ARE-Konsultationsinzidenz TSV von GitHub, parse und filtere."""
        logger.info(f"Fetching ARE-Konsultationsinzidenz from {self.DATA_URL}")

        response = requests.get(self.DATA_URL, timeout=120)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            dtype=str,
            na_values=['NA', 'na', ''],
        )

        logger.info(f"Loaded {len(df)} raw rows, columns: {df.columns.tolist()}")

        # Filter auf letzte 3 Saisons
        current_year = datetime.now().year
        min_season_start = current_year - 3
        df = df[df['Saison'].apply(
            lambda s: int(s.split('/')[0]) >= min_season_start if pd.notna(s) else False
        )]
        logger.info(f"After season filter (>= {min_season_start}): {len(df)} rows")

        # Datum parsen
        df['datum'] = df['Kalenderwoche'].apply(self._parse_iso_week)
        df['kw_num'] = df['Kalenderwoche'].apply(self._extract_week_number)

        # Numerische Spalten konvertieren
        df['ARE_Konsultationsinzidenz'] = pd.to_numeric(
            df['ARE_Konsultationsinzidenz'], errors='coerce'
        )
        df['Bundesland_ID'] = pd.to_numeric(df['Bundesland_ID'], errors='coerce')

        logger.info(
            f"Parsed ARE-Konsultation: {len(df)} rows, "
            f"Altersgruppen: {df['Altersgruppe'].unique().tolist()}, "
            f"Bundeslaender: {df['Bundesland'].nunique()}"
        )
        return df

    def import_data(self, df: pd.DataFrame) -> int:
        """Importiere ARE-Konsultationsinzidenz Daten in die Datenbank (Upsert)."""
        count = 0
        updated = 0

        for _, row in df.iterrows():
            datum = row['datum']
            saison = row['Saison']
            altersgruppe = row['Altersgruppe']
            bundesland = row['Bundesland']
            bundesland_id = row['Bundesland_ID']
            konsultationsinzidenz = row['ARE_Konsultationsinzidenz']

            if pd.isna(konsultationsinzidenz):
                continue

            # Upsert: check for existing record by natural key
            existing = self.db.query(AREKonsultation).filter(
                AREKonsultation.datum == datum,
                AREKonsultation.altersgruppe == altersgruppe,
                AREKonsultation.bundesland == bundesland,
            ).first()

            vals = {
                'kalenderwoche': int(row['kw_num']),
                'saison': saison,
                'bundesland_id': int(bundesland_id) if pd.notna(bundesland_id) else None,
                'konsultationsinzidenz': int(konsultationsinzidenz),
            }

            if existing:
                for k, v in vals.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                data = AREKonsultation(
                    datum=datum,
                    altersgruppe=altersgruppe,
                    bundesland=bundesland,
                    **vals,
                )
                self.db.add(data)
                count += 1

        self.db.commit()
        logger.info(f"ARE-Konsultation import: {count} new, {updated} updated")
        return count

    def run_full_import(self) -> dict:
        """Führe kompletten ARE-Konsultationsinzidenz-Import durch."""
        logger.info("Starting ARE-Konsultationsinzidenz full import...")

        try:
            df = self.fetch_data()
            count = self.import_data(df)

            saisons = df['Saison'].unique().tolist()
            bundeslaender = df['Bundesland'].unique().tolist()

            return {
                "success": True,
                "imported": count,
                "fetched": len(df),
                "saisons": saisons,
                "bundeslaender": bundeslaender,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"ARE-Konsultation import failed: {e}")
            return {"success": False, "error": str(e)}
