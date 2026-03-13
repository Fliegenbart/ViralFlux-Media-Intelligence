"""Shared validators and constrained types for API endpoints."""

from enum import Enum
from typing import Annotated

from fastapi import Query
from pydantic import AfterValidator

from app.services.ml.training_contract import (
    SUPPORTED_VIRUS_TYPES,
    normalize_virus_type,
)


class VirusTypEnum(str, Enum):
    """Allowed virus type values for API query parameters."""

    INFLUENZA_A = "Influenza A"
    INFLUENZA_B = "Influenza B"
    SARS_COV_2 = "SARS-CoV-2"
    RSV_A = "RSV A"


def validate_virus_typ(value: str) -> str:
    """Normalize and validate virus_typ, raising ValueError for unsupported values."""
    return normalize_virus_type(value)


# Reusable annotated type for virus_typ query parameters
VirusTypQuery = Annotated[
    str,
    Query(
        default="Influenza A",
        description=f"Virus type. Allowed: {', '.join(SUPPORTED_VIRUS_TYPES)}",
    ),
    AfterValidator(validate_virus_typ),
]
