from pytrends.request import TrendReq
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
import time

from app.models.database import GoogleTrendsData

logger = logging.getLogger(__name__)


class GoogleTrendsService:
    """Service zum Abrufen von Google Trends Daten."""
    
    # Keywords für Atemwegserkrankungen
    KEYWORDS = [
        "Erkältung",
        "Grippe",
        "Schnupfen",
        "Fieber",
        "Halsschmerzen",
        "Hausmittel Erkältung",
        "Corona Test",
        "Grippe Symptome",
        "Husten",
        "Kopfschmerzen Fieber"
    ]
    
    def __init__(self, db: Session):
        self.db = db
        self.pytrends = TrendReq(hl='de-DE', tz=60)  # Deutschland, MEZ
    
    def fetch_interest_over_time(
        self, 
        keywords: list[str], 
        timeframe: str = 'today 3-m',
        geo: str = 'DE'
    ) -> pd.DataFrame:
        """
        Hole Interest Over Time Daten von Google Trends.
        
        Args:
            keywords: Liste von Suchbegriffen (max 5 pro Request)
            timeframe: Zeitrahmen (z.B. 'today 3-m', 'today 12-m')
            geo: Land-Code (DE = Deutschland)
        """
        logger.info(f"Fetching Google Trends for keywords: {keywords}")
        
        try:
            # Build payload
            self.pytrends.build_payload(
                kw_list=keywords,
                timeframe=timeframe,
                geo=geo
            )
            
            # Get data
            df = self.pytrends.interest_over_time()
            
            if df.empty:
                logger.warning(f"No data returned for keywords: {keywords}")
                return pd.DataFrame()
            
            # Remove 'isPartial' column if exists
            if 'isPartial' in df.columns:
                df = df.drop(columns=['isPartial'])
            
            logger.info(f"Fetched {len(df)} data points for {len(keywords)} keywords")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching Google Trends: {e}")
            raise
    
    def import_trends_data(self, df: pd.DataFrame, region: str = 'DE'):
        """Importiere Trends-Daten in die Datenbank."""
        count = 0
        
        # DataFrame hat Keywords als Spalten, Datum als Index
        for date, row in df.iterrows():
            for keyword in df.columns:
                interest_score = row[keyword]
                
                # Skip if no data
                if pd.isna(interest_score):
                    continue
                
                # Check if already exists
                existing = self.db.query(GoogleTrendsData).filter(
                    GoogleTrendsData.datum == date,
                    GoogleTrendsData.keyword == keyword,
                    GoogleTrendsData.region == region
                ).first()
                
                if existing:
                    existing.interest_score = int(interest_score)
                else:
                    data = GoogleTrendsData(
                        datum=date,
                        keyword=keyword,
                        region=region,
                        interest_score=int(interest_score),
                        is_partial=False
                    )
                    self.db.add(data)
                    count += 1
        
        self.db.commit()
        logger.info(f"Imported {count} new Google Trends records")
        return count
    
    def run_full_import(self, months: int = 3):
        """
        Führe kompletten Import für alle Keywords durch.
        
        Args:
            months: Anzahl Monate zurück (max 5 Keywords pro Request)
        """
        logger.info(f"Starting Google Trends import for last {months} months...")
        
        total_imported = 0
        timeframe = f'today {months}-m'
        
        try:
            # Google Trends erlaubt max 5 Keywords pro Request
            # Wir splitten die Keywords in 5er-Gruppen
            keyword_chunks = [
                self.KEYWORDS[i:i+5] 
                for i in range(0, len(self.KEYWORDS), 5)
            ]
            
            for i, keywords in enumerate(keyword_chunks):
                logger.info(f"Processing keyword chunk {i+1}/{len(keyword_chunks)}: {keywords}")
                
                # Fetch data
                df = self.fetch_interest_over_time(
                    keywords=keywords,
                    timeframe=timeframe,
                    geo='DE'
                )
                
                if not df.empty:
                    count = self.import_trends_data(df, region='DE')
                    total_imported += count
                
                # Rate limiting: 60 Sekunden Pause nach jedem Request
                # Google Trends sperrt bei zu vielen Requests
                if i < len(keyword_chunks) - 1:
                    logger.info("Waiting 60 seconds to avoid rate limiting...")
                    time.sleep(60)
            
            result = {
                "success": True,
                "keywords_processed": len(self.KEYWORDS),
                "records_imported": total_imported,
                "timeframe": timeframe,
                "timestamp": datetime.utcnow()
            }
            
            logger.info(f"Google Trends import completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Google Trends import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow()
            }
    
    def get_related_queries(self, keyword: str) -> dict:
        """
        Hole verwandte Suchanfragen für ein Keyword.
        Nützlich für Keyword-Discovery.
        """
        try:
            self.pytrends.build_payload(
                kw_list=[keyword],
                timeframe='today 3-m',
                geo='DE'
            )
            
            related = self.pytrends.related_queries()
            return related[keyword]
            
        except Exception as e:
            logger.error(f"Error fetching related queries: {e}")
            return {}
