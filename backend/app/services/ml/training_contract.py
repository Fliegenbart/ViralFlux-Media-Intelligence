"""Shared training selection and virus-type constants for ML tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.services.ml.forecast_horizon_utils import (
    DEFAULT_FORECAST_REGION,
    SUPPORTED_FORECAST_HORIZONS,
    ensure_supported_horizon,
    normalize_forecast_region,
)
from app.services.ml.regional_panel_utils import ALL_BUNDESLAENDER, normalize_state_code

SUPPORTED_VIRUS_TYPES: tuple[str, ...] = (
    "Influenza A",
    "Influenza B",
    "SARS-CoV-2",
    "RSV A",
)
SUPPORTED_FORECAST_REGIONS: tuple[str, ...] = (DEFAULT_FORECAST_REGION, *ALL_BUNDESLAENDER)

INTERNAL_HISTORY_TEST_MAP: dict[str, list[str]] = {
    "Influenza A": ["influenza a", "influenza-a", "influenza_a"],
    "Influenza B": ["influenza b", "influenza-b", "influenza_b"],
    "SARS-CoV-2": ["sars-cov-2", "sars cov 2", "covid-19", "covid19"],
    "RSV A": ["rsv", "rsv a", "rsv-a", "rsv_a"],
}

_SUPPORTED_VIRUS_LOOKUP = {
    " ".join(virus.lower().replace("-", " ").replace("_", " ").split()): virus
    for virus in SUPPORTED_VIRUS_TYPES
}


@dataclass(frozen=True)
class TrainingSelection:
    """Normalized selection contract for training requests."""

    virus_types: tuple[str, ...]
    mode: str

    @property
    def virus_typ(self) -> str | None:
        if len(self.virus_types) == 1:
            return self.virus_types[0]
        return None


@dataclass(frozen=True)
class ScopeSelection:
    regions: tuple[str, ...]
    horizons: tuple[int, ...]


def normalize_virus_type(value: str) -> str:
    """Normalize a single virus label to the canonical supported name."""
    normalized_key = " ".join(str(value).strip().lower().replace("-", " ").replace("_", " ").split())
    if not normalized_key:
        raise ValueError("virus type must not be empty")

    normalized = _SUPPORTED_VIRUS_LOOKUP.get(normalized_key)
    if not normalized:
        supported = ", ".join(SUPPORTED_VIRUS_TYPES)
        raise ValueError(f"Unsupported virus type '{value}'. Supported values: {supported}")
    return normalized


def normalize_training_selection(
    *,
    virus_typ: str | None = None,
    virus_types: Sequence[str] | None = None,
) -> TrainingSelection:
    """Validate and normalize the public training-selection contract."""
    if virus_typ is not None and virus_types is not None:
        raise ValueError("Provide either virus_typ or virus_types, not both")

    if virus_typ is not None:
        return TrainingSelection(
            virus_types=(normalize_virus_type(virus_typ),),
            mode="single",
        )

    if virus_types is None:
        return TrainingSelection(
            virus_types=SUPPORTED_VIRUS_TYPES,
            mode="all",
        )

    if len(virus_types) == 0:
        raise ValueError("virus_types must not be empty")

    normalized_set = {normalize_virus_type(value) for value in virus_types}
    normalized = tuple(
        virus for virus in SUPPORTED_VIRUS_TYPES if virus in normalized_set
    )
    mode = "all" if normalized == SUPPORTED_VIRUS_TYPES else "subset"
    return TrainingSelection(virus_types=normalized, mode=mode)


def normalize_region_selection(
    *,
    region: str | None = None,
    regions: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Validate and normalize region selectors for direct forecast training."""
    if region is not None and regions is not None:
        raise ValueError("Provide either region or regions, not both")

    if region is None and regions is None:
        return (DEFAULT_FORECAST_REGION,)

    values = [region] if region is not None else list(regions or [])
    if not values:
        raise ValueError("regions must not be empty")

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            raise ValueError("region must not be empty")
        region_code = normalize_forecast_region(text)
        if region_code != DEFAULT_FORECAST_REGION:
            region_code = normalize_state_code(region_code) or normalize_state_code(text) or region_code
        if region_code not in SUPPORTED_FORECAST_REGIONS:
            supported = ", ".join(SUPPORTED_FORECAST_REGIONS)
            raise ValueError(f"Unsupported region '{value}'. Supported values: {supported}")
        if region_code not in seen:
            seen.add(region_code)
            normalized.append(region_code)
    return tuple(normalized)


def normalize_horizon_selection(
    *,
    horizon_days: int | None = None,
    horizon_days_list: Sequence[int] | None = None,
) -> tuple[int, ...]:
    """Validate and normalize direct forecast horizon selectors."""
    if horizon_days is not None and horizon_days_list is not None:
        raise ValueError("Provide either horizon_days or horizon_days_list, not both")

    if horizon_days is None and horizon_days_list is None:
        return tuple(SUPPORTED_FORECAST_HORIZONS)

    values = [horizon_days] if horizon_days is not None else list(horizon_days_list or [])
    if not values:
        raise ValueError("horizon_days_list must not be empty")

    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        horizon = ensure_supported_horizon(int(value))
        if horizon not in seen:
            seen.add(horizon)
            normalized.append(horizon)
    return tuple(sorted(normalized))


def normalize_scope_selection(
    *,
    region: str | None = None,
    regions: Sequence[str] | None = None,
    horizon_days: int | None = None,
    horizon_days_list: Sequence[int] | None = None,
) -> ScopeSelection:
    """Normalize the scoped training contract used by tasks and admin APIs."""
    return ScopeSelection(
        regions=normalize_region_selection(region=region, regions=regions),
        horizons=normalize_horizon_selection(
            horizon_days=horizon_days,
            horizon_days_list=horizon_days_list,
        ),
    )
