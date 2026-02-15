"""GrippeWeb Ingestion Service — RKI ARE/ILI Surveillance-Daten."""

import pandas as pd
import requests
from io import StringIO
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.core.config import get_settings
from app.models.database import GrippeWebData

logger = logging.getLogger(__name__)
settings = get_settings()


class GrippeWebIngestionService:
    """Service zum Importieren von RKI GrippeWeb ARE/ILI Daten."""

    BASE_URL = settings.RKI_GRIPPEWEB_URL
    DATA_URL = f"{BASE_URL}/GrippeWeb_Daten_des_Wochenberichts.tsv"

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_iso_week(kw_str: str) -> datetime:
        """Convert 'YYYY-Www' to the Monday of that ISO week.

        Example: '2024-W03' → datetime(2024, 1, 15)
        """
        return datetime.strptime(kw_str.strip() + '-1', '%G-W%V-%u')

    @staticmethod
    def _extract_week_number(kw_str: str) -> int:
        """Extract week number from 'YYYY-Www' → int (e.g., 3)."""
        return int(kw_str.strip().split('-W')[1])

    def fetch_data(self) -> pd.DataFrame:
        """Lade GrippeWeb TSV von GitHub, parse und filtere auf aktuelle Saisons."""
        logger.info(f"Fetching GrippeWeb data from {self.DATA_URL}")

        response = requests.get(self.DATA_URL, timeout=120)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            dtype=str,
            na_values=['NA', 'na', ''],
        )

        logger.info(f"Loaded {len(df)} raw rows, columns: {df.columns.tolist()}")

        # Filter auf aktuelle Saisons (letzte 3)
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
        df['Inzidenz'] = pd.to_numeric(df['Inzidenz'], errors='coerce')
        df['Meldungen'] = pd.to_numeric(df['Meldungen'], errors='coerce')

        # Region mapping: 'Bundesweit' → None
        df['region_mapped'] = df['Region'].apply(
            lambda r: None if r == 'Bundesweit' else r
        )

        logger.info(
            f"Parsed GrippeWeb: {len(df)} rows, "
            f"Erkrankungen: {df['Erkrankung'].unique().tolist()}, "
            f"Altersgruppen: {df['Altersgruppe'].unique().tolist()}, "
            f"Regionen: {df['Region'].unique().tolist()}"
        )
        return df

    def import_data(self, df: pd.DataFrame) -> int:
        """Importiere GrippeWeb-Daten in die Datenbank (Upsert)."""
        count = 0
        updated = 0

        for _, row in df.iterrows():
            datum = row['datum']
            erkrankung_typ = row['Erkrankung']
            altersgruppe = row['Altersgruppe']
            bundesland = row['region_mapped']
            inzidenz = row['Inzidenz']
            meldungen = row['Meldungen']

            if pd.isna(inzidenz):
                continue

            # Upsert: check for existing record
            query = self.db.query(GrippeWebData).filter(
                GrippeWebData.datum == datum,
                GrippeWebData.erkrankung_typ == erkrankung_typ,
                GrippeWebData.altersgruppe == altersgruppe,
            )
            if bundesland is None:
                query = query.filter(GrippeWebData.bundesland.is_(None))
            else:
                query = query.filter(GrippeWebData.bundesland == bundesland)

            existing = query.first()

            vals = {
                'kalenderwoche': int(row['kw_num']),
                'inzidenz': float(inzidenz),
                'anzahl_meldungen': int(meldungen) if pd.notna(meldungen) else None,
            }

            if existing:
                for k, v in vals.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                data = GrippeWebData(
                    datum=datum,
                    erkrankung_typ=erkrankung_typ,
                    altersgruppe=altersgruppe,
                    bundesland=bundesland,
                    **vals,
                )
                self.db.add(data)
                count += 1

        self.db.commit()
        logger.info(f"GrippeWeb import: {count} new, {updated} updated")
        return count

    def run_full_import(self) -> dict:
        """Führe kompletten GrippeWeb-Import durch."""
        logger.info("Starting GrippeWeb full import...")

        try:
            df = self.fetch_data()
            count = self.import_data(df)

            saisons = df['Saison'].unique().tolist()
            erkrankungen = df['Erkrankung'].unique().tolist()

            return {
                "success": True,
                "imported": count,
                "fetched": len(df),
                "saisons": saisons,
                "erkrankungen": erkrankungen,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"GrippeWeb import failed: {e}")
            return {"success": False, "error": str(e)}
