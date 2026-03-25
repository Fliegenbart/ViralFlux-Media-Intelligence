"""Schulferien-Service — Automatischer Import via schulferien-api.de (v2).

Lädt Schulferien für alle 16 Bundesländer (2022-2028).
API: https://schulferien-api.de/api/v2/{year}
Docs: https://github.com/maxleistner/deutsche-schulferien-api
"""

from app.core.time import utc_now
import requests
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
import logging

from app.models.database import SchoolHolidays

logger = logging.getLogger(__name__)

API_BASE = "https://schulferien-api.de/api/v2"

ALL_STATES = [
    "BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV",
    "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH",
]


class SchoolHolidaysService:
    """Schulferien-Service mit automatischem API-Import (schulferien-api.de v2)."""

    def __init__(self, db: Session):
        self.db = db

    def fetch_year(self, year: int) -> list[dict]:
        """Alle Ferien eines Jahres für alle Bundesländer in einem Call."""
        url = f"{API_BASE}/{year}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"schulferien-api.de Abruf fehlgeschlagen ({year}): {e}")
            return []

    def import_year(self, year: int) -> int:
        """Ferien eines Jahres importieren (alle Bundesländer, mit Upsert)."""
        entries = self.fetch_year(year)
        if not entries:
            return 0

        count_new = 0

        for entry in entries:
            state_code = entry.get("stateCode", "")
            # name_cp ist der capitalized Name ("Osterferien"), name ist lowercase
            ferien_typ = entry.get("name_cp", entry.get("name", "Sonstige"))

            start_str = entry.get("start", "")[:10]
            end_str = entry.get("end", "")[:10]

            try:
                start_datum = datetime.fromisoformat(start_str)
                end_datum = datetime.fromisoformat(end_str)
            except (ValueError, TypeError):
                logger.warning(f"Ungültiges Datum: {start_str} / {end_str}")
                continue

            if not state_code or state_code not in ALL_STATES:
                continue

            # Upsert: Match auf Bundesland + Typ + Jahr + Start
            # (manche Bundesländer haben 2 Herbstferien-Einträge etc.)
            existing = self.db.query(SchoolHolidays).filter(
                SchoolHolidays.bundesland == state_code,
                SchoolHolidays.ferien_typ == ferien_typ,
                SchoolHolidays.jahr == year,
                SchoolHolidays.start_datum == start_datum,
            ).first()

            if existing:
                if existing.end_datum != end_datum:
                    existing.end_datum = end_datum
            else:
                self.db.add(SchoolHolidays(
                    bundesland=state_code,
                    ferien_typ=ferien_typ,
                    start_datum=start_datum,
                    end_datum=end_datum,
                    jahr=year,
                ))
                count_new += 1

        self.db.commit()
        return count_new

    def run_full_import(self, years: list[int] = None) -> dict:
        """Alle Bundesländer für gewünschte Jahre importieren.

        Default: Vorjahr + aktuelles Jahr + nächstes Jahr.
        """
        if years is None:
            current_year = datetime.now().year
            years = [current_year - 1, current_year, current_year + 1]

        logger.info(f"Schulferien-Import: Jahre {years} (schulferien-api.de v2)")

        total_new = 0
        errors = []

        for year in years:
            try:
                count = self.import_year(year)
                total_new += count
                logger.info(f"Schulferien {year}: {count} neue Einträge")
            except Exception as e:
                logger.error(f"Import fehlgeschlagen {year}: {e}")
                errors.append(f"{year}: {str(e)}")
                self.db.rollback()

        total_in_db = self.db.query(SchoolHolidays).count()

        # Aufschlüsselung pro Bundesland
        from sqlalchemy import func
        per_state = dict(
            self.db.query(
                SchoolHolidays.bundesland,
                func.count(SchoolHolidays.id),
            ).group_by(SchoolHolidays.bundesland).all()
        )

        result = {
            "success": len(errors) == 0,
            "years": years,
            "new_entries": total_new,
            "total_in_db": total_in_db,
            "states_covered": len(per_state),
            "per_state": per_state,
            "errors": errors if errors else None,
            "timestamp": utc_now().isoformat(),
        }

        logger.info(
            f"Schulferien-Import abgeschlossen: {total_new} neu, "
            f"{total_in_db} gesamt, {len(per_state)} Bundesländer"
        )
        return result

    def is_holiday(self, datum: date, bundesland: str = None) -> bool:
        """Prüfe ob ein Datum in den Schulferien liegt."""
        query = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= datum,
            SchoolHolidays.end_datum >= datum,
        )
        if bundesland:
            query = query.filter(SchoolHolidays.bundesland == bundesland)
        return query.first() is not None

    def is_school_start(self, days_window: int = 7) -> bool:
        """True wenn in irgendeinem Bundesland Ferien innerhalb der letzten N Tage endeten."""
        now = datetime.now()
        window_start = now - timedelta(days=days_window)

        count = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.end_datum >= window_start,
            SchoolHolidays.end_datum <= now,
        ).count()

        return count > 0

    def get_upcoming_school_starts(self, days_ahead: int = 30) -> list[dict]:
        """Kommende Ferienenden (= Schulstarts) in den nächsten N Tagen."""
        now = datetime.now()
        future = now + timedelta(days=days_ahead)

        entries = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.end_datum >= now,
            SchoolHolidays.end_datum <= future,
        ).order_by(SchoolHolidays.end_datum.asc()).all()

        return [
            {
                "bundesland": e.bundesland,
                "ferien_typ": e.ferien_typ,
                "end_datum": e.end_datum.isoformat(),
                "school_start": (e.end_datum + timedelta(days=1)).strftime("%Y-%m-%d"),
                "days_until": (e.end_datum - now).days,
            }
            for e in entries
        ]

    def get_holidays_for_period(
        self, start_date: date, end_date: date, bundesland: str = None
    ) -> list:
        """Alle Ferienzeiträume für einen Zeitraum."""
        query = self.db.query(SchoolHolidays).filter(
            SchoolHolidays.start_datum <= end_date,
            SchoolHolidays.end_datum >= start_date,
        )
        if bundesland:
            query = query.filter(SchoolHolidays.bundesland == bundesland)
        return query.all()
