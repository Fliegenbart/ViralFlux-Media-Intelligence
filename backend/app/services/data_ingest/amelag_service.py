import pandas as pd
import requests
from datetime import datetime
from sqlalchemy.orm import Session
import logging
from typing import List

from app.core.config import get_settings
from app.models.database import WastewaterData, WastewaterAggregated

logger = logging.getLogger(__name__)
settings = get_settings()


class AmelagIngestionService:
    """Service zum Importieren von RKI AMELAG Abwasserdaten."""
    
    BASE_URL = settings.RKI_AMELAG_URL
    
    EINZELSTANDORTE_URL = f"{BASE_URL}/amelag_einzelstandorte.tsv"
    AGGREGIERT_URL = f"{BASE_URL}/amelag_aggregierte_kurve.tsv"
    
    def __init__(self, db: Session):
        self.db = db
    
    def fetch_einzelstandorte(self) -> pd.DataFrame:
        """Lade Einzelstandort-Daten von GitHub."""
        logger.info(f"Fetching AMELAG Einzelstandorte from {self.EINZELSTANDORTE_URL}")
        
        try:
            response = requests.get(self.EINZELSTANDORTE_URL, timeout=30)
            response.raise_for_status()
            
            # TSV einlesen
            df = pd.read_csv(
                pd.io.common.BytesIO(response.content),
                sep='\t',
                parse_dates=['datum']
            )
            
            logger.info(f"Loaded {len(df)} rows from Einzelstandorte")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching Einzelstandorte: {e}")
            raise
    
    def fetch_aggregiert(self) -> pd.DataFrame:
        """Lade aggregierte bundesweite Daten von GitHub."""
        logger.info(f"Fetching AMELAG aggregierte Kurve from {self.AGGREGIERT_URL}")
        
        try:
            response = requests.get(self.AGGREGIERT_URL, timeout=30)
            response.raise_for_status()
            
            df = pd.read_csv(
                pd.io.common.BytesIO(response.content),
                sep='\t',
                parse_dates=['datum']
            )
            
            logger.info(f"Loaded {len(df)} rows from aggregierte Kurve")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching aggregierte Kurve: {e}")
            raise
    
    def import_einzelstandorte(self, df: pd.DataFrame) -> int:
        """Importiere Einzelstandort-Daten in die Datenbank."""
        count = 0
        
        for _, row in df.iterrows():
            # Prüfen ob Eintrag bereits existiert
            existing = self.db.query(WastewaterData).filter(
                WastewaterData.standort == row['standort'],
                WastewaterData.datum == row['datum'],
                WastewaterData.virus_typ == row['typ']
            ).first()
            
            if existing:
                # Update
                existing.viruslast = row.get('viruslast')
                existing.viruslast_normalisiert = row.get('viruslast_normalisiert')
                existing.vorhersage = row.get('vorhersage')
                existing.obere_schranke = row.get('obere_schranke')
                existing.untere_schranke = row.get('untere_schranke')
                existing.einwohner = row.get('einwohner')
                existing.unter_bg = row.get('unter_bg') == 'ja'
            else:
                # Insert
                data = WastewaterData(
                    standort=row['standort'],
                    bundesland=row['bundesland'],
                    datum=row['datum'],
                    virus_typ=row['typ'],
                    viruslast=row.get('viruslast'),
                    viruslast_normalisiert=row.get('viruslast_normalisiert'),
                    vorhersage=row.get('vorhersage'),
                    obere_schranke=row.get('obere_schranke'),
                    untere_schranke=row.get('untere_schranke'),
                    einwohner=row.get('einwohner'),
                    unter_bg=row.get('unter_bg') == 'ja'
                )
                self.db.add(data)
                count += 1
        
        self.db.commit()
        logger.info(f"Imported {count} new Einzelstandorte records")
        return count
    
    def import_aggregiert(self, df: pd.DataFrame) -> int:
        """Importiere aggregierte Daten in die Datenbank."""
        count = 0
        
        for _, row in df.iterrows():
            existing = self.db.query(WastewaterAggregated).filter(
                WastewaterAggregated.datum == row['datum'],
                WastewaterAggregated.virus_typ == row['typ']
            ).first()
            
            if existing:
                existing.n_standorte = row.get('n')
                existing.anteil_bev = row.get('anteil_bev')
                existing.viruslast = row.get('viruslast')
                existing.viruslast_normalisiert = row.get('viruslast_normalisiert')
                existing.vorhersage = row.get('vorhersage')
                existing.obere_schranke = row.get('obere_schranke')
                existing.untere_schranke = row.get('untere_schranke')
            else:
                data = WastewaterAggregated(
                    datum=row['datum'],
                    virus_typ=row['typ'],
                    n_standorte=row.get('n'),
                    anteil_bev=row.get('anteil_bev'),
                    viruslast=row.get('viruslast'),
                    viruslast_normalisiert=row.get('viruslast_normalisiert'),
                    vorhersage=row.get('vorhersage'),
                    obere_schranke=row.get('obere_schranke'),
                    untere_schranke=row.get('untere_schranke')
                )
                self.db.add(data)
                count += 1
        
        self.db.commit()
        logger.info(f"Imported {count} new aggregated records")
        return count
    
    def run_full_import(self) -> dict:
        """Führe kompletten Import durch."""
        logger.info("Starting AMELAG full import...")
        
        try:
            # Einzelstandorte
            df_einzelstandorte = self.fetch_einzelstandorte()
            count_einzelstandorte = self.import_einzelstandorte(df_einzelstandorte)
            
            # Aggregiert
            df_aggregiert = self.fetch_aggregiert()
            count_aggregiert = self.import_aggregiert(df_aggregiert)
            
            result = {
                "success": True,
                "einzelstandorte_imported": count_einzelstandorte,
                "aggregiert_imported": count_aggregiert,
                "timestamp": datetime.utcnow()
            }
            
            logger.info(f"AMELAG import completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"AMELAG import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow()
            }
