"""Public signal response for the external API.

Die Antwort ist bewusst qualitativ und signalorientiert.
"""

from pydantic import BaseModel, Field
from enum import Enum


# ─── Enums (qualitativ, nicht numerisch) ────────────────────────────────────

class SignalLevel(str, Enum):
    LOW = "LOW"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalIntensity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ─── Response Models ────────────────────────────────────────────────────────

class ResponseMeta(BaseModel):
    timestamp: str
    region: str = "DE"


class Prediction(BaseModel):
    signal_index: int = Field(..., ge=0, le=100, description="Aggregated signal index (integer, no decimals)")
    signal_level: SignalLevel
    validity_period_days: int = 14


class SignalFactor(BaseModel):
    factor: str
    signal_intensity: SignalIntensity


class Explanation(BaseModel):
    signal_factors: list[SignalFactor]


class PublicRiskResponse(BaseModel):
    meta: ResponseMeta
    prediction: Prediction
    explanation: Explanation


class PublicAllVirusesResponse(BaseModel):
    meta: ResponseMeta
    viruses: dict[str, "PublicVirusEntry"]


class PublicVirusEntry(BaseModel):
    prediction: Prediction
    explanation: Explanation


# Rebuild for forward refs
PublicAllVirusesResponse.model_rebuild()
