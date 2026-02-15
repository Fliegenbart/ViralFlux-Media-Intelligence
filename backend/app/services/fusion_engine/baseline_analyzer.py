"""Baseline Analyzer — Historische Labordaten als Ground Truth.

Importiert interne Labordaten (Positivraten), berechnet saisonale
Baselines pro Kalenderwoche und erkennt Anomalien gegenüber
dem historischen Normalzustand.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.models.database import GanzimmunData

logger = logging.getLogger(__name__)


class BaselineAnalyzer:
    """Analyse interner historischer Labordaten (Ground Truth)."""

    def __init__(self, db: Session):
        self.db = db

    def ingest_internal_history(self, df: pd.DataFrame) -> dict:
        """Importiere lab_history.csv in GanzimmunData.

        Erwartete Spalten: datum, test_type, total_tests, positive_tests
        Optional: region
        """
        count_new = 0
        count_updated = 0

        for _, row in df.iterrows():
            datum = pd.to_datetime(row['datum'])
            test_typ = row['test_type']
            total = int(row['total_tests'])
            positive = int(row['positive_tests'])
            region = row.get('region', None)

            if total <= 0:
                continue

            existing = self.db.query(GanzimmunData).filter(
                GanzimmunData.datum == datum,
                GanzimmunData.test_typ == test_typ,
            ).first()

            if existing:
                existing.anzahl_tests = total
                existing.positive_ergebnisse = positive
                if region:
                    existing.region = region
                count_updated += 1
            else:
                entry = GanzimmunData(
                    datum=datum,
                    test_typ=test_typ,
                    anzahl_tests=total,
                    positive_ergebnisse=positive,
                    region=region,
                )
                self.db.add(entry)
                count_new += 1

        self.db.commit()
        logger.info(f"Lab-History Import: {count_new} neu, {count_updated} aktualisiert")
        return {"new": count_new, "updated": count_updated, "total": count_new + count_updated}

    def calculate_seasonal_baseline(self, test_typ: str = None) -> dict:
        """Saisonales Profil aus 10 Jahren historischer Daten.

        Gruppiert nach Kalenderwoche (1-52).
        Berechnet Mean + StdDev der Positivrate pro Woche.
        """
        query = self.db.query(GanzimmunData).filter(
            GanzimmunData.anzahl_tests > 0,
        )
        if test_typ:
            query = query.filter(GanzimmunData.test_typ == test_typ)

        data = query.all()

        if not data:
            return {"error": "Keine internen Labordaten vorhanden", "weeks": {}}

        weekly_rates: dict[int, list[float]] = {}
        for d in data:
            week = d.datum.isocalendar()[1]
            rate = (d.positive_ergebnisse or 0) / d.anzahl_tests
            weekly_rates.setdefault(week, []).append(rate)

        baseline = {}
        for week in range(1, 53):
            rates = weekly_rates.get(week, [])
            if rates:
                baseline[week] = {
                    "mean": round(float(np.mean(rates)), 4),
                    "std": round(float(np.std(rates)), 4),
                    "n_samples": len(rates),
                    "min": round(float(np.min(rates)), 4),
                    "max": round(float(np.max(rates)), 4),
                }
            else:
                baseline[week] = {"mean": 0, "std": 0, "n_samples": 0}

        return {
            "test_typ": test_typ or "alle",
            "total_records": len(data),
            "weeks": baseline,
        }

    def get_anomaly_factor(
        self,
        current_week: int,
        current_signal: float,
        test_typ: str = None,
    ) -> dict:
        """Delta-Analyse: Abweichung vom historischen Normalzustand.

        current_signal: normalisierter Wert (0-1)
        Returns: z-score, adjustment factor, und explanation.
        """
        baseline = self.calculate_seasonal_baseline(test_typ)
        week_data = baseline.get('weeks', {}).get(current_week)

        if not week_data or week_data['n_samples'] < 2:
            return {
                "z_score": 0,
                "adjustment": 1.0,
                "explanation": f"Keine Baseline für KW{current_week}",
                "is_black_swan": False,
            }

        mean = week_data['mean']
        std = week_data['std'] or 0.01
        z_score = (current_signal - mean) / std

        if z_score > 2.0:
            return {
                "z_score": round(z_score, 2),
                "adjustment": 1.0,  # Vertraue dem Signal
                "explanation": f"Black Swan: Signal {z_score:.1f}\u03c3 \u00fcber Baseline",
                "is_black_swan": True,
            }
        elif z_score < -1.0:
            suppression = min(0.3, abs(z_score) * 0.15)
            return {
                "z_score": round(z_score, 2),
                "adjustment": round(1 - suppression, 3),
                "explanation": f"False Alarm Suppression: {suppression:.0%} Reduktion",
                "is_black_swan": False,
            }

        return {
            "z_score": round(z_score, 2),
            "adjustment": 1.0,
            "explanation": f"Normal (z={z_score:.1f})",
            "is_black_swan": False,
        }
