"""Public API v1 for qualitative signal output.

Black-box endpoint: input = parameters, output = qualitative signal assessment.
"""

from app.core.time import utc_now
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
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
    SignalFactor,
    SignalLevel,
    SignalIntensity,
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

def _score_to_signal_level(score: float) -> SignalLevel:
    """Map numeric index to a qualitative signal level."""
    if score >= 90:
        return SignalLevel.CRITICAL
    elif score >= 65:
        return SignalLevel.HIGH
    elif score >= 30:
        return SignalLevel.ELEVATED
    return SignalLevel.LOW


def _score_to_intensity(value: float) -> SignalIntensity:
    """Map 0-1 signal to a qualitative intensity band."""
    if value >= 0.75:
        return SignalIntensity.CRITICAL
    elif value >= 0.45:
        return SignalIntensity.HIGH
    elif value >= 0.2:
        return SignalIntensity.MEDIUM
    return SignalIntensity.LOW


def _build_signal_factors(components: dict) -> list[SignalFactor]:
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
        factors.append(SignalFactor(
            factor=display_name,
            signal_intensity=_score_to_intensity(value),
        ))

    # Sort: highest impact first
    intensity_order = {
        SignalIntensity.CRITICAL: 0,
        SignalIntensity.HIGH: 1,
        SignalIntensity.MEDIUM: 2,
        SignalIntensity.LOW: 3,
    }
    factors.sort(key=lambda f: intensity_order.get(f.signal_intensity, 99))

    return factors


def obfuscate_result(internal: dict) -> PublicRiskResponse:
    """Transform internal result into an honest public signal contract.

    All weights, thresholds and formulas are stripped.
    Only qualitative signal assessments are emitted.
    """
    score = internal.get("decision_signal_index", 0)
    components = internal.get("component_scores", {})

    meta = ResponseMeta(
        timestamp=utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    prediction = Prediction(
        signal_index=int(round(score)),
        signal_level=_score_to_signal_level(score),
        validity_period_days=14,
    )

    explanation = Explanation(
        signal_factors=_build_signal_factors(components),
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
