from __future__ import annotations

from typing import Any

from app.core.time import utc_now

JsonDict = dict[str, Any]


def generated_at() -> str:
    return utc_now().isoformat()


def cockpit_ranking_signal(cockpit: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(cockpit or {})
    ranking_signal = payload.get("ranking_signal")
    if isinstance(ranking_signal, dict):
        return ranking_signal
    legacy_signal = payload.get("peix_epi_score")
    if isinstance(legacy_signal, dict):
        return legacy_signal
    return {}
