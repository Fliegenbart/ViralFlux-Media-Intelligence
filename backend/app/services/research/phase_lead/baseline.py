"""Seasonal baseline interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class SeasonalBaseline:
    """Baseline on the log-incidence scale."""

    def value(self, region_id: str, pathogen: str, day: date) -> float:
        raise NotImplementedError


@dataclass
class ConstantBaseline(SeasonalBaseline):
    log_value: float = 0.0

    def value(self, region_id: str, pathogen: str, day: date) -> float:
        return float(self.log_value)


@dataclass
class TableBaseline(SeasonalBaseline):
    values: dict[tuple[str, str, date], float]
    fallback: float = 0.0

    def value(self, region_id: str, pathogen: str, day: date) -> float:
        return float(self.values.get((region_id, pathogen, day), self.fallback))
