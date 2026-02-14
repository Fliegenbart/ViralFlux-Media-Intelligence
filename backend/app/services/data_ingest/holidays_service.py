from datetime import datetime, date
from sqlalchemy.orm import Session
import logging

from app.models.database import SchoolHolidays

logger = logging.getLogger(__name__)


class SchoolHolidaysService:
    """Service zum Verwalten von Schulferien-Daten."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def load_holidays_2025_2026(self):
        """
        Lade Schulferien 2025-2026 für alle deutschen Bundesländer.
        
        Quelle: Statische Daten (können später durch API ersetzt werden)
        """
        logger.info("Loading school holidays for 2025-2026...")
        
        # Beispiel-Daten für 2025-2026
        # In Produktion: API von schulferien.org oder offizielle Quellen
        holidays_data = [
            # Bayern
            {"bundesland": "BY", "typ": "Winterferien", "start": "2026-02-16", "end": "2026-02-20", "jahr": 2026},
            {"bundesland": "BY", "typ": "Osterferien", "start": "2026-04-06", "end": "2026-04-18", "jahr": 2026},
            {"bundesland": "BY", "typ": "Pfingstferien", "start": "2026-05-26", "end": "2026-06-05", "jahr": 2026},
            {"bundesland": "BY", "typ": "Sommerferien", "start": "2026-08-03", "end": "2026-09-14", "jahr": 2026},
            {"bundesland": "BY", "typ": "Herbstferien", "start": "2026-11-02", "end": "2026-11-06", "jahr": 2026},
            {"bundesland": "BY", "typ": "Weihnachtsferien", "start": "2026-12-23", "end": "2027-01-05", "jahr": 2026},
            
            # Nordrhein-Westfalen
            {"bundesland": "NW", "typ": "Winterferien", "start": "2026-02-09", "end": "2026-02-10", "jahr": 2026},
            {"bundesland": "NW", "typ": "Osterferien", "start": "2026-03-30", "end": "2026-04-11", "jahr": 2026},
            {"bundesland": "NW", "typ": "Sommerferien", "start": "2026-06-29", "end": "2026-08-11", "jahr": 2026},
            {"bundesland": "NW", "typ": "Herbstferien", "start": "2026-10-12", "end": "2026-10-24", "jahr": 2026},
            {"bundesland": "NW", "typ": "Weihnachtsferien", "start": "2026-12-23", "end": "2027-01-06", "jahr": 2026},
            
            # Hamburg
            {"bundesland": "HH", "typ": "Winterferien", "start": "2026-01-26", "end": "2026-01-30", "jahr": 2026},
            {"bundesland": "HH", "typ": "Osterferien", "start": "2026-03-02", "end": "2026-03-13", "jahr": 2026},
            {"bundesland": "HH", "typ": "Sommerferien", "start": "2026-07-23", "end": "2026-09-02", "jahr": 2026},
            {"bundesland": "HH", "typ": "Herbstferien", "start": "2026-10-12", "end": "2026-10-23", "jahr": 2026},
            {"bundesland": "HH", "typ": "Weihnachtsferien", "start": "2026-12-21", "end": "2027-01-04", "jahr": 2026},
            
            # Weitere Bundesländer können ergänzt werden...
            # BW, BE, BB, HB, HE, MV, NI, RP, SL, SN, ST, SH, TH
        ]
        
        count = 0
        for holiday in holidays_data:
            existing = self.db.query(SchoolHolidays).filter(
                SchoolHolidays.bundesland == holiday['bundesland'],
                SchoolHolidays.ferien_typ == holiday['typ'],
                SchoolHolidays.jahr == holiday['jahr']
            ).first()
            
            if not existing:
                data = SchoolHolidays(
                    bundesland=holiday['bundesland'],
                    ferien_typ=holiday['typ'],
                    start_datum=datetime.fromisoformat(holiday['start']),
                    end_datum=datetime.fromisoformat(holiday['end']),
                    jahr=holiday['jahr']
                )
                self.db.add(data)
                count += 1
        
        self.db.commit()
        logger.info(f"Loaded {count} new school holiday periods")
        return count
    
    def is_holiday(self, datum: date, bundesland: str = None) -> bool:
        """
        Prüfe ob ein Datum in den Schulferien liegt.
        
        Args:
            datum: Zu prüfendes Datum
            bundesland: Optional, spezifisches Bundesland (z.B. 'BY')
        
        Returns:
            True wenn Ferien, sonst False
        """
        query = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= datum,
            SchoolHolidays.end_datum >= datum
        )
        
        if bundesland:
            query = query.filter(SchoolHolidays.bundesland == bundesland)
        
        return query.first() is not None
    
    def get_holidays_for_period(
        self, 
        start_date: date, 
        end_date: date,
        bundesland: str = None
    ) -> list:
        """
        Hole alle Ferienzeiträume für einen Zeitraum.
        
        Args:
            start_date: Start des Zeitraums
            end_date: Ende des Zeitraums
            bundesland: Optional, spezifisches Bundesland
        
        Returns:
            Liste von SchoolHolidays
        """
        query = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= end_date,
            SchoolHolidays.end_datum >= start_date
        )
        
        if bundesland:
            query = query.filter(SchoolHolidays.bundesland == bundesland)
        
        return query.all()
    
    def run_full_import(self):
        """Führe kompletten Import durch."""
        logger.info("Starting school holidays import...")
        
        try:
            count = self.load_holidays_2025_2026()
            
            result = {
                "success": True,
                "holidays_imported": count,
                "timestamp": datetime.utcnow()
            }
            
            logger.info(f"School holidays import completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"School holidays import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow()
            }


# Zusätzliche Funktion für API-Integration (optional)
class SchoolHolidaysAPIService(SchoolHolidaysService):
    """
    Erweiterte Version mit API-Integration.
    
    Mögliche APIs:
    - schulferien.org API
    - ferien-api.de
    - Offizielle Kultusministerien
    """
    
    API_URL = "https://ferien-api.de/api/v1/holidays"
    
    def fetch_from_api(self, jahr: int, bundesland: str = None):
        """
        Hole Schulferien von externer API.
        
        Implementierung folgt bei Bedarf.
        """
        # TODO: API-Integration implementieren
        pass
