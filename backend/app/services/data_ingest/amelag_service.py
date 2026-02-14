import pandas as pd
import numpy as np
import requests
from io import StringIO
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.core.config import get_settings
from app.models.database import WastewaterAggregated, WastewaterData

logger = logging.getLogger(__name__)
settings = get_settings()


class AmelagIngestionService:
    """Service zum Importieren von RKI AMELAG Abwasserdaten."""

    BASE_URL = settings.RKI_AMELAG_URL
    AGGREGIERT_URL = f"{BASE_URL}/amelag_aggregierte_kurve.tsv"
    EINZELSTANDORTE_URL = f"{BASE_URL}/amelag_einzelstandorte.tsv"

    def __init__(self, db: Session):
        self.db = db

    def fetch_aggregiert(self) -> pd.DataFrame:
        """Lade aggregierte bundesweite Daten von GitHub."""
        logger.info(f"Fetching AMELAG aggregierte Kurve from {self.AGGREGIERT_URL}")

        response = requests.get(self.AGGREGIERT_URL, timeout=60)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            parse_dates=['datum'],
            na_values=['NA', 'na', ''],
        )

        # Numerische Spalten sicher konvertieren
        for col in ['viruslast', 'viruslast_normalisiert', 'vorhersage',
                     'obere_schranke', 'untere_schranke', 'n', 'anteil_bev']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        logger.info(f"Loaded {len(df)} rows, virus types: {df['typ'].unique().tolist()}")
        return df

    def import_aggregiert(self, df: pd.DataFrame) -> int:
        """Importiere aggregierte Daten in die Datenbank."""
        count = 0

        for _, row in df.iterrows():
            datum = row['datum']
            virus_typ = row['typ']
            viruslast = row.get('viruslast')

            # Skip rows ohne Viruslast
            if pd.isna(viruslast):
                continue

            existing = self.db.query(WastewaterAggregated).filter(
                WastewaterAggregated.datum == datum,
                WastewaterAggregated.virus_typ == virus_typ
            ).first()

            vals = {
                'n_standorte': int(row['n']) if pd.notna(row.get('n')) else None,
                'anteil_bev': float(row['anteil_bev']) if pd.notna(row.get('anteil_bev')) else None,
                'viruslast': float(viruslast),
                'viruslast_normalisiert': float(row['viruslast_normalisiert']) if pd.notna(row.get('viruslast_normalisiert')) else None,
                'vorhersage': float(row['vorhersage']) if pd.notna(row.get('vorhersage')) else None,
                'obere_schranke': float(row['obere_schranke']) if pd.notna(row.get('obere_schranke')) else None,
                'untere_schranke': float(row['untere_schranke']) if pd.notna(row.get('untere_schranke')) else None,
            }

            if existing:
                for k, v in vals.items():
                    setattr(existing, k, v)
            else:
                data = WastewaterAggregated(datum=datum, virus_typ=virus_typ, **vals)
                self.db.add(data)
                count += 1

        self.db.commit()
        logger.info(f"Imported {count} new aggregated records")
        return count

    def fetch_einzelstandorte(self) -> pd.DataFrame:
        """Lade Einzelstandort-Daten (pro Klaeranlage/Bundesland) von GitHub."""
        logger.info(f"Fetching AMELAG Einzelstandorte from {self.EINZELSTANDORTE_URL}")

        response = requests.get(self.EINZELSTANDORTE_URL, timeout=120)
        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text),
            sep='\t',
            parse_dates=['datum'],
            na_values=['NA', 'na', ''],
        )

        for col in ['viruslast', 'viruslast_normalisiert', 'vorhersage',
                     'obere_schranke', 'untere_schranke', 'einwohner']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'unter_bg' in df.columns:
            df['unter_bg'] = df['unter_bg'].map({'ja': True, 'nein': False})

        logger.info(f"Loaded {len(df)} Einzelstandort rows, {df['standort'].nunique()} sites, {df['bundesland'].nunique()} Bundeslaender")
        return df

    def import_einzelstandorte(self, df: pd.DataFrame) -> int:
        """Importiere Einzelstandort-Daten in die Datenbank."""
        count = 0

        for _, row in df.iterrows():
            datum = row['datum']
            virus_typ = row['typ']
            standort = row['standort']
            viruslast = row.get('viruslast')

            if pd.isna(viruslast):
                continue

            existing = self.db.query(WastewaterData).filter(
                WastewaterData.datum == datum,
                WastewaterData.virus_typ == virus_typ,
                WastewaterData.standort == standort
            ).first()

            vals = {
                'bundesland': row.get('bundesland', ''),
                'viruslast': float(viruslast),
                'viruslast_normalisiert': float(row['viruslast_normalisiert']) if pd.notna(row.get('viruslast_normalisiert')) else None,
                'vorhersage': float(row['vorhersage']) if pd.notna(row.get('vorhersage')) else None,
                'obere_schranke': float(row['obere_schranke']) if pd.notna(row.get('obere_schranke')) else None,
                'untere_schranke': float(row['untere_schranke']) if pd.notna(row.get('untere_schranke')) else None,
                'einwohner': int(row['einwohner']) if pd.notna(row.get('einwohner')) else None,
                'unter_bg': bool(row['unter_bg']) if pd.notna(row.get('unter_bg')) else None,
            }

            if existing:
                for k, v in vals.items():
                    setattr(existing, k, v)
            else:
                data = WastewaterData(datum=datum, virus_typ=virus_typ, standort=standort, **vals)
                self.db.add(data)
                count += 1

        self.db.commit()
        logger.info(f"Imported {count} new Einzelstandort records")
        return count

    def run_full_import(self) -> dict:
        """Fuehre kompletten Import durch (aggregiert + Einzelstandorte)."""
        logger.info("Starting AMELAG full import...")

        results = {}

        # Aggregierte Daten
        try:
            df_agg = self.fetch_aggregiert()
            count_agg = self.import_aggregiert(df_agg)
            results["aggregiert"] = {"success": True, "imported": count_agg, "fetched": len(df_agg)}
        except Exception as e:
            logger.error(f"Aggregiert import failed: {e}")
            results["aggregiert"] = {"success": False, "error": str(e)}

        # Einzelstandorte
        try:
            df_einzel = self.fetch_einzelstandorte()
            count_einzel = self.import_einzelstandorte(df_einzel)
            results["einzelstandorte"] = {
                "success": True,
                "imported": count_einzel,
                "fetched": len(df_einzel),
                "standorte": int(df_einzel['standort'].nunique()),
                "bundeslaender": int(df_einzel['bundesland'].nunique()),
            }
        except Exception as e:
            logger.error(f"Einzelstandorte import failed: {e}")
            results["einzelstandorte"] = {"success": False, "error": str(e)}

        return {
            "success": results.get("aggregiert", {}).get("success", False),
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
