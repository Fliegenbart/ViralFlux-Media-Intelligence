"""Public Risk Response — IP-geschützte API-Antwort.

Dieses Schema ist die "Black Box"-Schnittstelle nach außen.
Keine Gewichtungen, keine Schwellenwerte, keine Rohdaten-Koeffizienten.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ─── Enums (qualitativ, nicht numerisch) ────────────────────────────────────

class RiskLabel(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH_ALERT = "HIGH_ALERT"
    CRITICAL = "CRITICAL"


class ImpactIntensity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrendDirection(str, Enum):
    DECLINING = "DECLINING"
    STABLE = "STABLE"
    RISING = "RISING"
    SURGING = "SURGING"


class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class DriverType(str, Enum):
    WASTEWATER_LOAD = "WASTEWATER_LOAD"
    SUPPLY_CHAIN_BOTTLENECK = "SUPPLY_CHAIN_BOTTLENECK"
    SEARCH_BEHAVIOR = "SEARCH_BEHAVIOR"
    ENVIRONMENTAL_CONDITIONS = "ENVIRONMENTAL_CONDITIONS"
    SEASONAL_PATTERN = "SEASONAL_PATTERN"


# ─── Response Models ────────────────────────────────────────────────────────

class ResponseMeta(BaseModel):
    timestamp: str
    region: str = "DE"
    copyright: str = "Powered by VIRAL FLUX Core \u00a9 2026 \u2014 Algorithm proprietary."


class Prediction(BaseModel):
    risk_score: int = Field(..., ge=0, le=100, description="Aggregated risk (integer, no decimals)")
    risk_label: RiskLabel
    confidence_level: ConfidenceLevel
    validity_period_days: int = 14


class ContributingFactor(BaseModel):
    factor: str
    impact_intensity: ImpactIntensity
    trend: TrendDirection


class Explanation(BaseModel):
    primary_driver: DriverType
    contributing_factors: list[ContributingFactor]


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
