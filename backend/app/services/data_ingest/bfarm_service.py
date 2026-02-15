"""BfArM Lieferengpass Auto-Pull — Automatisierter Import der BfArM CSV.

Nutzt den bestehenden DrugShortageAnalyzer für Parsing und Signalberechnung.
Aktualisiert die globalen Caches in drug_shortage.py und outbreak_score.py,
damit der Outbreak Score sofort BfArM-Daten bekommt.

Datenquelle: https://anwendungen.pharmnet-bund.de/lieferengpassmeldungen/public/csv
- Statischer Link, kein Scraping nötig
- CSV: Semikolon-getrennt, Latin-1 Encoding
"""

import requests
import tempfile
import os
import logging
from datetime import datetime

from app.services.data_ingest.drug_shortage_service import DrugShortageAnalyzer

logger = logging.getLogger(__name__)

# Globaler Cache für die letzte Analyse
_last_signals: dict | None = None
_last_analyzer: DrugShortageAnalyzer | None = None


class BfarmIngestionService:
    """Automatisierter Import der BfArM Lieferengpass-CSV."""

    CSV_URL = "https://anwendungen.pharmnet-bund.de/lieferengpassmeldungen/public/csv"

    def run_full_import(self) -> dict:
        """Zieht aktuelle CSV, analysiert via DrugShortageAnalyzer, aktualisiert Caches."""
        global _last_signals, _last_analyzer

        logger.info(f"Starte BfArM CSV-Download von {self.CSV_URL}")

        response = requests.get(self.CSV_URL, timeout=120)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        try:
            analyzer = DrugShortageAnalyzer()
            analyzer.load_and_clean(tmp_path)
            signals = analyzer.get_infection_signals()

            # Globalen Cache aktualisieren
            _last_signals = signals
            _last_analyzer = analyzer

            # Singleton in drug_shortage.py aktualisieren (für /signals Endpoint)
            import app.api.drug_shortage as ds_module
            ds_module._analyzer = analyzer

            # Cache in outbreak_score.py aktualisieren
            import app.api.outbreak_score as os_module
            os_module._cached_shortage_signals = signals

            count = len(analyzer.df_filtered) if analyzer.df_filtered is not None else 0
            logger.info(
                f"BfArM Import erfolgreich: {count} relevante Meldungen, "
                f"Risk Score: {signals.get('current_risk_score')}"
            )

            return {
                "success": True,
                "total_records": len(analyzer.df) if analyzer.df is not None else 0,
                "relevant_records": count,
                "risk_score": signals.get('current_risk_score', 0),
                "wave_type": signals.get('wave_type', 'None'),
                "high_demand_shortages": signals.get('high_demand_shortages', 0),
                "pediatric_alert": signals.get('pediatric_alert', False),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"BfArM Import fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


def get_cached_signals() -> dict | None:
    """Gibt die zuletzt gecachten BfArM-Signale zurück."""
    return _last_signals
