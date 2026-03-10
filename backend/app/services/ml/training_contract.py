"""Shared training selection and virus-type constants for ML tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

SUPPORTED_VIRUS_TYPES: tuple[str, ...] = (
    "Influenza A",
    "Influenza B",
    "SARS-CoV-2",
    "RSV A",
)

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
