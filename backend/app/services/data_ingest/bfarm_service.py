"""BfArM Lieferengpass Auto-Pull — Automatisierter Import der BfArM CSV.

Nutzt den bestehenden DrugShortageAnalyzer für Parsing und Signalberechnung.
Signale werden in Redis gecacht (cross-worker safe) und zusätzlich in
die Module-Level-Caches von drug_shortage.py und outbreak_score.py geschrieben.

Datenquelle: https://anwendungen.pharmnet-bund.de/lieferengpassmeldungen/public/csv
- Statischer Link, kein Scraping nötig
- CSV: Semikolon-getrennt, Latin-1 Encoding
"""

from app.core.time import utc_now
import json
import os
import logging
import tempfile
from datetime import datetime

import requests

from app.services.data_ingest.drug_shortage_service import DrugShortageAnalyzer

logger = logging.getLogger(__name__)

REDIS_KEY = "bfarm:signals"
_REDIS_TTL_SECONDS = 6 * 3600  # 6h — täglicher Celery-Beat refresh überlappt

# Per-worker fallback cache (used when Redis is unreachable)
_last_signals: dict | None = None
_last_analyzer: DrugShortageAnalyzer | None = None
_last_refresh_attempt: datetime | None = None
_AUTO_REFRESH_RETRY_MINUTES = 30


def _get_redis():
    """Get Redis connection (best-effort, returns None on failure)."""
    try:
        import redis
        url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        return redis.from_url(url, decode_responses=True, socket_timeout=2)
    except Exception:
        return None


def _store_signals_redis(signals: dict) -> None:
    """Store signals in Redis for cross-worker sharing."""
    try:
        r = _get_redis()
        if r:
            r.setex(REDIS_KEY, _REDIS_TTL_SECONDS, json.dumps(signals, default=str))
    except Exception as exc:
        logger.debug("Redis store failed (non-critical): %s", exc)


def _load_signals_redis() -> dict | None:
    """Load signals from Redis (returns None on miss or error)."""
    try:
        r = _get_redis()
        if r:
            data = r.get(REDIS_KEY)
            if data:
                return json.loads(data)
    except Exception as exc:
        logger.debug("Redis load failed (non-critical): %s", exc)
    return None


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

            # Per-worker cache
            _last_signals = signals
            _last_analyzer = analyzer

            # Cross-worker cache via Redis
            _store_signals_redis(signals)

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
                "timestamp": utc_now().isoformat(),
            }
        except Exception as e:
            logger.error(f"BfArM Import fehlgeschlagen: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


def get_cached_signals() -> dict | None:
    """Gibt gecachte BfArM-Signale zurück.

    Reihenfolge: per-worker → Redis → Auto-Refresh (einmal pro 30 Min).
    """
    global _last_signals, _last_refresh_attempt

    # 1. Per-worker in-process cache
    if _last_signals is not None:
        return _last_signals

    # 2. Cross-worker Redis cache
    redis_signals = _load_signals_redis()
    if redis_signals is not None:
        _last_signals = redis_signals
        return redis_signals

    # 3. Auto-refresh (rate-limited)
    now = utc_now()
    if _last_refresh_attempt is not None:
        age_minutes = (now - _last_refresh_attempt).total_seconds() / 60.0
        if age_minutes < _AUTO_REFRESH_RETRY_MINUTES:
            return None

    _last_refresh_attempt = now

    try:
        logger.info("BfArM cache miss (worker + Redis): starte Auto-Refresh.")
        result = BfarmIngestionService().run_full_import()
        if result.get("success"):
            return _last_signals
        logger.warning("BfArM Auto-Refresh fehlgeschlagen: %s", result)
    except Exception as exc:
        logger.warning("BfArM Auto-Refresh Exception: %s", exc)

    return None
