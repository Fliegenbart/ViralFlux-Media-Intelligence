"""Legacy compatibility shim for the ranking signal service."""

from __future__ import annotations

from app.services.media.ranking_signal_core import (
    DEFAULT_RANKING_SIGNAL_CONFIG,
    DEFAULT_WEIGHTS,
    REGION_CODE_TO_NAME,
    REGION_NAME_TO_CODE,
    RankingSignalService,
    VIRUS_WEIGHTS,
    weather_signal_avg,
)

PEIX_CONFIG = DEFAULT_RANKING_SIGNAL_CONFIG
PeixEpiScoreService = RankingSignalService

__all__ = [
    "DEFAULT_WEIGHTS",
    "PEIX_CONFIG",
    "PeixEpiScoreService",
    "RankingSignalService",
    "REGION_CODE_TO_NAME",
    "REGION_NAME_TO_CODE",
    "VIRUS_WEIGHTS",
    "weather_signal_avg",
]
