"""Order Signal Analyzer — ERP-Bestelldaten als Fallback-Indikator.

Nutzt Bestellgeschwindigkeit (Order Velocity) als Proxy für
das Infektionsgeschehen, wenn echte Labordaten fehlen oder verzögert sind.

Logik: Bestellmenge ~ Verbrauch ~ Infektionsgeschehen
Bulk-Filter entfernt Stockpiling-Rauschen.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from app.models.database import GanzimmunData

logger = logging.getLogger(__name__)


class OrderSignalAnalyzer:
    """Analysiert Bestelldaten aus dem ERP-System."""

    def __init__(self, db: Session):
        self.db = db

    def ingest_orders(self, df: pd.DataFrame) -> dict:
        """Importiere orders.csv in GanzimmunData.extra_data.

        Erwartete Spalten: order_date, article_id, quantity, customer_id
        """
        count = 0

        # Median pro Artikel berechnen (für Bulk-Filter)
        medians = df.groupby('article_id')['quantity'].median().to_dict()

        for _, row in df.iterrows():
            datum = pd.to_datetime(row['order_date'])
            article_id = str(row['article_id'])
            quantity = int(row['quantity'])
            customer_id = str(row.get('customer_id', ''))

            # Bulk-Filter: > 5x Median markieren
            median_qty = medians.get(article_id, quantity)
            is_stockpile = quantity > (5 * median_qty) if median_qty > 0 else False

            entry = GanzimmunData(
                datum=datum,
                test_typ=article_id,
                anzahl_tests=quantity,
                positive_ergebnisse=None,  # Keine Testergebnisse bei Bestellungen
                extra_data={
                    'source': 'erp_orders',
                    'order_quantity': quantity,
                    'customer_id': customer_id,
                    'is_stockpile': is_stockpile,
                    'median_quantity': float(median_qty),
                },
            )
            self.db.add(entry)
            count += 1

        self.db.commit()
        logger.info(f"ERP Order Import: {count} Bestellungen importiert")
        return {"imported": count}

    def calculate_order_velocity(self, article_id: str = None) -> dict:
        """Bestellgeschwindigkeit berechnen (Akut-Indikator).

        Ignoriert is_stockpile Zeilen.
        Berechnet wöchentliche Velocity: (diese_Woche - letzte_Woche) / letzte_Woche
        """
        four_weeks_ago = datetime.now() - timedelta(days=28)

        query = self.db.query(GanzimmunData).filter(
            GanzimmunData.datum >= four_weeks_ago,
            GanzimmunData.extra_data.isnot(None),
        )
        if article_id:
            query = query.filter(GanzimmunData.test_typ == article_id)

        orders = query.all()

        if not orders:
            return {"velocity": 0.0, "alert_level": "none", "data_points": 0}

        # Nach Woche gruppieren (ohne Stockpiling)
        weekly: dict[int, int] = {}
        for o in orders:
            extra = o.extra_data or {}
            if extra.get('is_stockpile', False):
                continue
            week = o.datum.isocalendar()[1]
            qty = extra.get('order_quantity', o.anzahl_tests or 0)
            weekly[week] = weekly.get(week, 0) + qty

        if len(weekly) < 2:
            return {"velocity": 0.0, "alert_level": "none", "data_points": len(weekly)}

        sorted_weeks = sorted(weekly.keys())
        current = weekly[sorted_weeks[-1]]
        previous = weekly[sorted_weeks[-2]]

        if previous > 0:
            velocity = (current - previous) / previous
        else:
            velocity = 0.0

        if velocity > 0.5:
            alert = "red"
        elif velocity > 0.2:
            alert = "yellow"
        else:
            alert = "green"

        return {
            "velocity": round(velocity, 3),
            "alert_level": alert,
            "current_week_orders": current,
            "previous_week_orders": previous,
            "data_points": len(weekly),
            "weeks_analyzed": sorted_weeks,
        }

    def get_summary(self) -> dict:
        """Zusammenfassung aller Artikel-Velocities."""
        four_weeks_ago = datetime.now() - timedelta(days=28)

        articles = self.db.query(GanzimmunData.test_typ).filter(
            GanzimmunData.datum >= four_weeks_ago,
            GanzimmunData.extra_data.isnot(None),
        ).distinct().all()

        summaries = {}
        red_alerts = 0
        yellow_alerts = 0

        for (article_id,) in articles:
            vel = self.calculate_order_velocity(article_id)
            summaries[article_id] = vel
            if vel['alert_level'] == 'red':
                red_alerts += 1
            elif vel['alert_level'] == 'yellow':
                yellow_alerts += 1

        return {
            "articles": summaries,
            "red_alerts": red_alerts,
            "yellow_alerts": yellow_alerts,
            "total_articles": len(articles),
        }
