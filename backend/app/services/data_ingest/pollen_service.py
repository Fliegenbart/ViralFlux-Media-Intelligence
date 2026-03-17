"""PollenService - DWD Pollen OpenData Ingest."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import re
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import PollenData
from app.services.ml.nowcast_revision import capture_nowcast_snapshots


logger = logging.getLogger(__name__)
settings = get_settings()


REGION_HINTS = {
    "baden-württemberg": ["BW"],
    "bayern": ["BY"],
    "brandenburg und berlin": ["BB", "BE"],
    "mecklenburg-vorpommern": ["MV"],
    "niedersachsen und bremen": ["NI", "HB"],
    "nordrhein-westfalen": ["NW"],
    "rheinland-pfalz und saarland": ["RP", "SL"],
    "sachsen-anhalt": ["ST"],
    "sachsen": ["SN"],
    "schleswig-holstein und hamburg": ["SH", "HH"],
    "thüringen": ["TH"],
    "hessen": ["HE"],
}

DAY_OFFSETS = {
    "today": 0,
    "tomorrow": 1,
    "dayafter_to": 2,
}


class PollenService:
    """Importiert DWD-Pollen-Index (0-3) pro Bundesland-Code."""

    def __init__(self, db: Session):
        self.db = db

    def run_full_import(self, source_url: str | None = None) -> dict[str, Any]:
        url = source_url or settings.DWD_POLLEN_URL
        payload = self._fetch(url)
        if payload is None:
            return {"success": False, "error": "Pollenquelle nicht erreichbar", "source_url": url}

        last_update = self._parse_dwd_timestamp(payload.get("last_update"))
        base_date = (last_update or datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
        content = payload.get("content") or []

        parsed_records: list[dict[str, Any]] = []
        for region_entry in content:
            region_name = str(region_entry.get("region_name") or "").strip().lower()
            region_codes = self._map_region_name_to_codes(region_name)
            if not region_codes:
                continue

            pollen = region_entry.get("Pollen") or {}
            for pollen_type, horizon_map in pollen.items():
                if not isinstance(horizon_map, dict):
                    continue
                for day_key, day_offset in DAY_OFFSETS.items():
                    index_value = self._parse_index(horizon_map.get(day_key))
                    if index_value is None:
                        continue
                    datum = base_date + timedelta(days=day_offset)
                    for region_code in region_codes:
                        parsed_records.append(
                            {
                                "datum": datum,
                                "available_time": last_update or datetime.utcnow(),
                                "region_code": region_code,
                                "pollen_type": str(pollen_type).strip(),
                                "pollen_index": float(index_value),
                                "source": "DWD",
                            }
                        )

        inserted, updated = self._upsert(parsed_records)
        snapshot_rows = capture_nowcast_snapshots(self.db, ["pollen"]).get("pollen", 0)
        latest_date = max((row["datum"] for row in parsed_records), default=None)
        return {
            "success": inserted + updated > 0,
            "source_url": url,
            "records_total": len(parsed_records),
            "inserted": inserted,
            "updated": updated,
            "snapshot_rows": snapshot_rows,
            "regions": sorted({row["region_code"] for row in parsed_records}),
            "pollen_types": sorted({row["pollen_type"] for row in parsed_records}),
            "last_update": last_update.isoformat() if last_update else None,
            "latest_date": latest_date.isoformat() if latest_date else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _fetch(url: str) -> dict[str, Any] | None:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Pollen fetch failed from %s: %s", url, exc)
            return None

    @staticmethod
    def _parse_dwd_timestamp(raw: Any) -> datetime | None:
        if not raw:
            return None
        text = str(raw).replace(" Uhr", "").strip()
        # Beispiel: 2026-02-17 11:00
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_index(raw: Any) -> float | None:
        if raw is None:
            return None
        text = str(raw).strip().lower()
        if not text or text in {"-", "keine", "k.a.", "na", "n/a"}:
            return None
        nums = re.findall(r"\d+(?:[.,]\d+)?", text)
        if not nums:
            return None
        values = [float(item.replace(",", ".")) for item in nums]
        return round(sum(values) / len(values), 3)

    @staticmethod
    def _map_region_name_to_codes(region_name: str) -> list[str]:
        region = (region_name or "").strip().lower()
        if not region:
            return []
        for key, codes in REGION_HINTS.items():
            if key in region:
                return codes
        # fallback for single-state names
        if "berlin" in region:
            return ["BE"]
        if "brandenburg" in region:
            return ["BB"]
        if "hamburg" in region:
            return ["HH"]
        if "bremen" in region:
            return ["HB"]
        return []

    def _upsert(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        if not rows:
            return 0, 0

        # DWD payload kann dieselbe Kombination mehrfach liefern (z. B. durch Teilregionen).
        # Vor DB-Write auf eindeutige Keys reduzieren, sonst kollidiert der Unique-Index.
        deduped: dict[tuple[str, str, datetime], dict[str, Any]] = {}
        for row in rows:
            key = (
                str(row["region_code"]).strip().upper(),
                str(row["pollen_type"]).strip().lower(),
                row["datum"],
            )
            current = deduped.get(key)
            if current is None:
                deduped[key] = row
                continue

            current_ts = current.get("available_time") or datetime.min
            row_ts = row.get("available_time") or datetime.min
            if row_ts >= current_ts:
                deduped[key] = row

        inserted = 0
        updated = 0
        for record in deduped.values():
            existing = (
                self.db.query(PollenData)
                .filter(
                    PollenData.region_code == record["region_code"],
                    PollenData.pollen_type == record["pollen_type"],
                    PollenData.datum == record["datum"],
                )
                .first()
            )
            if existing:
                existing.pollen_index = float(record["pollen_index"])
                existing.available_time = record["available_time"]
                existing.source = record["source"]
                updated += 1
            else:
                self.db.add(PollenData(**record))
                inserted += 1

        self.db.commit()
        return inserted, updated
