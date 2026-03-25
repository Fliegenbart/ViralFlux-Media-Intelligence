"""Public API v1 — IP-geschützte Schnittstelle.

Black-Box-Endpunkte: Input = Parameter, Output = qualitative Bewertung.
Keine Gewichtungen, Schwellenwerte oder Rohdaten-Koeffizienten.
"""

from app.core.time import utc_now
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from datetime import datetime
import re
import logging

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.schemas.public_risk import (
    PublicRiskResponse,
    PublicAllVirusesResponse,
    PublicVirusEntry,
    ResponseMeta,
    Prediction,
    Explanation,
    ContributingFactor,
    RiskLabel,
    ImpactIntensity,
    TrendDirection,
    ConfidenceLevel,
    DriverType,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Valid virus types (whitelist) ──────────────────────────────────────────
VALID_VIRUS_TYPES = {"Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"}

# ─── PLZ regex (German postal codes: 5 digits, 01000-99999) ────────────────
PLZ_PATTERN = re.compile(r"^[0-9]{5}$")


# ─────────────────────────────────────────────────────────────────────────────
# Obfuscation Layer — converts internal precision into qualitative output
# ─────────────────────────────────────────────────────────────────────────────

def _score_to_risk_label(score: float) -> RiskLabel:
    """Map numeric score to qualitative label. Thresholds hidden."""
    if score >= 90:
        return RiskLabel.CRITICAL
    elif score >= 65:
        return RiskLabel.HIGH_ALERT
    elif score >= 30:
        return RiskLabel.ELEVATED
    return RiskLabel.NORMAL


def _score_to_impact(value: float) -> ImpactIntensity:
    """Map 0-1 signal to qualitative impact. Bands are intentionally wide."""
    if value >= 0.75:
        return ImpactIntensity.CRITICAL
    elif value >= 0.45:
        return ImpactIntensity.HIGH
    elif value >= 0.2:
        return ImpactIntensity.MEDIUM
    return ImpactIntensity.LOW


def _value_to_trend(current: float, label: str = "") -> TrendDirection:
    """Derive trend from signal intensity (simplified without history)."""
    if current >= 0.85:
        return TrendDirection.SURGING
    elif current >= 0.5:
        return TrendDirection.RISING
    elif current >= 0.2:
        return TrendDirection.STABLE
    return TrendDirection.DECLINING


def _confidence_to_level(conf_str: str) -> ConfidenceLevel:
    """Map German confidence string to enum."""
    mapping = {
        "Sehr Hoch": ConfidenceLevel.VERY_HIGH,
        "Hoch": ConfidenceLevel.HIGH,
        "Mittel": ConfidenceLevel.MEDIUM,
        "Niedrig": ConfidenceLevel.LOW,
    }
    return mapping.get(conf_str, ConfidenceLevel.MEDIUM)


def _determine_primary_driver(components: dict) -> DriverType:
    """Identify the dominant signal category."""
    layer_to_driver = {
        "bio": DriverType.WASTEWATER_LOAD,
        "market": DriverType.SUPPLY_CHAIN_BOTTLENECK,
        "psycho": DriverType.SEARCH_BEHAVIOR,
        "context": DriverType.ENVIRONMENTAL_CONDITIONS,
    }
    layers = {k: components.get(k, 0) for k in layer_to_driver}
    top = max(layers, key=layers.get)
    return layer_to_driver[top]


def _build_contributing_factors(components: dict) -> list[ContributingFactor]:
    """Build qualitative factor list from component scores."""
    factor_map = [
        ("Wastewater Load", "wastewater"),
        ("Emergency Visits", "notaufnahme"),
        ("Drug Availability", "drug_shortage"),
        ("Search Behavior", "search_trends"),
        ("Weather Conditions", "environment"),
        ("Order Patterns", "order_velocity"),
    ]

    factors = []
    for display_name, key in factor_map:
        value = components.get(key, 0.0)
        factors.append(ContributingFactor(
            factor=display_name,
            impact_intensity=_score_to_impact(value),
            trend=_value_to_trend(value),
        ))

    # Sort: highest impact first
    intensity_order = {
        ImpactIntensity.CRITICAL: 0,
        ImpactIntensity.HIGH: 1,
        ImpactIntensity.MEDIUM: 2,
        ImpactIntensity.LOW: 3,
    }
    factors.sort(key=lambda f: intensity_order.get(f.impact_intensity, 99))

    return factors


def obfuscate_result(internal: dict) -> PublicRiskResponse:
    """Transform internal high-precision result into safe public format.

    All weights, thresholds and formulas are stripped.
    Only qualitative assessments are emitted.
    """
    score = internal.get("final_risk_score", 0)
    components = internal.get("component_scores", {})
    confidence_str = internal.get("confidence_level", "Mittel")

    meta = ResponseMeta(
        timestamp=utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    prediction = Prediction(
        risk_score=int(round(score)),
        risk_label=_score_to_risk_label(score),
        confidence_level=_confidence_to_level(confidence_str),
        validity_period_days=14,
    )

    explanation = Explanation(
        primary_driver=_determine_primary_driver(components),
        contributing_factors=_build_contributing_factors(components),
    )

    return PublicRiskResponse(
        meta=meta,
        prediction=prediction,
        explanation=explanation,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _get_shortage_signals() -> dict | None:
    """Reuse shortage cache from outbreak_score module."""
    try:
        from app.api.outbreak_score import _get_shortage_signals as _inner
        return _inner()
    except Exception:
        return None


@router.get(
    "/risk",
    response_model=PublicRiskResponse,
    summary="Current risk assessment",
    description="Returns a qualitative risk assessment for a given pathogen. "
                "No raw weights, formulas, or threshold values are exposed.",
)
@limiter.limit("50/minute")
async def get_public_risk(
    request: Request,
    virus: str = Query(
        default="Influenza A",
        description="Pathogen type",
        examples=["Influenza A", "RSV A", "SARS-CoV-2"],
    ),
    plz: str = Query(
        default=None,
        description="German postal code (5 digits). Reserved for regional drill-down.",
    ),
    db: Session = Depends(get_db),
):
    # Input sanitization — strict whitelist
    if virus not in VALID_VIRUS_TYPES:
        virus = "Influenza A"

    if plz is not None and not PLZ_PATTERN.match(plz):
        plz = None  # silently ignore invalid PLZ

    from app.services.ml.forecast_decision_service import ForecastDecisionService

    internal = ForecastDecisionService(db).build_legacy_outbreak_score(
        virus_typ=virus,
    )

    return obfuscate_result(internal)


@router.get(
    "/risk/all",
    response_model=PublicAllVirusesResponse,
    summary="Risk assessment for all pathogens",
    description="Returns qualitative risk assessments for all tracked pathogens.",
)
@limiter.limit("50/minute")
async def get_public_risk_all(request: Request, db: Session = Depends(get_db)):
    from app.services.ml.forecast_decision_service import ForecastDecisionService

    internal = ForecastDecisionService(db).build_all_legacy_outbreak_scores(
        virus_types=sorted(VALID_VIRUS_TYPES),
    )

    meta = ResponseMeta(
        timestamp=utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    viruses = {}
    for virus_name, result in internal.get("per_virus", {}).items():
        public = obfuscate_result(result)
        viruses[virus_name] = PublicVirusEntry(
            prediction=public.prediction,
            explanation=public.explanation,
        )

    return PublicAllVirusesResponse(meta=meta, viruses=viruses)
