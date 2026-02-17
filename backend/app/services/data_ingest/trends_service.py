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

    KEYWORDS = [
        "Erkältung",
        "Grippe",
        "Fieber",
        "Corona Test",
        "Husten",
    ]
    AVAILABILITY_DELAY_DAYS = 3

    def __init__(self, db: Session):
        self.db = db

    def fetch_interest_over_time(
        self,
        keywords: list,
        timeframe: str = 'today 3-m',
        geo: str = 'DE'
    ) -> pd.DataFrame:
        """Hole Interest Over Time Daten von Google Trends."""
        logger.info(f"Fetching Google Trends for: {keywords}")

        pytrends = TrendReq(hl='de-DE', tz=60, timeout=(10, 30))
        pytrends.build_payload(kw_list=keywords, timeframe=timeframe, geo=geo)
        df = pytrends.interest_over_time()

        if df.empty:
            logger.warning(f"No data returned for keywords: {keywords}")
            return pd.DataFrame()

        if 'isPartial' in df.columns:
            df = df.drop(columns=['isPartial'])

        logger.info(f"Fetched {len(df)} data points for {len(keywords)} keywords")
        return df

    def import_trends_data(self, df: pd.DataFrame, region: str = 'DE') -> int:
        """Importiere Trends-Daten in die Datenbank."""
        count = 0

        for date, row in df.iterrows():
            available_time = pd.to_datetime(date).to_pydatetime() + timedelta(
                days=self.AVAILABILITY_DELAY_DAYS
            )
            for keyword in df.columns:
                interest_score = row[keyword]
                if pd.isna(interest_score):
                    continue

                existing = self.db.query(GoogleTrendsData).filter(
                    GoogleTrendsData.datum == date,
                    GoogleTrendsData.keyword == keyword,
                    GoogleTrendsData.region == region
                ).first()

                if existing:
                    existing.interest_score = int(interest_score)
                    if getattr(existing, "available_time", None) is None:
                        existing.available_time = available_time
                else:
                    data = GoogleTrendsData(
                        datum=date,
                        available_time=available_time,
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

    def run_full_import(self, months: int = 3) -> dict:
        """Führe Import für alle Keywords durch."""
        logger.info(f"Starting Google Trends import for last {months} months...")

        total_imported = 0
        timeframe = f'today {months}-m'

        try:
            # Google Trends erlaubt max 5 Keywords pro Request
            keyword_chunks = [
                self.KEYWORDS[i:i + 5]
                for i in range(0, len(self.KEYWORDS), 5)
            ]

            for i, keywords in enumerate(keyword_chunks):
                logger.info(f"Processing chunk {i + 1}/{len(keyword_chunks)}: {keywords}")

                try:
                    df = self.fetch_interest_over_time(
                        keywords=keywords,
                        timeframe=timeframe,
                        geo='DE'
                    )

                    if not df.empty:
                        count = self.import_trends_data(df, region='DE')
                        total_imported += count

                except Exception as e:
                    logger.warning(f"Trends chunk {i + 1} failed (might be rate-limited): {e}")

                # Pause zwischen Chunks
                if i < len(keyword_chunks) - 1:
                    time.sleep(15)

            return {
                "success": total_imported > 0,
                "keywords_processed": len(self.KEYWORDS),
                "records_imported": total_imported,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Google Trends import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
